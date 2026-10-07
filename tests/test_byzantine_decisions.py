"""The editor's decisions about the New Testament: the readings validated
against the pinned sources, the placements made by hand where code cannot
tell, the note lemmas, and the build stopping on a decision gone stale."""

from __future__ import annotations

import copy
import re
from collections.abc import Callable, Mapping
from typing import Any

import pytest

import bible.pipeline
from bible.byzantine import (
    ADDITIONAL,
    BOYD_ASV,
    FAA,
    PIERPONT,
    RV,
    checked,
    decide,
    decisions,
    verify,
)
from bible.byzantine.rows import (
    FaaRow,
    Instruction,
    Override,
    Placement,
    Report,
    Unit,
)
from bible.checks import CheckFailed

type Entry = dict[str, Any]
type Validate = Callable[[list[Entry]], tuple[list[Override], list[str]]]


@pytest.fixture(scope="module")
def readings(byzantine: Mapping[str, Any]) -> list[Entry]:
    """The readings of edition/byzantine.json, each with its key as its id."""
    return [
        {"id": key, **entry}
        for key, entry in byzantine["decisions"]["readings"].items()
    ]


@pytest.fixture(scope="module")
def placements(byzantine: Mapping[str, Any]) -> list[Placement]:
    """The placements of edition/byzantine-placements.json, as rows."""
    found: list[Placement] = byzantine["placements"]
    return found


@pytest.fixture(scope="module")
def reports(byzantine: Mapping[str, Any]) -> list[Report]:
    found: list[Report] = byzantine["reports"]
    return found


@pytest.fixture(scope="module")
def ledger(byzantine: Mapping[str, Any]) -> list[Unit]:
    found: list[Unit] = byzantine["units"]
    return found


@pytest.fixture(scope="module")
def lemmas(byzantine: Mapping[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = byzantine["note_lemmas"]
    return found


def arguments(byzantine: Mapping[str, Any]) -> tuple[Any, ...]:
    """What validate_overrides reads besides the entries, in order."""
    return (
        byzantine["units"],
        byzantine["kjv"],
        byzantine["witness_rows"],
        byzantine["texts"],
        byzantine["supplied"],
    )


@pytest.fixture(scope="module")
def validate(byzantine: Mapping[str, Any]) -> Validate:
    def run(entries: list[Entry]) -> tuple[list[Override], list[str]]:
        return decisions.validate_overrides(
            entries,
            *arguments(byzantine),
            revision_citations=byzantine["revision_citations"],
            faa_rows=byzantine["faa_rows"],
        )

    return run


@pytest.fixture(scope="module")
def sample(readings: list[Entry]) -> Callable[[], Entry]:
    """A real reading with an edit and both kinds of evidence (a witness row
    and a revision verse), copied so a test may spoil it."""
    entry = next(
        o
        for o in readings
        if o["kind"] == "edit"
        and any(w in o["evidence"] for w in (RV, BOYD_ASV))
        and any(w in o["evidence"] for w in (PIERPONT, "tcent", FAA))
    )
    return lambda: copy.deepcopy(entry)


# The real decisions


def test_the_real_decisions_validate_without_error(
    byzantine: Mapping[str, Any],
) -> None:
    assert byzantine["decision_errors"] == []
    assert byzantine["stale_placements"] == []


def test_the_real_readings_compile_one_entry_each(
    byzantine: Mapping[str, Any], readings: list[Entry]
) -> None:
    assert len(byzantine["overrides"]) == len(readings)
    for compiled, written in zip(byzantine["overrides"], readings):
        assert (
            compiled["id"]
            == written["id"]
            == decisions.override_id(compiled["unit_ids"])
        )
        assert len(compiled["bound"]) == len(written.get("edits", []))


def test_every_reading_edit_binds_to_the_pinned_kjv(
    byzantine: Mapping[str, Any], kjv_text: Mapping[str, str]
) -> None:
    for o in byzantine["overrides"]:
        for e in o["bound"]:
            assert kjv_text[e["ref"]][e["start"] : e["end"]] == e["old"]


def test_every_reading_tag_is_asserted_not_computed(readings: list[Entry]) -> None:
    for o in readings:
        groups = {t.split(":")[0] for t in o["tags"]}
        assert groups <= {"from", "gram"}, o["id"]
        assert "from" in groups and "gram" in groups, o["id"]


def test_every_reading_why_is_at_most_two_sentences(readings: list[Entry]) -> None:
    for o in readings:
        assert len(re.findall(r"[.!?](?:\s|$)", o["why"].strip())) <= 2, o["id"]


# Rejections


def test_the_sample_reading_validates_alone(
    validate: Validate, sample: Callable[[], Entry]
) -> None:
    compiled, errors = validate([sample()])
    assert errors == []
    assert len(compiled) == 1


def test_a_computed_tag_is_rejected(
    validate: Validate, sample: Callable[[], Entry]
) -> None:
    bad = sample()
    bad["tags"].append("op:omit")
    _, errors = validate([bad])
    assert len(errors) == 1 and "computed by the build" in errors[0]


def test_an_unknown_tag_is_rejected(
    validate: Validate, sample: Callable[[], Entry]
) -> None:
    bad = sample()
    bad["tags"].append("from:nowhere")
    _, errors = validate([bad])
    assert len(errors) == 1 and "malformed" in errors[0]


def test_from_must_occur_exactly_once(
    validate: Validate, sample: Callable[[], Entry], kjv_text: Mapping[str, str]
) -> None:
    bad = sample()
    ref = bad["edits"][0]["ref"]
    repeated = next(w for w in kjv_text[ref].split() if kjv_text[ref].count(w) > 1)
    bad["edits"][0]["from"] = repeated
    _, errors = validate([bad])
    assert len(errors) == 1 and "must occur exactly once" in errors[0]
    bad["edits"][0]["from"] = "words that are not in the verse"
    _, errors = validate([bad])
    assert "must occur exactly once" in errors[0] and "(0 found)" in errors[0]


def test_from_equal_to_to_is_rejected(
    validate: Validate, readings: list[Entry], byzantine: Mapping[str, Any]
) -> None:
    # Supplied words admit an equal-word edit that sets them in roman, so the
    # sample is a reading whose first edit touches none.
    overrides: list[Override] = byzantine["overrides"]
    entry = next(
        o
        for o in overrides
        if o["bound"]
        and o["bound"][0]["old"]
        and not any(
            a < o["bound"][0]["end"] and o["bound"][0]["start"] < b
            for a, b, _ in byzantine["supplied"].get(o["bound"][0]["ref"], [])
        )
    )
    bad = copy.deepcopy(next(o for o in readings if o["id"] == entry["id"]))
    bad["edits"][0]["to"] = bad["edits"][0]["from"]
    _, errors = validate([bad])
    assert len(errors) == 1 and "from equals to" in errors[0]


def test_a_fragment_cutting_through_a_word_is_rejected(
    validate: Validate, sample: Callable[[], Entry], kjv_text: Mapping[str, str]
) -> None:
    bad = sample()
    edit = bad["edits"][0]
    assert edit["from"] in kjv_text[edit["ref"]]
    # Drop the first letter of the fragment: it now starts inside a word.
    if not (edit["from"][0].isalpha() and edit["from"][1].isalpha()):
        pytest.skip("the sample fragment does not start with two letters")
    edit["from"] = edit["from"][1:]
    _, errors = validate([bad])
    assert errors and (
        "cuts through a word" in errors[0] or "must occur exactly once" in errors[0]
    )


def test_a_revision_quote_not_in_the_verse_is_rejected(
    validate: Validate, sample: Callable[[], Entry]
) -> None:
    bad = sample()
    witness = next(w for w in bad["evidence"] if w in (RV, BOYD_ASV))
    bad["evidence"][witness]["quote"] = "words the revision does not have here"
    _, errors = validate([bad])
    assert len(errors) == 1 and "quote is not in the verse once" in errors[0]


def test_a_witness_quote_not_in_the_entry_is_rejected(
    validate: Validate, sample: Callable[[], Entry]
) -> None:
    bad = sample()
    witness = next(w for w in bad["evidence"] if w in (PIERPONT, "tcent", FAA))
    bad["evidence"][witness]["quote"] = "words the entry does not contain"
    _, errors = validate([bad])
    assert len(errors) == 1 and "does not contain the quote" in errors[0]


def test_an_unknown_witness_is_rejected(
    validate: Validate, sample: Callable[[], Entry]
) -> None:
    bad = sample()
    bad["evidence"]["esv"] = {"ref": bad["edits"][0]["ref"], "quote": "anything"}
    _, errors = validate([bad])
    assert len(errors) == 1 and "unknown witness" in errors[0]


@pytest.mark.parametrize("kind", ["edit", "nochange"])
def test_every_editorial_ruling_requires_evidence(
    validate: Validate, sample: Callable[[], Entry], kind: str
) -> None:
    bad = sample()
    bad["kind"] = kind
    if kind == "nochange":
        bad["edits"] = []
    bad["evidence"] = {}
    compiled, errors = validate([bad])
    assert not compiled
    assert len(errors) == 1 and "evidence required" in errors[0]


def test_a_duplicate_unit_is_rejected(
    validate: Validate, sample: Callable[[], Entry]
) -> None:
    compiled, errors = validate([sample(), sample()])
    assert len(compiled) == 1
    assert len(errors) == 1 and "missing or duplicate unit" in errors[0]


def test_a_wrong_id_is_rejected(
    validate: Validate, sample: Callable[[], Entry]
) -> None:
    bad = sample()
    bad["id"] = "MAT 1:1#1"
    _, errors = validate([bad])
    assert len(errors) == 1 and "id should be" in errors[0]


def test_an_unknown_edit_field_is_rejected(
    validate: Validate, sample: Callable[[], Entry]
) -> None:
    bad = sample()
    bad["edits"][0]["note"] = "Textus Receptus: ..."
    _, errors = validate([bad])
    assert len(errors) == 1 and "unknown edit fields ['note']" in errors[0]


def test_kind_and_edits_must_agree(
    validate: Validate, sample: Callable[[], Entry]
) -> None:
    bad = sample()
    bad["kind"] = "nochange"
    _, errors = validate([bad])
    assert len(errors) == 1 and "kind edit needs edits, nochange has none" in errors[0]
    bad = sample()
    bad["edits"] = []
    _, errors = validate([bad])
    assert len(errors) == 1 and "kind edit needs edits" in errors[0]


def test_why_is_required_and_short(
    validate: Validate, sample: Callable[[], Entry]
) -> None:
    bad = sample()
    bad["why"] = "  "
    _, errors = validate([bad])
    assert len(errors) == 1 and "why required" in errors[0]
    bad = sample()
    bad["why"] = "One. Two. Three."
    _, errors = validate([bad])
    assert len(errors) == 1 and "at most two sentences" in errors[0]


def test_a_reading_is_a_fragment_not_the_verse(
    validate: Validate, sample: Callable[[], Entry], kjv_text: Mapping[str, str]
) -> None:
    bad = sample()
    edit = bad["edits"][0]
    edit["from"] = kjv_text[edit["ref"]]
    edit["to"] = "Something else."
    _, errors = validate([bad])
    assert len(errors) == 1 and "a fragment, not the verse" in errors[0]


def test_a_greek_key_naming_no_unit_is_rejected(
    validate: Validate, sample: Callable[[], Entry]
) -> None:
    bad = sample()
    bad["units"][0]["tr"] = "absent"
    _, errors = validate([bad])
    assert len(errors) == 1 and "names 0 units" in errors[0]


def test_an_insertion_needs_one_anchor(
    validate: Validate, sample: Callable[[], Entry], kjv_text: Mapping[str, str]
) -> None:
    bad = sample()
    edit = bad["edits"][0]
    first = kjv_text[edit["ref"]].split()[0]
    bad["edits"] = [
        {
            "ref": edit["ref"],
            "from": "",
            "to": "verily",
            "after": first,
            "before": first,
        }
    ]
    _, errors = validate([bad])
    assert (
        len(errors) == 1
        and "an insertion needs to and one of after/before" in errors[0]
    )


def test_overlapping_edits_in_one_reading_are_rejected(
    validate: Validate, sample: Callable[[], Entry]
) -> None:
    bad = sample()
    bad["edits"] = [bad["edits"][0], copy.deepcopy(bad["edits"][0])]
    compiled, errors = validate([bad])
    assert compiled == []
    assert len(errors) == 1 and "overlaps another edit" in errors[0]


@pytest.mark.parametrize("sole_evidence", [False, True])
def test_unloaded_additional_evidence_is_rejected(
    validate: Validate, sample: Callable[[], Entry], sole_evidence: bool
) -> None:
    bad = sample()
    citation = {"entry": 1, "quote": "Explicit additional fixture"}
    bad["evidence"] = (
        {ADDITIONAL: citation}
        if sole_evidence
        else {**bad["evidence"], ADDITIONAL: citation}
    )
    compiled, errors = validate([bad])
    assert not compiled
    assert len(errors) == 1 and "additional is not loaded" in errors[0]


def test_loaded_additional_evidence_is_checked(
    byzantine: Mapping[str, Any], sample: Callable[[], Entry]
) -> None:
    entry = sample()
    entry["evidence"] = {
        ADDITIONAL: {"entry": 1, "quote": "Explicit additional fixture"}
    }
    witness_rows = {
        **byzantine["witness_rows"],
        ADDITIONAL: {
            1: {"ref": entry["units"][0]["ref"], "raw": "Explicit additional fixture"}
        },
    }
    units, kjv, _, texts, supplied = arguments(byzantine)
    compiled, errors = decisions.validate_overrides(
        [entry], units, kjv, witness_rows, texts, supplied
    )
    assert len(compiled) == 1 and not errors
    entry["evidence"][ADDITIONAL]["quote"] = "Not in the fixture"
    compiled, errors = decisions.validate_overrides(
        [entry], units, kjv, witness_rows, texts, supplied
    )
    assert (
        not compiled and len(errors) == 1 and "does not contain the quote" in errors[0]
    )


# Revision and Far Above All citations


def citation_entry(readings: list[Entry], uid: str, witness: str, quote: str) -> Entry:
    entry = copy.deepcopy(next(o for o in readings if o["id"] == uid))
    entry["evidence"] = {witness: {"ref": entry["units"][0]["ref"], "quote": quote}}
    return entry


def nochange(unit: Unit, witness: str, quote: str) -> Entry:
    """A reading keeping the KJV at a unit, citing a revision's words."""
    ref = unit["ref"]
    return {
        "id": unit["id"],
        "units": [{"ref": ref, "tr": " ".join(unit["tr"]), "rp": " ".join(unit["rp"])}],
        "kind": "nochange",
        "tags": ["from:kjv-retained", "gram:supplied-word"],
        "why": "Citation fixture.",
        "evidence": {witness: {"ref": ref, "quote": quote}},
    }


@pytest.mark.parametrize("witness", [RV, "asv", BOYD_ASV])
def test_real_revision_supplied_citations(
    validate: Validate, byzantine: Mapping[str, Any], witness: str
) -> None:
    # Each reader's real spans are tested against a permitted Greek unit.
    by_ref = {u["ref"]: u for u in byzantine["units"]}
    ref, metadata = next(
        (ref, row)
        for ref, row in byzantine["revision_citations"][witness].items()
        if row and row["supplied"] and ref in by_ref
    )
    lo, hi = metadata["supplied"][0]
    entry = nochange(by_ref[ref], witness, "[" + metadata["text"][lo:hi] + "]")
    assert validate([entry])[1] == []
    # A plain full verse remains valid even with supplied words.
    entry["evidence"][witness]["quote"] = metadata["text"]
    assert validate([entry])[1] == []


@pytest.mark.parametrize(
    "witness,ref,quote",
    [
        # The RV's markup holds the next space.
        (RV, "MAT 3:11", "Holy Ghost and [with] fire"),
        # The source's own bracket, quoted verbatim.
        (RV, "JHN 8:11", "sin no more.]"),
        ("asv", "JHN 8:11", "from henceforth sin no more.]"),
    ],
)
def test_revision_citations_in_the_sources_own_words(
    validate: Validate,
    ledger: list[Unit],
    witness: str,
    ref: str,
    quote: str,
) -> None:
    unit = next(u for u in ledger if u["ref"] == ref)
    assert validate([nochange(unit, witness, quote)])[1] == []


@pytest.mark.parametrize(
    "quote",
    [
        "to sit on my right hand and on [my] left hand",
        "on [my] left hand",
        "and on [m]",
        "[y] left hand",
        "to  sit\n on my right hand and on [my] left hand",
    ],
)
def test_boyd_mark_citation_boundaries_and_whitespace(
    validate: Validate, readings: list[Entry], quote: str
) -> None:
    entry = citation_entry(readings, "MRK 10:40#1", BOYD_ASV, quote)
    assert validate([entry])[1] == []


@pytest.mark.parametrize(
    "quote",
    [
        "to sit on [my] right hand and on my left hand",
        "to sit on [my] right hand and on [my] left hand",
        "on [my] left hand is not mine to give; but it is for them",
        "on [[my]] left hand",
        "on [my left hand",
        "on my] left hand",
        "on []my left hand",
        "on [ ]my left hand",
    ],
)
def test_boyd_mark_bad_brackets(
    validate: Validate, readings: list[Entry], quote: str
) -> None:
    entry = citation_entry(readings, "MRK 10:40#1", BOYD_ASV, quote)
    compiled, errors = validate([entry])
    assert not compiled and len(errors) == 1


@pytest.mark.parametrize(
    "uid,quote",
    [
        ("REV 9:11#2", "They have as king over them [the] angel of the abyss"),
        ("REV 11:9#3", "three days [and] a half"),
    ],
)
def test_boyd_roman_words_cannot_be_bracketed(
    validate: Validate, readings: list[Entry], uid: str, quote: str
) -> None:
    compiled, errors = validate([citation_entry(readings, uid, BOYD_ASV, quote)])
    assert not compiled and "brackets differ" in errors[0]


def faa_entry(readings: list[Entry]) -> Entry:
    """The reading at Acts 28:11, citing only Far Above All's verse note."""
    entry = copy.deepcopy(next(o for o in readings if o["id"] == "ACT 28:11#1"))
    entry["evidence"] = {FAA: entry["evidence"][FAA]}
    return entry


def test_faa_real_acts_verse_note(validate: Validate, readings: list[Entry]) -> None:
    compiled, errors = validate([faa_entry(readings)])
    assert len(compiled) == 1 and not errors


@pytest.mark.parametrize(
    "change",
    [
        {"ref": "ACT 28:10"},
        {"ref": "ACT 28:999"},
        {"quote": "ἤχθημεν, we sailed"},
        {"field": "raw_English"},
        {"entry": "ACT 28:11#1"},
        {"extra": "unknown"},
        {"ref": None},
        {"field": None},
    ],
)
def test_faa_note_faults_rejected(
    validate: Validate, readings: list[Entry], change: dict[str, Any]
) -> None:
    entry = faa_entry(readings)
    entry["evidence"][FAA] = {**entry["evidence"][FAA], **change}
    compiled, errors = validate([entry])
    assert not compiled and len(errors) == 1


@pytest.mark.parametrize("field", ["ref", "field"])
def test_faa_note_requires_reference_and_field(
    validate: Validate, readings: list[Entry], field: str
) -> None:
    entry = faa_entry(readings)
    del entry["evidence"][FAA][field]
    assert validate([entry])[1]


def test_bracketed_citation_requires_metadata_and_a_unique_occurrence(
    byzantine: Mapping[str, Any], readings: list[Entry], validate: Validate
) -> None:
    entry = citation_entry(readings, "MRK 10:40#1", BOYD_ASV, "on [my] left hand")
    args = arguments(byzantine)
    assert "metadata missing" in decisions.validate_overrides([entry], *args)[1][0]
    metadata = copy.deepcopy(byzantine["revision_citations"])
    metadata[BOYD_ASV]["MRK 10:40"]["text"] += " changed"
    assert (
        "metadata missing or stale"
        in decisions.validate_overrides([entry], *args, revision_citations=metadata)[1][
            0
        ]
    )
    entry["evidence"][BOYD_ASV]["quote"] = "[my]"
    assert "not in the verse once" in validate([entry])[1][0]
    # A plain citation needs no metadata.
    entry["evidence"][BOYD_ASV]["quote"] = "on my left hand"
    assert decisions.validate_overrides([entry], *args)[1] == []


def test_faa_note_quote_is_verbatim_after_source_whitespace_normalization(
    byzantine: Mapping[str, Any], readings: list[Entry]
) -> None:
    entry = faa_entry(readings)
    rows: dict[str, FaaRow] = copy.deepcopy(dict(byzantine["faa_rows"]))
    rows["ACT 28:11"]["source_notes"] = rows["ACT 28:11"]["source_notes"].replace(
        "we were", "we\n  were"
    )
    args = arguments(byzantine)
    assert decisions.validate_overrides([entry], *args, faa_rows=rows)[1] == []
    entry["evidence"][FAA]["quote"] = "ἤχθημεν, we  were transported"
    assert (
        "does not contain"
        in decisions.validate_overrides([entry], *args, faa_rows=rows)[1][0]
    )


# Placements


def placed_row(rows: list[Report], row: Report) -> Report:
    return next(
        r for r in rows if r["witness"] == row["witness"] and r["entry"] == row["entry"]
    )


def test_the_real_placements_apply_to_the_reports_and_instructions(
    byzantine: Mapping[str, Any], placements: list[Placement]
) -> None:
    hand = [
        r
        for r in [*byzantine["reports"], *byzantine["instructions"]]
        if r.get("method") == "hand"
    ]
    assert len(hand) == len(placements)


def test_place_rejects_an_unknown_row(
    reports: list[Report], ledger: list[Unit], placements: list[Placement]
) -> None:
    bad: Placement = {**placements[0], "entry": "nonexistent#99"}
    _, errors, stale = decisions.place(reports, ledger, [bad])
    assert errors == [f"placement {bad['witness']}:{bad['entry']}: no such witness row"]
    assert stale == []


def test_place_rejects_a_missing_reason(
    reports: list[Report], ledger: list[Unit], placements: list[Placement]
) -> None:
    first = placements[0]
    _, errors, _ = decisions.place(reports, ledger, [{**first, "why": " "}])
    assert errors == [f"placement {first['witness']}:{first['entry']}: missing reason"]


def test_place_rejects_a_wrong_verse(
    reports: list[Report], ledger: list[Unit], placements: list[Placement]
) -> None:
    first = placements[0]
    _, errors, _ = decisions.place(reports, ledger, [{**first, "ref": "MAT 1:1"}])
    assert len(errors) == 1 and "the row is at" in errors[0]


def stale_placement(reports: list[Report], by_id: Mapping[str, Unit]) -> Placement:
    """A placement of a report where the code already places it."""
    row = next(
        r
        for r in reports
        if r.get("units")
        and r.get("method") not in {"hand", None}
        and len(r["units"]) == 1
    )
    unit = by_id[row["units"][0]["unit"]]
    return {
        "witness": row["witness"],
        "entry": row["entry"],
        "ref": row["ref"],
        "unit": {"tr": " ".join(unit["tr"]), "rp": " ".join(unit["rp"])},
        "why": "The code already places it.",
    }


def test_place_reports_a_stale_placement(
    reports: list[Report], ledger: list[Unit], by_id: Mapping[str, Unit]
) -> None:
    """A placement the code already makes on its own is stale, not applied twice."""
    decision = stale_placement(reports, by_id)
    placed, errors, stale = decisions.place(reports, ledger, [decision])
    assert errors == []
    assert stale == [decision]
    changed = next(
        r
        for r in placed
        if r["witness"] == decision["witness"] and r["entry"] == decision["entry"]
    )
    unit = by_id[next(a["unit"] for a in changed["units"])]
    assert changed["method"] == "hand" and changed["units"] == [
        {"unit": unit["id"], "scope": "constituent"}
    ]


def test_place_with_a_null_unit_takes_the_row_out_of_scope(
    reports: list[Report], ledger: list[Unit]
) -> None:
    row = next(r for r in reports if r.get("units"))
    decision: Placement = {
        "witness": row["witness"],
        "entry": row["entry"],
        "ref": row["ref"],
        "unit": None,
        "why": "Shared Greek.",
    }
    placed, errors, _ = decisions.place(reports, ledger, [decision])
    assert errors == []
    changed = placed_row(placed, row)
    assert (
        changed["units"] == []
        and changed["scope"] == "out-of-scope"
        and changed["reason"] == "Shared Greek."
    )


def test_place_leaves_the_input_instruction_edits_unchanged(
    byzantine: Mapping[str, Any], ledger: list[Unit]
) -> None:
    rows: list[Instruction] = byzantine["instructions"]
    row = copy.deepcopy(
        next(
            r
            for r in rows
            if r.get("edits") and any(e.get("bind") == "unique" for e in r["edits"])
        )
    )
    original = copy.deepcopy(row)
    decision: Placement = {
        "witness": row["source"],
        "entry": row["entry"],
        "ref": row["ref"] or "",
        "unit": None,
        "why": "Shared Greek.",
    }
    placed, errors, _ = decisions.place([row], ledger, [decision])
    assert errors == []
    assert placed[0]["scope"] == "out-of-scope"
    assert row == original


def test_cross_verse_placement_pairs_each_edit_with_its_own_verse() -> None:
    units: list[Unit] = [
        {
            "id": "ACT 9:5#1",
            "ref": "ACT 9:5",
            "tr": ["a"],
            "rp": ["b"],
            "tr_range": [0, 1],
        },
        {
            "id": "ACT 9:6#1",
            "ref": "ACT 9:6",
            "tr": ["c"],
            "rp": ["d"],
            "tr_range": [5, 6],
        },
    ]
    row: Instruction = {
        "source": ADDITIONAL,
        "entry": 1,
        "ref": "ACT 9:5",
        "refs": ["ACT 9:5", "ACT 9:6"],
        "edits": [
            {"ref": "ACT 9:5", "bind": "unique", "word_range": [10, 11]},
            {"ref": "ACT 9:6", "bind": "unique", "word_range": [0, 1]},
        ],
    }
    placement: Placement = {
        "witness": ADDITIONAL,
        "entry": 1,
        "ref": "ACT 9:5",
        "unit": [{"ref": u["ref"], "tr": u["tr"][0], "rp": u["rp"][0]} for u in units],
        "why": "The instruction spans both verses.",
    }
    placed, errors, _ = decisions.place([row], units, [placement])
    assert errors == []
    assert [e["units"] for e in placed[0]["edits"]] == [["ACT 9:5#1"], ["ACT 9:6#1"]]


# Note lemmas


def test_the_real_note_lemmas_validate(
    lemmas: list[dict[str, Any]], ledger: list[Unit]
) -> None:
    assert decisions.validate_lemmas(lemmas, ledger) == []
    assert lemmas


def test_validate_lemmas_names_each_fault(
    lemmas: list[dict[str, Any]], ledger: list[Unit]
) -> None:
    entries = [
        {"id": "MAT 0:0#1", "edit": 1, "lemma": "x", "why": "y"},
        {"id": lemmas[0]["id"], "edit": 0, "lemma": " ", "why": ""},
        {**lemmas[0]},
        {**lemmas[0]},
    ]
    errors = decisions.validate_lemmas(entries, ledger)
    assert any("no such unit" in e for e in errors)
    assert any("1-based index" in e for e in errors)
    assert any("lemma and why required" in e for e in errors)
    assert any(e.endswith("duplicate") for e in errors)


@pytest.mark.parametrize("field,value", [("why", 7), ("id", []), ("edit", [])])
def test_malformed_note_lemma_returns_errors_instead_of_crashing(
    lemmas: list[dict[str, Any]], ledger: list[Unit], field: str, value: object
) -> None:
    bad = {**lemmas[0], field: value}
    assert decisions.validate_lemmas([bad], ledger)


def test_lemma_entries_read_the_unit_and_the_note_from_the_key() -> None:
    rows = decisions.lemma_entries(
        {
            "1CO 15:39#1 TR": {"lemma": "one", "why": "a"},
            "1CO 15:39#1 TR#2": {"lemma": "two", "why": "b"},
        }
    )
    assert [(r["id"], r["edit"], r["lemma"]) for r in rows] == [
        ("1CO 15:39#1", 1, "one"),
        ("1CO 15:39#1", 2, "two"),
    ]
    with pytest.raises(ValueError, match="key is not a TR note's"):
        decisions.lemma_entries({"1CO 15:39#1 RP": {"lemma": "x", "why": "y"}})


# The build stops on a decision gone stale


def test_the_build_stops_on_a_stale_placement_a_redundant_reading_or_a_broken_invariant(
    edition: bible.pipeline.Edition, by_id: Mapping[str, Unit]
) -> None:
    context = edition.byzantine.context
    reports, ledger = context["reports"], context["units"]
    checked(context)
    # A placement the code now makes on its own.
    _, _, stale = decisions.place(reports, ledger, [stale_placement(reports, by_id)])
    with pytest.raises(CheckFailed, match="placements the code now makes"):
        checked({**context, "stale_placements": stale})
    # A reading that keeps the KJV where nothing would change it anyway.
    witnessed = {
        a["unit"]
        for rows in (reports, context["revision_rows"], context["instructions"])
        for row in rows
        for a in row.get("units", [])
    }
    quiet = next(
        u
        for u in ledger
        if u["id"] not in witnessed
        and not context["alarms"].get(u["id"], {}).get("alarm")
        and u["class"] != "structural"
    )
    reading: Override = {
        "id": quiet["id"],
        "unit_ids": [quiet["id"]],
        "kind": "nochange",
        "why": "Keep the KJV.",
        "evidence": {},
        "tag_set": [],
        "bound": [],
    }
    rows = decide.decide(
        [quiet],
        context["instructions"],
        reports,
        context["revision_rows"],
        [reading],
        context["alarms"],
        context["kjv"],
    )
    assert rows[0].get("redundant")
    with pytest.raises(
        CheckFailed, match=f"readings that change nothing.*{quiet['id']}"
    ):
        checked({**context, "dispositions": [*context["dispositions"], *rows]})
    # A unit the dispositions lose.
    invariants = verify.checks(
        context["documents"],
        context["prepared"],
        ledger,
        context["dispositions"][1:],
        context["structure"],
    )
    assert invariants["I1"] == "unit coverage differs"
    with pytest.raises(CheckFailed, match="invariants broken.*I1"):
        checked({**context, "invariants": invariants})
