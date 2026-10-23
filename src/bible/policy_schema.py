"""Shapes of the edition's JSON decisions after freezing.

Typing only: stages still validate these fields, and objects and lists remain
mapping proxies and tuples at runtime. Optional fields model decisions that
apply only to some entries; no defaults are introduced here.
"""

from collections.abc import Mapping
from typing import Literal, NotRequired, ReadOnly, TypedDict


class VersificationApocrypha(TypedDict, total=False):
    chapter: ReadOnly[int]
    edition: ReadOnly[str]
    kjv: ReadOnly[str | None]
    title: ReadOnly[str]


class Run(TypedDict, total=False):
    by: ReadOnly[str]
    edition: ReadOnly[str | None]
    kjv: ReadOnly[str | None]
    pairs: ReadOnly[Mapping[str, str]]
    why: ReadOnly[str]


class VersificationRelabel(TypedDict, total=False):
    edition: ReadOnly[str]
    opens: ReadOnly[Mapping[str, str]]
    why: ReadOnly[str]


class VersificationBreak(TypedDict, total=False):
    edition: ReadOnly[Mapping[str, str]]
    why: ReadOnly[str]


class VersificationStub(TypedDict, total=False):
    why: ReadOnly[str]


class VersificationRelocation(TypedDict, total=False):
    to: ReadOnly[str]
    why: ReadOnly[str]


class Versification(TypedDict, total=False):
    apocrypha: ReadOnly[tuple[VersificationApocrypha, ...]]
    books: ReadOnly[Mapping[str, str]]
    breaks: ReadOnly[Mapping[str, VersificationBreak]]
    kjv: ReadOnly[Mapping[str, tuple[Run, ...]]]
    old_testament: ReadOnly[tuple[str, ...]]
    readings: ReadOnly[Mapping[str, tuple[Run, ...]]]
    relabel: ReadOnly[Mapping[str, VersificationRelabel]]
    relocations: ReadOnly[Mapping[str, VersificationRelocation | str]]
    stubs: ReadOnly[Mapping[str, VersificationStub | str]]
    unnumbered: ReadOnly[Mapping[str, VersificationStub | str]]
    why: ReadOnly[str]


class PsalterNote(TypedDict):
    why: ReadOnly[str]


class Psalter(TypedDict):
    why: ReadOnly[str]
    kathismata: ReadOnly[tuple[tuple[int | str, ...], ...]]
    middle: ReadOnly[str]
    notes: ReadOnly[Mapping[str, PsalterNote]]


class ComparisonQuote(TypedDict):
    text: ReadOnly[str]
    highlights: ReadOnly[tuple[str, ...]]


class Comparison(TypedDict):
    passage: ReadOnly[str]
    kjv: ReadOnly[tuple[str, ...]]
    oleb: ReadOnly[tuple[str, ...]]
    osb: NotRequired[ReadOnly[ComparisonQuote]]


class Comparisons(TypedDict):
    why: ReadOnly[str]
    passages: ReadOnly[tuple[Comparison, ...]]


class LineBreak(TypedDict, total=False):
    follows: ReadOnly[str]
    line: ReadOnly[str | None]
    why: ReadOnly[str]


Paragraph = TypedDict(
    "Paragraph",
    {
        "at": ReadOnly[str],
        "from": ReadOnly[Literal["p", "m"]],
        "to": ReadOnly[Literal["p", "m", "join"]],
        "why": ReadOnly[str],
    },
)


class Lines(TypedDict, total=False):
    breaks: ReadOnly[Mapping[str, tuple[LineBreak, ...]]]
    prose: ReadOnly[Mapping[str, str]]
    unspaced: ReadOnly[Mapping[str, str]]
    paragraphs: ReadOnly[Mapping[str, tuple[Paragraph, ...]]]
    why: ReadOnly[str]


class Margin(TypedDict):
    why: ReadOnly[str]
    below: ReadOnly[Mapping[str, str]]


WordingChange = TypedDict(
    "WordingChange",
    {
        "from": ReadOnly[str],
        "note": ReadOnly[str],
        "spelling": ReadOnly[Literal["greek", "hebrew"]],
        "to": ReadOnly[str],
        "unit": ReadOnly[str],
        "why": ReadOnly[str],
    },
    total=False,
)


class AppendixNote(TypedDict, total=False):
    at: ReadOnly[str]
    before: ReadOnly[str]
    label: ReadOnly[str]
    paragraphs: ReadOnly[tuple[str, ...]]
    why: ReadOnly[str]


class Appendix(TypedDict, total=False):
    notes: ReadOnly[Mapping[str, AppendixNote]]
    source: ReadOnly[str]
    why: ReadOnly[str]


class QuotationsLxxToEdition(TypedDict, total=False):
    numbering: ReadOnly[str]
    target: ReadOnly[str]
    why: ReadOnly[str]


class QuotationsNarrowed(TypedDict, total=False):
    lxx: ReadOnly[str]
    why: ReadOnly[str]


class QuotationsNoteMerges(TypedDict, total=False):
    action: ReadOnly[str]
    drops: ReadOnly[tuple[str, ...]]
    why: ReadOnly[str]


class Quotations(TypedDict, total=False):
    class_conflicts: ReadOnly[tuple[ClassConflict, ...]]
    excluded: ReadOnly[Mapping[str, str]]
    lxx_to_edition: ReadOnly[Mapping[str, QuotationsLxxToEdition]]
    narrowed: ReadOnly[Mapping[str, QuotationsNarrowed]]
    note_merges: ReadOnly[Mapping[str, QuotationsNoteMerges]]


class ProseAddition(TypedDict):
    unit: ReadOnly[str]
    after: ReadOnly[str]
    # USJ paragraphs, frozen as the rest of the policy is.
    paragraphs: ReadOnly[tuple[Mapping[str, object], ...]]


# The marker a paragraph of front matter takes, by the words it opens with,
# or that a blank line takes, by the words of the paragraph after it.
MarkerChange = TypedDict(
    "MarkerChange",
    {
        "unit": ReadOnly[str],
        "from": ReadOnly[str],
        "to": ReadOnly[str],
        "opening": ReadOnly[str],
        "before": ReadOnly[str],
        "heading": ReadOnly[str],
        "why": ReadOnly[str],
    },
    total=False,
)


class ProseSection(TypedDict):
    unit: ReadOnly[str]
    before: ReadOnly[str]
    heading: ReadOnly[str]


class ProseItalicSpan(TypedDict):
    text: ReadOnly[str]
    within: ReadOnly[str]


class ProseItalics(TypedDict):
    unit: ReadOnly[str]
    opening: ReadOnly[str]
    spans: ReadOnly[tuple[str | ProseItalicSpan, ...]]


class ProseReference(TypedDict):
    unit: ReadOnly[str]
    after: ReadOnly[str]
    passages: ReadOnly[str]
    remove: NotRequired[ReadOnly[str]]


class ProseCaller(TypedDict):
    unit: ReadOnly[str]
    note: ReadOnly[str]
    after: ReadOnly[str]


ColophonChange = TypedDict(
    "ColophonChange",
    {"book": ReadOnly[str], "from": ReadOnly[str], "to": ReadOnly[str]},
)


class Prose(TypedDict, total=False):
    colophons: ReadOnly[tuple[ColophonChange, ...]]
    changes: ReadOnly[tuple[WordingChange, ...]]
    additions: ReadOnly[tuple[ProseAddition, ...]]
    markers: ReadOnly[tuple[MarkerChange, ...]]
    sections: ReadOnly[tuple[ProseSection, ...]]
    italics: ReadOnly[tuple[ProseItalics, ...]]
    references: ReadOnly[tuple[ProseReference, ...]]
    callers: ReadOnly[tuple[ProseCaller, ...]]
    why: ReadOnly[str]


Correction = TypedDict(
    "Correction",
    {
        "from": ReadOnly[str],
        "to": ReadOnly[str],
        "uncategorized": ReadOnly[bool],
        "why": ReadOnly[str],
    },
    total=False,
)


class NoteOverride(TypedDict, total=False):
    anchor: ReadOnly[str]
    former: ReadOnly[str]
    lemma: ReadOnly[str | None]
    note: ReadOnly[str | None]
    occurrence: ReadOnly[int]
    omitted: ReadOnly[bool]
    widen: ReadOnly[bool]
    sentence: ReadOnly[bool]
    quotation: ReadOnly[bool]
    uncategorized: ReadOnly[bool]
    verse: ReadOnly[str]
    why: ReadOnly[str]


Rendering = TypedDict(
    "Rendering",
    {
        "from": ReadOnly[str],
        "to": ReadOnly[str],
        "source_note": ReadOnly[str],
        "lemma": ReadOnly[str],
        "why": ReadOnly[str],
    },
)


class BrentonNotes(TypedDict, total=False):
    corrections: ReadOnly[Mapping[str, tuple[Correction, ...] | Correction]]
    notes: ReadOnly[Mapping[str, NoteOverride]]
    renderings: ReadOnly[Mapping[str, Rendering]]
    shapes: ReadOnly[Mapping[str, str]]


class Entry(TypedDict, total=False):
    abbreviated_singly: ReadOnly[str]
    abbreviation: ReadOnly[str]
    chapters: ReadOnly[tuple[int, ...]]
    cited_singly: ReadOnly[str]
    file: ReadOnly[str]
    heading: ReadOnly[tuple[tuple[str, str], ...]]
    id: ReadOnly[str]
    labelled_chapters: ReadOnly[bool]
    section: ReadOnly[str]
    short_title: ReadOnly[str]
    source: ReadOnly[str]
    source_id: ReadOnly[str]
    title: ReadOnly[str]


class ManifestExcluded(TypedDict, total=False):
    brenton: ReadOnly[tuple[str, ...]]


class Manifest(TypedDict, total=False):
    excluded: ReadOnly[ManifestExcluded]
    new_testament_front: ReadOnly[tuple[Entry, ...]]
    old_testament_front: ReadOnly[tuple[Entry, ...]]
    scripture: ReadOnly[tuple[Entry, ...]]
    title: ReadOnly[str]


class Witnesses(TypedDict, total=False):
    chapter: ReadOnly[str]
    id: ReadOnly[str]
    phrase: ReadOnly[str]


class Swete(TypedDict, total=False):
    agrees: ReadOnly[bool | None]
    evidence: ReadOnly[str]
    page: ReadOnly[int]
    reading: ReadOnly[str]
    volume: ReadOnly[int]


class EnglishEdit(TypedDict, total=False):
    span: ReadOnly[tuple[int, int]]
    to: ReadOnly[str]
    why: ReadOnly[str]


class English(TypedDict, total=False):
    edits: ReadOnly[tuple[EnglishEdit, ...]]
    source: ReadOnly[str]
    span: ReadOnly[tuple[int, int]]


class AlexandrinusPassagesInsertions(TypedDict, total=False):
    after: ReadOnly[str]
    before: ReadOnly[str]
    verses: ReadOnly[tuple[Decision, ...]]


class AlexandrinusPassagesMoves(TypedDict, total=False):
    label: ReadOnly[str]
    before: ReadOnly[str]
    verses: ReadOnly[str]


class AlexandrinusPassagesOmissions(TypedDict):
    verses: ReadOnly[tuple[str, ...]]
    note_target: ReadOnly[str]
    note: ReadOnly[str]
    source_notes: ReadOnly[Mapping[str, str]]
    swete: ReadOnly[Swete]
    why: ReadOnly[str]


AlexandrinusReadingsNoteEdits = TypedDict(
    "AlexandrinusReadingsNoteEdits",
    {
        "from": ReadOnly[str],
        "lemma": ReadOnly[str | None],
        "to": ReadOnly[str],
        "why": ReadOnly[str],
    },
    total=False,
)


class Alexandrinus(TypedDict, total=False):
    kept: ReadOnly[Mapping[str, Decision]]
    passages: ReadOnly[Mapping[str, Decision]]
    readings: ReadOnly[Mapping[str, Decision]]
    swete: ReadOnly[Mapping[str, str]]


class Terminology(TypedDict, total=False):
    display: ReadOnly[str]
    meaning: ReadOnly[str]
    note_forms: ReadOnly[tuple[str, ...]]
    note_term: ReadOnly[str]
    period_forms: ReadOnly[tuple[str, ...]]
    plural: ReadOnly[str]
    source_forms: ReadOnly[tuple[str, ...]]


class TurpieRowsAdditionalSourceHeadings(TypedDict, total=False):
    hebrew_normalized: ReadOnly[tuple[str, ...]]
    hebrew_printed: ReadOnly[tuple[str, ...]]
    lxx_normalized: ReadOnly[tuple[str, ...]]
    printed: ReadOnly[tuple[str, ...]]
    scope: ReadOnly[str]


class TurpieHeading(TypedDict, total=False):
    alternative_normalized: ReadOnly[tuple[str, ...]]
    evidence_pages: ReadOnly[tuple[int, ...]]
    normalized: ReadOnly[str | None]
    printed: ReadOnly[str]
    reference_location: ReadOnly[str]


TurpieRows = TypedDict(
    "TurpieRows",
    {
        "additional_source_headings": ReadOnly[TurpieRowsAdditionalSourceHeadings],
        "class": ReadOnly[str | None],
        "hebrew": ReadOnly[TurpieHeading],
        "id": ReadOnly[str],
        "kind": ReadOnly[str],
        "lxx": ReadOnly[TurpieHeading],
        "note": ReadOnly[str],
        "nt": ReadOnly[TurpieHeading],
        "part_markers": ReadOnly[tuple[str, ...]],
        "pdf_page": ReadOnly[int],
        "printed_sequence": ReadOnly[str],
        "source_headings": ReadOnly[str],
        "table_code": ReadOnly[str],
    },
    total=False,
)


class Turpie(TypedDict, total=False):
    edition: ReadOnly[str]
    pdf_page_numbering: ReadOnly[str]
    rows: ReadOnly[tuple[TurpieRows, ...]]
    transcription_scope: ReadOnly[str]


CitationsDecisions = TypedDict(
    "CitationsDecisions",
    {
        "not_a_citation": ReadOnly[bool],
        "numbering": ReadOnly[str],
        "passages": ReadOnly[str],
        "print": ReadOnly[str],
        "relative": ReadOnly[str],
        "source": ReadOnly[str],
        "unprinted": ReadOnly[bool],
        "why": ReadOnly[str],
    },
    total=False,
)


class CitationsDialects(TypedDict, total=False):
    books: ReadOnly[Mapping[str, str]]
    chapter_verse: ReadOnly[str]
    entries: ReadOnly[Mapping[str, str]]
    numbering: ReadOnly[str]
    numerals: ReadOnly[str]


class Citations(TypedDict, total=False):
    decisions: ReadOnly[
        Mapping[str, CitationsDecisions | tuple[CitationsDecisions, ...]]
    ]
    dialects: ReadOnly[Mapping[str, CitationsDialects]]
    units: ReadOnly[Mapping[str, str | None]]


# Functional, as except is a keyword.
RevisionsWords = TypedDict(
    "RevisionsWords",
    {
        "except": ReadOnly[tuple[str, ...]],
        "notes": ReadOnly[tuple[str, ...]],
        "scope": ReadOnly[Literal["scripture"]],
        "to": ReadOnly[str],
        "why": ReadOnly[str],
    },
    total=False,
)


class PunctuationRule(TypedDict, total=False):
    why: ReadOnly[str]


class NameKept(TypedDict, total=False):
    form: ReadOnly[str]
    verses: ReadOnly[tuple[str, ...]]
    who: ReadOnly[str]


class NameDecision(TypedDict, total=False):
    forms: ReadOnly[Mapping[str, tuple[str, ...]]]
    keep: ReadOnly[tuple[NameKept, ...]]
    to: ReadOnly[str]
    why: ReadOnly[str]


class Names(TypedDict, total=False):
    decisions: ReadOnly[Mapping[str, NameDecision]]
    why: ReadOnly[str]


class Ligatures(TypedDict, total=False):
    letters: ReadOnly[Mapping[str, str]]
    why: ReadOnly[str]


class Revisions(TypedDict, total=False):
    ligatures: ReadOnly[Ligatures]
    names: ReadOnly[Names]
    passages: ReadOnly[Mapping[str, Prose]]
    punctuation: ReadOnly[Mapping[str, PunctuationRule]]
    verses: ReadOnly[Mapping[str, RevisionGroup]]
    why: ReadOnly[str]
    words: ReadOnly[Mapping[str, RevisionsWords]]


class AbbreviationsExpanded(TypedDict, total=False):
    removed: ReadOnly[tuple[str, ...]]
    why: ReadOnly[str]


class Abbreviations(TypedDict, total=False):
    added: ReadOnly[tuple[tuple[str, ...], ...]]
    expanded: ReadOnly[AbbreviationsExpanded]
    meanings: ReadOnly[Prose]
    source_rows: ReadOnly[Mapping[str, str]]
    why: ReadOnly[str]


class KjvNotes(TypedDict, total=False):
    corrections: ReadOnly[Mapping[str, Correction]]
    notes: ReadOnly[Mapping[str, NoteOverride]]


class CcelNote(TypedDict, total=False):
    anchor: ReadOnly[str]
    duplicate: ReadOnly[str]
    omitted: ReadOnly[bool]
    verse: ReadOnly[str]
    supplied: ReadOnly[bool]
    why: ReadOnly[str]


class CcelNotes(TypedDict, total=False):
    corrections: ReadOnly[Mapping[str, Correction]]
    notes: ReadOnly[Mapping[str, CcelNote]]


RevisionChange = TypedDict(
    "RevisionChange",
    {
        "from": ReadOnly[str],
        "to": ReadOnly[str],
        "verse": ReadOnly[str],
        "why": ReadOnly[str],
    },
    total=False,
)


class RevisionGroup(TypedDict, total=False):
    changes: ReadOnly[tuple[RevisionChange, ...]]
    why: ReadOnly[str]
    wording: ReadOnly[Literal["spelling", "misprint"]]


class AlexandrinusSuppliedSource(TypedDict):
    source: ReadOnly[Literal["brenton"]]
    reference: ReadOnly[str]
    why: ReadOnly[str]


Decision = TypedDict(
    "Decision",
    {
        "appendix": ReadOnly[str],
        "edits": ReadOnly["tuple[Decision, ...]"],
        "english": ReadOnly[English],
        "from": ReadOnly[str],
        "insertions": ReadOnly[tuple[AlexandrinusPassagesInsertions, ...]],
        "kjv": ReadOnly[bool],
        "label": ReadOnly[str],
        "omits": ReadOnly[bool],
        "hebrew_agrees": ReadOnly[bool],
        "lemma": ReadOnly[str | None],
        "moved_to": ReadOnly[str],
        "moves": ReadOnly[tuple[AlexandrinusPassagesMoves, ...]],
        "omissions": ReadOnly[tuple[AlexandrinusPassagesOmissions, ...]],
        "note": ReadOnly[str | None],
        "note_at": ReadOnly[int],
        "note_edits": ReadOnly[Mapping[str, AlexandrinusReadingsNoteEdits]],
        "note_target": ReadOnly[str],
        "omit_verse": ReadOnly[bool],
        "reference": ReadOnly[str],
        "source_note": ReadOnly[str],
        "source_notes": ReadOnly[Mapping[str, str]],
        "supplied": ReadOnly[tuple[str, ...]],
        "supplied_sources": ReadOnly[tuple[AlexandrinusSuppliedSource, ...]],
        "swete": ReadOnly[Swete],
        "target": ReadOnly[str],
        "todo": ReadOnly[bool],
        "why": ReadOnly[str],
    },
    total=False,
)


class ByzantineUnit(TypedDict, total=False):
    ref: ReadOnly[str]
    tr: ReadOnly[str]
    rp: ReadOnly[str]
    nth: ReadOnly[int]


ByzantineEdit = TypedDict(
    "ByzantineEdit",
    {
        "ref": ReadOnly[str],
        "from": ReadOnly[str],
        "to": ReadOnly[str],
        "occurrence": ReadOnly[int],
        "after": ReadOnly[str],
        "before": ReadOnly[str],
        "greek": ReadOnly[str],
    },
    total=False,
)


class ByzantineEvidence(TypedDict, total=False):
    ref: ReadOnly[str]
    entry: ReadOnly[str | int]
    field: ReadOnly[str]
    quote: ReadOnly[str]


class ByzantineReading(TypedDict, total=False):
    units: ReadOnly[tuple[ByzantineUnit, ...]]
    kind: ReadOnly[str]
    edits: ReadOnly[tuple[ByzantineEdit, ...]]
    tags: ReadOnly[tuple[str, ...]]
    why: ReadOnly[str]
    evidence: ReadOnly[Mapping[str, ByzantineEvidence]]


class ByzantineOmitted(TypedDict, total=False):
    why: ReadOnly[str]


class ByzantineMoved(TypedDict, total=False):
    to: ReadOnly[str]
    why: ReadOnly[str]


class ByzantineStructure(TypedDict, total=False):
    why: ReadOnly[str]
    omitted: ReadOnly[Mapping[str, ByzantineOmitted]]
    moved: ReadOnly[Mapping[str, ByzantineMoved]]


class ByzantineLemma(TypedDict, total=False):
    lemma: ReadOnly[str]
    why: ReadOnly[str]


class ByzantineAccent(TypedDict, total=False):
    tr: ReadOnly[str]
    rp: ReadOnly[str]
    why: ReadOnly[str]


ByzantineCorrection = TypedDict(
    "ByzantineCorrection",
    {"from": ReadOnly[str], "to": ReadOnly[str], "why": ReadOnly[str]},
    total=False,
)


class ByzantineSide(TypedDict, total=False):
    unit: ReadOnly[ByzantineUnit]
    side: ReadOnly[str]
    why: ReadOnly[str]


Byzantine = TypedDict(
    "Byzantine",
    {
        "why": ReadOnly[str],
        "readings": ReadOnly[Mapping[str, ByzantineReading]],
        "structure": ReadOnly[ByzantineStructure],
        "accents": ReadOnly[Mapping[str, ByzantineAccent]],
        "hodges-farstad": ReadOnly[Mapping[str, ByzantineSide]],
        "lemmas": ReadOnly[Mapping[str, ByzantineLemma]],
        "scrivener": ReadOnly[Mapping[str, ByzantineCorrection]],
    },
    total=False,
)


class ByzantinePlacement(TypedDict, total=False):
    ref: ReadOnly[str]
    unit: ReadOnly[ByzantineUnit | tuple[ByzantineUnit, ...] | None]
    why: ReadOnly[str]


class ByzantinePlacements(TypedDict, total=False):
    why: ReadOnly[str]
    placements: ReadOnly[Mapping[str, ByzantinePlacement]]


class ClassConflict(TypedDict):
    rows: ReadOnly[tuple[str, ...]]
    why: ReadOnly[str]
