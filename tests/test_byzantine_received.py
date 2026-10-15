"""Whether the apparatuses establish a Received Text reading, and the witness
the New Testament's notes name: the printed RP2026 apparatus as read, every
row that gives the Received Text a reading standing at a unit, the Greek
the rows quote found in Scrivener's text, and TR printed only where the
apparatuses establish it."""

from __future__ import annotations

import copy
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import cast

import pytest

import bible.pipeline
from bible.byzantine import decisions, greek, received, stages
from bible.byzantine.inventories import reading_words
from bible.byzantine.rows import BoydNote, Disposition, Placement, Unit, Unmatched
from bible.byzantine.stages import Context
from bible.byzantine.units import PRINTED_APPARATUS
from bible.checks import CheckFailed
from bible.sources import Content
from bible.usj import Node


def rows_of(byzantine: Context) -> list[tuple[str, BoydNote]]:
    return [
        *(("tcgnt", n) for n in byzantine["tcgnt"]),
        *((PRINTED_APPARATUS, n) for n in byzantine["apparatus"]),
    ]


# The printed apparatus as read.


def test_the_printed_apparatus_gives_the_received_text_its_readings(
    byzantine: Context,
) -> None:
    rows = byzantine["apparatus"]
    assert Counter("SCR" if "SCR" in r["tr"][0]["sigla"] else "TR" for r in rows) == {
        "TR": 1735,
        "SCR": 150,
    }
    by_ref = {r["target_ref"]: r for r in rows}
    assert by_ref["EPH 1:7"]["rp"] == "τον πλουτον"
    assert by_ref["EPH 1:7"]["tr"] == [{"reading": "το πλουτον", "sigla": ["SCR"]}]
    assert by_ref["EPH 1:7"]["page"] == 551
    assert by_ref["LUK 1:35"]["tr"] == [
        {"reading": "γεννωμενον εκ σου", "sigla": ["SCR"]}
    ]
    # A verse the text omits is quoted whole, with its numerals as Boyd's.
    assert by_ref["ACT 24:7"]["rp"] == "---"
    assert " 7 " in by_ref["ACT 24:7"]["tr"][0]["reading"]
    # A word broken at a line end is put together.
    assert by_ref["MAT 8:25"]["tr"][0]["reading"] == "οι μαθηται αυτου"
    # Every entry has its caller's place in its verse, but the one whose
    # caller stands where RP2026 prints the doxology's number alone.
    unplaced = [r["target_ref"] for r in rows if r["position"] is None]
    assert unplaced == ["ROM 16:25"]
    for row in rows:
        position = row["position"]
        if position is not None:
            assert position["words"] == byzantine["printed"][position["ref"]]["Greek"]
            assert 0 <= position["offset"] <= len(position["words"])


def page(nodes: Iterable[tuple[str, str]]) -> str:
    return "".join(
        f'<text top="0" left="0" width="1" height="1" font="{font}">{text}</text>'
        for font, text in nodes
    )


def test_an_entry_opens_with_its_letter_and_reference_and_reads_to_the_next() -> None:
    fonts = {
        "3": "RPTimesNewRoman",
        "4": "RPTimesNewRomanBold",
        "9": "RPTimesNewRomanItalic",
        "11": "RPTimesNewRoman",
        "23": "RPTimesNewRomanBold",
        "27": "Gentium",
    }
    specs = "".join(
        f'<fontspec id="{i}" size="12" family="ABCDEF+{f}" color="#000000"/>'
        for i, f in fonts.items()
    )
    body = page(
        [
            ("23", "ΚΑΤΑ ΜΑΤΘΑΙΟΝ"),
            ("11", "a"),
            ("4", "1:6"),
            ("3", "σολομωνα ¦"),
            ("27", "TR"),
            ("3", "σολο-"),
            ("3", "μωντα"),
            ("11", "b"),
            ("4", "1:7"),
            ("3", "ασα ¦"),
            ("27", "CT"),
            ("3", "ασαφ"),
            ("11", "c"),
            ("4", "1:8"),
            ("3", "και ¦"),
            ("27", "RP"),
            ("11", "mg"),
            ("27", "SCR"),
            ("9", "om."),
            # The manuscript apparatus names no edition.
            ("11", "a"),
            ("4", "1:6"),
            ("3", "σολομωνα C D ¦ σολομωντα E K"),
        ]
    )
    xml = f'<pdf2xml>{specs}<page number="2">{body}</page></pdf2xml>'
    verses: Mapping[str, greek.PrintedVerse] = {
        "MAT 1:6": {
            "Greek": ["ton", "solomwna"],
            "accented": [],
            "page": 2,
            "callers": {"2 a": 1},
        },
    }
    rows = greek.apparatus(Content({"x.xml": xml.encode()}) / "x.xml", verses)
    assert [(r["target_ref"], r["rp"], r["tr"]) for r in rows] == [
        ("MAT 1:6", "σολομωνα", [{"reading": "σολομωντα", "sigla": ["TR"]}]),
        ("MAT 1:8", "και", [{"reading": "---", "sigla": ["RPmg", "SCR"]}]),
    ]
    assert rows[0]["position"] == {
        "ref": "MAT 1:6",
        "words": ["ton", "solomwna"],
        "offset": 1,
    }
    assert rows[1]["position"] is None


# Every row that gives the Received Text a reading stands at a unit.


def test_every_row_giving_the_received_text_a_reading_stands_at_a_unit(
    byzantine: Context, declared: bible.policy.Policy
) -> None:
    attached = {
        (a["inventory"], a["entry"])
        for u in byzantine["units"]
        for a in u["inventories"]
    }
    placed_nowhere = {
        tuple(key.split(" ")[:1]) + (int(key.split(" ")[1]),)
        for key, p in declared.byzantine_placements["placements"].items()
        if key.split()[0] in {"tcgnt", PRINTED_APPARATUS} and p["unit"] is None
    }
    assert placed_nowhere == {("tcgnt", 937), ("tcgnt", 1614)}
    for inventory, row in rows_of(byzantine):
        key = (inventory, row["entry"])
        assert key in attached or key in placed_nowhere, key
    assert {r["inventory"] for r in byzantine["unmatched"]} == {"collation"}


def test_a_row_nothing_places_stays_unmatched(byzantine: Context) -> None:
    row = byzantine["tcgnt"][0]
    units, remaining, errors = decisions.place_inventories(
        byzantine["units"], [{"inventory": "tcgnt", **row, "reason": "test"}], []
    )
    assert errors == [] and len(remaining) == 1
    assert units == byzantine["units"]


def test_the_greek_stage_stops_on_a_row_at_no_unit_or_a_stale_placement(
    byzantine: Context,
) -> None:
    def staged(placements: list[Placement]) -> None:
        stages.stage_greek(
            {
                "source_inputs": byzantine["source_inputs"],
                "decisions": byzantine["decisions"],
                "placements": placements,
            }
        )

    declared = byzantine["placements"]
    held = [p for p in declared if (p["witness"], p["entry"]) != ("tcgnt", 1627)]
    with pytest.raises(CheckFailed, match=r"at no unit: \['tcgnt 1627 at REV 12:8'\]"):
        staged(held)
    # MAT 3:8's row the code places itself.
    stale: Placement = {
        "witness": "tcgnt",
        "entry": next(
            n["entry"] for n in byzantine["tcgnt"] if n["target_ref"] == "MAT 3:8"
        ),
        "ref": "MAT 3:8",
        "unit": {"tr": "karpous acious", "rp": "karpon acion"},
        "why": "test",
    }
    with pytest.raises(CheckFailed, match="the code places the row"):
        staged([*declared, stale])


def test_a_placement_attaches_a_row_by_hand_and_goes_stale_when_the_code_does() -> None:
    unit: Unit = {
        "id": "MAT 1:1#1",
        "ref": "MAT 1:1",
        "tr": ["dabid"],
        "rp": ["dauid"],
        "inventories": [],
        "found_in": [],
        "hf": "unknown",
        "rp_alternate": False,
        "patriarchal": False,
    }
    row: Unmatched = {
        "inventory": "tcgnt",
        "entry": 5,
        "target_ref": "MAT 1:1",
        "hf": "RP",
        "rp_alternate": True,
        "patriarchal": False,
    }
    placement: Placement = {
        "witness": "tcgnt",
        "entry": 5,
        "ref": "MAT 1:1",
        "unit": {"tr": "dabid", "rp": "dauid"},
        "why": "test",
    }
    units, remaining, errors = decisions.place_inventories([unit], [row], [placement])
    assert (remaining, errors) == ([], [])
    assert units[0]["inventories"] == [
        {
            "inventory": "tcgnt",
            "entry": 5,
            "scope": "constituent",
            "method": "hand",
            "hf": "RP",
        }
    ]
    assert units[0]["found_in"] == ["tcgnt"]
    # Boyd's note gives its sides wherever it is placed, as the code's are.
    assert (units[0]["hf"], units[0]["rp_alternate"]) == ("RP", True)
    _, _, errors = decisions.place_inventories(
        [unit], [row], [{**placement, "unit": [{"tr": "dabid", "rp": "dauid"}] * 2}]
    )
    assert errors == ["placement tcgnt 5: duplicate unit"]
    _, _, errors = decisions.place_inventories([unit], [], [placement])
    assert errors == [
        "placement tcgnt 5: the code places the row, or there is no such row"
    ]
    _, _, errors = decisions.place_inventories(
        [unit], [row], [{**placement, "unit": {"ref": "MAT 1:1", "tr": "x", "rp": "y"}}]
    )
    assert "names 0 units" in errors[0]


# The Greek the rows give the Received Text is Scrivener's.


def movable(word: str) -> str:
    """A word without a final nu that may stand or not, which no English shows."""
    return word[:-1] if len(word) > 3 and word[-2:] in ("in", "en") else word


def quoted(reading: str) -> list[list[str]]:
    """A reading's words, in its pieces between ellipses, without the verse
    numerals it carries."""
    reading = re.sub(r"(?<!\S)\d+(?!\S)", "", reading)
    return [[movable(w) for w in reading_words(p) or []] for p in reading.split("…")]


def span(
    text: Mapping[str, list[str]], book: str, address: str, wide: bool
) -> list[str]:
    """The words of the verses an apparatus row is about ("1:10–11"), and with
    wide those either side, since the texts divide some verses otherwise."""
    chapter, verses = address.split(":")
    numbers = [int(n) for n in re.split("[–,-]", verses)]
    first, last = min(numbers), max(numbers)
    if wide:
        first, last = first - 1, last + 1
    return [
        movable(w)
        for v in range(first, last + 1)
        for w in text.get(f"{book} {chapter}:{v}", [])
    ]


def count(hay: list[str], parts: list[list[str]], letters: bool) -> int:
    """How often the parts stand in order, as words, or as letters (the texts
    divide some words otherwise)."""

    def times(stream: str | list[str], pieces: list[str] | list[list[str]]) -> int:
        def find(at: int, piece: str | list[str]) -> int:
            if isinstance(stream, str):
                return stream.find(cast(str, piece), at)
            n = len(piece)
            return next(
                (
                    i
                    for i in range(at, len(stream) - n + 1)
                    if stream[i : i + n] == piece
                ),
                -1,
            )

        total, at = 0, find(0, pieces[0])
        while at >= 0:
            rest, ok = at + len(pieces[0]), True
            for piece in pieces[1:]:
                rest = find(rest, piece)
                if rest < 0:
                    ok = False
                    break
                rest += len(piece)
            total += ok
            at = find(at + 1, pieces[0])
        return total

    parts = [p for p in parts if p]
    if not parts:
        return 0
    if letters:
        return times("".join(hay), ["".join(p) for p in parts])
    return times(hay, parts)


# Readings the comparison cannot see, each for its reason.
UNSEEN = {
    # A transposition, which each apparatus quotes as an omission at one place.
    ("tcgnt", "JHN 1:43"),
    (PRINTED_APPARATUS, "JHN 1:43"),
    (PRINTED_APPARATUS, "2CO 7:13"),
    # RP2026's Appendix A removed the words Boyd's RP2018 has and Scrivener lacks.
    ("tcgnt", "REV 11:16"),
}


def test_every_reading_the_apparatuses_give_the_received_text_is_scriveners(
    byzantine: Context,
) -> None:
    """The Greek each row of Boyd's apparatus and the printed RP2026's gives
    Scrivener stands in Scrivener's text at its verses, and an omission has
    the main words fewer times there than RP2026."""
    tr, rp = byzantine["tr"], byzantine["rp"]
    missing = set()
    for inventory, row in rows_of(byzantine):
        book = row["target_ref"].split()[0]
        for reading in row["tr"]:
            text, address = reading["reading"], row["fr"]
            # A reading at another place names it: "[16:27] om." is Scrivener's
            # reading at 16:27 of what RP prints here.
            elsewhere = re.match(r"\[(\d+:[\d–]+)\]\s*(.*)", text)
            if elsewhere:
                address, text = elsewhere[1], elsewhere[2]
            if "{" in text or elsewhere and not text.strip():
                continue  # where a passage stands (units.supplementary_units)
            if text.strip("- ") in ("", "om."):
                main = quoted(re.sub(r"\(.*?\)", "", row["rp"]))
                ok = any(
                    count(span(tr, book, address, wide), main, letters)
                    < count(span(rp, book, row["fr"], wide), main, letters)
                    for wide in (False, True)
                    for letters in (False, True)
                )
            else:
                ok = count(span(tr, book, address, True), quoted(text), True) > 0
            if not ok:
                missing.add((inventory, row["target_ref"]))
    assert missing == UNSEEN


def test_ephesians_1_7_is_scriveners_neuter_article(byzantine: Context) -> None:
    assert byzantine["tr"]["EPH 1:7"][-5:-3] == ["to", "plouton"]
    (unit,) = [u for u in byzantine["units"] if u["ref"] == "EPH 1:7"]
    assert (unit["tr"], unit["rp"]) == (["to"], ["ton"])
    assert {a["inventory"] for a in unit["inventories"]} == {"tcgnt", PRINTED_APPARATUS}
    assert received.status(unit, rows(byzantine)) == "SCR"
    accented = byzantine["tr_accented"]["EPH 1:7"]
    assert "τὸ" in accented and "τὸν" not in accented


def rows(byzantine: Context) -> received.Rows:
    return received.rows(byzantine["tcgnt"], byzantine["apparatus"])


def test_a_scrivener_correction_must_fit_its_verse_and_be_evidenced(
    byzantine: Context,
) -> None:
    text = {"EPH 1:7": ["kata", "ton", "plouton"]}
    fix = {"EPH 1:7": {"from": "τὸν πλοῦτον", "to": "τὸ πλοῦτον", "why": "test"}}
    assert greek.corrected(text, fix) == {"EPH 1:7": ["kata", "to", "plouton"]}
    with pytest.raises(CheckFailed, match="does not fit its verse"):
        greek.corrected({"EPH 1:7": ["kata", "to", "plouton"]}, fix)
    accented = greek.corrected(
        {"EPH 1:7": ["κατὰ", "τὸν", "πλοῦτον"]}, fix, accented=True
    )
    assert accented == {"EPH 1:7": ["κατὰ", "τὸ", "πλοῦτον"]}
    stages.evidenced(
        fix, byzantine["units"], byzantine["tcgnt"], byzantine["apparatus"]
    )
    # Without the printed RP2026's evidence, the correction stops the build.
    without: list[Unit] = [
        {
            **u,
            "inventories": [
                a for a in u["inventories"] if a["inventory"] != PRINTED_APPARATUS
            ],
        }
        for u in byzantine["units"]
    ]
    with pytest.raises(CheckFailed, match="apparatuses do not give: EPH 1:7"):
        stages.evidenced(fix, without, byzantine["tcgnt"], byzantine["apparatus"])


# The witness a note names.


def unit_with(*entries: tuple[str, int]) -> Unit:
    return {
        "id": "MAT 1:1#1",
        "inventories": [{"inventory": i, "entry": e} for i, e in entries],
    }


def note(key: str) -> Node:
    return {"type": "note", "x-key": key}


def note_row(entry: int, *sigla: str) -> BoydNote:
    return {"entry": entry, "tr": [{"reading": "x", "sigla": list(sigla)}]}


def test_a_unit_is_established_as_the_received_texts_where_no_row_says_scrivener_alone() -> (
    None
):
    found = received.rows(
        [note_row(1, "TR"), note_row(2, "SCR", "WH")], [note_row(1, "PT", "TR")]
    )
    assert (
        received.status(unit_with(("tcgnt", 1), (PRINTED_APPARATUS, 1)), found) == "TR"
    )
    assert received.status(unit_with(("tcgnt", 2)), found) == "SCR"
    assert received.status(unit_with(("tcgnt", 1), ("tcgnt", 2)), found) == "disputed"
    assert received.status(unit_with(("collation", 1)), found) is None


def test_a_note_names_the_received_text_only_where_every_unit_it_is_about_is_established() -> (
    None
):
    found = received.rows([note_row(1, "TR"), note_row(2, "SCR")], [])
    units: list[Unit] = [
        {"id": "A", "inventories": [{"inventory": "tcgnt", "entry": 1}]},
        {"id": "B", "inventories": [{"inventory": "tcgnt", "entry": 1}]},
        {"id": "C", "inventories": [{"inventory": "tcgnt", "entry": 2}]},
    ]
    rows: list[Disposition] = [
        {"unit": "A", "edits": [{"note": note("A TR#1")}]},
        # B's row is carried out by A's.
        {"unit": "B", "covered_by": "A"},
        {"unit": "C", "edits": [{"note": note("C TR#1")}], "note": note("C TR")},
        # A note combined from two rows names the witness of both.
        {"unit": "A", "edits": [{"note": note("AC TR#1")}]},
        {"unit": "C", "edits": [{"note": note("AC TR#1")}]},
        # A correction of shared Greek is keyed by its verse.
        {"unit": "MAT 1:1", "edits": [{"note": note("MAT 1:1 rendering#1")}]},
    ]
    assert received.labels(rows, units, found) == {
        "A TR#1": received.RECEIVED,
        "C TR#1": received.KING_JAMES,
        "C TR": received.KING_JAMES,
        "AC TR#1": received.KING_JAMES,
        "MAT 1:1 rendering#1": received.KING_JAMES,
    }


def test_rows_that_disagree_do_not_establish_the_received_text(
    byzantine: Context,
) -> None:
    (unit,) = [u for u in byzantine["units"] if u["id"] == "LUK 17:36#1"]
    found = rows(byzantine)
    assert received.status(unit, found) == "SCR"
    # Were Boyd to give the verse to TR, the printed RP2026 would still give
    # it to Scrivener alone.
    flipped = dict(found)
    for attachment in unit["inventories"]:
        key = (attachment["inventory"], attachment["entry"])
        if attachment["inventory"] == "tcgnt" and key in found:
            row = copy.deepcopy(found[key])
            for reading in row["tr"]:
                reading["sigla"] = ["TR" if s == "SCR" else s for s in reading["sigla"]]
            flipped[key] = row
    assert received.status(unit, flipped) == "disputed"


def printed(edition: bible.pipeline.Edition) -> dict[str, str]:
    return {
        row["key"]: row["note"]
        for code in bible.byzantine.BOOKS
        for row in edition.notes.get(code, [])
        if row["key"] and re.search(r" TR(#\d+)?$", row["key"])
    }


def test_the_notes_name_the_witness_the_apparatuses_establish(
    byzantine: Context, edition: bible.pipeline.Edition
) -> None:
    notes = printed(edition)
    witnesses = {
        key.removesuffix("#1"): term
        for key, term in byzantine["note_witnesses"].items()
        if " TR" in key
    }
    labels: Counter[str] = Counter()
    for key, text in notes.items():
        label = text.split(" ", 1)[0]
        assert (
            label
            == {received.RECEIVED: "TR", received.KING_JAMES: "KJV"}[witnesses[key]]
        ), key
        labels[label] += 1
    assert labels == {"TR": 756, "KJV": 95}


@pytest.mark.parametrize(
    ("key", "note"),
    [
        ("MAT 3:8#1 TR", "TR _fruits_"),
        ("ACT 8:36 TR", "TR adds verse 37"),
        ("ROM 14:24 TR", "TR has this passage at 16:25–27"),
        ("LUK 1:35#1 TR", "KJV adds _of thee_"),
        ("MRK 5:38#1 TR", "KJV _and them_"),
        ("MAT 23:13 TR", "KJV has this passage at 23:14"),
        ("LUK 17:35 TR", "KJV adds verse 36"),
    ],
)
def test_a_note_names_its_witness(
    edition: bible.pipeline.Edition, key: str, note: str
) -> None:
    assert printed(edition)[key].startswith(note)
