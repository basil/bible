"""The Greek unit ledger: reconciliation of the diff with the inventories,
classification, and the supplementary units."""

from __future__ import annotations

import copy
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import pytest

from bible.byzantine import BOOKS, greek
from bible.byzantine.decisions import with_hodges_farstad
from bible.byzantine.greek import (
    PrintedVerse,
    Structure,
    greek_words,
    occurrences,
    page_text,
)
from bible.byzantine.greek import pages as printed_pages
from bible.byzantine.inventories import word_breaks
from bible.byzantine.rows import (
    BoydNote,
    CollationRow,
    Token,
    Unit,
    UnitInventory,
    Unmatched,
)
from bible.byzantine.units import (
    NEUTRAL_CLASSES,
    annotated_class,
    blocks,
    classify,
    collation_ranges,
    ellipsis_pairs,
    keyed_units,
    matching_blocks,
    printed_page,
    quotation_forms,
    reconcile,
    supplementary_units,
)
from bible.sources import Content

# Synthetic texts move and omit no verse.
PLAIN = Structure({}, frozenset())

Tagged = dict[str, list[Token]]


@pytest.fixture(scope="module")
def structure(byzantine: Mapping[str, Any]) -> Structure:
    result = byzantine["structure"]
    assert isinstance(result, Structure)
    return result


@pytest.fixture(scope="module")
def tags(byzantine: Mapping[str, Any]) -> Tagged:
    return {**byzantine["tr_tags"], **byzantine["rp_tags"]}


@pytest.fixture(scope="module")
def splits(byzantine_inputs: Mapping[str, Content]) -> dict[str, list[str]]:
    return word_breaks(byzantine_inputs["tcgnt"] / "095XXC.usx")


def selected(byzantine: Mapping[str, Any], *entries: int) -> list[BoydNote]:
    return [r for r in byzantine["tcgnt"] if r["entry"] in entries]


def attached(
    units: Iterable[Unit], inventory: str = "tcgnt"
) -> list[tuple[Unit, UnitInventory]]:
    return [
        (u, a) for u in units for a in u["inventories"] if a["inventory"] == inventory
    ]


def unmatched_entries(rows: Iterable[Unmatched], inventory: str = "tcgnt") -> list[int]:
    return sorted(r["entry"] for r in rows if r["inventory"] == inventory)


def ranges(tr: list[int], rp: list[int]) -> Unit:
    """A unit by its token ranges alone."""
    return {"tr_range": tr, "rp_range": rp}


# The whole ledger.


def test_class_histogram_and_unmatched_inventory_entries(
    byzantine: Mapping[str, Any], units: list[Unit]
) -> None:
    assert Counter(u["class"] for u in units) == {
        "substitution": 516,
        "inflection": 273,
        "article": 212,
        "omission": 203,
        "spelling": 176,
        "particle": 140,
        "order": 131,
        "name-spelling": 83,
        "addition": 79,
        "pronoun": 62,
        "word-division": 28,
        "movable": 20,
        "structural": 9,
        "accent": 5,
        "prefix": 2,
    }
    assert len(units) == 1939
    assert len({u["id"] for u in units}) == 1939
    assert [(r["inventory"], r["entry"]) for r in byzantine["unmatched"]] == [
        ("collation", 927),
        ("collation", 1571),
        ("collation", 1810),
        ("tcgnt", 739),
        ("tcgnt", 937),
        ("tcgnt", 1035),
        ("tcgnt", 1334),
        ("tcgnt", 1438),
        ("tcgnt", 1450),
        ("tcgnt", 1614),
        ("tcgnt", 1627),
    ]
    assert Counter(u["hf"] for u in units) == {
        "RP": 1723,
        "TR": 127,
        "unknown": 66,
        "other": 23,
    }
    absent = Counter(tuple(sorted(u.get("inventory_absence", {}))) for u in units)
    assert absent == {(): 1889, ("collation", "tcgnt"): 50}
    assert all(
        u["class"] in {"movable", "word-division"}
        or u["ref"] in {"MAT 23:13", "MAT 23:14"}
        for u in units
        if u.get("inventory_absence")
    )
    assert NEUTRAL_CLASSES == {"movable", "word-division", "spelling", "name-spelling"}


def test_collation_bounds_preserve_every_greek_token(
    byzantine: Mapping[str, Any], units: list[Unit], structure: Structure
) -> None:
    tr, rp = byzantine["tr"], byzantine["rp"]
    byref: dict[str, list[Unit]] = {}
    for unit in units:
        if not unit.get("kind"):
            byref.setdefault(unit["ref"], []).append(unit)
    for ref, source in tr.items():
        rebuilt: list[str] = []
        at, other_at = 0, 0
        other = rp[structure.rp_ref(ref)]
        for unit in byref.get(ref, []):
            i, j = unit["tr_range"]
            k, l = unit["rp_range"]
            assert source[at:i] == other[other_at:k], ref
            assert source[i:j] == unit["tr"], ref
            assert other[k:l] == unit["rp"], ref
            rebuilt.extend(source[at:i] + unit["rp"])
            at, other_at = j, l
        rebuilt.extend(source[at:])
        assert rebuilt == other, ref
    omission = next(u for u in units if u["ref"] == "ACT 23:7")
    assert omission["tr"] == ["kai", "twn", "saddoukaiwn"]
    assert omission["rp"] == []
    assert omission["found_in"] == ["collation", "diff", "tcgnt"]


def test_rp2026_philemon_order_is_one_printed_unit(
    byzantine: Mapping[str, Any], units: list[Unit]
) -> None:
    tr, rp = byzantine["tr"], byzantine["rp"]
    rows = blocks({"PHM 1:1": tr["PHM 1:1"]}, {"PHM 1:1": rp["PHM 1:1"]}, PLAIN)
    assert [(r["class"], r["tr"], r["rp"]) for r in rows] == [
        ("order", ["xristou", "ihsou"], ["ihsou", "xristou"])
    ]
    unit = next(u for u in units if u["ref"] == "PHM 1:1")
    assert (unit["hf"], unit["found_in"]) == ("TR", ["diff", "rp2026-appendix-a"])
    assert keyed_units(units, "PHM 1:1", "xristou ihsou", "ihsou xristou") == [unit]
    assert [
        u["id"] for u in keyed_units(units, "MAT 3:8", "karpous acious", "karpon acion")
    ] == ["MAT 3:8#1"]


def test_a_hodges_farstad_side_must_name_its_unit_and_change_it(
    units: list[Unit],
) -> None:
    key = {"ref": "PHM 1:1", "tr": "xristou ihsou", "rp": "ihsou xristou"}
    side: dict[str, Any] = {"unit": key, "side": "TR", "why": "Test."}
    plain: list[Unit] = [
        {**u, "hf": "unknown"} if u["ref"] == "PHM 1:1" else u for u in units
    ]
    [unit] = [
        u
        for u in with_hodges_farstad(plain, {"PHM 1:1#1": side})
        if u["ref"] == "PHM 1:1"
    ]
    assert unit["hf"] == "TR"
    with pytest.raises(ValueError, match="changes nothing"):
        with_hodges_farstad(units, {"PHM 1:1#1": side})
    with pytest.raises(ValueError, match="the unit is PHM 1:1#1"):
        with_hodges_farstad(plain, {"PHM 1:1#2": side})
    with pytest.raises(ValueError, match="names 0 units"):
        with_hodges_farstad(plain, {"PHM 1:1#1": {**side, "unit": {**key, "tr": "x"}}})


# Reconciling Boyd's notes with the diff, on real entries.

# Each group is a regression: the published notes attach where they should,
# with the scope and Hodges-Farstad side their quotations establish.
ATTACHMENTS: list[dict[int, tuple[str, str, str]]] = [
    # Repeated insertions keep their published positions.
    {484: ("LUK 20:31", "constituent", "TR"), 1664: ("REV 13:14", "constituent", "RP")},
    # Context locates the final conjunction of an order unit.
    {1311: ("REV 2:3", "constituent", "RP")},
    # Published context and a preceding article keep unit boundaries.
    {1711: ("REV 15:2", "constituent", "RP"), 1881: ("REV 21:9", "unit", "RP")},
    # Context offsets locate repeated trimmed words.
    {
        272: ("MRK 13:32", "constituent", "RP"),
        583: ("JHN 8:7", "constituent", "other"),
        1750: ("REV 17:4", "constituent", "RP"),
        1762: ("REV 17:10", "constituent", "RP"),
    },
    # Positioned additions inside replacements remain constituents.
    {
        740: ("ACT 9:6", "constituent", "RP"),
        1335: ("REV 2:20", "constituent", "RP"),
        1403: ("REV 5:3", "constituent", "RP"),
        1431: ("REV 5:14", "constituent", "RP"),
        1647: ("REV 13:4", "constituent", "RP"),
        1860: ("REV 20:14", "constituent", "RP"),
        1891: ("REV 21:14", "constituent", "RP"),
    },
    # Shared context locates only its own constituent.
    {
        748: ("ACT 9:28", "constituent", "RP"),
        1036: ("EPH 1:10", "constituent", "RP"),
        1305: ("REV 1:20", "constituent", "RP"),
        1463: ("REV 6:11", "constituent", "RP"),
        1556: ("REV 9:16", "constituent", "RP"),
    },
]


@pytest.mark.parametrize("expected", ATTACHMENTS, ids=lambda e: ",".join(map(str, e)))
def test_published_notes_attach_with_their_scope_and_side(
    byzantine: Mapping[str, Any],
    tags: Tagged,
    structure: Structure,
    expected: dict[int, tuple[str, str, str]],
) -> None:
    tr, rp, coll = byzantine["tr"], byzantine["rp"], byzantine["collation"]
    rows = selected(byzantine, *expected)
    before = copy.deepcopy(rows)
    units, unmatched = reconcile(tr, rp, coll, rows, tags, structure=structure)
    assert unmatched_entries(unmatched) == []
    assert {
        a["entry"]: (u["ref"], a["scope"], u["hf"]) for u, a in attached(units)
    } == expected
    assert rows == before
    original = blocks(tr, rp, structure, coll, tags)
    for unit, _ in attached(units):
        assert any(
            (u["ref"], u["tr_range"], u["rp_range"])
            == (unit["ref"], unit["tr_range"], unit["rp_range"])
            for u in original
        )


def test_a_changed_main_text_position_cannot_donate_a_match(
    byzantine: Mapping[str, Any], tags: Tagged, structure: Structure
) -> None:
    tr, rp, coll = byzantine["tr"], byzantine["rp"], byzantine["collation"]
    changed = copy.deepcopy(selected(byzantine, 484, 1664))
    position = changed[1]["position"]
    assert position is not None
    position["words"][0] = "other"
    assert unmatched_entries(
        reconcile(tr, rp, coll, changed, tags, structure=structure)[1]
    ) == [1664]
    unit = next(
        u
        for u in reconcile(
            tr, rp, coll, selected(byzantine, 1311), tags, structure=structure
        )[0]
        if u["ref"] == "REV 2:3" and u["inventories"][-1]["inventory"] == "tcgnt"
    )
    assert unit["tr"] == "ebastasas kai upomonhn exeis kai".split()
    assert unit["rp"] == "upomonhn exeis kai ebastasas".split()


def test_mixed_and_unnumbered_quotes_stay_unmatched(
    byzantine: Mapping[str, Any], tags: Tagged, structure: Structure
) -> None:
    tr = byzantine["tr"]
    _, unmatched = reconcile(
        tr,
        byzantine["rp"],
        byzantine["collation"],
        selected(byzantine, 739, 1334, 1438, 1450),
        tags,
        structure=structure,
    )
    assert unmatched_entries(unmatched) == [739, 1334, 1438, 1450]
    assert all(
        r["reason"] == "no unique exact content match"
        for r in unmatched
        if r["inventory"] == "tcgnt"
    )
    for ref, following in (("REV 6:1", "REV 6:2"), ("REV 6:7", "REV 6:8")):
        assert tr[ref][-1] == "blepe"
        assert tr[following][:2] == ["kai", "eidon"]


def test_source_discrepancies_stay_unmatched(
    byzantine: Mapping[str, Any], tags: Tagged, structure: Structure
) -> None:
    tr, rp = byzantine["tr"], byzantine["rp"]
    _, unmatched = reconcile(
        tr,
        rp,
        byzantine["collation"],
        selected(byzantine, 1035, 1627),
        tags,
        structure=structure,
    )
    rows = {r["entry"]: r for r in unmatched if r["inventory"] == "tcgnt"}
    assert set(rows) == {1035, 1627}
    assert rows[1627]["rp"] == "ισχυσενε"
    assert tr["EPH 1:7"] == rp["EPH 1:7"]


def test_ellipsis_matches_real_published_order_and_omission_notes(
    byzantine: Mapping[str, Any], tags: Tagged, structure: Structure
) -> None:
    _, unmatched = reconcile(
        byzantine["tr"],
        byzantine["rp"],
        byzantine["collation"],
        selected(byzantine, 383, 660),
        tags,
        structure=structure,
    )
    assert unmatched_entries(unmatched) == []


def test_bare_percentages_and_positioned_repeated_names(units: list[Unit]) -> None:
    names = [u for u in units if u["ref"] == "MAT 1:6" and u["tr"] == ["dabid"]]
    assert len(names) == 2
    assert all(u["hf"] == "TR" for u in names)
    assert [
        {a["entry"] for a in u["inventories"] if a["inventory"] == "tcgnt"}
        for u in names
    ] == [{2}, {3}]


def test_terminal_nu_quotations_use_morphology_without_changing_units(
    units: list[Unit],
) -> None:
    unit = next(u for u in units if u["ref"] == "MRK 2:1")
    assert (unit["class"], unit["tr"], unit["rp"]) == (
        "order",
        ["palin", "eishlqen"],
        ["eishlqen", "palin"],
    )
    note = next(a for a in unit["inventories"] if a["inventory"] == "tcgnt")
    assert note["scope"] == "unit"
    assert (
        note["quotation_normalization"]
        == "closed movable endings and morphology-licensed nu"
    )


def test_appendix_c_locates_constituents_without_rewriting_units(
    byzantine: Mapping[str, Any],
    tags: Tagged,
    splits: dict[str, list[str]],
    structure: Structure,
) -> None:
    tr, rp, coll = byzantine["tr"], byzantine["rp"], byzantine["collation"]
    rows = selected(byzantine, 81, 82, 450, 451, 580, 581, 1432)
    before = copy.deepcopy((rows, splits))
    plain, _ = reconcile(tr, rp, coll, rows, tags, structure=structure)
    units, unmatched = reconcile(tr, rp, coll, rows, tags, splits, structure)
    assert unmatched_entries(unmatched) == []

    def shape(us: Iterable[Unit]) -> list[tuple[Any, ...]]:
        return [(u["tr"], u["rp"], u["tr_range"], u["rp_range"]) for u in us]

    assert shape(units) == shape(plain)
    ninety = next(u for u in units if u["ref"] == "MAT 18:12")
    note = next(a for a in ninety["inventories"] if a["inventory"] == "tcgnt")
    assert (note["scope"], ninety["hf"]) == ("constituent", "RP")
    assert (
        note["word_break_normalization"]
        == "Boyd Appendix C and closed movable quotation forms"
    )
    assert (rows, splits) == before


def test_cross_verse_quotation_checks_the_embedded_verse_number(
    byzantine: Mapping[str, Any], tags: Tagged, structure: Structure
) -> None:
    tr, rp, coll = byzantine["tr"], byzantine["rp"], byzantine["collation"]
    note: BoydNote = copy.deepcopy(
        next(r for r in byzantine["tcgnt"] if r["target_ref"] == "ACT 8:36")
    )
    units, unmatched = reconcile(tr, rp, coll, [note], tags, structure=structure)
    assert unmatched_entries(unmatched) == []
    omission = next(u for u in units if u["ref"] == "ACT 8:37")
    found = next(a for a in omission["inventories"] if a["inventory"] == "tcgnt")
    assert (found["scope"], found["quotation_span"]) == (
        "unit",
        ["ACT 8:36", "ACT 8:37"],
    )
    assert omission["class"] == "structural"
    note["tr"][0]["reading"] = note["tr"][0]["reading"].replace("37", "38")
    assert unmatched_entries(
        reconcile(tr, rp, coll, [note], tags, structure=structure)[1]
    ) == [note["entry"]]


def test_two_collation_entries_for_one_change_make_one_unit(
    byzantine: Mapping[str, Any],
) -> None:
    ref = "MAT 3:8"
    entry: CollationRow = next(
        c for c in byzantine["collation"] if c["target_ref"] == ref
    )
    wider: CollationRow = {
        **entry,
        "tr": ["oun", *entry["tr"]],
        "rp": ["oun", *entry["rp"]],
    }
    rows = blocks(
        {ref: byzantine["tr"][ref]}, {ref: byzantine["rp"][ref]}, PLAIN, [entry, wider]
    )
    assert [(r["tr_range"], r["rp_range"]) for r in rows] == [([2, 4], [2, 4])]


# Synthetic contracts of the locator and the classifier.


def test_locator_contracts_on_synthetic_streams() -> None:
    # A constituent addition needs a position and words the TR side lacks.
    a, b = ["old", "kept"], ["new", "added", "kept"]
    unit = ranges([0, 2], [0, 3])
    assert matching_blocks(a, b, [], ["added"], [unit], 1) == [0]
    assert matching_blocks(a, b, [], ["added"], [unit]) == []
    assert matching_blocks(a, b, [], ["added"], [unit], 0) == []
    assert matching_blocks(a, b, [], ["kept"], [unit], 2) == []
    assert matching_blocks(a, ["new", "added", "added"], [], ["added"], [unit]) == []
    # Context is checked, then stripped; an unchanged word locates nothing.
    tr = {"MAT 3:11": "en pneumati agiw kai puri".split()}
    rp = {"MAT 3:11": "en pneumati agiw".split()}
    units: Sequence[Unit] = blocks(tr, rp, PLAIN)
    assert matching_blocks(
        tr["MAT 3:11"], rp["MAT 3:11"], ["agiw", "kai", "puri"], ["agiw"], units
    ) == [0]
    assert (
        matching_blocks(
            tr["MAT 3:11"], rp["MAT 3:11"], ["pneumati"], ["pneumati"], units
        )
        == []
    )
    # A repeated reading abstains unless the note's position names one.
    a, b = "dabid kai dabid".split(), "dauid kai dauid".split()
    units = blocks({"MAT 1:6": a}, {"MAT 1:6": b}, PLAIN)
    assert matching_blocks(a, b, ["dabid"], ["dauid"], units) == []
    assert matching_blocks(a, b, ["dabid"], ["dauid"], units, 2) == [1]
    assert matching_blocks(a, b, ["dabid"], ["dauid"], units, 1) == []
    # An equivalent deletion context needs the literal local result.
    a = "kai ek tou mark autou ek tou number".split()
    b = "kai ek tou number".split()
    unit = ranges([3, 7], [3, 3])
    assert matching_blocks(a, b, a[:5], ["kai"], [unit], 0) == [0]
    assert matching_blocks(a, b, a[:5], ["kai"], [unit], 1) == []
    assert (
        matching_blocks(a, "kai ek other number".split(), a[:5], ["kai"], [unit], 0)
        == []
    )
    assert matching_blocks(a, b, a[:5], ["kai"], [ranges([3, 4], [3, 3])], 0) == []
    # Partial readings need the same collation unit; crossed quotations abstain.
    a, b = "x a y".split(), "z a w".split()
    unit = ranges([0, 3], [0, 3])
    assert matching_blocks(a, b, ["y"], ["w"], [unit]) == [0]
    assert matching_blocks(a, b, ["a"], ["a"], [unit]) == []
    assert (
        matching_blocks(
            a, b, ["x"], ["w"], blocks({"MAT 1:1": a}, {"MAT 1:1": b}, PLAIN)
        )
        == []
    )
    assert (
        collation_ranges(
            ["a", "b"],
            ["b", "a"],
            [{"tr": ["a"], "rp": ["a"]}, {"tr": ["b"], "rp": ["b"]}],
        )
        == []
    )
    # The article quoted at Mark 13:32 occurs earlier too. Only the complete
    # quotation identifies the article adjacent to "hour".
    a, b = ["ths", "other", "kai", "ths", "wras"], ["ths", "other", "h", "wras"]
    unit = ranges([2, 4], [2, 3])
    assert matching_blocks(a, b, ["ths", "wras"], ["wras"], [unit], 3) == [0]
    assert matching_blocks(a, b, ["ths", "wras"], ["wras"], [unit], 0) == []
    # A full quotation elsewhere cannot donate its trimmed word to this unit.
    a, b = ["anchor", "drop", "drop", "other"], ["anchor", "replacement", "other"]
    unit = ranges([2, 4], [1, 3])
    assert matching_blocks(a, b, ["anchor", "drop"], ["anchor"], [unit], 0) == []
    assert (
        matching_blocks(
            ["drop", "other"], b, ["missing", "drop"], ["missing"], [unit], 0
        )
        == []
    )


def test_ellipsis_cannot_hide_a_changed_interior() -> None:
    assert ellipsis_pairs("x … y", "z … w", ["x", "a", "y"], ["z", "a", "w"], {}) == [
        (["x", "a", "y"], ["z", "a", "w"])
    ]
    assert ellipsis_pairs("x … y", "z … w", ["x", "a", "y"], ["z", "b", "w"], {}) == []
    assert ellipsis_pairs("x … y", "z … w", ["x", "y"], ["z", "w"], {}) == []
    assert (
        ellipsis_pairs(
            "x … y", "z … w … v", ["x", "a", "y"], ["z", "a", "w", "b", "v"], {}
        )
        == []
    )


def test_synthetic_notes_establish_hf_side_only_when_they_agree() -> None:
    tr = {"MAT 1:1": "qhsaurou ths kardias ekballei ta agaqa".split()}
    rp = {"MAT 1:1": "qhsaurou ekballei agaqa".split()}
    coll: list[CollationRow] = [
        {
            "entry": 1,
            "target_ref": "MAT 1:1",
            "tr": tr["MAT 1:1"],
            "rp": rp["MAT 1:1"],
            "raw": "test",
        }
    ]
    note: BoydNote = {
        "entry": 1,
        "target_ref": "MAT 1:1",
        "tr": [{"reading": "θησαυρου της καρδιας"}],
        "rp": "θησαυρου",
        "hf": "RP",
        "rp_alternate": False,
        "patriarchal": False,
        "raw": "test",
    }
    units, unmatched = reconcile(tr, rp, coll, [note], structure=PLAIN)
    assert unmatched == []
    [unit] = [u for u in units if u["ref"] == "MAT 1:1"]
    assert (unit["hf"], unit["inventories"][-1]["scope"]) == ("RP", "constituent")
    # Same verse and context cannot attach an unrelated deletion.
    unrelated: BoydNote = {**note, "rp": "αγαθα"}
    assert len(reconcile(tr, rp, coll, [unrelated], structure=PLAIN)[1]) == 1
    # Agreeing constituent flags establish the side; a conflict is "other".
    tr = {"MAT 1:1": ["x", "a", "y"]}
    rp = {"MAT 1:1": ["z", "a", "w"]}
    coll = [
        {
            "entry": 1,
            "target_ref": "MAT 1:1",
            "tr": tr["MAT 1:1"],
            "rp": rp["MAT 1:1"],
            "raw": "z a w ] x a y",
        }
    ]
    first: BoydNote = {**note, "tr": [{"reading": "x"}], "rp": "z", "raw": "z ¦ x TR"}
    second: BoydNote = {
        **first,
        "entry": 2,
        "tr": [{"reading": "y"}],
        "rp": "w",
        "hf": "TR",
        "raw": "w ¦ y HF TR",
    }
    assert reconcile(tr, rp, coll, [first], structure=PLAIN)[0][0]["hf"] == "RP"
    assert (
        reconcile(tr, rp, coll, [first, second], structure=PLAIN)[0][0]["hf"] == "other"
    )


def test_collation_merges_transposition() -> None:
    tr = {"MRK 6:37": "diakosiwn dhnariwn".split()}
    rp = {"MRK 6:37": "dhnariwn diakosiwn".split()}
    entry: CollationRow = {
        "entry": 1,
        "target_ref": "MRK 6:37",
        "tr": tr["MRK 6:37"],
        "rp": rp["MRK 6:37"],
        "raw": "δηναριων διακοσιων ] διακοσιων δηναριων",
    }
    units, unmatched = reconcile(tr, rp, [entry], [], structure=PLAIN)
    assert unmatched == []
    [unit] = [u for u in units if u["ref"] == "MRK 6:37"]
    assert (unit["class"], unit["tr_range"], unit["id"]) == (
        "order",
        [0, 2],
        "MRK 6:37#1",
    )


def test_movable_normalization_keeps_original_ranges() -> None:
    units = blocks(
        {"MAT 1:1": ["eiden", "estin"]}, {"MAT 1:1": ["eide", "kai", "esti"]}, PLAIN
    )
    assert [u["class"] for u in units] == ["movable", "particle", "movable"]
    assert [u["tr_range"] for u in units] == [[0, 1], [1, 1], [1, 2]]
    assert [u["rp_range"] for u in units] == [[0, 1], [1, 2], [2, 3]]
    assert (units[0]["tr"], units[0]["rp"]) == (["eiden"], ["eide"])


def test_diff_normalization_requires_annotations_at_the_same_address() -> None:
    # The synthetic tokens carry no Strong's numbers; the diff reads none.
    tr, rp = {"MAT 1:1": ["legousin"]}, {"MAT 1:1": ["legousi"]}
    token: Token = {"word": "legousi", "strong": [], "parse": ["V-PAI-3P"]}
    noun: Token = {"word": "legousi", "strong": [], "parse": ["N-NSM"]}
    assert blocks(tr, rp, PLAIN, tags={"MAT 1:1": [token]})[0]["class"] == "movable"
    assert (
        blocks(tr, rp, PLAIN, tags={"MAT 1:2": [token]})[0]["class"] == "substitution"
    )
    assert blocks(tr, rp, PLAIN, tags={"MAT 1:1": [noun]})[0]["class"] == "substitution"


def test_quotation_aliases_do_not_remove_a_nouns_final_nu() -> None:
    forms = quotation_forms(
        {
            "MAT 1:1": [
                {"word": "eishlqen", "strong": [], "parse": ["V-2AAI-3S"]},
                {"word": "legousin", "strong": [], "parse": ["V-PAI-3P"]},
                {"word": "logon", "strong": [], "parse": ["N-ASM"]},
            ]
        }
    )
    assert forms["eishlqe"] == forms["eishlqen"]
    assert forms["legousi"] == forms["legousin"]
    assert "logon" not in forms
    assert classify(["eishlqe"], ["eishlqen"]) == "substitution"
    a, b = ["eishlqen", "palin"], ["palin", "eishlqen"]
    assert matching_blocks(
        a,
        b,
        ["eishlqe", "palin"],
        b,
        blocks({"MAT 1:1": a}, {"MAT 1:1": b}, PLAIN),
        forms=forms,
    ) == [0, 1]


def test_neutral_classes_do_not_expand_by_similarity() -> None:
    assert classify(["estin"], ["esti"]) == "movable"
    assert classify(["mh", "ti"], ["mhti"]) == "word-division"
    assert classify(["efqeiren"], ["diefqeiren"]) == "substitution"
    assert classify(["lama"], ["lima"]) == "substitution"
    assert classify(["hmwn"], ["umwn"]) == "pronoun"
    assert classify(["mou"], []) == "pronoun"
    assert classify([], ["soi"]) == "pronoun"
    assert classify(["autou"], ["hmwn"]) == "substitution"
    assert classify(["tou", "hmwn"], ["tou", "umwn"]) == "substitution"
    assert classify(["kai"], []) == "particle"
    assert classify(["tou"], []) == "article"
    assert classify(["a", "b"], ["b", "a"]) == "order"


def test_conjugation_numbers_and_attic_forms_are_not_lexical_changes() -> None:
    ref = "LUK 7:2"
    tr, rp = {ref: ["hmellen"]}, {ref: ["emellen"]}
    tags: Tagged = {
        "TR "
        + ref: [{"word": "hmellen", "strong": [3195, 5707], "parse": ["V-IAI-3S-ATT"]}],
        ref: [{"word": "emellen", "strong": [3195], "parse": ["V-IAI-3S"]}],
    }
    unit = blocks(tr, rp, PLAIN)[0]
    before = copy.deepcopy(tags)
    result = annotated_class(unit, tr, rp, tags)
    assert result["class"] == "spelling"
    assert result["classification_evidence"]["tr"] == tags["TR " + ref][0]
    assert tags == before
    forms = quotation_forms(tags)
    assert forms["hmelle"] == forms["hmellen"]
    tags["TR " + ref][0]["strong"].append(3004)
    assert annotated_class(unit, tr, rp, tags)["class"] == "substitution"
    tags["TR " + ref][0]["strong"] = [3195, 6000]
    assert annotated_class(unit, tr, rp, tags)["class"] == "substitution"


def test_annotation_classes_require_complete_exact_address_evidence() -> None:
    ref = "MAT 1:1"
    tr, rp = {ref: ["dabid"]}, {ref: ["dauid"]}
    unit = blocks(tr, rp, PLAIN)[0]
    tags: Tagged = {
        "TR " + ref: [{"word": "dabid", "strong": [1138], "parse": ["N-PRI"]}],
        ref: [{"word": "dauid", "strong": [1138], "parse": ["N-PRI"]}],
    }
    before = copy.deepcopy((unit, tags))
    assert annotated_class(unit, tr, rp, tags)["class"] == "name-spelling"
    assert (unit, tags) == before
    tags[ref][0]["parse"] = ["N-PRI", "N-NSM"]
    assert annotated_class(unit, tr, rp, tags)["class"] == "substitution"
    tags[ref][0]["parse"] = ["N-PRI"]
    tags[ref][0]["word"] = "different"
    assert annotated_class(unit, tr, rp, tags)["class"] == "substitution"


def test_disjunctive_eta_is_not_an_article(
    byzantine: Mapping[str, Any], units: list[Unit], tags: Tagged
) -> None:
    by_id = {u["id"]: u for u in units}
    for uid in ("MRK 6:15#1", "ACT 24:11#1", "1CO 6:16#1", "REV 13:17#2"):
        unit = by_id[uid]
        assert unit["class"] == "particle"
        assert unit["classification_evidence"]["tr"]["strong"] == [2228]
    for uid in ("LUK 4:38#1", "JHN 5:1#1", "EPH 2:21#1", "REV 10:1#2"):
        assert by_id[uid]["class"] == "article"
    # A homograph without exact, unambiguous source tags keeps its form class.
    unit = {**by_id["MRK 6:15#1"], "class": "article"}
    tr, rp = byzantine["tr"], byzantine["rp"]
    assert annotated_class(unit, tr, rp, {})["class"] == "article"
    ambiguous = copy.deepcopy(tags)
    ambiguous["TR MRK 6:15"][unit["tr_range"][0]]["strong"].append(3588)
    assert annotated_class(unit, tr, rp, ambiguous)["class"] == "article"


def test_real_morphology_classes_and_prefix_guard(
    byzantine: Mapping[str, Any], tags: Tagged
) -> None:
    tr, rp = byzantine["tr"], byzantine["rp"]
    for ref, expected in [
        ("MAT 1:1", "name-spelling"),
        ("MAT 8:13", "spelling"),
        ("MAT 8:8", "inflection"),
        ("REV 19:2", "substitution"),
        ("MAT 27:46", "substitution"),
    ]:
        classes = [
            annotated_class(u, tr, rp, tags)["class"]
            for u in blocks({ref: tr[ref]}, {ref: rp[ref]}, PLAIN)
        ]
        assert expected in classes, ref


# Supplementary units: relocations and accents.


def test_relocations_carry_both_inventories_and_stay_apart_from_wording(
    units: list[Unit],
) -> None:
    moves = [u for u in units if u.get("kind") == "relocation"]
    # In whatever order the structural decisions list them.
    assert sorted(u["ref"] for u in moves) == [
        "MAT 23:13",
        "MAT 23:14",
        "ROM 16:25",
        "ROM 16:26",
        "ROM 16:27",
    ]
    assert all(
        u["found_in"] == ["placement", "collation", "tcgnt"]
        and u["class"] == "structural"
        for u in moves
    )
    assert (
        len({(a["inventory"], a["entry"]) for u in moves for a in u["inventories"]})
        == 11
    )
    assert all(a["scope"] == "relocation" for u in moves for a in u["inventories"])
    last = next(u for u in moves if u["ref"] == "ROM 16:27")
    assert last["tr"] != last["rp"]
    # A move cannot absorb the doxology's independent added pronoun.
    assert [
        u["class"] for u in units if u["ref"] == "ROM 16:27" and not u.get("kind")
    ] == ["addition"]


def test_accent_units_check_the_printed_target_and_keep_equal_letters(
    byzantine: Mapping[str, Any], units: list[Unit]
) -> None:
    accents = {u["ref"]: u for u in units if u.get("kind") == "accent"}
    assert set(accents) == {"LUK 3:23", "PHP 3:5", "1CO 5:13", "MRK 4:8", "MRK 4:20"}
    assert all(u["tr"] == u["rp"] and u["class"] == "accent" for u in accents.values())
    assert accents["1CO 5:13"]["found_in"] == ["rp2026-printed", "tcgnt"]
    assert accents["1CO 5:13"]["inventories"] == [
        {"inventory": "tcgnt", "entry": 962, "scope": "unit"}
    ]
    assert accents["LUK 3:23"]["found_in"] == ["rp2026-apparatus", "tcgnt"]
    assert accents["PHP 3:5"]["found_in"] == ["rp2026-apparatus"]
    start, end = accents["MRK 4:8"]["tr_range"]
    assert (accents["MRK 4:8"]["hf"], accents["MRK 4:8"]["tr"]) == (
        "TR",
        byzantine["tr"]["MRK 4:8"][start:end],
    )
    assert accents["MRK 4:8"]["tr"].count("en") == 3


def test_supplementary_units_refuse_a_changed_printed_reading_or_scope(
    byzantine: Mapping[str, Any], structure: Structure
) -> None:
    tr, rp, coll, notes, printed = (
        byzantine["tr"],
        byzantine["rp"],
        byzantine["collation"],
        byzantine["tcgnt"],
        byzantine["printed"],
    )
    _, diacritics = greek.printed(
        byzantine["printed_xml"], structure.omitted, "REV 22:21"
    )
    accents = byzantine["decisions"]["accents"]
    before = copy.deepcopy((tr, rp, coll, notes, printed, diacritics))
    assert (
        len(
            supplementary_units(
                tr, rp, coll, notes, printed, diacritics, structure, accents
            )
        )
        == 10
    )
    assert (tr, rp, coll, notes, printed, diacritics) == before
    snapshot = copy.deepcopy(printed)
    snapshot["MRK 4:8"]["accented"][19] = "ἕν"
    with pytest.raises(ValueError, match="Printed breathing disagrees: MRK 4:8"):
        supplementary_units(
            tr, rp, coll, notes, snapshot, diacritics, structure, accents
        )
    snapshot = copy.deepcopy(printed)
    snapshot["1CO 5:13"]["accented"][rp["1CO 5:13"].index("krinei")] = "κρίνει"
    with pytest.raises(ValueError, match="Printed accent disagrees: 1CO 5:13"):
        supplementary_units(
            tr, rp, coll, notes, snapshot, diacritics, structure, accents
        )
    changed: list[BoydNote] = copy.deepcopy(notes)
    position = next(r for r in changed if r["entry"] == 173)["position"]
    assert position is not None
    position["offset"] += 1
    with pytest.raises(ValueError, match="Changed breathing scope"):
        supplementary_units(
            tr, rp, coll, changed, printed, diacritics, structure, accents
        )


def printed_checks(
    units: Iterable[Unit], snapshot: Mapping[str, PrintedVerse], printed_xml: Content
) -> list[dict[str, Any]]:
    """Twenty named Greek spot checks against the printed main text and apparatus:
    letters and boundaries, one unit per book from Matthew to James."""
    selected = "MAT 1:1#1|MRK 1:9#1|LUK 1:10#1|JHN 1:28#1|ACT 1:16#1|ROM 1:3#1|1CO 1:29#1|2CO 1:6#1|GAL 1:4#1|EPH 1:10#1|PHP 1:6#2|COL 1:2#1|1TH 2:6#1|2TH 2:4#1|1TI 1:2#1|2TI 1:14#1|TIT 2:2#1|PHM 1:6#1|HEB 1:1#1|JAS 1:5#1".split(
        "|"
    )
    by_id = {u["id"]: u for u in units}
    pages = printed_pages(printed_xml)
    result = []
    for key in selected:
        unit = by_id[key]
        page = printed_page(snapshot, unit["target_ref"])
        streams = []
        for main in (False, True):
            # The named 2 Corinthians phrase runs onto the following page.
            selected_pages = [pages[page]] + (
                [pages[page + 1]] if main and key == "2CO 1:6#1" else []
            )
            streams.append(greek_words(page_text(selected_pages, main)))
        if not occurrences(streams[0], unit["tr"]) or not occurrences(
            streams[1], unit["rp"]
        ):
            raise ValueError(f"Printed Greek spot check changed: {key}, page {page}")
        result.append(
            {
                "unit": key,
                "page": page,
                "tr": unit["tr"],
                "rp": unit["rp"],
                "check": "TR letters present in printed apparatus; RP letters present in printed main text",
            }
        )
    return result


def test_printed_spot_checks_name_twenty_units(
    byzantine: Mapping[str, Any], units: list[Unit]
) -> None:
    checks = printed_checks(units, byzantine["printed"], byzantine["printed_xml"])
    assert len(checks) == 20
    assert checks[0] == {
        "unit": "MAT 1:1#1",
        "page": 29,
        "tr": ["dabid"],
        "rp": ["dauid"],
        "check": "TR letters present in printed apparatus; RP letters present in printed main text",
    }
    assert [c["unit"].split()[0] for c in checks] == BOOKS[:20]


def test_duplicate_accent_unit_ids_are_rejected(
    byzantine: Mapping[str, Any], structure: Structure
) -> None:
    _, diacritics = greek.printed(
        byzantine["printed_xml"], structure.omitted, "REV 22:21"
    )
    assert diacritics
    with pytest.raises(ValueError, match=re.escape(diacritics[0]["ref"] + "#accent")):
        supplementary_units(
            byzantine["tr"],
            byzantine["rp"],
            byzantine["collation"],
            byzantine["tcgnt"],
            byzantine["printed"],
            [*diacritics, diacritics[0]],
            structure,
            byzantine["decisions"]["accents"],
        )
    ids = [u["id"] for u in byzantine["units"]]
    assert len(ids) == len(set(ids))
