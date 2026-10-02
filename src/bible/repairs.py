"""Corrections to the sources' transcription, made before anything reads them.

eBible's text of Brenton and Calvin George's transcription of the 1611 margin
have slips: a missing word space, a doubled label, a transcriber's remark.
edition/brenton-notes.json and edition/kjv-notes.json mend them, each with its
reason. A correction is made to the source's own text, where it must be found
once, and must fit one of the kinds of slip below unless it is marked
uncategorized, so that no correction can rewrite the translation unnoticed.
"""

import re
import unicodedata

from bible.checks import require
from bible.usfm import GREEK, canonical_text, verse_spans, words_of

# A bracketed remark of the transcriber's or eBible's, with a space beside it.
REMARK = re.compile(r" ?\[[^\]]*\] ?")
EMPTY_NOTE = re.compile(r"\\f \+ \\fr \S+ \\f\*")
# Any caller: the preface's notes use "*" as well as "+".
NOTE = re.compile(r"\\(f|x) \S \\(?:fr|xo) (\S+) ?(.*?)\\\1\*")
# Any paragraph but a heading (\is1, \is2) or a blank line (\ib).
APPENDIX_PARAGRAPH = re.compile(r"^\\(?!i[sb]\d*\b)\w+ [^\n]*", re.M)


def change(before, after):
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


def punctuation(text):
    return len(text) == 1 and unicodedata.category(text).startswith("P")


def letter_slip(old, new):
    """The kind of slip that replaces old with new, if it is one letter's."""
    if not old and len(new) == 1 and new.isalpha():
        return "missing letter"
    if not new and len(old) == 1 and old.isalpha():
        return "stray letter"
    if len(old) == len(new) == 1 and old.isalpha() and new.isalpha():
        return "wrong letter"
    return None


def category(before, after):
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
    if old == "[Greek characters]" and re.fullmatch(rf"[{GREEK}\s,.;]+", new):
        return "omitted Greek"
    return None


def check_category(found, entry, kind, key, what="slip"):
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


def corrected(text, correction, kind, key):
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


def in_a_note(text, snippet):
    """Whether the snippet's one occurrence lies within a note."""
    start = text.index(snippet)
    end = start + len(snippet)
    return any(m.start() <= start and end <= m.end() for m in NOTE.finditer(text))


def in_its_place(text, key, snippet):
    """Whether the snippet's one occurrence lies where its key says: in the verse
    it names, or in a file without verses, in a note standing among the words it
    names, or outside the notes, in the words it names."""
    start = text.index(snippet)
    end = start + len(snippet)
    place = key.partition(" ")[2]
    if verse := re.fullmatch(r"(\d+:\d+[a-z]?)(?:#([2-9]|[1-9]\d+))?", place):
        reference, number = verse.groups()
        matching = [m for m in NOTE.finditer(text) if m[2] == reference]
        if number is not None or in_a_note(text, snippet):
            index = int(number or 1) - 1
            return (
                index < len(matching)
                and matching[index].start() <= start
                and end <= matching[index].end()
            )
        return any(
            ref == reference and first <= start and end <= last
            for ref, first, last in verse_spans(text)
        )
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


def in_translation(text, snippet):
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


def brenton(code, text, corrections):
    """A Brenton source file with its corrections, and the keys of the notes
    they mend, without the file's code.

    A correction is keyed by the file's code and the verse or note it mends; #n
    names the nth note in a verse. Several corrections in one note form a list
    under one key. In a file without verses, the key names the words the note
    stands among, or outside the notes, the words it mends. Outside notes a
    correction may mend only word spaces in translation, so the translation
    stays eBible's. A preface, an introduction, or the appendix's notes and
    labels may have their words mended.
    """
    mended = set()
    for key, group in corrections.items():
        if key.split(" ")[0] != code:
            continue
        for correction in group if isinstance(group, tuple) else (group,):
            after = corrected(text, correction, "Brenton correction", key)
            require(
                in_its_place(text, key, correction["from"]),
                f"Brenton correction is not where its key says: {key}",
            )
            in_note = in_a_note(text, correction["from"])
            require(
                in_note
                or not in_translation(text, correction["from"])
                or canonical_text(correction["from"])
                == canonical_text(correction["to"]),
                f"Brenton correction changes the wording outside a note: {key}",
            )
            if in_note:
                mended.add(key.partition(" ")[2])
            text = after
    return text, frozenset(mended)
