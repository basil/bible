"""One disposition for every Greek unit, by precedence, with its tags."""

from __future__ import annotations

import copy
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import pytest

import bible.pipeline
from bible.byzantine import (
    ADDITIONAL,
    BOYD_ASV,
    PIERPONT,
    RV,
    TCENT,
    decide,
    rendering,
    stages,
    tags,
)
from bible.byzantine.instructions import bind_plain, compatibility, constructions
from bible.byzantine.rows import (
    Alarm,
    BoundEdit,
    Disposition,
    Instruction,
    InstructionEdit,
    Override,
    Report,
    RevisionRow,
    Unit,
)
from bible.byzantine.stages import Context
from bible.byzantine.tags import Tag
from bible.byzantine.units import NEUTRAL_CLASSES

DISPOSITIONS = {"override", "structural", "witnessed", "conflict", "neutral", "silent"}
ACTIONS = {"edit", "nochange", "covered", "omit", "move", "refused"}

REF = "MAT 3:8"
FIRST, SECOND = REF + "#1", REF + "#2"
KJV = {REF: "Bring forth therefore fruits meet for repentance:"}


@pytest.fixture(scope="module")
def context(edition: bible.pipeline.Edition) -> Context:
    return edition.byzantine.context


@pytest.fixture(scope="module")
def readings(context: Context) -> list[dict[str, Any]]:
    """The readings of edition/byzantine.json, each with its key as its id."""
    return [
        {"id": key, **entry} for key, entry in context["decisions"]["readings"].items()
    ]


def unit(uid: str = FIRST, classification: str = "substitution") -> Unit:
    return {"id": uid, "ref": REF, "class": classification, "hf": "RP"}


def replacing(
    entry: int = 1,
    new: str = "fruit",
    source: str = PIERPONT,
    units: Sequence[str] = (FIRST,),
) -> Instruction:
    """A compatible instruction replacing "fruits" in MAT 3:8."""
    return {
        "source": source,
        "entry": entry,
        "ref": REF,
        "refs": [REF],
        "compatibility": "compatible",
        "units": [{"unit": u} for u in units],
        "edits": [
            {
                "kind": "replace",
                "ref": REF,
                "word_range": [3, 4],
                "old": "fruits",
                "new": new,
                "units": list(units),
            }
        ],
    }


def keep_kjv(uid: str = FIRST) -> Override:
    return {
        "id": uid,
        "unit_ids": [uid],
        "kind": "nochange",
        "why": "Keep the KJV.",
        "evidence": {},
        "tag_set": [Tag.FROM_KJV_RETAINED, Tag.GRAM_LEXICAL],
        "bound": [],
    }


def bound(edit: Mapping[str, Any], ref: str, text: str) -> InstructionEdit:
    """An explicit edit bound to a verse's text, as an instruction makes it."""
    found = bind_plain(edit, text)
    assert found["bind"] == "unique"
    result: InstructionEdit = {
        "ref": ref,
        "kind": found["kind"],
        "old": found["old"],
        "new": found["new"],
        "bind": found["bind"],
        "word_range": found["word_range"],
    }
    if "side" in found:
        result["side"] = found["side"]
    return result


def decided(context: Context) -> list[Disposition]:
    """The dispositions decided again from the context's own inputs."""
    return decide.decide(
        context["units"],
        context["instructions"],
        context["reports"],
        context["revision_rows"],
        context["overrides"],
        context["alarms"],
        context["kjv"],
        supplied=context["supplied"],
    )


def test_every_unit_has_exactly_one_disposition(context: Context) -> None:
    rows = context["dispositions"]
    assert Counter(r["unit"] for r in rows) == Counter(
        u["id"] for u in context["units"]
    )
    assert all(r["disposition"] in DISPOSITIONS for r in rows)
    assert all(r["action"] in ACTIONS for r in rows)
    assert [r["unit"] for r in rows] == [u["id"] for u in context["units"]]


def test_decide_is_a_function_of_its_inputs(context: Context) -> None:
    """Running the stage again gives the same rows (before execution adds to them)."""
    again = decided(context)
    now = {r["unit"]: r for r in context["dispositions"]}
    assert len(again) == len(now)
    for row in again:
        # Execution adds the seam and finished-verse tags afterwards.
        assert (row["disposition"], row["tags"]) == (
            now[row["unit"]]["disposition"],
            [
                t
                for t in now[row["unit"]]["tags"]
                if t not in {"ev:finished-verse", "ev:seam-adjusted"}
            ],
        )


# Precedence


def test_an_overridden_unit_is_override(
    context: Context,
    dispositions: Mapping[str, Disposition],
    readings: list[dict[str, Any]],
) -> None:
    assert readings
    for o in context["overrides"]:
        for uid in o["unit_ids"]:
            row = dispositions[uid]
            assert row["disposition"] == "override" and row["override"] == o["id"]
            assert row["kind"] == o["kind"]
            if o["kind"] == "nochange":
                assert row["action"] == "nochange" and "op:nochange" in row["tags"]
            elif uid == o["unit_ids"][0]:
                assert row["action"] in {"edit", "refused"}
            else:
                assert (
                    row["action"] in {"covered", "refused"}
                    and row.get("covered_by") == o["unit_ids"][0]
                )
            if len(o["unit_ids"]) > 1:
                assert "ev:multi-unit" in row["tags"]
    first = readings[0]
    assert dispositions[first["units"][0]["ref"] + "#1"][
        "disposition"
    ] == "override" or any(
        dispositions[uid]["override"] == first["id"]
        for uid in context["overrides"][0]["unit_ids"]
    )


@pytest.mark.parametrize("higher", ["override", "structural", "conflict"])
def test_higher_dispositions_suppress_conflicting_witness_edits(higher: str) -> None:
    current = unit()
    overrides = []
    if higher == "override":
        overrides = [keep_kjv()]
    if higher in {"override", "structural"}:
        current.update({"class": "structural", "target_ref": "MAT 3:7"})
    rows = decide.decide(
        [current],
        [replacing(), replacing(2, "fruit trees")],
        [],
        [],
        overrides,
        {},
        KJV,
    )
    assert rows[0]["disposition"] == higher
    assert rows[0]["action"] == ("omit" if higher == "structural" else "nochange")
    assert not rows[0].get("ops")


class Refusal(rendering.Checker):
    """A rendering checker that refuses every instruction."""

    def __init__(self) -> None:
        pass

    def check(
        self,
        edit: InstructionEdit,
        unit_ids: Iterable[str],
        group: Sequence[InstructionEdit] | None = None,
    ) -> tuple[str, str | None]:
        return ("contradicted", "Every instruction is refused")


def test_two_readings_must_merge_even_when_every_instruction_is_refused(
    context: Context, readings: list[dict[str, Any]]
) -> None:
    original = next(o for o in readings if o["id"] == "ACT 9:5#1+ACT 9:6#1")
    split: dict[str, Any] = {}
    for key in original["units"]:
        entry = copy.deepcopy(original)
        del entry["id"]
        entry.update(units=[key], kind="nochange", edits=[])
        entry["evidence"] = {PIERPONT: entry["evidence"][PIERPONT]}
        split[f"{key['ref']}#1"] = entry
    units = [u for u in context["units"] if u["id"] in split]
    instruction = copy.deepcopy(
        next(
            i
            for i in context["instructions"]
            if i["source"] == PIERPONT and i["entry"] == 332
        )
    )
    instruction["compatibility"], instruction["compatibility_reason"] = compatibility(
        instruction,
        {u["id"]: u for u in units},
        context["kjv"],
        context["supplied"],
        Refusal(),
    )
    own: Context = {
        "decisions": {"readings": split, "lemmas": {}},
        "units": units,
        "kjv": context["kjv"],
        "reports": [],
        "placement_errors": [],
        "instructions": [instruction],
        "supplied": context["supplied"],
        "checker": Refusal(),
        "texts": {w: context["texts"][w] for w in (RV, BOYD_ASV)},
        "revision_citations": context["revision_citations"],
        "faa_rows": context["faa_rows"],
    }
    stages.stage_decisions(own)
    assert len(own["overrides"]) == 2  # Both entries individually validate.
    assert len(own["instructions"]) == 1
    assert own["instructions"][0]["compatibility"] == "incompatible"
    assert own["decision_errors"] == [
        "ACT#c1: taken by overrides ACT 9:5#1 and ACT 9:6#1; merge them into one"
    ]


def test_matthew_23_move_units_are_structural(
    dispositions: Mapping[str, Disposition],
) -> None:
    for uid, target in [
        ("MAT 23:13#move", "MAT 23:14"),
        ("MAT 23:14#move", "MAT 23:13"),
    ]:
        row = dispositions[uid]
        assert row["disposition"] == "structural"
        assert row["action"] == "move" and row["target_ref"] == target
        assert "op:move-verse" in row["tags"]


def test_every_structural_unit_is_structural(
    units: list[Unit], dispositions: Mapping[str, Disposition]
) -> None:
    structural = [
        u for u in units if u["class"] == "structural" or u.get("kind") == "relocation"
    ]
    assert len(structural) == 9
    for u in structural:
        row = dispositions[u["id"]]
        assert row["disposition"] == "structural"
        assert row["action"] == ("move" if u.get("kind") == "relocation" else "omit")
    omitted = {
        u["ref"] for u in structural if dispositions[u["id"]]["action"] == "omit"
    }
    assert omitted == {"LUK 17:36", "ACT 8:37", "ACT 15:34", "ACT 24:7"}


def test_matthew_3_8_is_witnessed_from_pierpont_with_remaining_corroboration(
    dispositions: Mapping[str, Disposition],
) -> None:
    row = dispositions["MAT 3:8#1"]
    assert row["disposition"] == "witnessed" and row["action"] == "edit"
    assert row["basis"].startswith("pierpont:")
    assert TCENT in row["corroborated_by"]
    assert {"from:pierpont", "ev:corroborated", "op:replace"} <= set(row["tags"])
    assert "ev:single-witness" not in row["tags"]
    assert row["execution"] == "applied"
    assert [(e["old"], e["new"]) for e in row["edits"]] == [("fruits", "fruit")]


def test_a_neutral_unit_with_no_reports_is_neutral(
    context: Context,
    dispositions: Mapping[str, Disposition],
    by_id: Mapping[str, Unit],
) -> None:
    rows = [r for r in context["dispositions"] if r["disposition"] == "neutral"]
    assert rows
    attached = {a["unit"] for i in context["instructions"] for a in i.get("units", [])}
    for row in rows:
        assert by_id[row["unit"]]["class"] in NEUTRAL_CLASSES
        assert row["witnesses"] == [] and row["unit"] not in attached
        assert row["action"] == "nochange" and "op:nochange" in row["tags"]
    assert dispositions["MAT 1:6#3"]["disposition"] == "neutral"
    assert by_id["MAT 1:6#3"]["class"] == "spelling"


def test_a_neutral_class_unit_a_witness_reports_is_not_neutral(
    context: Context, by_id: Mapping[str, Unit]
) -> None:
    for row in context["dispositions"]:
        if by_id[row["unit"]]["class"] in NEUTRAL_CLASSES and row["witnesses"]:
            assert row["disposition"] != "neutral"
    reports: list[Report] = [{"witness": TCENT, "units": [{"unit": FIRST}]}]
    row = decide.decide(
        [unit(classification="spelling")], [], reports, [], [], {}, KJV
    )[0]
    assert (row["disposition"], row["action"]) == ("silent", "nochange")


def test_a_conflict_executes_nothing(context: Context) -> None:
    for row in context["dispositions"]:
        if row["disposition"] == "conflict":
            assert row["action"] == "nochange"
            assert {"ev:witnesses-disagree", "op:nochange"} <= set(row["tags"])
            assert row["flags"]


def test_a_silent_unit_keeps_the_kjv(context: Context) -> None:
    for row in context["dispositions"]:
        if row["disposition"] == "silent":
            assert row["action"] == "nochange"
            assert {"op:nochange", "from:kjv-retained"} <= set(row["tags"])


# Tags and scores


def test_every_tag_is_a_tag(context: Context) -> None:
    for row in context["dispositions"]:
        for t in row["tags"]:
            Tag(t)
        assert row["tags"] == sorted(row["tags"])
        # The op: tags of a shared construction sit on the unit that executes it.
        if row["action"] != "covered":
            assert any(t.startswith("op:") for t in row["tags"]), row["unit"]


def test_computed_tags_never_appear_in_the_readings(
    readings: list[dict[str, Any]],
) -> None:
    for o in readings:
        for t in o["tags"]:
            assert Tag(t).group in tags.ASSERTED_GROUPS, (o["id"], t)


def test_witnessed_and_override_rows_carry_from_and_gram_tags(
    context: Context,
) -> None:
    for row in context["dispositions"]:
        if row["disposition"] in {"witnessed", "override"}:
            groups = {Tag(t).group for t in row["tags"]}
            assert {"from", "gram"} <= groups, (row["unit"], row["tags"])


def test_a_single_witness_and_a_corroborated_edit_exclude_each_other(
    context: Context,
) -> None:
    for row in context["dispositions"]:
        if row["disposition"] == "witnessed" and row["action"] != "nochange":
            both = {"ev:single-witness", "ev:corroborated"} & set(row["tags"])
            assert len(both) == 1, row["unit"]
            assert ("ev:corroborated" in both) == bool(row["corroborated_by"])


def test_revision_corroboration_does_not_splice_witnesses() -> None:
    edits: list[InstructionEdit] = [
        {"kind": "replace", "old": "fruits", "new": "fruit"},
        {"kind": "delete", "old": "and with fire", "new": ""},
    ]
    rows: list[RevisionRow] = [
        {"kind": "replace", "old": "fruits", "new": "fruit", "witness": RV},
        {"kind": "delete", "old": "and with fire", "new": "", "witness": BOYD_ASV},
    ]
    assert decide.revision_corroborating(edits, rows) == []
    rows.append({"kind": "delete", "old": "and with fire", "new": "", "witness": RV})
    assert decide.revision_corroborating(edits, rows) == [RV]
    assert decide.revision_corroborating([], rows) == []


@pytest.mark.parametrize("uid", ["COL 3:12#1", "REV 12:8#1", "REV 21:24#1"])
def test_a_revision_worded_differently_does_not_corroborate(
    dispositions: Mapping[str, Disposition], uid: str
) -> None:
    # RV has "compassion", "they", and "amidst"; the selected instructions
    # and Boyd have "mercy", "he", and "by", respectively.
    row = dispositions[uid]
    assert BOYD_ASV in row["corroborated_by"]
    assert RV not in row["corroborated_by"]
    assert "ev:revision-agrees" in row["tags"]


def test_only_agreeing_revisions_receive_corroboration(context: Context) -> None:
    by_unit: defaultdict[str, list[RevisionRow]] = defaultdict(list)
    for report in context["revision_rows"]:
        for attached in report.get("units", []):
            by_unit[attached["unit"]].append(report)
    for row in context["dispositions"]:
        if row["disposition"] != "witnessed" or row["action"] == "nochange":
            continue
        actual = set(row["corroborated_by"]) & {RV, BOYD_ASV}
        expected = set(
            decide.revision_corroborating(row["selected_edits"], by_unit[row["unit"]])
        )
        assert actual == expected, row["unit"]
        assert ("ev:revision-agrees" in row["tags"]) == bool(expected), row["unit"]


def test_revisions_and_alarms_change_no_decision_or_book(context: Context) -> None:
    """Without revision rows and alarms only evidence fields differ, and the
    prepared books and invariants are the same. Revision evidence keeps a
    nochange reading from being marked redundant, which decides whether the
    build stops on it, not the text."""
    full: Context = {**context}
    stages.stage_decide(full)
    bare: Context = {**context, "revision_rows": [], "alarms": {}}
    stages.stage_decide(bare)
    evidence_fields = {
        "tags",
        "flags",
        "corroborated_by",
        "alarm_phrases",
        "redundant",
    }
    for present, absent in zip(full["dispositions"], bare["dispositions"], strict=True):
        assert {k: v for k, v in present.items() if k not in evidence_fields} == {
            k: v for k, v in absent.items() if k not in evidence_fields
        }, present["unit"]
    stages.stage_edit(bare)
    stages.stage_verify(bare)
    assert bare["prepared"] == context["prepared"]
    assert bare["invariants"] == context["invariants"]


# Selection


def test_a_lower_precedence_edit_does_not_block_a_pierpont_selection(
    context: Context,
    instructions: Mapping[tuple[str, int | str], Instruction],
    kjv_text: Mapping[str, str],
) -> None:
    higher = copy.deepcopy(instructions[(PIERPONT, 603)])
    ref, uid = "1JN 4:16", "1JN 4:16#1"
    edit = bound(
        {
            "kind": "insert",
            "old": "",
            "new": "abideth",
            "anchor": "in him",
            "side": "before",
        },
        ref,
        kjv_text[ref],
    )
    edit.update({"units": [uid], "method": "aligned", "scope": "unit"})
    lower: Instruction = {
        "source": ADDITIONAL,
        "entry": 1,
        "ref": ref,
        "refs": [ref],
        "role": "instruction",
        "scope": "greek",
        "bind": "unique",
        "units": [{"unit": uid, "scope": "unit", "method": "aligned"}],
        "edits": [edit],
        "compatibility": "compatible",
    }
    grouped = constructions([higher, lower], kjv_text)
    rows = decide.decide(
        [u for u in context["units"] if u["id"] == uid],
        grouped,
        [],
        [],
        [],
        {},
        kjv_text,
    )
    row = rows[0]
    assert row["basis"] == "pierpont:603"
    assert row["disagreeing"] == [{"source": ADDITIONAL, "entry": 1}]
    assert "ev:witnesses-disagree" in row["tags"] and row["action"] == "edit"


def test_the_deciding_source_is_the_highest_present(
    context: Context, instructions: Mapping[tuple[str, int | str], Instruction]
) -> None:
    for row in context["dispositions"]:
        if row["disposition"] != "witnessed":
            continue
        source, entry = row["basis"].split(":")
        chosen = instructions[(source, int(entry) if entry.isdigit() else entry)]
        assert any(a["unit"] == row["unit"] for a in chosen["units"])
        assert chosen["compatibility"] in {"compatible", "agrees"}
        if source == ADDITIONAL:
            assert not any(
                i["source"] == PIERPONT
                and i["compatibility"] == "compatible"
                and any(a["unit"] == row["unit"] for a in i["units"])
                for i in context["instructions"]
            )


def test_a_covered_unit_names_an_executing_owner(
    context: Context, dispositions: Mapping[str, Disposition]
) -> None:
    for row in context["dispositions"]:
        if row["action"] == "covered":
            owner = dispositions[row["covered_by"]]
            assert owner["action"] == "edit"
            # A witnessed unit may be covered by an override that claims the
            # first unit of its shared construction (REV 3:7#4 by REV 3:7#3).
            assert (
                owner["disposition"] == row["disposition"]
                or owner["disposition"] == "override"
            ), row["unit"]


def test_a_wholly_shared_edit_still_executes_once() -> None:
    rows = decide.decide(
        [unit(), unit(SECOND)],
        [replacing(units=(FIRST, SECOND))],
        [],
        [],
        [],
        {},
        KJV,
    )
    assert [r["action"] for r in rows] == ["edit", "covered"]
    assert rows[1]["covered_by"] == FIRST
    assert sum(len(r.get("ops", [])) for r in rows) == 1


def test_a_unit_with_shared_and_private_edits_executes_its_private_edit() -> None:
    ref = "ACT 9:6"
    units: list[Unit] = [
        {"id": f"{ref}#{n}", "ref": ref, "class": "substitution"} for n in (1, 2)
    ]
    shared: InstructionEdit = {
        "kind": "replace",
        "ref": ref,
        "word_range": [0, 1],
        "old": "Arise",
        "new": "Rise",
        "units": [u["id"] for u in units],
    }
    own: InstructionEdit = {
        "kind": "replace",
        "ref": ref,
        "word_range": [2, 3],
        "old": "go",
        "new": "enter",
        "units": [units[1]["id"]],
    }
    instruction: Instruction = {
        "source": PIERPONT,
        "entry": 1,
        "compatibility": "compatible",
        "units": [{"unit": u["id"]} for u in units],
        "edits": [shared, own],
    }
    rows = decide.decide(units, [instruction], [], [], [], {}, {ref: "Arise and go"})
    assert [r["action"] for r in rows] == ["edit", "edit"]
    assert [[op["new"] for op in r["ops"]] for r in rows] == [["Rise"], ["enter"]]


def test_every_unit_has_one_disposition_and_action(context: Context) -> None:
    rows = context["dispositions"]
    assert len(rows) == len(context["units"])
    assert {r["disposition"] for r in rows} <= DISPOSITIONS
    tagged = Counter(t for r in rows for t in r["tags"])
    assert tagged["op:move-verse"] == 5 and tagged["op:omit-verse"] == 4


# Redundancy


def nochange_override(units: Sequence[Unit]) -> Override:
    return {
        "id": "+".join(u["id"] for u in units),
        "unit_ids": [u["id"] for u in units],
        "kind": "nochange",
        "why": "The reported difference leaves the KJV unchanged.",
        "evidence": {},
        "tag_set": [Tag.FROM_KJV_RETAINED, Tag.GRAM_LEXICAL],
        "bound": [],
    }


@pytest.mark.parametrize("reported_unit", [0, 1, None])
def test_nochange_redundancy_is_a_whole_override_decision(
    reported_unit: int | None,
) -> None:
    units: list[Unit] = [
        {"id": f"ACT 9:{verse}#1", "ref": f"ACT 9:{verse}", "class": "omission"}
        for verse in (5, 6)
    ]
    reports: list[Report] = (
        []
        if reported_unit is None
        else [{"witness": TCENT, "units": [{"unit": units[reported_unit]["id"]}]}]
    )
    rows = decide.decide(units, [], reports, [], [nochange_override(units)], {}, {})
    # The build stops on a reading if any of its rows is redundant, so a
    # quiet member never condemns the ruling another member's report justifies.
    assert [r.get("redundant", False) for r in rows] == [reported_unit is None] * 2


@pytest.mark.parametrize("evidence", ["revision", "alarm"])
def test_nochange_with_revision_evidence_is_not_redundant(evidence: str) -> None:
    # Without the reading the unit is silent with revision evidence still
    # open for review; a reading that settles it is not redundant.
    rev: Unit = {"id": "REV 8:9#1", "ref": "REV 8:9", "class": "omission"}
    revisions: list[RevisionRow] = (
        [{"units": [{"unit": rev["id"]}], "reviser": "retained"}]
        if evidence == "revision"
        else []
    )
    alarms: dict[str, Alarm] = (
        {
            rev["id"]: {
                "applicable": True,
                "available": True,
                "alarm": True,
                "missing": [],
            }
        }
        if evidence == "alarm"
        else {}
    )
    [row] = decide.decide(
        [rev], [], [], revisions, [nochange_override([rev])], alarms, {}
    )
    assert not row.get("redundant")


def test_an_override_mending_only_italics_or_a_capital_is_not_redundant() -> None:
    kjv = {"REV 5:7": "And he came and took the book out of the right hand"}
    instruction: Instruction = {
        "edits": [
            {
                "ref": "REV 5:7",
                "kind": "replace",
                "word_range": [5, 7],
                "old": "the book",
                "new": "it",
            }
        ]
    }
    start = kjv["REV 5:7"].index("the book")

    def override(new: str) -> Override:
        return {
            "bound": [
                {
                    "ref": "REV 5:7",
                    "start": start,
                    "end": start + len("the book"),
                    "old": "the book",
                    "new": new,
                }
            ]
        }

    assert decide.same_effect(override("it"), instruction, kjv)
    assert not decide.same_effect(override("[it]"), instruction, kjv)
    assert not decide.same_effect(override("It"), instruction, kjv)


@pytest.mark.parametrize("ref", ["MAT 9:5", "MRK 2:9"])
def test_romanizing_retained_thy_is_not_redundant(context: Context, ref: str) -> None:
    """The source italic Thy now renders sou; omitting thee alone keeps italics."""
    text = context["kjv"][ref]
    supplied = context["supplied"]
    assert any(value == "Thy" for _, _, value in supplied[ref])
    omission = bound({"kind": "delete", "old": "thee", "new": ""}, ref, text)
    instruction: Instruction = {"edits": [omission]}
    thy = text.index("Thy")
    thee = text.index("thee")
    omission_bound: BoundEdit = {"ref": ref, "start": thee, "end": thee + 4, "new": ""}
    roman: Override = {
        "bound": [
            omission_bound,
            {"ref": ref, "start": thy, "end": thy + 3, "new": "Thy"},
        ]
    }
    italic: Override = {
        "bound": [
            omission_bound,
            {"ref": ref, "start": thy, "end": thy + 3, "new": "[Thy]"},
        ]
    }
    kjv = context["kjv"]
    assert not decide.same_effect(roman, instruction, kjv, supplied)
    assert decide.same_effect(italic, instruction, kjv, supplied)
    assert decide.same_effect({"bound": [omission_bound]}, instruction, kjv, supplied)


def test_instruction_retains_source_italics_and_transposition_moves_them() -> None:
    kjv = {"X 1:1": "Thy sins be forgiven thee."}
    supplied = {"X 1:1": [(0, 3, "Thy")]}
    edit: InstructionEdit = {
        "ref": "X 1:1",
        "kind": "replace",
        "word_range": [0, 5],
        "old": kjv["X 1:1"],
        "new": "Thy sins be forgiven",
    }
    instruction: Instruction = {"edits": [edit]}

    def override(reading: str) -> Override:
        return {
            "bound": [
                {
                    "ref": "X 1:1",
                    "start": 0,
                    "end": len(kjv["X 1:1"]) - 1,
                    "new": reading,
                }
            ]
        }

    assert decide.same_effect(
        override("[Thy]  sins be forgiven"), instruction, kjv, supplied
    )
    assert not decide.same_effect(
        override("Thy sins be forgiven"), instruction, kjv, supplied
    )
    # Explicit brackets override inheritance for replacements, but a uniquely
    # identified transposed word still moves its original source styling.
    edit["new"] = "[sins] Thy be forgiven thee"
    assert decide.same_effect(
        override("[sins] Thy be forgiven thee"), instruction, kjv, supplied
    )
    edit["kind"] = "transpose"
    assert decide.same_effect(
        override("sins [Thy] be forgiven thee"), instruction, kjv, supplied
    )
    assert not decide.same_effect(
        override("[sins] Thy be forgiven thee"), instruction, kjv, supplied
    )


@pytest.mark.parametrize("case", ["capital", "punctuation"])
def test_redundancy_includes_capitals_and_punctuation(case: str) -> None:
    ref = "3JN 1:7" if case == "capital" else "2CO 7:13"
    text = "for his name’s sake" if case == "capital" else "in your comfort: yea"
    old, new = (
        ("his name’s sake", "the Name’s sake")
        if case == "capital"
        else ("your comfort: yea", "your comfort, and")
    )
    instruction: Instruction = {
        "edits": [bound({"kind": "replace", "old": old, "new": new}, ref, text)]
    }
    at = text.index(old)

    def override(reading: str) -> Override:
        return {
            "bound": [{"ref": ref, "start": at, "end": at + len(old), "new": reading}]
        }

    assert decide.same_effect(override(new), instruction, {ref: text})
    correction = "the name’s sake" if case == "capital" else "your comfort: and"
    assert not decide.same_effect(override(correction), instruction, {ref: text})


def test_redundancy_includes_an_instructions_stop() -> None:
    # Pierpont's "(Period) + And" ends the preceding sentence; an override
    # without that stop has a different effect and is not redundant.
    ref, text = "2CO 7:13", "we were comforted in your comfort"
    edit = bound(
        {"kind": "insert", "old": "", "new": "And", "anchor": "comforted"}, ref, text
    )
    edit["stop"] = "."
    instruction: Instruction = {"edits": [edit]}
    at = text.index(" in")

    def override(reading: str) -> Override:
        return {"bound": [{"ref": ref, "start": at, "end": at, "new": reading}]}

    assert decide.same_effect(override(". And"), instruction, {ref: text})
    assert not decide.same_effect(override("And"), instruction, {ref: text})
