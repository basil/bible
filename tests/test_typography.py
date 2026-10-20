"""Typography: quotes, ellipses and dashes curled from the words about them."""

from __future__ import annotations

import copy

import pytest

import bible.pipeline
from bible import scripture, typography, usj
from bible.checks import CheckFailed


def curled(body: str) -> str:
    doc = usj.parse(f"\\id GEN\n\\c 1\n\\p\n{body}\n")
    return usj.serialize(typography.typographic(doc)).split("\n", 4)[4].rstrip("\n")


@pytest.mark.parametrize(
    "body, expected",
    [
        # A quote opens after a space and closes after a word, across verses
        # and through the markup of supplied words.
        (
            "\\v 1 He said, 'Go,' and they went.\n\\v 2 'Stay,' said the \\add other\\add*'s son.",
            "\\v 1 He said, ‘Go,’ and they went.\n\\v 2 ‘Stay,’ said the \\add other\\add*’s son.",
        ),
        ('\\v 1 "Come" -- and they came...', "\\v 1 “Come” — and they came…"),
        # A quotation mark that closes a rendering closes.
        (
            "\\v 1 word \\f - \\fr 1:1 \\ft Alex. '\\fqa even Nabal\\ft '\\f*here",
            "\\v 1 word \\f - \\fr 1:1 \\ft Alex. ‘\\fqa even Nabal\\ft ’\\f*here",
        ),
    ],
)
def test_quotes_are_curled_by_the_words_about_them(body: str, expected: str) -> None:
    assert curled(body) == expected


def test_what_looks_like_markup_to_the_typographer_is_refused() -> None:
    with pytest.raises(CheckFailed, match="looks like HTML"):
        curled("\\v 1 a <b> c 'd'")
    with pytest.raises(CheckFailed, match="Ambiguous doubled quote"):
        curled("\\v 1 he said ''so''")
    with pytest.raises(CheckFailed, match="Backtick"):
        curled("\\v 1 the `word' of God")


def test_the_edition_is_sent_without_a_straight_quote(
    exported: dict[str, str], edition: bible.pipeline.Edition
) -> None:
    for code, text in exported.items():
        if code not in edition.authored:
            assert not typography.PLAIN.search(text), code
    # Only the form of the marks changes: the words are the prepared edition's.
    kingdoms = edition.documents["1KI"]
    assert (
        typography.count(kingdoms)
        == len(typography.PLAIN.findall(usj.serialize(kingdoms)))
        > 0
    )


def test_small_caps_distinguish_opening_god_from_divine_name_emphasis() -> None:
    source = usj.parse(
        "\\id HEB\n\\c 1\n\\p \\v 1 \\add \\+sc God\\+sc*\\add* spoke.\n"
        "\\p \\v 2 The \\sc Lord\\sc* \\f - \\ft A note.\\f*spoke."
    )
    before = copy.deepcopy(source)
    result = typography.small_caps(source)
    assert "\\add \\+sc God\\+sc*\\add*" in usj.serialize(result)
    assert "\\sc Lord" not in usj.serialize(result)
    assert [v.text for v in scripture.verses(result).values()] == [
        v.text for v in scripture.verses(source).values()
    ]
    assert source == before and typography.small_caps(result) == result
    # Unwrapped words run on as the parser would leave them.
    assert result == usj.parse(usj.serialize(result))


def test_a_declared_opening_keeps_its_small_capitals_or_is_refused() -> None:
    text = "\\id REV\n\\c 1\n\\p \\v 1 \\sc The\\sc* Revelation.\n\\p \\v 4 \\sc John\\sc*."
    assert "\\sc John\\sc*" in usj.serialize(typography.small_caps(usj.parse(text)))
    with pytest.raises(CheckFailed, match="REV 1:4"):
        typography.small_caps(usj.parse(text.replace("\\sc John\\sc*", "John")))


def test_selective_emphasis_is_unwrapped_without_new_speech_punctuation() -> None:
    source = usj.parse(
        "\\id MAT\n\\c 1\n\\p \\v 1 \\sc The\\sc* beginning.\n"
        "\\d \\v 2 \\sc A descriptive title.\\sc*\n"
        "\\p \\v 3 He said, \\sc Eli, Eli, \\add lama\\add* sabachthani\\sc*.\n"
        "\\p \\v 4 About \\sc Aquila\\sc* and \\sc Septuagint\\sc*."
    )
    result = usj.serialize(typography.small_caps(source))
    assert result.count("\\sc ") == 1
    assert "He said, Eli, Eli, \\add lama\\add* sabachthani." in result
    assert "About Aquila and Septuagint." in result


def test_a_title_that_opens_its_book_loses_its_small_capitals() -> None:
    source = usj.parse(
        "\\id LJE\n\\c 1\n\\d \\sc A copy\\sc* of an epistle.\n\\p \\v 1 For."
    )
    assert "\\sc" not in usj.serialize(typography.small_caps(source))


def test_only_the_audited_decorative_small_caps_remain(
    edition: bible.pipeline.Edition,
) -> None:
    spans: list[str] = []

    def collect(node: usj.Node) -> usj.Node:
        if usj.is_type(node, "char", "sc"):
            spans.append(usj.text_of(node["content"]))
        return node

    for doc in edition.documents.values():
        usj.with_content(doc, lambda content: usj.mapped(content, collect))
    assert len(spans) == 83
    assert spans.count("God") == 1  # Hebrews opens with this word.
    assert "Lord" not in spans
    for word in ("Some", "Great", "Zeal", "O Lord"):
        assert word in spans
