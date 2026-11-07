import pytest
from fake_resolve import FakeClient

from kresolve.models import LAYER_BASE, LAYER_HIGHLIGHT
from kresolve.planning import plan_frames
from kresolve.registry import get_grouper
from kresolve.resolve.title_builder import TemplateNotFound, TitleBuilder

STYLE = {"highlight_color": [1, 0.85, 0.1], "color": None, "font": None, "size": None, "position": None}


def kresolve_tracks(tl):
    return {t["name"]: (i + 1, t["items"]) for i, t in enumerate(tl.tracks) if t["name"].startswith("kresolve")}


def build(client, sample, **opts):
    clips = get_grouper("per_line").group(sample)
    report = TitleBuilder(client, STYLE, opts, log=lambda m: None).build(clips)
    return clips, report


@pytest.mark.parametrize("record_mode, end_inclusive", [
    ("absolute", True), ("relative", True), ("absolute", False), ("relative", False),
])
def test_build_places_every_clip_exactly(sample, record_mode, end_inclusive):
    client = FakeClient(record_mode=record_mode, end_inclusive=end_inclusive)
    clips, report = build(client, sample)
    assert report.ok, report.summary()
    tracks = kresolve_tracks(client.timeline)
    assert set(tracks) == {"kresolve", "kresolve HL"}
    assert tracks["kresolve HL"][0] > tracks["kresolve"][0]        # resaltado por encima
    plan = plan_frames(clips, 24, 86400)
    for layer, name in ((LAYER_BASE, "kresolve"), (LAYER_HIGHLIGHT, "kresolve HL")):
        got = sorted((i.start, i.duration) for i in tracks[name][1])
        want = [(f.record_frame, f.duration) for f in plan[layer]]
        assert got == want
    # la pista del usuario no se toca
    assert len(client.timeline.tracks[0]["items"]) == 1


def test_text_style_and_writeon(sample):
    client = FakeClient()
    build(client, sample)
    tracks = kresolve_tracks(client.timeline)
    base = sorted(tracks["kresolve"][1], key=lambda i: i.start)
    hl = sorted(tracks["kresolve HL"][1], key=lambda i: i.start)
    assert base[0].comp.tool.inputs["StyledText"].startswith("Hola que tal,")
    assert "Red1" not in base[0].comp.tool.inputs                   # base: respeta la plantilla
    assert base[0].comp.tool.inputs["End"] == 1.0                    # base: Write On sin tocar
    first = hl[0].comp.tool.inputs
    assert first["StyledText"] == base[0].comp.tool.inputs["StyledText"]
    assert (first["Red1"], first["Green1"], first["Blue1"]) == (1.0, 0.85, 0.1)
    assert 0.0 <= first["Start"] < first["End"] < 0.2
    assert hl[0].name == "Hola" and hl[0].color == "Orange"
    assert all(i.comp.locked == 0 for i in hl)                       # Lock/Unlock equilibrados


def test_rebuild_replaces_previous_clips(sample):
    client = FakeClient()
    build(client, sample)
    n_tracks = len(client.timeline.tracks)
    first = {k: len(v[1]) for k, v in kresolve_tracks(client.timeline).items()}
    build(client, sample)
    assert len(client.timeline.tracks) == n_tracks                   # reutiliza pistas
    assert {k: len(v[1]) for k, v in kresolve_tracks(client.timeline).items()} == first


def test_rebuild_refuses_when_replace_disabled(sample):
    client = FakeClient()
    build(client, sample)
    with pytest.raises(RuntimeError, match="ya tiene"):
        build(client, sample, replace_existing=False)


def test_locked_track_is_unlocked(sample):
    client = FakeClient()
    build(client, sample)
    idx = kresolve_tracks(client.timeline)["kresolve"][0]
    client.timeline.tracks[idx - 1]["locked"] = True
    _, report = build(client, sample)
    assert report.ok


def test_template_not_found_lists_titles(sample):
    client = FakeClient(template_name="Mi titulo")
    with pytest.raises(TemplateNotFound, match=r"Mi titulo \(Fusion Title\)"):
        build(client, sample)


def test_custom_template_and_tool_names(sample):
    client = FakeClient(template_name="Karaoke")
    client.template.tool_name = "Text1"
    _, report = build(client, sample, template="karaoke", tool_name="NoExiste")
    assert report.ok                                                 # cae al primer TextPlus


def test_diagnostics_builds_on_a_separate_timeline(tmp_path):
    from kresolve.resolve.diagnostics import run_diagnostics
    client = FakeClient()
    user_timeline = client.timeline
    lines = []
    assert run_diagnostics(client, {}, STYLE, tmp_path, log=lines.append)
    assert client.timeline is not user_timeline and client.timeline.name == "kresolve_test"
    assert len(user_timeline.tracks) == 1                            # la timeline del usuario intacta
    base = kresolve_tracks(client.timeline)["kresolve"][1]
    assert sorted(i.comp.tool.inputs["StyledText"] for i in base) == ["Esto es una prueba", "de karaoke"]
    assert (tmp_path / "textplus_inputs.txt").exists()


def test_diagnostics_reports_missing_template(tmp_path):
    from kresolve.resolve.diagnostics import run_diagnostics
    lines = []
    assert not run_diagnostics(FakeClient(template_name="otro"), {}, STYLE, tmp_path, log=lines.append)
    assert any("No encuentro la plantilla" in ln for ln in lines)


def test_clear_removes_only_kresolve(sample):
    client = FakeClient()
    build(client, sample)
    removed = TitleBuilder(client, STYLE, {}, log=lambda m: None).clear(delete_tracks=True)
    assert removed > 0
    assert [t["name"] for t in client.timeline.tracks] == ["Video 1"]
