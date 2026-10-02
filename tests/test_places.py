"""Placing the verses: the table and the words, heard together.

On verses made for the purpose; test_versification.py checks the places of
the edition's own."""

from __future__ import annotations

from typing import Any, cast

import pytest
from conftest import changed

import bible.policy
from bible import alignment, places, usj
from bible.checks import CheckFailed
from bible.policy_schema import Run
from bible.references import Verse, parse_verse

OURS = (
    "\\id GEN\n\\c 1\n\\p\n"
    "\\v 1 The ark rested upon the mountains of Ararat.\n"
    "\\v 2 The raven went forth from the window.\n"
    "\\v 3 The dove found no rest for her foot.\n"
    "\\v 4 Noe builded an altar of clean beasts.\n"
    "\\v 5 Abimelech king of Gerara.\n"
    "\\v 6 The bow shall be seen in the cloud.\n"
    "\\v 6a The addition of the Greek.\n"
)
THEIRS = (
    "\\id GEN\n\\c 1\n\\p\n"
    "\\v 1 And the ark rested upon the mountains of Ararat.\n"
    "\\v 2 And the dove found no rest for the sole of her foot.\n"
    "\\v 3 And he sent forth a raven from the window.\n"
    "\\v 4 And Noah builded an altar, and took of every clean beast.\n"
    "\\v 5 Ahimelek of Philistia.\n"
    "\\v 6 The bow shall be seen in the cloud.\n"
    "\\v 7 While the earth remaineth, seedtime and harvest.\n"
)


class Texts(places.Texts):
    def __init__(self, ours: str, theirs: str) -> None:
        self.books = {"GEN": "GEN"}
        self.edition = alignment.Verses({"GEN": usj.parse(ours)})
        self.kjv = alignment.Verses({"GEN": usj.parse(theirs)}, titled=True)
        self.weight = alignment.weights(self.edition.words, self.kjv.words)


def same(texts: places.Texts) -> dict[Verse, tuple[Verse, ...] | None]:
    """The table's account of a Bible it says nothing of."""
    return {
        verse: () if verse.letter else (Verse("GEN", verse.chapter, verse.number),)
        for verse in texts.edition.words
    }


def blocks(texts: places.Texts, table: places.Table) -> list[tuple[str, str, str]]:
    return [
        (" ".join(map(str, ours)), " ".join(map(str, theirs)), by)
        for ours, theirs, by in places.aligned(texts, "GEN", table)
    ]


def test_the_words_move_a_verse_and_its_place_keeps_one() -> None:
    texts = Texts(OURS, THEIRS)
    table = same(texts)
    # Where the table's rows disagree, it says nothing.
    table[parse_verse("GEN 1:5")] = None
    assert blocks(texts, table) == [
        ("GEN 1:1", "GEN 1:1", "words"),
        ("GEN 1:2", "GEN 1:3", "words"),
        ("GEN 1:3", "GEN 1:2", "words"),
        ("GEN 1:4", "GEN 1:4", "words"),
        # Names spelt otherwise share no words.
        ("GEN 1:5", "GEN 1:5", "place"),
        ("GEN 1:6", "GEN 1:6", "words"),
        ("GEN 1:6a", "", "words"),
        ("", "GEN 1:7", "words"),
    ]


def test_a_verse_left_over_joins_the_pair_that_has_its_words() -> None:
    ours = OURS.replace(
        "\\v 4 Noe builded an altar of clean beasts.\n",
        "\\v 4 Noe builded an altar\n\\v 4a of clean beasts.\n",
    )
    texts = Texts(ours, THEIRS)
    table = same(texts)
    assert ("GEN 1:4 GEN 1:4a", "GEN 1:4", "words") in blocks(texts, table)


def test_the_words_must_outvote_the_table() -> None:
    texts = Texts(OURS, THEIRS)
    raven, dove = parse_verse("GEN 1:2"), parse_verse("GEN 1:3")
    table = same(texts)
    assert places.outvotes(texts, table, raven, dove)
    assert places.outvotes(texts, table, raven, raven)
    # One that shares a word with its neighbour doesn't go to it for that.
    assert not places.outvotes(texts, table, parse_verse("GEN 1:1"), dove)


def test_the_words_may_not_leave_a_verse_without_a_place() -> None:
    texts = Texts(OURS, THEIRS)
    one, two, three = (parse_verse(f"GEN 1:{n}") for n in (1, 2, 3))
    taken: list[places.WitnessBlock] = [
        {"edition": [one], "words": [two], "table": [one], "by": "words"},
        {"edition": [two], "words": [], "table": [two], "by": "words"},
    ]
    settled = places.settle(texts, taken)
    assert [(b["words"], b["by"]) for b in settled] == [
        ([one], "table"),
        ([two], "table"),
    ]
    # Unless a verse that stands in the way has no other place to go.
    held: list[places.WitnessBlock] = [
        {"edition": [one], "words": [two], "table": None, "by": "words"},
        {"edition": [two], "words": [], "table": [two], "by": "words"},
        {"edition": [three], "words": [three], "table": [three], "by": "words"},
    ]
    assert [b["words"] for b in places.settle(texts, held)] == [[two], [], [three]]


def test_runs_are_written_verse_for_verse_or_whole() -> None:
    verses = [parse_verse(f"GEN 1:{n}") for n in range(1, 8)]
    lettered = parse_verse("GEN 1:6a")
    entries = [
        ([verses[0]], [verses[1]], "words", None),
        ([verses[1]], [verses[2]], "words", None),
        ([verses[2]], [verses[3]], "table", None),
        ([verses[3], verses[4]], [verses[4]], "words", None),
        ([lettered], [verses[6]], "reading", "x"),
        ([verses[6]], [], "words", None),
    ]
    assert places._runs(entries) == [
        {"edition": "GEN 1:1-2", "kjv": "GEN 1:2-3", "by": "words"},
        {"edition": "GEN 1:3", "kjv": "GEN 1:4", "by": "table"},
        {"edition": "GEN 1:4-5", "kjv": "GEN 1:5", "by": "words"},
        {"edition": "GEN 1:6a", "kjv": "GEN 1:7", "by": "reading", "why": "x"},
        {"edition": "GEN 1:7", "kjv": None, "by": "words"},
    ]


def test_what_has_been_read_stands() -> None:
    # Whatever the witnesses give for its verses, and with the overlaps it
    # declares; what is left of the King James Bible's verses is missing.
    reading: Run = {
        "edition": "GEN 1:2-3",
        "kjv": "GEN 1:2-3",
        "why": "x",
        "pairs": {"GEN 1:2": "GEN 1:2-3", "GEN 1:3": "GEN 1:3"},
    }
    raven, dove = parse_verse("GEN 1:2"), parse_verse("GEN 1:3")
    proposed = [([raven], [dove], "words", None), ([dove], [raven], "words", None)]
    assert places.decided(Texts(OURS, THEIRS), "GEN", proposed, [reading]) == [
        {**reading, "by": "reading"},
        {"edition": None, "kjv": "GEN 1:7"},
    ]


@pytest.mark.parametrize(
    "reading, refusal",
    [
        ({"edition": "GEN 1:2", "kjv": "GEN 1:3"}, "missing or unknown fields"),
        ({"edition": "GEN 1:2", "kjv": "GEN 1:3", "why": ""}, "without its reason"),
        ({"edition": "GEN 1:9", "kjv": "GEN 1:3", "why": "x"}, "its Bible lacks"),
        ({"edition": "GEN 1:2", "kjv": "GEN 1:9", "why": "x"}, "its Bible lacks"),
    ],
)
def test_a_reading_must_fit_both_bibles(reading: dict[str, Any], refusal: str) -> None:
    with pytest.raises(CheckFailed, match=refusal):
        places.written(Texts(OURS, THEIRS), "GEN", [], [cast(Run, reading)])


def test_a_reading_must_change_what_the_witnesses_give() -> None:
    raven, dove = parse_verse("GEN 1:2"), parse_verse("GEN 1:3")
    proposed: list[places.Placement] = [
        ([raven], [dove], "words", None),
        ([dove], [raven], "words", None),
    ]
    given: Run = {"edition": "GEN 1:2", "kjv": "GEN 1:3", "why": "x"}
    with pytest.raises(CheckFailed, match="changes nothing: GEN 1:2 = GEN 1:3"):
        places.decided(Texts(OURS, THEIRS), "GEN", proposed, [given])
    # Nor may it only part a run in two: each verse stands where it stood.
    ark = parse_verse("GEN 1:1")
    run: list[places.Placement] = [
        ([ark], [raven], "table", None),
        ([raven], [dove], "table", None),
    ]
    part: Run = {"edition": "GEN 1:1", "kjv": "GEN 1:2", "why": "x"}
    with pytest.raises(CheckFailed, match="changes nothing: GEN 1:1 = GEN 1:2"):
        places.decided(Texts(OURS, THEIRS), "GEN", run, [part])


def test_a_reading_is_of_a_book_of_the_old_testament(
    policy: bible.policy.Policy,
) -> None:
    stray = changed(
        policy,
        "versification",
        lambda data: data["readings"].update(
            TOB=[{"edition": "TOB 1:1", "kjv": "TOB 1:2", "why": "x"}]
        ),
    )
    with pytest.raises(CheckFailed, match=r"outside the Old Testament: \['TOB'\]"):
        places.placed({}, {}, policy=stray)
