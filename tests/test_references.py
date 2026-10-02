"""References read from the edition's files and printed on its pages."""

import pytest

from bible.checks import CheckFailed
from bible.references import (
    EDITION,
    Books,
    Passage,
    Verse,
    parse_passage,
    parse_passages,
    parse_verse,
    roman,
    runs,
    verse_at,
)

BOOKS = Books({"ISA": "Esaias", "PRO": "Proverbs", "1CO": "1 Corinthians"})


@pytest.mark.parametrize(
    "written", ["ISA 40:3", "ISA 40:3-5", "PRO 22:8a", "1CO 2:9", "DAG 0:19"]
)
def test_a_passage_is_written_as_it_is_read(written):
    assert str(parse_passage(written)) == written


def test_a_passage_names_each_of_its_verses():
    verses = parse_passage("ISA 40:3-5").verses
    assert list(map(str, verses)) == ["ISA 40:3", "ISA 40:4", "ISA 40:5"]
    assert parse_passage("PRO 22:8a").verses == [Verse("PRO", 22, 8, "a")]


@pytest.mark.parametrize(
    "written,refusal",
    [
        ("PRO 22:8a-9", "Lettered verse in a range: PRO 22:8a-9"),
        ("ISA 40:5-3", "Reversed passage: ISA 40:5-3"),
        ("ISA 40:3-5a", "Malformed passage"),
        ("ISA 40:3-41:2", "Malformed passage"),
        ("Isaiah 40:3", "Malformed passage"),
        ("ISA 40", "Malformed passage"),
        ("", "Malformed passage"),
    ],
)
def test_a_malformed_passage_is_refused(written, refusal):
    with pytest.raises(CheckFailed, match=refusal):
        parse_passage(written)


def test_a_passage_keeps_to_one_chapter():
    with pytest.raises(CheckFailed, match="Passage beyond one chapter"):
        Passage(Verse("ISA", 8, 23), Verse("ISA", 9, 1))
    with pytest.raises(CheckFailed, match="Passage beyond one chapter"):
        Passage(Verse("ISA", 8, 23), Verse("JER", 8, 23))


def test_a_verse_is_no_range():
    assert parse_verse("PRO 22:8a") == Verse("PRO", 22, 8, "a")
    assert verse_at("PRO", "22:8a") == Verse("PRO", 22, 8, "a")
    with pytest.raises(CheckFailed, match="Malformed verse reference: ISA 40:3-5"):
        parse_verse("ISA 40:3-5")


def test_a_list_is_read_passage_by_passage():
    passages = parse_passages("EXO 20:13-16; DEU 5:17-20")
    assert list(map(str, passages)) == ["EXO 20:13-16", "DEU 5:17-20"]


@pytest.mark.parametrize(
    "verses,passages",
    [
        (
            "ISA 8:22; ISA 8:23; ISA 9:1; ISA 9:2; ISA 9:4",
            "ISA 8:22-23; ISA 9:1-2; ISA 9:4",
        ),
        # A lettered verse joins no run, nor does the verse after it continue it.
        ("PRO 22:7; PRO 22:8a; PRO 22:9", "PRO 22:7; PRO 22:8a; PRO 22:9"),
    ],
)
def test_consecutive_verses_run_together(verses, passages):
    found = runs(map(parse_verse, verses.split("; ")))
    assert "; ".join(map(str, found)) == passages


def test_books_order_verses_as_their_bible_does():
    verses = ["1CO 2:9", "PRO 22:9", "PRO 22:8a", "ISA 40:3", "PRO 22:8", "ISA 9:1"]
    ordered = sorted(map(parse_verse, verses), key=BOOKS.position)
    assert list(map(str, ordered)) == [
        "ISA 9:1",
        "ISA 40:3",
        "PRO 22:8",
        "PRO 22:8a",
        "PRO 22:9",
        "1CO 2:9",
    ]


def test_a_passage_prints_under_its_books_name():
    assert EDITION.passage(parse_passage("ISA 40:3-5"), BOOKS) == "Esaias 40:3–5"
    assert EDITION.passage(parse_passage("PRO 22:8a"), BOOKS) == "Proverbs 22:8a"
    with pytest.raises(CheckFailed, match="No display name for JER"):
        EDITION.passage(parse_passage("JER 1:1"), BOOKS)


def test_a_list_names_each_book_once():
    assert (
        EDITION.listed(parse_passages("ISA 8:23; ISA 9:1; 1CO 2:9"), BOOKS)
        == "Esaias 8:23; 9:1; 1 Corinthians 2:9"
    )
    # But again, where another book comes between.
    assert (
        EDITION.listed(parse_passages("ISA 8:23; 1CO 2:9; ISA 9:1"), BOOKS)
        == "Esaias 8:23; 1 Corinthians 2:9; Esaias 9:1"
    )


def test_one_of_a_books_chapters_may_have_its_own_name():
    books = Books({"PSA": "Psalms", "ISA": "Esaias"}, {"PSA": "Psalm"})
    assert EDITION.passage(parse_passage("PSA 117:22-23"), books) == "Psalm 117:22–23"
    assert EDITION.listed(parse_passages("PSA 2:1; PSA 2:7"), books) == "Psalm 2:1; 2:7"
    assert (
        EDITION.listed(parse_passages("PSA 2:7; PSA 109:1"), books)
        == "Psalms 2:7; 109:1"
    )
    assert books.name("PSA") == "Psalms" and books.name("ISA", [1]) == "Esaias"


@pytest.mark.parametrize(
    "numeral,number",
    [("I", 1), ("IV", 4), ("IX", 9), ("XIX", 19), ("XL", 40), ("CXVII", 117)],
)
def test_roman_numerals(numeral, number):
    assert roman(numeral) == number
