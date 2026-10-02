"""Verses, as the stages that read and change the translation see them.

A verse runs from its number to the next, across the paragraphs and lines
that hold it. Its words are read without its notes, each paragraph parted
from the next by a newline; a place in the verse is an offset in those words.
Changes are declared by such offsets and made together, so that none
disturbs the place of another.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from bible import usj
from bible.checks import require

type Inventory = Mapping[str, Mapping[str, Sequence[str]]]

WORD = re.compile(r"[^\W\d_]+(?:[’'][^\W\d_]+)*")


def word_spans(text: str) -> list[tuple[str, int, int]]:
    """Words with their offsets, ignoring case and punctuation. An apostrophe
    joins a word (king’s is kings); a hyphen separates one (market-place)."""
    return [
        (re.sub(r"[’']", "", m[0]).casefold(), m.start(), m.end())
        for m in WORD.finditer(text)
    ]


def words_of(text: str) -> list[str]:
    return [word for word, _, _ in word_spans(text)]


def plain(text: str) -> str:
    """Words with their spaces and line breaks as single spaces."""
    return " ".join(text.split())


@dataclass(frozen=True)
class Verse:
    reference: str
    # Where it stands: the block, and the items of the block's content.
    parts: tuple[tuple[int, int, int, int], ...]
    text: str
    # Each note in it, with the offset in the words where it stands.
    notes: tuple[tuple[int, usj.Node], ...]

    @property
    def lines(self) -> tuple[int, ...]:
        """The offsets at which a new paragraph or line of the verse begins."""
        return tuple(m.end() for m in re.finditer("\n", self.text))

    def part_at(self, offset: int, *, at_end: bool = False) -> tuple[int, int]:
        """The part holding an offset, and the offset within it. An offset
        between two parts is the end of the first only if asked."""
        start = 0
        for index, (_, _, _, length) in enumerate(self.parts):
            last = index == len(self.parts) - 1
            if offset < start + length or last or (at_end and offset == start + length):
                require(
                    0 <= offset - start <= length,
                    f"Place between the paragraphs of {self.reference}",
                )
                return index, offset - start
            start += length + 1
        raise AssertionError("A verse has at least one part")


def _noted(content: usj.Content, at: int, found: list[tuple[int, usj.Node]]) -> int:
    for item in content:
        if isinstance(item, str):
            at += len(item)
        elif item["type"] == "note":
            found.append((at, item))
        elif "content" in item:
            at = _noted(item["content"], at, found)
    return at


def verses(doc: usj.Document) -> dict[str, Verse]:
    """Every verse of a document, by "chapter:verse", in order.

    What stands between one verse number and the next is the verse's, a
    heading set within it included. A paragraph that holds nothing of the
    verse is no part of it: a blank line, or the paragraph the next verse
    opens.
    """
    result: dict[str, Verse] = {}
    chapter: str | None = None
    reference: str | None = None
    parts: list[tuple[int, int, int]] = []

    def hold(block: int, start: int, end: int) -> None:
        # A verse whose number closes its paragraph still stands there.
        if reference is not None and (end > start or not parts):
            parts.append((block, start, end))

    def close() -> None:
        if reference is None:
            return
        require(reference not in result, f"Duplicate verse: {reference}")
        texts: list[str] = []
        notes: list[tuple[int, usj.Node]] = []
        offset = 0
        for block, lo, hi in parts:
            items = doc["content"][block]["content"][lo:hi]
            _noted(items, offset, notes)
            texts.append(usj.text_of(items))
            offset += len(texts[-1]) + 1
        result[reference] = Verse(
            reference,
            tuple((*part, len(text)) for part, text in zip(parts, texts)),
            "\n".join(texts),
            tuple(notes),
        )

    for index, block in enumerate(doc["content"]):
        if block["type"] == "chapter":
            close()
            chapter, reference, parts = block["number"], None, []
        elif block["type"] == "para":
            start = 0
            for at, item in enumerate(block["content"]):
                if usj.is_type(item, "verse"):
                    hold(index, start, at)
                    close()
                    require(chapter is not None, "Verse before a chapter")
                    reference, parts = f"{chapter}:{item['number']}", []
                    start = at + 1
            hold(index, start, len(block["content"]))
    close()
    return result


def heads(doc: usj.Document) -> dict[str, list[usj.Node]]:
    """What stands before each chapter's first verse, by chapter: its
    paragraphs, the one that holds the verse as far as its number."""
    result: dict[str, list[usj.Node]] = {}
    chapter: str | None = None
    for block in doc["content"]:
        if block["type"] == "chapter":
            chapter = block["number"]
            result[chapter] = []
        elif chapter is not None and block["type"] == "para":
            content = block["content"]
            first = next(
                (i for i, item in enumerate(content) if usj.is_type(item, "verse")),
                None,
            )
            result[chapter].append({**block, "content": content[:first]})
            if first is not None:
                chapter = None
    return result


def edited(
    doc: usj.Document, changes: Iterable[tuple[Verse, int, int, usj.Content]]
) -> usj.Document:
    """The document with changes made to its verses' words.

    A change is (verse, start, end, content): the words from start to end, by
    their offsets in the verse, give way to the content. A change of no words
    is an insertion, and stands after the notes already at its place; those
    at one place stand in the order given.
    """
    by_part: dict[tuple[int, int, int], list[tuple[int, int, int, usj.Content]]] = {}
    for order, (verse, start, end, content) in enumerate(changes):
        index, local = verse.part_at(start, at_end=start == end)
        require(
            end == start or verse.part_at(end, at_end=True)[0] == index,
            f"Change across the paragraphs of {verse.reference}",
        )
        block, lo, hi, _ = verse.parts[index]
        by_part.setdefault((block, lo, hi), []).append(
            (local, local + end - start, order, content)
        )
    blocks = list(doc["content"])
    # From the end of each paragraph, so that earlier places hold.
    for (block, lo, hi), listed in sorted(by_part.items(), reverse=True):
        content = blocks[block]["content"]
        items = content[lo:hi]
        floor = None
        for start, end, _, new in sorted(listed, key=lambda c: (-c[0], c[2])):
            require(
                floor is None or end <= floor,
                f"Overlapping changes in {usj.book_code(doc)}",
            )
            if start == end:
                items = usj.inserted(items, start, new)
            else:
                items = usj.replaced(items, start, end, new)
                floor = start
        blocks[block] = {
            **blocks[block],
            "content": usj.joined(content[:lo], items, content[hi:]),
        }
    return usj.with_blocks(doc, blocks)


def rewritten(
    doc: usj.Document, changes: Iterable[tuple[Verse, int, int, str]]
) -> usj.Document:
    """The document with stretches of its verses' words rewritten in place,
    each in the styles its words stood in: a change is (verse, start, end,
    words), by the verse's offsets."""
    by_part: dict[tuple[int, int, int], list[tuple[int, int, str]]] = {}
    for verse, start, end, words in changes:
        # Words only added stand at the end of the paragraph they follow.
        index, local = verse.part_at(start, at_end=start == end)
        require(
            verse.part_at(end, at_end=True)[0] == index,
            f"Change across the paragraphs of {verse.reference}",
        )
        block, lo, hi, _ = verse.parts[index]
        by_part.setdefault((block, lo, hi), []).append(
            (local, local + end - start, words)
        )
    blocks = list(doc["content"])
    # From the end of each paragraph, so that earlier parts stay in place: a
    # style left without words goes with them.
    for (block, lo, hi), edits in sorted(by_part.items(), reverse=True):
        content = blocks[block]["content"]
        blocks[block] = {
            **blocks[block],
            "content": [
                *content[:lo],
                *usj.substituted(content[lo:hi], edits),
                *content[hi:],
            ],
        }
    return usj.with_blocks(doc, blocks)


def map_notes(doc: usj.Document, change: usj.Change) -> usj.Document:
    """The document with each note replaced by what change makes of it: a
    note, a list of content, or None to drop it."""

    def visit(item: usj.Node) -> usj.Node | usj.Content | None:
        return change(item) if item["type"] == "note" else item

    return usj.with_blocks(
        doc,
        [
            (
                {**block, "content": usj.mapped(block["content"], visit)}
                if block["type"] == "para"
                else block
            )
            for block in doc["content"]
        ],
    )
