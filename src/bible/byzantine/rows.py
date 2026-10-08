"""The rows the reconciliation makes and passes between its modules: plain
dictionaries, as the sources are read and the ledger is written, with their
keys declared. Every key is optional, since a row gains keys as it passes
from stage to stage; a stage reads only the keys the stages before it set.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

from bible.usj import Node

if TYPE_CHECKING:
    from bible.byzantine.tags import Tag


class GreekKey(TypedDict, total=False):
    """A unit named by its verse and its Greek, and which of several."""

    ref: str
    tr: str
    rp: str
    nth: int


class Token(TypedDict):
    """A word of a parsed Greek text, with its Strong's numbers and parsing."""

    word: str
    strong: list[int]
    parse: list[str]


Unit = TypedDict(
    "Unit",
    {
        "class": "str",
        "classification_evidence": "dict[str, Any]",
        "found_in": "list[str]",
        "hf": "str",
        "id": "str",
        "inventories": "list[UnitInventory]",
        "inventory_absence": "dict[str, Any]",
        "kind": "str",
        "page": "int",
        "patriarchal": "bool",
        "ref": "str",
        "rp": "list[str]",
        "rp_accented": "str",
        "rp_alternate": "bool",
        "rp_range": "list[int]",
        "target_ref": "str",
        "tr": "list[str]",
        "tr_accented": "str",
        "tr_range": "list[int]",
    },
    total=False,
)
"""One place the Greek texts differ: the Received Text's words and the Byzantine text's at a verse, with the inventories that record it."""


class UnitInventory(TypedDict, total=False):
    """A record of a unit in Robinson's collation or Boyd's apparatus."""

    entry: int
    hf: str
    inventory: str
    quotation_normalization: str
    quotation_span: list[str]
    scope: str
    word_break_normalization: str


class Instruction(TypedDict, total=False):
    """A published instruction in the King James words, bound to the pinned text and attached to its units."""

    alternatives: list[dict[str, Any]]
    berry: dict[str, Any] | None
    bind: str
    change: None | str
    compatibility: str
    compatibility_reason: None | str
    construction: None | str
    context: str
    displaced: str
    displaced_by: list[str]
    displaced_choice: bool
    edits: list[InstructionEdit]
    entry: int
    group: str
    informational: bool
    issues: list[dict[str, Any]]
    joint: list[dict[str, Any]]
    line: int
    method: str
    nochange: bool
    placement: str
    quotation: None | str
    raw: str
    reason: str
    ref: None | str
    refs: list[str]
    refused_by: str
    rendering: None | str
    role: str
    scope: str
    source: str
    status: str
    strength: None | str
    units: list[Attachment]
    weight: dict[str, Any] | None


class InstructionEdit(TypedDict, total=False):
    """One edit an instruction makes, bound to the verse."""

    bind: str
    context_exact: bool
    kind: str
    method: None | str
    new: str
    no_effect: bool
    old: str
    positions: list[int]
    quoted_old: str
    quoted_context: str
    ref: str
    scope: str
    side: str
    stop: str
    units: list[str]
    word_range: list[int]


class Attachment(TypedDict, total=False):
    """How a witness's row attaches to a unit."""

    method: str
    scope: str
    unit: str


class Report(TypedDict, total=False):
    """An apparatus report: what a witness says a difference comes to in English."""

    contrast_evidence: list[dict[str, Any]]
    english: str
    english_context: str
    entry: int | str
    greek: str
    greek_entry: int
    greek_group: int
    greek_note: bool
    greek_order: str
    kind: str
    method: str
    new: None | str
    new_scope: str
    old: None | str
    omitted_greek_variants: list[dict[str, Any]]
    pairing: str
    placement: str
    raw: str
    reason: str
    ref: str
    rp_range: list[int]
    scope: str
    source_address: str
    source_main_html: None | str
    source_main_passages: dict[str, Any]
    source_main_text: None | str
    source_notes: str
    source_original: str
    source_original_html: str
    source_table_html: str
    source_table_transcription: str
    target_ref: str
    tr_range: list[int]
    units: list[Attachment]
    via: dict[str, Any]
    witness: str


class RevisionRow(TypedDict, total=False):
    """A reviser's change at a unit: the Revised Version's or Boyd's ASV's."""

    entry: str
    hf: str
    kind: str
    method: str
    new: str
    old: str
    ref: str
    reviser: str
    scope: str
    side: str
    units: list[Attachment]
    witness: str
    word_range: list[int]


Disposition = TypedDict(
    "Disposition",
    {
        "action": "str",
        "alarm_phrases": "list[str]",
        "basis": "str",
        "class": "str",
        "corroborated_by": "list[str]",
        "covered_by": "str",
        "disagreeing": "list[dict[str, Any]]",
        "disposition": "str",
        "edits": "list[Edit]",
        "evidence": "dict[str, Any]",
        "execution": "str",
        "flags": "list[str]",
        "kind": "str",
        "note": "Node | None",
        "note_ref": "str",
        "note_scope": "NoteScope",
        "old": "str",
        "ops": "list[dict[str, Any]]",
        "override": "str",
        "readings": "list[str]",
        "reason": "str",
        "reasons": "list[str]",
        "redundant": "bool",
        "ref": "str",
        "refused_instruction": "dict[str, Any]",
        "selected": "dict[str, Any]",
        "selected_edits": "list[InstructionEdit]",
        "source_note": "Node",
        "source_note_ref": "str",
        "tags": "list[str]",
        "target_ref": "str",
        "tcent_reports": "bool",
        "unit": "str",
        "why": "str",
        "witnesses": "list[str]",
    },
    total=False,
)
"""What the build decides for a unit, and what it did."""


class Edit(TypedDict, total=False):
    """An edit carried out on a verse, with its note."""

    applied_range: list[int]
    kind: str
    new: str
    note: Node
    note_owner: bool
    note_scope: NoteScope
    old: str
    prefix: str
    range: list[int]
    ref: str
    rendered: str
    seams: list[Seam]
    suffix: str


Seam = TypedDict(
    "Seam",
    {
        "external": "bool",
        "from": "str",
        "range": "list[int]",
        "rule": "int",
        "style": "str",
        "to": "str",
    },
    total=False,
)
"""What the executor touched beside the edited words."""


class NoteScope(TypedDict, total=False):
    """Where a Textus Receptus note stands and what it is about."""

    combined: bool
    full: bool
    offset: int
    range: list[int] | None
    ref: str
    source_range: list[int]
    terminal_stop: str


class Override(TypedDict, total=False):
    """A reading of the editor's, compiled: its units, its edits bound to the verse, its tags and its evidence."""

    bound: list[BoundEdit]
    edits: list[dict[str, Any]]
    evidence: dict[str, dict[str, Any]]
    id: str
    kind: str
    tag_set: list[Tag]
    tags: list[str]
    unit_ids: list[str]
    units: list[GreekKey]
    why: str


class BoundEdit(TypedDict, total=False):
    """An override's edit at character offsets."""

    end: int
    new: str
    old: str
    ref: str
    side: str
    start: int
    unstyle: bool


class Placement(TypedDict, total=False):
    """Which unit a witness's row is about, by the editor's decision."""

    entry: int | str
    ref: str
    unit: GreekKey | list[GreekKey] | None
    why: str
    witness: str


class PierpontRow(TypedDict, total=False):
    """A row of Pierpont's booklet as transcribed."""

    berry: dict[str, Any]
    cells: list[str]
    change: dict[str, Any]
    columns: list[str]
    context_ref: None | str
    continuation_of: int
    entry: int
    heading: str
    informational: bool
    instruction: dict[str, Any]
    issues: list[dict[str, Any]]
    line: int
    quotation: dict[str, Any]
    ref: None | str
    reference_raw: str
    refs: list[str]
    role: str
    source_original: str
    table: int
    weight: dict[str, Any]


class PierpontTable(TypedDict, total=False):
    """A table of the booklet."""

    columns: list[str]
    heading: str
    line: int
    section: str
    table: int


class Alarm(TypedDict, total=False):
    """The revision alarm at a unit: whether both revisions lack the King James words."""

    alarm: bool
    applicable: bool
    available: bool
    missing: list[str]
    phrases: list[str]


class Unmatched(TypedDict, total=False):
    """An inventory row that matched no unit."""

    entry: int
    fr: str
    hf: str
    inventory: str
    patriarchal: bool
    position: dict[str, Any] | None
    raw: str
    reason: str
    rp: list[str] | str
    rp_alternate: bool
    source_address: str
    source_main_html: str | None
    source_main_passages: dict[str, Any]
    source_original: str
    source_original_html: str
    target_ref: str
    tr: list[BoydReading] | list[str]
    variants: list[BoydReading]


class CollationRow(TypedDict, total=False):
    """A row of Robinson's collation."""

    entry: int
    raw: str
    rp: list[str]
    target_ref: str
    tr: list[str]


class BoydNote(TypedDict, total=False):
    """A note of Boyd's Greek apparatus, or of his English one (TCENT), which
    also gives the passage it is about."""

    entry: int
    fr: str
    hf: str
    patriarchal: bool
    position: dict[str, Any] | None
    raw: str
    rp: str
    rp_alternate: bool
    source_address: str
    source_main_html: str | None
    source_main_passages: dict[str, Any]
    source_original: str
    source_original_html: str
    target_ref: str
    tr: list[BoydReading]
    variants: list[BoydReading]


class BoydReading(TypedDict, total=False):
    """A reading an apparatus note gives, with its sigla."""

    reading: str
    sigla: list[str]


class FaaRow(TypedDict, total=False):
    """A verse of Far Above All, with its Greek and English groups."""

    RP_English: None | str
    RP_English_groups: list[dict[str, Any]]
    RP_English_unavailable: str
    RP_Greek: None | str
    RP_Greek_groups: list[dict[str, Any]]
    RP_Greek_unavailable: str
    TR_English: None | str
    TR_English_groups: list[dict[str, Any]]
    TR_English_unavailable: str
    TR_Greek: None | str
    TR_Greek_groups: list[dict[str, Any]]
    TR_Greek_unavailable: str
    raw_English: str
    raw_Greek: str
    source_English_html: str
    source_notes: str
    source_table_html: str
    source_table_text: str


class SelectedListRow(TypedDict, total=False):
    """A footnote of the Majority Standard Bible or the World English Bible, read as a contrast."""

    english: str
    english_context: str
    entry: int | str
    greek: str
    greek_order: str
    method: str
    new: None | str
    new_scope: str
    old: None | str
    placement: str
    raw: str
    reason: str
    ref: str
    scope: str
    source_main_html: None | str
    source_main_text: None | str
    source_original_html: str
    source_table_transcription: str
    target_ref: str
    units: list[Attachment]
    witness: str
