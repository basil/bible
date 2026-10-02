"""Turpie's transcription agrees with itself: each printed heading with its
normalized passages, and each row with its table's markers and numbering.

A misreading entered the same way in both fields passes; only the page
catches that.
"""

from __future__ import annotations

import re

import pytest

import bible.policy
from bible.policy_schema import TurpieHeading, TurpieRows
from bible.references import ROMAN, parse_passage, roman

# Turpie's names for the books.
BOOKS = dict(
    name.split("=")
    for name in (
        "Gen=GEN, Exod=EXO, Lev=LEV, Num=NUM, Deut=DEU, Josh=JOS, 1 Sam=1SA, "
        "2 Sam=2SA, Job=JOB, Ps=PSA, Prov=PRO, Eccl=ECC, Is=ISA, Jer=JER, "
        "Jerem=JER, Ezek=EZK, Hos=HOS, Hosea=HOS, Joel=JOL, Amos=AMO, Mic=MIC, "
        "Hab=HAB, Hag=HAG, Zech=ZEC, Mal=MAL, Matt=MAT, Mark=MRK, Luke=LUK, "
        "John=JHN, Acts=ACT, Rom=ROM, 1 Cor=1CO, 2 Cor=2CO, Gal=GAL, Eph=EPH, "
        "1 Tim=1TI, 2 Tim=2TI, Heb=HEB, James=JAS, 1 Pet=1PE, 2 Pet=2PE, Rev=REV"
    ).split(", ")
)
# The Septuagint's four books of Kingdoms; the Hebrew column's Kings are ours.
KINGS = {
    "lxx": {"1 Kings": "1SA", "2 Kings": "2SA", "3 Kings": "1KI", "4 Kings": "2KI"},
    "hebrew": {"1 Kings": "1KI", "2 Kings": "2KI"},
    "nt": {},
}
MARKER = re.compile(r"\b(lp|fp)\b")
# A textual variant beside a heading, as "(and 28 lp. in ς)", names no source.
VARIANT = re.compile(r"\s*\(and \d+ lp\. in ς\)")
SEGMENT = re.compile(
    r"(?:(?P<book>[1-4] [A-Z][a-z]+|[A-Z][a-z]+)\.?\s+)?"
    r"(?P<chapter>[IVXLC]+|\d+)\.\s*(?P<verses>.+)"
)
VERSES = re.compile(
    r"(?:(?P<chapter>[IVXLC]+)\.\s*)?(?P<first>\d+)"
    r"(?:\s*–\s*(?:(?P<to_chapter>[IVXLC]+)\.\s*)?(?P<last>\d+))?"
)


def number(chapter: str) -> int:
    return roman(chapter) if chapter[0] in ROMAN else int(chapter)


def printed_verses(
    printed: str, column: str
) -> list[tuple[str | None, int | None, int]]:
    """Every verse a printed heading names, as (book, chapter, verse).

    A heading may leave out its book, or its book and chapter ("ver. 15."), to
    carry them over from the one before it; "——. ——. 8." does the same. A
    parenthesis gives the Hebrew numbering, and names nothing new.
    """
    verses, book, chapter = [], None, None
    printed = MARKER.sub("", VARIANT.sub("", printed)).replace(" .", ".")
    for segment in re.split(r";\s*", printed.rstrip(".")):
        segment = re.sub(r"\s*\([^)]*\)", "", segment).replace("——. ——.", "")
        segment = segment.strip().rstrip(".")
        if match := re.fullmatch(r"ver\.\s+(.+)", segment):
            listed = match[1]
        elif match := re.fullmatch(r"\d+", segment):
            listed = segment
        else:
            match = SEGMENT.fullmatch(segment)
            assert match, f"Unreadable printed heading: {segment!r}"
            if match["book"]:
                book = KINGS[column].get(match["book"]) or BOOKS[match["book"]]
            chapter, listed = number(match["chapter"]), match["verses"]
        # Listed verses are joined by "and", "or", a comma, or a full stop.
        joins = r",\s*|(?<=\d)\.\s+(?=\d)|\s+and\s+|\s+or\s+"
        for part in re.split(joins, listed.rstrip(".")):
            match = VERSES.fullmatch(part.strip())
            assert match, f"Unreadable printed verses: {part!r}"
            if match["chapter"]:
                chapter = roman(match["chapter"])
            first = int(match["first"])
            if match["to_chapter"]:
                # A range across a chapter runs to the next chapter's verse.
                verses.append((book, chapter, first))
                chapter = roman(match["to_chapter"])
                first = 1
            last = int(match["last"] or first)
            verses += [(book, chapter, v) for v in range(first, last + 1)]
    return verses


def normalized_verses(passages: list[str]) -> list[tuple[str, int, int]]:
    return [
        (verse.book, verse.chapter, verse.number)
        for passage in passages
        for verse in parse_passage(passage).verses
    ]


@pytest.fixture(scope="module")
def rows(policy: bible.policy.Policy) -> tuple[TurpieRows, ...]:
    return policy.turpie["rows"]


@pytest.fixture(scope="module")
def headings(
    rows: tuple[TurpieRows, ...],
) -> list[tuple[str, TurpieRows, str, TurpieHeading]]:
    """Each heading that Turpie prints, as (where it stands, its row, its
    column, the heading)."""
    return [
        (f"{row['id']} {column}", row, column, row[column])
        for row in rows
        for column in ("nt", "lxx", "hebrew")
        if "printed" in row[column]
    ]


def test_part_markers_are_the_printed_ones(rows: tuple[TurpieRows, ...]) -> None:
    for row in rows:
        printed = VARIANT.sub("", row["nt"]["printed"])
        markers = sorted(set(MARKER.findall(printed)))
        assert markers == list(row.get("part_markers", ())), row["id"]


def test_normalized_passages_are_the_printed_ones(
    headings: list[tuple[str, TurpieRows, str, TurpieHeading]],
) -> None:
    for where, row, column, heading in headings:
        assert heading["normalized"] is not None
        normalized = normalized_verses(heading["normalized"].split("; "))
        printed = set(printed_verses(heading["printed"], column))
        assert set(normalized) <= printed, where
        assert len(normalized) == len(set(normalized)), where
        # A printed alternative or later heading is kept apart from the link.
        later = row.get("additional_source_headings", {})
        # Only a source column has later headings; the New Testament's has none.
        later_headings: tuple[str, ...] = ()
        if column == "lxx":
            later_headings = later.get("lxx_normalized", ())
        elif column == "hebrew":
            later_headings = later.get("hebrew_normalized", ())
        kept_apart = normalized_verses(
            [*heading.get("alternative_normalized", ()), *later_headings]
        )
        assert printed <= set(normalized + kept_apart), where


def test_printed_headings_share_one_style(
    headings: list[tuple[str, TurpieRows, str, TurpieHeading]],
) -> None:
    for where, _, _, heading in headings:
        printed = heading["printed"]
        assert printed.endswith("."), f"A heading ends with a full stop: {where}"
        ranged = re.search(r"\d\s*[-—]\s*\d", printed)
        assert not ranged, f"Ranges take an en dash: {where}"
        stray = re.search(r"\s{2}|\s\.|\.\.", printed)
        assert not stray, f"Stray spacing or stops: {where}"


def test_source_columns_differ_only_in_numbering(
    rows: tuple[TurpieRows, ...],
) -> None:
    # A column's verses may run longer, or break at another chapter, so only
    # the books and the Psalm numbering are compared, passage by passage.
    kingdoms = {"1SA", "2SA", "1KI", "2KI"}

    def firsts(heading: TurpieHeading) -> list[tuple[str, int, int]]:
        assert heading["normalized"] is not None
        return [normalized_verses([p])[0] for p in heading["normalized"].split("; ")]

    def books(verses: list[tuple[str, int, int]]) -> set[str]:
        return {"KINGDOMS" if b in kingdoms else b for b, _, _ in verses}

    for row in rows:
        if not (row["lxx"].get("normalized") and row["hebrew"].get("normalized")):
            continue
        lxx, hebrew = firsts(row["lxx"]), firsts(row["hebrew"])
        assert books(lxx) == books(hebrew), row["id"]
        if len(lxx) != len(hebrew):
            continue
        for (book, chapter_a, _), (_, chapter_b, _) in zip(lxx, hebrew):
            # Psalms 10-147 of the Hebrew are one lower in the Septuagint, which
            # joins 9-10 and 114-115 and divides 116 and 147.
            assert book != "PSA" or chapter_b - chapter_a in (0, 1, 2), row["id"]


def test_rows_follow_the_pages_and_classes_the_tables(
    rows: tuple[TurpieRows, ...],
) -> None:
    pages = [row["pdf_page"] for row in rows]
    assert pages == sorted(pages)
    # Turpie gives each class its own table, A to E in turn, so a row's page
    # fixes its class: a class read from the wrong table goes backwards.
    classes = [row["class"] for row in rows if row["kind"] == "table"]
    assert all(c is not None for c in classes)
    assert classes == sorted(c for c in classes if c is not None)


def test_each_table_numbers_its_heads_in_order(
    rows: tuple[TurpieRows, ...],
) -> None:
    """Turpie's own slips are retained, and a note on the slip says so."""
    previous = None
    for row in rows:
        sequence = re.fullmatch(r"\((\d+)\)", row.get("printed_sequence", ""))
        if row["kind"] != "table" or not sequence:
            continue
        number = int(sequence[1])
        if previous and previous["table_code"] == row["table_code"]:
            expected = int(previous["printed_sequence"].strip("()")) + 1
        else:
            expected = 1
        if number != expected:
            # A skip after a repeated number is noted at the repeat.
            notes = row.get("note", "") + (previous.get("note", "") if previous else "")
            assert "as printed" in notes, row["id"]
        previous = row
