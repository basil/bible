"""The 1611 translators' New Testament marginal notes: parsing Calvin George's
transcription, applying edition/marginal-notes.json, and setting each note as
a footnote in the Cambridge text."""

from collections import Counter
import functools
import re

from bible import paths, sources
from bible.checks import require
from bible.files import read_json
from bible.usfm import verse_spans, word_tokens

MARGINAL_NOTES = read_json(paths.EDITION_DIR / "marginal-notes.json")
EXPECTED_NT_MARGINAL_NOTES = 775


@functools.cache
def marginal_notes():
    """The 1611 translators' New Testament marginal notes, by book, in source order.

    George's listing gives a reference, the words the note glosses (the lemma), and
    the note. The Old Testament entries belong to the Hebrew Old Testament, which
    this edition does not print, so they are never read.
    """
    text = (paths.ROOT / sources.SOURCES["marginal_notes"]["file"]).read_text(
        encoding="utf-8"
    )
    require(
        text.count("\nMatthew 1:11 ") == 1,
        "Marginal notes New Testament boundary changed",
    )
    books = MARGINAL_NOTES["books"]
    entry_pattern = re.compile(
        "(" + "|".join(map(re.escape, books)) + r") (\d+):(\d+) (.+?): (.+)"
    )
    corrections = dict(MARGINAL_NOTES["corrections"])
    anchors = MARGINAL_NOTES["anchors"]
    result = {}
    seen = Counter()
    for paragraph in re.split(r"\n\s*\n", text[text.index("\nMatthew 1:11 ") :]):
        # The Markdown wraps long entries; a continuation line joins its entry.
        entry = " ".join(paragraph.split())
        if not entry:
            continue
        match = entry_pattern.fullmatch(entry)
        require(match is not None, f"Unparsed marginal note: {entry}")
        book, chapter, verse, lemma, note = match.groups()
        code = books[book]
        key = f"{code} {chapter}:{verse} {lemma}"
        seen[key] += 1
        if seen[key] > 1:
            key += f"#{seen[key]}"
        if key in corrections:
            correction = corrections.pop(key)
            require(
                note.count(correction["from"]) == 1,
                f"Marginal note correction does not apply: {key}",
            )
            note = note.replace(correction["from"], correction["to"])
        require(
            "[" not in note and "]" not in note,
            f"Transcriber's remark left in marginal note: {key}",
        )
        result.setdefault(code, []).append(
            {
                "key": key,
                "chapter": chapter,
                "verse": verse,
                "lemma": lemma,
                "note": note,
            }
        )
    require(not corrections, f"Unused marginal note corrections: {sorted(corrections)}")
    keys = {n["key"] for notes in result.values() for n in notes}
    require(
        set(anchors) <= keys,
        f"Unused marginal note anchors: {sorted(set(anchors) - keys)}",
    )
    require(
        len(keys) == EXPECTED_NT_MARGINAL_NOTES,
        f"Expected {EXPECTED_NT_MARGINAL_NOTES} New Testament marginal notes, found {len(keys)}",
    )
    return result


def marginal_note_usfm(reference, note):
    # Brenton's own style: the label in fqa, the note in ft, a closing full stop.
    label = re.match(r"(Or,|Gr\.) ", note)
    body = f"\\fqa {label[1]} \\ft {note[label.end():]}" if label else f"\\ft {note}"
    if not body.endswith((".", "?", "!")):
        body += "."
    return f"\\f + \\fr {reference} {body}\\f*"


def insert_marginal_notes(code, text, record):
    """Set each marginal note as a footnote whose caller precedes the words it glosses.

    Brenton's callers, like the 1611 marks, stand before the glossed words, and so do
    these. A note is anchored at George's lemma, or at the Cambridge words recorded
    for it in edition/marginal-notes.json where the spelling differs, the lemma occurs
    more than once, or the reference is wrong.
    """
    notes = marginal_notes().get(code, [])
    if not notes:
        return text
    require("\\f " not in text, f"Cambridge text already has footnotes: {code}")
    spans = {reference: (start, end) for reference, start, end in verse_spans(text)}
    inserts = {}
    for note in notes:
        override = MARGINAL_NOTES["anchors"].get(note["key"], {})
        reference = override.get("verse", f"{note['chapter']}:{note['verse']}")
        require(reference in spans, f"Marginal note verse missing: {note['key']}")
        start, end = spans[reference]
        anchor = [w for w, _ in word_tokens(override.get("anchor", note["lemma"]))]
        words = word_tokens(text[start:end])
        hits = [
            offset
            for i, (_, offset) in enumerate(words)
            if [w for w, _ in words[i : i + len(anchor)]] == anchor
        ]
        occurrence = override.get("occurrence")
        require(
            len(hits) == 1 if occurrence is None else 0 < occurrence <= len(hits),
            f"Marginal note anchor not found exactly once: {note['key']} ({len(hits)})",
        )
        position = start + hits[(occurrence or 1) - 1]
        # Keep the note outside a character style that opens on the glossed word.
        while opener := re.search(r"\\\+?(?:add|sc) $", text[start:position]):
            position = start + opener.start()
        preceding = text[start:position]
        require(
            len(re.findall(r"\\\+?(?:add|sc) ", preceding))
            == len(re.findall(r"\\\+?(?:add|sc)\*", preceding)),
            f"Marginal note caller inside a character span: {note['key']}",
        )
        inserts.setdefault(position, []).append(
            marginal_note_usfm(reference, note["note"])
        )
    original = text
    for position in sorted(inserts, reverse=True):
        text = text[:position] + "".join(inserts[position]) + text[position:]
    note_pattern = r"\\f \+ .*?\\f\*"
    require(
        len(re.findall(note_pattern, text)) == len(notes)
        and re.sub(note_pattern, "", text) == original,
        f"Marginal note insertion changed the text: {code}",
    )
    record(
        "insert 1611 translators' marginal notes (Calvin George's transcription)",
        source=sources.SOURCES["marginal_notes"]["file"],
        count=len(notes),
        anchor_overrides=[
            n["key"] for n in notes if n["key"] in MARGINAL_NOTES["anchors"]
        ],
        corrected_notes=[
            n["key"] for n in notes if n["key"] in MARGINAL_NOTES["corrections"]
        ],
    )
    return text
