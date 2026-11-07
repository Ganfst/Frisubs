"""Modelos de datos compartidos por todas las etapas.

Solo librería estándar: este módulo también se carga dentro de Resolve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

LAYER_BASE = "base"            # frase o palabra visible
LAYER_HIGHLIGHT = "highlight"  # capa superior con solo la palabra activa
LAYERS = (LAYER_BASE, LAYER_HIGHLIGHT)


@dataclass
class Word:
    text: str
    start: float          # segundos desde el inicio del audio exportado
    end: float
    prob: float = 1.0


@dataclass
class Segment:
    words: list[Word] = field(default_factory=list)

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end

    @property
    def text(self) -> str:
        return " ".join(w.text.strip() for w in self.words)


@dataclass
class Transcript:
    language: str | None
    segments: list[Segment] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def iter_words(self) -> Iterator[Word]:
        for s in self.segments:
            yield from s.words

    @property
    def duration(self) -> float:
        ends = [s.end for s in self.segments if s.words]
        return max(ends) if ends else 0.0


@dataclass
class TitleClip:
    """Lo que el TitleBuilder debe crear: texto + ventana de tiempo + capa.

    ``words`` es la fuente de verdad del texto. Guardar las palabras (y no solo
    la cadena) permite calcular el rango de caracteres de la palabra activa
    después de transformar el texto (p. ej. mayúsculas).
    """

    words: list[str]
    start: float
    end: float
    layer: str = LAYER_BASE
    highlight_index: int | None = None   # palabra activa dentro de ``words``

    @property
    def text(self) -> str:
        return " ".join(self.words)

    @property
    def highlight_span(self) -> tuple[int, int] | None:
        """Rango [inicio, fin) en caracteres de la palabra activa dentro de ``text``."""
        if self.highlight_index is None:
            return None
        return word_span(self.words, self.highlight_index)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "words": list(self.words),
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "layer": self.layer,
            "highlight_index": self.highlight_index,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TitleClip":
        words = d.get("words")
        if not words:
            words = str(d.get("text", "")).split()
        hi = d.get("highlight_index")
        return cls(
            words=[str(w) for w in words],
            start=float(d["start"]),
            end=float(d["end"]),
            layer=str(d.get("layer", LAYER_BASE)),
            highlight_index=None if hi is None else int(hi),
        )


def word_span(words: list[str], index: int) -> tuple[int, int]:
    """Posición [inicio, fin) de ``words[index]`` en ``" ".join(words)``."""
    if not 0 <= index < len(words):
        raise IndexError(f"highlight_index {index} fuera de rango (0..{len(words) - 1})")
    start = sum(len(w) + 1 for w in words[:index])
    return start, start + len(words[index])
