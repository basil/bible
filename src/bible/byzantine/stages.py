"""The stages of the reconciliation, in the order of the modules' dependencies.

Each stage is a function of the read inputs and the records of the stages
before it, and returns a frozen record of what it worked out (the decide
stage, a tuple of its dispositions); it stops on its own decisions that do
not fit their sources and changes nothing it was given.
`bible.byzantine.reconciled` runs them and gathers the records as the
Reconciliation.
"""

from __future__ import annotations

import collections
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from bible.byzantine import (
    BOOKS,
    BOYD_ASV,
    FAA,
    INSTRUCTION_SOURCES,
    RV,
    TCENT,
    apparatus,
    crosswire,
    decide,
    decisions,
    edit,
    english,
    greek,
    instructions,
    inventories,
    notes,
    pierpont,
    received,
    rendering,
    revisers,
    units,
    verify,
)
from bible.byzantine.crosswire import Aligned, Tagged
from bible.byzantine.english import Citation
from bible.byzantine.rows import (
    Alarm,
    BoydNote,
    CollationRow,
    Disposition,
    FaaRow,
    Instruction,
    Override,
    Placement,
    Report,
    RevisionRow,
    Token,
    Unit,
    Unmatched,
)
from bible.byzantine.tags import Tag, tagged
from bible.checks import require
from bible.references import parse_passage
from bible.sources import Content
from bible.usj import Document, Node


@dataclass(frozen=True)
class Inputs:
    """What the reconciliation is given: the read sources by the registry's
    names, the King James books, and the editor's decisions
    (edition/byzantine.json) and placements (edition/byzantine-placements.json),
    thawed."""

    sources: Mapping[str, Content]
    kjv: Mapping[str, Document]
    decisions: Mapping[str, Any]
    placements: tuple[Placement, ...]


@dataclass(frozen=True)
class Greek:
    """The Greek texts and the unit ledger."""

    structure: greek.Structure
    # Scrivener's text, corrected, and its accented form aligned to it.
    tr: Mapping[str, list[str]]
    tr_alignment: greek.Alignment
    # RP2018's text as the printed RP2026 prints it, and the printed text
    # aligned to it.
    rp: Mapping[str, list[str]]
    rp_alignment: greek.Alignment
    printed: Mapping[str, greek.PrintedVerse]
    # The parsed texts' tags, the Received Text's only where its transcription
    # agrees with Scrivener's.
    tr_tags: Mapping[str, list[Token]]
    rp_tags: Mapping[str, list[Token]]
    # RP's marginal readings, where the Byzantine manuscripts are divided.
    alternates: Mapping[str, list[greek.MarginalAlternate]]
    collation: tuple[CollationRow, ...]
    tcgnt: tuple[BoydNote, ...]
    # The printed RP2026's apparatus.
    apparatus: tuple[BoydNote, ...]
    units: tuple[Unit, ...]
    unmatched: tuple[Unmatched, ...]
    # The verses at which the parsed Received Text differs from Scrivener's.
    annotation_mismatches: tuple[str, ...]


@dataclass(frozen=True)
class English:
    """The King James books and verses, the revisions' texts, and the
    CrossWire bridge."""

    documents: Mapping[str, Document]
    subscriptions: Mapping[str, list[Node]]
    kjv: Mapping[str, str]
    supplied: Mapping[str, list[tuple[int, int, str]]]
    revision_citations: Mapping[str, Mapping[str, Citation | None]]
    texts: Mapping[str, Mapping[str, str]]
    aligned: Mapping[str, Aligned]
    bridge_failures: Mapping[str, str]
    crosswire: Mapping[str, Tagged]


@dataclass(frozen=True)
class Apparatuses:
    """The modern-English apparatuses attached to units."""

    faa_rows: Mapping[str, FaaRow]
    reports: tuple[Report, ...]


@dataclass(frozen=True)
class Instructions:
    """Pierpont's booklet and its instructions, bound, attached and checked
    for compatibility with the units' Greek."""

    inventory: pierpont.Inventory
    rows: tuple[Instruction, ...]


@dataclass(frozen=True)
class Revisions:
    """The RV and Boyd's ASV as witnesses, and the revision alarm."""

    rows: tuple[RevisionRow, ...]
    admitted: Mapping[str, frozenset[str]]
    alarms: Mapping[str, Alarm]


@dataclass(frozen=True)
class Decisions:
    """The editor's readings and lemmas, validated against the placed rows,
    and the instructions judged and chosen by construction."""

    instructions: tuple[Instruction, ...]
    overrides: tuple[Override, ...]
    lemmas: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class Edited:
    """The King James books with the dispositions carried out and their notes
    finished, and the dispositions with their edits, or why each was refused,
    before the verify stage flags them."""

    prepared: Mapping[str, Document]
    # The term each note names, by its key (received.labels).
    note_witnesses: Mapping[str, str]
    dispositions: tuple[Disposition, ...]


@dataclass(frozen=True)
class Verified:
    """The invariants checked on what was prepared, every edited verse's
    problems, and the dispositions flagged with them: the finished set."""

    invariants: Mapping[str, str]
    finished: Mapping[str, list[str]]
    dispositions: tuple[Disposition, ...]


@dataclass(frozen=True)
class Reconciliation:
    """Everything the reconciliation worked out, by the stage that made it,
    for the promotion, the review and the textual variants."""

    inputs: Inputs
    greek: Greek
    english: English
    apparatuses: Apparatuses
    instructions: Instructions
    revisions: Revisions
    decisions: Decisions
    edited: Edited
    verified: Verified


def inputs(
    sources: Mapping[str, Content],
    kjv: Mapping[str, Document],
    decided: Mapping[str, Any],
    placements: Mapping[str, Any],
) -> Inputs:
    """The reconciliation's inputs, the placements keyed by witness and entry."""
    placed: list[Placement] = []
    for key, entry in placements["placements"].items():
        witness, _, number = key.partition(" ")
        placement: Placement = {
            "witness": witness,
            "entry": int(number) if number.isdigit() else number,
        }
        placement.update(entry)
        placed.append(placement)
    return Inputs(
        MappingProxyType(sources),
        MappingProxyType(kjv),
        MappingProxyType(decided),
        tuple(placed),
    )


def structure_of(
    decided: Mapping[str, Any], tr: Mapping[str, list[str]], rp: Mapping[str, list[str]]
) -> greek.Structure:
    """The structural decisions, held to both texts: the omitted verses are
    exactly those RP2018 numbers without words, and the moves account for
    every address one text has and the other lacks."""
    omitted = greek.empty_verses(rp)
    declared = frozenset(decided["omitted"])
    require(
        declared == omitted,
        f"Structural decisions disagree with the Byzantine text: omitted "
        f"{sorted(omitted ^ declared)}",
    )
    moved: dict[str, str] = {}
    for ref, entry in decided["moved"].items():
        for source, destination in zip(
            parse_passage(ref).verses, parse_passage(entry["to"]).verses, strict=True
        ):
            moved[str(source)] = str(destination)
    kjv_only = set(tr) - set(rp)
    rp_only = set(rp) - set(tr)
    require(
        kjv_only == {ref for ref in moved if moved[ref] not in tr}
        and rp_only == {target for target in moved.values() if target not in tr},
        f"Structural decisions do not account for the verses one text lacks: "
        f"{sorted(kjv_only)} {sorted(rp_only)}",
    )
    for ref, target in moved.items():
        require(
            ref not in tr or target not in tr or moved.get(target) == ref,
            f"Exchanged verses must be moved both ways: {ref}",
        )
    return greek.Structure(moved, omitted)


def fitting(errors: Sequence[str], stale: Sequence[Placement] = ()) -> None:
    """The editor's decisions of a stage all fit their sources, and each of
    its placements places a row the code does not place on its own."""
    require(
        not errors, f"Byzantine decisions that do not fit their sources: {errors[:5]}"
    )
    keys = [f"{p['witness']} {p['entry']}" for p in stale]
    require(not keys, f"Byzantine placements the code now makes: {keys}")


def evidenced(
    corrections: Mapping[str, Mapping[str, str]],
    ledger: Sequence[Unit],
    tcgnt: Sequence[BoydNote],
    printed: Sequence[BoydNote],
) -> None:
    """A correction of the Scrivener transcription stands only where both
    apparatuses give its words as Scrivener's, at a unit it makes."""
    rows = received.rows(tcgnt, printed)
    for ref, correction in corrections.items():
        words = greek.greek_words(correction["to"])
        found = {
            a["inventory"]
            for u in ledger
            if u["ref"] == ref
            for a in u["inventories"]
            if (a["inventory"], a["entry"]) in rows
            and inventories.reading_words(
                rows[(a["inventory"], a["entry"])]["tr"][0]["reading"]
            )
            == words
        }
        require(
            found == {"tcgnt", units.PRINTED_APPARATUS},
            f"Scrivener correction the apparatuses do not give: {ref}",
        )


def stage_greek(given: Inputs) -> Greek:
    """The Greek texts and the unit ledger."""
    corrections = given.decisions.get("scrivener", {})
    tr = greek.corrected(greek.scrivener(given.sources["scrivener"]), corrections)
    parsed, tr_tags = greek.parsed_scrivener(given.sources["parsed_tr"])
    mismatches = [ref for ref in tr if parsed[ref] != tr[ref]]
    checked = {f"TR {ref}": t for ref, t in tr_tags.items() if ref not in mismatches}
    rp, tags = greek.rp2018(given.sources["rp2018"])
    structure = structure_of(given.decisions["structure"], tr, rp)
    root = greek.tree(given.sources["rp2026"])
    printed, diacritics = greek.printed(root, structure.omitted, list(rp)[-1])
    rp = greek.rp2026(rp, printed)
    collation = inventories.collation(given.sources["collation"])
    tcgnt = inventories.boyd(given.sources["tcgnt"])
    require(len(tcgnt) == 1948, f"TCGNT inventory: {len(tcgnt)}, expected 1948")
    splits = inventories.word_breaks(given.sources["tcgnt"] / "095XXC.usx")
    rp_alignment = greek.align(
        {ref: verse["accented"] for ref, verse in printed.items()}, rp
    )
    printed_apparatus = greek.apparatus(root, printed)
    sides = collections.Counter(
        "SCR" if "SCR" in n["tr"][0]["sigla"] else "TR" for n in printed_apparatus
    )
    require(
        sides == {"TR": 1735, "SCR": 150},
        f"RP2026 apparatus inventory: {dict(sides)}, expected 1735 TR and 150 SCR",
    )
    ledger, unmatched = units.reconcile(
        tr,
        rp,
        collation,
        tcgnt,
        {**checked, **tags},
        splits,
        structure,
        printed_apparatus,
    )
    extra = units.supplementary_units(
        tr,
        rp,
        collation,
        tcgnt,
        printed,
        diacritics,
        structure,
        given.decisions["accents"],
        rp_alignment,
        printed_apparatus,
    )
    attached = {(a["inventory"], a["entry"]) for u in extra for a in u["inventories"]}
    unmatched = [r for r in unmatched if (r["inventory"], r["entry"]) not in attached]
    ledger, unmatched, errors = decisions.place_inventories(
        [*ledger, *extra],
        unmatched,
        [p for p in given.placements if p["witness"] in units.QUOTED],
    )
    require(not errors, f"Byzantine placements of Greek apparatus rows: {errors}")
    unplaced = [
        f"{r['inventory']} {r['entry']} at {r['target_ref']}"
        for r in unmatched
        if r["inventory"] in units.QUOTED
    ]
    require(
        not unplaced,
        f"Rows of the Greek apparatuses that give the Received Text a reading at no unit: {unplaced}",
    )
    evidenced(corrections, ledger, tcgnt, printed_apparatus)
    ledger = decisions.with_hodges_farstad(ledger, given.decisions["hodges-farstad"])
    tr_alignment = greek.accented_scrivener(
        given.sources["accented_tr"], tr, corrections
    )
    return Greek(
        structure=structure,
        tr=MappingProxyType(tr),
        tr_alignment=tr_alignment,
        rp=MappingProxyType(rp),
        rp_alignment=rp_alignment,
        printed=MappingProxyType(printed),
        tr_tags=MappingProxyType(checked),
        rp_tags=MappingProxyType(tags),
        alternates=MappingProxyType(
            greek.marginal_alternates(given.sources["rp_margin"])
        ),
        collation=tuple(collation),
        tcgnt=tuple(tcgnt),
        apparatus=tuple(printed_apparatus),
        units=tuple(ledger),
        unmatched=tuple(unmatched),
        annotation_mismatches=tuple(mismatches),
    )


def stage_english(given: Inputs, greek_: Greek) -> English:
    """The KJV and the three English witnesses, and the CrossWire bridge."""
    documents, verses, subscriptions = english.kjv(given.kjv)
    kjv = {ref: v.text for ref, v in verses.items()}
    rv_documents, rv = english.rv(given.sources["rv"])
    asv_documents, asv = english.asv(given.sources["asv"])
    boyd_documents, boyd = english.boyd_asv(given.sources["boyd_asv"])
    revision_citations: dict[str, Mapping[str, Citation | None]] = {
        name: {
            ref: english.citation_metadata(docs[ref.split()[0]], verse)
            for ref, verse in rows.items()
        }
        for name, docs, rows in (
            (RV, rv_documents, rv),
            ("asv", asv_documents, asv),
            (BOYD_ASV, boyd_documents, boyd),
        )
    }
    revision_citations[BOYD_ASV] = revisers.at_kjv_addresses(
        revision_citations[BOYD_ASV], kjv, greek_.structure, missing=None
    )
    aligned_source = crosswire.crosswire(given.sources["crosswire"])
    aligned, bridge_failures = crosswire.bridge(aligned_source, greek_.tr, kjv)
    supplied: dict[str, list[tuple[int, int, str]]] = {}
    for ref, verse in verses.items():
        found = english.supplied_spans(documents[ref.split()[0]], verse)
        if found:
            supplied[ref] = found
    return English(
        documents=MappingProxyType(documents),
        subscriptions=MappingProxyType(subscriptions),
        kjv=MappingProxyType(kjv),
        supplied=MappingProxyType(supplied),
        revision_citations=MappingProxyType(revision_citations),
        texts=MappingProxyType(
            {
                RV: {r: v.text for r, v in rv.items()},
                "asv": {r: v.text for r, v in asv.items()},
                BOYD_ASV: revisers.at_kjv_addresses(
                    {r: v.text for r, v in boyd.items()}, kjv, greek_.structure
                ),
            }
        ),
        aligned=MappingProxyType(aligned),
        bridge_failures=MappingProxyType(bridge_failures),
        crosswire=MappingProxyType(aligned_source),
    )


def stage_reports(given: Inputs, greek_: Greek) -> Apparatuses:
    """The modern-English apparatuses attached to units."""
    tcent = inventories.tcent(given.sources["tcent"])
    faa_rows = apparatus.faa(given.sources["faa"])
    structure = greek_.structure
    boyd_reports = apparatus.tcent_reports(tcent, greek_.tcgnt, greek_.units, structure)
    faa_reports = apparatus.faa_reports(
        faa_rows, greek_.tr, greek_.rp, greek_.units, structure
    )
    # The editor's placements of the Greek-bound apparatuses come first: the
    # selected lists inherit their locations from them.
    anchors, errors_a, stale_a = decisions.place(
        [*boyd_reports, *faa_reports],
        greek_.units,
        [p for p in given.placements if p["witness"] in {TCENT, FAA}],
    )
    selected, errors_s, stale_s = decisions.place(
        apparatus.attach_contrasts(
            [
                *apparatus.msb(
                    given.sources["msb"], given.sources["msb_tables"], structure
                ),
                *apparatus.web(given.sources["web"], structure),
            ],
            [r for r in anchors if r["witness"] == FAA],
            [r for r in anchors if r["witness"] == TCENT],
        ),
        greek_.units,
        [
            p
            for p in given.placements
            if p["witness"] not in {TCENT, FAA, *INSTRUCTION_SOURCES, *units.QUOTED}
        ],
    )
    fitting([*errors_a, *errors_s], [*stale_a, *stale_s])
    return Apparatuses(
        faa_rows=MappingProxyType(faa_rows), reports=(*anchors, *selected)
    )


def checker(greek_: Greek, english_: English) -> rendering.Checker:
    """The check that an instruction's English renders RP2026's Greek, from
    the pinned texts and their tags, for the instructions and decisions
    stages."""
    return rendering.Checker(
        english_.crosswire,
        english_.aligned,
        greek_.tr,
        greek_.rp,
        greek_.tr_tags,
        greek_.rp_tags,
        greek_.units,
        english_.kjv,
        greek_.structure,
        greek_.alternates,
    )


def stage_instructions(
    given: Inputs,
    greek_: Greek,
    english_: English,
    apparatuses: Apparatuses,
    check: rendering.Checker,
) -> Instructions:
    """The KJV-worded instruction source, bound, attached and checked."""
    kjv = english_.kjv
    inventory = pierpont.read(given.sources["pierpont"].read_text(), kjv)
    rows = pierpont.instructions(inventory, kjv)
    # An objective apparatus placement also corrects the evidence used by an
    # instruction's contrast fallback.
    rows = instructions.attach(
        rows,
        greek_.units,
        english_.aligned,
        [r for r in apparatuses.reports if r["witness"] in {TCENT, FAA}],
    )
    rows, errors, stale = decisions.place(
        rows,
        greek_.units,
        [p for p in given.placements if p["witness"] in INSTRUCTION_SOURCES],
    )
    fitting(errors, stale)
    by_id = {u["id"]: u for u in greek_.units}
    return Instructions(
        inventory=inventory,
        rows=tuple(
            {
                **row,
                **instructions.compatibility(row, by_id, kjv, english_.supplied, check),
            }
            for row in rows
        ),
    )


def stage_revisions(
    greek_: Greek, english_: English, instructions_: Instructions
) -> Revisions:
    """The RV and Boyd's ASV as witnesses, and the revision alarm."""
    kjv, aligned, ledger = english_.kjv, english_.aligned, greek_.units
    admitted = revisers.readable(ledger, greek_.tcgnt)
    texts = english_.texts
    rows = [
        *revisers.revision_reports(
            RV,
            kjv,
            texts[RV],
            aligned,
            ledger,
            admitted[RV],
            instructions=instructions_.rows,
        ),
        *revisers.revision_reports(
            BOYD_ASV,
            kjv,
            texts[BOYD_ASV],
            aligned,
            ledger,
            admitted[BOYD_ASV],
            base=texts["asv"],
            instructions=instructions_.rows,
        ),
    ]
    return Revisions(
        rows=tuple(rows),
        admitted=MappingProxyType({k: frozenset(v) for k, v in admitted.items()}),
        alarms=MappingProxyType(
            revisers.alarms(
                ledger, aligned, kjv, {RV: texts[RV], BOYD_ASV: texts[BOYD_ASV]}
            )
        ),
    )


def stage_decisions(
    given: Inputs,
    greek_: Greek,
    english_: English,
    apparatuses: Apparatuses,
    instructions_: Instructions,
    check: rendering.Checker,
) -> Decisions:
    """The editor's readings and lemmas, validated against the placed rows."""
    ledger, kjv = greek_.units, english_.kjv
    readings = [
        {"id": key, **entry} for key, entry in given.decisions["readings"].items()
    ]
    overrides, errors_o = decisions.validate_overrides(
        readings,
        ledger,
        kjv,
        decisions.witness_rows(apparatuses.reports, instructions_.rows),
        english_.texts,
        english_.supplied,
        revision_citations=english_.revision_citations,
        faa_rows=apparatuses.faa_rows,
        printed=greek_.printed,
        alignment=greek_.rp_alignment,
        structure=greek_.structure,
    )
    # Judge and choose instructions by construction, never in parts.
    rows = instructions.constructions(instructions_.rows, kjv, check, overrides)
    # One override owns a construction: two that take one must be merged.
    errors_c = sorted(
        {
            f"{r['construction']}: taken by overrides {' and '.join(r['displaced_by'])}; merge them into one"
            for r in rows
            if len(r.get("displaced_by") or []) > 1
        }
    )
    lemmas = decisions.lemma_entries(given.decisions["lemmas"])
    errors_l = decisions.validate_lemmas(lemmas, ledger)
    fitting([*errors_o, *errors_c, *errors_l])
    return Decisions(
        instructions=tuple(rows), overrides=tuple(overrides), lemmas=tuple(lemmas)
    )


def stage_decide(
    greek_: Greek,
    english_: English,
    apparatuses: Apparatuses,
    revisions: Revisions,
    decisions_: Decisions,
) -> tuple[Disposition, ...]:
    """One disposition per unit. A reading the build would carry out alike
    without it stops the build."""
    rows = decide.decide(
        greek_.units,
        decisions_.instructions,
        apparatuses.reports,
        revisions.rows,
        decisions_.overrides,
        revisions.alarms,
        english_.kjv,
        supplied=english_.supplied,
    )
    redundant = sorted(
        row["override"] for row in rows if row.get("redundant") and row.get("override")
    )
    require(not redundant, f"Byzantine readings that change nothing: {redundant}")
    return tuple(rows)


def stage_edit(
    greek_: Greek,
    english_: English,
    decisions_: Decisions,
    dispositions: Sequence[Disposition],
) -> Edited:
    """Apply the dispositions to the KJV, then the structural changes, then
    finish the notes. A reading the build could not carry out stops it."""
    documents = english_.documents
    prepared, rows = edit.execute(documents, dispositions, BOOKS)
    prepared, rows = edit.structural(prepared, rows, greek_.structure)
    prepared, rows = notes.apply(documents, prepared, rows, decisions_.lemmas)
    refused = sorted(row["unit"] for row in rows if row.get("execution") == "refused")
    require(not refused, f"Byzantine readings the build could not carry out: {refused}")
    # Say where the executor mended punctuation beside the edited words;
    # capitals it changes there are not tagged.
    rows = [
        (
            tagged(row, Tag.EV_SEAM_ADJUSTED)
            if any(
                seam["rule"] == 2 and seam.get("from", "").strip(" ")
                for e in row.get("edits", [])
                for seam in e.get("seams", [])
            )
            else row
        )
        for row in rows
    ]
    witnesses = received.labels(
        rows, greek_.units, received.rows(greek_.tcgnt, greek_.apparatus)
    )
    return Edited(
        prepared=MappingProxyType(prepared),
        note_witnesses=MappingProxyType(witnesses),
        dispositions=tuple(rows),
    )


def stage_verify(
    greek_: Greek, english_: English, decisions_: Decisions, edited: Edited
) -> Verified:
    """Check the invariants on what was prepared, and flag each disposition
    with the problems of the verses it edited. A broken invariant, or a note
    that does not give back the King James words, stops the build."""
    results = verify.checks(
        english_.documents,
        edited.prepared,
        greek_.units,
        edited.dispositions,
        greek_.structure,
        decisions_.lemmas,
    )
    problems = verify.finished_verses(
        english_.documents, edited.prepared, edited.dispositions, greek_.structure
    )
    verify.held(results, problems)
    return Verified(
        invariants=MappingProxyType(results),
        finished=MappingProxyType(problems),
        dispositions=verify.flagged(edited.dispositions, problems),
    )
