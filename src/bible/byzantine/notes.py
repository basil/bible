"""Give each Textus Receptus footnote a unique lemma in the finished verse.

Edits keep their offsets and quotations; this stage changes only their notes,
after all wording and verse moves are settled. A note names enough of the
verse to be unambiguous, and its alternative can replace those words without
breaking the sentence, following the convention of the Orthodox Liturgical
English Bible (OLEB). The lemmas of edition/byzantine.json widen a lemma by
hand where the rule chooses badly.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from bible import lemmas, scripture, usj
from bible.byzantine.edit import (
    NOTE_LABELS,
    PASSAGE_NOTES,
    source_content,
    supplied_content,
)
from bible.byzantine.rows import Disposition, Edit, NoteScope
from bible.checks import CheckFailed, present
from bible.lemmas import Span, Words
from bible.scripture import Verse
from bible.usj import Content, Document, Node

if TYPE_CHECKING:
    from bible.terminology import Registry

STOPS = frozenset(",;:.!?—")


def lemma_range(scope: NoteScope) -> list[int]:
    """The offsets of a note's lemma in its verse."""
    return present(scope["range"], f"A Textus Receptus note without a lemma: {scope}")


def with_field(note: Node, marker: str, content: Content) -> Node:
    """The note with new content in its field of the marker."""
    return {
        **note,
        "content": [
            (
                {**n, "content": content}
                if isinstance(n, dict) and n.get("marker") == marker
                else n
            )
            for n in note["content"]
        ],
    }


def readable_span(
    text: str, words: Words, first: int, last: int, readings: Sequence[str] = ()
) -> Span:
    # Prefer the witness's complete phrase when it survives verbatim here.
    found: list[tuple[int, int, int]] = []
    for priority, reading in enumerate(readings):
        tokens = scripture.words_of(usj.text_of(supplied_content(reading)))
        if not tokens:
            continue
        for at in lemmas.occurrences(words, tokens):
            end = at + len(tokens) - 1
            if at <= first <= last <= end:
                found.append((priority, at, end))
    if found:
        _, first, last = min(found, key=lambda s: (s[0], s[2] - s[1]))
    # Articles, possessives and other determiners need the words they govern.
    open_words = (
        lemmas.LINKING_WORDS
        | lemmas.POSSESSIVES
        | {"this", "these", "those", "that", "every", "all", "some", "any", "own"}
    )
    while last + 1 < len(words) and words[last][0] in open_words:
        last += 1
    return lemmas.unique_span(text, words, first, last)


def splices(edits: Sequence[Edit]) -> list[tuple[int, int, int]]:
    """The declared splices and external seams of a verse's edits: the
    source offsets each replaces, and the length of what stands there now."""
    changes: list[tuple[int, int, int]] = []
    for edit in edits:
        lo, hi = edit["applied_range"]
        new = (
            edit.get("prefix", "")
            + usj.text_of(supplied_content(edit["rendered"]))
            + edit.get("suffix", "")
        )
        changes.append((lo, hi, len(new)))
        for seam in edit["seams"]:
            if seam.get("external"):
                start, end = seam["range"]
                changes.append((start, end, len(seam["to"])))
    return changes


def source_range(a: int, b: int, edits: Sequence[Edit]) -> tuple[int, int]:
    """Map finished-verse boundaries through the declared splices and seams.

    A boundary inside a replacement includes its whole source reading.
    No word alignment or guess about the English enters this mapping.
    """
    changes = splices(edits)

    def boundary(at: int, closing: bool) -> int:
        shift = 0
        for lo, hi, length in sorted(set(changes), key=lambda c: (c[0], c[1] > c[0])):
            start, end = lo + shift, lo + shift + length
            if at <= start:
                return at - shift
            if at < end:
                return hi if closing else lo
            shift += length - (hi - lo)
        return at - shift

    return boundary(a, False), boundary(b, True)


def placeable(document: Document, verse: Verse, at: int) -> bool:
    """Whether a note can stand at this offset: never inside a character style."""
    index, local = verse.part_at(at, at_end=True)
    block, lo, hi, _ = verse.parts[index]
    try:
        usj.split(document["content"][block]["content"][lo:hi], local, whole=True)
    except CheckFailed:
        return False
    return True


def lemma_end(document: Document, verse: Verse, end: int) -> int:
    """The end of a lemma, widened to the last word of any italic span it ends
    inside, so that its note can stand right after it (or after the span's
    closing stops)."""
    at = end
    while at < len(verse.text) and not placeable(document, verse, at):
        at += 1
    words = [b for _, _, b in scripture.word_spans(verse.text) if b <= at]
    return max(end, words[-1]) if words else end


def with_lemma(note: Node, phrase: str) -> Node:
    """The note with phrase as its lemma."""
    return {
        **with_field(note, "fq", [phrase + ": "]),
        "x-scope": {**note["x-scope"], "lemma": phrase},
    }


def relemma(note: Node, text: str, a: int, b: int) -> Node:
    return with_lemma(note, scripture.plain(text[a:b]))


def without_notes(content: Content) -> Content:
    return usj.mapped(content, lambda n: None if n["type"] == "note" else n)


def phrase_of(note: Node) -> str | None:
    field = next(
        (n for n in note["content"] if isinstance(n, dict) and n.get("marker") == "fq"),
        None,
    )
    return usj.text_of(field["content"]).removesuffix(": ") if field else None


def adjacent_lemma(text: str, words: Words, offset: int) -> Span:
    """The lemma for words the Textus Receptus adds at `offset`: the words
    just before the gap, grown leftwards until they are unique in the verse;
    or, where a stop stands between them and the gap (the omission began a
    sentence or clause), the words just after it. Never words on both sides,
    so the TR's words go back exactly where the lemma ends or begins."""
    before = [i for i, (_, a, b) in enumerate(words) if b <= offset]
    after = [i for i, (_, a, b) in enumerate(words) if a >= offset]
    stop = bool(before) and any(
        c in ".;:?!" for c in text[words[before[-1]][2] : offset]
    )

    def unique(first: int, last: int) -> bool:
        phrase = scripture.words_of(text[words[first][1] : words[last][2]])
        return len(lemmas.occurrences(words, phrase)) == 1

    sides: list[tuple[str, list[int]]] = (
        [("after", after), ("before", before)]
        if stop or not before
        else [("before", before), ("after", after)]
    )
    for side, indices in sides:
        for k in range(1, min(len(indices), 10) + 1):
            first, last = (
                (indices[-k], indices[-1])
                if side == "before"
                else (indices[0], indices[k - 1])
            )
            if unique(first, last):
                return first, last
    raise ValueError("no unique lemma beside an omission")


def scoped_note(
    verse: Verse,
    offset: int,
    note: Node,
    edit: Edit | None = None,
    omitted: str | None = None,
    readings: Sequence[str] = (),
) -> tuple[Node, NoteScope]:
    text, words = verse.text, scripture.word_spans(verse.text)
    fields = {n["marker"]: n for n in note["content"] if isinstance(n, dict)}
    label = usj.text_of(fields["ft"]["content"])
    quotation = fields.get("fq", {}).get("content", [])
    span: Span | None = None
    glossed: Span | None = None
    if edit and edit["kind"] != "delete":
        rendered = usj.text_of(supplied_content(edit["rendered"]))
        start = offset - len(rendered)
        if text[start:offset] != rendered:
            raise ValueError(f"TR note is not beside its reading: {note['x-key']}")
        touched = [i for i, (_, a, b) in enumerate(words) if a < offset and start < b]
        if not touched:
            raise ValueError(f"TR note reading has no words: {note['x-key']}")
        glossed = touched[0], touched[-1]
        span = readable_span(text, words, *glossed, readings)
        # Carry a changed sentence/clause boundary inside the lemma where the
        # verse continues, rather than leave two stops after substitution.
        old_stop = edit["old"][-1:]
        new_stop = rendered[-1:]
        if (
            span[1] == glossed[1]
            and glossed[1] + 1 < len(words)
            and old_stop != new_stop
            and (old_stop in STOPS or new_stop in STOPS)
        ):
            following = lemmas.clause_after(text, words, glossed[1] + 1, [])
            span = readable_span(text, words, span[0], following[-1])
    elif "fq" in fields and not omitted:
        span = glossed = adjacent_lemma(text, words, offset)
    elif "fq" in fields:
        span, glossed, _ = lemmas.inferred_lemma(
            "f", text, words, offset, None, addition=True
        )
    # A relocation comment applies to the whole verse, rather than a rendering.
    phrase = lemmas.lemma_text(text, words, span) if span else None
    if phrase and len(lemmas.occurrences(words, scripture.words_of(phrase))) != 1:
        raise ValueError(f"TR note lemma is not unique: {note['x-key']}")
    content: Content = [fields["fr"]]
    if phrase:
        content.append(usj.char("fq", phrase + ": "))
    content.append(usj.char("ft", label))
    if "fq" in fields:
        content.append(usj.char("fqa", *quotation))
    extra: usj.Extra = {
        "x-key": note["x-key"],
        "x-scope": {
            **note["x-scope"],
            "lemma": phrase,
            "glossed": (lemmas.lemma_text(text, words, glossed) if glossed else None),
        },
        "category": "edition",
    }
    finished = usj.note("f", *content, **extra)
    return finished, {
        "range": ([words[span[0]][1], words[span[1]][2]] if span else None),
        "offset": offset,
    }


def apply(
    original: Mapping[str, Document],
    documents: Mapping[str, Document],
    dispositions: Sequence[Disposition],
    decisions: Sequence[Mapping[str, Any]] = (),
) -> tuple[dict[str, Document], list[Disposition]]:
    """Finish every OLEB note. decisions: the lemmas of edition/byzantine.json,
    as rows keyed by unit id and 1-based edit index. A decision whose edit does
    not exist is stale and refused."""
    declared = {f"{d['id']} TR#{d['edit']}": d for d in decisions}
    if len(declared) != len(decisions):
        raise ValueError("Duplicate TR note lemma decision")
    used: set[str] = set()
    source_verses = {book: scripture.verses(doc) for book, doc in original.items()}
    by_ref: dict[str, list[Edit]] = {}
    for row in dispositions:
        for edit in row.get("edits", []):
            by_ref.setdefault(edit["ref"], []).append(edit)
    document_verses = {book: scripture.verses(doc) for book, doc in documents.items()}
    locations: dict[str, tuple[str, str, Verse, int, Node]] = {}
    for book, verses in document_verses.items():
        for ref, verse in verses.items():
            for offset, note in verse.notes:
                key = note.get("x-key")
                if note.get("category") == "edition" and key:
                    if key in locations:
                        raise ValueError(f"Duplicate TR note key: {key}")
                    locations[key] = book, ref, verse, offset, note
    changed: dict[str, Node | None] = {}
    rows: list[Disposition] = []
    # The corrections of shared Greek have no notes to finish.
    corrections = [r for r in dispositions if r.get("disposition") == "shared"]

    def full_form(
        book: str,
        verse: Verse,
        offset: int,
        finished: Node,
        scope: NoteScope,
        edit: Edit,
        declared_lemma: bool = False,
    ) -> tuple[Node, NoteScope]:
        """Keep "adds: X" or "omits: X" only where it gives back the KJV's
        words exactly, case and stops included, in the lemma and the word on
        either side of it: X has no stop, and an addition's lemma stands just
        before the gap. Otherwise the note quotes the KJV's own words for a
        lemma that spans the change: across the gap of an omission, and on to
        the next word after an addition (whose capital may change)."""
        source_book, source_ref = edit["ref"].split()
        source = source_verses[source_book][source_ref]
        words = scripture.word_spans(verse.text)
        part = verse.part_at(offset, at_end=True)[0]
        same = [w for w in words if verse.part_at(w[1])[0] == part]

        def kjv(a: int, b: int) -> str:
            lo, hi = source_range(a, b, by_ref[edit["ref"]])
            lo, hi = min(lo, edit["range"][0]), max(hi, edit["range"][1])
            return scripture.plain(source.text[lo:hi])

        a, b = lemma_range(scope)
        ca = max([w[1] for w in same if w[2] <= a] or [a])
        cb = min([w[2] for w in same if w[1] >= b] or [b])
        text = verse.text
        restored: str | None
        if edit["kind"] == "delete":
            reading = scripture.plain(edit["old"])
            restored = (
                scripture.plain(text[ca:b] + " " + reading + text[b:cb])
                if b <= offset
                else None
            )
        else:
            reading = scripture.plain(usj.text_of(supplied_content(edit["rendered"])))
            at = text.rfind(reading, a, b)
            restored = (
                scripture.plain(text[ca:at] + " " + text[at + len(reading) : cb])
                if at >= 0
                else None
            )
        if (
            restored is not None
            and re.sub(r"\s+([,;:.!?])", r"\1", restored) == kjv(ca, cb)
            and not any(c in STOPS for c in reading)
        ):
            return finished, scope
        if edit["kind"] == "delete":
            if b <= offset:
                b = min([w[2] for w in same if w[1] >= offset] or [b])
            # A declared phrase after an unchanged stop can quote the omitted
            # opening word without carrying the preceding phrase into its lemma.
            clause_start = text[:a].rstrip().endswith((".", ";", ":", "!", "?", ","))
            if a >= offset and not (declared_lemma and clause_start):
                a = max([w[1] for w in same if w[2] <= offset] or [a])
        elif b == offset:
            b = cb
        b = lemma_end(documents[book], verse, b)
        finished = relemma(finished, text, a, b)
        finished = {
            **with_field(finished, "ft", [NOTE_LABELS["replace"]]),
            "x-scope": {**finished["x-scope"], "kind": "replace"},
        }
        return finished, {**scope, "range": [a, b], "full": True}

    def finish(
        note: Node,
        edit: Edit | None = None,
        omitted: str | None = None,
        readings: Sequence[str] = (),
    ) -> tuple[Node, NoteScope]:
        book, ref, verse, offset, actual = locations[note["x-key"]]
        finished, scope = scoped_note(verse, offset, actual, edit, omitted, readings)
        if note["x-key"] in declared:
            decision = declared[note["x-key"]]
            if not decision.get("why", "").strip():
                raise ValueError(f"TR note lemma lacks a reason: {note['x-key']}")
            words = scripture.word_spans(verse.text)
            span = lemmas.phrase_span(words, decision["lemma"], note["x-key"])
            a, b = words[span[0]][1], words[span[1]][2]
            start = (
                offset - len(usj.text_of(supplied_content(edit["rendered"])))
                if edit
                else offset
            )
            if not edit or not a <= start <= offset <= b:
                raise ValueError(
                    f"TR note lemma does not contain its reading: {note['x-key']}"
                )
            phrase = lemmas.lemma_text(verse.text, words, span)
            if phrase == finished["x-scope"]["lemma"]:
                raise ValueError(
                    f"TR note lemma decision changes nothing: {note['x-key']}"
                )
            finished = with_lemma(finished, phrase)
            scope["range"] = [a, b]
            used.add(note["x-key"])
        if scope["range"]:
            end = lemma_end(documents[book], verse, scope["range"][1])
            if end != scope["range"][1]:
                scope["range"] = [scope["range"][0], end]
                finished = relemma(finished, verse.text, scope["range"][0], end)
        if edit and edit["kind"] in {"insert", "delete"} and scope["range"]:
            finished, scope = full_form(
                book,
                verse,
                offset,
                finished,
                scope,
                edit,
                declared_lemma=note["x-key"] in declared,
            )
        if edit and (edit["kind"] not in {"insert", "delete"} or scope.get("full")):
            source_book, source_ref = edit["ref"].split()
            source = source_verses[source_book][source_ref]
            lemma = lemma_range(scope)
            a, b = source_range(lemma[0], lemma[1], by_ref[edit["ref"]])
            # The alternative includes the entire edit, even when an
            # omission's lemma ends immediately before its source fragment.
            # Compare its outer boundary, not a stop inside that fragment.
            b = max(b, edit["range"][1])
            # An edit whose KJV words end with a stop keeps that stop inside
            # the alternative's substitution.
            end = lemma[1]
            old_stop, new_stop = source.text[b : b + 1], verse.text[end : end + 1]
            if b == edit["range"][1] and edit["old"][-1:] in STOPS:
                old_stop = edit["old"][-1]
            after = [
                i
                for i, (_, start, _) in enumerate(scripture.word_spans(verse.text))
                if start > end
            ]
            if old_stop != new_stop and (old_stop in STOPS or new_stop in STOPS):
                if after:
                    words = scripture.word_spans(verse.text)
                    last = lemmas.clause_after(verse.text, words, after[0], [])[-1]
                    end = lemma_end(documents[book], verse, words[last][2])
                elif new_stop and new_stop in STOPS:
                    # At a verse end there is no following clause to absorb
                    # a changed stop. Include it in the lemma itself.
                    end += 1
                finished = relemma(finished, verse.text, lemma[0], end)
                lemma[1] = end
                a, b = source_range(lemma[0], lemma[1], by_ref[edit["ref"]])
            # Keep punctuation included in the witnessed source fragment even
            # when the displayed lemma ends at its final word.
            a, b = min(a, edit["range"][0]), max(b, edit["range"][1])
            quote = source_content(original[source_book], source, a, b)
            quote = without_notes(quote)
            finished = with_field(finished, "fqa", quote)
            scope["source_range"] = [a, b]
        changed[note["x-key"]] = finished
        return finished, {**scope, "ref": book + " " + ref}

    for row in dispositions:
        if row.get("disposition") == "shared":
            continue
        updated = row.copy()
        if row.get("edits"):
            updated["edits"] = []
            # A published phrase that survives verbatim can supply lemma
            # context (an instruction's quotation). It
            # cannot change the wording.
            readings = [r for r in row.get("readings", []) if r]
            for edit in row["edits"]:
                note, scope = finish(edit["note"], edit, readings=readings)
                updated["edits"].append({**edit, "note": note, "note_scope": scope})
        held = row.get("note")
        if held:
            note, scope = finish(
                held,
                omitted=(row["ref"] if row.get("action") == "omit" else None),
            )
            updated["note"] = note
            updated["note_scope"] = scope
        rows.append(updated)
    if set(declared) != used:
        raise ValueError(
            f"Stale TR note lemma decisions: {sorted(set(declared) - used)}"
        )
    # One construction can take several splices (a moved pronoun, for example).
    # Explicit, disjoint lemmas can separate independent replacements;
    # words moved between edits still restore together.
    # Notes whose context overlaps must not repeat each other's readings.
    by_verse: dict[tuple[str, int], list[tuple[int, Edit, int, int]]] = {}
    moving_owners: set[int] = set()
    for owner, row in enumerate(rows):
        deltas: list[tuple[Counter[str], Counter[str]]] = []
        for edit in row.get("edits", []):
            old = Counter(scripture.words_of(edit["old"].lower()))
            new = Counter(scripture.words_of(edit["new"].lower()))
            deltas.append((old - new, new - old))
        if any(
            removed & added
            for i, (removed, _) in enumerate(deltas)
            for j, (_, added) in enumerate(deltas)
            if i != j
        ):
            moving_owners.add(owner)
        for edit in row.get("edits", []):
            scope = edit["note_scope"]
            lemma = lemma_range(scope)
            a, b = source_range(lemma[0], lemma[1], by_ref[edit["ref"]])
            lo, hi = edit["range"]
            # One note per construction, but never across a paragraph or a
            # poetry line: a note's quotation must stand in one part.
            source_book, source_ref = edit["ref"].split()
            part = source_verses[source_book][source_ref].part_at(lo)[0]
            by_verse.setdefault((scope["ref"], part), []).append(
                (owner, edit, min(a, lo), max(b, hi))
            )
    for (address, _), entries in by_verse.items():
        groups: list[list[tuple[int, Edit, int, int]]] = []
        for entry in entries:
            merged = [entry]
            while True:
                lo, hi = min(e[2] for e in merged), max(e[3] for e in merged)
                touching = [
                    g
                    for g in groups
                    if (
                        {e[0] for e in merged} & {e[0] for e in g}
                        and not (
                            any(e[1]["note"]["x-key"] in declared for e in merged + g)
                            and all(e[1]["kind"] == "replace" for e in merged + g)
                            and not any(e[0] in moving_owners for e in merged + g)
                        )
                    )
                    or lo < max(e[3] for e in g)
                    and min(e[2] for e in g) < hi
                ]
                if not touching:
                    break
                for group in touching:
                    groups.remove(group)
                    merged.extend(group)
            groups.append(merged)
        for group in groups:
            if len(group) == 1:
                continue
            book, ref = address.split()
            verse = document_verses[book][ref]
            a = min(lemma_range(e[1]["note_scope"])[0] for e in group)
            b = max(lemma_range(e[1]["note_scope"])[1] for e in group)
            source_book, source_ref = group[0][1]["ref"].split()
            lo, hi = min(e[2] for e in group), max(e[3] for e in group)
            source = source_verses[source_book][source_ref]
            quote = source_content(original[source_book], source, lo, hi)
            quote = without_notes(quote)
            primary = min(group, key=lambda e: e[1]["note_scope"]["offset"])[1]
            key, offset = primary["note"]["x-key"], primary["note_scope"]["offset"]
            phrase = scripture.plain(verse.text[a:b])
            scope = {
                "ref": address,
                "range": [a, b],
                "source_range": [lo, hi],
                "offset": offset,
                "combined": True,
            }
            extra: usj.Extra = {
                "x-key": key,
                "x-scope": {"kind": "replace", "lemma": phrase, "glossed": phrase},
                "category": "edition",
            }
            note = usj.note(
                "f",
                usj.char("fr", ref + " "),
                usj.char("fq", phrase + ": "),
                usj.char("ft", NOTE_LABELS["replace"]),
                usj.char("fqa", *quote),
                **extra,
            )
            for _, edit, _, _ in group:
                old_key = edit["note"]["x-key"]
                changed[old_key] = note if old_key == key else None
                edit["note"] = note
                edit["note_scope"] = scope
                edit["note_owner"] = old_key == key

    # Omit a shared boundary stop from both the lemma and its alternative.
    # Keep a changed stop: it is part of the reading, especially across verses.
    def stopped(note: Node, scope: NoteScope, kind: str | None, omit: bool) -> Node:
        body = next(
            (
                n
                for n in note["content"]
                if isinstance(n, dict) and n.get("marker") == "fqa"
            ),
            None,
        )
        quote = usj.text_of(body["content"]) if body else ""
        book, ref = scope["ref"].split()
        verse = document_verses[book][ref]
        following = verse.text[scope["range"][1] :] if scope["range"] else ""
        # A short form's words carry no stop; a full form's final stop is
        # dropped where the same stop is printed after its lemma, so that
        # putting the alternative back restores that one stop. An omitted
        # verse's quotation keeps its stop.
        short = kind in {"delete", "insert"} and not scope.get("full")
        if (
            body
            and not omit
            and quote[-1:] in ",;:.!?"
            and quote
            and not quote.endswith("..")
            and (bool(following) and following[:1] == quote[-1:] or short)
            and quote[:-1].rstrip() != phrase_of(note)
        ):
            scope["terminal_stop"] = quote[-1]
            note = with_field(
                note,
                "fqa",
                usj.substituted(body["content"], [(len(quote) - 1, len(quote), "")]),
            )
            changed[note["x-key"]] = note
        return note

    for row in rows:
        for edit in row.get("edits", []):
            if edit.get("note_owner", True):
                edit["note"] = stopped(
                    edit["note"], edit["note_scope"], edit.get("kind"), False
                )
        held = row.get("note")
        if held:
            row["note"] = stopped(
                held, row["note_scope"], row.get("kind"), row.get("action") == "omit"
            )
    # All participants retain the same finished note for the independent check.
    for row in rows:
        for edit in row.get("edits", []):
            edit["note"] = present(
                changed[edit["note"]["x-key"]], f"A note lost: {edit['note']}"
            )

    def finished(note: Node) -> Node | None:
        key = note.get("x-key")
        return note if key is None else changed.get(key, note)

    prepared = {
        book: scripture.map_notes(document, finished)
        for book, document in documents.items()
    }
    # A TR note whose quotation took in a correction of shared Greek would
    # give the correction to the TR. A refused correction has no edits; the
    # build names it once the stages are done.
    corrected: dict[str, list[tuple[str, int, int]]] = {}
    for correction in corrections:
        for change in correction.get("edits", []):
            lo, hi = change["range"]
            corrected.setdefault(change["ref"], []).append((correction["unit"], lo, hi))
    for row in rows:
        for edit in row.get("edits", []):
            a, b = edit["note_scope"].get("source_range", edit["range"])
            for unit, lo, hi in corrected.get(edit["ref"], []):
                if a < hi and lo < b:
                    raise ValueError(
                        f"Byzantine reading {unit} is quoted by TR note {edit['note']['x-key']}"
                    )
    return placed(prepared, rows), [*rows, *corrections]


def placed(
    prepared: dict[str, Document], rows: Sequence[Disposition]
) -> dict[str, Document]:
    """Each note stands at the end of its lemma, and its lemma keeps the
    verse's italics, so that a note on supplied words alone shows what
    differs. Moving a note changes no offset in the verse's words."""
    owners: dict[str, tuple[Node, NoteScope]] = {}
    for row in rows:
        for edit in row.get("edits", []):
            if edit.get("note_owner", True):
                owners[edit["note"]["x-key"]] = edit["note"], edit["note_scope"]
        held = row.get("note")
        if held and row.get("note_scope"):
            owners[held["x-key"]] = held, row["note_scope"]
    finished: dict[str, Node] = {}
    by_book: dict[str, list[tuple[Node, NoteScope]]] = {}
    for key, item in owners.items():
        scope = item[1]
        if scope.get("range"):
            by_book.setdefault(scope["ref"].split()[0], []).append(item)
    for book, items in by_book.items():
        verses = scripture.verses(prepared[book])
        moved: list[tuple[str, int, Node]] = []
        for owned, scope in items:
            ref = scope["ref"].split()[1]
            a, b = lemma_range(scope)
            lemma = without_notes(source_content(prepared[book], verses[ref], a, b))
            note = with_field(owned, "fq", usj.joined(lemma, [": "]))
            scope["offset"] = b
            finished[note["x-key"]] = note
            moved.append((ref, b, note))
        document = scripture.map_notes(
            prepared[book], lambda n: None if n.get("x-key") in finished else n
        )
        verses = scripture.verses(document)
        changes: list[tuple[Verse, int, int, Content]] = []
        for ref, at, note in moved:
            verse = verses[ref]
            # A lemma ending inside an italic span ("thing;") puts its note
            # after the span's closing stops.
            while not placeable(document, verse, at):
                if verse.text[at : at + 1] not in STOPS:
                    raise ValueError(
                        f"{ref} {at} {verse.text[max(0,at-30):at]!r}|{verse.text[at:at+30]!r} {note['x-key']}"
                    )
                at += 1
            changes.append((verse, at, at, [note]))
            owners[note["x-key"]][1]["offset"] = at
        prepared[book] = scripture.edited(document, changes)
    # Every participant of a combined note holds the same finished note.
    for row in rows:
        for edit in row.get("edits", []):
            edit["note"] = finished.get(edit["note"]["x-key"], edit["note"])
        held = row.get("note")
        if held:
            row["note"] = finished.get(held["x-key"], held)
    return prepared


# The notes as the edition prints them.


def for_edition(document: Document, terms: Registry) -> Document:
    """The finished notes in the edition's form: the witness's label, the
    words that stand in the note for a replaced reading as an alternative and
    for words added or omitted as a quotation (none where the whole lemma is
    omitted, since it stands before the label), the lemma declared for the
    annotate stage to set, and the note at the start of its lemma, as every
    edition note stands. A verse-level note stands at its verse's start.

    The reconciliation names its notes "unit TR#n"; the edition's key is
    "unit TR" for a unit's one note, and "unit TR#n" for a second."""
    verses = scripture.verses(document)
    moved: list[tuple[str, int, int, Node]] = []
    for ref, verse in verses.items():
        words = scripture.word_spans(verse.text)
        for offset, note in verse.notes:
            if note.get("category") != "edition":
                continue
            fields = {n["marker"]: n for n in note["content"] if isinstance(n, dict)}
            lemma = phrase_of(note)
            scope = note["x-scope"]
            kind, where = scope["kind"], scope.get("where")
            content: Content = [
                fields["fr"],
                usj.char("fl", terms.display("textus-receptus") + " "),
            ]
            quotation = usj.text_of(fields.get("fqa", {}).get("content", []))
            adds, omits = terms.display("addition"), terms.display("omission")
            if kind == "replace":
                # A replaced reading: the note's words stand for the lemma.
                content.append(usj.char("fqa", quotation))
            elif kind == "omits" and quotation == lemma:
                # The whole lemma omitted: the words stand once, before the
                # label, as Brenton's "Vat. omits" leaves them.
                content.append(usj.char("ft", omits))
            elif kind in {"adds", "omits", "adds-verse"}:
                # Words added, or some of the lemma omitted: quoted, after
                # what was done.
                done = {
                    "adds": adds,
                    "omits": omits,
                    "adds-verse": f"{adds} verse {where}",
                }[kind]
                content.append(usj.char("ft", done + " "))
                content.append(usj.char("fq", quotation))
            else:
                content.append(usj.char("ft", PASSAGE_NOTES[kind].format(where=where)))
            key = note["x-key"].removesuffix("#1")
            if lemma is None:
                at = 0
            else:
                hits = lemmas.occurrences(words, scripture.words_of(lemma))
                if len(hits) != 1:
                    raise ValueError(f"TR note lemma is not unique: {key}")
                at = words[hits[0]][1]
            extra: usj.Extra = {
                "x-key": key,
                "x-scope": {"declared": lemma},
                "category": "edition",
            }
            moved.append(
                (
                    ref,
                    at,
                    offset,
                    usj.note("f", *content, caller="+", **extra),
                )
            )
    document = scripture.map_notes(
        document, lambda n: None if n.get("category") == "edition" else n
    )
    verses = scripture.verses(document)
    return scripture.edited(
        document,
        [
            (verses[ref], at, at, [note])
            for ref, at, _, note in sorted(moved, key=lambda m: (m[0], m[1], m[2]))
        ],
    )
