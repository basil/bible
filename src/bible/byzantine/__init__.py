"""The King James New Testament conformed to the Byzantine text of Robinson
and Pierpont (2026).

Scrivener's reconstruction of the Received Text the King James translators
followed and RP2026 differ in some 1,900 places. The modules here read the
pinned Greek texts and the published witnesses to which differences show in
English and how (greek, inventories, units, english, crosswire, apparatus,
pierpont, instructions, revisers, rendering), validate the editor's decisions
against them (decisions), give every difference one disposition (decide),
carry the edits and the structural changes out on the King James books
(edit), set the Textus Receptus footnotes (notes), check the result (verify),
and write the review (review) and the appendix of readings (appendix).

`reconciled` runs them in the order of their dependencies on the sources the
read stage parsed; `promoted` gives one book as the promote stage prints it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from bible.byzantine.rows import Placement
from bible.sources import NEW_TESTAMENT, Content
from bible.usj import Document

if TYPE_CHECKING:
    from bible.byzantine.stages import Context
    from bible.terminology import Registry

# USFM book codes in canonical order.
BOOKS = NEW_TESTAMENT
# The books by their English names.
BOOKS_BY_NAME = dict(
    zip(
        (
            "Matthew|Mark|Luke|John|Acts|Romans|1 Corinthians|2 Corinthians|Galatians|"
            "Ephesians|Philippians|Colossians|1 Thessalonians|2 Thessalonians|1 Timothy|"
            "2 Timothy|Titus|Philemon|Hebrews|James|1 Peter|2 Peter|1 John|2 John|3 John|"
            "Jude|Revelation"
        ).split("|"),
        BOOKS,
        strict=True,
    )
)

# Witness identifiers, used everywhere a source is named: ledger rows, the
# evidence of a reading, tags and the review.
PIERPONT = "pierpont"  # Pierpont, Some Improvements to the KJV (1990)
ADDITIONAL = "additional"  # a second KJV-worded instruction source; none is read
TCENT = "tcent"  # Boyd, Text-Critical English New Testament apparatus
FAA = "faa"  # Thomason, Far Above All translation with TR variants
MSB = "msb"  # Majority Standard Bible footnotes
WEB = "web"  # World English Bible footnotes
RV = "rv"  # Revised Version of 1881
BOYD_ASV = "boyd-asv"  # Boyd's ASV conformed to RP2018 (2021)
INSTRUCTION_SOURCES = (PIERPONT, ADDITIONAL)  # in order of precedence
APPARATUS = (TCENT, FAA, MSB, WEB)
REVISIONS = (RV, BOYD_ASV)
WITNESSES = (*INSTRUCTION_SOURCES, *APPARATUS, *REVISIONS)


@dataclass(frozen=True)
class Reconciled:
    """Everything the reconciliation worked out, for the promotion, the
    review and the appendix: the Greek ledger, the witnesses attached to it,
    the dispositions, and the King James books with the dispositions carried
    out (before their subscriptions are put back), by the names the
    stages give them (stages.Context)."""

    context: Context


def reconciled(
    inputs: Mapping[str, Content],
    kjv: Mapping[str, Document],
    decisions: Mapping[str, Any],
    placements: Mapping[str, Any],
) -> Reconciled:
    """Every stage of the reconciliation, in order, from the read sources and
    the editor's decisions (edition/byzantine.json, thawed) and placements
    (edition/byzantine-placements.json, thawed)."""
    from bible.byzantine import stages

    placed: list[Placement] = []
    for key, entry in placements["placements"].items():
        witness, _, number = key.partition(" ")
        placement: Placement = {
            "witness": witness,
            "entry": int(number) if number.isdigit() else number,
        }
        placement.update(entry)
        placed.append(placement)
    context: Context = {
        "source_inputs": inputs,
        "kjv_documents": kjv,
        "decisions": decisions,
        "placements": placed,
    }
    for stage in stages.STAGES:
        stage(context)
    checked(context)
    return Reconciled(context)


def checked(context: Context) -> None:
    """The reconciliation holds to its decisions and its invariants: a
    decision that does not fit its source, a placement the code now makes
    on its own, a reading the build would carry out alike without it, an
    instruction it could not carry out, a broken invariant, or an "Or,"
    note that does not give back the King James words stops the build and
    names itself."""
    from bible.byzantine.verify import UNRESTORED_RENDERING
    from bible.checks import require

    require(
        not context["decision_errors"],
        f"Byzantine decisions that do not fit their sources: {context['decision_errors'][:5]}",
    )
    stale = [f"{p['witness']} {p['entry']}" for p in context["stale_placements"]]
    require(not stale, f"Byzantine placements the code now makes: {stale}")
    redundant = sorted(
        row["override"]
        for row in context["dispositions"]
        if row.get("redundant") and row.get("override")
    )
    require(not redundant, f"Byzantine readings that change nothing: {redundant}")
    refused = sorted(
        row["unit"]
        for row in context["dispositions"]
        if row.get("execution") == "refused"
    )
    require(not refused, f"Byzantine readings the build could not carry out: {refused}")
    failed = {k: v for k, v in context["invariants"].items() if v != "pass"}
    require(not failed, f"Byzantine invariants broken: {failed}")
    unrestored = sorted(
        ref
        for ref, problems in context["finished"].items()
        if any(p.startswith(UNRESTORED_RENDERING) for p in problems)
    )
    require(
        not unrestored,
        f"Rendering notes that do not restore the King James wording: {unrestored}",
    )


def promoted(code: str, found: Reconciled, terms: Registry) -> Document:
    """A King James book with the Byzantine readings in it and the Textus
    Receptus notes on them in the edition's form, labelled with the witness's
    abbreviation, and its subscription put back after its verses."""
    from bible import usj
    from bible.byzantine import notes

    doc = notes.for_edition(found.context["prepared"][code], terms)
    tail = found.context["subscriptions"].get(code, ())
    if not tail:
        return doc
    return usj.with_blocks(doc, [*doc["content"], *tail])
