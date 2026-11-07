"""Interfaz de los groupers y utilidades comunes (partir líneas, márgenes)."""

from __future__ import annotations

from typing import Iterator, Protocol

from ..models import LAYER_BASE, Segment, TitleClip, Transcript

# Valores por defecto de ``grouping.options`` en config.yaml
DEFAULT_OPTIONS = {
    "max_chars": 42,     # caracteres máximos por línea en pantalla
    "max_words": 8,      # palabras máximas por línea
    "max_gap": 1.0,      # silencio (s) que fuerza un salto de línea
    "lead_in": 0.0,      # s que la línea aparece antes de la primera palabra
    "hold": 0.3,         # s que la línea se queda tras la última palabra
    "window": 4,         # sliding: palabras visibles a la vez
    "highlight": True,   # per_line / sliding: crear capa de resaltado
    "fill_gaps": True,   # per_word: mantener la palabra hasta la siguiente
}

_PUNCT = (".", ",", ";", ":", "!", "?", "…")


class Grouper(Protocol):
    def group(self, t: Transcript, **opts) -> list[TitleClip]: ...


def merged_options(opts: dict | None) -> dict:
    out = dict(DEFAULT_OPTIONS)
    out.update({k: v for k, v in (opts or {}).items() if v is not None})
    return out


def split_segment(seg: Segment, max_chars: int, max_words: int, max_gap: float) -> list[Segment]:
    """Parte un segmento de Whisper en líneas aptas para pantalla.

    Corta cuando la línea excede ``max_chars`` o ``max_words``, o cuando hay un
    silencio mayor que ``max_gap``. Si la línea ya va por más del 60 % del
    límite y la palabra termina en puntuación, corta ahí (queda más natural).
    """
    lines: list[Segment] = []
    cur: list = []
    cur_len = 0
    for w in seg.words:
        wlen = len(w.text)
        if cur:
            gap = w.start - cur[-1].end
            too_long = cur_len + 1 + wlen > max_chars
            too_many = len(cur) >= max_words
            if too_long or too_many or gap > max_gap:
                lines.append(Segment(cur))
                cur, cur_len = [], 0
        cur.append(w)
        cur_len = wlen if len(cur) == 1 else cur_len + 1 + wlen
        if w.text.endswith(_PUNCT) and cur_len >= 0.6 * max_chars:
            lines.append(Segment(cur))
            cur, cur_len = [], 0
    if cur:
        lines.append(Segment(cur))
    return lines


def iter_lines(t: Transcript, opts: dict) -> Iterator[Segment]:
    o = merged_options(opts)
    for seg in t.segments:
        if not seg.words:
            continue
        yield from split_segment(seg, int(o["max_chars"]), int(o["max_words"]), float(o["max_gap"]))


def word_end(words: list, i: int) -> float:
    """Fin de la ventana de la palabra i: hasta que empieza la siguiente."""
    w = words[i]
    if i + 1 < len(words):
        nxt = words[i + 1].start
        if nxt > w.start:
            return nxt
    return w.end


def apply_padding(clips: list[TitleClip], lead_in: float, hold: float, layer: str = LAYER_BASE) -> None:
    """Alarga los clips de una capa sin que se solapen entre sí (en el sitio).

    Primero el ``lead_in`` (ver la línea antes de cantarla importa más) y
    después el ``hold``, limitado por el nuevo inicio de la línea siguiente.
    """
    same = sorted((c for c in clips if c.layer == layer), key=lambda c: c.start)
    if lead_in > 0:
        prev_end = 0.0
        for c in same:
            original_end = c.end
            c.start = max(prev_end, c.start - lead_in)
            prev_end = original_end
    if hold > 0:
        for i, c in enumerate(same):
            limit = same[i + 1].start if i + 1 < len(same) else float("inf")
            c.end = max(c.end, min(c.end + hold, limit))
