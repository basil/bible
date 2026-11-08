"""References read from the edition's files and printed on its pages."""

from __future__ import annotations

import pytest

from bible.checks import CheckFailed
from bible.references import (
    EDITION,
    Books,
    Item,
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
    "written",
    ["ISA 40:3", "ISA 40:3-5", "PRO 22:8a", "1CO 2:9", "DAG 0:19", "ACT 6:8-7:5"],
)
def test_a_passage_is_written_as_it_is_read(written: str) -> None:
    assert str(parse_passage(written)) == written


def test_a_passage_names_each_of_its_verses() -> None:
    verses = parse_passage("ISA 40:3-5").verses
    assert list(map(str, verses)) == ["ISA 40:3", "ISA 40:4", "ISA 40:5"]
    assert parse_passage("PRO 22:8a").verses == [Verse("PRO", 22, 8, "a")]


@pytest.mark.parametrize(
    "written,refusal",
    [
        ("PRO 22:8a-9", "Lettered verse in a range: PRO 22:8a-9"),
        ("ISA 40:5-3", "Reversed passage: ISA 40:5-3"),
        ("ISA 40:3-5a", "Malformed passage"),
        ("ISA 40:3-41:2a", "Malformed passage"),
        ("ISA 40:3-40:5", "Malformed passage"),
        ("ISA 41:2-40:3", "Reversed passage: ISA 41:2-40:3"),
        ("PRO 22:8a-23:1", "Lettered verse in a range: PRO 22:8a-23:1"),
        ("Isaiah 40:3", "Malformed passage"),
        ("ISA 40", "Malformed passage"),
        ("", "Malformed passage"),
    ],
)
def test_a_malformed_passage_is_refused(written: str, refusal: str) -> None:
    with pytest.raises(CheckFailed, match=refusal):
        parse_passage(written)


def test_a_passage_keeps_to_one_book() -> None:
    with pytest.raises(CheckFailed, match="Passage beyond one book"):
        Passage(Verse("ISA", 8, 23), Verse("JER", 8, 23))


def test_a_passage_may_stretch_to_a_later_chapter() -> None:
    stretch = parse_passage("ISA 8:23-9:1")
    assert stretch == Passage(Verse("ISA", 8, 23), Verse("ISA", 9, 1))
    assert stretch.stretches and not parse_passage("ISA 8:23").stretches
    # Its verses are known only from what the edition prints.
    with pytest.raises(CheckFailed, match="beyond one chapter need the inventory"):
        _ = stretch.verses
    assert EDITION.passage(stretch, BOOKS) == "Esaias 8:23–9:1"
    assert EDITION.within(parse_passage("ACT 6:8-7:5")) == "6:8–7:5"
    # A citation's item keeps to one chapter, and refuses a stretch rather
    # than lose its end.
    assert Item.of(parse_passage("ISA 8:20-23")) == Item(8, 20, 23)
    with pytest.raises(CheckFailed, match="Citation item beyond one chapter"):
        Item.of(stretch)
    # One that stretches over two psalms cites them as several.
    psalms = Books({"PSA": "Pss."}, {"PSA": "Ps."})
    assert EDITION.passage(parse_passage("PSA 9:20-10:3"), psalms) == "Pss. 9:20–10:3"
    assert EDITION.listed([parse_passage("PSA 9:20-10:3")], psalms) == (
        "Pss. 9:20–10:3"
    )


def test_a_verse_is_no_range() -> None:
    assert parse_verse("PRO 22:8a") == Verse("PRO", 22, 8, "a")
    assert verse_at("PRO", "22:8a") == Verse("PRO", 22, 8, "a")
    with pytest.raises(CheckFailed, match="Malformed verse reference: ISA 40:3-5"):
        parse_verse("ISA 40:3-5")


def test_a_list_is_read_passage_by_passage() -> None:
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
def test_consecutive_verses_run_together(verses: str, passages: str) -> None:
    found = runs(map(parse_verse, verses.split("; ")))
    assert "; ".join(map(str, found)) == passages


def test_books_order_verses_as_their_bible_does() -> None:
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


def test_a_passage_prints_under_its_books_name() -> None:
    assert EDITION.passage(parse_passage("ISA 40:3-5"), BOOKS) == "Esaias 40:3–5"
    assert EDITION.passage(parse_passage("PRO 22:8a"), BOOKS) == "Proverbs 22:8a"
    with pytest.raises(CheckFailed, match="No display name for JER"):
        EDITION.passage(parse_passage("JER 1:1"), BOOKS)


def test_a_list_joins_a_passage_to_the_chapter_the_last_ends_in() -> None:
    assert (
        EDITION.listed(parse_passages("ISA 6:8-7:5; ISA 7:47-60; ISA 8:1"), BOOKS)
        == "Esaias 6:8–7:5, 47–60; 8:1"
    )


def test_a_book_of_one_chapter_cites_its_verses_alone() -> None:
    books = Books({"JUD": "Jude", "ISA": "Esaias"}, chapterless=["JUD"])
    assert EDITION.passage(parse_passage("JUD 1:1-10"), books) == "Jude 1–10"
    assert EDITION.within(parse_passage("JUD 1:19"), books) == "19"
    assert EDITION.within(parse_passage("JUD 1:19")) == "1:19"
    assert (
        EDITION.listed(parse_passages("JUD 1:1-10; JUD 1:19; ISA 1:1"), books)
        == "Jude 1–10, 19; Esaias 1:1"
    )


def test_a_list_names_each_book_once() -> None:
    assert (
        EDITION.listed(parse_passages("ISA 8:23; ISA 9:1; 1CO 2:9"), BOOKS)
        == "Esaias 8:23; 9:1; 1 Corinthians 2:9"
    )
    # And each chapter once, where its passages stand together.
    assert (
        EDITION.listed(parse_passages("ISA 8:23; ISA 9:1; ISA 9:2-3; ISA 8:1"), BOOKS)
        == "Esaias 8:23; 9:1, 2–3; 8:1"
    )
    # But again, where another book comes between.
    assert (
        EDITION.listed(parse_passages("ISA 8:23; 1CO 2:9; ISA 9:1"), BOOKS)
        == "Esaias 8:23; 1 Corinthians 2:9; Esaias 9:1"
    )


def test_one_of_a_books_chapters_may_have_its_own_name() -> None:
    books = Books({"PSA": "Psalms", "ISA": "Esaias"}, {"PSA": "Psalm"})
    assert EDITION.passage(parse_passage("PSA 117:22-23"), books) == "Psalm 117:22–23"
    assert EDITION.listed(parse_passages("PSA 2:1; PSA 2:7"), books) == "Psalm 2:1, 7"
    assert (
        EDITION.listed(parse_passages("PSA 2:7; PSA 109:1"), books)
        == "Psalms 2:7; 109:1"
    )
    assert books.name("PSA") == "Psalms" and books.name("ISA", [1]) == "Esaias"


def test_a_books_abbreviation_may_have_one_for_a_single_chapter() -> None:
    books = Books(
        {"PSA": "Psalms"}, {"PSA": "Psalm"}, Books({"PSA": "Pss."}, {"PSA": "Ps."})
    )
    assert books.abbreviated.abbreviated is books.abbreviated
    assert (
        EDITION.listed(parse_passages("PSA 2:1; PSA 2:7"), books.abbreviated)
        == "Ps. 2:1, 7"
    )
    assert (
        EDITION.listed(parse_passages("PSA 2:7; PSA 109:1"), books.abbreviated)
        == "Pss. 2:7; 109:1"
    )


@pytest.mark.parametrize(
    "numeral,number",
    [("I", 1), ("IV", 4), ("IX", 9), ("XIX", 19), ("XL", 40), ("CXVII", 117)],
)
def test_roman_numerals(numeral: str, number: int) -> None:
    assert roman(numeral) == number
