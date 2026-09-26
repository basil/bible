"""Unit tests for the pipeline's text helpers, on small synthetic USFM."""

import pytest

import pipeline
from pipeline import CheckFailed
from source_inventory import inventory


def test_canonical_text_keeps_words_numbers_and_punctuation():
    text = "\\v 1 In the \\add beginning\\add* God, \\wj 50\\asterisk\\wj*.\n"
    assert pipeline.canonical_text(text) == "1InthebeginningGod,50*."


def test_passage_payload_ignores_headings_and_labels():
    text = (
        "\\id GEN\n\\h Genesis\n\\c 1\n\\s1 The Creation\n\\cp A\n\\p\n"
        "\\v 1 In the beginning\\f + \\fr 1:1 \\ft Or, first\\f*\n"
        "\\v 2 And the earth\\x - \\xo 1:2 \\xt Ps 1\\x*\n"
    )
    assert pipeline.passage_payload(text) == "Inthebeginning+Or,firstAndtheearth-Ps1"


def test_preserved_markers_counts_notes_and_styles_only():
    text = "\\p\n\\v 1 \\add he\\add* said\\f + \\fr 1:1 \\ft x\\f* \\+it y\\+it*"
    assert pipeline.preserved_markers(text) == {
        "add": 1,
        "add*": 1,
        "f": 1,
        "fr": 1,
        "ft": 1,
        "f*": 1,
        "+it": 1,
        "+it*": 1,
    }


def test_word_tokens_join_apostrophes_and_split_hyphens():
    assert pipeline.word_tokens("The King’s market-place") == [
        ("the", 0),
        ("kings", 4),
        ("market", 11),
        ("place", 18),
    ]


def test_word_tokens_offsets_index_the_usfm():
    text = "\\add the\\add* king"
    assert [(w, text[o : o + len(w)]) for w, o in pipeline.word_tokens(text)] == [
        ("the", "the"),
        ("king", "king"),
    ]


def test_verse_spans():
    text = "\\c 1\n\\p\n\\v 1 A.\n\\v 2 B.\n\\c 2\n\\v 1 C."
    assert [
        (reference, text[start:end])
        for reference, start, end in pipeline.verse_spans(text)
    ] == [("1:1", "A.\n"), ("1:2", "B.\n"), ("2:1", "C.")]


@pytest.mark.parametrize(
    "note, usfm",
    [
        ("Or, a thing", "\\f + \\fr 1:1 \\fqa Or, \\ft a thing.\\f*"),
        ("Gr. logos.", "\\f + \\fr 1:1 \\fqa Gr. \\ft logos.\\f*"),
        ("Who is he?", "\\f + \\fr 1:1 \\ft Who is he?\\f*"),
    ],
)
def test_marginal_note_usfm(note, usfm):
    assert pipeline.marginal_note_usfm("1:1", note) == usfm


@pytest.mark.parametrize(
    "value, marker, expected",
    [
        (
            "The Gospel according to S. John.",
            "toc1",
            "The Gospel according to Saint John",
        ),
        ("S. JOHN", "mt1", "SAINT JOHN"),
        ("The Epistle of JAS.", "h", "The Epistle of JAS"),
        ("Acts", "h", "Acts"),
    ],
)
def test_normalize_printed_title(value, marker, expected):
    assert pipeline.normalize_printed_title(value, marker) == expected


def test_normalize_title_lines_touches_only_the_first_of_each_marker():
    text = "\\h S. John.\n\\mt1 S. JOHN.\n\\p\n\\h S. Paul.\n"
    assert (
        pipeline.normalize_title_lines(text, ("h", "mt1"))
        == "\\h Saint John\n\\mt1 SAINT JOHN\n\\p\n\\h S. Paul.\n"
    )


BRENTON = {"id": "GEN", "source": "brenton"}
NAMES = {"title": "The First Book of Moses, Called Genesis"}


def test_heading_lines_default_to_one_main_line():
    assert pipeline.heading_lines(BRENTON, NAMES) == [
        ("mt1", "THE FIRST BOOK OF MOSES, CALLED GENESIS")
    ]


def test_heading_lines_follow_the_manifest():
    entry = {
        **BRENTON,
        "heading": [
            ["mt2", "The First Book of Moses,"],
            ["mt3", "Called"],
            ["mt1", "Genesis"],
        ],
    }
    assert pipeline.heading_lines(entry, NAMES) == [
        ("mt2", "THE FIRST BOOK OF MOSES,"),
        ("mt3", "CALLED"),
        ("mt1", "GENESIS"),
    ]


def test_cambridge_books_keep_their_own_headings():
    assert pipeline.heading_lines({"id": "MAT", "source": "kjv"}, NAMES) is None
    with pytest.raises(CheckFailed, match="keep their own heading layout"):
        pipeline.heading_lines(
            {"id": "MAT", "source": "kjv", "heading": [["mt1", "x"]]}, NAMES
        )


@pytest.mark.parametrize(
    "heading",
    [
        [["mt2", "The First Book of Moses, Called Genesis"]],
        [["mt1", "The First Book of Moses,"], ["mt1", "Called Genesis"]],
        [["mt4", "The First Book of Moses,"], ["mt1", "Called Genesis"]],
        [["mt2", "The First Book of Moses, "], ["mt1", "Called Genesis"]],
        [["mt2", ""], ["mt1", "The First Book of Moses, Called Genesis"]],
        [["mt1", "The First Book of Moses, Called Genesis", "extra"]],
        "The First Book of Moses, Called Genesis",
    ],
)
def test_invalid_heading_layouts(heading):
    with pytest.raises(CheckFailed, match="Invalid heading: GEN"):
        pipeline.heading_lines({**BRENTON, "heading": heading}, NAMES)


def test_heading_lines_must_spell_the_title():
    entry = {**BRENTON, "heading": [["mt2", "The Book of"], ["mt1", "Genesis"]]}
    with pytest.raises(CheckFailed, match="do not spell the contents title"):
        pipeline.heading_lines(entry, NAMES)


@pytest.mark.parametrize(
    "code, names",
    [
        (
            "JAS",
            (
                "The Catholic Epistle of Saint James",
                "THE CATHOLIC EPISTLE OF",
                "SAINT JAMES",
            ),
        ),
        (
            "1PE",
            (
                "The First Catholic Epistle of Saint Peter",
                "THE FIRST CATHOLIC EPISTLE OF",
                "SAINT PETER",
            ),
        ),
    ],
)
def test_catholic_epistle_names(code, names):
    assert pipeline.catholic_epistle_names(code) == names


def test_typographic_quotes():
    text = "\\c 1\n\\v 1 He said, \"Go--now.\" It's `done'...\n"
    result, count = pipeline.typographic_quotes(text)
    assert result == "\\c 1\n\\v 1 He said, “Go—now.” It’s ‘done’…\n"
    assert count == 7


@pytest.mark.parametrize(
    "text, message",
    [
        ("\\v 1 a <b> c", "looks like HTML"),
        ('\\v 1 a \\"b', "SmartyPants escape"),
        ("\\v 1 a ''b''", "Ambiguous doubled quote"),
        ("\\v 1 a `1", "Backtick is not an opening quote"),
    ],
)
def test_typographic_quotes_refuses_ambiguous_text(text, message):
    with pytest.raises(CheckFailed, match=message):
        pipeline.typographic_quotes(text)


def test_note_callers_may_repeat_on_different_pages():
    pipeline.check_note_callers("a 1:1 First.\nb 1:2 Second.\n\fa 1:3 Third.\n")


def test_note_callers_may_not_repeat_on_one_page():
    with pytest.raises(CheckFailed, match=r"page 2: \['a'\]"):
        pipeline.check_note_callers("\fa 1:1 First.\na 1:3 Second.\n")


def test_inventory():
    text = "\\id GEN\n\\c 1\n\\p\n\\v 1 A\n\\v 2-3 B\n\\c 2\n\\v 1a C\\f + \\ft n\\f*\n"
    assert inventory(text) == {
        "chapters": {"1": ["1", "2-3"], "2": ["1a"]},
        "markers": {"c": 2, "f": 1, "f*": 1, "ft": 1, "id": 1, "p": 1, "v": 3},
    }


@pytest.mark.parametrize(
    "text, message",
    [
        ("\\c 1\n\\v 1 A\n\\c 1\n", "Duplicate chapter 1"),
        ("\\c 1\n\\v 1 A\n\\v 1 B\n", "Duplicate verse 1:1"),
        ("\\v 1 A\n\\c 1\n", "Verse before chapter"),
    ],
)
def test_inventory_rejects_malformed_numbering(text, message):
    with pytest.raises(ValueError, match=message):
        inventory(text)
