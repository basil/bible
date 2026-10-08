"""Independent checks on the prepared books of the Orthodox Liturgical English
Bible (OLEB), read as USJ documents.

I1 every unit has one disposition; I2 every character in which the OLEB
differs from the pinned KJV lies inside a declared edit or its seam, recomputed
here without the executor; I3 every edit has its note, at its place, quoting
its source words; I4 the 7,953-verse inventory, with RP's omissions and
relocations.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from bible import lemmas, scripture, usj
from bible.byzantine.edit import renumber, supplied_content
from bible.byzantine.greek import Structure
from bible.byzantine.rows import Disposition, Edit, NoteScope, Unit
from bible.checks import present
from bible.scripture import Verse
from bible.usj import Content, Document, Node


def signature(note: str | Node) -> str:
    return usj.serialize([note])


def _italic_content(
    content: Iterable[str | Node], italic: bool = False
) -> list[tuple[str, bool]]:
    """Character/italic pairs, without notes or layout spacing."""
    result: list[tuple[str, bool]] = []
    for item in content:
        if isinstance(item, str):
            result.extend((char, italic) for char in item if not char.isspace())
        elif item.get("type") != "note":
            result.extend(
                _italic_content(
                    item.get("content", []),
                    italic or item.get("marker") in {"add", "it"},
                )
            )
    return result


def _verse_italic_span(
    document: Document, verse: Verse, start: int, end: int
) -> list[tuple[str, bool]]:
    """Read a span directly from the document, independently of the executor."""
    result: list[tuple[str, bool]] = []
    offset = 0
    for index, (block, lo, hi, _) in enumerate(verse.parts):
        if index:
            offset += 1  # scripture.verses joins paragraph parts with a newline

        def read(content: Iterable[str | Node], italic: bool = False) -> None:
            nonlocal offset
            for item in content:
                if isinstance(item, str):
                    for char in item:
                        if start <= offset < end and not char.isspace():
                            result.append((char, italic))
                        offset += 1
                elif item.get("type") != "note":
                    read(
                        item.get("content", []),
                        italic or item.get("marker") in {"add", "it"},
                    )

        read(document["content"][block]["content"][lo:hi])
    return result


def closure(source: str, edits: Sequence[Edit]) -> str:
    """Compile the declared English independently of the USJ executor."""
    changes: list[tuple[int, int, str]] = []
    for edit in edits:
        external: list[tuple[int, int, str]] = []
        lo, hi = edit["range"]
        start, end = edit["applied_range"]
        if source[lo:hi] != edit["old"] or not 0 <= start <= lo <= hi <= end <= len(
            source
        ):
            raise ValueError("stale source offsets")
        if any(c not in " \n\t,;:.!?" for c in source[start:lo] + source[hi:end]):
            raise ValueError("punctuation seam changes words")
        new = edit["new"]
        rendered = usj.text_of(supplied_content(edit["rendered"]))
        for seam in edit["seams"]:
            a, b = seam["range"]
            if not 0 <= a <= b <= len(source):
                raise ValueError("stale seam offsets")
            if seam["rule"] == 2 and seam.get("external"):
                if source[a:b] != seam["from"]:
                    raise ValueError("stale external punctuation")
                if any(c not in ",;:.?!" for c in seam["from"] + seam["to"]):
                    raise ValueError("punctuation seam changes words")
                external.append((a, b, seam["to"]))
            elif seam["rule"] == 4 and seam.get("external"):
                old, initial = seam["from"], seam["to"]
                if (
                    b != a + 1
                    or source[a:b] != old
                    or len(initial) != 1
                    or not old.isalpha()
                    or old == initial
                    or old.casefold() != initial.casefold()
                    or (a and source[a - 1].isalpha())
                ):
                    raise ValueError("case adjustment changes more than an initial")
                external.append((a, b, initial))
            elif seam["rule"] == 4:
                before, after = seam["from"], seam["to"]
                first_letter = re.search(r"[A-Za-zÆæ]", before)
                if (
                    first_letter is None
                    or len(before) != len(after)
                    or before[: first_letter.start()] != after[: first_letter.start()]
                    or before[first_letter.start() + 1 :]
                    != after[first_letter.start() + 1 :]
                    or before[first_letter.start()].casefold()
                    != after[first_letter.start()].casefold()
                    or usj.text_of(supplied_content(after)) != new
                ):
                    raise ValueError("case adjustment changes more than an initial")
            elif seam["rule"] == 3:
                continue  # a kept character style changes no words
            elif seam["rule"] != 2:
                raise ValueError("unknown seam rule")
        if new != rendered:
            raise ValueError("undeclared change to new words")
        prefix, suffix = edit.get("prefix", ""), edit.get("suffix", "")
        if (prefix or suffix) and (lo != hi or any(c != " " for c in prefix + suffix)):
            raise ValueError("insertion seam changes words")
        changes.append((start, end, prefix + rendered + suffix))
        # The source model declares the splice before its external seams.
        # Keep that order for two insertions at the same immutable offset.
        changes.extend(external)
    # Replacements at the same offset precede insertions in the source model;
    # applying text backwards needs the reverse order to reproduce that.
    ordered = sorted(changes, key=lambda c: (c[0], c[1] > c[0]), reverse=True)
    for i, (a, b, _) in enumerate(ordered):
        if any(a < y and x < b for x, y, _ in ordered[i + 1 :]):
            raise ValueError("overlapping declared changes")
    text = source
    for a, b, new in ordered:
        text = text[:a] + new + text[b:]
    return text


def checks(
    original: Mapping[str, Document],
    prepared: Mapping[str, Document],
    units: Sequence[Unit],
    dispositions: Sequence[Disposition],
    structure: Structure,
) -> dict[str, str]:
    """One result per invariant: "pass" or the first failure, by name."""
    results = {f"I{i}": "pass" for i in range(1, 5)}

    def fail(key: str, label: str) -> None:
        if results[key] == "pass":
            results[key] = label

    def identities(selected: Mapping[str, Any]) -> set[tuple[str, int | str]]:
        return {(i["source"], i["entry"]) for i in selected.get("joint", [])}

    def shared_witness(row: Disposition, owner: Disposition) -> bool:
        # `basis` names the first instruction at each unit. A construction
        # can have several instructions, so its covered unit and owner may
        # name different first rows while sharing an executing instruction.
        chosen, owning = row.get("selected", {}), owner.get("selected", {})
        return (
            chosen.get("source") is not None
            and chosen.get("source") == owning.get("source")
            and bool(identities(chosen) & identities(owning))
        )

    if Counter(u["id"] for u in units) != Counter(r["unit"] for r in dispositions):
        fail("I1", "unit coverage differs")
    actions = {
        "override": {"edit", "covered", "nochange", "refused"},
        "structural": {"omit", "move", "refused"},
        "witnessed": {"edit", "covered", "nochange", "refused"},
        "conflict": {"nochange"},
        "neutral": {"nochange"},
        "silent": {"nochange"},
    }
    owners = {r["unit"]: r for r in dispositions}
    for row in dispositions:
        disposition, action = row.get("disposition"), row.get("action")
        if not disposition:
            fail("I1", "unit without a disposition")
        elif disposition not in actions:
            fail("I1", "unknown disposition")
        elif action not in actions[disposition]:
            fail("I1", "action incompatible with disposition")
        owner_id = row.get("covered_by")
        if action == "covered" and not owner_id:
            fail("I1", "covered unit without its owner")
        if not owner_id:
            continue
        owner = owners.get(owner_id)
        if owner is None:
            fail("I1", "covered unit without its owner")
        elif owner_id == row["unit"] or owner.get("covered_by"):
            fail("I1", "covered unit must name a direct, distinct owner")
        elif (
            action not in {"covered", "refused"}
            or owner.get("action") not in {"edit", "refused"}
            or disposition not in {"override", "witnessed"}
            or owner.get("disposition") != disposition
            or (
                row.get("override") != owner.get("override")
                if disposition == "override"
                else not shared_witness(row, owner)
            )
        ):
            fail("I1", "covered unit and owner have different decisions")
    if set(prepared) != set(original):
        fail("I4", "prepared book inventory differs")
    rows: defaultdict[str, list[Disposition]] = defaultdict(list)
    moves: dict[str, str] = {}
    omissions: set[str] = set()
    # Structural notes, by the verse that carries them.
    placed_notes: defaultdict[str | None, list[Node]] = defaultdict(list)
    note_scopes: defaultdict[str, list[NoteScope]] = defaultdict(list)
    for row in dispositions:
        if row.get("execution") != "applied":
            continue
        held = row.get("note")
        if held:
            placed_notes[row.get("note_ref", row.get("target_ref"))].append(held)
            if row.get("note_scope"):
                note_scopes[signature(held)].append(row["note_scope"])
        if row.get("source_note"):
            placed_notes[row["source_note_ref"]].append(row["source_note"])
        for edit in row.get("edits", []):
            if edit.get("note_scope"):
                note_scopes[signature(edit["note"])].append(edit["note_scope"])
        if row.get("edits"):
            addresses = {e["ref"] for e in row["edits"]}
            for address in addresses:
                rows[address].append(
                    {
                        **row,
                        "edits": [e for e in row["edits"] if e["ref"] == address],
                    }
                )
        else:
            rows[row["ref"]].append(row)
        if row.get("action") == "move":
            moves[row["target_ref"]] = row["ref"]
        elif row.get("action") == "omit":
            omissions.add(row["ref"])
            book, ref = row["ref"].split()
            verse = scripture.verses(original[book])[ref]
            marker = "fqa" if row.get("note_scope") else "fq"
            note = present(held, f"{row['ref']}: an omitted verse without its note")
            quoted = [
                n
                for n in note["content"]
                if isinstance(n, dict) and n.get("marker") == marker
            ]
            if (
                row.get("old") != verse.text
                or len(quoted) != 1
                or usj.text_of(quoted[0]["content"]) != verse.text
            ):
                fail("I3", f"{row['ref']}: omitted quotation differs")
    for book, parsed in prepared.items():
        if book not in original:
            continue  # I4 already reports the unexpected book.
        source = scripture.verses(original[book])
        actual = scripture.verses(parsed)
        expected_refs = {
            structure.rp_ref(book + " " + ref).split()[1]
            for ref in source
            if book + " " + ref not in omissions
        }
        required_moves = {
            target: origin
            for origin, target in structure.moved.items()
            if origin.split()[0] == book and origin.split()[1] in source
        }
        applied_moves = {
            target: origin
            for target, origin in moves.items()
            if origin.split()[0] == book
        }
        if applied_moves != required_moves:
            fail("I4", f"{book}: required relocations not applied")
        if set(actual) != expected_refs:
            fail("I4", f"{book}: verse inventory differs")
        if {book + " " + ref for ref in source} & structure.omitted != omissions & {
            book + " " + ref for ref in source
        }:
            fail("I4", f"{book}: required omissions not applied")
        for ref, verse in actual.items():
            target = book + " " + ref
            origin = moves.get(target, target)
            old_ref = origin.split()[1]
            if old_ref not in source:
                fail("I2", f"{target}: no source verse")
                continue
            edits = [e for row in rows[origin] for e in row.get("edits", [])]
            try:
                expected = closure(source[old_ref].text, edits)
                if expected != verse.text:
                    fail("I2", f"{target}: unaccounted character difference")
            except ValueError as error:
                fail("I2", f"{target}: {error}")
            expected_notes: Content = [n for _, n in source[old_ref].notes]
            expected_notes += [
                e["note"]
                for row in rows[origin]
                for e in row.get("edits", [])
                if e.get("note_owner", True)
            ]
            # A moved verse carries its notes, the OLEB’s own among them,
            # to its new number (edit.renumber).
            if origin != target:
                expected_notes = renumber(expected_notes, ref)
            expected_notes += placed_notes[target]
            if Counter(signature(n) for n in expected_notes) != Counter(
                signature(n) for _, n in verse.notes
            ):
                fail("I3", f"{target}: notes differ")
            for edit in edits:
                scope = edit.get("note_scope")
                marker = "fqa" if scope else "fq"
                quoted = [
                    n
                    for n in edit["note"]["content"]
                    if isinstance(n, dict) and n.get("marker") == marker
                ]
                expected_quote = (
                    usj.text_of(supplied_content(edit["rendered"]))
                    if edit["kind"] == "insert"
                    else edit["old"]
                )
                if scope:
                    if "source_range" in scope:
                        a, b = scope["source_range"]
                        lo, hi = edit["range"]
                        if not 0 <= a <= lo <= hi <= b <= len(source[old_ref].text):
                            fail("I3", f"{target}: stale TR quotation extent")
                        expected_quote = source[old_ref].text[a:b]
                if (
                    len(quoted) != 1
                    or usj.text_of(quoted[0]["content"])
                    + (scope.get("terminal_stop", "") if scope else "")
                    != expected_quote
                ):
                    fail("I3", f"{target}: quotation differs")
            for offset, note in verse.notes:
                # Identify our notes by the checked dispositions, not by what
                # they say of themselves, then re-read their lemma and place.
                fields = [
                    n
                    for n in note["content"]
                    if isinstance(n, dict) and n.get("marker") == "fq"
                ]
                scopes = note_scopes[signature(note)]
                if not scopes:
                    continue
                scope = next(
                    (s for s in scopes if s["ref"] == target and s["offset"] == offset),
                    None,
                )
                if scope is None:
                    fail("I3", f"{target}: TR note is at the wrong place")
                    continue
                if note.get("caller") != "-":
                    fail("I3", f"{target}: TR note leaves a caller")
                if scope["range"] is not None:
                    a, b = scope["range"]
                    expected = scripture.plain(verse.text[a:b]) + ": "
                    if (
                        len(fields) != 1
                        or usj.text_of(fields[0]["content"]) != expected
                    ):
                        fail("I3", f"{target}: TR lemma differs from its span")
                        continue
                    lemma_style = _italic_content(fields[0]["content"])
                    # The final colon belongs to the note, outside its lemma.
                    if lemma_style[:-1] != _verse_italic_span(parsed, verse, a, b):
                        fail("I3", f"{target}: TR lemma italics differ from its span")
                    phrase = usj.text_of(fields[0]["content"]).removesuffix(": ")
                    if (
                        len(
                            lemmas.occurrences(
                                scripture.word_spans(verse.text),
                                scripture.words_of(phrase),
                            )
                        )
                        != 1
                    ):
                        fail("I3", f"{target}: TR lemma is not unique")
                elif fields:
                    fail("I3", f"{target}: verse-level TR note has a lemma")
    return results


# The finished verse: does it read, and does each note restore the KJV?

STOPS = ",;:.?!"


def _note_parts(note: Node) -> tuple[str, str]:
    fields = {
        n.get("marker"): usj.text_of(n.get("content", []))
        for n in note.get("content", [])
        if isinstance(n, dict)
    }
    return fields.get("fq", "").removesuffix(": "), fields.get("fqa", "")


def _restorable(text: str) -> str:
    """Normalize spacing and apostrophe typography, preserving every stop."""
    text = " ".join(text.replace("'", "’").split())
    return re.sub(r"\s+([,;:.!?])", r"\1", text)


def restores(
    finished: str, original: str, notes: Iterable[tuple[int, Node]]
) -> str | None:
    """Whether putting every Textus Receptus note back at its own place gives
    the KJV's words exactly, capitals and stops included: each note's Liskov
    test, all notes at once. `notes` are (offset, note) as the verse holds
    them; a note stands at the end of its lemma. A note of words the TR adds
    puts them after the lemma, one of words it omits takes them out of it,
    and a replacement's alternative replaces its lemma; a note of a verse
    added or a passage moved restores no words. Returns None when the KJV
    comes back, else what comes back instead."""
    text = finished
    for offset, note in sorted(notes, key=lambda n: n[0], reverse=True):
        kind = note.get("x-scope", {}).get("kind")
        if kind not in {"replace", "adds", "omits"}:
            continue
        lemma, alternative = _note_parts(note)
        # The lemma is plain; the verse keeps its line breaks between parts.
        pattern = r"\s+".join(re.escape(word) for word in lemma.split(" "))
        spans = [
            (m.start(), m.end())
            for m in re.finditer(r"(?<![A-Za-z])" + pattern + r"(?![A-Za-z])", text)
            if m.end() <= offset and not text[m.end() : offset].strip(STOPS)
        ]
        if len(spans) != 1:
            return f"lemma does not end at its note: {lemma!r}"
        lo, hi = spans[0]
        if kind == "adds":
            text = text[:hi] + " " + alternative + text[hi:]
        elif kind == "omits":
            found = list(
                re.finditer(
                    r"(?<![A-Za-z])" + re.escape(alternative) + r"(?![A-Za-z])",
                    text[lo:hi],
                )
            )
            if not found:
                return f"omitted words not in the lemma: {alternative!r}"
            k = found[-1]
            text = text[: lo + k.start()] + text[lo + k.end() :]
        else:
            text = text[:lo] + alternative + text[hi:]
    restored = _restorable(text)
    if restored != _restorable(original):
        return f"notes restore {restored[:120]!r}"
    return None


def lint(finished: str, original: str, previous: str = "") -> list[str]:
    """Join problems an edit introduced: each pattern counted in the finished
    verse and the KJV verse; only an increase is reported. The finished verse
    before it, if any, says whether it opens a sentence."""
    patterns = {
        "space before a stop": r"\s[,;:.?!]",
        "two stops together": r"[,;:.?!]\s*[,;:.?!]",
        "lower case after a full stop": r"[.?!]\s+[a-z]",
        "empty supplied word": r"\[\s*\]",
        "doubled word": r"\b(\w+)\s+\1\b",
    }
    found = []
    for name, pattern in patterns.items():
        if len(re.findall(pattern, finished)) > len(re.findall(pattern, original)):
            found.append(name)
    # A KJV verse that opens a sentence still opens one after the edit.
    now, was = (re.search(r"[^\W\d_]", text) for text in (finished, original))
    opening = not previous.strip() or re.search(r"[.?!]\W*$", previous)
    if opening and now and was and now[0].islower() and was[0].isupper():
        found.append("lower case at a sentence opening")
    return found


def finished_verses(
    original_docs: Mapping[str, Document],
    prepared_docs: Mapping[str, Document],
    dispositions: Iterable[Disposition],
    structure: Structure,
) -> dict[str, list[str]]:
    """Every edited verse: its join problems and whether its notes restore the
    KJV. Returns {ref: [problem, ...]} for the verses with problems."""
    edited = {e["ref"] for r in dispositions for e in r.get("edits", [])}
    originals = {book: scripture.verses(doc) for book, doc in original_docs.items()}
    prepared = {book: scripture.verses(doc) for book, doc in prepared_docs.items()}
    preceding = {
        book: dict(zip(list(verses)[1:], verses.values(), strict=False))
        for book, verses in prepared.items()
    }
    result: dict[str, list[str]] = {}
    for ref in sorted(edited):
        book, address = ref.split()
        target_book, target_address = structure.rp_ref(ref).split()
        before = originals[book].get(address)
        after = prepared[target_book].get(target_address)
        if before is None or after is None:
            continue
        previous = preceding[target_book].get(target_address)
        problems = lint(
            scripture.plain(after.text),
            scripture.plain(before.text),
            scripture.plain(previous.text) if previous else "",
        )
        notes = [(at, n) for at, n in after.notes if n.get("category") == "edition"]
        failure = restores(after.text, before.text, notes)
        if failure:
            problems.append(f"note does not restore the KJV ({failure})")
        if problems:
            result[ref] = problems
    return result
