from __future__ import annotations

from typing import Callable, Protocol

from ..models import Transcript

# progress(fracción 0..1, texto del último segmento)
ProgressFn = Callable[[float, str], None]


class Transcriber(Protocol):
    def transcribe(self, wav_path: str, language: str | None = None,
                   progress: ProgressFn | None = None) -> Transcript: ...
