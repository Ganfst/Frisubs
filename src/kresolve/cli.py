"""CLI de kresolve (typer). Ejecuta ``kresolve --help`` para ver los comandos."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated, Optional

import typer

from . import __version__
from .config import PROJECT_ROOT, Config

app = typer.Typer(add_completion=False, no_args_is_help=True, rich_markup_mode=None,
                  help="Karaoke editable en DaVinci Resolve: audio -> Whisper -> JSON -> clips Text+.")
_state: dict = {"config": None}


def cfg() -> Config:
    if _state.get("cfg") is None:
        _state["cfg"] = Config.load(_state["config"])
    return _state["cfg"]


def echo(msg: str = "") -> None:
    typer.echo(msg)


def fail(msg: str, code: int = 1):
    typer.echo(f"ERROR: {msg}", err=True)
    raise typer.Exit(code)


@app.callback()
def _main(config: Annotated[Optional[Path], typer.Option("--config", "-c", help="Ruta a config.yaml")] = None,
          version: Annotated[bool, typer.Option("--version", help="Muestra la versión")] = False):
    _state["config"] = config
    if version:
        echo(f"kresolve {__version__}")
        raise typer.Exit()


# ------------------------------------------------------------------ audio
@app.command("extract-audio")
def extract_audio(video: Path,
                  out: Annotated[Optional[Path], typer.Option(help="WAV de salida")] = None):
    """Extrae el audio de un archivo de vídeo/audio con ffmpeg (sin Resolve)."""
    from .overlay import ffmpeg_exe
    c = cfg()
    if not video.is_file():
        fail(f"No existe {video}")
    out = out or c.work_file(str(c.section("resolve").get("audio_name") or "kresolve_audio") + ".wav")
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
           "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out)]
    subprocess.run(cmd, check=True)
    meta = out.with_name(out.stem + ".meta.json")
    if meta.exists():
        meta.unlink()   # el meta de un render anterior de Resolve ya no aplica
    echo(f"Audio: {out}")
    echo("Nota: los tiempos serán relativos al inicio de ESTE archivo. Si en la timeline el clip no empieza")
    echo("en el primer frame, usa 'kresolve 1 - Exportar audio' desde Resolve en su lugar.")


@app.command("export-audio")
def export_audio():
    """Renderiza el audio de la timeline activa (Resolve Studio, scripting externo)."""
    from .resolve.audio_export import export_timeline_audio
    from .resolve.client import ResolveClient
    c = cfg()
    r = c.section("resolve")
    client = ResolveClient(install_dir=r.get("install_dir"))
    export_timeline_audio(client, c.work_dir, str(r.get("audio_name") or "kresolve_audio"),
                          bool(r.get("use_in_out")), log=echo)


# ------------------------------------------------------------ transcribir
@app.command()
def transcribe(audio: Path,
               model: Annotated[Optional[str], typer.Option(help="Modelo Whisper (large-v3, medium, small...)")] = None,
               language: Annotated[Optional[str], typer.Option(help="Idioma (es, en...) o 'auto'")] = None,
               device: Annotated[Optional[str], typer.Option(help="auto | cuda | cpu")] = None,
               out: Annotated[Optional[Path], typer.Option(help="JSON de salida")] = None,
               pause_on_error: Annotated[bool, typer.Option(hidden=True)] = False):
    """Transcribe un audio -> work/transcript.json (+ .srt)."""
    from .pipeline import transcribe_audio
    try:
        c = cfg()
        t0 = time.time()

        def progress(frac, text):
            echo(f"[{frac * 100:5.1f}%] {text}")

        t, paths = transcribe_audio(c, audio, language=language or "config", model=model, device=device,
                                    out=out, log=echo, progress=progress)
        n_words = sum(len(s.words) for s in t.segments)
        echo(f"\n{len(t.segments)} segmentos, {n_words} palabras, idioma={t.language}, "
             f"{time.time() - t0:.0f} s ({t.meta.get('device')})")
        for kind, p in paths.items():
            echo(f"  {kind}: {p}")
        echo("Siguiente: corrige el JSON si hace falta y ejecuta build-titles (o 'kresolve 3 - Crear titulos').")
        if pause_on_error:
            time.sleep(3)
    except Exception as exc:
        if not pause_on_error:
            raise
        import traceback
        traceback.print_exc()
        echo(f"\nERROR: {exc}")
        input("Pulsa Enter para cerrar esta ventana...")
        raise typer.Exit(1)


# ----------------------------------------------------------- plan / subs
@app.command()
def plan(transcript: Path,
         out: Annotated[Optional[Path], typer.Option(help="plan.json de salida")] = None,
         strategy: Annotated[Optional[str], typer.Option(help="per_word | per_line | per_line_single | sliding")] = None,
         style: Annotated[Optional[str], typer.Option(help="Preset de styles/presets.yaml")] = None):
    """Agrupa la transcripción y escribe el plan que consume Resolve (work/plan.json)."""
    from .exporters.json_io import save_plan
    from .pipeline import build_plan, load
    c = cfg()
    t = load(c, transcript, log=lambda m: typer.echo(m, err=True))
    p = build_plan(c, t, strategy, style)
    out = save_plan(p, out or c.work_file("plan.json"))
    layers = {}
    for clip in p["clips"]:
        layers[clip.layer] = layers.get(clip.layer, 0) + 1
    typer.echo(f"Plan: {out} | estrategia={p['strategy']} | estilo={p['style']['name']} | clips={layers}", err=True)


@app.command()
def subs(transcript: Path,
         ass: Annotated[bool, typer.Option("--ass/--no-ass", help="Generar también .ass")] = True):
    """Regenera .srt (y .ass) a partir del JSON, por ejemplo después de corregirlo."""
    from .exporters.srt import save_srt
    from .overlay import write_ass
    from .pipeline import group_clips, load
    from .planning import transform_clips
    c = cfg()
    t = load(c, transcript)
    echo(f"SRT: {save_srt(t, transcript.with_suffix('.srt'), c.grouping_options)}")
    if ass:
        ov = c.section("overlay")
        style = c.style()
        clips = transform_clips(group_clips(c, t), style)
        echo(f"ASS: {write_ass(clips, style, transcript.with_suffix('.ass'), int(ov.get('width') or 1920), int(ov.get('height') or 1080))}")


# ---------------------------------------------------------------- Resolve
@app.command("build-titles")
def build_titles(transcript: Path,
                 strategy: Annotated[Optional[str], typer.Option(help="Sobrescribe grouping.strategy")] = None):
    """Crea los Text+ en la timeline activa (Resolve Studio, scripting externo)."""
    from .pipeline import build_titles as _build, load
    from .resolve.client import ResolveClient
    c = cfg()
    t = load(c, transcript)
    client = ResolveClient(install_dir=c.section("resolve").get("install_dir"))
    echo(f"{client.product} {client.version} | timeline '{client.timeline_name}' | {client.fps_raw} fps")
    report = _build(c, client, t, strategy, log=echo)
    echo(report.summary())


@app.command("clear-titles")
def clear_titles(delete_tracks: Annotated[bool, typer.Option(help="Borrar también las pistas")] = False):
    """Borra los clips de las pistas kresolve de la timeline activa (Studio)."""
    from .resolve.client import ResolveClient
    from .resolve.title_builder import TitleBuilder
    c = cfg()
    client = ResolveClient(install_dir=c.section("resolve").get("install_dir"))
    TitleBuilder(client, {}, c.section("resolve"), echo).clear(delete_tracks)


@app.command()
def run(skip_export: Annotated[bool, typer.Option(help="Usar el audio ya exportado en work/")] = False):
    """export-audio -> transcribe -> build-titles (Resolve Studio)."""
    c = cfg()
    name = str(c.section("resolve").get("audio_name") or "kresolve_audio")
    if not skip_export:
        export_audio()
    audio = next((p for p in sorted(c.work_dir.glob(name + ".*")) if p.suffix.lower() != ".json"), None)
    if not audio:
        fail(f"No hay audio {name}.* en {c.work_dir}")
    transcribe(audio)
    build_titles(c.work_file("transcript.json"))


# ---------------------------------------------------------------- overlay
@app.command()
def overlay(transcript: Path,
            out: Annotated[Optional[Path], typer.Option(help=".mov de salida")] = None,
            width: Annotated[Optional[int], typer.Option()] = None,
            height: Annotated[Optional[int], typer.Option()] = None,
            fps: Annotated[Optional[str], typer.Option(help="p. ej. 24, 25, 29.97")] = None,
            strategy: Annotated[Optional[str], typer.Option()] = None):
    """Renderiza un overlay ProRes 4444 con alfa (karaoke con color por palabra) con ffmpeg."""
    from .overlay import render_overlay
    from .pipeline import group_clips, load
    from .planning import transform_clips
    c = cfg()
    t = load(c, transcript)
    ov = c.section("overlay")
    fps = fps or ov.get("fps") or (t.meta.get("source") or {}).get("fps") or "24"
    style = c.style()
    clips = transform_clips(group_clips(c, t, strategy), style)
    out = out or c.work_file("overlay.mov")
    render_overlay(clips, style, out, int(width or ov.get("width") or 1920),
                   int(height or ov.get("height") or 1080), fps, log=echo)
    echo(f"Overlay: {out}")
    echo("Impórtalo al Media Pool y ponlo en una pista por encima del vídeo, alineado al inicio de la timeline.")


# ------------------------------------------------------------- utilidades
@app.command("install-scripts")
def install_scripts(uninstall: Annotated[bool, typer.Option(help="Quitar los scripts")] = False,
                    target: Annotated[Optional[Path], typer.Option(help="Carpeta Scripts/Utility")] = None):
    """Instala los scripts de Workspace > Scripts (funcionan en Resolve gratuito)."""
    from .resolve import install as inst
    if uninstall:
        for p in inst.uninstall(target):
            echo(f"Eliminado {p}")
        return
    project_dir = cfg().base_dir if cfg().path else PROJECT_ROOT
    for p in inst.install(project_dir, sys.executable, target):
        echo(f"Instalado {p}")
    echo(f"\nProyecto: {project_dir}\nPython:   {sys.executable}")
    echo("Reinicia DaVinci Resolve y búscalos en Workspace > Scripts. Abre Workspace > Console para ver la salida.")


@app.command("dump-config", hidden=True)
def dump_config():
    """Configuración resuelta en JSON (la usan los scripts de menú)."""
    sys.stdout.write(json.dumps(cfg().to_json_dict(), ensure_ascii=False))


@app.command()
def doctor(connect: Annotated[bool, typer.Option(help="Intentar conectar con Resolve (Studio)")] = False):
    """Comprueba el entorno: Python, dependencias, GPU, ffmpeg, Resolve y config."""
    rows: list[tuple[str, str, str]] = []

    def row(ok, label, detail=""):
        rows.append(("OK" if ok is True else ("--" if ok is None else "!!"), label, detail))

    row(sys.version_info >= (3, 10), "Python", f"{sys.version.split()[0]} ({sys.executable})")
    try:
        c = cfg()
        row(True, "config.yaml", str(c.path or "(valores por defecto)"))
        row(True, "work_dir", str(c.work_dir))
        st = c.style()
        row(True, "estilo", st["name"])
    except Exception as exc:
        c = None
        row(False, "config.yaml", str(exc))
    for mod in ("faster_whisper", "ctranslate2", "yaml", "typer"):
        try:
            m = __import__(mod)
            row(True, mod, getattr(m, "__version__", ""))
        except Exception as exc:
            row(False, mod, str(exc))
    try:
        from .transcribe.faster_whisper_engine import prepare_cuda_dlls
        added = prepare_cuda_dlls()
        import ctranslate2
        n = ctranslate2.get_cuda_device_count()
        detail = f"{n} GPU CUDA" + (f" | DLL de pip: {len(added)} carpetas" if added else "")
        if n and os.name == "nt":
            import ctypes
            missing = []
            for dll in ("cublas64_12.dll", "cudnn64_9.dll"):
                try:
                    ctypes.WinDLL(dll)
                except OSError:
                    missing.append(dll)
            if missing:
                detail += f" | faltan {', '.join(missing)}: pip install -e .[cuda]  (si no, se usará CPU)"
                row(None, "GPU", detail)
            else:
                row(True, "GPU", detail)
        else:
            row(None if not n else True, "GPU", detail + ("" if n else " (se usará CPU)"))
    except Exception as exc:
        row(None, "GPU", str(exc))
    ff = shutil.which("ffmpeg")
    row(True if ff else None, "ffmpeg", ff or "no está en el PATH (solo hace falta para extract-audio/overlay)")

    from .resolve.client import find_fusionscript, scripting_api_dir
    install_dir = c.section("resolve").get("install_dir") if c else None
    lib = find_fusionscript(install_dir)
    row(bool(lib), "fusionscript", str(lib) if lib else "no encontrado: pon resolve.install_dir en config.yaml")
    api = scripting_api_dir()
    row(api.is_dir(), "Scripting API", str(api))
    from .resolve import install as inst
    have = inst.installed()
    row(len(have) == len(inst.SCRIPTS) or None, "scripts de menú",
        f"{len(have)}/{len(inst.SCRIPTS)} en {inst.user_scripts_dir()}" + ("" if have else " (kresolve install-scripts)"))
    if connect:
        try:
            from .resolve.client import ResolveClient
            cl = ResolveClient(install_dir=install_dir)
            row(True, "conexión Resolve", f"{cl.product} {cl.version} | '{cl.timeline_name}' {cl.fps_raw} fps")
        except Exception as exc:
            row(False, "conexión Resolve", str(exc).splitlines()[0])

    width = max(len(r[1]) for r in rows)
    for status, label, detail in rows:
        echo(f"[{status}] {label.ljust(width)}  {detail}")
    if any(r[0] == "!!" for r in rows):
        raise typer.Exit(1)


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    app()


if __name__ == "__main__":
    main()
