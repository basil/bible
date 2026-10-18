"""The editor's decisions about the New Testament, validated against the
pinned sources.

The readings of edition/byzantine.json (subjective): the wording where no
instruction settles a unit, a ruling that a reported difference is not
applied, or, keyed by a verse rather than units, a correction of the English
where the TR and RP2026 share the Greek. edition/byzantine-placements.json (objective): which Greek unit a
witness's row is about where code cannot tell. The lemmas of
edition/byzantine.json: a footnote lemma widened by hand. Every entry is
keyed by verse and Greek, so unit numbering may change under it; every quote
is checked against the source it cites, so nothing can drift unnoticed.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from typing import Any, TypeIs, TypeVar, cast

from bible.byzantine import BOOKS, FAA, WITNESSES, greek
from bible.byzantine.crosswire import curly_apostrophes
from bible.byzantine.rows import (
    BoundEdit,
    FaaRow,
    GreekKey,
    Instruction,
    Override,
    Placement,
    Report,
    SelectedListRow,
    Unit,
    UnitInventory,
    Unmatched,
)
from bible.byzantine.tags import asserted
from bible.byzantine.units import keyed_units, record_side
from bible.checks import CheckFailed, present, require
from bible.scripture import plain

# A witness's row that a placement can attach: an apparatus report, a
# selected list's footnote, or an instruction.
Row = TypeVar("Row", Report, SelectedListRow, Instruction)

# The fields of an override's edit; policy.check holds the decisions' own.
EDIT_KEYS = ("ref", "from", "to", "occurrence", "after", "before", "greek")

# A verse's supplied words: the offsets and the words of each.
type Supplied = Mapping[str, Sequence[tuple[int, int, str]]]


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

    wanted = [greek.letter_key(w) for w in cited.split()]
    hits = greek.occurrences(
        [greek.letter_key(w) for w in printed[target]["accented"]], wanted
    )
    require(
        len(hits) == 1, f"greek must occur once at RP2026 {target} ({len(hits)} found)"
    )
    a, b = hits[0], hits[0] + len(wanted)
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
) -> tuple[list[Override], list[str]]:
    """Each override bound to the pinned KJV and its evidence to its sources.

    Returns (compiled, errors). A compiled override has everything as
    written, and its units' ids (`unit_ids`), its edits at character offsets
    (`bound`) and its tags (`tag_set`).
    witness_rows: {witness: {entry: row}} for the instruction sources and the
    apparatus; texts: {witness: verses} for the revisions. Optional
    revision_citations carries normalized text and USJ supplied spans;
    faa_rows supplies verse notes independently of apparatus reports.
    printed, alignment and structure, RP2026's, check the Greek of an
    override without units (shared_greek).
    """
    compiled: list[Override] = []
    errors: list[str] = []
    claimed: set[str] = set()
    occupied: defaultdict[str, list[tuple[int, int]]] = defaultdict(list)
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
            if kind not in {"edit", "nochange"} or (kind == "nochange") == bool(edits):
                raise CheckFailed(f"{label}: kind edit needs edits, nochange has none")
            require(ids or kind == "edit", f"{label}: without units, the kind is edit")
            why = entry.get("why")
            if not isinstance(why, str) or not why.strip():
                raise CheckFailed(f"{label}: why required")
            tags = asserted(entry.get("tags", []))
            require(
                not ids or len(re.findall(r"[.!?](?:\s|$)", why.strip())) <= 2,
                f"{label}: why is at most two sentences",
            )
            require(
                not ids
                or (
                    any(t.group == "from" for t in tags)
                    and any(t.group == "gram" for t in tags)
                ),
                f"{label}: one from: and one gram: tag required",
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
                    not any(
                        start < b and a < end or (start == end == a == b)
                        for a, b in [
                            *occupied[ref],
                            *((e["start"], e["end"]) for e in bound if e["ref"] == ref),
                        ]
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
            evidence = entry.get("evidence", {})
            require(
                isinstance(evidence, dict) and evidence, f"{label}: evidence required"
            )
            permitted = refs | {e["ref"] for e in bound}
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
                elif witness in texts:
                    ref = item.get("ref")
                    verse = plain(texts[witness].get(ref, ""))
                    normalized = plain(quote)
                    # A bracket the source itself prints is quoted verbatim.
                    bracketed = (
                        "[" in normalized or "]" in normalized
                    ) and normalized not in verse
                    wording, marked = (
                        bracketed_quote(normalized) if bracketed else (normalized, [])
                    )
                    require(
                        ref in permitted and verse.count(wording) == 1,
                        f"{label}: {witness} quote is not in the verse once",
                    )
                    if bracketed:
                        metadata = (revision_citations or {}).get(witness, {}).get(ref)
                        if metadata is None or metadata["text"] != verse:
                            raise CheckFailed(
                                f"{label}: {witness} supplied-word metadata missing or stale"
                            )
                        start = verse.index(wording)
                        end = start + len(wording)
                        expected = [
                            (max(a, start) - start, min(b, end) - start)
                            for a, b in metadata["supplied"]
                            if a < end and start < b
                        ]
                        require(
                            marked == expected,
                            f"{label}: {witness} brackets differ from source supplied words",
                        )
                elif witness in witness_rows:
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
                        cited.get("ref") in permitted
                        or set(cited.get("refs", [])) & refs,
                        f"{label}: {witness} {item.get('entry')} is about another verse",
                    )
                elif witness in WITNESSES:
                    raise CheckFailed(
                        f"{label}: {witness} is not loaded; its quote cannot be checked"
                    )
                else:
                    raise CheckFailed(f"{label}: unknown witness {witness}")
            override: Override = {
                "id": entry["id"],
                "units": entry.get("units", []),
                "kind": kind,
                "tags": entry.get("tags", []),
                "why": why,
                "evidence": evidence,
                "unit_ids": ids,
                "bound": bound,
                "tag_set": tags,
            }
            if "edits" in entry:
                override["edits"] = edits
            compiled.append(override)
            claimed.update(ids)
            for e in bound:
                occupied[e["ref"]].append((e["start"], e["end"]))
        except (CheckFailed, ValueError, KeyError, TypeError, AttributeError) as error:
            errors.append(
                str(error)
                if str(error).startswith(label)
                else f"{label}: malformed ({error})"
            )
    return compiled, errors


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
            # A null placement is stale only if the row was already out of scope.
            already = (
                row.get("scope") == "out-of-scope"
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
            row["scope"] = "greek" if ids else "out-of-scope"
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
