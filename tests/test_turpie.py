"""Turpie's transcription agrees with itself: each printed heading with its
normalized passages, and each row with its table's markers and numbering.

A misreading entered the same way in both fields passes; only the page
catches that.
"""

import re

import pytest

from bible.quotations import TURPIE
from bible.versemap import expand, parse

ROWS = TURPIE["rows"]
COLUMNS = ("nt", "lxx", "hebrew")
each_row = pytest.mark.parametrize("row", ROWS, ids=[row["id"] for row in ROWS])

BOOKS = {
    "Gen": "GEN",
    "Exod": "EXO",
    "Lev": "LEV",
    "Num": "NUM",
    "Deut": "DEU",
    "Josh": "JOS",
    "1 Sam": "1SA",
    "2 Sam": "2SA",
    "Job": "JOB",
    "Ps": "PSA",
    "Prov": "PRO",
    "Eccl": "ECC",
    "Is": "ISA",
    "Jer": "JER",
    "Jerem": "JER",
    "Ezek": "EZK",
    "Hos": "HOS",
    "Hosea": "HOS",
    "Joel": "JOL",
    "Amos": "AMO",
    "Mic": "MIC",
    "Hab": "HAB",
    "Hag": "HAG",
    "Zech": "ZEC",
    "Mal": "MAL",
    "Matt": "MAT",
    "Mark": "MRK",
    "Luke": "LUK",
    "John": "JHN",
    "Acts": "ACT",
    "Rom": "ROM",
    "1 Cor": "1CO",
    "2 Cor": "2CO",
    "Gal": "GAL",
    "Eph": "EPH",
    "1 Tim": "1TI",
    "2 Tim": "2TI",
    "Heb": "HEB",
    "James": "JAS",
    "1 Pet": "1PE",
    "2 Pet": "2PE",
    "Rev": "REV",
}
# The Septuagint's four books of Kingdoms; the Hebrew column's Kings are ours.
KINGS = {
    "lxx": {"1 Kings": "1SA", "2 Kings": "2SA", "3 Kings": "1KI", "4 Kings": "2KI"},
    "hebrew": {"1 Kings": "1KI", "2 Kings": "2KI"},
    "nt": {},
}
ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
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


def roman(numeral):
    values = [ROMAN[c] for c in numeral]
    return sum(-v if v < w else v for v, w in zip(values, values[1:] + [0]))


def number(chapter):
    return roman(chapter) if chapter[0] in ROMAN else int(chapter)


def printed_verses(printed, column):
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


def normalized_verses(passages):
    verses = []
    for passage in passages:
        for verse in expand(passage):
            book, chapter, v = parse(verse)
            verses.append((book, chapter, int(v)))
    return verses


@each_row
def test_part_markers_are_the_printed_ones(row):
    printed = VARIANT.sub("", row["nt"]["printed"])
    assert sorted(set(MARKER.findall(printed))) == row.get("part_markers", [])


@each_row
@pytest.mark.parametrize("column", COLUMNS)
def test_normalized_passages_are_the_printed_ones(row, column):
    heading = row[column]
    if "printed" not in heading:
        return
    normalized = normalized_verses(heading["normalized"].split("; "))
    printed = set(printed_verses(heading["printed"], column))
    assert set(normalized) <= printed
    assert len(normalized) == len(set(normalized))
    # A printed alternative or later heading is kept apart from the link.
    kept_apart = heading.get("alternative_normalized", []) + row.get(
        "additional_source_headings", {}
    ).get(f"{column}_normalized", [])
    assert printed <= set(normalized + normalized_verses(kept_apart))


@each_row
@pytest.mark.parametrize("column", COLUMNS)
def test_printed_headings_share_one_style(row, column):
    printed = row[column].get("printed")
    if printed is None:
        return
    assert printed.endswith("."), "A heading ends with a full stop"
    assert not re.search(r"\d\s*[-—]\s*\d", printed), "Ranges take an en dash"
    assert not re.search(r"\s{2}|\s\.|\.\.", printed), "Stray spacing or stops"


@each_row
def test_source_columns_differ_only_in_numbering(row):
    lxx, hebrew = row["lxx"].get("normalized"), row["hebrew"].get("normalized")
    if not (lxx and hebrew):
        return
    # A column's verses may run longer, or break at another chapter, so only
    # the books and the Psalm numbering are compared, passage by passage.
    kingdoms = {"1SA", "2SA", "1KI", "2KI"}
    lxx = [normalized_verses([p])[0] for p in lxx.split("; ")]
    hebrew = [normalized_verses([p])[0] for p in hebrew.split("; ")]

    def books(verses):
        return {"KINGDOMS" if b in kingdoms else b for b, _, _ in verses}

    assert books(lxx) == books(hebrew)
    if len(lxx) != len(hebrew):
        return
    for (book, chapter_a, _), (_, chapter_b, _) in zip(lxx, hebrew):
        if book == "PSA":
            # Psalms 10-147 of the Hebrew are one lower in the Septuagint, which
            # joins 9-10 and 114-115 and divides 116 and 147.
            assert chapter_b - chapter_a in (0, 1, 2), f"Psalm {chapter_a}, {chapter_b}"


def test_rows_follow_the_pages():
    pages = [row["pdf_page"] for row in ROWS]
    assert pages == sorted(pages)


def test_classes_follow_the_tables():
    # Turpie gives each class its own table, A to E in turn, so a row's page
    # fixes its class: a class read from the wrong table goes backwards.
    classes = [row["class"] for row in ROWS if row["kind"] == "table"]
    assert classes == sorted(classes)


def test_each_table_numbers_its_heads_in_order():
    """Turpie's own slips are retained, and a note on the slip says so."""
    previous = None
    for row in ROWS:
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
            notes = row.get("note", "") + (previous or {}).get("note", "")
            assert "as printed" in notes, row["id"]
        previous = row
