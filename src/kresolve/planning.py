"""De TitleClips en segundos a un plan en frames listo para Resolve.

Aquí vive la única conversión segundos -> frames del proyecto, más el estilo
resuelto y el cálculo del rango Write On del resaltado. Solo librería
estándar (se ejecuta dentro de Resolve).
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .models import LAYERS, TitleClip

PLAN_VERSION = 1

# Valores de un preset de styles/presets.yaml. ``None`` = respetar la plantilla Text+.
STYLE_DEFAULTS = {
    "font": None,              # p. ej. "Open Sans"
    "style": None,             # p. ej. "Bold"
    "size": None,              # tamaño Text+ (relativo al ancho), p. ej. 0.08
    "color": None,             # [r, g, b] 0..1 del texto base
    "highlight_color": [1.0, 0.85, 0.1],
    "position": None,          # [x, y] 0..1 (Text+ Layout > Center; y=0 abajo)
    "uppercase": False,
    # Solo para el overlay .ass / ffmpeg:
    "ass_size": 72,            # px a 1080p
    "outline": 3,
    "shadow": 1,
    "outline_color": [0, 0, 0],
}

_NTSC = {
    23.976: Fraction(24000, 1001),
    29.97: Fraction(30000, 1001),
    47.952: Fraction(48000, 1001),
    59.94: Fraction(60000, 1001),
    119.88: Fraction(120000, 1001),
}


def fps_fraction(value) -> Fraction:
    """'23.976', 23.976, '29.97 DF', 25 -> fracción exacta."""
    s = str(value).strip().upper()
    for tag in (" NDF", " DF", "NDF", "DF"):
        s = s.replace(tag, "")
    f = float(s)
    if f <= 0:
        raise ValueError(f"fps inválido: {value!r}")
    for nominal, exact in _NTSC.items():
        if abs(f - nominal) < 0.01:
            return exact
    return Fraction(f).limit_denominator(1001)


def parse_fps(value) -> float:
    return float(fps_fraction(value))


@dataclass
class FrameClip:
    clip: TitleClip
    record_frame: int   # frame absoluto en la timeline (incluye GetStartFrame)
    duration: int       # en frames, >= 1


def plan_frames(clips: list[TitleClip], fps, timeline_start: int = 0,
                offset_frames: int = 0) -> dict[str, list[FrameClip]]:
    """Convierte a frames por capa, sin solapes dentro de cada capa.

    - Redondeo al frame más cercano.
    - Duración mínima 1 frame.
    - Si un clip empieza antes de que acabe el anterior de su capa, se retrasa.
    """
    rate = float(fps_fraction(fps))
    out: dict[str, list[FrameClip]] = {}
    for layer in LAYERS:
        same = sorted((c for c in clips if c.layer == layer), key=lambda c: (c.start, c.end))
        planned: list[FrameClip] = []
        prev_end = None
        for c in same:
            s = round(c.start * rate)
            e = round(c.end * rate)
            if prev_end is not None and s < prev_end:
                s = prev_end
            if e <= s:
                e = s + 1
            planned.append(FrameClip(c, timeline_start + offset_frames + s, e - s))
            prev_end = e
        if planned:
            out[layer] = planned
    return out


def writeon_range(text: str, span: tuple[int, int], pad: float = 0.5,
                  count_spaces: bool = True) -> tuple[float, float]:
    """Rango Write On (Start, End en 0..1) que deja visible solo ``span``.

    Text+ muestra la porción [Start, End] del texto. Se añade medio carácter de
    margen a cada lado: como las palabras están separadas por espacios, el
    margen solo puede destapar espacios (invisibles), y así el resultado no
    depende de si Fusion redondea hacia arriba o hacia abajo.
    """
    cs, ce = span
    if not count_spaces:
        cs = len("".join(text[:cs].split()))
        ce = cs + len("".join(text[span[0]:span[1]].split()))
        n = len("".join(text.split()))
    else:
        n = len(text)
    if n == 0:
        return 0.0, 1.0
    return max(0.0, (cs - pad) / n), min(1.0, (ce + pad) / n)


def resolve_style(presets: dict, name: str) -> dict:
    if name not in presets:
        raise KeyError(f"Preset de estilo {name!r} no existe. Disponibles: {', '.join(sorted(presets)) or '(ninguno)'}")
    style = dict(STYLE_DEFAULTS)
    style.update(presets[name] or {})
    style["name"] = name
    return style


def transform_clips(clips: list[TitleClip], style: dict) -> list[TitleClip]:
    """Transformaciones de texto del estilo (por ahora, mayúsculas)."""
    if not style.get("uppercase"):
        return clips
    return [TitleClip([w.upper() for w in c.words], c.start, c.end, c.layer, c.highlight_index)
            for c in clips]


def make_plan(clips: list[TitleClip], style: dict, resolve_opts: dict, *, strategy: str,
              offset_frames: int = 0, source: dict | None = None) -> dict:
    return {
        "version": PLAN_VERSION,
        "strategy": strategy,
        "style": style,
        "resolve": resolve_opts,
        "offset_frames": int(offset_frames),
        "source": source or {},
        "clips": transform_clips(clips, style),
    }
