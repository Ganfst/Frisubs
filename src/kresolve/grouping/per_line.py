from __future__ import annotations

from ..models import LAYER_BASE, LAYER_HIGHLIGHT, TitleClip
from ..registry import register_grouper
from .base import apply_padding, iter_lines, merged_options, word_end


@register_grouper("per_line")
class PerLine:
    """Frase completa + palabra activa resaltada (karaoke clásico).

    Genera dos capas que el TitleBuilder pone en pistas distintas:

    - ``base``: un clip por línea con la frase entera.
    - ``highlight``: un clip por palabra con la misma frase y
      ``highlight_index`` apuntando a la palabra activa. En Resolve ese clip
      solo deja visible esa palabra (Write On) y la pinta del color de
      resaltado, exactamente encima de la frase base.
    """

    def group(self, t, **opts):
        o = merged_options(opts)
        clips: list[TitleClip] = []
        for line in iter_lines(t, o):
            words = [w.text for w in line.words]
            clips.append(TitleClip(words, line.start, line.end, layer=LAYER_BASE))
            if o["highlight"]:
                for i, w in enumerate(line.words):
                    clips.append(TitleClip(words, w.start, word_end(line.words, i),
                                           layer=LAYER_HIGHLIGHT, highlight_index=i))
        apply_padding(clips, float(o["lead_in"]), float(o["hold"]))
        return clips


@register_grouper("per_line_single")
class PerLineSingle:
    """Un clip por línea, sin resaltado (subtítulos normales)."""

    def group(self, t, **opts):
        o = merged_options(opts)
        clips = [TitleClip([w.text for w in line.words], line.start, line.end)
                 for line in iter_lines(t, o)]
        apply_padding(clips, float(o["lead_in"]), float(o["hold"]))
        return clips
