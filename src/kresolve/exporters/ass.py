"""Exportador ASS (Advanced SubStation) con resaltado por palabra.

Reproduce el mismo modelo de dos capas que se usa en Resolve:

- capa 0 (``base``): la línea completa en el color normal.
- capa 1 (``highlight``): la misma línea con todas las palabras
  transparentes salvo la activa, pintada del color de resaltado. Como el texto
  es idéntico, libass la coloca exactamente encima.

Con ffmpeg se convierte en un overlay con alfa (ver ``overlay.py``), que es la
vía 100 % fiable para tener color por palabra también en Resolve gratuito.
"""

from __future__ import annotations

from ..models import LAYER_HIGHLIGHT, TitleClip


def ass_time(sec: float) -> str:
    cs = max(0, int(round(sec * 100)))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_color(rgb, alpha: float = 0.0) -> str:
    """[r, g, b] (0..1) -> &HAABBGGRR. ``alpha`` 0 = opaco, 1 = transparente."""
    r, g, b = (max(0, min(255, int(round(float(c) * 255)))) for c in list(rgb)[:3])
    a = max(0, min(255, int(round(alpha * 255))))
    return f"&H{a:02X}{b:02X}{g:02X}{r:02X}"


def _bgr(rgb) -> str:
    return ass_color(rgb)[4:]  # sin el byte de alfa: &HBBGGRR


def _escape(text: str) -> str:
    return text.replace("\\", "/").replace("{", "(").replace("}", ")")


def _highlight_text(clip: TitleClip, color) -> str:
    parts = []
    for j, w in enumerate(clip.words):
        if j == clip.highlight_index:
            parts.append("{\\alpha&H00&\\1c&H" + _bgr(color) + "&}" + _escape(w) + "{\\alpha&HFF&}")
        else:
            parts.append(_escape(w))
    return "{\\alpha&HFF&}" + " ".join(parts)


def clips_to_ass(clips: list[TitleClip], style: dict, width: int = 1920, height: int = 1080) -> str:
    font = style.get("font") or "Arial"
    bold = -1 if str(style.get("style") or "Bold").lower().startswith("bold") else 0
    size = round(float(style.get("ass_size") or 72) * height / 1080)
    outline = float(style.get("outline", 3) or 0)
    shadow = float(style.get("shadow", 1) or 0)
    color = style.get("color") or [1, 1, 1]
    hl = style.get("highlight_color") or [1, 0.85, 0.1]
    outline_color = style.get("outline_color") or [0, 0, 0]
    px, py = (style.get("position") or [0.5, 0.12])[:2]
    pos = f"{{\\an5\\pos({round(float(px) * width)},{round((1 - float(py)) * height)})}}"

    out = [
        "[Script Info]",
        "; Generado por kresolve",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font},{size},{ass_color(color)},{ass_color(hl)},{ass_color(outline_color)},"
        f"{ass_color([0, 0, 0], 0.5)},{bold},0,0,0,100,100,0,0,1,{outline:g},{shadow:g},5,10,10,10,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for c in sorted(clips, key=lambda c: (c.start, c.layer)):
        if c.end <= c.start:
            continue
        if c.layer == LAYER_HIGHLIGHT and c.highlight_index is not None:
            layer, text = 1, _highlight_text(c, hl)
        else:
            layer, text = 0, _escape(c.text)
        out.append(f"Dialogue: {layer},{ass_time(c.start)},{ass_time(c.end)},Default,,0,0,0,,{pos}{text}")
    return "\n".join(out) + "\n"
