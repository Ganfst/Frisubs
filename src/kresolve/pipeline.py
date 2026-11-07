"""Orquesta las etapas. Lo usan la CLI y (vía subprocess) los scripts de menú."""

from __future__ import annotations

import json
from pathlib import Path

from .config import Config
from .exporters.json_io import load_transcript, save_transcript
from .exporters.srt import save_srt
from .models import TitleClip, Transcript
from .planning import make_plan
from .registry import get_grouper, get_transcriber_class

TRANSCRIPT_NAME = "transcript.json"


def audio_meta(audio: Path) -> dict:
    """Lee ``<audio>.meta.json`` si lo dejó export-audio (timeline, fps, offset)."""
    meta = Path(audio).with_name(Path(audio).stem + ".meta.json")
    if meta.is_file():
        try:
            return json.loads(meta.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def make_transcriber(cfg: Config, model: str | None = None, device: str | None = None, log=print):
    t = dict(cfg.section("transcriber"))
    engine = t.pop("engine", "faster-whisper")
    t.pop("language", None)
    if model:
        t["model"] = model
    if device:
        t["device"] = device
    return get_transcriber_class(engine)(log=log, **t)


def transcribe_audio(cfg: Config, audio, *, language: str | None = "config", model: str | None = None,
                     device: str | None = None, out: Path | None = None, log=print,
                     progress=None) -> tuple[Transcript, dict]:
    audio = Path(audio).resolve()
    if not audio.is_file():
        raise FileNotFoundError(f"No existe el audio: {audio}")
    if language == "config":
        language = cfg.section("transcriber").get("language")
    engine = make_transcriber(cfg, model, device, log)
    t = engine.transcribe(str(audio), language=language, progress=progress)
    t.meta["audio"] = str(audio)
    src = audio_meta(audio)
    if src:
        t.meta["source"] = src
    paths = write_outputs(cfg, t, out)
    return t, paths


def write_outputs(cfg: Config, t: Transcript, out: Path | None = None) -> dict:
    o = cfg.section("output")
    out = Path(out) if out else cfg.work_file(TRANSCRIPT_NAME)
    paths = {"json": save_transcript(t, out)}
    if o.get("save_srt", True):
        paths["srt"] = save_srt(t, out.with_suffix(".srt"), cfg.grouping_options)
    if o.get("save_ass"):
        from .overlay import write_ass
        from .planning import transform_clips
        ov = cfg.section("overlay")
        style = cfg.style()
        paths["ass"] = write_ass(transform_clips(group_clips(cfg, t), style), style, out.with_suffix(".ass"),
                                 int(ov.get("width") or 1920), int(ov.get("height") or 1080))
    return paths


def group_clips(cfg: Config, t: Transcript, strategy: str | None = None) -> list[TitleClip]:
    return get_grouper(strategy or cfg.strategy).group(t, **cfg.grouping_options)


def build_plan(cfg: Config, t: Transcript, strategy: str | None = None, style: str | None = None) -> dict:
    strategy = strategy or cfg.strategy
    source = t.meta.get("source") or {}
    return make_plan(group_clips(cfg, t, strategy), cfg.style(style), dict(cfg.section("resolve")),
                     strategy=strategy, offset_frames=int(source.get("offset_frames") or 0), source=source)


def load(cfg: Config, transcript_path, log=print) -> Transcript:
    return load_transcript(transcript_path, log=lambda m: log(f"AVISO: {m}"))


def build_titles(cfg: Config, client, t: Transcript, strategy: str | None = None, log=print):
    from .resolve.title_builder import TitleBuilder
    plan = build_plan(cfg, t, strategy)
    src_tl = plan["source"].get("timeline")
    if src_tl and src_tl != client.timeline_name:
        log(f"AVISO: el audio se exportó de '{src_tl}' y la timeline activa es '{client.timeline_name}'.")
    builder = TitleBuilder(client, plan["style"], plan["resolve"], log)
    return builder.build(plan["clips"], plan["offset_frames"])
