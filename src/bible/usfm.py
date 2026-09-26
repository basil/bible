"""USFM text helpers: inventories, chapter and verse structure, and the
canonical forms that the build's wording and markup checks compare.

Verse labels are strings (including bridges and letters), and markers are
counted by name.
"""

import collections
import re

from bible.checks import require

# A USFM marker: its name, with the + of a nested character style and the * that
# closes a span.
MARKER = r"\\(\+?[\w-]+\*?)"
HEADING_MARKERS = ("mt1", "mt2", "mt3")
# Notes, character styles and table cells, which PTXprint must keep...
NOTE_AND_STYLE_MARKERS = {"f", "x", "add", "it", "tr", "tc1", "tc2", "vp"}
# ...and the parts of notes, which preparation must keep as well.
NOTE_PART_MARKERS = {"fr", "ft", "fqa", "xo", "xt"}
# USFM's escapes for characters that would otherwise be markup.
ESCAPED_CHARACTERS = {
    "asterisk": "*",
    "percent": "%",
    "hash": "#",
    "dollar": "$",
    "ampersand": "&",
    "circumflex": "^",
    "space": " ",
}


def marker_counts(text):
    return collections.Counter(re.findall(MARKER, text))


def inventory(text):
    chapters = {}
    chapter = None
    for m in re.finditer(r"\\(c|v)\s+(\S+)", text):
        kind, label = m.groups()
        if kind == "c":
            if label in chapters:
                raise ValueError(f"Duplicate chapter {label}")
            chapter = label
            chapters[chapter] = []
        else:
            if chapter is None:
                raise ValueError("Verse before chapter")
            if label in chapters[chapter]:
                raise ValueError(f"Duplicate verse {chapter}:{label}")
            chapters[chapter].append(label)
    return {"chapters": chapters, "markers": dict(sorted(marker_counts(text).items()))}


def source_marker(text, marker):
    match = re.search(r"^\\" + marker + r"\s+([^\n]+)", text, re.M)
    require(match is not None, f"Missing source {marker} marker")
    return match[1].strip()


def replace_marker_line(text, marker, value, code):
    """The text with the value of its first \\marker line replaced."""
    text, count = re.subn(
        r"^(\\" + marker + r"\s+)[^\n]*",
        lambda m: m[1] + value,
        text,
        count=1,
        flags=re.M,
    )
    require(count == 1, f"Missing {marker} heading: {code}")
    return text


def marker_lines(text, markers):
    """The (marker, value) pairs of the lines that open with one of the markers."""
    pattern = r"^\\(" + "|".join(markers) + r")\s+([^\n]*)$"
    return [
        (marker, value.strip()) for marker, value in re.findall(pattern, text, re.M)
    ]


def chapter_parts(text):
    parts = re.split(r"(?=\\c \d+\s)", text)
    return parts[0], parts[1:]


def renumber_chapters(chapters, offset):
    """Chapters whose opening chapter marker is lowered by offset."""
    return [
        re.sub(r"^\\c (\d+)", lambda m: f"\\c {int(m[1]) - offset}", c, count=1)
        for c in chapters
    ]


def verse_spans(text):
    """Each verse's reference with the offsets of its text, up to the next verse."""
    spans = []
    chapter = None
    markers = list(re.finditer(r"\\(c|v) (\S+)\s*", text))
    for index, m in enumerate(markers):
        if m[1] == "c":
            chapter = m[2]
            continue
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        spans.append((f"{chapter}:{m[2]}", m.end(), end))
    return spans


def word_tokens(text):
    """Words with their offsets, ignoring markup, case, and punctuation.

    Markers are blanked rather than removed so that offsets index the USFM itself.
    Apostrophes join a word (king’s is kings); hyphens separate one (market-place).
    """
    masked = re.sub(MARKER, lambda m: " " * len(m[0]), text)
    return [
        (re.sub(r"[’']", "", m[0]).casefold(), m.start())
        for m in re.finditer(r"[A-Za-z]+(?:[’'][A-Za-z]+)*", masked)
    ]


def canonical_text(text):
    # Ignore only markup and whitespace; retain every source word, number and punctuation.
    text = re.sub(
        r"\\(" + "|".join(ESCAPED_CHARACTERS) + r")\b\s?",
        lambda m: ESCAPED_CHARACTERS[m[1]],
        text,
    )
    text = re.sub(MARKER + r"\s?", "", text)
    return re.sub(r"\s+", "", text)


def passage_payload(text):
    """A wording witness that ignores only headings and displayed reference labels."""
    text = text[text.index(r"\c ") :]
    text = re.sub(r"\\s\d?\s+[^\n]*", "", text)
    text = re.sub(r"\\cp\s+[^\n]*", "", text)
    text = re.sub(r"\\(?:c|v)\s+\d+[a-z]?\s*", "", text)
    text = re.sub(r"\\(?:fr|xo)\s+\d+:\d+[a-z]?\s*", "", text)
    return canonical_text(text)


def preserved_markers(text):
    """Counts of the note and character-style markers, which preparation must keep."""
    kept = NOTE_AND_STYLE_MARKERS | NOTE_PART_MARKERS
    return {
        marker: count
        for marker, count in marker_counts(text).items()
        if marker.lstrip("+").rstrip("*") in kept
    }
