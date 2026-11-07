from __future__ import annotations

from ..models import TitleClip
from ..registry import register_grouper
from .base import merged_options, word_end


@register_grouper("per_word")
class PerWord:
    """Un clip por palabra (estilo subtítulo dinámico de redes sociales).

    Con ``fill_gaps`` la palabra se mantiene hasta que empieza la siguiente si
    el silencio entre ambas es menor que ``max_gap``; así no parpadea.
    """

    def group(self, t, **opts):
        o = merged_options(opts)
        clips = []
        for s in t.segments:
            for i, w in enumerate(s.words):
                end = w.end
                if o["fill_gaps"]:
                    nxt = word_end(s.words, i)
                    if nxt - w.end <= float(o["max_gap"]):
                        end = max(end, nxt)
                clips.append(TitleClip([w.text], w.start, end))
        return clips
