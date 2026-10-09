"""The editor's decisions about the New Testament, validated against the
pinned sources.

The readings of edition/byzantine.json (subjective): the wording where no
instruction settles a unit, or a ruling that a reported difference is not
applied. edition/byzantine-placements.json (objective): which Greek unit a
witness's row is about where code cannot tell. The lemmas of
edition/byzantine.json: a footnote lemma widened by hand. Every entry is
keyed by verse and Greek, so unit numbering may change under it; every quote
is checked against the source it cites, so nothing can drift unnoticed.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from typing import Any, TypeIs, TypeVar

from bible.byzantine import BOOKS, FAA, WITNESSES
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
)
from bible.byzantine.tags import asserted
from bible.byzantine.units import keyed_units

# A witness's row that a placement can attach: an apparatus report, a
# selected list's footnote, or an instruction.
Row = TypeVar("Row", Report, SelectedListRow, Instruction)

# The fields of an override's edit; policy.check holds the decisions' own.
EDIT_KEYS = ("ref", "from", "to", "occurrence", "after", "before")

# A verse's supplied words: the offsets and the words of each.
type Supplied = Mapping[str, Sequence[tuple[int, int, str]]]


def ref_key(ref: str) -> tuple[int, int, int]:
    book, address = ref.split()
    chapter, verse = address.split(":")
    return BOOKS.index(book), int(chapter), int(verse)


def resolve(greek: Mapping[str, Any], units: Sequence[Unit], label: str) -> Unit:
    """The one unit a Greek key names: verse, tr and rp words, optional nth."""
    for field in ("ref", "tr", "rp"):
        if not isinstance(greek.get(field), str):
            raise ValueError(f"{label}: Greek key needs ref, tr and rp strings")
    found = keyed_units(units, greek["ref"], greek["tr"], greek["rp"])
    if "nth" in greek:
        nth = greek["nth"]
        if type(nth) is not int or not 1 <= nth <= len(found):
            raise ValueError(f"{label}: nth does not select a unit")
        found = [found[nth - 1]]
    if len(found) != 1:
        raise ValueError(
            f"{label}: Greek key {greek['ref']} {greek['tr']!r} -> {greek['rp']!r} names {len(found)} units"
        )
    return found[0]


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
        if unit["id"] != key:
            raise ValueError(f"{label}: the unit is {unit['id']}")
        if unit["hf"] == decision["side"]:
            raise ValueError(f"{label} changes nothing")
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
                raise ValueError("malformed supplied-word brackets")
            start = len(text)
        elif char == "]":
            if start is None or start == len(text) or not text[start:].strip():
                raise ValueError("malformed supplied-word brackets")
            ranges.append((start, len(text)))
            start = None
        else:
            text += char
    if start is not None:
        raise ValueError("malformed supplied-word brackets")
    return text, ranges


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
) -> tuple[list[Override], list[str]]:
    """Each override bound to the pinned KJV and its evidence to its sources.

    Returns (compiled, errors). A compiled override has everything as
    written, and its units' ids (`unit_ids`), its edits at character offsets
    (`bound`) and its tags (`tag_set`).
    witness_rows: {witness: {entry: row}} for the instruction sources and the
    apparatus; texts: {witness: verses} for the revisions. Optional
    revision_citations carries normalized text and USJ supplied spans;
    faa_rows supplies verse notes independently of apparatus reports.
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
            if not ids or len(ids) != len(set(ids)) or claimed & set(ids):
                raise ValueError(f"{label}: missing or duplicate unit")
            if entry.get("id") != override_id(ids):
                raise ValueError(f"{label}: id should be {override_id(ids)}")
            kind = entry.get("kind")
            edits = entry.get("edits", [])
            if kind not in {"edit", "nochange"} or (kind == "nochange") == bool(edits):
                raise ValueError(f"{label}: kind edit needs edits, nochange has none")
            why = entry.get("why")
            if not isinstance(why, str) or not why.strip():
                raise ValueError(f"{label}: why required")
            if len(re.findall(r"[.!?](?:\s|$)", why.strip())) > 2:
                raise ValueError(f"{label}: why is at most two sentences")
            tags = asserted(entry.get("tags", []))
            if not any(t.group == "from" for t in tags) or not any(
                t.group == "gram" for t in tags
            ):
                raise ValueError(f"{label}: one from: and one gram: tag required")
            refs = {g["ref"] for g in entry["units"]}
            books = {r.split()[0] for r in refs}
            if len(books) != 1:
                raise ValueError(f"{label}: units in more than one book")
            bound: list[BoundEdit] = []
            for edit in edits:
                unknown = set(edit) - set(EDIT_KEYS)
                if unknown:
                    raise ValueError(f"{label}: unknown edit fields {sorted(unknown)}")
                ref, old, new = edit["ref"], edit["from"], edit["to"]
                if ref not in kjv or ref.split()[0] not in books:
                    raise ValueError(
                        f"{label}: edit at {ref} is not in the units' book"
                    )
                if (
                    not isinstance(old, str)
                    or not isinstance(new, str)
                    or "\\" in old + new
                    or "\n" in old + new
                ):
                    raise ValueError(f"{label}: from and to are plain strings")
                if new != new.strip() or "  " in new:
                    raise ValueError(f"{label}: to has stray spaces")
                text = kjv[ref]
                if old:
                    if old.strip() == text.strip():
                        raise ValueError(
                            f"{label}: an override is a fragment, not the verse"
                        )
                    hits = [m.start() for m in re.finditer(re.escape(old), text)]
                    if "occurrence" in edit:
                        n = edit["occurrence"]
                        if type(n) is not int or not 1 <= n <= len(hits):
                            raise ValueError(
                                f"{label}: occurrence does not select a match at {ref}"
                            )
                        hits = [hits[n - 1]]
                    if len(hits) != 1:
                        raise ValueError(
                            f"{label}: from must occur exactly once at {ref} ({len(hits)} found)"
                        )
                    start = hits[0]
                    end = start + len(old)
                    if cuts_word(text, start, end):
                        raise ValueError(f"{label}: from cuts through a word at {ref}")
                    # The same words are a change only when the KJV supplies
                    # some of them in italics and RP2026 has Greek for them:
                    # the override sets them in roman (John 19:17 "the place").
                    unstyle = old == new and any(
                        a < end and start < b for a, b, _ in supplied.get(ref, [])
                    )
                    if old == new and not unstyle:
                        raise ValueError(f"{label}: from equals to at {ref}")
                else:
                    anchor = edit.get("after") or edit.get("before")
                    if not anchor or not new or ("after" in edit and "before" in edit):
                        raise ValueError(
                            f"{label}: an insertion needs to and one of after/before"
                        )
                    hits = [m.start() for m in re.finditer(re.escape(anchor), text)]
                    if len(hits) != 1:
                        raise ValueError(
                            f"{label}: anchor must occur exactly once at {ref}"
                        )
                    if cuts_word(text, hits[0], hits[0] + len(anchor)):
                        raise ValueError(
                            f"{label}: anchor cuts through a word at {ref}"
                        )
                    start = end = hits[0] + (len(anchor) if "after" in edit else 0)
                if any(
                    start < b and a < end or (start == end == a == b)
                    for a, b in [
                        *occupied[ref],
                        *((e["start"], e["end"]) for e in bound if e["ref"] == ref),
                    ]
                ):
                    raise ValueError(f"{label}: overlaps another edit at {ref}")
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
            if not isinstance(evidence, dict) or not evidence:
                raise ValueError(f"{label}: evidence required")
            permitted = refs | {e["ref"] for e in bound}
            for witness, item in evidence.items():
                quote = item.get("quote") if isinstance(item, dict) else None
                if not isinstance(quote, str) or not quote.strip():
                    raise ValueError(f"{label}: evidence {witness} needs a quote")
                if witness == FAA and ("ref" in item or "field" in item):
                    if (
                        set(item) != {"ref", "field", "quote"}
                        or item.get("field") != "source_notes"
                    ):
                        raise ValueError(
                            f"{label}: faa verse note needs ref, field source_notes and quote only"
                        )
                    ref = item["ref"]
                    faa_row = (faa_rows or {}).get(ref)
                    if ref not in permitted or faa_row is None:
                        raise ValueError(
                            f"{label}: faa verse note is about another or missing verse"
                        )
                    notes = " ".join(faa_row.get("source_notes", "").split())
                    if quote not in notes:
                        raise ValueError(
                            f"{label}: faa verse note does not contain the quote"
                        )
                elif witness in texts:
                    ref = item.get("ref")
                    verse = " ".join(texts[witness].get(ref, "").split())
                    normalized = " ".join(quote.split())
                    # A bracket the source itself prints is quoted verbatim.
                    bracketed = (
                        "[" in normalized or "]" in normalized
                    ) and normalized not in verse
                    wording, marked = (
                        bracketed_quote(normalized) if bracketed else (normalized, [])
                    )
                    if ref not in permitted or verse.count(wording) != 1:
                        raise ValueError(
                            f"{label}: {witness} quote is not in the verse once"
                        )
                    if bracketed:
                        metadata = (revision_citations or {}).get(witness, {}).get(ref)
                        if metadata is None or metadata["text"] != verse:
                            raise ValueError(
                                f"{label}: {witness} supplied-word metadata missing or stale"
                            )
                        start = verse.index(wording)
                        end = start + len(wording)
                        expected = [
                            (max(a, start) - start, min(b, end) - start)
                            for a, b in metadata["supplied"]
                            if a < end and start < b
                        ]
                        if marked != expected:
                            raise ValueError(
                                f"{label}: {witness} brackets differ from source supplied words"
                            )
                elif witness in witness_rows:
                    if witness == FAA and set(item) != {"entry", "quote"}:
                        raise ValueError(
                            f"{label}: faa report needs entry and quote only"
                        )
                    cited = witness_rows[witness].get(item.get("entry"))
                    if cited is None:
                        raise ValueError(
                            f"{label}: {witness} has no entry {item.get('entry')}"
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
                    if quote not in haystack:
                        raise ValueError(
                            f"{label}: {witness} {item.get('entry')} does not contain the quote"
                        )
                    if cited.get("ref") not in permitted and not (
                        set(cited.get("refs", [])) & refs
                    ):
                        raise ValueError(
                            f"{label}: {witness} {item.get('entry')} is about another verse"
                        )
                elif witness in WITNESSES:
                    raise ValueError(
                        f"{label}: {witness} is not loaded; its quote cannot be checked"
                    )
                else:
                    raise ValueError(f"{label}: unknown witness {witness}")
            override: Override = {
                "id": entry["id"],
                "units": entry["units"],
                "kind": kind,
                "tags": entry["tags"],
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
        except (ValueError, KeyError, TypeError, AttributeError) as error:
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
            if not decision.get("why", "").strip():
                raise ValueError(f"{label}: missing reason")
            if key not in index:
                raise ValueError(f"{label}: no such witness row")
            row = result[index[key]]
            if row.get("ref") != decision["ref"]:
                raise ValueError(f"{label}: the row is at {row.get('ref')}")
            wanted = decision["unit"]
            keys: list[GreekKey] = (
                []
                if wanted is None
                else wanted if isinstance(wanted, list) else [wanted]
            )
            found = [
                resolve({**g, "ref": g.get("ref", decision["ref"])}, units, label)
                for g in keys
            ]
            ids = [u["id"] for u in found]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{label}: duplicate unit")
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
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            errors.append(
                str(error)
                if str(error).startswith(label)
                else f"{label}: malformed ({error})"
            )
    return result, errors, stale


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
            errors.append(f"{label}: edit is a 1-based index")
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
        if not tail.startswith("TR") or not re.fullmatch(r"TR(#[1-9]\d*)?", tail):
            raise ValueError(f"note lemma {key}: key is not a TR note's")
        rows.append(
            {"id": unit_id, "edit": int(tail[3:]) if "#" in tail else 1, **entry}
        )
    return rows
