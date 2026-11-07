from __future__ import annotations

from ..models import LAYER_BASE, LAYER_HIGHLIGHT, TitleClip
from ..registry import register_grouper
from .base import iter_lines, merged_options, word_end


@register_grouper("sliding")
class Sliding:
    """Karaoke acumulado: las palabras van apareciendo una a una.

    Dentro de cada línea, el clip de la palabra i muestra las últimas
    ``window`` palabras hasta la i inclusive. Con ``highlight`` se añade la
    capa de resaltado sobre la palabra recién aparecida.

    Consejo: en la plantilla Text+ pon el anclaje horizontal a la izquierda
    (H Anchor = -1) para que el texto no se recentre en cada palabra.
    """

    def group(self, t, **opts):
        o = merged_options(opts)
        n = max(1, int(o["window"]))
        clips: list[TitleClip] = []
        for line in iter_lines(t, o):
            for i, w in enumerate(line.words):
                first = max(0, i - n + 1)
                words = [x.text for x in line.words[first:i + 1]]
                end = word_end(line.words, i)
                clips.append(TitleClip(words, w.start, end, layer=LAYER_BASE))
                if o["highlight"]:
                    clips.append(TitleClip(words, w.start, end, layer=LAYER_HIGHLIGHT,
                                           highlight_index=len(words) - 1))
        return clips
