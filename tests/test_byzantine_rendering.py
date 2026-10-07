"""The rendering check: an instruction's English must render RP2026's reading.

Two confirmed failures of attachment alone, now refused, and their correct
neighbours, which still execute.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from test_byzantine_instructions import additional_instruction

from bible.byzantine import PIERPONT
from bible.byzantine.instructions import compatibility, same_content
from bible.byzantine.rendering import Checker, content, stems
from bible.byzantine.rows import Disposition, Instruction, InstructionEdit, Unit

Instructions = dict[tuple[str, int | str], Instruction]


@pytest.fixture(scope="module")
def checker(byzantine: Mapping[str, Any]) -> Checker:
    found: Checker = byzantine["checker"]
    return found


def test_rev_4_8_six_more_holy_render_nothing_rp_adds(
    checker: Checker,
    kjv_text: Mapping[str, str],
    dispositions: dict[str, Disposition],
) -> None:
    row = additional_instruction(
        kjv_text,
        "REV 4:8",
        "",
        ", ".join(["holy"] * 6),
        ["REV 4:8#1"],
        kind="insert",
        anchor="holy",
        occurrence=3,
        side="after",
    )
    # The instruction concerns an HF expansion absent from RP2026, rather
    # than this unit's added article. Even if misattached, it must be refused.
    verdict, reason = checker.check(row["edits"][0], ["REV 4:8#1"])
    assert verdict == "contradicted" and "9 'holy' for 3" in (reason or "")
    # RP adds only the article
    assert dispositions["REV 4:8#1"]["disposition"] == "silent"


def test_rev_7_5_judah_keeps_sealed_but_reuben_and_gad_lose_it(
    instructions: Instructions, dispositions: dict[str, Disposition]
) -> None:
    judah = instructions[(PIERPONT, 726)]
    assert judah["compatibility"] == "incompatible"
    assert "G4972" in (judah["compatibility_reason"] or "")
    assert dispositions["REV 7:5#1"]["disposition"] == "silent"
    for entry, unit in ((727, "REV 7:5#2"), (728, "REV 7:5#3")):
        assert instructions[(PIERPONT, entry)]["compatibility"] == "compatible"
        assert dispositions[unit]["disposition"] == "witnessed"


@pytest.mark.parametrize(
    "entry, unit",
    [(5, "MAT 3:8#1"), (6, "MAT 3:11#1"), (7, "MAT 4:10#1"), (131, "LUK 3:19#1")],
)
def test_ordinary_instructions_are_verified(
    instructions: Instructions,
    dispositions: dict[str, Disposition],
    entry: int,
    unit: str,
) -> None:
    row = instructions[(PIERPONT, entry)]
    assert (row["compatibility"], row["rendering"]) == ("compatible", "verified")
    assert "ev:lexically-supported" in dispositions[unit]["tags"]


def test_every_executed_instruction_has_a_rendering_verdict(
    dispositions: dict[str, Disposition],
) -> None:
    witnessed = [
        r
        for r in dispositions.values()
        if r["disposition"] == "witnessed" and r["action"] == "edit"
    ]
    assert witnessed
    assert all(
        {"ev:lexically-supported", "ev:lexically-unresolved"} & set(r["tags"])
        for r in witnessed
    )


def test_function_words_and_stems() -> None:
    assert content("and [it is] the holy place of God") == ["holy", "place", "god"]
    assert {"seal", "sealed"} <= stems("sealed") and "seal" in stems("sealeth")


def test_omission_cannot_extend_into_retained_neighbouring_greek(
    checker: Checker, instructions: Instructions
) -> None:
    edit = instructions[(PIERPONT, 6)]["edits"][0]
    assert checker.check(edit, edit["units"])[0] == "verified"
    # The Greek drops kai puri, but keeps agiw pneumati. Binding the larger
    # phrase does not give the fire omission authority over the Holy Ghost.
    broad: InstructionEdit = {
        **edit,
        "old": "the Holy Ghost, and with fire",
        "word_range": [31, 37],
    }
    verdict, reason = checker.check(broad, broad["units"])
    assert verdict == "contradicted" and "outside the attached unit" in (reason or "")


@pytest.mark.parametrize("entry", [69, 78, 622])
def test_added_greek_does_not_license_unlimited_english_repetitions(
    checker: Checker, instructions: Instructions, entry: int
) -> None:
    edit = instructions[(PIERPONT, entry)]["edits"][0]
    assert checker.check(edit, edit["units"])[0] == "verified"
    repeated: InstructionEdit = {
        **edit,
        "new": " ".join([edit["new"]] * (2 if entry == 69 else 12)),
    }
    verdict, reason = checker.check(repeated, repeated["units"])
    assert verdict == "contradicted" and "Greek word(s)" in (reason or "")


@pytest.mark.parametrize("entry", [103, 288])
def test_phrase_tags_do_not_make_omitted_now_a_retained_content_word(
    checker: Checker, instructions: Instructions, entry: int
) -> None:
    edit = instructions[(PIERPONT, entry)]["edits"][0]
    # CrossWire tags "Now" with retained Greek in both verses, though the
    # omitted oun renders it elsewhere in the KJV.
    assert checker.check(edit, edit["units"])[0] != "contradicted"


def test_a_number_change_does_not_add_a_lexical_occurrence(
    checker: Checker, instructions: Instructions
) -> None:
    edit = instructions[(PIERPONT, 787)]["edits"][0]
    # KJV supplies the second "kingdoms" in Rev 11:15; changing the first
    # from plural to singular adds no occurrence of the lemma.
    assert (edit["old"], edit["new"]) == ("kingdoms", "kingdom")
    assert checker.check(edit, edit["units"])[0] == "verified"


@pytest.mark.parametrize(
    "source, entry, ref",
    [
        (PIERPONT, 653, "REV 3:1"),
        (PIERPONT, 741, "REV 8:3"),
        (PIERPONT, 812, "REV 13:10"),
        (PIERPONT, 226, "JHN 6:39"),
    ],
)
def test_marginal_readings_are_refused(
    checker: Checker, instructions: Instructions, source: str, entry: int, ref: str
) -> None:
    row = instructions[(source, entry)]
    assert row["ref"] == ref
    verdict, reason = checker.check(row["edits"][0], row["edits"][0].get("units") or [])
    assert verdict == "contradicted" and "marginal" in (reason or "")


def test_a_margin_spanning_the_difference_is_not_refused(
    instructions: Instructions,
) -> None:
    # ACT 21:8 we -> they, RP's main hlqon
    assert instructions[(PIERPONT, 388)]["compatibility"] == "compatible"


def test_order_units_admit_only_reorderings(
    byzantine: Mapping[str, Any],
    by_id: dict[str, Unit],
    kjv_text: Mapping[str, str],
    instructions: Instructions,
    dispositions: dict[str, Disposition],
) -> None:
    supplied = byzantine["supplied"]
    # A pure Greek reordering preserves the KJV's "thunderings"; an explicit
    # additional transposition is compatible after Pierpont's rerendering
    # fails.
    assert instructions[(PIERPONT, 673)]["compatibility"] == "incompatible"
    assert "content words" in (
        instructions[(PIERPONT, 673)]["compatibility_reason"] or ""
    )
    row = additional_instruction(
        kjv_text,
        "REV 4:5",
        "thunderings and voices",
        "voices and thunderings",
        ["REV 4:5#1"],
        kind="transpose",
    )
    assert compatibility(row, by_id, kjv_text, supplied)[0] == "compatible"
    assert dispositions["REV 4:5#1"]["disposition"] == "override"
    # Rev 22:8 only reorders content words, adjusting grammar around them.
    assert instructions[(PIERPONT, 949)]["compatibility"] == "compatible"
    # 1 Pet 2:12 "shall behold" -> "have beheld" changes a word on an order unit.
    row = instructions[(PIERPONT, 580)].copy()
    row["edits"] = [
        {**e, "units": ["1PE 2:12#1"], "method": "sole"} for e in row["edits"]
    ]
    row["units"], row["scope"], row["role"], row["bind"] = (
        [{"unit": "1PE 2:12#1"}],
        "greek",
        "instruction",
        "unique",
    )
    status, reason = compatibility(row, by_id, kjv_text, supplied)
    assert status == "incompatible" and "reorders" in (reason or "")


@pytest.mark.parametrize("kind", ["replace", "transpose"])
def test_reordering_cannot_rerender_content_even_as_a_transposition(
    byzantine: Mapping[str, Any],
    by_id: dict[str, Unit],
    kjv_text: Mapping[str, str],
    kind: str,
) -> None:
    row = additional_instruction(
        kjv_text,
        "REV 4:5",
        "thunderings and voices",
        "voices and thunderings",
        ["REV 4:5#1"],
        kind="transpose",
    )
    row["edits"] = [{**row["edits"][0], "kind": kind, "new": "voices and thunders"}]
    status, reason = compatibility(row, by_id, kjv_text, byzantine["supplied"])
    assert status == "incompatible" and "content words" in (reason or "")


def test_reordering_preserves_content_forms_and_multiplicity() -> None:
    assert same_content(
        "saw these things, and heard them", "heard and saw these things"
    )
    assert same_content("[Holy] place, and God", "God and holy place")
    assert not same_content("thunderings and voices", "voices and thunders")
    assert not same_content("words and truth", "truth and word")
    assert not same_content("holy, holy", "holy")
    assert not same_content("holy", "[holy] place")


@pytest.mark.parametrize("entry", [593, 864])
def test_transpositions_across_substitution_units_preserve_content(
    byzantine: Mapping[str, Any],
    by_id: dict[str, Unit],
    kjv_text: Mapping[str, str],
    instructions: Instructions,
    entry: int,
) -> None:
    supplied = byzantine["supplied"]
    row = instructions[(PIERPONT, entry)].copy()
    assert len(row["edits"][0]["units"]) == 2
    assert compatibility(row, by_id, kjv_text, supplied)[0] == "compatible"
    row["edits"] = [{**row["edits"][0], "new": row["edits"][0]["new"] + " words"}]
    assert compatibility(row, by_id, kjv_text, supplied)[0] == "incompatible"
