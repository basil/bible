"""The shared instruction logic on real rows: attach, compatibility, select,
corroborating, and a second instruction source."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from bible.byzantine import ADDITIONAL, PIERPONT
from bible.byzantine import instructions as inst
from bible.byzantine.crosswire import Aligned
from bible.byzantine.rows import (
    Disposition,
    Instruction,
    InstructionEdit,
    Report,
    Unit,
)

Instructions = dict[tuple[str, int | str], Instruction]


def additional_row(
    kjv: Mapping[str, str],
    ref: str,
    old: str,
    new: str,
    *,
    kind: str = "replace",
    entry: int = 1,
    occurrence: int | None = None,
    anchor: str | None = None,
    side: str = "after",
) -> Instruction:
    """An explicitly authored proposal of the `ADDITIONAL` source, bound to
    the pinned KJV and attached to no unit, in the shape every instruction
    source gives."""
    proposal: dict[str, Any] = {"ref": ref, "kind": kind, "old": old, "new": new}
    if anchor is not None:
        proposal.update(anchor=anchor, side=side)
    if occurrence is not None:
        proposal["occurrence"] = occurrence
    bound = inst.bind_plain(proposal, kjv[ref])
    edits: list[InstructionEdit] = []
    if bound["bind"] == "unique":
        edit: InstructionEdit = {
            "kind": kind,
            "ref": ref,
            "word_range": bound["word_range"],
            "old": old,
            "new": new,
            "bind": "unique",
        }
        if "side" in bound:
            edit["side"] = bound["side"]
        edits.append(edit)
    return {
        "source": ADDITIONAL,
        "entry": entry,
        "ref": ref,
        "refs": [ref],
        "role": "instruction",
        "bind": bound["bind"],
        "edits": edits,
    }


def additional_instruction(
    kjv: Mapping[str, str],
    ref: str,
    old: str,
    new: str,
    units: Sequence[str],
    *,
    kind: str = "replace",
    entry: int = 1,
    occurrence: int | None = None,
    anchor: str | None = None,
    side: str = "after",
) -> Instruction:
    """An additional proposal bound uniquely and attached to stated units,
    compatible: for tests of what follows attachment, independent of any
    source's parser."""
    row = additional_row(
        kjv,
        ref,
        old,
        new,
        kind=kind,
        entry=entry,
        occurrence=occurrence,
        anchor=anchor,
        side=side,
    )
    assert row["bind"] == "unique"
    for edit in row["edits"]:
        edit.update({"units": list(units), "method": "aligned", "scope": "unit"})
    row["scope"] = "greek"
    row["units"] = [{"unit": u, "scope": "unit", "method": "aligned"} for u in units]
    row["compatibility"] = "compatible"
    return row


def row(instructions: Instructions, source: str, entry: int) -> Instruction:
    """A copy of a built row: `compatibility` records its verdict on the row,
    which must not reach the session's shared build."""
    return copy.deepcopy(instructions[(source, entry)])


# --- attach -------------------------------------------------------------------------


def test_attach_methods_on_real_rows(instructions: Instructions) -> None:
    fruit = row(instructions, PIERPONT, 5)  # MAT 3:8
    assert fruit["units"] == [
        {"unit": "MAT 3:8#1", "scope": "constituent", "method": "aligned"}
    ]
    assert fruit["edits"][0]["positions"] == [2]
    satan = row(instructions, PIERPONT, 7)  # MAT 4:10: one unit, no bridge for "hence"
    assert satan["units"] == [
        {"unit": "MAT 4:10#1", "scope": "constituent", "method": "sole"}
    ]
    mark = row(instructions, PIERPONT, 95)  # MRK 9:40 us/our -> you/your
    assert [e["method"] for e in mark["edits"]] == ["contrast", "sole"]
    assert {u for e in mark["edits"] for u in e["units"]} == {"MRK 9:40#1"}
    peter = row(instructions, PIERPONT, 593)  # reordering across two units
    assert peter["edits"][0]["kind"] == "transpose"
    assert [a["unit"] for a in peter["units"]] == ["2PE 1:4#1", "2PE 1:4#2"]
    assert {a["method"] for a in peter["units"]} == {"construction"}
    # compatible on its own; superseded where a higher source executes the
    # construction
    assert peter["compatibility"] in {"compatible", "superseded"}


def test_attach_on_a_small_fixture_leaves_inputs_alone(
    instructions: Instructions,
) -> None:
    source_row = row(instructions, PIERPONT, 5)
    source_row.pop("units", None)
    source_row.pop("scope", None)
    source_row.pop("compatibility", None)
    source_row.pop("compatibility_reason", None)
    for e in source_row["edits"]:
        e.pop("units", None)
        e.pop("scope", None)
        e.pop("method", None)
        e.pop("positions", None)
    unit: Unit = {
        "id": "MAT 3:8#1",
        "ref": "MAT 3:8",
        "tr": ["karpous", "acious"],
        "rp": ["karpon", "acion"],
        "tr_range": [2, 4],
        "rp_range": [2, 4],
        "class": "inflection",
        "hf": "RP",
    }
    # "Bring forth therefore fruits meet for repentance:"
    positions = [[0], [0], [1], [2], [3], [4, 5], [4, 5]]
    aligned: dict[str, Aligned] = {
        "MAT 3:8": {
            "positions": positions,
            "direct": positions,
            "greek_length": 6,
            "word_ranges": [
                [0, 5],
                [6, 11],
                [12, 21],
                [22, 28],
                [29, 33],
                [34, 37],
                [38, 48],
            ],
        }
    }
    report: Report = {
        "witness": "faa",
        "entry": "MAT 3:8#1",
        "ref": "MAT 3:8",
        "old": "fruits",
        "new": "fruit",
        "method": "greek",
        "units": [{"unit": "MAT 3:8#1", "scope": "unit"}],
    }
    before = copy.deepcopy((source_row, unit, aligned, report))
    attached = inst.attach([source_row], [unit], aligned, [report])[0]
    assert attached["units"] == [
        {"unit": "MAT 3:8#1", "scope": "constituent", "method": "aligned"}
    ]
    assert attached["scope"] == "greek"
    assert (
        inst.attach([source_row], [unit], {}, [report])[0]["units"][0]["method"]
        == "contrast"
    )
    assert inst.attach([source_row], [unit], {}, [])[0]["units"][0]["method"] == "sole"
    two: list[Unit] = [
        unit,
        {**unit, "id": "MAT 3:8#2", "tr_range": [0, 1], "rp_range": [0, 1]},
    ]
    unplaced = inst.attach([source_row], two, {}, [])[0]
    assert (unplaced["units"], unplaced["scope"], unplaced["reason"]) == (
        [],
        "verse",
        "edit attaches to no unit",
    )
    elsewhere = inst.attach(
        [source_row], [{**unit, "ref": "MAT 3:9", "id": "MAT 3:9#1"}], {}, []
    )[0]
    assert (elsewhere["scope"], elsewhere["reason"]) == (
        "out-of-scope",
        "no Greek unit in the verse",
    )
    assert (source_row, unit, aligned, report) == before


# --- compatibility ---------------------------------------------------------------------


def test_compatibility_statuses_on_real_rows(
    instructions: Instructions,
    by_id: dict[str, Unit],
    kjv_text: Mapping[str, str],
    byzantine: Mapping[str, Any],
) -> None:
    supplied = byzantine["supplied"]

    def check(source: str, entry: int) -> tuple[str, str | None]:
        return inst.compatibility(
            row(instructions, source, entry), by_id, kjv_text, supplied
        )

    assert check(PIERPONT, 5) == ("compatible", None)
    assert check(PIERPONT, 11) == ("compatible", None)  # MAT 5:47 brethren -> friends
    # A placement separates this rendering advice from the actual spelling
    # difference. Misattaching it still cannot license the change.
    assert check(PIERPONT, 171)[0] == "out-of-scope"
    attached = row(instructions, PIERPONT, 171)
    attached["role"] = "instruction"
    attached["scope"] = "greek"
    for edit in attached["edits"]:
        edit["units"] = ["LUK 13:34#1"]
    assert inst.compatibility(attached, by_id, kjv_text, supplied) == (
        "incompatible",
        "LUK 13:34#1 is spelling only",
    )
    # JUD 1:24: one of two edits touches an italic word
    assert check(PIERPONT, 612) == ("compatible", None)
    assert check(PIERPONT, 27) == ("unbound", "binding absent")
    # The placement excludes nine Holies: RP2026's main text has three.
    assert check(PIERPONT, 679)[0] == "out-of-scope"
    assert check(PIERPONT, 29) == ("out-of-scope", "no Greek unit in the verse")
    assert check(PIERPONT, 968)[0] == "agrees"


def test_compatibility_shape_checks_on_a_synthetic_unit(
    instructions: Instructions,
    by_id: dict[str, Unit],
    kjv_text: Mapping[str, str],
    byzantine: Mapping[str, Any],
) -> None:
    supplied = byzantine["supplied"]
    fruit = row(instructions, PIERPONT, 5)
    spelling: Unit = {**by_id["MAT 3:8#1"], "class": "spelling"}
    assert inst.compatibility(
        fruit, {**by_id, "MAT 3:8#1": spelling}, kjv_text, supplied
    ) == ("incompatible", "MAT 3:8#1 is spelling only")
    fire = row(instructions, PIERPONT, 6)  # MAT 3:11 omit "and with fire"
    fire["edits"][0]["method"] = "sole"
    longer: Unit = {**by_id["MAT 3:11#1"], "rp_range": [29, 31]}
    assert inst.compatibility(
        fire, {**by_id, "MAT 3:11#1": longer}, kjv_text, supplied
    ) == ("incompatible", "omission at MAT 3:11#1, where RP is not shorter")
    assert inst.compatibility(fire, by_id, kjv_text, supplied) == (
        "compatible",
        None,
    )
    hell = row(instructions, PIERPONT, 629)  # REV 1:18 transposition
    hell["edits"][0]["method"] = "sole"
    substitution: Unit = {**by_id["REV 1:18#1"], "class": "substitution"}
    assert inst.compatibility(
        hell, {**by_id, "REV 1:18#1": substitution}, kjv_text, supplied
    ) == ("incompatible", "transposition at REV 1:18#1, which is not a reordering")
    ambiguous: Instruction = {
        **fruit,
        "edits": [{**fruit["edits"][0], "bind": "ambiguous"}],
    }
    assert inst.compatibility(ambiguous, by_id, kjv_text, supplied) == (
        "unbound",
        "an occurrence does not bind uniquely",
    )
    no_effect: Instruction = {
        **fruit,
        "edits": [{**fruit["edits"][0], "no_effect": True}],
    }
    assert inst.compatibility(no_effect, by_id, kjv_text, supplied)[0] == "agrees"
    # An insertion whose words the KJV already has agrees; beside a real
    # change it does not bind, and the row blocks its group.
    already: InstructionEdit = {**fruit["edits"][0], "bind": "already"}
    alone: Instruction = {**fruit, "bind": "already", "edits": [already]}
    assert inst.compatibility(alone, by_id, kjv_text, supplied)[0] == "agrees"
    beside: Instruction = {
        **fruit,
        "bind": "already",
        "edits": [already, fruit["edits"][0]],
    }
    assert inst.compatibility(beside, by_id, kjv_text, supplied) == (
        "unbound",
        "an insertion the KJV already has stands with a change",
    )


# --- select and corroborate ----------------------------------------------------------------


def test_pierpont_is_selected_and_remaining_witnesses_corroborate(
    byzantine: Mapping[str, Any],
    kjv_text: Mapping[str, str],
    dispositions: dict[str, Disposition],
) -> None:
    rows = byzantine["instructions"]
    selected, disagreeing, conflict = inst.select(rows, "MAT 3:8#1", kjv_text)
    assert selected is not None
    assert (selected["source"], selected["entry"]) == (PIERPONT, 5)
    assert (disagreeing, conflict) == ([], None)
    assert inst.corroborating(
        selected, "MAT 3:8#1", rows, byzantine["reports"], kjv_text
    ) == ["faa", "msb", "tcent"]
    assert dispositions["MAT 9:5#1"]["disposition"] == "override"
    assert inst.select(rows, "MAT 9:5#1", kjv_text)[0] is None


def test_disagreeing_additional_wording(
    instructions: Instructions, kjv_text: Mapping[str, str]
) -> None:
    higher = row(instructions, PIERPONT, 603)
    lower = additional_instruction(
        kjv_text,
        "1JN 4:16",
        "",
        "abideth",
        ["1JN 4:16#1"],
        kind="insert",
        anchor="in him",
        side="before",
    )
    rows = inst.constructions([higher, lower], kjv_text)
    selected, disagreeing, conflict = inst.select(rows, "1JN 4:16#1", kjv_text)
    assert selected is not None
    assert selected["source"] == PIERPONT
    assert [(d["source"], d["edits"][0]["new"]) for d in disagreeing] == [
        (ADDITIONAL, "abideth")
    ]
    assert conflict is None
    assert inst.corroborating(selected, "1JN 4:16#1", rows, [], kjv_text) == []


def test_joint_instructions_conflicts_and_agreement_only(
    byzantine: Mapping[str, Any],
    kjv_text: Mapping[str, str],
    instructions: Instructions,
) -> None:
    rows = byzantine["instructions"]
    selected, disagreeing, conflict = inst.select(rows, "REV 16:7#1", kjv_text)
    assert selected is not None
    assert selected["joint"] == [
        {"source": PIERPONT, "entry": 855},
        {"source": PIERPONT, "entry": 856},
    ]
    assert [(e["old"], e["new"]) for e in selected["edits"]] == [
        ("another", ""),
        ("out of", ""),
    ]
    fruit = row(instructions, PIERPONT, 5)
    other = copy.deepcopy(fruit)
    other["entry"] += 10000
    other["edits"][0]["new"] = "fruitage"
    assert inst.select([fruit, other], "MAT 3:8#1", kjv_text) == (
        None,
        [],
        "conflicting pierpont instructions at the unit",
    )
    assert inst.select([fruit, other], "MAT 3:8#1") == (
        None,
        [],
        "conflicting pierpont instructions at the unit",
    )
    agrees: Instruction = {
        **fruit,
        "compatibility": "agrees",
        "role": "agrees",
        "edits": [],
    }
    selected, disagreeing, conflict = inst.select([agrees], "MAT 3:8#1", kjv_text)
    assert selected is not None
    assert (selected["nochange"], selected["edits"], disagreeing, conflict) == (
        True,
        [],
        [],
        None,
    )
    incompatible: Instruction = {**fruit, "compatibility": "incompatible"}
    assert inst.select([incompatible], "MAT 3:8#1", kjv_text) == (None, [], None)


def test_signature_effect_and_overlap(
    instructions: Instructions, kjv_text: Mapping[str, str]
) -> None:
    fruit = row(instructions, PIERPONT, 5)
    assert inst.signature(fruit, "MAT 3:8#1") == (
        ("MAT 3:8", "replace", (3, 4), (("fruits",), ("fruit",)), "before"),
    )
    assert inst.signature(fruit, "MAT 3:9#1") == ()
    assert inst.effect(fruit["edits"], kjv_text)["MAT 3:8"][:5] == (
        "bring",
        "forth",
        "therefore",
        "fruit",
        "meet",
    )
    edit = fruit["edits"][0]
    assert inst.overlapping([edit, {**edit, "word_range": [3, 5]}])
    assert not inst.overlapping([edit, {**edit, "word_range": [4, 5]}])
    assert inst.overlapping(
        [{**edit, "word_range": [3, 3]}, {**edit, "word_range": [3, 3]}]
    )
    assert not inst.overlapping([edit, {**edit, "ref": "MAT 3:9"}])


# --- a second source -----------------------------------------------------------------------


def test_bind_plain_locates_explicit_edits(kjv_text: Mapping[str, str]) -> None:
    text = kjv_text["1JN 5:8"]  # "and" four times
    assert (
        inst.bind_plain({"kind": "delete", "old": "and"}, text)["bind"] == "ambiguous"
    )
    assert inst.bind_plain({"kind": "delete", "old": "and", "occurrence": 2}, text)[
        "word_range"
    ] == [11, 12]
    assert (
        inst.bind_plain({"kind": "delete", "old": "and", "occurrence": 9}, text)["bind"]
        == "absent"
    )
    assert inst.bind_plain(
        {"kind": "replace", "old": "witness", "new": "record"}, text
    )["word_range"] == [6, 7]
    assert (
        inst.bind_plain({"kind": "replace", "old": "testimony", "new": "record"}, text)[
            "bind"
        ]
        == "absent"
    )
    added = inst.bind_plain(
        {"kind": "insert", "new": "also", "anchor": "three", "side": "after"},
        kjv_text["MAT 3:8"],
    )
    assert added["bind"] == "absent"
    added = inst.bind_plain(
        {"kind": "insert", "new": "good", "anchor": "fruits"}, kjv_text["MAT 3:8"]
    )
    assert (added["bind"], added["word_range"], added["side"]) == (
        "unique",
        [4, 4],
        "after",
    )
    added = inst.bind_plain(
        {"kind": "insert", "new": "good", "anchor": "fruits", "side": "before"},
        kjv_text["MAT 3:8"],
    )
    assert added["word_range"] == [3, 3]
    assert (
        inst.bind_plain({"kind": "insert", "new": "good"}, kjv_text["MAT 3:8"])["bind"]
        == "absent"
    )


def test_explicit_occurrence_cannot_fall_back_to_a_unique_word() -> None:
    edit = {"kind": "delete", "old": "witness", "occurrence": 2}
    assert inst.bind_plain(edit, "a witness")["bind"] == "absent"
    assert inst.bind_plain({**edit, "occurrence": 1}, "a witness")["word_range"] == [
        1,
        2,
    ]
    for occurrence in (0, -1, True, 1.5, "1", None):
        with pytest.raises(ValueError, match="positive integer"):
            inst.bind_plain({**edit, "occurrence": occurrence}, "a witness")


def test_insertion_cannot_silently_treat_an_unknown_side_as_before() -> None:
    edit = {"kind": "insert", "anchor": "witness", "new": "faithful", "side": "befroe"}
    with pytest.raises(ValueError, match="side must be before or after"):
        inst.bind_plain(edit, "a witness")
    for side, position in (("before", 1), ("after", 2)):
        assert inst.bind_plain({**edit, "side": side}, "a witness")["word_range"] == [
            position,
            position,
        ]


def test_additional_rows_attach_and_rank_after_pierpont(
    kjv_text: Mapping[str, str],
    units: list[Unit],
    byzantine: Mapping[str, Any],
    by_id: dict[str, Unit],
    instructions: Instructions,
) -> None:
    proposal = additional_row(kjv_text, "MAT 3:8", "fruits", "fruit")
    assert proposal["edits"] == [
        {
            "kind": "replace",
            "ref": "MAT 3:8",
            "word_range": [3, 4],
            "old": "fruits",
            "new": "fruit",
            "bind": "unique",
        }
    ]
    additional = inst.attach(
        [proposal],
        [u for u in units if u["ref"] == "MAT 3:8"],
        byzantine["aligned"],
        byzantine["reports"],
    )
    additional[0]["compatibility"], _ = inst.compatibility(
        additional[0], by_id, kjv_text, byzantine["supplied"]
    )
    assert additional[0]["units"] == [
        {"unit": "MAT 3:8#1", "scope": "constituent", "method": "aligned"}
    ]
    assert additional[0]["compatibility"] == "compatible"
    selected, disagreeing, _ = inst.select(
        [*additional, row(instructions, PIERPONT, 5)], "MAT 3:8#1", kjv_text
    )
    assert selected is not None
    assert selected["source"] == PIERPONT and disagreeing == []
    assert inst.corroborating(selected, "MAT 3:8#1", additional, [], kjv_text) == [
        ADDITIONAL
    ]
    alone = inst.select(additional, "MAT 3:8#1", kjv_text)[0]
    assert alone is not None and alone["source"] == ADDITIONAL


def test_an_insertion_occurrence_chooses_its_anchor() -> None:
    text = "and he said and went"
    edit = {"kind": "insert", "anchor": "and", "new": "lo", "side": "after"}
    assert inst.bind_plain(edit, text)["bind"] == "ambiguous"
    assert inst.bind_plain({**edit, "occurrence": 2}, text)["word_range"] == [4, 4]
    assert inst.bind_plain({**edit, "occurrence": 3}, text)["bind"] == "absent"
