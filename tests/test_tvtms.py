"""STEPBible's table, read against a Bible's verses."""

from __future__ import annotations

import pytest

from bible import tvtms, usj
from bible.tvtms import Bible, Row

GREEK = (
    "\\id JOL\n\\c 2\n\\p\n\\v 26 And ye shall eat.\n\\v 27 And ye shall know.\n"
    "\\c 3\n\\p\n\\v 1 And it shall come to pass afterward that I will pour out.\n"
    "\\v 2 And on my servants.\n\\v 2a And on my handmaids in those days.\n"
    "\\c 4\n\\p\n\\v 1 For, behold, in those days.\n"
)


@pytest.fixture
def bible() -> Bible:
    return Bible({"JOL": usj.parse(GREEK)})


def test_the_table_is_read_whole() -> None:
    found, unread = tvtms.rows()
    assert len(found) == 22860
    # Lists of scattered verses, as "9:10,15,23,24,25", name no run to read.
    assert len(unread) == 14
    assert {row.action.rstrip("*") for row in found} >= {
        "Keep verse",
        "Renumber verse",
    }


@pytest.mark.parametrize(
    "written,verses",
    [
        ("Gen.31:55", [("GEN", "31", 55, "")]),
        ("Psa.50:Title", [("PSA", "50", 0, "")]),
        ("1Ki.2:35!a", [("1KI", "2", 35, "a")]),
        ("Jol.2:28-29", [("JOL", "2", 28, ""), ("JOL", "2", 29, "")]),
        ("Gen.5:32; 6:1", [("GEN", "5", 32, ""), ("GEN", "6", 1, "")]),
        ("Gen.2:25-3:1", [("GEN", "2", 25, ""), ("GEN", "3", 1, "")]),
        ("Est.A:3", [("EST", "A", 3, "")]),
    ],
)
def test_a_reference_names_its_verses(
    written: str, verses: list[tuple[int | str, ...]]
) -> None:
    assert tvtms._verses(written) == verses


@pytest.mark.parametrize("written", ["1Ki.9:10,15", "Gen.1", "5:1", ""])
def test_an_unreadable_reference_is_none(written: str) -> None:
    assert tvtms._verses(written) is None


@pytest.mark.parametrize(
    "tests,holds",
    [
        ("Jol.3:1=Exist", True),
        ("Jol.3:5=Exist", False),
        ("Jol.3:5=NotExist & Jol.3:1=Exist", True),
        ("Jol.2:27=Last", True),
        ("Jol.2:32=Last", False),
        ("JOL.2:27=Last", True),
        # The second verse's first lettered part, 3:2a.
        ("Jol.3:2.1=Exist", True),
        ("Jol.3:2.2=Exist", False),
        ("Jol.3:TextBeforeV1=NotExist", True),
        ("Jol.3:1>Jol.3:2", True),
        ("Jol.3:2*4<Jol.3:1", False),
        ("Jol.3:2*2<Jol.3:1+Jol.4:1", True),
        ("", True),
    ],
)
def test_a_test_asks_what_the_bible_has(bible: Bible, tests: str, holds: bool) -> None:
    assert bible.passes(tests) is holds


@pytest.mark.parametrize("tests", ["3:1=Exist", "Jol.3:1=Exist & nonsense"])
def test_an_unreadable_test_is_neither(bible: Bible, tests: str) -> None:
    assert bible.passes(tests) is None


def test_the_account_is_of_the_rows_the_bible_passes(
    bible: Bible, monkeypatch: pytest.MonkeyPatch
) -> None:
    def row(tradition: str, source: str, standard: str, tests: str = "") -> Row:
        source_verses, standard_verses = tvtms._verses(source), tvtms._verses(standard)
        assert source_verses is not None and standard_verses is not None
        verses = tuple(source_verses), tuple(standard_verses)
        return Row(tradition, *verses, "Renumber verse", tests)

    rows = [
        row("Hebrew", "Jol.3:1", "Jol.2:28", "Jol.2:27=Last"),
        row("English", "Jol.3:1", "Jol.3:1", "Jol.2:32=Last"),
        row("Greek", "Jol.3:2!a", "Jol.2:29"),
        row("Greek", "Jol.3:1!b", "Jol.2:28"),
        row("Hebrew", "Hos.2:1", "Hos.1:10"),
    ]
    monkeypatch.setattr(tvtms, "rows", lambda: (rows, []))
    account = tvtms.account(bible, {"JOL": ["JOL"]})
    found = {
        str(verse): [list(map(str, standard)) for standard, _ in answers]
        for verse, answers in account.items()
    }
    assert found == {
        # A part the Bible doesn't letter is part of its verse.
        "JOL 3:1": [["JOL 2:28"], ["JOL 2:28"]],
        "JOL 3:2a": [["JOL 2:29"]],
    }
