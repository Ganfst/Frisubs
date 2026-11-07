"""Motor faster-whisper con tiempos por palabra.

``faster_whisper`` se importa al cargar el modelo, no al importar el módulo,
para que registrar el motor no exija tener instaladas sus dependencias.
"""

from __future__ import annotations

import os
import site
import sys
from pathlib import Path

from ..models import Segment, Transcript, Word
from ..registry import register_transcriber

# Opciones de config.yaml que se pasan tal cual a WhisperModel.transcribe()
_TRANSCRIBE_KEYS = ("vad_filter", "beam_size", "initial_prompt", "condition_on_previous_text",
                    "temperature", "no_speech_threshold", "hallucination_silence_threshold")

_CUDA_ERROR_HINTS = ("cublas", "cudnn", "cuda", "cudart", "libcu", "nvrtc")


def prepare_cuda_dlls() -> list[str]:
    """Windows: añade al buscador de DLL las carpetas ``nvidia/*/bin`` de pip.

    Los paquetes ``nvidia-cublas-cu12`` y ``nvidia-cudnn-cu12`` (extra ``[cuda]``)
    instalan las DLL dentro de site-packages, donde ctranslate2 no las busca.
    Devuelve las carpetas añadidas.
    """
    if os.name != "nt":
        return []
    roots = set()
    for getter in (site.getsitepackages, lambda: [site.getusersitepackages()]):
        try:
            roots.update(getter())
        except Exception:
            pass
    roots.add(str(Path(sys.prefix) / "Lib" / "site-packages"))
    added = []
    for root in roots:
        nvidia = Path(root) / "nvidia"
        if not nvidia.is_dir():
            continue
        for bin_dir in sorted(nvidia.glob("*/bin")):
            d = str(bin_dir)
            if d in added:
                continue
            try:
                os.add_dll_directory(d)
            except (OSError, AttributeError):
                pass
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            added.append(d)
    return added


def _is_cuda_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(h in msg for h in _CUDA_ERROR_HINTS)


@register_transcriber("faster-whisper")
class FasterWhisperEngine:
    def __init__(self, model: str = "large-v3", device: str = "auto", compute_type: str = "auto",
                 download_root: str | None = None, log=print, **options):
        self.model_name = model
        self.device = device or "auto"
        self.compute_type = compute_type or "auto"
        self.download_root = download_root
        self.options = {k: v for k, v in options.items() if k in _TRANSCRIBE_KEYS and v is not None}
        self.log = log
        self.used_device: str | None = None

    def _load(self, device: str, compute_type: str):
        prepare_cuda_dlls()
        from faster_whisper import WhisperModel
        self.log(f"Cargando modelo '{self.model_name}' (device={device}, compute_type={compute_type})...")
        return WhisperModel(self.model_name, device=device, compute_type=compute_type,
                            download_root=self.download_root)

    def transcribe(self, wav_path, language=None, progress=None) -> Transcript:
        try:
            return self._run(self.device, self.compute_type, wav_path, language, progress)
        except (RuntimeError, OSError) as exc:
            if self.device == "cpu" or not _is_cuda_error(exc):
                raise
            self.log(f"AVISO: la GPU no está disponible ({exc}).")
            self.log("       Sigo en CPU (int8). Para usar la GPU: pip install -e .[cuda]  (ver GUIA, paso 3).")
            return self._run("cpu", "int8", wav_path, language, progress)

    def _run(self, device, compute_type, wav_path, language, progress) -> Transcript:
        model = self._load(device, compute_type)
        if language in ("", "auto", "null", "None"):
            language = None
        segs, info = model.transcribe(str(wav_path), language=language, word_timestamps=True,
                                      **self.options)
        out = Transcript(language=info.language)
        total = float(getattr(info, "duration", 0.0) or 0.0)
        for s in segs:   # generador: aquí es donde realmente se transcribe
            words = []
            for w in s.words or []:
                text = w.word.strip()
                if text:
                    words.append(Word(text, round(float(w.start), 3), round(float(w.end), 3),
                                      round(float(w.probability), 3)))
            if words:
                out.segments.append(Segment(words))
            if progress and total > 0:
                progress(min(1.0, float(s.end) / total), s.text.strip())
        # Con device="auto" ctranslate2 elige; el modelo interno sabe cuál usó.
        self.used_device = str(getattr(getattr(model, "model", None), "device", device))
        out.meta.update({
            "engine": "faster-whisper",
            "model": self.model_name,
            "device": self.used_device,
            "language_probability": round(float(getattr(info, "language_probability", 0.0) or 0.0), 3),
            "audio_duration": round(total, 3),
        })
        return out
