"""The edition's editorial policy: selection, order, titles, and headings."""

from collections import Counter
from pathlib import Path
import re

import pytest

import pipeline
from pipeline import (
    EDITION,
    SOURCES,
    canonical_text,
    scripture_unit,
    source_id,
    source_marker,
    source_usfm,
)

UNITS = EDITION["scripture"]
BRENTON_UNITS = [u for u in UNITS if u["source"] == "brenton"]
IDS = [u["id"] for u in UNITS]

ORTHODOX_OLD_TESTAMENT = """
    GEN EXO LEV NUM DEU JOS JDG RUT 1SA 2SA 1KI 2KI 1CH 2CH MAN 1ES EZR NEH
    TOB JDT ESG 1MA 2MA 3MA 4MA PSA JOB PRO ECC SNG WIS SIR HOS AMO MIC JOL
    OBA JON NAM HAB ZEP HAG ZEC MAL ISA JER BAR LAM LJE EZK DAG
""".split()

# Brenton titles this edition revises; every other Brenton unit keeps its toc1.
REVISED_TITLES = {
    "GEN": "The First Book of Moses, Called Genesis",
    "EXO": "The Second Book of Moses, Called Exodus",
    "LEV": "The Third Book of Moses, Called Leviticus",
    "NUM": "The Fourth Book of Moses, Called Numbers",
    "DEU": "The Fifth Book of Moses, Called Deuteronomy",
    "JOS": "The Book of Jesus, the Son of Navi",
    "JDG": "The Book of Judges",
    "RUT": "The Book of Ruth",
    "EZK": "The Book of the Prophet Ezekiel",
    "MIC": "Michaias",
    "1SA": "The First Book of Kingdoms, Otherwise Called, The First Book of Samuel",
    "2SA": "The Second Book of Kingdoms, Otherwise Called, The Second Book of Samuel",
    "1KI": "The Third Book of Kingdoms, Otherwise Called, The First Book of the Kings",
    "2KI": "The Fourth Book of Kingdoms, Otherwise Called, The Second Book of the Kings",
    "1CH": "The First Book of the Chronicles",
    "2CH": "The Second Book of the Chronicles",
    "MAN": "The Prayer of Manasses King of Juda, When He Was Holden Captive in Babylon",
    "1ES": "The First Book of Esdras",
    "EZR": "The Second Book of Esdras",
    "NEH": "The Book of Nehemias",
    "ESG": "The Book of Esther",
    "DAG": "The Book of Daniel",
    "SNG": "The Song of Songs",
    "WIS": "The Wisdom of Solomon",
    "SIR": "The Wisdom of Jesus, the Son of Sirach, or, Ecclesiasticus",
    "LAM": "The Lamentations of Jeremias",
    "LJE": "The Epistle of Jeremy",
    "1MA": "The First Book of the Maccabees",
    "2MA": "The Second Book of the Maccabees",
    "3MA": "The Third Book of the Maccabees",
    "4MA": "The Fourth Book of the Maccabees",
    "PSA": "The Book of Psalms",
    "JOB": "The Book of Job",
    "PRO": "The Proverbs",
    "ECC": "Ecclesiastes, or, The Preacher",
    "ISA": "The Book of the Prophet Esaias",
    "JER": "The Book of the Prophet Jeremias",
}

PAULINE_EPISTLES = "ROM 1CO 2CO GAL EPH PHP COL 1TH 2TH 1TI 2TI TIT PHM HEB".split()

# The letters of James, Peter, John, and Jude, as the Greek tradition names them.
CATHOLIC_EPISTLES = {
    "JAS": ("", "James"),
    "1PE": ("First ", "Peter"),
    "2PE": ("Second ", "Peter"),
    "1JN": ("First ", "John"),
    "2JN": ("Second ", "John"),
    "3JN": ("Third ", "John"),
    "JUD": ("", "Jude"),
}

SAINT_HEADINGS = {
    "MAT": {"mt1": "SAINT MATTHEW"},
    "MRK": {"mt1": "SAINT MARK"},
    "LUK": {"mt1": "SAINT LUKE"},
    "JHN": {"mt1": "SAINT JOHN"},
    "REV": {"mt2": "SAINT JOHN THE DIVINE"},
}

# Brenton files printed as front matter or appendices, or left out: the
# standalone Nehemias witness (Nehemias is printed from the combined
# Ezra-Nehemiah file).
BRENTON_NON_SCRIPTURE = {
    source_id(e)
    for key in ("old_testament_front", "appendices")
    for e in EDITION[key]
    if e["source"] == "brenton"
} | set(EDITION["excluded"]["brenton"])


def printed_heading(text):
    return pipeline.marker_lines(text, pipeline.HEADING_MARKERS)


# Selection and order


def test_scripture_unit_counts():
    assert len(IDS) == len(set(IDS)) == 78
    assert len(BRENTON_UNITS) == 51
    assert sum(u["source"] == "kjv" for u in UNITS) == 27


def test_orthodox_old_testament_order():
    assert IDS[: len(ORTHODOX_OLD_TESTAMENT)] == ORTHODOX_OLD_TESTAMENT
    assert IDS[len(ORTHODOX_OLD_TESTAMENT)] == "MAT"


def test_no_separate_units_for_grouped_sources():
    assert not {"2ES", "SUS", "BEL"} & set(IDS)


def test_every_brenton_scripture_source_is_printed_once(archives):
    source_use = pipeline.brenton_source_use()
    assert set(source_use) == set(archives["brenton"]) - BRENTON_NON_SCRIPTURE
    # The combined Ezra-Nehemiah file supplies both 2 Esdras and Nehemias.
    counts = Counter(source_use)
    assert counts == {code: 2 if code == "EZR" else 1 for code in counts}


def selected(key):
    return [(e["source"], source_id(e)) for e in EDITION[key]]


def test_old_testament_front_matter():
    assert selected("old_testament_front") == [
        ("brenton", "XXB"),
        ("brenton", "INT"),
        ("brenton", "OTH"),
        ("brenton", "FRT"),
    ]


def test_new_testament_front_matter():
    assert selected("new_testament_front") == [("kjv", "OTH"), ("kjv", "INT")]


def test_appendices():
    assert selected("appendices") == [
        ("brenton", "XXA"),
        ("brenton", "BAK"),
        ("brenton", "XXC"),
    ]


@pytest.fixture(scope="module")
def ordered_ids():
    return [e["id"] for e in pipeline.ordered_entries()]


def run_of(ordered_ids, *codes):
    first = ordered_ids.index(codes[0])
    return ordered_ids[first : first + len(codes)]


def test_editors_introduction_opens_the_book(ordered_ids):
    assert ordered_ids[0] == "CNC"


def test_old_testament_front_matter_follows_its_divider(ordered_ids):
    codes = ("CNC", "XXF", "XXB", "XXE", "OTH", "XXD", "GEN")
    assert run_of(ordered_ids, *codes) == list(codes)


def test_new_testament_front_matter_follows_its_divider(ordered_ids):
    codes = ("DAG", "XXG", "TDX", "NDX", "MAT")
    assert run_of(ordered_ids, *codes) == list(codes)


def test_appendices_close_the_book(ordered_ids):
    codes = ("REV", "GLO", "XXA", "BAK", "XXC")
    assert run_of(ordered_ids, *codes) == list(codes)
    assert ordered_ids[-1] == "XXC"


# Special content in the pinned sources


def test_kjv_dedication_is_present(archives):
    assert "Greatandmanifoldweretheblessings" in canonical_text(
        archives["kjv"]["OTH"][2]
    )


def test_combined_ezra_nehemiah_source():
    chapters = SOURCES["brenton"]["files"]["EZR"]["chapters"]
    assert list(chapters) == [str(i) for i in range(1, 24)]


def test_greek_additions_are_present():
    inventory = SOURCES["brenton"]["files"]
    assert "151" in inventory["PSA"]["chapters"], "Psalm 151"
    assert "1b" in inventory["ESG"]["chapters"]["1"], "Esther additions"
    assert len(inventory["DAG"]["chapters"]["3"]) > 90, "Daniel 3 additions"


@pytest.mark.parametrize("code", ["MAN", "3MA", "4MA"])
def test_apocryphal_books_are_present(code):
    assert SOURCES["brenton"]["files"][code]["chapters"]


# Titles and headings


@pytest.mark.parametrize("unit", BRENTON_UNITS, ids=lambda u: u["id"])
def test_brenton_title(archives, unit):
    expected = REVISED_TITLES.get(unit["id"]) or source_marker(
        source_usfm(unit, archives), "toc1"
    )
    assert unit["title"] == expected


@pytest.mark.parametrize("unit", UNITS, ids=lambda u: u["id"])
def test_book_name_markers(archives, scripture, unit):
    text = scripture[unit["id"]]
    names = pipeline.resolved_book_names(unit, source_usfm(unit, archives))
    assert source_marker(text, "toc1") == names["title"]
    assert (
        source_marker(text, "h") == source_marker(text, "toc2") == names["short_title"]
    )
    assert source_marker(text, "toc3") == names["abbreviation"]


@pytest.mark.parametrize("unit", UNITS, ids=lambda u: u["id"])
def test_printed_titles_have_no_period(scripture, unit):
    markers = ("h", "toc1", *pipeline.HEADING_MARKERS)
    lines = pipeline.marker_lines(scripture[unit["id"]], markers)
    assert not [value for _, value in lines if "." in value]


@pytest.mark.parametrize("unit", UNITS, ids=lambda u: u["id"])
def test_heading_follows_the_manifest(archives, scripture, unit):
    names = pipeline.resolved_book_names(unit, source_usfm(unit, archives))
    assert printed_heading(scripture[unit["id"]]) == pipeline.heading_lines(unit, names)


@pytest.mark.parametrize("code", PAULINE_EPISTLES)
def test_pauline_titles_name_saint_paul(archives, scripture, code):
    unit = scripture_unit(code)
    original = source_usfm(unit, archives)
    assert unit["title"] == re.sub(
        r"\bPaul(?: the Apostle)?\b", "Saint Paul", source_marker(original, "toc1")
    )
    assert source_marker(scripture[code], "mt2") == re.sub(
        r"\bPAUL(?: THE APOSTLE)?\b", "SAINT PAUL", source_marker(original, "mt2")
    )


@pytest.mark.parametrize("code", sorted(CATHOLIC_EPISTLES))
def test_catholic_epistle_titles(scripture, code):
    ordinal, person = CATHOLIC_EPISTLES[code]
    assert scripture_unit(code)["title"] == (
        f"The {ordinal}Catholic Epistle of Saint {person}"
    )
    assert printed_heading(scripture[code]) == [
        ("mt2", f"THE {ordinal.upper()}CATHOLIC EPISTLE OF"),
        ("mt1", f"SAINT {person.upper()}"),
    ]


@pytest.mark.parametrize(
    "code, marker, expected",
    [
        (code, marker, expected)
        for code, markers in SAINT_HEADINGS.items()
        for marker, expected in markers.items()
    ],
)
def test_saint_headings(scripture, code, marker, expected):
    assert source_marker(scripture[code], marker) == expected


@pytest.mark.parametrize("unit", UNITS, ids=lambda u: u["id"])
def test_book_names_xml(archives, book_names, unit):
    assert book_names[unit["id"]] == pipeline.resolved_book_names(
        unit, source_usfm(unit, archives)
    )


@pytest.mark.parametrize(
    "entry",
    [e for e in pipeline.ordered_entries() if "title" in e],
    ids=lambda e: e["id"],
)
def test_book_names_xml_follows_the_manifest(book_names, entry):
    names = book_names[entry["id"]]
    for field in pipeline.BOOK_NAME_MARKERS:
        if field in entry:
            assert names[field] == entry[field]


def test_jeremias_table_titles(book_names):
    table = next(e for e in EDITION["appendices"] if e["id"] == "XXA")
    title = "Table of Chapters and Verses in " + book_names["JER"]["short_title"]
    assert table["title"] == table["short_title"] == title
    assert book_names["XXA"]["title"] == book_names["XXA"]["short_title"] == title


def test_esdras_and_nehemias_never_share_names(book_names):
    esdras = set(book_names["EZR"].values())
    nehemias = set(book_names["NEH"].values())
    assert esdras.isdisjoint(nehemias)
    assert "Ezra and Nehemiah" not in esdras | nehemias


# The edition's own front matter


def test_no_apocrypha_divider():
    assert "THE APOCRYPHA" not in Path("config/front.sfm").read_text(encoding="utf-8")


def test_editors_introduction_is_a_unit():
    # A unit, so that it follows the contents page and is listed in it.
    text = Path("config/introduction.sfm").read_text(encoding="utf-8")
    assert "\\periph" not in text


@pytest.mark.parametrize("path", sorted(map(str, Path("config").glob("*.sfm"))))
def test_edition_text_is_typed_with_curly_quotes(path):
    # Preparation curls the sources' quotes; the edition's own text is typed curly.
    text = re.sub(r'\|\w+="[^"\n]*"', "", Path(path).read_text(encoding="utf-8"))
    assert not re.findall(r"[^\n]*['\"`][^\n]*", text)
