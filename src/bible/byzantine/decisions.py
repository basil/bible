"""The editor's decisions about the New Testament, validated against the
pinned sources.

The readings of edition/byzantine.json (subjective): the wording where no
instruction settles a unit, a ruling that a reported difference is not
applied, or, keyed by a verse rather than units, a correction of the English
where the TR and RP2026 share the Greek; and its instructions, the decisions
on Pierpont's own corrections of shared Greek, whose edits the build reads
from his booklet. edition/byzantine-placements.json (objective): which Greek
unit a witness's row is about where code cannot tell. The lemmas of
edition/byzantine.json: a footnote lemma widened by hand. Every entry is
keyed by verse and Greek, so unit numbering may change under it; every quote
is checked against the source it cites, so nothing can drift unnoticed.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from copy import deepcopy
from typing import TYPE_CHECKING, Any, TypeIs, TypeVar, cast

from bible.byzantine import BOOKS, FAA, KJV, PIERPONT, WITNESSES, greek
from bible.byzantine.crosswire import SPAN, curly_apostrophes, kjv_bounds, words
from bible.byzantine.edit import sentence_start
from bible.byzantine.received import VERSIONS
from bible.byzantine.rows import (
    BoundEdit,
    Carrier,
    FaaRow,
    GreekKey,
    Instruction,
    InstructionEdit,
    Override,
    Placement,
    Report,
    SelectedListRow,
    Unit,
    UnitInventory,
    Unmatched,
)
from bible.byzantine.tags import Grammar, Wording
from bible.byzantine.units import keyed_units, record_side
from bible.checks import CheckFailed, present, require
from bible.scripture import plain

if TYPE_CHECKING:
    from bible.byzantine.stages import Greek

# A witness's row that a placement can attach: an apparatus report, a
# selected list's footnote, or an instruction.
Row = TypeVar("Row", Report, SelectedListRow, Instruction)

# The fields of an override's edit; policy.check holds the decisions' own.
EDIT_KEYS = ("ref", "from", "to", "occurrence", "after", "before", "greek")

# A verse's supplied words: the offsets and the words of each.
type Supplied = Mapping[str, Sequence[tuple[int, int, str]]]
# The check of a decision's evidence against its sources (evidence_checked
# with its sources bound), given the decision's label, its evidence, and the
# verses it is about.
type Evidence = Callable[[str, Mapping[str, Any], set[str]], object]


def ref_key(ref: str) -> tuple[int, int, int]:
    book, address = ref.split()
    chapter, verse = address.split(":")
    return BOOKS.index(book), int(chapter), int(verse)


def resolve(greek: Mapping[str, Any], units: Sequence[Unit], label: str) -> Unit:
    """The one unit a Greek key names: verse, tr and rp words, optional nth."""
    for field in ("ref", "tr", "rp"):
        require(
            isinstance(greek.get(field), str),
            f"{label}: Greek key needs ref, tr and rp strings",
        )
    found = keyed_units(units, greek["ref"], greek["tr"], greek["rp"])
    if "nth" in greek:
        nth = greek["nth"]
        require(
            type(nth) is int and 1 <= nth <= len(found),
            f"{label}: nth does not select a unit",
        )
        found = [found[nth - 1]]
    require(
        len(found) == 1,
        f"{label}: Greek key {greek['ref']} {greek['tr']!r} -> {greek['rp']!r} names {len(found)} units",
    )
    return found[0]


def placed_units(decision: Placement, units: Sequence[Unit], label: str) -> list[Unit]:
    """The units a placement names: one Greek key, several, or none (`unit:
    null`), each key's verse the placement's unless it names its own."""
    wanted = decision["unit"]
    keys: list[GreekKey] = (
        [] if wanted is None else wanted if isinstance(wanted, list) else [wanted]
    )
    found = [
        resolve({**g, "ref": g.get("ref", decision["ref"])}, units, label) for g in keys
    ]
    ids = [u["id"] for u in found]
    require(len(ids) == len(set(ids)), f"{label}: duplicate unit")
    return found


def override_id(unit_ids: Iterable[str]) -> str:
    return "+".join(unit_ids)


def with_hodges_farstad(
    units: Sequence[Unit], sides: Mapping[str, Mapping[str, Any]]
) -> list[Unit]:
    """The units with the side of Hodges and Farstad's text that the editor
    read where no apparatus gives it, by unit id. A decision whose key is not
    its unit's, or that gives the side the unit has already, is refused."""
    result = list(units)
    for key, decision in sides.items():
        label = f"Hodges-Farstad side {key}"
        unit = resolve(decision["unit"], result, label)
        require(unit["id"] == key, f"{label}: the unit is {unit['id']}")
        require(unit["hf"] != decision["side"], f"{label} changes nothing")
        result[result.index(unit)] = {**unit, "hf": decision["side"]}
    return result


# Overrides


def cuts_word(text: str, start: int, end: int) -> bool:
    """Whether text[start:end] begins or ends inside a word."""

    def joined(a: str, b: str) -> bool:
        return all(c.isalnum() or c in "’'" for c in (a, b))

    starts_inside = 0 < start < len(text) and joined(text[start - 1], text[start])
    ends_inside = start < end < len(text) and joined(text[end - 1], text[end])
    return starts_inside or ends_inside


def bracketed_quote(quote: str) -> tuple[str, list[tuple[int, int]]]:
    """Return the literal wording and explicitly bracketed supplied ranges."""
    text, ranges, start = "", list[tuple[int, int]](), None
    for char in quote:
        if char == "[":
            if start is not None:
                raise CheckFailed("malformed supplied-word brackets")
            start = len(text)
        elif char == "]":
            if start is None or start == len(text) or not text[start:].strip():
                raise CheckFailed("malformed supplied-word brackets")
            ranges.append((start, len(text)))
            start = None
        else:
            text += char
    if start is not None:
        raise CheckFailed("malformed supplied-word brackets")
    return text, ranges


def spans_within(
    spans: Iterable[tuple[int, int]], start: int, end: int
) -> list[tuple[int, int]]:
    """The parts of spans that fall in text[start:end], from its start."""
    return [
        (max(a, start) - start, min(b, end) - start)
        for a, b in spans
        if a < end and start < b
    ]


def letter_hits(verse: Sequence[str], cited: str) -> list[int]:
    """Where the cited Greek words stand in a verse's, by their letters."""
    return greek.occurrences(
        [greek.letter_key(w) for w in verse],
        [greek.letter_key(w) for w in cited.split()],
    )


def shared_greek(
    cited: str,
    ref: str,
    units: Sequence[Unit],
    printed: Mapping[str, greek.PrintedVerse],
    alignment: greek.Alignment,
    structure: greek.Structure,
) -> None:
    """Refuse Greek that is not whole words occurring once in RP2026's
    printed verse, or that a difference from the TR touches."""
    require(ref not in structure.omitted, "the verse is omitted by RP2026")
    target = structure.rp_ref(ref)

    require(
        alignment.text.get(target) == printed[target]["accented"],
        f"{ref}: printed words disagree with Greek alignment offsets",
    )
    require(
        all(address == target for address in alignment.addresses[target]),
        f"{ref}: unsupported cross-verse joined-word alignment",
    )

    hits = letter_hits(printed[target]["accented"], cited)
    require(
        len(hits) == 1, f"greek must occur once at RP2026 {target} ({len(hits)} found)"
    )
    a, b = hits[0], hits[0] + len(cited.split())
    tokens = [
        i for i, (x, y) in enumerate(alignment.spans[target]) if a <= x and y <= b
    ]
    require(
        tokens and alignment.project(target, [tokens[0], tokens[-1] + 1]) == (a, b),
        "greek cuts an aligned word",
    )
    start, end = tokens[0], tokens[-1] + 1
    # Words RP2026 lacks stand between two of its words, and touch the Greek
    # on either side of them.
    require(
        not any(
            u["target_ref"] == target
            and u["class"] != "structural"
            and (
                start <= u["rp_range"][0] <= end
                if u["rp_range"][0] == u["rp_range"][1]
                else start < u["rp_range"][1] and u["rp_range"][0] < end
            )
            for u in units
        ),
        "greek touches a difference between the TR and RP2026",
    )


def witness_rows(
    reports: Iterable[Report], instructions: Iterable[Instruction]
) -> dict[str, dict[int | str, Report | Instruction]]:
    """Every witness's rows by its entry, for the evidence a reading names."""
    found: dict[str, dict[int | str, Report | Instruction]] = {}
    for r in reports:
        found.setdefault(r["witness"], {})[r["entry"]] = r
    for i in instructions:
        found.setdefault(i["source"], {})[i["entry"]] = i
    return found


def cited_greek(override: Override) -> list[str]:
    """The RP2026 Greek each edit of a correction of shared Greek renders:
    written with the edits, or declared for an instruction's."""
    if "instruction" in override:
        return list(override["greek"])
    return [e["greek"] for e in override.get("edits", [])]


def instruction_bound(
    label: str,
    entry: Mapping[str, Any],
    kjv: Mapping[str, str],
    units: Sequence[Unit],
    printed: Mapping[str, greek.PrintedVerse],
    alignment: greek.Alignment,
    structure: greek.Structure,
) -> list[BoundEdit]:
    """An instruction's edits, read from the pinned booklet, bound to its
    verse as a reading's are, each rendering the shared Greek the entry
    names for it (shared_greek). Only a replacement's routine sentence-initial
    capital is adapted. Sentence repair, uncertain casing, or an edit beyond
    the instruction's own words requires an explicit reading."""
    bound: list[BoundEdit] = []
    for e, quotation in zip(entry["instruction"]["edits"], entry["greek"], strict=True):
        ref = e["ref"]
        require("stop" not in e, f"{label}: an instruction with a stop is a reading")
        try:
            shared_greek(quotation, ref, units, printed, alignment, structure)
        except CheckFailed as error:
            raise CheckFailed(f"{label}: {error}") from None
        text = kjv[ref]
        start, end = kjv_bounds(text, e)
        new = e["new"]
        # As a written edit is checked: a change, with its brackets balanced.
        require(e["old"] != new, f"{label}: an edit that changes nothing at {ref}")
        try:
            bracketed_quote(new)
        except CheckFailed as error:
            raise CheckFailed(f"{label}: new has {error} at {ref}") from None
        actual = [m[0] for m in SPAN.finditer(text[start:end])]
        quoted = [m[0] for m in SPAN.finditer(e.get("quoted_old", e["old"]))]
        opening = sentence_start(text, start)
        routine = (
            opening
            and actual
            and quoted
            and actual[0] == quoted[0][:1].upper() + quoted[0][1:]
            and actual[1:] == quoted[1:]
        )
        require(
            actual == quoted or routine,
            f"{label}: instruction needs explicit reading for casing or scope",
        )
        replacement = SPAN.search(new)
        if routine and replacement and replacement[0][0].islower():
            at = replacement.start()
            new = new[:at] + new[at].upper() + new[at + 1 :]
        following = SPAN.search(text, end)
        require(
            not (opening and not new and following and following[0][0].islower()),
            f"{label}: sentence repair needs an explicit reading",
        )
        require(
            not (
                not actual
                and new
                and following
                and following[0][0].isupper()
                and not new.rstrip().endswith(tuple(".!?"))
            ),
            f"{label}: insertion with uncertain casing needs an explicit reading",
        )
        bound.append(
            {
                "ref": ref,
                "start": start,
                "end": end,
                "old": text[start:end],
                "new": new,
                "side": "after" if e.get("side") == "after" else "before",
            }
        )
    return bound


def former_checked(
    label: str,
    former: Mapping[str, Any],
    refs: set[str],
    texts: Mapping[str, Mapping[str, str]],
) -> None:
    """A version cited for the former English of a correction of shared
    Greek: one the notes may name (received.VERSIONS), quoted once, in whole
    words, from its pinned text at the reading's verse."""
    witness, ref = former["witness"], former["ref"]
    require(witness in VERSIONS, f"{label}: former names no version: {witness}")
    require(ref in refs, f"{label}: former is about another verse: {ref}")
    verse = plain(texts[witness].get(ref, ""))
    quote = plain(former.get("quote", ""))
    require(
        bool(quote) and verse.count(quote) == 1,
        f"{label}: former quote is not in {witness} {ref} once",
    )
    start = verse.index(quote)
    require(
        not cuts_word(verse, start, start + len(quote)),
        f"{label}: former quote cuts through a word",
    )


def evidence_checked(
    label: str,
    evidence: Mapping[str, Any],
    refs: set[str],
    *,
    permitted: set[str] | None = None,
    kjv: Mapping[str, str],
    witness_rows: Mapping[str, Mapping[int | str, Mapping[str, Any]]],
    texts: Mapping[str, Mapping[str, str]],
    supplied: Supplied,
    revision_citations: (
        Mapping[str, Mapping[str, Mapping[str, Any] | None]] | None
    ) = None,
    faa_rows: Mapping[str, FaaRow] | None = None,
) -> tuple[str, int, int] | None:
    """Each item of a decision's evidence found in its source: a witness's
    row by its entry (an instruction or an apparatus report), a Far Above
    All verse note, a King James parallel, or a verse of a text the build
    reads, quoted once at a verse the decision is about (permitted, the
    decision's own verses unless given). Returns the King James parallel's
    place, if one is cited."""
    if permitted is None:
        permitted = refs
    parallel: tuple[str, int, int] | None = None
    for witness, item in evidence.items():
        quote = item.get("quote") if isinstance(item, dict) else None
        if not isinstance(quote, str) or not quote.strip():
            raise CheckFailed(f"{label}: evidence {witness} needs a quote")
        if witness == FAA and ("ref" in item or "field" in item):
            require(
                set(item) == {"ref", "field", "quote"}
                and item.get("field") == "source_notes",
                f"{label}: faa verse note needs ref, field source_notes and quote only",
            )
            ref = item["ref"]
            faa_row = (faa_rows or {}).get(ref)
            if ref not in permitted or faa_row is None:
                raise CheckFailed(
                    f"{label}: faa verse note is about another or missing verse"
                )
            notes = " ".join(faa_row.get("source_notes", "").split())
            require(
                quote in notes,
                f"{label}: faa verse note does not contain the quote",
            )
        elif "entry" in item and witness in witness_rows:
            require(
                witness != FAA or set(item) == {"entry", "quote"},
                f"{label}: faa report needs entry and quote only",
            )
            cited = present(
                witness_rows[witness].get(item.get("entry")),
                f"{label}: {witness} has no entry {item.get('entry')}",
            )
            haystack = " ".join(
                str(cited.get(k) or "")
                for k in (
                    "raw",
                    "old",
                    "new",
                    "quotation",
                    "change",
                    "source_notes",
                )
            )
            require(
                quote in haystack,
                f"{label}: {witness} {item.get('entry')} does not contain the quote",
            )
            require(
                cited.get("ref") in permitted or set(cited.get("refs", [])) & refs,
                f"{label}: {witness} {item.get('entry')} is about another verse",
            )
        elif witness in texts:
            ref = item.get("ref")
            verse = plain(texts[witness].get(ref, ""))
            normalized = plain(quote)
            # A bracket the source itself prints is quoted verbatim.
            bracketed = (
                "[" in normalized or "]" in normalized
            ) and normalized not in verse
            quoted, marked = (
                bracketed_quote(normalized) if bracketed else (normalized, [])
            )
            require(
                ref in permitted and verse.count(quoted) == 1,
                f"{label}: {witness} quote is not in the verse once",
            )
            if bracketed:
                metadata = (revision_citations or {}).get(witness, {}).get(ref)
                if metadata is None or metadata["text"] != verse:
                    raise CheckFailed(
                        f"{label}: {witness} supplied-word metadata missing or stale"
                    )
                start = verse.index(quoted)
                end = start + len(quoted)
                require(
                    marked == spans_within(metadata["supplied"], start, end),
                    f"{label}: {witness} brackets differ from source supplied words",
                )
        elif witness == KJV:
            require(
                set(item) == {"ref", "quote"},
                f"{label}: kjv parallel needs ref and quote only",
            )
            ref = item["ref"]
            verse = present(kjv.get(ref), f"{label}: kjv parallel {ref} is not a verse")
            quoted, marked = bracketed_quote(plain(quote))
            require(
                verse.count(quoted) == 1,
                f"{label}: kjv quote is not in the verse once",
            )
            start = verse.index(quoted)
            end = start + len(quoted)
            require(
                not cuts_word(verse, start, end),
                f"{label}: kjv quote cuts through a word",
            )
            # The KJV's supplied words are bracketed, as the
            # revisions' are, so that the parallel shows its italics.
            spans = ((a, b) for a, b, _ in supplied.get(ref, []))
            require(
                marked == spans_within(spans, start, end),
                f"{label}: kjv brackets differ from the supplied words",
            )
            parallel = ref, start, end
        elif witness in WITNESSES:
            raise CheckFailed(
                f"{label}: {witness} is not loaded; its quote cannot be checked"
            )
        else:
            raise CheckFailed(f"{label}: unknown witness {witness}")
    return parallel


def overlaps(start: int, end: int, taken: Iterable[tuple[int, int]]) -> bool:
    """Whether a span, or an insertion point, meets one of the spans taken."""
    return any(start < b and a < end or (start == end == a == b) for a, b in taken)


def validate_overrides(
    entries: Iterable[Mapping[str, Any]],
    units: Sequence[Unit],
    kjv: Mapping[str, str],
    witness_rows: Mapping[str, Mapping[int | str, Mapping[str, Any]]],
    texts: Mapping[str, Mapping[str, str]],
    supplied: Supplied,
    *,
    revision_citations: (
        Mapping[str, Mapping[str, Mapping[str, Any] | None]] | None
    ) = None,
    faa_rows: Mapping[str, FaaRow] | None = None,
    printed: Mapping[str, greek.PrintedVerse] | None = None,
    alignment: greek.Alignment | None = None,
    structure: greek.Structure | None = None,
    among: Sequence[Override] = (),
) -> tuple[list[Override], list[str]]:
    """Each override bound to the pinned KJV and its evidence to its sources.

    Returns (compiled, errors). A compiled override has everything as
    written, and its units' ids (`unit_ids`), its edits at character offsets
    (`bound`), its wording sources, and its grammatical kinds.
    witness_rows: {witness: {entry: row}} for the instruction sources and the
    apparatus; texts: {witness: verses} for the revisions. Optional
    revision_citations carries normalized text and USJ supplied spans;
    faa_rows supplies verse notes independently of apparatus reports.
    printed, alignment and structure, RP2026's, check the Greek of an
    override without units (shared_greek). The entries may claim no unit
    and edit no words that the overrides already compiled (among) do.
    """
    compiled: list[Override] = []
    errors: list[str] = []
    claimed: set[str] = {i for o in among for i in o["unit_ids"]}
    occupied: defaultdict[str, list[tuple[int, int]]] = defaultdict(list)
    for o in among:
        for e in o["bound"]:
            occupied[e["ref"]].append((e["start"], e["end"]))
    parallels: list[tuple[str, str, int, int]] = [
        (f"override {o['id']}", *o["parallel"]) for o in among if "parallel" in o
    ]
    for number, entry in enumerate(entries, 1):
        label = f"override {entry.get('id') or number}"
        try:
            found = [resolve(g, units, label) for g in entry.get("units", [])]
            ids = [u["id"] for u in found]
            require(
                len(ids) == len(set(ids)) and not claimed & set(ids),
                f"{label}: duplicate unit",
            )
            # Without units, an override corrects the English of Greek the
            # TR and RP2026 share, keyed by its verse, each edit naming its
            # Greek: there is no difference to tag and no TR note to write.
            if ids and entry.get("id") != override_id(ids):
                raise CheckFailed(f"{label}: id should be {override_id(ids)}")
            require(
                ids or entry.get("id") in kjv,
                f"{label}: without units, the id is a verse",
            )
            kind = entry.get("kind")
            edits = entry.get("edits", [])
            # The edits are written in the reading, or read from an
            # instruction of Pierpont's where the Greek is shared.
            written, read = bool(edits), "instruction" in entry
            if kind not in {"edit", "nochange"}:
                raise CheckFailed(f"{label}: kind is edit or nochange")
            require(
                not (written and read), f"{label}: edits or an instruction, not both"
            )
            require(
                (kind == "edit") == (written or read),
                f"{label}: kind edit needs edits or an instruction, nochange has none",
            )
            require(ids or kind == "edit", f"{label}: without units, the kind is edit")
            why = entry.get("why")
            if not isinstance(why, str) or not why.strip():
                raise CheckFailed(f"{label}: why required")
            require(
                all(
                    isinstance(entry.get(field, []), (list, tuple))
                    for field in ("wording", "grammar")
                ),
                f"{label}: wording and grammar must be lists",
            )
            wording = [Wording(w) for w in entry.get("wording", [])]
            grammar = [Grammar(g) for g in entry.get("grammar", [])]
            require(
                len(wording) == len(set(wording)) and len(grammar) == len(set(grammar)),
                f"{label}: duplicate wording or grammar",
            )
            require(
                not ids or len(re.findall(r"[.!?](?:\s|$)", why.strip())) <= 2,
                f"{label}: why is at most two sentences",
            )
            require(
                bool(wording) == bool(ids)
                and bool(grammar) == bool(ids)
                and (bool(ids) or not {"wording", "grammar"} & set(entry)),
                f"{label}: wording and grammar go with units",
            )
            refs = {g["ref"] for g in entry["units"]} if ids else {entry["id"]}
            books = {r.split()[0] for r in refs}
            require(len(books) == 1, f"{label}: units in more than one book")
            bound: list[BoundEdit] = []
            for edit in edits:
                unknown = set(edit) - set(EDIT_KEYS)
                require(not unknown, f"{label}: unknown edit fields {sorted(unknown)}")
                ref, old, new = edit["ref"], edit["from"], edit["to"]
                require(
                    ref in kjv and ref.split()[0] in books,
                    f"{label}: edit at {ref} is not in the units' book",
                )
                require(
                    not (
                        ("greek" in edit) == bool(ids) or not ids and ref != entry["id"]
                    ),
                    f"{label}: greek, at its verse, for an edit without units only",
                )
                if not ids:
                    if printed is None or alignment is None or structure is None:
                        raise CheckFailed(f"{label}: RP2026 is needed to check greek")
                    try:
                        shared_greek(
                            edit["greek"], ref, units, printed, alignment, structure
                        )
                    except CheckFailed as error:
                        raise CheckFailed(f"{label}: {error}") from None
                require(
                    isinstance(old, str)
                    and isinstance(new, str)
                    and "\\" not in old + new
                    and "\n" not in old + new,
                    f"{label}: from and to are plain strings",
                )
                require(
                    new == new.strip() and "  " not in new,
                    f"{label}: to has stray spaces",
                )
                try:
                    bracketed_quote(new)
                except CheckFailed as error:
                    raise CheckFailed(f"{label}: to has {error} at {ref}") from None
                text = kjv[ref]
                if old:
                    require(
                        old.strip() != text.strip(),
                        f"{label}: an override is a fragment, not the verse",
                    )
                    hits = [m.start() for m in re.finditer(re.escape(old), text)]
                    if "occurrence" in edit:
                        n = edit["occurrence"]
                        require(
                            type(n) is int and 1 <= n <= len(hits),
                            f"{label}: occurrence does not select a match at {ref}",
                        )
                        hits = [hits[n - 1]]
                    require(
                        len(hits) == 1,
                        f"{label}: from must occur exactly once at {ref} ({len(hits)} found)",
                    )
                    start = hits[0]
                    end = start + len(old)
                    require(
                        not cuts_word(text, start, end),
                        f"{label}: from cuts through a word at {ref}",
                    )
                    # Words added before or after the KJV's, or dropped from
                    # one end of them, are an insertion or a deletion, whose
                    # note says what the TR omits or adds; written as a
                    # replacement they would quote the kept words too.
                    a, b = old.split(), curly_apostrophes(new).split()
                    require(
                        len(a) >= len(b) or a not in (b[: len(a)], b[-len(a) :]),
                        f"{label}: from is a prefix or suffix of to at {ref}: an "
                        'insertion in disguise; write from "" with after or before',
                    )
                    require(
                        not b
                        or len(b) >= len(a)
                        or b not in (a[: len(b)], a[-len(b) :]),
                        f"{label}: to is a prefix or suffix of from at {ref}: a "
                        'deletion in disguise; write to "" on the words dropped',
                    )
                    # The same words are a change only when the KJV supplies
                    # some of them in italics and RP2026 has Greek for them:
                    # the override sets them in roman (John 19:17 "the place").
                    unstyle = old == new and any(
                        a < end and start < b for a, b, _ in supplied.get(ref, [])
                    )
                    require(old != new or unstyle, f"{label}: from equals to at {ref}")
                else:
                    anchor = edit.get("after") or edit.get("before")
                    require(
                        anchor and new and not ("after" in edit and "before" in edit),
                        f"{label}: an insertion needs to and one of after/before",
                    )
                    hits = [m.start() for m in re.finditer(re.escape(anchor), text)]
                    require(
                        len(hits) == 1,
                        f"{label}: anchor must occur exactly once at {ref}",
                    )
                    require(
                        not cuts_word(text, hits[0], hits[0] + len(anchor)),
                        f"{label}: anchor cuts through a word at {ref}",
                    )
                    start = end = hits[0] + (len(anchor) if "after" in edit else 0)
                require(
                    not overlaps(
                        start,
                        end,
                        [
                            *occupied[ref],
                            *((e["start"], e["end"]) for e in bound if e["ref"] == ref),
                        ],
                    ),
                    f"{label}: overlaps another edit at {ref}",
                )
                binding: BoundEdit = {
                    "ref": ref,
                    "start": start,
                    "end": end,
                    "old": old,
                    "new": new,
                    "side": "after" if "after" in edit else "before",
                }
                if old and old == new:
                    binding["unstyle"] = True
                bound.append(binding)
            if "instruction" in entry:
                require(
                    not ids, f"{label}: an instruction is read for shared Greek only"
                )
                if printed is None or alignment is None or structure is None:
                    raise CheckFailed(f"{label}: RP2026 is needed to check greek")
                bound = instruction_bound(
                    label, entry, kjv, units, printed, alignment, structure
                )
                for n, e in enumerate(bound):
                    taken = [
                        *occupied[e["ref"]],
                        *(
                            (b["start"], b["end"])
                            for b in bound[:n]
                            if b["ref"] == e["ref"]
                        ),
                    ]
                    require(
                        not overlaps(e["start"], e["end"], taken),
                        f"{label}: overlaps another edit at {e['ref']}",
                    )
            if "former" in entry:
                require(not ids, f"{label}: a Greek difference names its Greek witness")
                former_checked(label, entry["former"], refs, texts)
            evidence = entry.get("evidence", {})
            require(
                isinstance(evidence, dict) and evidence, f"{label}: evidence required"
            )
            permitted = refs | {e["ref"] for e in bound}
            parallel = evidence_checked(
                label,
                evidence,
                refs,
                permitted=permitted,
                kjv=kjv,
                witness_rows=witness_rows,
                texts=texts,
                supplied=supplied,
                revision_citations=revision_citations,
                faa_rows=faa_rows,
            )
            require(
                (Wording.KJV_PARALLEL in wording) == (KJV in evidence),
                f"{label}: kjv-parallel wording and kjv evidence go together",
            )
            override: Override = {
                "id": entry["id"],
                "units": entry.get("units", []),
                "kind": kind,
                "wording": wording,
                "grammar": grammar,
                "why": why,
                "evidence": evidence,
                "unit_ids": ids,
                "bound": bound,
            }
            for field in ("edits", "instruction", "greek", "former"):
                if field in entry:
                    override[field] = entry[field]
            if parallel:
                override["parallel"] = parallel
            compiled.append(override)
            claimed.update(ids)
            for e in bound:
                occupied[e["ref"]].append((e["start"], e["end"]))
            if parallel:
                parallels.append((label, *parallel))
        except (CheckFailed, ValueError, KeyError, TypeError, AttributeError) as error:
            errors.append(
                str(error)
                if str(error).startswith(label)
                else f"{label}: malformed ({error})"
            )
    # A parallel is the KJV's wording as the edition prints it, so no
    # override, its own or another's, may change the words it quotes.
    for label, ref, start, end in parallels:
        if any(start < b and a < end for a, b in occupied[ref]):
            errors.append(f"{label}: kjv parallel is words an override edits")
    return compiled, errors


# Pierpont's instructions where the Greek is shared

CATEGORY = "c"
# The compatibility of a row no unit carries out.
UNCARRIED = frozenset({"no-greek-unit", "unattached"})


def instruction_key(row: Instruction) -> str:
    """The decision's key for an instruction: its source and entry."""
    return f"{row['source']} {row['entry']}"


def category_c_rows(instructions: Sequence[Instruction]) -> dict[str, Instruction]:
    """Pierpont's category-c rows by their decision keys."""
    return {
        instruction_key(row): row
        for row in instructions
        if row["source"] == PIERPONT
        and (row.get("weight") or {}).get("category") == CATEGORY
    }


def instruction_entries(
    declared: Mapping[str, Mapping[str, Any]],
    instructions: Sequence[Instruction],
    target: Greek,
    carriers: Mapping[str, Carrier],
    evidence: Evidence,
) -> list[dict[str, Any]]:
    """The decisions on Pierpont's category-c rows (edition/byzantine.json
    instructions), checked, as the readings they add: one entry per edit
    that carries itself (carriers), in the form validate_overrides binds,
    with the instruction in place of written edits. Each decision names the
    RP2026 Greek it is about, found once in the row's verse, so that it
    cannot outlive the text it judges; the source supplies the English.

    Stops the build on a decision that names no category-c row or leaves
    one undecided, Greek that does not occur once in RP2026 at the row's
    verse, evidence not in its source (evidence), a former version on a
    decision that makes no edit itself, or an edit that would carry itself
    without binding uniquely to shared Greek.
    """
    category = category_c_rows(instructions)
    require(
        set(declared) == set(category),
        f"Category-c decisions and rows differ: {sorted(set(declared) ^ set(category))}",
    )
    result: list[dict[str, Any]] = []
    for key, entry in declared.items():
        source = category[key]
        refs = source["refs"]
        label = f"instruction {key}"
        for quotation in entry["greek"]:
            hits = sum(
                len(
                    letter_hits(
                        target.rp_alignment.text.get(target.structure.rp_ref(ref), ()),
                        quotation,
                    )
                )
                for ref in refs
            )
            require(quotation.split() and hits == 1, f"{label}: Greek must occur once")
        carrier = carriers.get(key)
        if carrier is None or carrier["kind"] != "itself":
            evidence(label, entry.get("evidence", {}), set(refs))
            require(
                "former" not in entry,
                f"{label}: former goes on the reading that makes the edit",
            )
            continue
        require(
            source.get("bind") == "unique" and source.get("compatibility") in UNCARRIED,
            f"{label}: the instruction does not bind uniquely to shared Greek",
        )
        require(len(refs) == 1, f"{label}: an instruction spanning verses")
        require(
            len(entry["greek"]) == len(source["edits"]),
            f"{label}: each edit of the instruction needs its Greek",
        )
        result.append(
            {
                "id": refs[0],
                "kind": "edit",
                "instruction": source,
                "greek": entry["greek"],
                "why": entry["why"],
                "evidence": {
                    PIERPONT: {"entry": source["entry"], "quote": source["raw"]},
                    **entry.get("evidence", {}),
                },
                **({"former": entry["former"]} if "former" in entry else {}),
            }
        )
    # A reading read from an instruction is keyed by its verse, as a written
    # correction of shared Greek is; two at one verse would share the key.
    verses = [e["id"] for e in result]
    shared = sorted({v for v in verses if verses.count(v) > 1})
    require(
        not shared,
        f"Two instructions carry themselves at one verse; write one reading "
        f"with both edits and name it as their carrier: {shared}",
    )
    return result


def enclosing(
    e: InstructionEdit, override: Override, kjv: Mapping[str, str]
) -> tuple[BoundEdit, int, int] | None:
    """The bound edit of an override within which an instruction's edit
    stands, with the edit's offsets in the verse: its words, or its insertion
    point, which may stand on either side of a space."""
    ref = e["ref"]
    text = kjv[ref]
    lo, hi = kjv_bounds(text, e)
    for b in override["bound"]:
        if b["ref"] != ref:
            continue
        start, end = lo, hi
        if start == end:
            if b["end"] <= start and not text[b["end"] : start].strip():
                start = end = b["end"]
            elif end <= b["start"] and not text[end : b["start"]].strip():
                start = end = b["start"]
        if b["start"] <= start <= end <= b["end"]:
            return b, start, end
    return None


def bound_edits(row: Instruction) -> list[InstructionEdit]:
    """An instruction's edits bound to a verse, by their words."""
    return [
        e
        for e in row.get("edits", [])
        if e.get("ref") is not None and e.get("word_range") is not None
    ]


def overlapping_readings(
    row: Instruction, overrides: Sequence[Override], kjv: Mapping[str, str]
) -> list[str]:
    """Readings whose edits overlap an instruction's, without judging meaning."""
    return [
        o["id"]
        for o in overrides
        if any(
            e["ref"] == b["ref"]
            and overlaps(*kjv_bounds(kjv[e["ref"]], e), [(b["start"], b["end"])])
            for e in bound_edits(row)
            for b in o["bound"]
        )
    ]


def covering(
    row: Instruction,
    overrides: Sequence[Override],
    kjv: Mapping[str, str],
    *,
    ordered: bool = True,
) -> str | None:
    """The override whose bound edits carry out every edit of an instruction
    word for word, if one does, for the review: each edit's words stand
    within one of its bound edits (enclosing), and the words of the whole
    replacement, the unchanged words around the instruction's own span
    included, are the override's, apart from punctuation and italic
    brackets. Not ordered, the same words in another order count too (John
    7:52). Neither decides what executes: the editor names a reading that
    carries an edit out (carriers)."""
    edits = bound_edits(row)
    if not edits:
        return None

    def covered(e: InstructionEdit, o: Override) -> bool:
        found = enclosing(e, o, kjv)
        if found is None:
            return False
        b, start, end = found
        proposed = " ".join(
            (b["old"][: start - b["start"]], e["new"], b["old"][end - b["start"] :])
        )
        mine, theirs = words(proposed), words(b["new"])
        return mine == theirs or (not ordered and sorted(mine) == sorted(theirs))

    return next((o["id"] for o in overrides if all(covered(e, o) for e in edits)), None)


def carriers(
    declared: Mapping[str, Mapping[str, Any]],
    rows: Sequence[Instruction],
    overrides: Sequence[Override],
    kjv: Mapping[str, str],
) -> dict[str, Carrier]:
    """The executor of each category-c edit. A named reading is the editor's
    judgment; check that it exists and concerns the instruction's passage,
    not whether its words express the instruction's meaning. An unnamed
    overlapping reading prevents independent execution, but does not imply
    fulfillment. A nochange may coexist with a reading of the same words."""
    sources = category_c_rows(rows)
    require(
        set(declared) == set(sources),
        f"Category-c decisions and rows differ: {sorted(set(declared) ^ set(sources))}",
    )
    # The readings: an override read from an instruction is the row itself.
    readings = {o["id"]: o for o in overrides if "instruction" not in o}
    result: dict[str, Carrier] = {}
    for key, entry in declared.items():
        row = sources[key]
        label = f"instruction {key}"
        taken = row.get("displaced_by") or []
        carrier: Carrier | None = None
        if entry["kind"] == "nochange":
            require("carrier" not in entry, f"{label}: nochange has no carrier")
            require(
                row.get("compatibility") != "compatible",
                f"{label}: nochange, but its unit executes the instruction",
            )
            continue
        if row.get("compatibility") == "compatible":
            require("carrier" not in entry, f"{label}: its unit carries it out")
            carrier = {"kind": "unit", "ids": [a["unit"] for a in row.get("units", [])]}
        elif "carrier" in entry:
            named = entry["carrier"]
            require(named in readings, f"{label}: carrier {named} is no reading")
            require(
                named in taken
                or any(e["ref"] in row["refs"] for e in readings[named]["bound"]),
                f"{label}: reading {named} concerns another passage",
            )
            carrier = {"kind": "reading", "ids": [named]}
        if carrier is None:
            conflicts = sorted(
                set(taken)
                | set(overlapping_readings(row, list(readings.values()), kjv))
            )
            require(
                not conflicts,
                f"{label}: overlaps readings {', '.join(conflicts)}; "
                "decide whether a reading carries the instruction or revise the edits",
            )
            ref = row["refs"][0]
            require(
                ref not in readings,
                f"{label}: the reading at {ref} does not carry it out; add its edit "
                "to the reading, or name it as the carrier",
            )
            carrier = {"kind": "itself", "ids": [ref]}
        result[key] = carrier
    return result


# Placements


def instruction(row: Report | SelectedListRow | Instruction) -> TypeIs[Instruction]:
    """Whether a witness's row is an instruction, which has edits to bind."""
    return "edits" in row


def place(
    rows: Sequence[Row], units: Sequence[Unit], placements: Iterable[Placement]
) -> tuple[list[Row], list[str], list[Placement]]:
    """Attach witness rows (apparatus reports or instructions) by hand.

    A placement names a row by witness and entry and a unit by its Greek key,
    several units, or none (`unit: null`: the row is about Greek both texts
    share, or about no Greek at all). Returns (rows, errors, stale) where
    stale lists placements the code now makes on its own.
    """
    result = deepcopy(list(rows))
    index = {
        (r.get("witness") or r.get("source"), r["entry"]): i
        for i, r in enumerate(result)
    }
    errors: list[str] = []
    stale: list[Placement] = []
    for decision in placements:
        label = f"placement {decision.get('witness')}:{decision.get('entry')}"
        try:
            key = decision["witness"], decision["entry"]
            require(decision.get("why", "").strip(), f"{label}: missing reason")
            if key not in index:
                raise CheckFailed(f"{label}: no such witness row")
            row = result[index[key]]
            require(
                row.get("ref") == decision["ref"],
                f"{label}: the row is at {row.get('ref')}",
            )
            found = placed_units(decision, units, label)
            ids = [u["id"] for u in found]
            current = [a["unit"] for a in row.get("units", [])]
            # Stale: the code already puts the row where the placement does.
            # A null placement is stale only if the row already had no Greek unit.
            already = (
                row.get("scope") == "no-greek-unit"
                if not ids
                else row.get("scope") == "greek"
            )
            if current == ids and already and row.get("method") != "hand":
                stale.append(decision)
            row.pop("reason", None)
            if instruction(row):
                bound = [e for e in row["edits"] if e.get("bind") == "unique"]
                if ids and len(bound) > 1 and len(bound) == len(ids):
                    for edit, unit in zip(
                        sorted(
                            bound, key=lambda e: (ref_key(e["ref"]), e["word_range"])
                        ),
                        sorted(found, key=lambda u: (ref_key(u["ref"]), u["tr_range"])),
                    ):
                        edit.update(
                            {
                                "units": [unit["id"]],
                                "method": "hand",
                                "scope": "constituent",
                            }
                        )
                else:
                    for edit in bound:
                        edit.update(
                            {
                                "units": list(ids),
                                "method": "hand" if ids else None,
                                "scope": "constituent",
                            }
                        )
                row["units"] = [
                    {"unit": uid, "scope": "constituent", "method": "hand"}
                    for uid in ids
                ]
            else:  # an apparatus report
                row["units"] = [{"unit": uid, "scope": "constituent"} for uid in ids]
            row["scope"] = "greek" if ids else "no-greek-unit"
            if not ids:
                row["reason"] = decision["why"]
            row["method"] = "hand"
            row["placement"] = decision["why"]
        except (CheckFailed, ValueError, KeyError, TypeError, AttributeError) as error:
            errors.append(
                str(error)
                if str(error).startswith(label)
                else f"{label}: malformed ({error})"
            )
    return result, errors, stale


def place_inventories(
    units: Sequence[Unit],
    unmatched: Sequence[Unmatched],
    placements: Iterable[Placement],
) -> tuple[list[Unit], list[Unmatched], list[str]]:
    """Attach by hand the rows of the Greek apparatuses that give the Received
    Text a reading (Boyd's and the printed RP2026's) which the code cannot
    place on a unit. A placement names the row by its inventory and entry and
    the units by their Greek keys, or none (`unit: null`: the row is about no
    difference of the two texts). Returns the units, the rows still
    unmatched, and what is wrong: a placement of a row the code places on
    its own, or of no row, or one that names no unit."""
    result = deepcopy(list(units))
    rows = {(r["inventory"], r["entry"]): r for r in unmatched}
    errors: list[str] = []
    placed: set[tuple[str, int]] = set()
    for decision in placements:
        label = f"placement {decision.get('witness')} {decision.get('entry')}"
        try:
            key = (decision["witness"], cast(int, decision["entry"]))
            require(decision.get("why", "").strip(), f"{label}: missing reason")
            require(
                key in rows,
                f"{label}: the code places the row, or there is no such row",
            )
            require(
                rows[key]["target_ref"] == decision["ref"],
                f"{label}: the row is at {rows[key]['target_ref']}",
            )
            row = rows[key]
            for unit in placed_units(decision, result, label):
                attachment: UnitInventory = {
                    "inventory": key[0],
                    "entry": key[1],
                    "scope": "constituent",
                    "method": "hand",
                }
                # Hodges and Farstad's side is Boyd's to report, as where the
                # code places his note (units.reconcile).
                if key[0] == "tcgnt":
                    attachment["hf"] = row["hf"]
                unit["inventories"].append(attachment)
                if key[0] == "tcgnt":
                    record_side(unit, row)
                if key[0] not in unit["found_in"]:
                    unit["found_in"] = [*unit["found_in"], key[0]]
            placed.add(key)
        except (CheckFailed, ValueError, KeyError, TypeError, AttributeError) as error:
            errors.append(
                str(error)
                if str(error).startswith(label)
                else f"{label}: malformed ({error})"
            )
    remaining = [r for r in unmatched if (r["inventory"], r["entry"]) not in placed]
    return result, remaining, errors


# Note lemmas


def validate_lemmas(
    entries: Iterable[Mapping[str, Any]], units: Sequence[Unit]
) -> list[str]:
    """What is wrong with each note lemma decision: its unit, the number of
    its note, its lemma and its reason."""
    errors: list[str] = []
    by_id = {u["id"]: u for u in units}
    seen: set[tuple[str, int]] = set()
    for entry in entries:
        label = f"note lemma {entry.get('id')}"
        unit_id = entry.get("id")
        edit_index = entry.get("edit")
        if not isinstance(unit_id, str) or unit_id not in by_id:
            errors.append(f"{label}: no such unit")
        if type(edit_index) is not int or edit_index < 1:
            errors.append(f"{label}: edit is the note's 1-based index")
        if (
            not isinstance(entry.get("lemma"), str)
            or not entry["lemma"].strip()
            or not isinstance(entry.get("why"), str)
            or not entry["why"].strip()
        ):
            errors.append(f"{label}: lemma and why required")
        if not isinstance(unit_id, str) or type(edit_index) is not int:
            continue
        key = (unit_id, edit_index)
        if key in seen:
            errors.append(f"{label}: duplicate")
        seen.add(key)
    return errors


def lemma_entries(lemmas: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The lemma decisions as rows of the unit they concern and the number of
    the note, from their keys: "1CO 15:39#1 TR" and "1CO 15:39#1 TR#2"."""
    rows: list[dict[str, Any]] = []
    for key, entry in lemmas.items():
        unit_id, _, tail = key.rpartition(" ")
        require(
            re.fullmatch(r"TR(#[1-9]\d*)?", tail),
            f"note lemma {key}: key is not a TR note's",
        )
        rows.append(
            {"id": unit_id, "edit": int(tail[3:]) if "#" in tail else 1, **entry}
        )
    return rows
