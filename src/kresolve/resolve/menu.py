"""Punto de entrada de los scripts de Workspace > Scripts (Resolve gratuito y Studio).

Se ejecuta en el Python integrado de Resolve, que no tiene pip ni las
dependencias del proyecto. Por eso:

- lo que necesita Resolve (render, crear Text+) se hace aquí, solo con stdlib;
- lo que necesita dependencias (leer config.yaml, transcribir con Whisper,
  agrupar) se delega al Python del entorno virtual con ``python -m kresolve``.

La salida aparece en Workspace > Console.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

from ..exporters.json_io import load_plan
from .audio_export import AUDIO_EXTS, export_timeline_audio
from .client import ResolveClient, ResolveNotAvailable
from .diagnostics import run_diagnostics
from .title_builder import TemplateNotFound, TitleBuilder

EXPECTED_ERRORS = (ResolveNotAvailable, TemplateNotFound, FileNotFoundError)

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_CONSOLE = 0x00000010


def log(msg: str = "") -> None:
    print(f"[kresolve] {msg}", flush=True)


class MenuRunner:
    def __init__(self, resolve, project_dir, python_exe):
        self.resolve = resolve
        self.project_dir = Path(project_dir)
        self.python = str(python_exe)
        if not Path(self.python).is_file():
            raise FileNotFoundError(f"No existe el Python del proyecto: {self.python}\n"
                                    "Vuelve a ejecutar 'kresolve install-scripts' desde el entorno virtual.")
        self.cfg = self.cli_json("dump-config")
        self.work_dir = Path(self.cfg["_work_dir"])
        self.ropts = self.cfg.get("resolve") or {}
        self._client = None

    # ------------------------------------------------------------ helpers
    def _env(self) -> dict:
        env = dict(os.environ)
        for k in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP"):
            env.pop(k, None)   # que el Python del venv no herede los de Resolve
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        return env

    def cli(self, *args, console: bool = False) -> subprocess.CompletedProcess:
        cmd = [self.python, "-m", "kresolve", *map(str, args)]
        log("$ " + " ".join(f'"{a}"' if " " in a else a for a in cmd[2:]))
        flags = 0
        if os.name == "nt":
            flags = CREATE_NEW_CONSOLE if console else CREATE_NO_WINDOW
        if console:   # ventana propia con la barra de progreso de Whisper
            proc = subprocess.run(cmd, cwd=str(self.project_dir), env=self._env(), creationflags=flags)
        else:
            proc = subprocess.run(cmd, cwd=str(self.project_dir), env=self._env(), creationflags=flags,
                                  capture_output=True, text=True, encoding="utf-8", errors="replace")
            for line in (proc.stderr or "").splitlines():
                log(line)
        if proc.returncode != 0:
            out = "" if console else (proc.stdout or "")[-2000:]
            raise RuntimeError(f"'kresolve {args[0]}' terminó con código {proc.returncode}. {out}")
        return proc

    def cli_json(self, *args) -> dict:
        proc = self.cli(*args)
        return json.loads(proc.stdout)

    @property
    def client(self) -> ResolveClient:
        if self._client is None:
            self._client = ResolveClient(self.resolve, self.ropts.get("install_dir"))
            log(f"{self._client.product} {self._client.version} | timeline '{self._client.timeline_name}' "
                f"| {self._client.fps_raw} fps")
        return self._client

    def latest_audio(self) -> Path:
        name = str(self.ropts.get("audio_name") or "kresolve_audio")
        found = sorted((f for f in self.work_dir.glob("*") if f.suffix.lower() in AUDIO_EXTS),
                       key=lambda f: (f.stem == name, f.stat().st_mtime))
        if not found:
            raise FileNotFoundError(f"No hay audio en {self.work_dir}. Ejecuta antes 'kresolve 1 - Exportar audio'.")
        return found[-1]

    # ------------------------------------------------------------- acciones
    def diagnose(self):
        log(f"Proyecto kresolve: {self.project_dir}")
        log(f"Python del entorno: {self.python}")
        log(f"Python de Resolve:  {sys.version.split()[0]} ({sys.executable})")
        log(f"Config: {self.cfg.get('_config_path')} | work: {self.work_dir}")
        ok = run_diagnostics(self.client, self.ropts, self.cfg["_style"], self.work_dir, log)
        log("DIAGNÓSTICO OK" if ok else "DIAGNÓSTICO CON AVISOS (lee los mensajes de arriba)")

    def export_audio(self):
        export_timeline_audio(self.client, self.work_dir, str(self.ropts.get("audio_name") or "kresolve_audio"),
                              bool(self.ropts.get("use_in_out")), log=log)

    def transcribe(self):
        audio = self.latest_audio()
        log(f"Transcribiendo {audio.name} en una ventana aparte (puede tardar varios minutos)...")
        self.cli("transcribe", str(audio), "--pause-on-error", console=True)
        log(f"Transcripción lista: {self.work_dir / 'transcript.json'}")

    def build_titles(self):
        transcript = self.work_dir / "transcript.json"
        if not transcript.is_file():
            raise FileNotFoundError(f"No existe {transcript}. Ejecuta antes 'kresolve 2 - Transcribir'.")
        plan_path = self.work_dir / "plan.json"
        self.cli("plan", str(transcript), "--out", str(plan_path))
        plan = load_plan(plan_path)
        src_tl = (plan.get("source") or {}).get("timeline")
        if src_tl and src_tl != self.client.timeline_name:
            log(f"AVISO: el audio se exportó de la timeline '{src_tl}' y la activa es "
                f"'{self.client.timeline_name}'.")
        builder = TitleBuilder(self.client, plan["style"], plan.get("resolve"), log)
        report = builder.build(plan["clips"], int(plan.get("offset_frames") or 0))
        log(report.summary())

    def clear(self):
        TitleBuilder(self.client, {}, self.ropts, log).clear()

    def all(self):
        self.export_audio()
        self.transcribe()
        self.build_titles()


ACTIONS = {
    "diagnose": MenuRunner.diagnose,
    "export-audio": MenuRunner.export_audio,
    "transcribe": MenuRunner.transcribe,
    "build-titles": MenuRunner.build_titles,
    "clear": MenuRunner.clear,
    "all": MenuRunner.all,
}


def run(action: str, resolve=None, project_dir=None, python_exe=None) -> bool:
    t0 = time.time()
    log("=" * 60)
    log(f"{action}  ({time.strftime('%H:%M:%S')})")
    try:
        runner = MenuRunner(resolve, project_dir, python_exe)
        ACTIONS[action](runner)
        log(f"Terminado en {time.time() - t0:.1f} s.")
        return True
    except Exception as exc:
        for i, line in enumerate(str(exc).splitlines() or [repr(exc)]):
            log(("ERROR: " if i == 0 else "  ") + line)
        if not isinstance(exc, EXPECTED_ERRORS):   # errores conocidos: sin traceback
            for line in traceback.format_exc().splitlines():
                log("  " + line)
        return False
