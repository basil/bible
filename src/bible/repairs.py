"""Corrections to the sources' transcription, made before anything reads them.

eBible's text of Brenton and Calvin George's transcription of the 1611 margin
have slips: a missing word space, a doubled label, a transcriber's remark, a
dropped note. A note of Brenton's 1844 printing that the later Bagster
printings, and so eBible, dropped or shortened is restored the same way.
edition/brenton-notes.json and edition/kjv-notes.json mend them, each with its
reason. A correction is made to the source's own text, where it must be found
once, and must fit one of the kinds of slip below unless it is marked
uncategorized, so that no correction can rewrite the translation unnoticed.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

from bible.checks import require
from bible.policy_schema import Correction
from bible.references import book_of
from bible.usfm import GREEK, canonical_text, verse_spans, words_of

# A bracketed remark of the transcriber's or eBible's, with a space beside it.
REMARK = re.compile(r" ?\[[^\]]*\] ?")
EMPTY_NOTE = re.compile(r"\\f \+ \\fr \S+ \\f\*")
# Any caller: the preface's notes use "*" as well as "+".
NOTE = re.compile(r"\\(f|x) \S \\(?:fr|xo) (\S+) ?(.*?)\\\1\*")
# Any paragraph but a heading (\is1, \is2) or a blank line (\ib).
APPENDIX_PARAGRAPH = re.compile(r"^\\(?!i[sb]\d*\b)\w+ [^\n]*", re.M)


def change(before: str, after: str) -> tuple[int, str, str]:
    """Where after departs from before: the offset, the stretch of before it
    replaces, and what replaces it."""
    start = 0
    while start < min(len(before), len(after)) and before[start] == after[start]:
        start += 1
    end = 0
    while (
        end < min(len(before), len(after)) - start
        and before[-1 - end] == after[-1 - end]
    ):
        end += 1
    return start, before[start : len(before) - end], after[start : len(after) - end]


def punctuation(text: str) -> bool:
    return len(text) == 1 and unicodedata.category(text).startswith("P")


def letter_slip(old: str, new: str) -> str | None:
    """The kind of slip that replaces old with new, if it is one letter's."""
    if not old and len(new) == 1 and new.isalpha():
        return "missing letter"
    if not new and len(old) == 1 and old.isalpha():
        return "stray letter"
    if len(old) == len(new) == 1 and old.isalpha() and new.isalpha():
        return "wrong letter"
    return None


def inserted_note(before: str, at: int, new: str) -> bool:
    """Whether new, inserted in before at an offset, is one whole note.

    change() takes the insertion as late as it can, so a note set before a
    marker or another note shares the start of what follows it: its backslash,
    or its own opening. The insertion may stand as far back as new ends with
    what stands before it; each such place is tried.
    """
    shift = 0
    while True:
        moved = before[at - shift : at] + new[: len(new) - shift]
        # One note and nothing else: a lazy fullmatch would take two notes
        # with words between them for one.
        if (note := NOTE.match(moved)) and note.end() == len(moved):
            return True
        shift += 1
        if shift > min(at, len(new)) or before[at - shift] != new[-shift]:
            return False


def category(before: str, after: str) -> str | None:
    """The kind of slip a correction mends, or None if it is none of them."""
    at, old, new = change(before, after)
    if not old and new == " ":
        return "missing word space"
    if not old and punctuation(new):
        return "missing punctuation"
    if not new and punctuation(old):
        return "stray punctuation"
    if punctuation(old) and punctuation(new):
        return "wrong punctuation"
    if kind := letter_slip(old, new):
        return kind
    if old and not new:
        beside = (
            before[max(0, at - len(old)) : at],
            before[at + len(old) :][: len(old)],
        )
        if old in beside:
            return "doubled text"
        if REMARK.fullmatch(old):
            return "remark"
        if EMPTY_NOTE.fullmatch(old):
            return "empty note"
    if not old and inserted_note(before, at, new):
        return "missing note"
    if old == "[Greek characters]" and re.fullmatch(rf"[{GREEK}\s,.;]+", new):
        return "omitted Greek"
    return None


def check_category(
    found: str | None,
    entry: Mapping[str, object],
    kind: str,
    key: str,
    what: str = "slip",
) -> None:
    """An entry must fit a category, unless it is marked uncategorized, and
    only then."""
    uncategorized = entry.get("uncategorized", False)
    require(
        found is not None or uncategorized,
        f"{kind} fits no category of {what}: {key}",
    )
    require(
        found is None or not uncategorized,
        f"{kind} listed as uncategorized is a {found}: {key}",
    )


def corrected(text: str, correction: Correction, kind: str, key: str) -> str:
    """The text with a correction's one occurrence of its "from" replaced."""
    require(text.count(correction["from"]) == 1, f"{kind} does not apply: {key}")
    require(
        correction["from"] not in correction["to"],
        f"{kind} is a no-op or remains applicable: {key}",
    )
    check_category(
        category(correction["from"], correction["to"]), correction, kind, key
    )
    return text.replace(correction["from"], correction["to"])


def in_a_note(text: str, snippet: str) -> bool:
    """Whether the snippet's one occurrence lies within a note."""
    start = text.index(snippet)
    end = start + len(snippet)
    return any(m.start() <= start and end <= m.end() for m in NOTE.finditer(text))


# A key that names a verse, or with #n the verse's nth note.
VERSE_KEY = re.compile(r"(\d+:\d+[a-z]?)(?:#([2-9]|[1-9]\d+))?")


def in_its_place(text: str, key: str, snippet: str) -> bool:
    """Whether the snippet's one occurrence, keyed by words rather than a verse,
    lies where its key says: in a file without verses, in a note standing among
    the words it names, or outside the notes, in the words it names."""
    start = text.index(snippet)
    end = start + len(snippet)
    place = key.partition(" ")[2]
    if "#" in place:
        return False
    touched = [m for m in NOTE.finditer(text) if m.start() < end and start < m.end()]
    if not touched and not verse_spans(text):
        return words_of(place) == words_of(snippet)
    if len(touched) != 1:
        return False
    note = touched[0]
    before, after = (
        words_of(NOTE.sub("", side))
        for side in (text[: note.start()], text[note.end() :])
    )
    named = words_of(place)
    return any(
        before[len(before) - k :] + after[: len(named) - k] == named
        for k in range(1, len(named))
    )


def target(text: str, key: str, snippet: str) -> tuple[int, int, bool]:
    """Where a correction keyed by a verse applies, and whether it is a note:
    the note #n names, or with no number the verse's first note where the
    snippet is in it, or else the verse from its marker."""
    reference, number = VERSE_KEY.fullmatch(key.partition(" ")[2]).groups()  # type: ignore[union-attr]
    notes = [m for m in NOTE.finditer(text) if m[2] == reference]
    spans = [
        (first, last) for ref, first, last in verse_spans(text) if ref == reference
    ]
    if number is not None or (notes and snippet in notes[0][0]):
        # Words in the first note and in the verse's own words as well do
        # not say which a key without a number means.
        require(
            number is not None
            or not any(snippet in NOTE.sub("", text[a:b]) for a, b in spans),
            f"Brenton correction is ambiguous between a note and its verse: {key}",
        )
        index = int(number or 1) - 1
        require(
            index < len(notes), f"Brenton correction is not where its key says: {key}"
        )
        return notes[index].start(), notes[index].end(), True
    require(len(spans) == 1, f"Brenton correction is not where its key says: {key}")
    first, last = spans[0]
    return text.rfind("\\v ", 0, first), last, False


def in_translation(text: str, snippet: str) -> bool:
    """Whether the snippet's one occurrence touches translation: a book's verses,
    or a passage the appendix supplies. Most of the appendix's notes come before
    its first passage; after it, a paragraph is translation from its first \\vp,
    the label before being Brenton's, or throughout, where it has none. That
    errs toward the translation: a passage may open with its label alone, and
    the few notes set among the passages are taken for one."""
    start = text.index(snippet)
    end = start + len(snippet)
    spans = [(first, last) for _, first, last in verse_spans(text)]
    if (passages := text.find("\\vp ")) >= 0:
        for m in APPENDIX_PARAGRAPH.finditer(text, text.rfind("\n", 0, passages) + 1):
            spans.append((m.start() + max(m[0].find("\\vp "), 0), m.end()))
    return any(first < end and start < last for first, last in spans)


def brenton(
    code: str, text: str, corrections: Mapping[str, Correction | tuple[Correction, ...]]
) -> tuple[str, frozenset[str]]:
    """A Brenton source file with its corrections, and the keys of the notes
    they mend, without the file's code.

    A correction is keyed by the file's code and the verse or note it mends; #n
    names the nth note in a verse, and a key without it the verse's first note
    where the correction's words are in it. A correction to a note is made
    within that note alone, where its words must be found once, and may not
    reach beyond it. Outside notes a correction may only mend word spaces in
    translation or restore a whole note Brenton printed that the transcription
    lacks, his 1844 printing's among them, so the translation stays eBible's.
    In a file without verses, the key names the words the note stands among,
    or outside the notes, the words it mends, which are found once in the
    file; a preface, an introduction, or the appendix's notes and labels may
    have their words mended.
    """
    mended = set()
    for key, group in corrections.items():
        if book_of(key) != code:
            continue
        place = key.partition(" ")[2]
        for correction in group if isinstance(group, tuple) else (group,):
            source = correction["from"]
            restored = category(source, correction["to"]) == "missing note"
            if VERSE_KEY.fullmatch(place):
                start, end, in_note = target(text, key, source)
                found = [m.start() for m in re.finditer(re.escape(source), text)]
                within = text[start:end]
                require(
                    not in_note
                    or not any(
                        at < start < at + len(source) or at < end < at + len(source)
                        for at in found
                    ),
                    f"Brenton correction reaches beyond its note: {key}",
                )
                require(
                    source in within or not found,
                    f"Brenton correction is not where its key says: {key}",
                )
                after = corrected(within, correction, "Brenton correction", key)
                if in_note:
                    require(not restored, f"Brenton note restored in a note: {key}")
                    # It leaves one whole note, or removes the note whole.
                    require(
                        NOTE.fullmatch(after) is not None or not after,
                        f"Brenton correction reaches beyond its note: {key}",
                    )
                    mended.add(place)
                else:
                    at = start + within.index(source)
                    touched = [
                        m
                        for m in NOTE.finditer(text)
                        if m.start() < at + len(source) and at < m.end()
                    ]
                    require(
                        all(
                            m.start() <= at and at + len(source) <= m.end()
                            for m in touched
                        ),
                        f"Brenton correction reaches beyond its note: {key}",
                    )
                    require(
                        not touched,
                        f"Brenton correction is not where its key says: {key}",
                    )
                    require(
                        restored
                        or canonical_text(source) == canonical_text(correction["to"]),
                        f"Brenton correction changes the wording outside a note: {key}",
                    )
                text = text[:start] + after + text[end:]
                continue
            after = corrected(text, correction, "Brenton correction", key)
            require(
                in_its_place(text, key, source),
                f"Brenton correction is not where its key says: {key}",
            )
            in_note = in_a_note(text, source)
            require(
                not (in_note and restored), f"Brenton note restored in a note: {key}"
            )
            in_scripture = not (in_note or restored or not in_translation(text, source))
            require(
                not in_scripture
                or canonical_text(NOTE.sub("", source))
                == canonical_text(NOTE.sub("", correction["to"])),
                f"Brenton correction changes the wording outside a note: {key}",
            )
            require(
                not in_scripture
                or len(NOTE.findall(source)) == len(NOTE.findall(correction["to"])),
                f"Brenton correction adds or drops a note outside a note: {key}",
            )
            if in_note:
                mended.add(place)
            text = after
    return text, frozenset(mended)
