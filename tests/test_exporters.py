import json

import pytest

from kresolve.exporters.ass import ass_color, ass_time, clips_to_ass
from kresolve.exporters.json_io import load_plan, load_transcript, save_plan, save_transcript, transcript_from_dict
from kresolve.exporters.srt import format_ts, transcript_to_srt
from kresolve.models import LAYER_HIGHLIGHT, TitleClip


def test_json_roundtrip(sample, tmp_path):
    out = save_transcript(sample, tmp_path / "t.json")
    again = load_transcript(out)
    assert [s.text for s in again.segments] == [s.text for s in sample.segments]
    assert again.meta["source"]["start_frame"] == 86400
    text = out.read_text(encoding="utf-8")
    assert '"_text": "Hola que tal,' in text
    # una palabra por línea: fácil de editar a mano
    assert '{"text": "karaoke", "start": 2.950, "end": 3.600, "prob": 0.900}' in text
    json.loads(text)


def test_load_is_tolerant_to_hand_edits():
    warnings = []
    t = transcript_from_dict({"language": "es", "segments": [
        {"words": [{"text": "b", "start": "2.0", "end": 2.5}, {"text": "a", "start": 1.0, "end": 0.5},
                   {"text": "  ", "start": 3, "end": 4}]},
        {"text": "línea añadida a mano", "start": 5.0, "end": 7.0},
    ]}, log=warnings.append)
    assert [w.text for w in t.segments[0].words] == ["a", "b"]      # ordenadas
    assert t.segments[0].words[0].end == pytest.approx(1.05)         # end < start corregido
    assert [w.text for w in t.segments[1].words] == ["línea", "añadida", "a", "mano"]
    assert t.segments[1].words[0].start == 5.0 and t.segments[1].words[-1].end == pytest.approx(7.0)
    assert len(warnings) == 3


def test_load_reports_bad_numbers():
    with pytest.raises(ValueError, match=r"segments\[0\]\.words\[0\]\.start"):
        transcript_from_dict({"segments": [{"words": [{"text": "x", "start": "abc", "end": 1}]}]})


def test_load_reports_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text('{"segments": [ {"words": [}', encoding="utf-8")
    with pytest.raises(ValueError, match="línea 1"):
        load_transcript(p)


def test_srt(sample):
    assert format_ts(3725.5) == "01:02:05,500"
    srt = transcript_to_srt(sample, {"max_chars": 42})
    blocks = srt.strip().split("\n\n")
    assert blocks[0].startswith("1\n00:00:00,500 --> ")
    assert "Segunda frase tras un silencio" in blocks[-1]


def test_ass_colors_and_times():
    assert ass_time(3725.5) == "1:02:05.50"
    assert ass_color([1, 0.85, 0.1]) == "&H001AD9FF"
    assert ass_color([0, 0, 0], 0.5) == "&H80000000"


def test_ass_highlight_layer_hides_other_words():
    words = ["Hola", "que", "tal"]
    clips = [TitleClip(words, 0.5, 2.0), TitleClip(words, 0.8, 1.0, LAYER_HIGHLIGHT, highlight_index=1)]
    ass = clips_to_ass(clips, {"font": "Open Sans", "position": [0.5, 0.12]}, 1920, 1080)
    lines = [ln for ln in ass.splitlines() if ln.startswith("Dialogue:")]
    assert lines[0].startswith("Dialogue: 0,0:00:00.50,0:00:02.00")
    assert lines[0].endswith("{\\an5\\pos(960,950)}Hola que tal")
    assert "{\\alpha&HFF&}Hola {\\alpha&H00&\\1c&H1AD9FF&}que{\\alpha&HFF&} tal" in lines[1]
    assert lines[1].startswith("Dialogue: 1,")


def test_plan_roundtrip(tmp_path):
    clip = TitleClip(["a", "b"], 1.0, 2.0, LAYER_HIGHLIGHT, 1)
    p = save_plan({"version": 1, "style": {}, "clips": [clip]}, tmp_path / "plan.json")
    back = load_plan(p)["clips"][0]
    assert back == clip
    assert json.loads(p.read_text(encoding="utf-8"))["clips"][0]["text"] == "a b"
