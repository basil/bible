"""Preserve a translation's former wording when its rendering is corrected."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

from bible import notes, scripture, usj
from bible.byzantine.edit import source_content
from bible.byzantine.notes import (
    lemma_end,
    readable_span,
    source_range,
    splices,
    without_notes,
)
from bible.byzantine.rows import Disposition, Edit
from bible.byzantine.verify import closure
from bible.checks import require
from bible.policy_schema import Rendering
from bible.usj import Document, Node


def alternative(ref: str, key: str, lemma: str, content: usj.Content) -> Node:
    return usj.note(
        "f",
        usj.char("fr", ref + " "),
        usj.char("ft", "Or, "),
        usj.char("fqa", usj.text_of(content)),
        **usj.Extra(
            {"x-key": key, "category": "edition", "x-scope": {"declared": lemma}}
        ),
    )


def brenton(code: str, doc: Document, decisions: Mapping[str, Rendering]) -> Document:
    """Promote a pinned alternative, retaining the source key for its reversal."""
    for key, decision in decisions.items():
        book, address = key.split()
        if book != code:
            continue
        # A note's key is its verse, numbered after the verse's first note.
        ref = address.partition("#")[0]
        verses = scripture.verses(doc)
        require(ref in verses, f"Rendering verse missing: {key}")
        verse = verses[ref]
        old, new, lemma = decision["from"], decision["to"], decision["lemma"]
        require(old != new and verse.text.count(old) == 1, f"Stale rendering: {key}")
        found = [n for _, n in verse.notes if n.get("x-key") == key]
        require(len(found) == 1, f"Rendering source note missing: {key}")
        require(
            notes.source_text(found[0]) == decision["source_note"],
            f"Stale rendering source note: {key}",
        )
        # The former words are those the lemma's words replace.
        before, _, after = new.partition(lemma)
        former = old[len(before) : len(old) - len(after)]
        require(
            lemma in new and before + former + after == old and bool(former.strip()),
            f"Rendering lemma outside its words: {key}",
        )
        at = verse.text.index(old)
        among = [n for offset, n in verse.notes if at <= offset <= at + len(old)]
        require(
            len(among) == 1 and among[0] is found[0],
            f"Rendering source note outside its words, or another note among them: {key}",
        )
        # Remove the source note before rewriting the words it stands among.
        doc = scripture.map_notes(doc, lambda n: None if n.get("x-key") == key else n)
        doc = scripture.rewritten(
            doc, [(scripture.verses(doc)[ref], at, at + len(old), new)]
        )
        verse = scripture.verses(doc)[ref]
        require(verse.text.count(lemma) == 1, f"Rendering lemma not unique: {key}")
        start = verse.text.index(lemma)
        doc = scripture.edited(
            doc, [(verse, start, start, [alternative(ref, key, lemma, [former])])]
        )
    return doc


def kjv(
    code: str,
    doc: Document,
    original: Document,
    rows: Sequence[Disposition],
    reversed_margins: Mapping[str, Mapping[str, object]],
) -> Document:
    """Quote executed source ranges, widening both sides of each comparison.

    Independent edits keep separate notes. Moved words and overlapping
    contextual lemmas restore together. Existing reversed margins count as
    coverage only when their complete comparison restores the pinned text.
    """
    by_ref: dict[str, list[Edit]] = {}
    # Each correction with its unit and its place among the unit's edits.
    corrections: dict[str, list[tuple[str, int, Edit]]] = {}
    for row in rows:
        for number, edit in enumerate(row.get("edits", ()), 1):
            book, ref = edit["ref"].split()
            if book != code:
                continue
            by_ref.setdefault(ref, []).append(edit)
            if row.get("disposition") == "shared":
                corrections.setdefault(ref, []).append((row["unit"], number, edit))
    originals = scripture.verses(original)
    finished = scripture.verses(doc)
    changes: list[tuple[scripture.Verse, int, int, usj.Content]] = []
    for ref, entries in corrections.items():
        require(
            ref in finished and ref in originals,
            f"Rendering verse missing: {code} {ref}",
        )
        verse = finished[ref]
        source = originals[ref]
        edits = by_ref[ref]
        words = scripture.word_spans(verse.text)
        cuts = sorted(set(splices(edits)))
        variants = [e for e in edits if all(e is not c for *_, c in entries)]

        def current(at: int, closing: bool = False) -> int:
            shift = 0
            for lo, hi, length in cuts:
                # A closing boundary takes in words inserted at it, never a
                # replacement that begins there.
                if at < lo or at == lo and (not closing or hi > lo):
                    break
                if at < hi:
                    return lo + shift + (length if closing else 0)
                shift += length - (hi - lo)
            return at + shift

        restorations: list[tuple[int, int, str]] = []
        covered: set[int] = set()
        for key, margin in reversed_margins.items():
            if not key.startswith(f"{code} {ref} ") or "former" not in margin:
                continue
            former, anchor = str(margin["former"]), str(margin["anchor"])
            require(
                source.text.count(former) == 1 and verse.text.count(anchor) == 1,
                f"Stale reversed rendering margin: {key}",
            )
            lo = source.text.index(former)
            hi = lo + len(former)
            a = verse.text.index(anchor)
            b = a + len(anchor)
            owned = {
                i
                for i, (*_, edit) in enumerate(entries)
                if edit["range"][0] < hi and lo < edit["range"][1]
            }
            require(
                bool(owned) and not covered & owned,
                f"Reversed margin has no unique correction: {key}",
            )
            left = min([lo, *[entries[i][2]["applied_range"][0] for i in owned]])
            right = max([hi, *[entries[i][2]["applied_range"][1] for i in owned]])
            start, end = current(left), current(right, True)
            restored = verse.text[start:a] + former + verse.text[b:end]
            require(
                start <= a <= b <= end
                and scripture.plain(restored)
                == scripture.plain(source.text[left:right]),
                f"Reversed margin does not restore its correction: {key}",
            )
            covered.update(owned)
            restorations.append((a, b, former))

        groups: list[tuple[set[int], int, int]] = []
        for i, (*_, edit) in enumerate(entries):
            if i in covered:
                continue
            lo, hi = edit["applied_range"]
            a, b = current(lo), current(hi, True)
            selected = [j for j, (_, x, y) in enumerate(words) if x < b and a < y]
            if not selected:
                selected = [j for j, (_, x, _) in enumerate(words) if x >= a][:1]
                previous = [j for j, (_, _, y) in enumerate(words) if y <= a][-1:]
                selected = previous + selected
            require(bool(selected), f"Rendering has no contextual words: {edit['ref']}")
            if edit["kind"] == "insert":
                if max(selected) + 1 < len(words):
                    selected.append(max(selected) + 1)
                elif min(selected) > 0:
                    selected.append(min(selected) - 1)
            first, last = readable_span(verse.text, words, min(selected), max(selected))
            groups.append(({i}, words[first][1], lemma_end(doc, verse, words[last][2])))
        # Words removed by one edit and added by another belong to one reading.
        moving: set[tuple[int, int]] = set()
        for i, (unit, _, edit) in enumerate(entries):
            removed = Counter(scripture.words_of(edit["old"].lower())) - Counter(
                scripture.words_of(edit["new"].lower())
            )
            for j, (other, _, change) in enumerate(entries):
                added = Counter(scripture.words_of(change["new"].lower())) - Counter(
                    scripture.words_of(change["old"].lower())
                )
                if i != j and unit == other and removed & added:
                    moving.add((i, j))
        merged = True
        while merged:
            merged = False
            for i, (owners, a, b) in enumerate(groups):
                for j in range(i + 1, len(groups)):
                    others, c, d = groups[j]
                    if (
                        a < d
                        and c < b
                        or any(
                            x in owners and y in others or y in owners and x in others
                            for x, y in moving
                        )
                    ):
                        groups[i] = (owners | others, min(a, c), max(b, d))
                        groups.pop(j)
                        merged = True
                        break
                if merged:
                    break
        for owners, a, b in groups:
            lo, hi = source_range(a, b, edits)
            require(
                all(
                    lo <= entries[i][2]["range"][0] and entries[i][2]["range"][1] <= hi
                    for i in owners
                ),
                f"Rendering loses its source words: {code} {ref}",
            )
            require(
                not any(lo < e["range"][1] and e["range"][0] < hi for e in variants),
                f"Rendering quotes a TR change: {code} {ref}",
            )
            # A boundary stop printed beside the lemma belongs to neither
            # reading. Keep changed stops; restoration below checks them.
            if (
                hi > lo
                and source.text[hi - 1] in ",;:.!?"
                and verse.text[b : b + 1] == source.text[hi - 1]
            ):
                hi -= 1
            lemma = scripture.plain(verse.text[a:b])
            quote = without_notes(source_content(original, source, lo, hi))
            require(
                scripture.plain(usj.text_of(quote))
                == scripture.plain(source.text[lo:hi])
                and scripture.plain(source.text[lo:hi]) != lemma,
                f"Ineffective rendering note: {code} {ref}",
            )
            require(
                verse.part_at(a)[0] == verse.part_at(b, at_end=True)[0],
                f"Rendering crosses a paragraph: {code} {ref}",
            )
            unit, number, _ = entries[min(owners)]
            key = f"{unit} rendering#{number}"
            changes.append((verse, a, a, [alternative(ref, key, lemma, quote)]))
            restorations.append((a, b, usj.text_of(quote)))
        restored = verse.text
        end = len(restored)
        for a, b, former in sorted(restorations, reverse=True):
            require(b <= end, f"Overlapping rendering notes: {code} {ref}")
            restored = restored[:a] + former + restored[b:]
            end = a
        expected = closure(source.text, variants)
        require(
            scripture.plain(restored) == scripture.plain(expected),
            f"Rendering notes do not restore the King James wording: {code} {ref}: "
            f"{restored!r} != {expected!r}",
        )
    return scripture.edited(doc, changes)
