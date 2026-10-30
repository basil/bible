"""The editor's decisions about the New Testament: the readings validated
against the pinned sources, the placements made by hand where code cannot
tell, the note lemmas, and the build stopping on a decision gone stale."""

from __future__ import annotations

import copy
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from functools import partial
from typing import Any

import pytest

import bible.pipeline
from bible import scripture, usj
from bible.byzantine import (
    ADDITIONAL,
    BOYD_ASV,
    FAA,
    PIERPONT,
    RV,
    decide,
    decisions,
    received,
    stages,
    verify,
)
from bible.byzantine.english import verses_of
from bible.byzantine.rows import (
    BoundEdit,
    Carrier,
    FaaRow,
    Instruction,
    Override,
    Placement,
    Report,
    Unit,
)
from bible.byzantine.stages import Reconciliation
from bible.byzantine.units import QUOTED
from bible.checks import CheckFailed

type Entry = dict[str, Any]
type Validate = Callable[[list[Entry]], tuple[list[Override], list[str]]]


@pytest.fixture(scope="module")
def readings(byzantine: Reconciliation) -> list[Entry]:
    """The readings of edition/byzantine.json, each with its key as its id."""
    return [
        {"id": key, **entry}
        for key, entry in byzantine.inputs.decisions["readings"].items()
    ]


@pytest.fixture(scope="module")
def placements(byzantine: Reconciliation) -> list[Placement]:
    """The placements of edition/byzantine-placements.json, as rows."""
    return list(byzantine.inputs.placements)


@pytest.fixture(scope="module")
def reports(byzantine: Reconciliation) -> list[Report]:
    return list(byzantine.apparatuses.reports)


@pytest.fixture(scope="module")
def ledger(byzantine: Reconciliation) -> list[Unit]:
    return list(byzantine.greek.units)


@pytest.fixture(scope="module")
def lemmas(byzantine: Reconciliation) -> list[dict[str, Any]]:
    return list(byzantine.decisions.lemmas)


def arguments(byzantine: Reconciliation) -> tuple[Any, ...]:
    """What validate_overrides reads besides the entries, in order."""
    return (
        byzantine.greek.units,
        byzantine.english.kjv,
        decisions.witness_rows(
            byzantine.apparatuses.reports, byzantine.instructions.rows
        ),
        byzantine.english.texts,
        byzantine.english.supplied,
    )


@pytest.fixture(scope="module")
def validate(byzantine: Reconciliation) -> Validate:
    def run(entries: list[Entry]) -> tuple[list[Override], list[str]]:
        return decisions.validate_overrides(
            entries,
            *arguments(byzantine),
            revision_citations=byzantine.english.revision_citations,
            faa_rows=byzantine.apparatuses.faa_rows,
            printed=byzantine.greek.printed,
            alignment=byzantine.greek.rp_alignment,
            structure=byzantine.greek.structure,
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


def test_the_real_readings_compile_one_entry_each(
    byzantine: Reconciliation, readings: list[Entry]
) -> None:
    # The readings written, then the corrections read from Pierpont.
    expanded = readings + decisions.instruction_entries(
        byzantine.decisions.instruction_decisions,
        byzantine.instructions.rows,
        byzantine.greek,
        byzantine.decisions.instruction_carriers,
        lambda label, evidence, refs: None,
    )
    assert len(byzantine.decisions.overrides) == len(expanded)
    for compiled, written in zip(byzantine.decisions.overrides, expanded, strict=True):
        assert compiled["id"] == written["id"]
        assert compiled["id"] == (
            decisions.override_id(compiled["unit_ids"])
            if compiled["unit_ids"]
            else compiled["bound"][0]["ref"]
        )
        assert len(compiled["bound"]) == len(
            written.get("edits") or written.get("instruction", {}).get("edits", [])
        )


def test_every_reading_edit_binds_to_the_pinned_kjv(
    byzantine: Reconciliation, kjv_text: Mapping[str, str]
) -> None:
    for o in byzantine.decisions.overrides:
        for e in o["bound"]:
            assert kjv_text[e["ref"]][e["start"] : e["end"]] == e["old"]


def test_readings_declare_wording_and_grammar_only_for_units(
    readings: list[Entry],
) -> None:
    for reading in readings:
        assert "tags" not in reading
        assert bool(reading.get("wording")) == bool(reading.get("units"))
        assert bool(reading.get("grammar")) == bool(reading.get("units"))


def test_every_reading_why_is_at_most_two_sentences(readings: list[Entry]) -> None:
    for o in readings:
        if "units" in o:
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
    bad["wording"].append("op:omit")
    _, errors = validate([bad])
    assert len(errors) == 1 and "malformed" in errors[0]


def test_an_unknown_tag_is_rejected(
    validate: Validate, sample: Callable[[], Entry]
) -> None:
    bad = sample()
    bad["grammar"].append("nowhere")
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
    validate: Validate, readings: list[Entry], byzantine: Reconciliation
) -> None:
    # Supplied words admit an equal-word edit that sets them in roman, so the
    # sample is a reading whose first edit touches none.
    overrides = byzantine.decisions.overrides
    entry = next(
        o
        for o in overrides
        if o["bound"]
        and o["bound"][0]["old"]
        and not any(
            a < o["bound"][0]["end"] and o["bound"][0]["start"] < b
            for a, b, _ in byzantine.english.supplied.get(o["bound"][0]["ref"], [])
        )
    )
    bad = copy.deepcopy(next(o for o in readings if o["id"] == entry["id"]))
    bad["edits"][0]["to"] = bad["edits"][0]["from"]
    _, errors = validate([bad])
    assert len(errors) == 1 and "from equals to" in errors[0]


def test_an_insertion_or_deletion_in_disguise_is_rejected(
    validate: Validate, readings: list[Entry]
) -> None:
    """Words added at either end of the King James words, or dropped from
    one end, are written as an insertion or a deletion, so that the note
    says what the TR omits or adds instead of quoting the kept words."""
    entry = next(
        o
        for o in readings
        if o.get("edits")
        and len(o["edits"][0]["from"].split()) > 1
        and o["edits"][0]["to"]
    )
    bad = copy.deepcopy(entry)
    bad["edits"][0]["to"] = bad["edits"][0]["from"] + " verily"
    _, errors = validate([bad])
    assert len(errors) == 1 and "an insertion in disguise" in errors[0]
    bad["edits"][0]["to"] = "Verily " + bad["edits"][0]["from"]
    _, errors = validate([bad])
    assert len(errors) == 1 and "an insertion in disguise" in errors[0]
    bad["edits"][0]["to"] = bad["edits"][0]["from"].split()[0]
    _, errors = validate([bad])
    assert len(errors) == 1 and "a deletion in disguise" in errors[0]
    # Words added inside the King James words are a replacement still.
    first, *rest = bad["edits"][0]["from"].split()
    bad["edits"][0]["to"] = " ".join([first, "verily", *rest])
    _, errors = validate([bad])
    assert not errors


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


def kjv_parallel(readings: list[Entry]) -> Entry:
    """A real reading that borrows the KJV's own rendering from elsewhere."""
    return copy.deepcopy(next(o for o in readings if "kjv" in o.get("evidence", {})))


def test_a_kjv_parallel_is_quoted_from_the_pinned_text(
    validate: Validate, readings: list[Entry]
) -> None:
    entry = kjv_parallel(readings)
    assert "kjv-parallel" in entry["wording"]
    compiled, errors = validate([entry])
    assert len(compiled) == 1 and not errors


def test_a_kjv_parallel_quote_not_in_the_verse_is_rejected(
    validate: Validate, readings: list[Entry]
) -> None:
    bad = kjv_parallel(readings)
    bad["evidence"]["kjv"]["quote"] = "words the King James verse does not have"
    _, errors = validate([bad])
    assert len(errors) == 1 and "kjv quote is not in the verse once" in errors[0]
    bad = kjv_parallel(readings)
    bad["evidence"]["kjv"]["ref"] = "MAT 99:99"
    _, errors = validate([bad])
    assert len(errors) == 1 and "is not a verse" in errors[0]


def test_a_kjv_parallel_marks_the_supplied_words(
    validate: Validate, readings: list[Entry]
) -> None:
    bad = next(
        copy.deepcopy(o)
        for o in readings
        if "[" in o.get("evidence", {}).get("kjv", {}).get("quote", "")
    )
    bad["evidence"]["kjv"]["quote"] = (
        bad["evidence"]["kjv"]["quote"].replace("[", "").replace("]", "")
    )
    _, errors = validate([bad])
    assert len(errors) == 1 and "brackets differ from the supplied words" in errors[0]


def test_a_kjv_parallel_is_not_the_edited_words(
    validate: Validate,
    readings: list[Entry],
    byzantine: Reconciliation,
    kjv_text: Mapping[str, str],
) -> None:
    # Words a reading replaces, printed once and in roman, so that only
    # their being the edit itself can refuse them as its parallel.
    compiled = {o["id"]: o for o in byzantine.decisions.overrides}
    supplied = byzantine.english.supplied
    bad, edit = next(
        (copy.deepcopy(o), e)
        for o in readings
        if "kjv" in o["evidence"]
        for e in compiled[o["id"]]["bound"]
        if e["old"]
        and kjv_text[e["ref"]].count(e["old"]) == 1
        and not any(
            a < e["end"] and e["start"] < b for a, b, _ in supplied.get(e["ref"], [])
        )
    )
    bad["evidence"]["kjv"] = {"ref": edit["ref"], "quote": edit["old"]}
    _, errors = validate([bad])
    assert len(errors) == 1 and "is words an override edits" in errors[0]


def test_a_kjv_parallel_is_not_words_another_reading_edits(
    validate: Validate,
    readings: list[Entry],
    byzantine: Reconciliation,
    kjv_text: Mapping[str, str],
) -> None:
    # Revelation 4:4's "elders sitting", once REV 14:14#1's parallel, stands
    # in words REV 4:4#1+REV 4:4#2 replaces, without the "I saw" it needs.
    compiled = {o["id"]: o for o in byzantine.decisions.overrides}
    supplied = byzantine.english.supplied
    bad = kjv_parallel(readings)
    other, edit = next(
        (o, e)
        for o in readings
        if o["id"] != bad["id"]
        for e in compiled[o["id"]]["bound"]
        if e["old"]
        and kjv_text[e["ref"]].count(e["old"]) == 1
        and not any(
            a < e["end"] and e["start"] < b for a, b, _ in supplied.get(e["ref"], [])
        )
    )
    bad["evidence"]["kjv"] = {"ref": edit["ref"], "quote": edit["old"]}
    compiled_alone, errors = validate([bad])
    assert len(compiled_alone) == 1 and not errors
    _, errors = validate([bad, other])
    assert len(errors) == 1 and "is words an override edits" in errors[0]
    assert errors[0].startswith(f"override {bad['id']}")


def test_a_kjv_parallel_is_whole_words(
    validate: Validate, readings: list[Entry]
) -> None:
    bad = next(
        copy.deepcopy(o)
        for o in readings
        if o["evidence"].get("kjv", {}).get("quote") == "in a word"
    )
    bad["evidence"]["kjv"]["quote"] = "n a word"
    _, errors = validate([bad])
    assert len(errors) == 1 and "kjv quote cuts through a word" in errors[0]


def test_the_tag_and_the_evidence_go_together(
    validate: Validate, readings: list[Entry], sample: Callable[[], Entry]
) -> None:
    bad = kjv_parallel(readings)
    del bad["evidence"]["kjv"]
    _, errors = validate([bad])
    assert len(errors) == 1 and "go together" in errors[0]
    bad = sample()
    assert "kjv-parallel" not in bad["wording"]
    bad["evidence"]["kjv"] = {"ref": "MAT 1:1", "quote": "The book of the generation"}
    _, errors = validate([bad])
    assert len(errors) == 1 and "go together" in errors[0]


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
    assert len(errors) == 1 and "duplicate unit" in errors[0]


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
    assert (
        len(errors) == 1
        and "kind edit needs edits or an instruction, nochange has none" in errors[0]
    )
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
    byzantine: Reconciliation, sample: Callable[[], Entry]
) -> None:
    entry = sample()
    entry["evidence"] = {
        ADDITIONAL: {"entry": 1, "quote": "Explicit additional fixture"}
    }
    witness_rows: dict[str, Mapping[int | str, Mapping[str, Any]]] = {
        **decisions.witness_rows(
            byzantine.apparatuses.reports, byzantine.instructions.rows
        ),
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


# Corrections of shared Greek: readings without units


def correction() -> Entry:
    return {
        "id": "LUK 23:42",
        "kind": "edit",
        "edits": [
            {
                "ref": "LUK 23:42",
                "from": "into thy kingdom",
                "to": "in thy kingdom",
                "greek": "ἐν τῇ βασιλείᾳ σου",
            }
        ],
        "why": "Test.",
        "evidence": {"rv": {"ref": "LUK 23:42", "quote": "in thy kingdom"}},
    }


def test_a_correction_of_shared_greek_validates_without_units_or_tags(
    validate: Validate,
) -> None:
    compiled, errors = validate([correction()])
    assert errors == [] and compiled[0]["unit_ids"] == []


@pytest.mark.parametrize("field", ["wording", "grammar"])
def test_a_correction_of_shared_greek_has_no_wording_or_grammar(
    validate: Validate, field: str
) -> None:
    _, errors = validate([{**correction(), field: []}])
    assert len(errors) == 1 and "wording and grammar go with units" in errors[0]


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("greek", "εἰς τὴν βασιλείαν σου", "greek must occur once"),
        ("greek", "εν τῇ βασιλείᾳ σου", "greek must occur once"),
        ("ref", "LUK 23:43", "greek, at its verse"),
        ("greek", None, "greek, at its verse"),
    ],
)
def test_a_correction_names_the_greek_it_renders(
    validate: Validate, field: str, value: str | None, message: str
) -> None:
    bad = correction()
    if value is None:
        del bad["edits"][0][field]
    else:
        bad["edits"][0][field] = value
    _, errors = validate([bad])
    assert len(errors) == 1 and message in errors[0]


def test_a_correction_cannot_claim_a_greek_difference(validate: Validate) -> None:
    bad = {
        "id": "MAT 3:8",
        "kind": "edit",
        "edits": [
            {"ref": "MAT 3:8", "from": "fruits", "to": "fruit", "greek": "καρπὸν"}
        ],
        "why": "Test.",
        "evidence": {"rv": {"ref": "MAT 3:8", "quote": "fruit"}},
    }
    _, errors = validate([bad])
    assert len(errors) == 1 and "touches a difference" in errors[0]


def test_a_reading_of_a_difference_names_no_greek(
    validate: Validate, sample: Callable[[], Entry]
) -> None:
    bad = sample()
    bad["edits"][0]["greek"] = "καρπὸν"
    _, errors = validate([bad])
    assert len(errors) == 1 and "greek, at its verse" in errors[0]


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
        "wording": ["kjv-retained"],
        "grammar": ["supplied-word"],
        "why": "Citation fixture.",
        "evidence": {witness: {"ref": ref, "quote": quote}},
    }


@pytest.mark.parametrize("witness", [RV, "asv", BOYD_ASV])
def test_real_revision_supplied_citations(
    validate: Validate, byzantine: Reconciliation, witness: str
) -> None:
    # Each reader's real spans are tested against a permitted Greek unit.
    by_ref = {u["ref"]: u for u in byzantine.greek.units}
    ref, metadata = next(
        (ref, row)
        for ref, row in byzantine.english.revision_citations[witness].items()
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
    byzantine: Reconciliation, readings: list[Entry], validate: Validate
) -> None:
    entry = citation_entry(readings, "MRK 10:40#1", BOYD_ASV, "on [my] left hand")
    args = arguments(byzantine)
    assert "metadata missing" in decisions.validate_overrides([entry], *args)[1][0]
    metadata = copy.deepcopy(dict(byzantine.english.revision_citations))
    changed = metadata[BOYD_ASV]["MRK 10:40"]
    assert changed is not None
    changed["text"] += " changed"
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
    byzantine: Reconciliation, readings: list[Entry]
) -> None:
    entry = faa_entry(readings)
    rows: dict[str, FaaRow] = copy.deepcopy(dict(byzantine.apparatuses.faa_rows))
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
    byzantine: Reconciliation, placements: list[Placement]
) -> None:
    hand = [
        r
        for r in [*byzantine.apparatuses.reports, *byzantine.decisions.instructions]
        if r.get("method") == "hand"
    ]
    # The Greek apparatuses' rows are placed on the units themselves, or
    # nowhere (received.py's tests).
    greek = [p for p in placements if p["witness"] in QUOTED]
    assert len(greek) == 26
    assert len(hand) == len(placements) - len(greek)


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


def stale_placement(reports: Sequence[Report], by_id: Mapping[str, Unit]) -> Placement:
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


def test_place_with_a_null_unit_marks_the_row_as_having_no_greek_unit(
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
        and changed["scope"] == "no-greek-unit"
        and changed["reason"] == "Shared Greek."
    )


def test_place_leaves_the_input_instruction_edits_unchanged(
    byzantine: Reconciliation, ledger: list[Unit]
) -> None:
    rows = byzantine.decisions.instructions
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
    assert placed[0]["scope"] == "no-greek-unit"
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
    with pytest.raises(CheckFailed, match="key is not a TR note's"):
        decisions.lemma_entries({"1CO 15:39#1 RP": {"lemma": "x", "why": "y"}})


# The build stops on a decision gone stale


def test_the_build_stops_on_a_stale_placement_a_redundant_reading_or_a_broken_invariant(
    edition: bible.pipeline.Edition, by_id: Mapping[str, Unit]
) -> None:
    context = edition.byzantine
    reports, ledger = context.apparatuses.reports, context.greek.units
    # A placement the code now makes on its own stops the stage that reads it.
    placement = stale_placement(reports, by_id)
    with pytest.raises(
        CheckFailed,
        match=f"placements the code now makes.*{placement['witness']} {placement['entry']}",
    ):
        stages.stage_reports(
            replace(context.inputs, placements=(*context.inputs.placements, placement)),
            context.greek,
        )
    # A reading that keeps the KJV where nothing would change it anyway.
    witnessed = {
        a["unit"]
        for rows in (reports, context.revisions.rows, context.decisions.instructions)
        for row in rows
        for a in row.get("units", [])
    }
    quiet = next(
        u
        for u in ledger
        if u["id"] not in witnessed
        and not context.revisions.alarms.get(u["id"], {}).get("alarm")
        and u["class"] != "structural"
    )
    reading: Override = {
        "id": quiet["id"],
        "unit_ids": [quiet["id"]],
        "kind": "nochange",
        "why": "Keep the KJV.",
        "evidence": {},
        "wording": [],
        "grammar": [],
        "bound": [],
    }
    rows = decide.decide(
        [quiet],
        context.decisions.instructions,
        reports,
        context.revisions.rows,
        [reading],
        context.revisions.alarms,
        context.english.kjv,
    )
    assert rows[0].get("redundant")
    with pytest.raises(
        CheckFailed, match=f"readings that change nothing.*{quiet['id']}"
    ):
        stages.stage_decide(
            context.greek,
            context.english,
            context.apparatuses,
            context.revisions,
            replace(
                context.decisions, overrides=(*context.decisions.overrides, reading)
            ),
        )
    # A unit the dispositions lose.
    invariants = verify.checks(
        context.english.documents,
        context.edited.prepared,
        ledger,
        context.verified.dispositions[1:],
        context.greek.structure,
    )
    assert invariants["I1"] == "unit coverage differs"
    with pytest.raises(CheckFailed, match="invariants broken.*I1"):
        verify.held(invariants, {})


@pytest.mark.parametrize("mismatch", ["words", "address"])
def test_shared_greek_refuses_mismatched_alignment(
    byzantine: Reconciliation, mismatch: str
) -> None:
    alignment = copy.deepcopy(byzantine.greek.rp_alignment)
    ref = "LUK 23:42"
    if mismatch == "words":
        alignment.text[ref] = ["wrong", *alignment.text[ref]]
        message = "printed words disagree"
    else:
        alignment.addresses[ref][0] = "LUK 23:41"
        message = "cross-verse joined-word"
    with pytest.raises(CheckFailed, match=f"{ref}:.*{message}"):
        decisions.shared_greek(
            "ἐν τῇ βασιλείᾳ σου",
            ref,
            byzantine.greek.units,
            byzantine.greek.printed,
            alignment,
            byzantine.greek.structure,
        )


def test_the_build_stops_on_ordinary_tr_restoration_failures(
    edition: bible.pipeline.Edition,
) -> None:
    context = edition.byzantine
    with pytest.raises(CheckFailed, match="Notes that do not restore.*LUK 2:21"):
        verify.held(
            context.verified.invariants,
            {
                "LUK 2:21": [
                    "variant: note does not restore the corrected KJV (damaged coupled alternative)"
                ]
            },
        )


@pytest.mark.parametrize("field", ["wording", "grammar"])
def test_reading_claims_are_unique(
    validate: Validate, sample: Callable[[], Entry], field: str
) -> None:
    bad = sample()
    bad[field].append(bad[field][0])
    _, errors = validate([bad])
    assert len(errors) == 1 and "duplicate wording or grammar" in errors[0]


@pytest.mark.parametrize("field", ["wording", "grammar"])
def test_reading_units_need_both_kinds_of_claim(
    validate: Validate, sample: Callable[[], Entry], field: str
) -> None:
    bad = sample()
    bad[field] = []
    _, errors = validate([bad])
    assert len(errors) == 1 and "wording and grammar go with units" in errors[0]


# Pierpont's category-c instructions (edition/byzantine.json instructions), and
# the version a correction of shared Greek cites for its former words (former)
type Declared = dict[str, dict[str, Any]]


def declared_of(found: Reconciliation) -> Declared:
    return {
        k: copy.deepcopy(dict(v))
        for k, v in found.decisions.instruction_decisions.items()
    }


def instruction_entries(
    found: Reconciliation, declared: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """The readings the decisions add, checked as the decisions stage checks
    them, with the evidence checker the stage uses."""
    return decisions.instruction_entries(
        declared,
        found.decisions.instructions,
        found.greek,
        found.decisions.instruction_carriers,
        partial(
            decisions.evidence_checked,
            kjv=found.english.kjv,
            witness_rows=decisions.witness_rows(
                found.apparatuses.reports, found.instructions.rows
            ),
            texts=found.english.texts,
            supplied=found.english.supplied,
            revision_citations=found.english.revision_citations,
            faa_rows=found.apparatuses.faa_rows,
        ),
    )


def readings_of(found: Reconciliation) -> list[Override]:
    """The editor's readings compiled, without the instructions read as readings."""
    return [o for o in found.decisions.overrides if "instruction" not in o]


def test_every_category_c_row_is_decided(byzantine: Reconciliation) -> None:
    declared = byzantine.decisions.instruction_decisions
    assert set(declared) == set(decisions.category_c_rows(byzantine.instructions.rows))
    assert len(declared) == 39
    assert Counter(e["kind"] for e in declared.values()) == {"edit": 25, "nochange": 14}
    # The edits that execute themselves are overrides keyed by their verse;
    # the others are their unit's, or a reading's that took the construction
    # (Mark 15:3, Colossians 1:24, in other words than Pierpont's) or that
    # carries out the edit word for word at a verse with no unit (Acts 10:20).
    added = instruction_entries(byzantine, declared)
    assert len(added) == 20
    compiled = {o["id"]: o for o in byzantine.decisions.overrides}
    for entry in added:
        override = compiled[entry["id"]]
        assert override["instruction"] is entry["instruction"]
        row = next(
            r for r in byzantine.verified.dispositions if r["unit"] == entry["id"]
        )
        assert row["disposition"] == "shared" and row["execution"] == "applied"
    carriers = byzantine.decisions.instruction_carriers
    assert set(carriers) == {k for k, e in declared.items() if e["kind"] == "edit"}
    assert {k: c for k, c in carriers.items() if c["kind"] != "itself"} == {
        "pierpont 23": {"kind": "unit", "ids": ["MAT 10:25#1"]},
        "pierpont 117": {"kind": "reading", "ids": ["MRK 15:3#1"]},
        "pierpont 345": {"kind": "reading", "ids": ["ACT 10:20"]},
        "pierpont 510": {"kind": "reading", "ids": ["COL 1:24#1"]},
        "pierpont 874": {"kind": "reading", "ids": ["REV 17:9"]},
    }
    assert {c["ids"][0] for c in carriers.values() if c["kind"] == "itself"} == {
        e["id"] for e in added
    }


@pytest.mark.parametrize(
    ("change", "error"),
    [
        (lambda d: d.pop("pierpont 276"), "rows differ"),
        (lambda d: d.update({"pierpont 99999": d["pierpont 276"]}), "rows differ"),
        (lambda d: d["pierpont 276"].update(greek=["λέξεις ἀνύπαρκτοι"]), "once"),
        (
            lambda d: d["pierpont 276"].update(
                greek=["τὸν λόγον μου", "τὸν λόγον μου"]
            ),
            "needs its Greek",
        ),
        # The former version goes on the reading that makes the edit.
        (
            lambda d: d["pierpont 345"].update(former=d["pierpont 29"]["former"]),
            "goes on the reading",
        ),
        (
            lambda d: d["pierpont 23"].update(former=d["pierpont 29"]["former"]),
            "goes on the reading",
        ),
        # Evidence is read from its source.
        (
            lambda d: d["pierpont 566"]["evidence"]["rv"].update(
                quote="imaginary wording"
            ),
            "not in the verse once",
        ),
        (
            lambda d: d["pierpont 566"]["evidence"]["rv"].update(ref="JAS 3:15"),
            "not in the verse once",
        ),
        (
            lambda d: d["pierpont 566"]["evidence"].update(
                unknown={"ref": "JAS 3:14", "quote": "heart"}
            ),
            "unknown witness",
        ),
    ],
)
def test_a_decision_must_fit_its_row_and_its_sources(
    byzantine: Reconciliation, change: Any, error: str
) -> None:
    declared = declared_of(byzantine)
    change(declared)
    with pytest.raises(CheckFailed, match=error):
        instruction_entries(byzantine, declared)


def test_an_instruction_executes_only_where_it_binds_to_shared_greek(
    byzantine: Reconciliation,
) -> None:
    declared = declared_of(byzantine)
    rows = copy.deepcopy(list(byzantine.instructions.rows))
    row = next(i for i in rows if i["source"] == "pierpont" and i["entry"] == 276)
    row["bind"] = "ambiguous"
    with pytest.raises(CheckFailed, match="does not bind uniquely"):
        decisions.instruction_entries(
            declared,
            rows,
            byzantine.greek,
            byzantine.decisions.instruction_carriers,
            lambda label, evidence, refs: None,
        )
    # A reading at the verse that does not carry the correction out leaves it
    # no room; a reading at a unit of the verse leaves it to carry itself.
    placed = byzantine.decisions.instructions
    readings = readings_of(byzantine)
    kjv = byzantine.english.kjv
    stray: Override = {
        "id": "JHN 14:23",
        "unit_ids": [],
        "bound": [
            {"ref": "JHN 14:23", "start": 0, "end": 2, "old": "If", "new": "When"}
        ],
    }
    with pytest.raises(CheckFailed, match="pierpont 276: the reading at JHN 14:23"):
        decisions.carriers(declared, placed, [*readings, stray], kjv)
    at_unit: Override = {**stray, "id": "JHN 14:23#9", "unit_ids": ["JHN 14:23#9"]}
    carriers = decisions.carriers(declared, placed, [*readings, at_unit], kjv)
    assert carriers["pierpont 276"] == {"kind": "itself", "ids": ["JHN 14:23"]}


def test_two_instructions_cannot_carry_themselves_at_one_verse(
    byzantine: Reconciliation,
) -> None:
    # A reading read from an instruction is keyed by its verse, so a second
    # row at John 14:23 would share the key of the first.
    declared = declared_of(byzantine)
    rows = copy.deepcopy(list(byzantine.decisions.instructions))
    first = next(i for i in rows if i["source"] == "pierpont" and i["entry"] == 276)
    second = copy.deepcopy(first)
    second["entry"] = 9999
    rows.append(second)
    declared["pierpont 9999"] = copy.deepcopy(declared["pierpont 276"])
    carriers: dict[str, Carrier] = {
        **byzantine.decisions.instruction_carriers,
        "pierpont 9999": {"kind": "itself", "ids": ["JHN 14:23"]},
    }
    with pytest.raises(CheckFailed, match="carry themselves at one verse.*JHN 14:23"):
        decisions.instruction_entries(
            declared,
            rows,
            byzantine.greek,
            carriers,
            lambda label, evidence, refs: None,
        )


def test_an_edit_is_carried_out_by_its_unit_a_reading_or_itself(
    byzantine: Reconciliation,
) -> None:
    declared = declared_of(byzantine)
    rows = byzantine.decisions.instructions
    overrides = byzantine.decisions.overrides
    kjv = byzantine.english.kjv
    carriers = decisions.carriers(declared, rows, overrides, kjv)
    assert carriers == byzantine.decisions.instruction_carriers
    # A carrier is declared by the editor; the build checks its passage.
    without = [o for o in overrides if o["id"] != "ACT 10:20"]
    with pytest.raises(CheckFailed, match="pierpont 345: carrier ACT 10:20 is no"):
        decisions.carriers(declared, rows, without, kjv)
    elsewhere = {
        **declared,
        "pierpont 345": {**declared["pierpont 345"], "carrier": "LUK 23:42"},
    }
    with pytest.raises(
        CheckFailed, match="pierpont 345: reading LUK 23:42 concerns another"
    ):
        decisions.carriers(elsewhere, rows, overrides, kjv)
    for key, reading in (("pierpont 510", "COL 1:24#1"), ("pierpont 345", "ACT 10:20")):
        unnamed = {
            **declared,
            key: {k: v for k, v in declared[key].items() if k != "carrier"},
        }
        with pytest.raises(CheckFailed, match=f"{key}: overlaps readings {reading}"):
            decisions.carriers(unnamed, rows, overrides, kjv)
    at_unit = {
        **declared,
        "pierpont 23": {**declared["pierpont 23"], "carrier": "MAT 10:25#1"},
    }
    with pytest.raises(CheckFailed, match="pierpont 23: its unit carries it out"):
        decisions.carriers(at_unit, rows, overrides, kjv)
    # Rejecting Pierpont does not reject another correction of the same words.
    declared["pierpont 345"] = {
        k: v
        for k, v in {**declared["pierpont 345"], "kind": "nochange"}.items()
        if k != "carrier"
    }
    assert "pierpont 345" not in decisions.carriers(declared, rows, overrides, kjv)
    # Execution of the instruction itself is still a mechanical contradiction.
    declared["pierpont 23"] = {**declared["pierpont 23"], "kind": "nochange"}
    with pytest.raises(
        CheckFailed, match="pierpont 23: nochange, but its unit executes"
    ):
        decisions.carriers(declared, rows, overrides, kjv)


def test_carriers_validate_keys_before_looking_up_rows(
    byzantine: Reconciliation,
) -> None:
    declared = declared_of(byzantine)
    declared["pierpont 99999"] = declared["pierpont 276"]
    with pytest.raises(CheckFailed, match="Category-c decisions and rows differ"):
        decisions.carriers(
            declared,
            byzantine.decisions.instructions,
            readings_of(byzantine),
            byzantine.english.kjv,
        )


def test_a_declared_carrier_need_not_enclose_the_instruction(
    byzantine: Reconciliation,
) -> None:
    readings = readings_of(byzantine)
    # The editor may recast a sentence elsewhere in the same verse. Span
    # containment is not evidence that this does or does not fulfill Pierpont.
    recast: Override = {
        "id": "ACT 10:20",
        "unit_ids": [],
        "bound": [{"ref": "ACT 10:20", "start": 0, "end": 1, "old": "A", "new": "B"}],
    }
    readings = [recast if o["id"] == recast["id"] else o for o in readings]
    carriers = decisions.carriers(
        declared_of(byzantine),
        byzantine.decisions.instructions,
        readings,
        byzantine.english.kjv,
    )
    assert carriers["pierpont 345"] == {"kind": "reading", "ids": ["ACT 10:20"]}


def test_overlap_reports_all_readings_even_when_none_encloses_the_instruction() -> None:
    row: Instruction = {
        "edits": [{"ref": "JHN 14:23", "old": "my words", "word_range": [1, 3]}]
    }
    readings: list[Override] = [
        {"id": "first", "bound": [{"ref": "JHN 14:23", "start": 5, "end": 7}]},
        {"id": "second", "bound": [{"ref": "JHN 14:23", "start": 8, "end": 13}]},
        {"id": "elsewhere", "bound": [{"ref": "JHN 14:23", "start": 0, "end": 4}]},
    ]
    assert decisions.overlapping_readings(
        row, readings, {"JHN 14:23": "keep my words"}
    ) == ["first", "second"]


@pytest.mark.parametrize(
    ("text", "edit", "expected"),
    [
        (
            "Keep my words.",
            {"kind": "replace", "old": "keep", "new": "observe", "word_range": [0, 1]},
            "Observe",
        ),
        (
            "I keep my words.",
            {"kind": "replace", "old": "keep", "new": "observe", "word_range": [1, 2]},
            "observe",
        ),
        (
            "And here is the mind.",
            {"kind": "delete", "old": "And", "new": "", "word_range": [0, 1]},
            None,
        ),
        (
            "I Keep my words.",
            {"kind": "replace", "old": "keep", "new": "observe", "word_range": [1, 2]},
            None,
        ),
        (
            "Keep my words.",
            {"kind": "insert", "old": "", "new": "Now", "word_range": [0, 0]},
            None,
        ),
    ],
)
def test_direct_instruction_casing_stays_within_its_own_words(
    byzantine: Reconciliation,
    text: str,
    edit: dict[str, Any],
    expected: str | None,
) -> None:
    ref = "JHN 14:23"
    target = byzantine.greek
    entry = {
        "instruction": {"edits": [{"ref": ref, **edit}]},
        "greek": ["τὸν λόγον μου"],
    }

    def bound() -> list[BoundEdit]:
        return list(
            decisions.instruction_bound(
                "instruction",
                entry,
                {ref: text},
                target.units,
                target.printed,
                target.rp_alignment,
                target.structure,
            )
        )

    if expected is None:
        with pytest.raises(CheckFailed, match="explicit reading"):
            bound()
    else:
        result = bound()
        assert result[0]["new"] == expected
        assert result[0]["old"] == text[result[0]["start"] : result[0]["end"]]
        assert result[0]["end"] <= text.index(" my")


def test_the_former_version_is_quoted_from_its_text_at_the_verse() -> None:
    former = {
        "witness": "vulgate",
        "ref": "LUK 23:42",
        "quote": "in regnum tuum",
        "why": "The accusative supports into.",
    }
    texts = {"vulgate": {"LUK 23:42": "cum veneris in regnum  tuum."}}
    decisions.former_checked("reading", former, {"LUK 23:42"}, texts)
    for bad, error in [
        ({**former, "witness": "tyndale"}, "names no version"),
        ({**former, "witness": "king-james-version"}, "names no version"),
        ({**former, "ref": "LUK 23:43"}, "about another verse"),
        ({**former, "quote": "in regno tuo"}, "not in vulgate LUK 23:42 once"),
        ({**former, "quote": "in regnum tu"}, "cuts through a word"),
    ]:
        with pytest.raises(CheckFailed, match=error):
            decisions.former_checked("reading", bad, {"LUK 23:42"}, texts)
    with pytest.raises(CheckFailed, match="once"):
        decisions.former_checked(
            "reading",
            former,
            {"LUK 23:42"},
            {"vulgate": {"LUK 23:42": "in regnum tuum in regnum tuum"}},
        )


def test_a_greek_difference_names_its_greek_witness_not_a_version(
    byzantine: Reconciliation,
) -> None:
    reading = copy.deepcopy(byzantine.inputs.decisions["readings"]["MRK 15:3#1"])
    reading["former"] = {
        "witness": "vulgate",
        "ref": "MRK 15:3",
        "quote": "ipse autem nihil respondit",
        "why": "The Latin has the clause.",
    }
    _, errors = decisions.validate_overrides(
        [{"id": "MRK 15:3#1", **reading}],
        byzantine.greek.units,
        byzantine.english.kjv,
        decisions.witness_rows(
            byzantine.apparatuses.reports, byzantine.instructions.rows
        ),
        byzantine.english.texts,
        byzantine.english.supplied,
    )
    assert errors == ["override MRK 15:3#1: a Greek difference names its Greek witness"]


@pytest.mark.parametrize(
    ("ref", "words"),
    [
        ("JHN 14:23", "keep my word:"),
        ("1TH 2:12", "who calleth you"),
        ("REV 17:9", "Here is the mind"),
        ("ROM 6:11", "through Christ Jesus"),
    ],
)
def test_instructions_correct_shared_greek_without_a_difference_unit(
    byzantine: Reconciliation, ref: str, words: str
) -> None:
    assert words in verses_of(byzantine.edited.prepared)[ref].text
    row = next(r for r in byzantine.verified.dispositions if r["unit"] == ref)
    assert row["disposition"] == "shared"
    assert not any(u["id"] == ref for u in byzantine.greek.units)


@pytest.mark.parametrize(
    ("ref", "words"), [("ROM 16:4", "their own necks"), ("JAS 3:14", "in your hearts")]
)
def test_a_nochange_keeps_the_king_james_words_without_a_note(
    edition: bible.pipeline.Edition, ref: str, words: str
) -> None:
    book, address = ref.split()
    document = edition.documents[book]
    assert words in scripture.verses(document)[address].text
    assert not any(
        n.get("x-key") == f"{ref} rendering" for n in usj.notes_of(document["content"])
    )
