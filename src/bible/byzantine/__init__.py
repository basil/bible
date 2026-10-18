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
and write the review (review) and the textual variants (variants).

`reconciled` runs the stages (stages) in the order of their dependencies on
the sources the read stage parsed, each a function of the results before it
and stopping the build on what does not hold, and gathers their results as
the Reconciliation; `promoted` gives one book as the promote stage prints it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from bible import usj
from bible.sources import NEW_TESTAMENT, Content
from bible.usj import Document

if TYPE_CHECKING:
    from bible.byzantine.stages import Reconciliation
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


def reconciled(
    inputs: Mapping[str, Content],
    kjv: Mapping[str, Document],
    decisions: Mapping[str, Any],
    placements: Mapping[str, Any],
) -> Reconciliation:
    """Every stage of the reconciliation, in order, from the read sources and
    the editor's decisions (edition/byzantine.json, thawed) and placements
    (edition/byzantine-placements.json, thawed): everything it worked out,
    for the promotion, the review and the variants, by the stage that made
    it (stages.Reconciliation). Each stage stops the build on a decision
    that does not fit its source or changes nothing, a placement the code
    now makes on its own, a reading it could not carry out, a broken
    invariant, or a note that does not give back the King James words."""
    from bible.byzantine import stages

    given = stages.inputs(inputs, kjv, decisions, placements)
    greek = stages.stage_greek(given)
    english = stages.stage_english(given, greek)
    apparatuses = stages.stage_reports(given, greek)
    check = stages.checker(greek, english)
    instructions = stages.stage_instructions(given, greek, english, apparatuses, check)
    revisions = stages.stage_revisions(greek, english, instructions)
    decided = stages.stage_decisions(
        given, greek, english, apparatuses, instructions, check
    )
    dispositions = stages.stage_decide(greek, english, apparatuses, revisions, decided)
    edited = stages.stage_edit(greek, english, decided, dispositions)
    verified = stages.stage_verify(greek, english, decided, edited)
    return stages.Reconciliation(
        inputs=given,
        greek=greek,
        english=english,
        apparatuses=apparatuses,
        instructions=instructions,
        revisions=revisions,
        decisions=decided,
        edited=edited,
        verified=verified,
    )


def promoted(code: str, found: Reconciliation, terms: Registry) -> Document:
    """A King James book with the Byzantine readings in it and the notes on
    them in the edition's form, labelled with the abbreviation of the witness
    they name (received.labels), and its subscription put back after its
    verses."""
    from bible.byzantine import notes

    doc = notes.for_edition(
        found.edited.prepared[code], terms, found.edited.note_witnesses
    )
    tail = found.english.subscriptions.get(code, ())
    if not tail:
        return doc
    return usj.with_blocks(doc, [*doc["content"], *tail])
