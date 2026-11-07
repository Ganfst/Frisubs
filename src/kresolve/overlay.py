"""Overlay de karaoke con alfa (ProRes 4444) renderizado con ffmpeg + libass.

Alternativa a los Text+ cuando se quiere color por palabra garantizado o no se
puede usar la API de Resolve: se importa el .mov en una pista superior.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from .exporters.ass import clips_to_ass
from .models import TitleClip
from .planning import fps_fraction


def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise FileNotFoundError("No encuentro ffmpeg en el PATH. Instálalo (winget install Gyan.FFmpeg) "
                                "y abre una terminal nueva.")
    return exe


def write_ass(clips: list[TitleClip], style: dict, path, width: int, height: int) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(clips_to_ass(clips, style, width, height), encoding="utf-8")
    return path


def render_overlay(clips: list[TitleClip], style: dict, out_mov, width: int = 1920, height: int = 1080,
                   fps="24", tail: float = 1.0, log=print) -> Path:
    out_mov = Path(out_mov).resolve()
    ass_path = write_ass(clips, style, out_mov.with_suffix(".ass"), width, height)
    duration = max((c.end for c in clips), default=0.0) + tail
    rate = fps_fraction(fps)
    rate_s = f"{rate.numerator}/{rate.denominator}" if rate.denominator != 1 else str(rate.numerator)
    cmd = [
        ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-stats", "-stats_period", "10", "-y",
        "-f", "lavfi", "-i", f"color=c=black@0.0:s={width}x{height}:r={rate_s}:d={duration:.3f},format=rgba",
        # Ruta relativa + cwd: evita escapar "C:\..." dentro del filtro de ffmpeg.
        "-vf", f"ass={ass_path.name}:alpha=1",
        # prores_aw perfil 4 = ProRes 4444 con alfa. Medido: el doble de rápido que prores_ks
        # con el mismo resultado (14 s frente a 29,5 s para 11 s de 1080p).
        "-c:v", "prores_aw", "-profile:v", "4", "-pix_fmt", "yuva444p10le",
        "-an", out_mov.name,
    ]
    log(f"Renderizando overlay {width}x{height} @ {rate_s} fps, {duration:.1f} s -> {out_mov}")
    log("(la primera vez libass crea la caché de fuentes y puede tardar un minuto más)")
    t0 = time.time()
    subprocess.run(cmd, cwd=str(out_mov.parent), check=True)
    log(f"Overlay renderizado en {time.time() - t0:.0f} s")
    return out_mov
