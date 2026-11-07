"""Render de solo audio de la timeline activa.

API usada (Resolve 21.1+): ``GetAudioRenderFormats``, ``GetAudioRenderCodecs``
y las claves ``AudioFormat`` / ``AudioCodec`` de ``SetRenderSettings`` (válidas
cuando ``ExportVideo`` es False). Los nombres de formato y códec no se
escriben a mano: se descubren y se elige WAV / PCM si existen.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

AUDIO_EXTS = (".wav", ".aif", ".aiff", ".flac", ".mp3", ".m4a", ".aac")
_PREFERRED = ("wav", "aif", "aiff", "flac", "mp3", "m4a")
_DONE = ("Complete", "Failed", "Cancelled", "Background Render Cancelled", "Remote Render Cancelled")


def _call(obj, name, *args, default=None):
    fn = getattr(obj, name, None)
    if fn is None:
        return default
    try:
        r = fn(*args)
    except Exception:
        return default
    return default if r is None else r


def pick_audio_format(project) -> list[tuple[str, str]]:
    """Candidatos (formato, códec) en orden de preferencia."""
    formats = _call(project, "GetAudioRenderFormats", default={}) or {}   # {nombre: extensión}
    by_ext = {str(ext).lower().lstrip("."): str(name) for name, ext in formats.items()}
    candidates: list[tuple[str, str]] = []
    for ext in _PREFERRED:
        if ext not in by_ext:
            continue
        codecs = _call(project, "GetAudioRenderCodecs", ext, default={}) or {}   # {descripción: nombre}
        names = sorted(codecs.items(), key=lambda kv: 0 if "pcm" in (kv[0] + kv[1]).lower() else 1)
        for _desc, codec in names[:2]:
            candidates.append((ext, str(codec)))
            candidates.append((by_ext[ext], str(codec)))   # por si AudioFormat espera el nombre
    if not candidates:   # versión antigua sin las funciones de descubrimiento
        candidates = [("wav", "lpcm"), ("wav", "LinearPCM")]
    return candidates


def export_timeline_audio(client, out_dir, name: str = "kresolve_audio", use_in_out: bool = False,
                          sample_rate: int = 48000, timeout: float = 3600, log=print) -> tuple[Path, dict]:
    """Renderiza el audio de la timeline. Devuelve (ruta_audio, meta).

    ``meta["offset_frames"]`` es el desfase (frames desde el inicio de la
    timeline) del primer sample renderizado; se guarda junto al audio en
    ``<name>.meta.json`` y build-titles lo suma a los tiempos.
    """
    p, tl = client.project, client.timeline
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob(name + ".*"):
        if old.suffix.lower() in AUDIO_EXTS:
            old.unlink()

    settings = {"ExportVideo": False, "ExportAudio": True, "TargetDir": str(out_dir), "CustomName": name}
    offset = 0
    if use_in_out:
        marks = _call(tl, "GetMarkInOut", default={}) or {}
        rng = marks.get("audio") or marks.get("video") or {}
        if "in" in rng and "out" in rng:
            offset = int(rng["in"])
            settings.update({"SelectAllFrames": False,
                             "MarkIn": client.start_frame + int(rng["in"]),
                             "MarkOut": client.start_frame + int(rng["out"])})
            log(f"Rango In/Out: frames {rng['in']}..{rng['out']} (relativos al inicio de la timeline)")
        else:
            log("AVISO: use_in_out = true pero la timeline no tiene In/Out. Se renderiza completa.")
    if "MarkIn" not in settings:
        settings["SelectAllFrames"] = True

    prev_fc = _call(p, "GetCurrentRenderFormatAndCodec", default={}) or {}
    prev_mode = _call(p, "GetCurrentRenderMode", default=1)
    _call(p, "SetCurrentRenderMode", 1)   # un solo archivo

    chosen = None
    for fmt, codec in pick_audio_format(p):
        if p.SetRenderSettings({**settings, "AudioFormat": fmt, "AudioCodec": codec}):
            chosen = (fmt, codec)
            break
    if not chosen:
        formats = _call(p, "GetAudioRenderFormats", default={})
        raise RuntimeError(
            "Resolve rechazó la configuración de render de audio.\n"
            f"  Formatos de audio disponibles: {formats}\n"
            "  Prueba a renderizar el audio a mano (Deliver > Audio only > WAV) en la carpeta work/\n"
            "  o usa: kresolve extract-audio <video>"
        )
    p.SetRenderSettings({"AudioSampleRate": int(sample_rate), "AudioBitDepth": 16})   # opcional
    log(f"Render de audio: formato={chosen[0]} códec={chosen[1]} -> {out_dir}")

    job = p.AddRenderJob()
    if not job:
        raise RuntimeError("AddRenderJob() falló. ¿La timeline tiene audio y la carpeta de destino es válida?")
    try:
        started = False
        for args in (([job],), (job,)):   # firma 21.x (lista) y firma antigua (varargs)
            try:
                started = p.StartRendering(*args)
            except TypeError:
                started = False
            if started:
                break
        if not started:
            raise RuntimeError("StartRendering() devolvió False.")
        t0, last = time.time(), -10
        while True:
            st = _call(p, "GetRenderJobStatus", job, default={}) or {}
            status = st.get("JobStatus", "")
            pct = int(st.get("CompletionPercentage", 0) or 0)
            if pct >= last + 10:
                log(f"  render {pct}%")
                last = pct
            if status in _DONE or (not status and not p.IsRenderingInProgress() and time.time() - t0 > 5):
                break
            if time.time() - t0 > timeout:
                p.StopRendering()
                raise TimeoutError(f"El render superó {timeout:.0f} s")
            time.sleep(0.5)
        if status and status != "Complete":
            raise RuntimeError(f"Render terminado con estado {status!r}: {st.get('Error', '')}")
    finally:
        _call(p, "DeleteRenderJob", job)
        if prev_fc.get("format") and prev_fc.get("codec"):
            _call(p, "SetCurrentRenderFormatAndCodec", prev_fc["format"], prev_fc["codec"])
        _call(p, "SetCurrentRenderMode", prev_mode)
        p.SetRenderSettings({"ExportVideo": True})

    found = sorted((f for f in out_dir.glob(name + ".*") if f.suffix.lower() in AUDIO_EXTS),
                   key=lambda f: f.stat().st_mtime)
    if not found:
        raise FileNotFoundError(f"El render terminó pero no aparece {name}.* en {out_dir}")
    audio = found[-1]
    meta = {
        "timeline": client.timeline_name,
        "fps": client.fps_raw,
        "start_frame": client.start_frame,
        "offset_frames": offset,
        "audio_format": chosen[0],
        "rendered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    meta_path = audio.with_name(audio.stem + ".meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Audio exportado: {audio}")
    return audio, meta
