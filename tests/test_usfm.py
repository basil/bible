"""The USFM text helpers, on small synthetic USFM."""

import pytest

from bible import usfm
from bible.usfm import inventory


def test_canonical_text_keeps_words_numbers_and_punctuation():
    text = "\\v 1 In the \\add beginning\\add* God, \\wj 50\\asterisk\\wj*.\n"
    assert usfm.canonical_text(text) == "1InthebeginningGod,50*."


def test_passage_payload_ignores_headings_and_labels():
    text = (
        "\\id GEN\n\\h Genesis\n\\c 1\n\\s1 The Creation\n\\cp A\n\\p\n"
        "\\v 1 In the beginning\\f + \\fr 1:1 \\ft Or, first\\f*\n"
        "\\v 2 And the earth\\x - \\xo 1:2 \\xt Ps 1\\x*\n"
    )
    assert usfm.passage_payload(text) == "Inthebeginning+Or,firstAndtheearth-Ps1"


def test_preserved_markers_counts_notes_and_styles_only():
    text = "\\p\n\\v 1 \\add he\\add* said\\f + \\fr 1:1 \\ft x\\f* \\+it y\\+it*"
    assert usfm.preserved_markers(text) == {
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
    assert usfm.word_tokens("The King’s market-place") == [
        ("the", 0),
        ("kings", 4),
        ("market", 11),
        ("place", 18),
    ]


def test_word_tokens_offsets_index_the_usfm():
    text = "\\add the\\add* king"
    assert [(w, text[o : o + len(w)]) for w, o in usfm.word_tokens(text)] == [
        ("the", "the"),
        ("king", "king"),
    ]


def test_renumber_chapters():
    chapters = ["\\c 11\n\\v 1 A \\c 11 B\n", "\\c 12\n\\v 1 C\n"]
    assert usfm.renumber_chapters(chapters, 10) == [
        "\\c 1\n\\v 1 A \\c 11 B\n",
        "\\c 2\n\\v 1 C\n",
    ]


def test_verse_spans():
    text = "\\c 1\n\\p\n\\v 1 A.\n\\v 2 B.\n\\c 2\n\\v 1 C."
    assert [
        (reference, text[start:end]) for reference, start, end in usfm.verse_spans(text)
    ] == [("1:1", "A.\n"), ("1:2", "B.\n"), ("2:1", "C.")]


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
