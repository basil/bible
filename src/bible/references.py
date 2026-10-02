"""A verse and a passage, as the edition's files write them ("ISA 40:3-5") and
as its pages print them ("Esaias 40:3–5").

A verse may carry the letter by which Brenton sets apart a Septuagint
addition, as Proverbs 22:8a, but a lettered verse is never part of a range.
A passage keeps to one chapter; nothing guesses where a chapter ends.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from bible.checks import present, require

# A verse within its chapter, as a verse marker and a note's origin name it.
VERSE_LABEL = r"\d+[a-z]?"
# A verse, or a range of unlettered verses within one chapter.
PASSAGE = re.compile(r"([1-4]?[A-Z]{2,3}) (\d+):(\d+)([a-z]?)(?:-(\d+))?")
ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


@dataclass(frozen=True)
class Verse:
    book: str
    chapter: int
    number: int
    letter: str = ""

    @property
    def label(self) -> str:
        """The verse within its book, as "22:8a"."""
        return f"{self.chapter}:{self.number}{self.letter}"

    def __str__(self) -> str:
        return f"{self.book} {self.label}"


@dataclass(frozen=True)
class Passage:
    first: Verse
    last: Verse

    def __post_init__(self) -> None:
        first, last = self.first, self.last
        require(
            (first.book, first.chapter) == (last.book, last.chapter),
            f"Passage beyond one chapter: {first}-{last}",
        )
        require(
            first == last or not (first.letter or last.letter),
            f"Lettered verse in a range: {self}",
        )
        require(last.number >= first.number, f"Reversed passage: {self}")

    def __str__(self) -> str:
        if self.first == self.last:
            return str(self.first)
        return f"{self.first}-{self.last.number}{self.last.letter}"

    @property
    def verses(self) -> list[Verse]:
        first = self.first
        return [
            Verse(first.book, first.chapter, number, first.letter)
            for number in range(first.number, self.last.number + 1)
        ]


def parse_passage(text: str) -> Passage:
    match = present(PASSAGE.fullmatch(text), f"Malformed passage: {text}")
    book, chapter, first_number, letter, last = match.groups()
    first = Verse(book, int(chapter), int(first_number), letter)
    return Passage(
        first, first if last is None else Verse(book, int(chapter), int(last))
    )


def parse_verse(text: str) -> Verse:
    match = PASSAGE.fullmatch(text)
    require(
        match is not None and match[5] is None, f"Malformed verse reference: {text}"
    )
    return parse_passage(text).first


def parse_passages(text: str) -> list[Passage]:
    """The passages of a list, as "EXO 20:13-16; DEU 5:17-20"."""
    return [parse_passage(passage) for passage in text.split("; ")]


def verse_at(book: str, label: str) -> Verse:
    """A book's verse by its label, as scripture.verses names it."""
    return parse_verse(f"{book} {label}")


def runs(verses: Iterable[Verse]) -> list[Passage]:
    """Verses as passages, each run of consecutive unlettered verses as one.

    A lettered verse stands alone.
    """
    passages: list[Passage] = []
    for verse in verses:
        last = passages[-1].last if passages else None
        if (
            last
            and (last.book, last.chapter) == (verse.book, verse.chapter)
            and not (last.letter or verse.letter)
            and last.number == verse.number - 1
        ):
            passages[-1] = Passage(passages[-1].first, verse)
        else:
            passages.append(Passage(verse, verse))
    return passages


def roman(numeral: str) -> int:
    values = [ROMAN[c] for c in numeral]
    return sum(-v if v < w else v for v, w in zip(values, values[1:] + [0]))


class Books:
    """One Bible's books, in its order, under the names its pages print.

    A book of many may have a name for one of them: a psalm of the Psalms.
    The same books under their citation abbreviations are `abbreviated`:
    these books themselves, if they have none.
    """

    def __init__(
        self,
        names: Mapping[str, str] | Iterable[tuple[str, str]],
        one: Mapping[str, str] | Iterable[tuple[str, str]] = (),
        abbreviated: Books | None = None,
    ) -> None:
        self.names = dict(names)
        self.one = dict(one)
        self.abbreviated = abbreviated or self
        self.order = {code: index for index, code in enumerate(self.names)}

    def name(self, code: str, chapters: Iterable[int] = ()) -> str:
        """A book's name where it is cited: that of one of its chapters, if
        it has such a name and one chapter is cited."""
        require(code in self.names, f"No display name for {code}")
        if code in self.one and len(set(chapters)) == 1:
            return self.one[code]
        return self.names[code]

    def position(self, verse: Verse) -> tuple[int, int, int, str]:
        """Where a verse stands in this Bible, a lettered verse after its own."""
        return self.order[verse.book], verse.chapter, verse.number, verse.letter


@dataclass(frozen=True)
class Style:
    """How a reference is punctuated in print."""

    chapter_verse: str = ":"
    range: str = "–"
    verses: str = ", "
    passages: str = "; "

    def stretch(self, first: int, last: int, letter: str = "") -> str:
        """A verse, or a range of them: "7", "6–9", "8a"."""
        if first == last:
            return f"{first}{letter}"
        return f"{first}{self.range}{last}"

    def within(self, passage: Passage) -> str:
        """A passage within its book: "40:3–5"."""
        first, last = passage.first, passage.last
        return (
            f"{first.chapter}{self.chapter_verse}"
            f"{self.stretch(first.number, last.number, first.letter)}"
        )

    def passage(self, passage: Passage, books: Books) -> str:
        name = books.name(passage.first.book, [passage.first.chapter])
        return f"{name} {self.within(passage)}"

    def listed(self, passages: Sequence[Passage], books: Books) -> str:
        """Passages in order, each book named once, and each chapter once
        where its passages stand together: "Exodus 20:12, 13–17; Deuteronomy
        5:16"."""
        printed: list[str] = []
        for n, passage in enumerate(passages):
            book = passage.first.book
            if n and passages[n - 1].first.book == book:
                if passages[n - 1].first.chapter == passage.first.chapter:
                    printed[-1] += self.verses + self.stretch(
                        passage.first.number, passage.last.number, passage.first.letter
                    )
                    continue
                printed.append(self.within(passage))
                continue
            chapters = [
                p.first.chapter
                for p in itertools.takewhile(
                    lambda p: p.first.book == book, passages[n:]
                )
            ]
            printed.append(f"{books.name(book, chapters)} {self.within(passage)}")
        return self.passages.join(printed)


EDITION = Style()


@dataclass(frozen=True)
class LastVerse:
    """An unresolved source chapter end (historical ``ult.``)."""


LAST_VERSE = LastVerse()


@dataclass(frozen=True)
class Item:
    """A chapter, or a stretch of its verses, that a citation names."""

    chapter: int
    first: int | LastVerse | None = None
    last: int | LastVerse | None = None
    letter: str = ""

    def passage(self, book: str) -> Passage | None:
        """The item's verses, if it names any."""
        if self.first is None:
            return None
        assert isinstance(self.first, int) and isinstance(self.last, int)
        return Passage(
            Verse(book, self.chapter, self.first, self.letter),
            Verse(book, self.chapter, self.last, self.letter),
        )
