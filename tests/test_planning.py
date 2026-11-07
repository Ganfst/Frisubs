from fractions import Fraction

import pytest

from kresolve.models import LAYER_BASE, LAYER_HIGHLIGHT, TitleClip
from kresolve.planning import fps_fraction, plan_frames, resolve_style, transform_clips, writeon_range


@pytest.mark.parametrize("raw, exact", [
    ("24", Fraction(24)), (25, Fraction(25)), ("23.976", Fraction(24000, 1001)),
    ("29.97 DF", Fraction(30000, 1001)), (59.94, Fraction(60000, 1001)), ("23.98", Fraction(24000, 1001)),
])
def test_fps_fraction(raw, exact):
    assert fps_fraction(raw) == exact


def test_plan_frames_rounding_offsets_and_layers():
    clips = [TitleClip(["a"], 0.5, 1.0), TitleClip(["b"], 1.0, 1.5),
             TitleClip(["a"], 0.5, 0.75, LAYER_HIGHLIGHT, 0)]
    plan = plan_frames(clips, "24", timeline_start=86400, offset_frames=10)
    assert [(f.record_frame, f.duration) for f in plan[LAYER_BASE]] == [(86422, 12), (86434, 12)]
    assert [(f.record_frame, f.duration) for f in plan[LAYER_HIGHLIGHT]] == [(86422, 6)]


def test_plan_frames_never_overlaps_and_min_one_frame():
    clips = [TitleClip(["a"], 0.0, 0.01), TitleClip(["b"], 0.01, 0.02), TitleClip(["c"], 0.015, 1.0)]
    plan = plan_frames(clips, 24)[LAYER_BASE]
    assert all(f.duration >= 1 for f in plan)
    for a, b in zip(plan, plan[1:]):
        assert a.record_frame + a.duration <= b.record_frame


def test_plan_frames_ntsc_no_drift():
    clip = TitleClip(["x"], 3600.0, 3601.0)   # una hora
    f = plan_frames([clip], "23.976")[LAYER_BASE][0]
    assert f.record_frame == round(3600 * 24000 / 1001)


def test_writeon_range_only_shows_word():
    text = "Hola que tal"
    start, end = writeon_range(text, (5, 8))
    n = len(text)
    visible = [i for i in range(n) if start * n <= i < end * n]
    assert "".join(text[i] for i in visible).strip() == "que"
    visible_b = [i for i in range(n) if start * n < i + 1 <= end * n]   # otra convención de redondeo
    assert "".join(text[i] for i in visible_b).strip() == "que"


def test_writeon_range_without_spaces():
    s, e = writeon_range("Hola que tal", (5, 8), pad=0, count_spaces=False)
    assert (s, e) == (4 / 10, 7 / 10)


def test_resolve_style_and_uppercase():
    st = resolve_style({"x": {"uppercase": True}}, "x")
    assert st["name"] == "x" and st["font"] is None and st["highlight_color"]
    out = transform_clips([TitleClip(["hola", "qué"], 0, 1, LAYER_HIGHLIGHT, 1)], st)
    assert out[0].text == "HOLA QUÉ" and out[0].highlight_span == (5, 8)
    with pytest.raises(KeyError, match="no existe"):
        resolve_style({}, "nope")
