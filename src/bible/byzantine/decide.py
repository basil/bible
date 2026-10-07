"""One disposition for every Greek unit.

Precedence: an override; a structural unit; a witnessed instruction (or a
conflict between instructions); a neutral unit; silence. Nothing else gates
execution. Corroboration, Pierpont's weight, Hodges-Farstad's side, the
revision alarm and an unplaced row in the verse are tags, never guards, and
the tags give the unit its controversy score.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from bible.byzantine import ADDITIONAL, APPARATUS, FAA, PIERPONT, TCENT
from bible.byzantine.crosswire import (
    bracket_kept,
    contrast,
    curly_apostrophes,
    edit_offsets,
    reports_by_unit,
    spans,
    unique_moves,
)
from bible.byzantine.decisions import Supplied
from bible.byzantine.instructions import corroborating, select
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
from bible.byzantine.tags import Tag
from bible.byzantine.units import NEUTRAL_CLASSES

HYPER_LITERAL = set(APPARATUS) - {TCENT}
GRAM_BY_CLASS = {
    "article": Tag.GRAM_ARTICLE,
    "particle": Tag.GRAM_PARTICLE,
    "pronoun": Tag.GRAM_PRONOUN,
    "order": Tag.GRAM_ORDER,
    "name-spelling": Tag.GRAM_NAME,
    "inflection": Tag.GRAM_INFLECTION,
    "accent": Tag.GRAM_PUNCTUATION,
    "substitution": Tag.GRAM_LEXICAL,
    "omission": Tag.GRAM_LEXICAL,
    "addition": Tag.GRAM_LEXICAL,
    "prefix": Tag.GRAM_LEXICAL,
}
OP_BY_KIND = {
    "replace": Tag.OP_REPLACE,
    "delete": Tag.OP_OMIT,
    "insert": Tag.OP_ADD,
    "transpose": Tag.OP_TRANSPOSE,
}
# The words that change, before and after (crosswire.contrast).
type Contrast = tuple[tuple[str, ...], tuple[str, ...]]

FROM_BY_SOURCE = {
    PIERPONT: Tag.FROM_PIERPONT,
    ADDITIONAL: Tag.FROM_ADDITIONAL,
}


def edit_kind(edit: BoundEdit) -> str:
    """An override edit's kind of operation."""
    return (
        "replace"
        if edit["new"] and edit["old"]
        else "delete" if edit["old"] else "insert"
    )


def unit_tags(unit: Unit) -> set[Tag]:
    tags = set()
    if unit.get("hf") not in {"RP", "unknown"}:
        tags.add(Tag.EV_HF_DIFFERS)
    if unit.get("rp_alternate"):
        tags.add(Tag.EV_RP_ALTERNATE)
    if unit.get("patriarchal"):
        tags.add(Tag.EV_PATRIARCHAL_TR)
    return tags


def revision_corroborating(
    edits: Sequence[InstructionEdit], revision_rows: Sequence[RevisionRow]
) -> list[str]:
    """Revisions that each support every edit's contrast at the unit.

    Partial support from different revisions cannot form one corroborating
    witness, and an attached revision with different wording earns no credit.
    """
    wanted = {(e["kind"], contrast(e["old"], e["new"])) for e in edits}
    found: defaultdict[str, set[tuple[str, Contrast]]] = defaultdict(set)
    for r in revision_rows:
        found[r["witness"]].add((r["kind"], contrast(r["old"], r["new"])))
    return sorted(w for w, contrasts in found.items() if wanted and wanted <= contrasts)


def displaced(
    o: Override, instructions: Sequence[Instruction], kjv: Mapping[str, str]
) -> tuple[list[Instruction], list[InstructionEdit]]:
    """What would execute at an override's units without it: the
    instructions their sources would select there, and the edits of the
    constructions it took that were compatible."""
    taken = {id(i) for i in instructions if o["id"] in (i.get("displaced_by") or [])}
    view: list[Instruction] = [
        (
            {
                **i,
                "compatibility": (
                    i["displaced"] if i.get("displaced_choice") else "superseded"
                ),
            }
            if id(i) in taken
            else i
        )
        for i in instructions
    ]
    picks: list[Instruction] = []
    for other in o["unit_ids"]:
        chosen, _, _ = select(view, other, kjv)
        if chosen and not chosen.get("nochange"):
            picks.append(chosen)
    combined: list[InstructionEdit] = []
    for i in instructions:
        if (
            id(i) in taken
            and i.get("displaced_choice")
            and i["displaced"] == "compatible"
        ):
            combined += [e for e in i["edits"] if e not in combined]
    return picks, combined


def decide(
    units: Sequence[Unit],
    instructions: Sequence[Instruction],
    reports: Sequence[Report],
    revision_rows: Sequence[RevisionRow],
    overrides: Sequence[Override],
    alarms: Mapping[str, Alarm],
    kjv: Mapping[str, str],
    supplied: Supplied | None = None,
) -> list[Disposition]:
    """Dispositions for every unit, in ledger order.

    instructions: attached and checked instruction rows; reports: the
    apparatus reports; revision_rows: RV and Boyd ASV rows (revision_reports);
    overrides: compiled overrides (decisions.validate_overrides); alarms:
    revisions.alarms. A unit an override covers belongs to that override; an
    edit that several units share is executed by the first of them and the
    others are `covered`.
    """
    by_unit_reports = reports_by_unit(reports)
    by_unit_revisions = reports_by_unit(revision_rows)
    by_unit_instructions = reports_by_unit(instructions)
    verse_unplaced: defaultdict[str, bool] = defaultdict(bool)
    for r in reports:
        # The selected lists (MSB, WEB) are placed only by an exact
        # English contrast; a verse-level row of theirs is not a loose end.
        if r.get("scope") == "verse" and r["witness"] in {TCENT, FAA}:
            verse_unplaced[r["ref"]] = True
    # The sources whose instructions attach to each unit.
    attached_sources: defaultdict[str, set[str]] = defaultdict(set)
    for i in instructions:
        if i.get("scope") == "verse":
            for ref in i.get("refs", []):
                verse_unplaced[ref] = True
        for a in i.get("units", []):
            attached_sources[a["unit"]].add(i["source"])
    override_of: dict[str, Override] = {}
    for o in overrides:
        for uid in o["unit_ids"]:
            override_of[uid] = o
    displacements: dict[str, tuple[list[Instruction], list[InstructionEdit]]] = {}
    order = {u["id"]: n for n, u in enumerate(units)}
    result: list[Disposition] = []
    for unit in units:
        uid = unit["id"]
        tags = unit_tags(unit)
        flags: list[str] = []
        row: Disposition = {
            "unit": uid,
            "ref": unit["ref"],
            "class": unit["class"],
            "witnesses": sorted({r["witness"] for r in by_unit_reports[uid]}),
        }
        if verse_unplaced[unit["ref"]]:
            tags.add(Tag.EV_UNPLACED_ROW_IN_VERSE)
        selected, disagreeing, conflict = select(instructions, uid, kjv)
        if TCENT in row["witnesses"]:
            row["tcent_reports"] = True
        if selected and not selected.get("nochange"):
            row["selected"] = {
                "source": selected["source"],
                "entry": selected["entry"],
                "joint": selected["joint"],
            }
            row["selected_edits"] = [
                e for e in selected["edits"] if uid in e.get("units", [])
            ]
        if uid in override_of:
            o = override_of[uid]
            owner = o["unit_ids"][0]
            row.update(
                {
                    "disposition": "override",
                    "override": o["id"],
                    "kind": o["kind"],
                    "why": o["why"],
                    "evidence": o["evidence"],
                }
            )
            tags.update(o["tag_set"])
            if o["kind"] == "nochange":
                row["action"] = "nochange"
                tags.add(Tag.OP_NOCHANGE)
            elif uid == owner:
                row["action"] = "edit"
                row["ops"] = [
                    {
                        "kind": edit_kind(e),
                        "ref": e["ref"],
                        "range": [e["start"], e["end"]],
                        "old": e["old"],
                        "new": e["new"],
                        "side": e["side"],
                        "raw_range": True,
                        **({"unstyle": True} if e.get("unstyle") else {}),
                    }
                    for e in o["bound"]
                ]
                tags.update(OP_BY_KIND[op["kind"]] for op in row["ops"])
            else:
                row["action"] = "covered"
                row["covered_by"] = owner
                tags.update(OP_BY_KIND[edit_kind(e)] for e in o["bound"])
            if len(o["unit_ids"]) > 1:
                tags.add(Tag.EV_MULTI_UNIT)
            # Compare the override with what would execute without it: the
            # whole construction, in the wording of the source that would have
            # executed it. The same effect makes the override redundant, a
            # different one a refusal of that instruction.
            if o["id"] not in displacements:
                displacements[o["id"]] = displaced(o, instructions, kjv)
            picks, combined = displacements[o["id"]]
            if (
                o["kind"] == "edit"
                and combined
                and same_effect(o, {"edits": combined}, kjv, supplied)
            ):
                row["redundant"] = True
            elif (
                o["kind"] == "nochange"
                and not picks
                and not conflict
                and not any(by_unit_reports[other] for other in o["unit_ids"])
                and not any(by_unit_revisions[other] for other in o["unit_ids"])
                and not any(
                    alarms.get(other, {}).get("alarm") for other in o["unit_ids"]
                )
                and not any(
                    any(a["unit"] in o["unit_ids"] for a in i.get("units", []))
                    for i in instructions
                )
            ):
                # Redundancy belongs to the whole override: a quiet member
                # cannot erase a ruling justified by another member's witness.
                # Attached revision rows or a revision alarm would leave the
                # unit open for review without it, so they also keep it.
                row["redundant"] = True
            elif refusing := picks or (
                [selected]
                if selected and selected.get("nochange") and o["kind"] == "edit"
                else []
            ):
                tags.add(Tag.EV_INSTRUCTION_REFUSED)
                first = refusing[0]
                row["refused_instruction"] = {
                    "source": first["source"],
                    "entry": first["entry"],
                }
            if conflict:
                flags.append(conflict)
        elif unit["class"] == "structural" or unit.get("kind") == "relocation":
            row.update(
                {
                    "disposition": "structural",
                    "action": "move" if unit.get("kind") == "relocation" else "omit",
                    "target_ref": unit["target_ref"],
                }
            )
            tags.add(
                Tag.OP_MOVE_VERSE
                if unit.get("kind") == "relocation"
                else Tag.OP_OMIT_VERSE
            )
            tags.add(Tag.GRAM_LEXICAL)
        elif conflict:
            row.update(
                {"disposition": "conflict", "action": "nochange", "reason": conflict}
            )
            tags.update({Tag.EV_WITNESSES_DISAGREE, Tag.OP_NOCHANGE})
            flags.append(conflict)
        elif selected and selected.get("nochange"):
            row.update(
                {
                    "disposition": "witnessed",
                    "action": "nochange",
                    "basis": f"{selected['source']}:{selected['entry']}",
                }
            )
            tags.update({Tag.OP_NOCHANGE, Tag.EV_KJV_ALREADY, Tag.FROM_KJV_RETAINED})
            tags.add(GRAM_BY_CLASS.get(unit["class"], Tag.GRAM_LEXICAL))
        elif selected:
            edits = row["selected_edits"]
            shared = sorted(
                {u for e in edits for u in e.get("units", [])}, key=order.__getitem__
            )
            owner = shared[0] if shared else uid
            owned_edits = [
                e
                for e in edits
                if min(e.get("units") or [uid], key=order.__getitem__) == uid
            ]
            row.update(
                {
                    "disposition": "witnessed",
                    "basis": f"{selected['source']}:{selected['entry']}",
                }
            )
            if not owned_edits:
                row.update({"action": "covered", "covered_by": owner})
            else:
                row["action"] = "edit"
                row["ops"] = [operation(e) for e in owned_edits]
            tags.update(OP_BY_KIND[e["kind"]] for e in edits)
            tags.add(FROM_BY_SOURCE[selected["source"]])
            rendering = selected.get("rendering")
            if rendering:
                tags.add(
                    Tag.EV_RENDERING_VERIFIED
                    if rendering == "verified"
                    else Tag.EV_RENDERING_UNVERIFIED
                )
            tags.add(GRAM_BY_CLASS.get(unit["class"], Tag.GRAM_LEXICAL))
            support = corroborating(
                selected, uid, by_unit_instructions[uid], by_unit_reports[uid], kjv
            )
            row["corroborated_by"] = support
            agreeing_revisions = revision_corroborating(edits, by_unit_revisions[uid])
            if agreeing_revisions:
                tags.add(Tag.EV_REVISION_AGREES)
                row["corroborated_by"] = sorted(set(support) | set(agreeing_revisions))
            tags.add(
                Tag.EV_CORROBORATED if row["corroborated_by"] else Tag.EV_SINGLE_WITNESS
            )
            if disagreeing:
                tags.add(Tag.EV_WITNESSES_DISAGREE)
                row["disagreeing"] = [
                    {"source": i["source"], "entry": i["entry"]} for i in disagreeing
                ]
            if selected["source"] == PIERPONT:
                strength = selected.get("strength")
                if strength == "mandatory":
                    tags.add(Tag.EV_PIERPONT_MANDATORY)
                elif strength == "weak":
                    tags.add(Tag.EV_PIERPONT_WEAK)
            if (
                len(shared) > 1
                or len(selected.get("joint", [])) > 1
                and len({e["ref"] for e in selected["edits"]}) > 1
            ):
                tags.add(Tag.EV_MULTI_UNIT)
        elif (
            unit["class"] in NEUTRAL_CLASSES
            and not by_unit_reports[uid]
            and not attached_sources[uid]
        ):
            row.update({"disposition": "neutral", "action": "nochange"})
            tags.add(Tag.OP_NOCHANGE)
        else:
            row.update({"disposition": "silent", "action": "nochange"})
            tags.update({Tag.OP_NOCHANGE, Tag.FROM_KJV_RETAINED})
            witnesses = set(row["witnesses"])
            if TCENT in witnesses:
                tags.add(Tag.EV_TCENT_REPORTS)
            elif witnesses and witnesses <= HYPER_LITERAL:
                tags.add(Tag.EV_HYPER_LITERAL_ONLY)
            if any(r.get("reviser") == "revised" for r in by_unit_revisions[uid]):
                flags.append("Boyd changed the ASV here")
            if unit.get("kind") == "accent":
                tags.add(Tag.GRAM_PUNCTUATION)
            unattached = [
                i
                for i in instructions
                if i.get("compatibility") in {"unattached", "incompatible", "unbound"}
                and unit["ref"] in i.get("refs", [])
            ]
            if unattached:
                flags.append(
                    f"{len(unattached)} instruction(s) in the verse not executed"
                )
        alarm = alarms.get(uid, {})
        if alarm.get("alarm") and row["disposition"] in {
            "silent",
            "neutral",
            "conflict",
        }:
            tags.add(Tag.EV_REVISION_ALARM)
            row["alarm_phrases"] = alarm["missing"]
        row["tags"] = sorted(t.value for t in tags)
        row["flags"] = flags
        result.append(row)
    return result


def operation(edit: InstructionEdit) -> dict[str, Any]:
    """What the executor needs of an instruction's edit."""
    op: dict[str, Any] = {
        "kind": edit["kind"],
        "ref": edit["ref"],
        "word_range": edit["word_range"],
        "old": edit["old"],
        "new": edit["new"],
    }
    if "side" in edit:
        op["side"] = edit["side"]
    if "stop" in edit:
        op["stop"] = edit["stop"]
    if "quoted_old" in edit:
        op["quoted_old"] = edit["quoted_old"]
    return op


def surface(text: str) -> str:
    """A verse's text for comparison: spacing normalized, everything else
    kept, supplied-word brackets, capitals and stops included."""
    text = curly_apostrophes(text)
    return re.sub(r"\s+([,;:.!?])", r"\1", " ".join(text.split()))


def same_effect(
    override: Override,
    selected: Instruction,
    kjv: Mapping[str, str],
    supplied: Supplied | None = None,
) -> bool:
    """Compare words, capitals, stops and supplied-word formatting.

    Untouched text keeps its source formatting. Instructions retain supplied
    words they carry over; raw override replacements declare italics explicitly
    with brackets. Transpositions move uniquely identified source words with
    their original formatting, as the executor does.
    """

    def characters(reading: str) -> list[tuple[str, bool]]:
        italic = False
        result = []
        for char in reading:
            if char == "[":
                italic = True
            elif char == "]":
                italic = False
            else:
                result.append((char, italic))
        return result

    def comparison(chars: list[tuple[str, bool]]) -> tuple[str, tuple[bool, ...]]:
        # Italic run boundaries and spacing do not change the printed words.
        text = "".join(char for char, _ in chars)
        return surface(text), tuple(
            style for char, style in chars if not char.isspace()
        )

    by_ref: defaultdict[str, list[InstructionEdit]] = defaultdict(list)
    for e in selected["edits"]:
        by_ref[e["ref"]].append(e)
    mine: defaultdict[str, list[BoundEdit]] = defaultdict(list)
    for bound in override["bound"]:
        mine[bound["ref"]].append(bound)
    if set(by_ref) != set(mine):
        return False
    for ref in mine:
        text = kjv[ref]
        source = [(char, False) for char in text]
        own_supplied = (supplied or {}).get(ref, [])
        for a, b, _ in own_supplied:
            source[a:b] = [(char, True) for char in text[a:b]]
        planned: list[tuple[int, int, list[tuple[str, bool]]]] = []
        for e in by_ref[ref]:
            lo, hi = edit_offsets(text, e)
            if (
                e["kind"] == "insert"
                and e.get("side") == "after"
                and e["word_range"][0]
            ):
                lo = hi = spans(text)[e["word_range"][0] - 1][2]
            new = e["new"]
            if "[" not in new:
                kept = [
                    text[max(a, lo) : min(b, hi)]
                    for a, b, _ in own_supplied
                    if a < hi and lo < b
                ]
                new = bracket_kept(new, kept)
            replacement = characters(new)
            if e["kind"] == "transpose":
                moves = unique_moves(text[lo:hi], "".join(c for c, _ in replacement))
                for start, end, a, b in moves:
                    replacement[start:end] = source[lo + a : lo + b]
            planned.append((lo, hi, [(" ", False)] + replacement + [(" ", False)]))
            if e.get("stop") and e["word_range"][0]:
                # The executor ends the preceding sentence with the
                # instruction's stop (Pierpont's "(Period) + And") unless the
                # KJV already has it there; equal offsets keep it first.
                at = spans(text)[e["word_range"][0] - 1][2]
                if text[at : at + 1] != e["stop"]:
                    planned.append((at, at, [(e["stop"], False)]))
        instruction = list(source)
        for lo, hi, chars in sorted(planned, key=lambda p: (p[0], p[1]), reverse=True):
            instruction[lo:hi] = chars
        result = list(source)
        for bound in sorted(mine[ref], key=lambda b: b["start"], reverse=True):
            result[bound["start"] : bound["end"]] = (
                [(" ", False)] + characters(bound["new"]) + [(" ", False)]
            )
        if comparison(instruction) != comparison(result):
            return False
    return True
