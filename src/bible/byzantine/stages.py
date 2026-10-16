"""The stages of the reconciliation, each adding to a context what it worked
out from the stages before it, in the order of the modules' dependencies."""

from __future__ import annotations

import collections
from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypedDict

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
)
from bible.byzantine import revisers as revisions
from bible.byzantine import units, verify
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
    Unit,
    Unmatched,
)
from bible.byzantine.tags import Tag, retag
from bible.checks import require
from bible.references import parse_passage
from bible.scripture import Verse
from bible.sources import Content
from bible.usj import Document, Node


class Context(TypedDict, total=False):
    """What the reconciliation has worked out, by name: its inputs, then
    what each stage adds."""

    # The inputs: the read sources, the King James books, and the editor's
    # decisions (edition/byzantine.json) and placements
    # (edition/byzantine-placements.json), thawed.
    source_inputs: Mapping[str, Content]
    kjv_documents: Mapping[str, Document]
    decisions: Mapping[str, Any]
    placements: list[Placement]
    # stage_greek: the Greek texts and the unit ledger.
    structure: greek.Structure
    tr: greek.Text
    tr_accented: greek.Text
    tr_alignment: greek.Alignment
    rp_alignment: greek.Alignment
    rp: greek.Text
    rp_tags: greek.Tags
    tr_tags: greek.Tags
    printed: dict[str, greek.PrintedVerse]
    printed_xml: Content
    collation: list[CollationRow]
    tcgnt: list[BoydNote]
    apparatus: list[BoydNote]
    units: list[Unit]
    unmatched: list[Unmatched]
    annotation_mismatches: list[str]
    # stage_english: the King James books and verses, the revisions' texts,
    # and the CrossWire bridge.
    documents: dict[str, Document]
    subscriptions: dict[str, list[Node]]
    verses: dict[str, Verse]
    kjv: dict[str, str]
    supplied: dict[str, list[tuple[int, int, str]]]
    revision_citations: dict[str, dict[str, Citation | None]]
    texts: dict[str, dict[str, str]]
    aligned: dict[str, Aligned]
    bridge_failures: dict[str, str]
    crosswire: dict[str, Tagged]
    # stage_reports: the apparatuses.
    faa_rows: dict[str, FaaRow]
    reports: list[Report]
    placement_errors: list[str]
    stale_placements: list[Placement]
    # stage_instructions: Pierpont's booklet and its instructions.
    checker: rendering.Checker
    pierpont_inventory: pierpont.Inventory
    instructions: list[Instruction]
    # stage_revisions: the revisions as witnesses.
    revision_rows: list[RevisionRow]
    revision_admitted: dict[str, set[str]]
    alarms: dict[str, Alarm]
    # stage_decisions: the editor's decisions, validated and applied.
    overrides: list[Override]
    note_lemmas: list[dict[str, Any]]
    decision_errors: list[str]
    witness_rows: dict[str, dict[int | str, Report | Instruction]]
    # stage_decide, stage_edit and stage_verify: the dispositions, the books with the
    # dispositions carried out, and the checks.
    dispositions: list[Disposition]
    prepared: dict[str, Document]
    note_witnesses: dict[str, str]
    invariants: dict[str, str]
    finished: dict[str, list[str]]


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


def stage_greek(context: Context) -> None:
    """The Greek texts and the unit ledger."""
    corrections = context["decisions"].get("scrivener", {})
    tr = greek.corrected(
        greek.scrivener(context["source_inputs"]["scrivener"]), corrections
    )
    parsed, tr_tags = greek.parsed_scrivener(context["source_inputs"]["parsed_tr"])
    mismatches = [ref for ref in tr if parsed[ref] != tr[ref]]
    checked = {f"TR {ref}": t for ref, t in tr_tags.items() if ref not in mismatches}
    rp, tags = greek.rp2018(context["source_inputs"]["rp2018"])
    structure = structure_of(context["decisions"]["structure"], tr, rp)
    xml = context["source_inputs"]["rp2026"]
    root = greek.tree(xml)
    printed, diacritics = greek.printed(root, structure.omitted, list(rp)[-1])
    rp = greek.rp2026(rp, printed)
    collation = inventories.collation(context["source_inputs"]["collation"])
    notes_ = inventories.boyd(context["source_inputs"]["tcgnt"])
    require(len(notes_) == 1948, f"TCGNT inventory: {len(notes_)}, expected 1948")
    splits = inventories.word_breaks(context["source_inputs"]["tcgnt"] / "095XXC.usx")
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
        notes_,
        {**checked, **tags},
        splits,
        structure,
        printed_apparatus,
    )
    extra = units.supplementary_units(
        tr,
        rp,
        collation,
        notes_,
        printed,
        diacritics,
        structure,
        context["decisions"]["accents"],
        rp_alignment,
        printed_apparatus,
    )
    attached = {(a["inventory"], a["entry"]) for u in extra for a in u["inventories"]}
    unmatched = [r for r in unmatched if (r["inventory"], r["entry"]) not in attached]
    ledger, unmatched, errors = decisions.place_inventories(
        [*ledger, *extra],
        unmatched,
        [p for p in context["placements"] if p["witness"] in units.QUOTED],
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
    evidenced(corrections, ledger, notes_, printed_apparatus)
    ledger = decisions.with_hodges_farstad(
        ledger, context["decisions"]["hodges-farstad"]
    )
    tr_alignment = greek.accented_scrivener(
        context["source_inputs"]["accented_tr"], tr, corrections
    )
    context.update(
        {
            "structure": structure,
            "tr": tr,
            "tr_accented": tr_alignment.text,
            "tr_alignment": tr_alignment,
            "rp_alignment": rp_alignment,
            "rp": rp,
            "rp_tags": tags,
            "tr_tags": checked,
            "printed": printed,
            "printed_xml": xml,
            "collation": collation,
            "tcgnt": notes_,
            "apparatus": printed_apparatus,
            "units": ledger,
            "unmatched": unmatched,
            "annotation_mismatches": mismatches,
        }
    )


def stage_english(context: Context) -> None:
    """The KJV and the three English witnesses, and the CrossWire bridge."""
    documents, verses, subscriptions = english.kjv(context["kjv_documents"])
    kjv = {ref: v.text for ref, v in verses.items()}
    rv_documents, rv = english.rv(context["source_inputs"]["rv"])
    asv_documents, asv = english.asv(context["source_inputs"]["asv"])
    boyd_documents, boyd = english.boyd_asv(context["source_inputs"]["boyd_asv"])
    revision_citations: dict[str, dict[str, Citation | None]] = {
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
    revision_citations[BOYD_ASV] = revisions.at_kjv_addresses(
        revision_citations[BOYD_ASV], kjv, context["structure"], missing=None
    )
    aligned_source = crosswire.crosswire(context["source_inputs"]["crosswire"])
    aligned, bridge_failures = crosswire.bridge(aligned_source, context["tr"], kjv)
    supplied: dict[str, list[tuple[int, int, str]]] = {}
    for ref, verse in verses.items():
        found = english.supplied_spans(documents[ref.split()[0]], verse)
        if found:
            supplied[ref] = found
    context.update(
        {
            "documents": documents,
            "subscriptions": subscriptions,
            "verses": verses,
            "kjv": kjv,
            "supplied": supplied,
            "revision_citations": revision_citations,
            "texts": {
                RV: {r: v.text for r, v in rv.items()},
                "asv": {r: v.text for r, v in asv.items()},
                BOYD_ASV: revisions.at_kjv_addresses(
                    {r: v.text for r, v in boyd.items()}, kjv, context["structure"]
                ),
            },
            "aligned": aligned,
            "bridge_failures": bridge_failures,
            "crosswire": aligned_source,
        }
    )


def stage_reports(context: Context) -> None:
    """The modern-English apparatuses attached to units."""
    tcent = inventories.tcent(context["source_inputs"]["tcent"])
    faa_rows = apparatus.faa(context["source_inputs"]["faa"])
    structure = context["structure"]
    boyd_reports = apparatus.tcent_reports(
        tcent, context["tcgnt"], context["units"], structure
    )
    faa_reports = apparatus.faa_reports(
        faa_rows, context["tr"], context["rp"], context["units"], structure
    )
    # The editor's placements of the Greek-bound apparatuses come first: the
    # selected lists inherit their locations from them.
    anchors, errors_a, stale_a = decisions.place(
        [*boyd_reports, *faa_reports],
        context["units"],
        [p for p in context["placements"] if p["witness"] in {TCENT, FAA}],
    )
    selected, errors_s, stale_s = decisions.place(
        apparatus.attach_contrasts(
            [
                *apparatus.msb(
                    context["source_inputs"]["msb"],
                    context["source_inputs"]["msb_tables"],
                    structure,
                ),
                *apparatus.web(context["source_inputs"]["web"], structure),
            ],
            [r for r in anchors if r["witness"] == FAA],
            [r for r in anchors if r["witness"] == TCENT],
        ),
        context["units"],
        [
            p
            for p in context["placements"]
            if p["witness"] not in {TCENT, FAA, *INSTRUCTION_SOURCES, *units.QUOTED}
        ],
    )
    context.update(
        {
            "faa_rows": faa_rows,
            "reports": [*anchors, *selected],
            "placement_errors": [*errors_a, *errors_s],
            "stale_placements": [*stale_a, *stale_s],
        }
    )


def stage_instructions(context: Context) -> None:
    """The KJV-worded instruction source, bound, attached and checked."""
    kjv = context["kjv"]
    inventory = pierpont.read(context["source_inputs"]["pierpont"].read_text(), kjv)
    rows = pierpont.instructions(inventory, kjv)
    # An objective apparatus placement also corrects the evidence used by an
    # instruction's contrast fallback.
    rows = instructions.attach(
        rows,
        context["units"],
        context["aligned"],
        [r for r in context["reports"] if r["witness"] in {TCENT, FAA}],
    )
    rows, errors, stale = decisions.place(
        rows,
        context["units"],
        [p for p in context["placements"] if p["witness"] in INSTRUCTION_SOURCES],
    )
    by_id = {u["id"]: u for u in context["units"]}
    context["checker"] = rendering.Checker(
        context["crosswire"],
        context["aligned"],
        context["tr"],
        context["rp"],
        context["tr_tags"],
        context["rp_tags"],
        context["units"],
        kjv,
        context["structure"],
        greek.marginal_alternates(context["source_inputs"]["rp_margin"]),
    )
    for row in rows:
        row["compatibility"], row["compatibility_reason"] = instructions.compatibility(
            row, by_id, kjv, context["supplied"], context["checker"]
        )
    context.update(
        {
            "pierpont_inventory": inventory,
            "instructions": rows,
            "placement_errors": [*context["placement_errors"], *errors],
            "stale_placements": [*context["stale_placements"], *stale],
        }
    )


def stage_revisions(context: Context) -> None:
    """The RV and Boyd's ASV as witnesses, and the revision alarm."""
    kjv, aligned, ledger = context["kjv"], context["aligned"], context["units"]
    admitted = revisions.readable(ledger, context["tcgnt"])
    texts = context["texts"]
    placed = context["instructions"]
    rows = [
        *revisions.revision_reports(
            RV,
            kjv,
            texts[RV],
            aligned,
            ledger,
            admitted[RV],
            instructions=placed,
        ),
        *revisions.revision_reports(
            BOYD_ASV,
            kjv,
            texts[BOYD_ASV],
            aligned,
            ledger,
            admitted[BOYD_ASV],
            base=texts["asv"],
            instructions=placed,
        ),
    ]
    context.update(
        {
            "revision_rows": rows,
            "revision_admitted": admitted,
            "alarms": revisions.alarms(
                ledger, aligned, kjv, {RV: texts[RV], BOYD_ASV: texts[BOYD_ASV]}
            ),
        }
    )


def stage_decisions(context: Context) -> None:
    """The editor's readings and lemmas, validated against the placed rows."""
    ledger, kjv = context["units"], context["kjv"]
    reports, rows = context["reports"], context["instructions"]
    witness_rows: dict[str, dict[int | str, Report | Instruction]] = {}
    for r in reports:
        witness_rows.setdefault(r["witness"], {})[r["entry"]] = r
    for row in rows:
        witness_rows.setdefault(row["source"], {})[row["entry"]] = row
    readings = [
        {"id": key, **entry} for key, entry in context["decisions"]["readings"].items()
    ]
    overrides, errors_o = decisions.validate_overrides(
        readings,
        ledger,
        kjv,
        witness_rows,
        context["texts"],
        context["supplied"],
        revision_citations=context["revision_citations"],
        faa_rows=context["faa_rows"],
        printed=context["printed"],
        alignment=context["rp_alignment"],
        structure=context["structure"],
    )
    # Judge and choose instructions by construction, never in parts.
    rows = instructions.constructions(rows, kjv, context["checker"], overrides)
    # One override owns a construction: two that take one must be merged.
    errors_c = sorted(
        {
            f"{r['construction']}: taken by overrides {' and '.join(r['displaced_by'])}; merge them into one"
            for r in rows
            if len(r.get("displaced_by") or []) > 1
        }
    )
    lemmas = decisions.lemma_entries(context["decisions"]["lemmas"])
    errors_l = decisions.validate_lemmas(lemmas, ledger)
    context.update(
        {
            "instructions": rows,
            "overrides": overrides,
            "note_lemmas": lemmas,
            "decision_errors": [
                *context["placement_errors"],
                *errors_o,
                *errors_c,
                *errors_l,
            ],
            "witness_rows": witness_rows,
        }
    )


def stage_decide(context: Context) -> None:
    """One disposition per unit."""
    rows = decide.decide(
        context["units"],
        context["instructions"],
        context["reports"],
        context["revision_rows"],
        context["overrides"],
        context["alarms"],
        context["kjv"],
        supplied=context["supplied"],
    )
    context["dispositions"] = rows


def stage_edit(context: Context) -> None:
    """Apply the dispositions to the KJV, then the structural changes, then
    finish the notes."""
    documents, rows = context["documents"], context["dispositions"]
    by_entry = {(i["source"], i["entry"]): i for i in context["instructions"]}
    for row in rows:
        selected = row.get("selected")
        if selected:
            i = by_entry[(selected["source"], selected["entry"])]
            row["readings"] = [i.get("quotation") or ""]
    prepared, rows = edit.execute(documents, rows, BOOKS)
    prepared, rows = edit.structural(prepared, rows, context["structure"])
    prepared, rows = notes.apply(documents, prepared, rows, context["note_lemmas"])
    # Say where the executor mended punctuation beside the edited words;
    # capitals it changes there are not tagged.
    for row in rows:
        seams = [
            seam
            for e in row.get("edits", [])
            for seam in e.get("seams", [])
            if seam["rule"] == 2 and seam.get("from", "").strip(" ")
        ]
        if seams:
            retag(row, Tag.EV_SEAM_ADJUSTED)
    witnesses = received.labels(
        rows, context["units"], received.rows(context["tcgnt"], context["apparatus"])
    )
    context.update(
        {"prepared": prepared, "dispositions": rows, "note_witnesses": witnesses}
    )


def stage_verify(context: Context) -> None:
    """Check the invariants on what was prepared."""
    results = verify.checks(
        context["documents"],
        context["prepared"],
        context["units"],
        context["dispositions"],
        context["structure"],
        context["note_lemmas"],
    )
    problems = verify.finished_verses(
        context["documents"],
        context["prepared"],
        context["dispositions"],
        context["structure"],
    )
    for row in context["dispositions"]:
        refs = {e["ref"] for e in row.get("edits", [])}
        cause = "correction:" if row["disposition"] == "shared" else "variant:"
        found = [
            p
            for ref in sorted(refs)
            for p in problems.get(ref, [])
            if p.startswith(cause)
        ]
        if found:
            row["flags"] = [
                *row.get("flags", []),
                *(f"finished verse: {p}" for p in found),
            ]
            retag(row, Tag.EV_FINISHED_VERSE)
    context.update({"invariants": results, "finished": problems})


STAGES: tuple[Callable[[Context], None], ...] = (
    stage_greek,
    stage_english,
    stage_reports,
    stage_instructions,
    stage_revisions,
    stage_decisions,
    stage_decide,
    stage_edit,
    stage_verify,
)
