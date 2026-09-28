"""A verse and a passage, as the edition's files write them ("ISA 40:3-5") and
as its pages print them ("Esaias 40:3–5").

A verse may carry the letter by which Brenton sets apart a Septuagint
addition, as Proverbs 22:8a, but a lettered verse is never part of a range.
A passage keeps to one chapter; nothing guesses where a chapter ends.
"""

import itertools
import re
from dataclasses import dataclass

from bible.checks import require

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
    def label(self):
        """The verse within its book, as "22:8a"."""
        return f"{self.chapter}:{self.number}{self.letter}"

    def __str__(self):
        return f"{self.book} {self.label}"


@dataclass(frozen=True)
class Passage:
    first: Verse
    last: Verse

    def __post_init__(self):
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

    def __str__(self):
        if self.first == self.last:
            return str(self.first)
        return f"{self.first}-{self.last.number}{self.last.letter}"

    @property
    def verses(self):
        first = self.first
        return [
            Verse(first.book, first.chapter, number, first.letter)
            for number in range(first.number, self.last.number + 1)
        ]


def parse_passage(text):
    match = PASSAGE.fullmatch(text)
    require(match is not None, f"Malformed passage: {text}")
    book, chapter, first, letter, last = match.groups()
    first = Verse(book, int(chapter), int(first), letter)
    return Passage(
        first, first if last is None else Verse(book, int(chapter), int(last))
    )


def parse_verse(text):
    match = PASSAGE.fullmatch(text)
    require(
        match is not None and match[5] is None, f"Malformed verse reference: {text}"
    )
    return parse_passage(text).first


def parse_passages(text):
    """The passages of a list, as "EXO 20:13-16; DEU 5:17-20"."""
    return [parse_passage(passage) for passage in text.split("; ")]


def verse_at(book, label):
    """A book's verse by its label, as verse_spans names it."""
    return parse_verse(f"{book} {label}")


def runs(verses):
    """Verses as passages, each run of consecutive unlettered verses as one.

    A lettered verse stands alone.
    """
    passages = []
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


def roman(numeral):
    values = [ROMAN[c] for c in numeral]
    return sum(-v if v < w else v for v, w in zip(values, values[1:] + [0]))


class Books:
    """One Bible's books, in its order, under the names its pages print.

    A book of many may have a name for one of them: a psalm of the Psalms.
    """

    def __init__(self, names, one=()):
        self.names = dict(names)
        self.one = dict(one)
        self.order = {code: index for index, code in enumerate(self.names)}

    def name(self, code, chapters=()):
        """A book's name where it is cited: that of one of its chapters, if
        it has such a name and one chapter is cited."""
        require(code in self.names, f"No display name for {code}")
        if code in self.one and len(set(chapters)) == 1:
            return self.one[code]
        return self.names[code]

    def position(self, verse):
        """Where a verse stands in this Bible, a lettered verse after its own."""
        return self.order[verse.book], verse.chapter, verse.number, verse.letter


@dataclass(frozen=True)
class Style:
    """How a reference is punctuated in print."""

    chapter_verse: str = ":"
    range: str = "–"
    verses: str = ", "
    passages: str = "; "

    def stretch(self, first, last, letter=""):
        """A verse, or a range of them: "7", "6–9", "8a"."""
        if first == last:
            return f"{first}{letter}"
        return f"{first}{self.range}{last}"

    def within(self, passage):
        """A passage within its book: "40:3–5"."""
        first, last = passage.first, passage.last
        return (
            f"{first.chapter}{self.chapter_verse}"
            f"{self.stretch(first.number, last.number, first.letter)}"
        )

    def passage(self, passage, books):
        name = books.name(passage.first.book, [passage.first.chapter])
        return f"{name} {self.within(passage)}"

    def listed(self, passages, books):
        """Passages in order, each book named once: "Esaias 8:23; 9:1;
        Matthew 4:15"."""
        printed = []
        for n, passage in enumerate(passages):
            book = passage.first.book
            if n and passages[n - 1].first.book == book:
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
