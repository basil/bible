"""Shapes of the edition's JSON decisions after freezing.

Typing only: stages still validate these fields, and objects and lists remain
mapping proxies and tuples at runtime. Optional fields model decisions that
apply only to some entries; no defaults are introduced here.
"""

from collections.abc import Mapping
from typing import TypedDict


class VersificationApocrypha(TypedDict, total=False):
    chapter: int
    edition: str
    kjv: str | None
    title: str


class Run(TypedDict, total=False):
    by: str
    edition: str | None
    kjv: str | None
    pairs: Mapping[str, str]
    why: str


class VersificationRelabel(TypedDict, total=False):
    edition: str
    opens: str


class VersificationStub(TypedDict, total=False):
    why: str


class VersificationRelocation(TypedDict, total=False):
    to: str
    why: str


class Versification(TypedDict, total=False):
    apocrypha: "tuple[VersificationApocrypha, ...]"
    books: Mapping[str, str]
    kjv: "Mapping[str, tuple[Run, ...]]"
    old_testament: tuple[str, ...]
    readings: "Mapping[str, tuple[Run, ...]]"
    relabel: "Mapping[str, VersificationRelabel]"
    relocations: "Mapping[str, VersificationRelocation | str]"
    stubs: "Mapping[str, VersificationStub | str]"
    why: str


class BookIntroductionsGlosses(TypedDict, total=False):
    after: str
    insert: str
    replace: str
    why: str


WordingChange = TypedDict(
    "WordingChange",
    {
        "from": "str",
        "note": "str",
        "to": "str",
        "unit": "str",
        "why": "str",
    },
    total=False,
)


class BookIntroductionsSections(TypedDict, total=False):
    heading: str
    paragraphs: tuple[str, ...]


class BookIntroductions(TypedDict, total=False):
    books: Mapping[str, tuple[str, ...]]
    front: tuple[str, ...]
    glosses: "Mapping[str, tuple[BookIntroductionsGlosses, ...]]"
    names: "Mapping[str, tuple[WordingChange, ...]]"
    omit: Mapping[str, str]
    sections: "Mapping[str, Mapping[str, BookIntroductionsSections]]"
    source: str


class QuotationsAlignment(TypedDict, total=False):
    outscored: Mapping[str, str]
    passages: Mapping[str, str]
    range_ends: Mapping[str, str]
    unscored: Mapping[str, str]


class QuotationsLxxToEdition(TypedDict, total=False):
    numbering: str
    target: str
    why: str


class QuotationsNarrowed(TypedDict, total=False):
    lxx: str
    why: str


class QuotationsNoteMerges(TypedDict, total=False):
    action: str
    drops: tuple[str, ...]
    why: str


class Quotations(TypedDict, total=False):
    alignment: "QuotationsAlignment"
    class_conflicts: "tuple[ClassConflict, ...]"
    excluded: Mapping[str, str]
    lxx_to_edition: "Mapping[str, QuotationsLxxToEdition]"
    narrowed: "Mapping[str, QuotationsNarrowed]"
    note_merges: "Mapping[str, QuotationsNoteMerges]"


class Prose(TypedDict, total=False):
    changes: "tuple[WordingChange, ...]"
    why: str


Correction = TypedDict(
    "Correction",
    {
        "from": "str",
        "to": "str",
        "uncategorized": "bool",
        "why": "str",
    },
    total=False,
)


class NoteOverride(TypedDict, total=False):
    anchor: str
    lemma: str | None
    note: str | None
    occurrence: int
    omitted: bool
    widen: bool
    sentence: bool
    quotation: bool
    uncategorized: bool
    verse: str
    why: str


class BrentonNotes(TypedDict, total=False):
    corrections: "Mapping[str, tuple[Correction, ...] | Correction]"
    notes: "Mapping[str, NoteOverride]"
    shapes: Mapping[str, str]


class Entry(TypedDict, total=False):
    abbreviated_singly: str
    abbreviation: str
    chapters: tuple[int, ...]
    cited_singly: str
    file: str
    heading: tuple[tuple[str, str], ...]
    id: str
    section: str
    short_title: str
    source: str
    source_id: str
    title: str


class ManifestExcluded(TypedDict, total=False):
    brenton: tuple[str, ...]


class Manifest(TypedDict, total=False):
    appendices: "tuple[Entry, ...]"
    excluded: "ManifestExcluded"
    front_matter: "tuple[Entry, ...]"
    new_testament_front: "tuple[Entry, ...]"
    old_testament_front: "tuple[Entry, ...]"
    scripture: "tuple[Entry, ...]"
    title: str


class Witnesses(TypedDict, total=False):
    chapter: str
    id: str
    phrase: str


class Swete(TypedDict, total=False):
    agrees: bool | None
    evidence: str
    page: int
    reading: str
    volume: int


class EnglishEdit(TypedDict, total=False):
    span: tuple[int, int]
    to: str
    why: str


class English(TypedDict, total=False):
    edits: "tuple[EnglishEdit, ...]"
    source: str
    span: tuple[int, int]


class AlexandrinusPassagesInsertions(TypedDict, total=False):
    after: str
    before: str
    verses: "tuple[Decision, ...]"


AlexandrinusReadingsNoteEdits = TypedDict(
    "AlexandrinusReadingsNoteEdits",
    {
        "from": "str",
        "lemma": "str",
        "to": "str",
        "why": "str",
    },
    total=False,
)


class AlexandrinusReadingsWitnesses(TypedDict, total=False):
    adopted: tuple[str, ...]
    displaced: str


class Alexandrinus(TypedDict, total=False):
    kept: "Mapping[str, Decision]"
    passages: "Mapping[str, Decision]"
    readings: "Mapping[str, Decision]"
    swete: Mapping[str, str]
    witness_evidence: Mapping[str, str]


class Terminology(TypedDict, total=False):
    display: str
    meaning: str
    note_forms: tuple[str, ...]
    period_forms: tuple[str, ...]
    plural: str
    source_forms: tuple[str, ...]


class TurpieRowsAdditionalSourceHeadings(TypedDict, total=False):
    hebrew_normalized: tuple[str, ...]
    hebrew_printed: tuple[str, ...]
    lxx_normalized: tuple[str, ...]
    printed: tuple[str, ...]
    scope: str


class TurpieHeading(TypedDict, total=False):
    alternative_normalized: tuple[str, ...]
    evidence_pages: tuple[int, ...]
    normalized: str | None
    printed: str
    reference_location: str


TurpieRows = TypedDict(
    "TurpieRows",
    {
        "additional_source_headings": "TurpieRowsAdditionalSourceHeadings",
        "class": "str | None",
        "hebrew": "TurpieHeading",
        "id": "str",
        "kind": "str",
        "lxx": "TurpieHeading",
        "note": "str",
        "nt": "TurpieHeading",
        "part_markers": "tuple[str, ...]",
        "pdf_page": "int",
        "printed_sequence": "str",
        "source_headings": "str",
        "table_code": "str",
    },
    total=False,
)


class Turpie(TypedDict, total=False):
    edition: str
    pdf_page_numbering: str
    rows: "tuple[TurpieRows, ...]"
    transcription_scope: str


CitationsDecisions = TypedDict(
    "CitationsDecisions",
    {
        "not_a_citation": "bool",
        "numbering": "str",
        "passages": "str",
        "print": "str",
        "relative": "str",
        "source": "str",
        "unprinted": "bool",
        "why": "str",
    },
    total=False,
)


class CitationsDialects(TypedDict, total=False):
    books: Mapping[str, str]
    chapter_verse: str
    entries: Mapping[str, str]
    numbering: str
    numerals: str


class Citations(TypedDict, total=False):
    decisions: "Mapping[str, CitationsDecisions | tuple[CitationsDecisions, ...]]"
    dialects: "Mapping[str, CitationsDialects]"
    names: "Mapping[str, tuple[WordingChange, ...]]"
    units: Mapping[str, str | None]


class RevisionsWords(TypedDict, total=False):
    to: str
    why: str


class PunctuationRule(TypedDict, total=False):
    why: str


class Revisions(TypedDict, total=False):
    passages: "Mapping[str, Prose]"
    punctuation: "Mapping[str, PunctuationRule]"
    verses: "Mapping[str, RevisionGroup]"
    why: str
    words: "Mapping[str, RevisionsWords]"


class AbbreviationsExpanded(TypedDict, total=False):
    removed: tuple[str, ...]
    why: str


class Abbreviations(TypedDict, total=False):
    added: tuple[tuple[str, ...], ...]
    expanded: "AbbreviationsExpanded"
    meanings: "Prose"
    source_rows: Mapping[str, str]
    why: str


class KjvNotes(TypedDict, total=False):
    corrections: "Mapping[str, Correction]"
    notes: "Mapping[str, NoteOverride]"


RevisionChange = TypedDict(
    "RevisionChange",
    {
        "from": "str",
        "to": "str",
        "verse": "str",
        "why": "str",
    },
    total=False,
)


class RevisionGroup(TypedDict, total=False):
    changes: "tuple[RevisionChange, ...]"
    why: str


Decision = TypedDict(
    "Decision",
    {
        "appendix": "str",
        "edits": "tuple[Decision, ...]",
        "english": "English",
        "from": "str",
        "insertions": "tuple[AlexandrinusPassagesInsertions, ...]",
        "kjv": "bool",
        "lemma": "str | None",
        "note": "str | None",
        "note_at": "int",
        "note_edits": "Mapping[str, AlexandrinusReadingsNoteEdits]",
        "note_target": "str",
        "omit_verse": "bool",
        "reference": "str",
        "source_note": "str",
        "source_notes": "Mapping[str, str]",
        "supplied": "tuple[str, ...]",
        "swete": "Swete",
        "target": "str",
        "todo": "bool",
        "why": "str",
        "witnesses": "AlexandrinusReadingsWitnesses",
    },
    total=False,
)


class ByzantineUnit(TypedDict, total=False):
    ref: str
    tr: str
    rp: str
    nth: int


ByzantineEdit = TypedDict(
    "ByzantineEdit",
    {
        "ref": str,
        "from": str,
        "to": str,
        "occurrence": int,
        "after": str,
        "before": str,
    },
    total=False,
)


class ByzantineEvidence(TypedDict, total=False):
    ref: str
    entry: str | int
    field: str
    quote: str


class ByzantineReading(TypedDict, total=False):
    units: tuple[ByzantineUnit, ...]
    kind: str
    edits: tuple[ByzantineEdit, ...]
    tags: tuple[str, ...]
    why: str
    evidence: Mapping[str, ByzantineEvidence]


class ByzantineOmitted(TypedDict, total=False):
    why: str


class ByzantineMoved(TypedDict, total=False):
    to: str
    why: str


class ByzantineStructure(TypedDict, total=False):
    why: str
    omitted: Mapping[str, ByzantineOmitted]
    moved: Mapping[str, ByzantineMoved]


class ByzantineLemma(TypedDict, total=False):
    lemma: str
    why: str


class ByzantineAccent(TypedDict, total=False):
    tr: str
    rp: str
    why: str


class ByzantineSide(TypedDict, total=False):
    unit: ByzantineUnit
    side: str
    why: str


Byzantine = TypedDict(
    "Byzantine",
    {
        "why": str,
        "readings": Mapping[str, ByzantineReading],
        "structure": ByzantineStructure,
        "accents": Mapping[str, ByzantineAccent],
        "hodges-farstad": Mapping[str, ByzantineSide],
        "lemmas": Mapping[str, ByzantineLemma],
    },
    total=False,
)


class ByzantinePlacement(TypedDict, total=False):
    ref: str
    unit: ByzantineUnit | tuple[ByzantineUnit, ...] | None
    why: str


class ByzantinePlacements(TypedDict, total=False):
    why: str
    placements: Mapping[str, ByzantinePlacement]


class ClassConflict(TypedDict):
    rows: tuple[str, ...]
    why: str
