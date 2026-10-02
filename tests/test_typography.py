"""Typography: quotes, ellipses and dashes curled from the words about them."""

import pytest

from bible import typography, usj
from bible.checks import CheckFailed


def curled(body):
    doc = usj.parse(f"\\id GEN\n\\c 1\n\\p\n{body}\n")
    return usj.serialize(typography.typographic(doc)).split("\n", 3)[3].rstrip("\n")


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
        # The sources' few `single' quotes open with a backtick.
        ("\\v 1 the `word' of God", "\\v 1 the ‘word’ of God"),
        # A quotation that opens a note's commentary after a rendering opens,
        # though no space stands before it; one that closes a rendering closes.
        (
            "\\v 1 word \\f - \\fr 1:1 \\fq word: \\ft Gr. \\fqa saying\\ft 'as some read'\\f*here",
            "\\v 1 word \\f - \\fr 1:1 \\fq word: \\ft Gr. \\fqa saying\\ft ‘as some read’\\f*here",
        ),
        (
            "\\v 1 word \\f - \\fr 1:1 \\ft Alex. '\\fqa even Nabal\\ft '\\f*here",
            "\\v 1 word \\f - \\fr 1:1 \\ft Alex. ‘\\fqa even Nabal\\ft ’\\f*here",
        ),
    ],
)
def test_quotes_are_curled_by_the_words_about_them(body, expected):
    assert curled(body) == expected


def test_what_looks_like_markup_to_the_typographer_is_refused():
    with pytest.raises(CheckFailed, match="looks like HTML"):
        curled("\\v 1 a <b> c 'd'")
    with pytest.raises(CheckFailed, match="Ambiguous doubled quote"):
        curled("\\v 1 he said ''so''")


def test_the_edition_is_sent_without_a_straight_quote(exported, edition):
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
