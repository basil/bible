"""Promote a gloss of Brenton's into his text, keeping the former wording in
the note. The King James corrections of shared Greek take their "Or," notes
from the promote stage (bible.byzantine.notes)."""

from __future__ import annotations

from collections.abc import Mapping

from bible import notes, scripture, usj
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
