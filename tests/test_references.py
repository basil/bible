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


def test_consecutive_verses_run_together():
    verses = [
        *parse_passage("ISA 8:22-23").verses,
        *parse_passage("ISA 9:1-2").verses,
        parse_verse("ISA 9:4"),
    ]
    assert list(map(str, runs(verses))) == ["ISA 8:22-23", "ISA 9:1-2", "ISA 9:4"]


def test_a_lettered_verse_joins_no_run():
    verses = [Verse("PRO", 22, 7), Verse("PRO", 22, 8, "a"), Verse("PRO", 22, 9)]
    assert list(map(str, runs(verses))) == ["PRO 22:7", "PRO 22:8a", "PRO 22:9"]
    # Nor does the verse after a lettered one continue it.
    verses = [Verse("PRO", 22, 8, "a"), Verse("PRO", 22, 9)]
    assert list(map(str, runs(verses))) == ["PRO 22:8a", "PRO 22:9"]


def test_a_verse_is_usable_as_a_key():
    assert {parse_verse("ISA 1:9"): 1}[Verse("ISA", 1, 9)] == 1
    assert len({parse_verse("ISA 1:9"), verse_at("ISA", "1:9")}) == 1


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
    assert (
        EDITION.listed(parse_passages("ISA 8:23; ISA 9:1; 1CO 2:9"), BOOKS)
        == "Esaias 8:23; Esaias 9:1; 1 Corinthians 2:9"
    )
    with pytest.raises(CheckFailed, match="No display name for JER 1:1"):
        EDITION.passage(parse_passage("JER 1:1"), BOOKS)


@pytest.mark.parametrize(
    "numeral,number",
    [("I", 1), ("IV", 4), ("IX", 9), ("XIX", 19), ("XL", 40), ("CXVII", 117)],
)
def test_roman_numerals(numeral, number):
    assert roman(numeral) == number
