"""The edition's books, assembled from the sources' (edition/manifest.json):
a book's chapters selected from a file that holds two, Daniel grouped with
Susanna and Bel and the Dragon, the close of Malachias opened as a chapter of
its own, and each book under the edition's name and heading.

What the edition prints is read from the assembled books themselves: nothing
predicts which chapters and verses a manuscript decision or a grouping leaves.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from typing import TypedDict, Unpack

import bible.policy
import bible.references
import bible.sources
from bible import usfm, usj, versification
from bible.checks import present, require
from bible.policy import source_id
from bible.policy_schema import Entry
from bible.references import Books
from bible.usj import Document, Node


class ChapterExtra(TypedDict, total=False):
    pubnumber: str


NAME_MARKERS = {"title": "toc1", "short_title": "toc2", "abbreviation": "toc3"}
NAME_ATTRIBUTES = {"abbreviation": "abbr", "short_title": "short", "title": "long"}
# A hidden chapter number: the chapter is one for citing, and prints none.
HIDDEN = "​"
# Daniel's parts that the Greek sets about it, each under a heading.
DANIEL = (("SUS", "0", "Susanna"), ("BEL", "13", "Bel and the Dragon"))
SONG = (
    "3:25",
    "Then Azarias stood up, and prayed on this manner",
    "The Song of the Three Children",
)


def source_marker(text: str, marker: str) -> str:
    """The words of a source file's first line of a kind."""
    match = present(
        re.search(r"^\\" + marker + r"\s+([^\n]+)", text, re.M),
        f"Missing source {marker} marker",
    )
    return match[1].strip()


def source_text(entry: Entry, sources: bible.sources.Sources) -> str:
    """The text an entry is prepared from: its source file, or the edition's own."""
    if "file" in entry:
        return sources.authored[entry["file"]]
    return sources[entry["source"]][source_id(entry)]


def printed_title(value: str, marker: str) -> str:
    saint = "SAINT" if marker.startswith("mt") else "Saint"
    value = re.sub(r"(?<!\w)S\.(?=\s|$)", saint, value)
    return re.sub(r"\.(\s*)$", r"\1", value)


def names(entry: Entry, text: str) -> dict[str, str]:
    """The contents title, running-head title, and abbreviation of an entry.

    The edition's names replace the source's. Front matter that the edition
    does not rename keeps its source names, as preparation prints them.
    """
    if "title" not in entry and "section" not in entry:
        found = {
            field: source_marker(text, marker) for field, marker in NAME_MARKERS.items()
        }
        found["title"] = printed_title(found["title"], "toc1")
        return found
    require(entry.get("title"), f"Missing title: {entry['id']}")
    return {
        "title": entry["title"],
        "short_title": entry.get("short_title") or source_marker(text, "toc2"),
        "abbreviation": entry.get("abbreviation") or source_marker(text, "toc3"),
    }


def books(
    policy: bible.policy.Policy, sources: bible.sources.Sources
) -> bible.references.Books:
    """The edition's books, in its order, under their running-head names,
    and the names by which one of a book's chapters is cited."""
    return Books(
        (
            (unit["id"], names(unit, source_text(unit, sources))["short_title"])
            for unit in policy.scripture
        ),
        _cited_singly(policy),
    )


def kjv_books(
    policy: bible.policy.Policy, sources: bible.sources.Sources
) -> bible.references.Books:
    """The King James Bible's books, in its order, under its own names for
    them, which a reader's other Bible has."""
    return Books(
        (
            (code, source_marker(text, "toc2"))
            for code, text in sources.kjv.items()
            if re.search(r"^\\toc2\s", text, re.M)
        ),
        _cited_singly(policy),
    )


def _cited_singly(policy: bible.policy.Policy) -> Iterator[tuple[str, str]]:
    return (
        (unit["id"], unit["cited_singly"])
        for unit in policy.scripture
        if "cited_singly" in unit
    )


def heading_lines(entry: Entry, found: Mapping[str, str]) -> list[tuple[str, str]]:
    """The mt lines printed over a book, as (marker, text) pairs.

    As in the Cambridge KJV, the heading is the contents title itself. The
    manifest's optional "heading" says how to break it into lines and which
    line is the main one; without it the whole title is one mt1 line.
    """
    lines = entry.get("heading", (("mt1", found["title"]),))
    require(
        all(
            len(line) == 2
            and line[0] in usfm.HEADING_MARKERS
            and isinstance(line[1], str)
            and line[1].strip() == line[1] != ""
            for line in lines
        )
        and sum(marker == "mt1" for marker, _ in lines) == 1,
        f"Invalid heading: {entry['id']}",
    )
    require(
        " ".join(text for _, text in lines) == found["title"],
        f"Heading lines do not spell the contents title: {entry['id']}",
    )
    return [(marker, text) for marker, text in lines]


def named(entry: Entry, doc: Document, text: str) -> Document:
    """A document with the edition's names and heading in place of the source's."""
    found = names(entry, text)
    replacements = {
        "h": found["short_title"],
        **{marker: found[field] for field, marker in NAME_MARKERS.items()},
    }
    blocks, seen = [], set()
    for index, block in enumerate(doc["content"]):
        if block["type"] == "chapter":
            blocks += doc["content"][index:]
            break
        marker = block.get("marker")
        if marker in replacements:
            blocks.append({**block, "content": [replacements[marker]]})
            seen.add(marker)
        elif marker == "mt1":
            blocks += [usj.para(m, value) for m, value in heading_lines(entry, found)]
            seen.add(marker)
        elif marker not in ("mt2", "mt3"):
            # The whole heading is replaced, so the source's subtitle lines go.
            blocks.append(block)
    require(
        seen == {*replacements, "mt1"},
        f"Missing book header fields: {entry['id']}: {sorted(seen)}",
    )
    return usj.with_blocks(doc, blocks)


def chapters_of(doc: Document) -> tuple[list[Node], list[list[Node]]]:
    """A document's blocks before its first chapter, and each chapter's blocks."""
    starts = [i for i, block in enumerate(doc["content"]) if block["type"] == "chapter"]
    require(bool(starts), f"Source has no chapters: {usj.book_code(doc)}")
    return doc["content"][: starts[0]], [
        doc["content"][a:b] for a, b in zip(starts, [*starts[1:], len(doc["content"])])
    ]


def relabelled(
    blocks: list[Node], number: int | str, **extra: Unpack[ChapterExtra]
) -> list[Node]:
    chapter, *rest = blocks
    return [{**chapter, "number": str(number), **extra}, *rest]


def daniel(doc: Document, brenton: Mapping[str, Document]) -> Document:
    """Daniel with Susanna before it and Bel and the Dragon after, each a
    chapter that prints no number under its heading, and the Song of the Three
    Children headed where it begins."""
    header, chapters = chapters_of(doc)
    require(len(chapters) == 12, "Daniel source boundaries changed")
    parts = {}
    for code, number, title in DANIEL:
        _, found = chapters_of(brenton[code])
        require(len(found) == 1, "Daniel source boundaries changed")
        parts[code] = [
            usj.para("s1", title),
            *relabelled(found[0], number, pubnumber=HIDDEN),
        ]
    reference, opens, title = SONG
    third = chapters[2]
    at = next(
        (
            (index, n)
            for index, block in enumerate(third)
            if block["type"] == "para"
            for n, item in enumerate(block["content"])
            if usj.is_type(item, "verse") and item["number"] == reference.split(":")[1]
        ),
        None,
    )
    require(
        at is not None
        and usj.text_of(third[at[0]]["content"][at[1] + 1 :]).startswith(opens),
        "Daniel 3 Song of the Three Children boundary changed",
    )
    assert at is not None
    index, n = at
    block = third[index]
    chapters[2] = [
        *third[:index],
        # The paragraph the verse stood in closes before the heading.
        {**block, "content": block["content"][:n]},
        usj.para("s1", title),
        usj.para("p", *block["content"][n:]),
        *third[index + 1 :],
    ]
    blocks = [*header, *parts["SUS"], *(b for c in chapters for b in c), *parts["BEL"]]
    return usj.with_blocks(doc, blocks)


def opened_chapters(code: str, doc: Document, policy: bible.policy.Policy) -> Document:
    """A book with the close of a chapter opened as a chapter of its own,
    where the edition relabels it, as Malachias 3:19-24 is its chapter 4."""
    for labels, printed, opens in versification.new_chapters(code, policy=policy):
        first, chapter = labels[0], printed[0].chapter
        targets: Mapping[tuple[str | None, str], bible.references.Verse] = {
            (str(v.chapter), f"{v.number}{v.letter}"): t
            for v, t in zip(labels, printed)
        }
        blocks: list[Node] = []
        current: str | None = None
        opened = False
        for block in doc["content"]:
            if block["type"] == "chapter":
                current = block["number"]
            elif block["type"] == "para":
                numbers = [
                    (n, item)
                    for n, item in enumerate(block["content"])
                    if usj.is_type(item, "verse")
                ]
                if any((current, item["number"]) in targets for _, item in numbers):
                    content = list(block["content"])
                    for n, item in numbers:
                        target = targets.get((current, item["number"]))
                        if target is None:
                            continue
                        if target == printed[0]:
                            # Open the chapter before its paragraph, not inside it.
                            require(
                                n == 0
                                and block["marker"] == "p"
                                and usj.text_of(content[1:]).startswith(opens),
                                f"{code} chapter {chapter} boundary changed",
                            )
                            blocks.append(
                                {
                                    "type": "chapter",
                                    "marker": "c",
                                    "number": str(chapter),
                                }
                            )
                            opened = True
                        content[n] = {**item, "number": str(target.number)}
                    block = {**block, "content": content}
            blocks.append(block)
        require(opened, f"{code} chapter boundary changed")
        doc = usj.with_blocks(doc, blocks)
        found = usj.inventory(doc)
        require(
            list(found) == [str(c) for c in range(1, chapter + 1)]
            and found[str(first.chapter)] == [str(i) for i in range(1, first.number)]
            and found[str(chapter)] == [str(v.number) for v in printed],
            f"Wrong {code} {first.chapter}-{chapter} verse labels",
        )
    return doc


def scripture_unit(
    entry: Entry,
    brenton: Mapping[str, Document],
    kjv: Mapping[str, Document],
    policy: bible.policy.Policy,
) -> Document:
    """One of the edition's books, from its source's chapters, before its
    name and its notes."""
    code = entry["id"]
    doc = (brenton if entry["source"] == "brenton" else kjv)[source_id(entry)]
    if "chapters" in entry:
        # Part of a source file that holds more than one book, numbered from 1.
        first, last = entry["chapters"]
        header, chapters = chapters_of(doc)
        require(
            0 < first <= last <= len(chapters),
            f"Manifest chapters outside the source: {code}",
        )
        doc = usj.with_blocks(
            doc,
            [
                *header,
                *(
                    block
                    for n, chapter in enumerate(chapters[first - 1 : last], 1)
                    for block in relabelled(chapter, n)
                ),
            ],
        )
        require(
            list(usj.inventory(doc)) == [str(c) for c in range(1, last - first + 2)],
            f"Wrong chapter selection: {code}",
        )
    elif code == "DAG":
        doc = daniel(doc, brenton)
        require(
            list(usj.inventory(doc)) == [str(i) for i in range(14)],
            "Wrong chapter grouping: DAG",
        )
    # A book printed from a file that holds another is a unit of its own.
    book, *rest = doc["content"]
    doc = usj.with_blocks(doc, [{**book, "code": code}, *rest])
    return opened_chapters(code, doc, policy)


def check_divided(policy: bible.policy.Policy, sources: bible.sources.Sources) -> None:
    """A source divided between units must be printed whole, each chapter once."""
    divided: dict[tuple[str, str], list[str]] = {}
    for unit in policy.scripture:
        if "chapters" in unit:
            first, last = unit["chapters"]
            divided.setdefault((unit["source"], source_id(unit)), []).extend(
                str(c) for c in range(first, last + 1)
            )
    for (source, code), chapters in divided.items():
        found = re.findall(r"^\\c (\d+)", sources[source][code], re.M)
        require(chapters == found, f"Divided source not printed whole: {source}/{code}")


def inventory(units: Mapping[str, Document]) -> dict[str, dict[str, list[str]]]:
    """What the edition prints: each book's chapters and their verses."""
    return {code: usj.inventory(doc) for code, doc in units.items()}
