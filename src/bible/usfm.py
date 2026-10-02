"""USFM as text: what the build reads of a source before it is parsed, and of
PTXprint's files after they are written. Every document between is USJ.

Verse labels are strings (including bridges and letters), and markers are
counted by name.
"""

from __future__ import annotations

import re
from typing import TypedDict

from bible import scripture


class Inventory(TypedDict):
    chapters: dict[str, list[str]]
    markers: dict[str, int]


# Unicode source alphabets.
GREEK = "\u0370-\u03ff\u1f00-\u1fff"
HEBREW = "\u0590-\u05ff"
# A marker as printing removes it: a closing one ends at its asterisk, and an
# opening one takes one space.
MARKUP = re.compile(r"\\\+?[\w-]+(?:\*| ?)")
HEADING_MARKERS = ("mt1", "mt2", "mt3")
# USFM's escapes for characters that would otherwise be markup.
ESCAPED = {
    "asterisk": "*",
    "percent": "%",
    "hash": "#",
    "dollar": "$",
    "ampersand": "&",
    "circumflex": "^",
    "space": " ",
}


def inventory(text: str) -> Inventory:
    """A text's chapters with their verses' labels, and its markers counted."""
    chapters: dict[str, list[str]] = {}
    chapter: str | None = None
    for kind, label in re.findall(r"\\(c|v)\s+(\S+)", text):
        if kind == "c":
            chapter = label
            chapters[chapter] = []
        else:
            assert chapter is not None
            chapters[chapter].append(label)
    markers: dict[str, int] = {}
    for marker in re.findall(r"\\(\+?[\w-]+\*?)", text):
        markers[marker] = markers.get(marker, 0) + 1
    return {"chapters": chapters, "markers": markers}


def heading(text: str) -> str:
    """The words of a text's heading lines."""
    lines = re.findall(
        r"^\\(?:" + "|".join(HEADING_MARKERS) + r")\s+([^\n]*)$", text, re.M
    )
    return " ".join(line.strip() for line in lines)


def verse_spans(text: str) -> list[tuple[str, int, int]]:
    """Each verse's reference with the offsets of its text, up to the next verse."""
    spans, chapter = [], None
    markers = list(re.finditer(r"\\(c|v) (\S+)\s*", text))
    for index, m in enumerate(markers):
        if m[1] == "c":
            chapter = m[2]
            continue
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        spans.append((f"{chapter}:{m[2]}", m.end(), end))
    return spans


def words_of(text: str) -> list[str]:
    """The words of a stretch of USFM, as scripture.words_of reads them,
    ignoring its markup."""
    return scripture.words_of(MARKUP.sub("", text))


def plain_text(text: str) -> str:
    """The printable words of a stretch of USFM, markup removed, spaces collapsed."""
    return " ".join(MARKUP.sub("", text).split())


def canonical_text(text: str) -> str:
    """A text's printed characters, without its markup and spaces."""
    text = re.sub(r"\\(" + "|".join(ESCAPED) + r")\b\s?", lambda m: ESCAPED[m[1]], text)
    return re.sub(r"\s+", "", re.sub(r"\\(\+?[\w-]+\*?)\s?", "", text))
