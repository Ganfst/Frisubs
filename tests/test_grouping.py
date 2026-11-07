from kresolve.grouping.base import apply_padding, split_segment
from kresolve.models import LAYER_BASE, LAYER_HIGHLIGHT, Segment, TitleClip, Word, word_span
from kresolve.registry import get_grouper, grouper_names


def words(*specs):
    return [Word(t, s, e) for t, s, e in specs]


def test_registry_has_builtin_groupers():
    assert {"per_word", "per_line", "per_line_single", "sliding"} <= set(grouper_names())


def test_per_word_one_clip_per_word_and_fill_gaps(sample):
    clips = get_grouper("per_word").group(sample)
    assert len(clips) == sum(len(s.words) for s in sample.segments)
    # "tal," acaba en 1.4 y "esto" empieza en 1.6: hueco < max_gap -> se rellena
    tal = next(c for c in clips if c.text == "tal,")
    assert tal.end == 1.6
    # último de la frase: no hay siguiente, se queda en su fin
    assert next(c for c in clips if c.text == "Resolve.").end == 4.4


def test_per_word_without_fill_gaps(sample):
    clips = get_grouper("per_word").group(sample, fill_gaps=False)
    assert next(c for c in clips if c.text == "tal,").end == 1.4


def test_per_line_layers_and_highlight_windows(sample):
    clips = get_grouper("per_line").group(sample, lead_in=0, hold=0)
    base = [c for c in clips if c.layer == LAYER_BASE]
    hl = [c for c in clips if c.layer == LAYER_HIGHLIGHT]
    assert len(hl) == 16                     # una por palabra
    assert len(base) >= 2
    for c in hl:
        line = next(b for b in base if b.start <= c.start < b.end or b.start == c.start)
        assert c.text == line.text           # misma frase: la capa HL cae encima
        assert c.highlight_index is not None
    # ventanas contiguas dentro de una línea: fin de una = inicio de la siguiente
    first_line = [c for c in hl if c.text == base[0].text]
    for a, b in zip(first_line, first_line[1:]):
        assert a.end == b.start


def test_per_line_padding_no_overlap(sample):
    clips = get_grouper("per_line").group(sample, lead_in=0.2, hold=0.3)
    base = sorted((c for c in clips if c.layer == LAYER_BASE), key=lambda c: c.start)
    assert base[0].start == 0.3              # 0.5 - lead_in
    for a, b in zip(base, base[1:]):
        assert a.end <= b.start


def test_per_line_single_has_no_highlight(sample):
    clips = get_grouper("per_line_single").group(sample)
    assert clips and all(c.layer == LAYER_BASE and c.highlight_index is None for c in clips)


def test_sliding_window(sample):
    clips = get_grouper("sliding").group(sample, window=3, highlight=True, max_chars=200, max_words=20)
    base = [c for c in clips if c.layer == LAYER_BASE]
    assert base[0].words == ["Hola"]
    assert base[1].words == ["Hola", "que"]
    assert base[3].words == ["que", "tal,", "esto"]
    hl = [c for c in clips if c.layer == LAYER_HIGHLIGHT]
    assert all(c.highlight_index == len(c.words) - 1 for c in hl)


def test_split_segment_limits():
    seg = Segment(words(("uno", 0, 1), ("dos", 1, 2), ("tres", 2, 3), ("cuatro", 3, 4)))
    assert [s.text for s in split_segment(seg, 200, 2, 10)] == ["uno dos", "tres cuatro"]
    assert [s.text for s in split_segment(seg, 8, 10, 10)] == ["uno dos", "tres", "cuatro"]


def test_split_segment_gap_and_punctuation():
    seg = Segment(words(("hola", 0, 0.5), ("mundo", 3.0, 3.5), ("adiós", 3.5, 4)))
    assert [s.text for s in split_segment(seg, 42, 8, 1.0)] == ["hola", "mundo adiós"]
    seg = Segment(words(("una", 0, 1), ("frase.", 1, 2), ("otra", 2, 3)))
    assert [s.text for s in split_segment(seg, 12, 8, 10)] == ["una frase.", "otra"]


def test_apply_padding_keeps_order():
    clips = [TitleClip(["a"], 1.0, 2.0), TitleClip(["b"], 2.1, 3.0)]
    apply_padding(clips, lead_in=0.5, hold=0.5)
    assert clips[0].start == 0.5
    assert clips[0].end <= clips[1].start
    assert clips[1].start == 2.0              # lead_in limitado por el fin original de "a"
    assert clips[1].end == 3.5


def test_word_span():
    w = ["Hola", "que", "tal"]
    assert word_span(w, 0) == (0, 4)
    assert word_span(w, 1) == (5, 8)
    assert " ".join(w)[5:8] == "que"
    assert TitleClip(w, 0, 1, highlight_index=2).highlight_span == (9, 12)
