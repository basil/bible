"""Instructions are judged and executed by construction, never in parts; and
every finished verse is read whole."""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterable, Mapping
from typing import Any

import pytest
from test_byzantine_instructions import additional_instruction

from bible import usj
from bible.byzantine import ADDITIONAL, PIERPONT
from bible.byzantine.edit import NOTE_LABELS, NoteKind
from bible.byzantine.instructions import constructions, select
from bible.byzantine.rendering import Checker
from bible.byzantine.rows import Disposition, Instruction, InstructionEdit
from bible.byzantine.verify import lint, restores
from bible.scripture import Verse

Instructions = dict[tuple[str, int | str], Instruction]


def test_conflicting_words_at_different_units_take_the_group_whole(
    instructions: Instructions, kjv_text: Mapping[str, str]
) -> None:
    # Seed an overlap in the two adjoining constructions in Rev 13:16.
    # Each unit alone sees only one instruction; together they compete for
    # "a mark". The original, non-overlapping wording is the positive control.
    marks = copy.deepcopy(instructions[(PIERPONT, 817)])
    marks["compatibility"] = "compatible"
    verb = additional_instruction(
        kjv_text, "REV 13:16", "to receive", "that they should give", ["REV 13:16#1"]
    )
    verb.update({"source": PIERPONT, "entry": 10830, "compatibility": "compatible"})
    original = constructions([copy.deepcopy(marks), copy.deepcopy(verb)], kjv_text)
    for uid in ("REV 13:16#1", "REV 13:16#2"):
        assert select(original, uid, kjv_text)[0] is not None

    verb["edits"][0].update(
        {
            "word_range": [14, 18],
            "old": "to receive a mark",
            "new": "that they should give marks",
        }
    )
    mutated = constructions([marks, verb], kjv_text)
    assert marks["group"] == verb["group"]
    for uid in ("REV 13:16#1", "REV 13:16#2"):
        assert select(mutated, uid, kjv_text) == (
            None,
            [],
            "conflicting pierpont instructions in the construction",
        )


def test_a_group_with_a_refused_member_stands_down_whole(
    instructions: Instructions,
) -> None:
    # Rev 2:3: Pierpont's omission of "hast laboured" is refused, so his "and"
    # beside it does not execute alone.
    assert instructions[(PIERPONT, 633)]["compatibility"] == "incompatible"
    blocked = instructions[(PIERPONT, 634)]
    assert blocked["compatibility"] == "blocked" and "633" in (
        blocked["compatibility_reason"] or ""
    )
    assert blocked["group"] == instructions[(PIERPONT, 633)]["group"]


def test_matthew_11_16_shared_greek_changes_have_no_unit(
    instructions: Instructions,
) -> None:
    # The only main-text unit concerns children, while these instructions
    # concern retained words for markets and fellows.
    for entry in (25, 26):
        row = instructions[(PIERPONT, entry)]
        assert row["compatibility"] == "out-of-scope"
        assert row["units"] == []


def test_a_lower_source_in_the_same_construction_is_superseded(
    instructions: Instructions, kjv_text: Mapping[str, str]
) -> None:
    rows = constructions(
        [
            copy.deepcopy(instructions[(PIERPONT, 5)]),
            additional_instruction(
                kjv_text, "MAT 3:8", "fruits", "fruit", ["MAT 3:8#1"]
            ),
        ],
        kjv_text,
    )
    assert rows[1]["compatibility"] == "superseded"
    selected = select(rows, "MAT 3:8#1", kjv_text)[0]
    assert selected is not None and selected["source"] == PIERPONT


def test_an_override_takes_its_construction_whole(
    byzantine: Mapping[str, Any],
) -> None:
    rows: list[Instruction] = byzantine["instructions"]
    taken = [
        i
        for i in rows
        if "takes this construction" in (i.get("compatibility_reason") or "")
    ]
    assert taken
    overridden = {u for o in byzantine["overrides"] for u in o["unit_ids"]}
    for i in taken:
        units = {a["unit"] for a in i.get("units", [])}
        assert i["compatibility"] == "blocked"
        assert units & overridden or i["construction"]


def executed(byzantine: Mapping[str, Any]) -> list[Disposition]:
    dispositions: list[Disposition] = byzantine["dispositions"]
    return [
        d
        for d in dispositions
        if d["disposition"] == "witnessed" and d["action"] == "edit"
    ]


def test_every_executed_construction_has_one_source(
    byzantine: Mapping[str, Any], instructions: Instructions
) -> None:
    # Each executed edit comes from a compatible row whose edits all bind
    # uniquely to units, and no construction mixes two sources' rows.
    owners: dict[str | None, set[str]] = {}
    assert executed(byzantine)
    for d in executed(byzantine):
        for identity in d["selected"]["joint"]:
            source, entry = identity["source"], identity["entry"]
            witness = instructions[source, entry]
            assert witness["compatibility"] == "compatible"
            assert all(
                e["bind"] == "unique" and e.get("units") for e in witness["edits"]
            )
            owners.setdefault(witness["construction"], set()).add(source)
    assert all(len(sources) == 1 for sources in owners.values())


def test_no_executed_construction_contradicts_the_main_text(
    byzantine: Mapping[str, Any], instructions: Instructions
) -> None:
    # The executed edits of each construction, read together, are checked
    # against the pinned Greek rather than trusted from the disposition labels.
    checker: Checker = byzantine["checker"]
    groups: dict[str | None, list[InstructionEdit]] = {}
    for d in executed(byzantine):
        witness = instructions[d["selected"]["source"], d["selected"]["entry"]]
        own = groups.setdefault(witness["construction"], [])
        for edit in d["selected_edits"]:
            if edit not in own:
                own.append(edit)
    assert groups
    for construction, edits in groups.items():
        for edit in edits:
            verdict, reason = checker.check(edit, edit["units"], edits)
            assert verdict != "contradicted", (construction, reason)


def note(lemma: str, kind: NoteKind, alternative: str) -> usj.Node:
    extra: usj.Extra = {"category": "edition", "x-scope": {"kind": kind}}
    return usj.note(
        "f",
        usj.char("fq", lemma + ": "),
        usj.char("ft", NOTE_LABELS[kind]),
        usj.char("fqa", alternative),
        **extra,
    )


def test_notes_must_restore_the_kjv() -> None:
    kjv = "Bring forth therefore fruits meet for repentance:"
    edition = "Bring forth therefore fruit meet for repentance:"
    at = edition.index("fruit") + len("fruit")
    assert restores(edition, kjv, [(at, note("fruit", "replace", "fruits"))]) is None
    assert (
        restores(edition, kjv, [(at, note("fruit", "replace", "fruit tree"))])
        is not None
    )
    kjv = "he shall baptize you with the Holy Ghost, and with fire:"
    edition = "he shall baptize you with the Holy Ghost:"
    at = edition.index(":")
    # Exact: the comma before the TR's words is part of what must come back.
    assert (
        restores(
            edition,
            kjv,
            [
                (
                    at,
                    note("with the Holy Ghost", "adds", "and with fire"),
                )
            ],
        )
        is not None
    )
    assert (
        restores(
            edition,
            kjv,
            [
                (
                    at,
                    note("Holy Ghost", "replace", "Holy Ghost, and with fire"),
                )
            ],
        )
        is None
    )
    # A note stands at the end of its lemma.
    assert (
        restores(
            edition,
            kjv,
            [(0, note("Holy Ghost", "replace", "Holy Ghost, and with fire"))],
        )
        is not None
    )
    # A plain lemma still finds its words across a paragraph's line break.
    kjv = "he said,\nThou art the Christ."
    edition = "he said,\nThou art Christ."
    at = edition.index("Christ") + len("Christ")
    assert (
        restores(
            edition,
            kjv,
            [
                (
                    at,
                    note(
                        "said, Thou art Christ",
                        "replace",
                        "said, Thou art the Christ",
                    ),
                )
            ],
        )
        is None
    )
    kjv = "Art not thou one of his disciples? He denied it."
    edition = "Art not thou one of his disciples? Then he denied it."
    at = edition.index("Then") + len("Then")
    # Capitals count: taking out "Then" leaves "he", not the KJV's "He".
    assert restores(edition, kjv, [(at, note("Then", "omits", "Then"))]) is not None
    at = edition.index("Then he") + len("Then he")
    assert restores(edition, kjv, [(at, note("Then he", "replace", "He"))]) is None


def test_lint_reports_only_what_an_edit_introduced() -> None:
    common = {"but", "and"}
    assert lint("to destroy: But who art thou", "to destroy: who art thou", common) == [
        "capital after a comma or colon"
    ]
    assert lint("the seven also: left", "the seven also: and they left", common) == []
    assert "two stops together" in lint("elders., said", "elders, said", common)


def test_every_finished_verse_problem_is_flagged_for_review(
    byzantine: Mapping[str, Any], dispositions: dict[str, Disposition]
) -> None:
    for ref in byzantine["finished"]:
        rows = [
            r
            for r in dispositions.values()
            if any(e["ref"] == ref for e in r.get("edits", []))
        ]
        assert rows and all("ev:finished-verse" in r["tags"] for r in rows)


def test_a_lower_source_executes_where_the_higher_one_failed(
    instructions: Instructions, kjv_text: Mapping[str, str]
) -> None:
    failed = copy.deepcopy(instructions[(PIERPONT, 730)])
    assert failed["compatibility"] == "unbound"
    lower = additional_instruction(
        kjv_text,
        "REV 7:6",
        "were sealed",
        "",
        ["REV 7:6#2"],
        kind="delete",
        occurrence=2,
    )
    rows = constructions([failed, lower], kjv_text)
    selected = select(rows, "REV 7:6#2", kjv_text)[0]
    assert selected is not None and selected["source"] == ADDITIONAL


def test_a_unit_the_higher_source_leaves_alone_is_its_decision(
    instructions: Instructions, kjv_text: Mapping[str, str]
) -> None:
    # Rev 13:16: Pierpont changes only "a mark"; Additional's group also covers
    # the verb, but does not take the construction from Pierpont.
    # Test source precedence independently of the editorial override.
    rows = [
        copy.deepcopy(instructions[(PIERPONT, 817)]),
        additional_instruction(
            kjv_text,
            "REV 13:16",
            "to receive",
            "that they should give",
            ["REV 13:16#1"],
            entry=1,
        ),
        additional_instruction(
            kjv_text, "REV 13:16", "a mark", "marks", ["REV 13:16#2"], entry=2
        ),
    ]
    for row in rows:
        row["compatibility"], row["compatibility_reason"] = "compatible", None
    constructions(rows, kjv_text)
    assert rows[0]["compatibility"] == "compatible"
    assert rows[1]["compatibility"] == "superseded"
    selected = select(rows, "REV 13:16#2", kjv_text)[0]
    assert selected is not None and selected["source"] == PIERPONT
    assert select(rows, "REV 13:16#1", kjv_text)[0] is None


def test_a_row_that_does_not_bind_blocks_its_group(
    instructions: Instructions,
) -> None:
    # Rev 6:11: Pierpont 715 is about the same unit as 714 but does not bind.
    assert instructions[(PIERPONT, 715)]["compatibility"] == "unbound"
    assert instructions[(PIERPONT, 714)]["compatibility"] == "blocked"


def test_an_instruction_across_verses_is_blocked_whole_by_an_override(
    instructions: Instructions,
) -> None:
    row = instructions[(PIERPONT, 332)]  # Acts 9:5-6
    assert row["compatibility"] == "blocked" and row["displaced_by"] == [
        "ACT 9:5#1+ACT 9:6#1"
    ]


def test_an_override_may_set_supplied_words_in_roman(
    byzantine: Mapping[str, Any], prepared_verses: dict[str, Verse]
) -> None:
    document: usj.Document = byzantine["prepared"]["JHN"]
    verse = prepared_verses["JHN 19:17"]
    content = [
        item
        for block, lo, hi, _ in verse.parts
        for item in document["content"][block]["content"][lo:hi]
    ]

    def supplied(items: Iterable[str | usj.Node]) -> list[str]:
        return [
            usj.text_of(n.get("content", []))
            for n in usj.walk(items)
            if n.get("marker") == "add"
        ]

    text = [i for i in content if isinstance(i, str) or not usj.is_note(i)]
    assert "the place" not in supplied(text)  # roman in the text
    # italic in the note's KJV alternative
    assert "the place" in supplied(usj.notes_of(content))


def test_edits_print_the_curly_apostrophe(
    prepared_text: Callable[[str], str],
) -> None:
    assert "brother’s" in prepared_text("LUK 3:19")
    assert "'" not in prepared_text("LUK 3:19")
    assert "Lamb’s" in prepared_text("REV 21:9")


def test_every_note_in_the_edition_restores_the_kjv(
    byzantine: Mapping[str, Any],
) -> None:
    finished: dict[str, list[str]] = byzantine["finished"]
    assert not [ps for ps in finished.values() if any("restore" in p for p in ps)]


def delete_sealed(ref: str, unit: str, at: int = 0) -> InstructionEdit:
    return {
        "ref": ref,
        "kind": "delete",
        "word_range": [at, at + 1],
        "old": "sealed",
        "new": "",
        "bind": "unique",
        "units": [unit],
    }


def witness(
    source: str,
    entry: int,
    ref: str,
    units: Iterable[str],
    edits: Iterable[InstructionEdit] = (),
    status: str = "compatible",
) -> Instruction:
    return {
        "source": source,
        "entry": entry,
        "ref": ref,
        "units": [{"unit": u} for u in units],
        "edits": list(edits),
        "compatibility": status,
    }


def test_failed_higher_source_requires_complete_lower_source_coverage() -> None:
    ref = "REV 7:6"
    first, second = ref + "#1", ref + "#2"
    failed = witness(PIERPONT, 1, ref, [first, second], status="unbound")
    replacement = witness(ADDITIONAL, 2, ref, [first], [delete_sealed(ref, first)])
    kjv = {ref: "sealed twelve thousand sealed"}
    partial = constructions([copy.deepcopy(failed), copy.deepcopy(replacement)], kjv)
    assert select(partial, first, kjv)[0] is None
    assert partial[1]["compatibility"] == "blocked"

    # The identical failure allows a lower source that owns both units.
    complete = copy.deepcopy(replacement)
    complete["units"].append({"unit": second})
    complete["edits"].append(delete_sealed(ref, second, 3))
    whole = constructions([copy.deepcopy(failed), complete], kjv)
    assert all(select(whole, uid, kjv)[0] is not None for uid in (first, second))


@pytest.mark.parametrize("partially_bound", [False, True])
def test_a_failure_across_verses_requires_lower_source_coverage_of_both(
    partially_bound: bool,
) -> None:
    # Pierpont's row spans Rev 7:6-7 and fails, whether or not one of its
    # edits bound; Additional's row for 7:7 alone does not replace it in part.
    first, second = "REV 7:6", "REV 7:7"
    a, b = first + "#1", second + "#1"
    failed = witness(
        PIERPONT,
        1,
        first,
        [a, b],
        [delete_sealed(first, a)] if partially_bound else [],
        "unbound",
    )
    lower = witness(ADDITIONAL, 2, second, [b], [delete_sealed(second, b)])
    kjv = {first: "sealed twelve thousand", second: "sealed twelve thousand"}
    partial = constructions([copy.deepcopy(failed), copy.deepcopy(lower)], kjv)
    assert select(partial, b, kjv)[0] is None
    assert partial[0]["construction"] == partial[1]["construction"]

    # One lower row covering both verses executes.
    lower["units"].append({"unit": a})
    lower["edits"].append(delete_sealed(first, a))
    complete = constructions([copy.deepcopy(failed), lower], kjv)
    assert all(select(complete, uid, kjv)[0] is not None for uid in (a, b))


def test_a_lower_sources_failure_does_not_block_the_higher_source() -> None:
    ref = "REV 7:6"
    a, b, c = ref + "#1", ref + "#2", ref + "#3"
    partial = witness(PIERPONT, 1, ref, [a], [delete_sealed(ref, a)])
    failed = witness(PIERPONT, 2, ref, [b], status="unbound")
    complete = witness(
        ADDITIONAL, 3, ref, [a, b], [delete_sealed(ref, a), delete_sealed(ref, b, 3)]
    )
    lower = witness(ADDITIONAL, 4, ref, [b, c], status="unbound")
    kjv = {ref: "sealed twelve thousand sealed twelve thousand"}
    rows = constructions(
        [copy.deepcopy(r) for r in (partial, failed, complete, lower)], kjv
    )
    assert len({r["construction"] for r in rows}) == 1
    # Neither source covers everything it owes. No source above Pierpont
    # failed, so Pierpont executes at a as it would without the additional
    # source; the additional source's failure at b and c does not block it.
    selected = select(rows, a, kjv)[0]
    assert selected is not None and selected["source"] == PIERPONT
    assert all(select(rows, uid, kjv)[0] is None for uid in (b, c))


def test_unbound_cross_verse_row_blocks_members_in_its_secondary_verse() -> None:
    first, second = "ACT 9:5#1", "ACT 9:6#1"
    failed = witness(PIERPONT, 1, "ACT 9:5", [first, second], status="unbound")
    failed["refs"] = ["ACT 9:5", "ACT 9:6"]
    trembling: InstructionEdit = {
        "ref": "ACT 9:6",
        "kind": "delete",
        "word_range": [0, 1],
        "old": "trembling",
        "new": "",
        "bind": "unique",
        "units": [second],
    }
    bound = witness(PIERPONT, 2, "ACT 9:6", [second], [trembling])
    kjv = {"ACT 9:5": "Lord", "ACT 9:6": "trembling"}
    unlisted = copy.deepcopy(failed)
    unlisted.pop("refs")
    rows = constructions([copy.deepcopy(failed), copy.deepcopy(bound)], kjv)
    assert rows[0]["group"] == rows[1]["group"]
    assert rows[1]["compatibility"] == "blocked"

    # Units in two verses group the row even without its own list of refs.
    rows = constructions([unlisted, copy.deepcopy(bound)], kjv)
    assert rows[1]["compatibility"] == "blocked"
    assert select(rows, second)[0] is None


def test_one_row_overlapping_itself_is_not_a_conflict_between_instructions(
    instructions: Instructions, kjv_text: Mapping[str, str]
) -> None:
    # Its overlap is the executor's to refuse; no second instruction disagrees.
    marks = copy.deepcopy(instructions[(PIERPONT, 817)])
    first = next(
        e for e in marks["edits"] if e["word_range"][1] - e["word_range"][0] > 1
    )
    inside = first["word_range"][0] + 1
    marks["edits"].append(
        {
            **first,
            "kind": "insert",
            "old": "",
            "new": "lo",
            "word_range": [inside, inside],
        }
    )
    grouped = constructions([marks], kjv_text)
    uid = next(a["unit"] for a in marks["units"])
    assert (
        select(grouped, uid, kjv_text)[2]
        != "conflicting pierpont instructions in the construction"
    )
