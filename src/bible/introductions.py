"""The introductions to the books of the Apocrypha, from the front-matter
chapter that introduces them together, printed where the books are.

The chapter isn't Brenton's: it was written for a later edition of his
translation.

The chapter's account of each book is set as an uncalled footnote on the
book's first verse, except for the Song of the Three Children, whose account
follows its heading at Daniel 3:25.
Its general paragraphs, and the one about a book this edition doesn't print,
stay at the front; its headings, which the books' titles replace, are dropped.
edition/book-introductions.json says where each paragraph goes, by its opening
words, and gives the reason for each editorial gloss and name change, and for any
omission.
"""

from collections import Counter
import itertools
import re

from bible import edition, paths
from bible.checks import require
from bible.files import read_json
from bible.usfm import NOTE, marker_counts, plain_text, verse_spans

INTRODUCTIONS = read_json(paths.EDITION_DIR / "book-introductions.json")
FRONT = "front"
PARAGRAPH = re.compile(r"^\\ip\s")
HEADING = re.compile(r"^\\is\d?\s+(.*?)\s*$")
# The chapter's header, paragraphs and headings, each on a line of its own.
LINE = re.compile(r"^\\(?:id|h|toc\d|mt\d?|ip|is\d?)\s")
# An editorial gloss, which the edition's introduction says is bracketed.
GLOSS = re.compile(r" ?\[[^\[\]]+\]")


def source_lines(source_text):
    """The chapter's lines, which front_text and placed_paragraphs both read.

    A paragraph that ran on to another line would be moved only in part.
    """
    lines = source_text.split("\n")
    strays = [line[:40] for line in lines if line.strip() and not LINE.match(line)]
    require(not strays, f"Book introduction line of an unknown kind: {strays}")
    return lines


def once_in_words(text, words):
    """Whether the words occur once in the text, and not as part of a longer word."""
    return (
        text.count(words) == 1
        and re.search(rf"(?<!\w){re.escape(words)}(?!\w)", text) is not None
    )


def source_paragraphs(source_text):
    """The chapter's paragraphs, unglossed, in source order."""
    return [
        PARAGRAPH.sub("", line, count=1).strip()
        for line in source_lines(source_text)
        if PARAGRAPH.match(line)
    ]


def placed_paragraphs(source_text):
    """Each placement (front or a book's id) with its paragraphs, as (index in
    the source, key, glossed body), in source order.

    Every paragraph of the source must be placed or explicitly omitted exactly
    once, and every gloss must apply once.
    """
    bodies = source_paragraphs(source_text)
    bracketed = [b[:40] for b in bodies if "[" in b or "]" in b]
    require(not bracketed, f"Book introduction brackets not a gloss's: {bracketed}")
    plain = [plain_text(b) for b in bodies]
    # A misspelt field would otherwise fail as a KeyError, not a refusal.
    malformed = sorted(
        f"{code}@{verse}"
        for code, sections in INTRODUCTIONS["sections"].items()
        for verse, section in sections.items()
        if section.keys() != {"heading", "paragraphs"}
    )
    require(
        not malformed,
        f"Book introduction sections with missing or unknown fields: {malformed}",
    )
    placements = (
        [(FRONT, key) for key in INTRODUCTIONS["front"]]
        + [(code, key) for code, keys in INTRODUCTIONS["books"].items() for key in keys]
        + [
            (f"{code}@{verse}", key)
            for code, sections in INTRODUCTIONS["sections"].items()
            for verse, section in sections.items()
            for key in section["paragraphs"]
        ]
    )
    omitted = INTRODUCTIONS["omit"]
    require(all(omitted.values()), "Omitted book introductions need a reason")
    accounted = placements + [(None, key) for key in omitted]
    books = {u["id"] for u in edition.MANIFEST["scripture"] if u["source"] == "brenton"}
    unknown = sorted(
        (set(INTRODUCTIONS["books"]) | set(INTRODUCTIONS["sections"])) - books
    )
    require(not unknown, f"Book introductions for books outside the edition: {unknown}")
    indices = []
    for _, key in accounted:
        matches = [i for i, p in enumerate(plain) if p.startswith(key)]
        require(
            len(matches) == 1, f"Book introduction key names no one paragraph: {key}"
        )
        indices.append(matches[0])
    doubled = sorted(bodies[i][:40] for i, n in Counter(indices).items() if n > 1)
    require(not doubled, f"Book introduction paragraphs placed twice: {doubled}")
    placed = set(indices)
    unplaced = [b[:40] for i, b in enumerate(bodies) if i not in placed]
    require(not unplaced, f"Book introduction paragraphs not placed: {unplaced}")
    glosses = INTRODUCTIONS["glosses"]
    names = INTRODUCTIONS["names"]
    placed_keys = {key for _, key in placements}
    unused = sorted(set(glosses) - placed_keys)
    require(not unused, f"Glosses on no placed paragraph: {unused}")
    unused_names = sorted(set(names) - placed_keys)
    require(not unused_names, f"Name changes on no placed paragraph: {unused_names}")
    no_glosses = sorted(key for key, entries in glosses.items() if not entries)
    require(not no_glosses, f"Glosses with no gloss: {no_glosses}")
    no_changes = sorted(key for key, changes in names.items() if not changes)
    require(not no_changes, f"Name changes with no change: {no_changes}")
    result = {}
    for (place, key), index in zip(accounted, indices):
        if place is None:
            continue
        body = bodies[index]
        for gloss in glosses.get(key, []):
            require(gloss.get("why"), f"Gloss without a why: {key}")
            require(
                GLOSS.fullmatch(gloss.get("insert", "")),
                f"Gloss is not one bracketed insertion: {key}",
            )
            # A gloss follows the source's words, or replaces them. Once in the
            # source as well, so that no gloss falls inside or across another.
            replaces = "replace" in gloss
            words = gloss.get("replace" if replaces else "after")
            require(
                replaces != ("after" in gloss)
                and words
                and once_in_words(bodies[index], words)
                and once_in_words(body, words),
                f"Gloss does not apply: {key}",
            )
            if replaces:
                require(
                    not gloss["insert"].startswith(" "),
                    f"Gloss replacing words starts with a space: {key}",
                )
                body = body.replace(words, gloss["insert"])
            else:
                require(
                    gloss["insert"].startswith(" "),
                    f"Gloss following words starts without a space: {key}",
                )
                body = body.replace(words, words + gloss["insert"])
        for change in names.get(key, []):
            require(change.get("why"), f"Name change without a why: {key}")
            old, new = change.get("from"), change.get("to")
            # The source's words, so that no change alters or removes a gloss.
            require(
                old
                and new
                and old != new
                and once_in_words(bodies[index], old)
                and once_in_words(body, old),
                f"Name change does not apply once: {key}",
            )
            # The editor's own words are bracketed, and only a gloss adds them.
            require(
                "[" not in new and "]" not in new,
                f"Name change adds brackets, which are a gloss's: {key}",
            )
            body = body.replace(old, new)
        # The source's italics and small capitals survive its glosses and name
        # changes, which no later check compares with the source.
        require(
            marker_counts(body) == marker_counts(bodies[index]),
            f"Gloss or name change alters the markup: {key}",
        )
        result.setdefault(place, []).append((index, key, body))
    # A book or section with no paragraphs would print no note, or fail to be
    # found, and a front with none would print a title alone.
    empty = sorted(
        (
            {FRONT}
            | set(INTRODUCTIONS["books"])
            | {
                f"{code}@{verse}"
                for code, sections in INTRODUCTIONS["sections"].items()
                for verse in sections
            }
        )
        - set(result)
    )
    require(not empty, f"Book introductions with no paragraphs: {empty}")
    for place, paragraphs in result.items():
        order = [i for i, _, _ in paragraphs]
        require(
            order == sorted(order), f"Book introduction out of source order: {place}"
        )
    return result


def front_text(source_text, record):
    """The front-matter chapter without its headings and the paragraphs its
    books print."""
    front = placed_paragraphs(source_text).get(FRONT, [])
    kept = {index: body for index, _, body in front}
    lines = []
    dropped_headings = []
    paragraph_index = itertools.count()
    for line in source_lines(source_text):
        if PARAGRAPH.match(line):
            index = next(paragraph_index)
            if index not in kept:
                continue
            line = f"\\ip {kept[index]}"
        elif heading := HEADING.match(line):
            dropped_headings.append(heading[1])
            continue
        lines.append(line)
    keys = [key for _, key, _ in front]
    record(
        "move the books' introductions to footnotes on their opening verses",
        kept_paragraphs=keys,
        omitted_paragraphs=dict(INTRODUCTIONS["omit"]),
        dropped_headings=dropped_headings,
        **edits(keys),
    )
    return "\n".join(lines)


def edits(keys):
    """The glosses and name changes on the paragraphs, as a record lists them."""
    return {
        "glosses": [
            gloss["insert"].strip()
            for key in keys
            for gloss in INTRODUCTIONS["glosses"].get(key, [])
        ],
        "names": [
            {"from": change["from"], "to": change["to"]}
            for key in keys
            for change in INTRODUCTIONS["names"].get(key, [])
        ],
    }


def note_body(body):
    """A paragraph's USFM inside a note, where character styles nest."""
    return re.sub(r"\\(?!\+)(\w+\*?)", r"\\+\1", body)


def underscored(body):
    """A paragraph as the notes review shows it, its italic between underscores."""
    return plain_text(re.sub(r"\\it (.*?)\\it\*", r"_\1_", body))


def book_notes(source_text):
    """Each introduced book's footnote, the keys of its paragraphs, the note as
    the notes review shows it, and its source paragraphs without glosses or name
    changes, by id."""
    bodies = source_paragraphs(source_text)
    return {
        place: (
            "\\f - \\ft "
            + " ".join(note_body(body) for _, _, body in paragraphs)
            + "\\f*",
            [key for _, key, _ in paragraphs],
            " ".join(underscored(body) for _, _, body in paragraphs),
            " ".join(plain_text(bodies[index]) for index, _, _ in paragraphs),
        )
        for place, paragraphs in placed_paragraphs(source_text).items()
        if place != FRONT
    }


def with_book_note(code, text, source_text, record, review=None):
    """The book's and its sections' introductions on their opening verses, each
    listed in the notes review."""
    notes = book_notes(source_text)
    placements = [("first verse", notes[code])] if code in notes else []
    placements += [
        (verse, notes[f"{code}@{verse}"])
        for verse in INTRODUCTIONS["sections"].get(code, {})
    ]
    if not placements:
        return text
    spans = verse_spans(text)
    require(spans, f"No first verse for the book introduction: {code}")
    insertions = []
    for verse, (note, keys, shown, source) in placements:
        matching = (
            spans[:1]
            if verse == "first verse"
            else [span for span in spans if span[0] == verse]
        )
        require(len(matching) == 1, f"Book introduction verse missing: {code} {verse}")
        start = matching[0][1]
        if verse != "first verse":
            heading = INTRODUCTIONS["sections"][code][verse]["heading"]
            require(
                text[:start].endswith(
                    f"\\s1 {heading}\n\\p\n\\v {verse.split(':')[1]} "
                ),
                f"Book introduction heading changed: {code} {verse}",
            )
        insertions.append((start, note))
        if review is not None:
            reference = f"{code} {matching[0][0]}"
            review.append(
                {
                    "key": f"{reference} introduction",
                    "rule": "book introduction",
                    "verse": plain_text(NOTE.sub("", text[start : matching[0][2]])),
                    "lemma": None,
                    "note": shown,
                    "source": source,
                    "style": "introduction",
                }
            )
        record(
            "introduce the book or section with a footnote from the introduction to the Apocrypha",
            source_id=INTRODUCTIONS["source"],
            verse=matching[0][0],
            paragraphs=keys,
            **edits(keys),
        )
    # From the end, so earlier offsets hold; notes at one offset keep the order
    # they're placed in, the book's before a section's.
    for start, note in reversed(sorted(insertions, key=lambda i: i[0])):
        text = text[:start] + note + text[start:]
    return text
