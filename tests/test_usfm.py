"""The USFM text helpers, on small synthetic USFM."""

import pytest

from bible import usfm


def test_canonical_text_keeps_words_numbers_and_punctuation():
    text = "\\v 1 In the \\add beginning\\add* God, \\wj 50\\asterisk\\wj*.\n"
    assert usfm.canonical_text(text) == "1InthebeginningGod,50*."


def test_plain_text_keeps_the_words_apart():
    text = "\\v 1 In the \\add beginning\\add*\n\\q1 God,  \\+it made\\+it*.\n"
    assert usfm.plain_text(text) == "1 In the beginning God, made."


@pytest.mark.parametrize(
    "text,words",
    [
        # An apostrophe joins a word, and a hyphen parts one.
        ("The King’s market-place", ["the", "kings", "market", "place"]),
        ("\\add the\\add* king, 2 kings", ["the", "king", "kings"]),
        # The Cambridge text marks part of a word as added (1 Thessalonians 4:12).
        ("of no\\add thing\\add*. high\\add*ways", ["of", "nothing", "highways"]),
    ],
)
def test_words_ignore_markup_case_and_punctuation(text, words):
    assert usfm.words_of(text) == words


def test_heading_joins_the_title_lines():
    text = "\\id 1SA\n\\h 1 Kingdoms\n\\mt2 THE FIRST BOOK OF \n\\mt1 KINGDOMS\n\\c 1\n"
    assert usfm.heading(text) == "THE FIRST BOOK OF KINGDOMS"
    assert usfm.heading("\\id FRT\n\\ip No title.\n") == ""


def test_verse_spans():
    text = "\\c 1\n\\p\n\\v 1 A.\n\\v 2 B.\n\\c 2\n\\v 1 C."
    assert [
        (reference, text[start:end]) for reference, start, end in usfm.verse_spans(text)
    ] == [("1:1", "A.\n"), ("1:2", "B.\n"), ("2:1", "C.")]


def test_inventory():
    text = "\\id GEN\n\\c 1\n\\p\n\\v 1 A\n\\v 2-3 B\n\\c 2\n\\v 1a C\\f + \\ft n\\f*\n"
    assert usfm.inventory(text) == {
        "chapters": {"1": ["1", "2-3"], "2": ["1a"]},
        "markers": {"c": 2, "f": 1, "f*": 1, "ft": 1, "id": 1, "p": 1, "v": 3},
    }
