"""Exportador SRT: una entrada por línea de pantalla (mismo corte que per_line)."""

from __future__ import annotations

from pathlib import Path

from ..grouping.base import iter_lines
from ..models import Transcript


def format_ts(sec: float) -> str:
    ms = max(0, int(round(sec * 1000)))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def transcript_to_srt(t: Transcript, line_opts: dict | None = None) -> str:
    blocks = []
    for i, line in enumerate(iter_lines(t, line_opts or {}), 1):
        blocks.append(f"{i}\n{format_ts(line.start)} --> {format_ts(line.end)}\n{line.text}\n")
    return "\n".join(blocks)


def save_srt(t: Transcript, path, line_opts: dict | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8 con BOM: Resolve y la mayoría de editores detectan bien los acentos.
    path.write_text(transcript_to_srt(t, line_opts), encoding="utf-8-sig")
    return path
