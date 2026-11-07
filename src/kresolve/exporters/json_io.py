"""Lectura/escritura del JSON de transcripción (el punto de corte del pipeline).

El archivo se escribe con una palabra por línea para que sea fácil de corregir
a mano. ``_text`` de cada segmento es solo informativo: se regenera al guardar
y se ignora al leer, salvo que el segmento no tenga ``words`` (ver abajo).

Solo librería estándar: también se usa dentro de Resolve.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from ..models import Segment, TitleClip, Transcript, Word

FORMAT_VERSION = 1


def _dump(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def transcript_to_json(t: Transcript) -> str:
    lines = ["{",
             f'  "version": {FORMAT_VERSION},',
             f'  "language": {_dump(t.language)},',
             '  "meta": ' + json.dumps(t.meta, ensure_ascii=False, indent=2).replace("\n", "\n  ") + ",",
             '  "segments": [']
    for si, s in enumerate(t.segments):
        lines.append("    {")
        lines.append(f'      "_text": {_dump(s.text)},')
        lines.append('      "words": [')
        for wi, w in enumerate(s.words):
            comma = "," if wi + 1 < len(s.words) else ""
            lines.append(f'        {{"text": {_dump(w.text)}, "start": {w.start:.3f}, '
                         f'"end": {w.end:.3f}, "prob": {w.prob:.3f}}}{comma}')
        lines.append("      ]")
        lines.append("    }" + ("," if si + 1 < len(t.segments) else ""))
    lines.append("  ]")
    lines.append("}")
    return "\n".join(lines) + "\n"


def save_transcript(t: Transcript, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(transcript_to_json(t), encoding="utf-8")
    return path


def _num(v, where: str) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{where}: se esperaba un número y hay {v!r}") from None


def _spread_words(text: str, start: float, end: float) -> list[Word]:
    """Reparte un texto sin tiempos por palabra a lo largo de [start, end]."""
    tokens = text.split()
    if not tokens:
        return []
    total = sum(len(x) for x in tokens) or 1
    out, t = [], start
    for tok in tokens:
        d = (end - start) * len(tok) / total
        out.append(Word(tok, round(t, 3), round(t + d, 3), 0.0))
        t += d
    return out


def transcript_from_dict(data: dict, log: Callable[[str], None] | None = None) -> Transcript:
    warn = log or (lambda _m: None)
    if not isinstance(data, dict) or "segments" not in data:
        raise ValueError("El JSON no parece una transcripción de kresolve (falta 'segments').")
    segments: list[Segment] = []
    for si, sd in enumerate(data["segments"]):
        where = f"segments[{si}]"
        words: list[Word] = []
        raw_words = sd.get("words") or []
        if not raw_words and sd.get("text") and "start" in sd and "end" in sd:
            # Línea añadida a mano sin tiempos por palabra: se reparten.
            words = _spread_words(str(sd["text"]), _num(sd["start"], where + ".start"),
                                  _num(sd["end"], where + ".end"))
            warn(f"{where}: sin 'words'; repartidas {len(words)} palabras entre start y end.")
        for wi, wd in enumerate(raw_words):
            wwhere = f"{where}.words[{wi}]"
            text = str(wd.get("text", wd.get("word", ""))).strip()
            if not text:
                warn(f"{wwhere}: palabra vacía, se omite.")
                continue
            start = _num(wd.get("start"), wwhere + ".start")
            end = _num(wd.get("end"), wwhere + ".end")
            if end < start:
                warn(f"{wwhere} ({text!r}): end < start; se ajusta end = start + 0.05.")
                end = start + 0.05
            words.append(Word(text, start, end, float(wd.get("prob", 1.0) or 0.0)))
        words.sort(key=lambda w: w.start)
        if words:
            segments.append(Segment(words))
    segments.sort(key=lambda s: s.start)
    return Transcript(language=data.get("language"), segments=segments, meta=dict(data.get("meta") or {}))


def load_transcript(path, log: Callable[[str], None] | None = None) -> Transcript:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: JSON inválido en la línea {exc.lineno}, columna {exc.colno}: {exc.msg}") from None
    return transcript_from_dict(data, log)


# ---------------------------------------------------------------- plan.json
# El "plan" es lo que se le pasa a Resolve: clips ya agrupados + estilo +
# opciones del TitleBuilder. Así el lado Resolve no necesita PyYAML ni
# conocer las estrategias de agrupación.

def save_plan(plan: dict, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dict(plan)
    data["clips"] = [c.to_dict() if isinstance(c, TitleClip) else c for c in plan["clips"]]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load_plan(path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    data["clips"] = [TitleClip.from_dict(c) for c in data.get("clips", [])]
    return data
