"""STEPBible's table of versification traditions (TVTMS), as a second opinion
on where a Bible's verses stand in the King James Bible.

A row of its expanded table gives a verse's standard reference, which in the
Old Testament is the King James Bible's, under tests of the Bible it is read
against: which verses exist, which one ends its chapter, which of two is the
longer. The rows whose tests a Bible passes are the table's account of it.

The table seeds edition/versification.json and is compared with it. It isn't
the authority: its tests weren't written for eBible's Brenton, and where its
account and the words of the two translations disagree, the words decide.
"""

import collections
import functools
import re
from dataclasses import dataclass

from bible import paths
from bible.references import Verse
from bible.sources import SOURCES, pinned_bytes
from bible.usfm import chapter_parts, verse_spans, words_of

SOURCE = SOURCES["versification"]
# A reference as the table writes it, as "Gen.31:55", "Psa.50:Title", or the
# part of a verse "Gen.3:1!a". Esther's Greek additions are chapters A to F.
REFERENCE = re.compile(
    r"(?:(?P<book>[1-4]?[A-Za-z][A-Za-z0-9]{1,2})\.)?"
    r"(?P<chapter>\d+|[A-F]):(?P<verse>\d+|Title)(?:!(?P<part>\w+))?"
    r"(?:-(?:(?P<to_chapter>\d+):)?(?P<last>\d+))?"
)
# A test of one verse, its lettered part ("1Ki.2:35.1" is 2:35a), or the words
# before a chapter's first verse.
TEST = re.compile(
    r"(?P<book>[1-4]?[A-Za-z][A-Za-z0-9]{1,2})\.(?P<chapter>\d+|[A-F]):"
    r"(?P<verse>\d+|TextBeforeV1)(?:\.(?P<part>\d+))?"
    r"=(?P<is>Exist|NotExist|Last)"
)
# A test of lengths, as "Mal.3:23*2>Mal.3:22+Mal.3:24".
TERM = re.compile(r"([1-4]?[A-Za-z][A-Za-z0-9]{1,2})\.(\d+):(\d+)(?:\*(\d+))?")
# A psalm's title stands before its first verse, as its verse 0.
TITLE = 0


@dataclass(frozen=True)
class Row:
    tradition: str
    source: tuple
    standard: tuple
    action: str
    tests: str


def _verses(text, book=None):
    """The verses a reference, range or list names, as (book, chapter, verse,
    part), or None if it can't be read."""
    verses = []
    for item in re.split(r"\s*;\s*", text.strip()):
        match = REFERENCE.fullmatch(item)
        if match is None or not (match["book"] or book):
            return None
        book = (match["book"] or book).upper()
        chapter = match["chapter"]
        first = TITLE if match["verse"] == "Title" else int(match["verse"])
        if match["to_chapter"]:
            # A range across chapters names its ends; what lies between is
            # the Bible's to say.
            verses += [
                (book, chapter, first, ""),
                (book, match["to_chapter"], int(match["last"]), ""),
            ]
            continue
        last = int(match["last"] or first)
        part = match["part"] or ""
        verses += [(book, chapter, verse, part) for verse in range(first, last + 1)]
    return verses


@functools.cache
def rows():
    """The expanded table's rows, and how many of them couldn't be read."""
    text = pinned_bytes(SOURCE["file"], SOURCE["sha256"]).decode("utf-8-sig")
    lines = text.replace("\r\n", "\n").split("\n")
    start = lines.index(next(l for l in lines if l.startswith("#DataStart(Expanded)")))
    end = lines.index(next(l for l in lines if l.startswith("#DataEnd(Expanded)")))
    found, unread = [], []
    for line in lines[start + 2 : end]:
        cells = [cell.strip() for cell in line.split("\t")]
        if len(cells) < 9 or not cells[1] or cells[1].startswith("'"):
            continue
        source, standard = _verses(cells[1]), _verses(cells[2])
        if not source or not standard:
            unread.append(line)
            continue
        found.append(Row(cells[0], tuple(source), tuple(standard), cells[3], cells[8]))
    return found, unread


class Bible:
    """What the table's tests ask of a Bible: which verses it has, and how
    long each is. Books are named as the table names them, in capitals."""

    def __init__(self, scripture):
        self.length = {}
        self.last = {}
        self.titled = set()
        for book, text in scripture.items():
            text = re.sub(r"\\([fx]) .*?\\\1\*", "", text, flags=re.S)
            for chapter in chapter_parts(text)[1]:
                number, head = re.match(
                    r"\\c (\d+)(.*?)(?=\\v |\Z)", chapter, re.S
                ).groups()
                if words_of(head):
                    self.titled.add((book, number))
            for reference, start, end in verse_spans(text):
                chapter, label = reference.split(":")
                self.length[book, chapter, label] = len(words_of(text[start:end]))
                self.last[book, chapter] = int(re.match(r"\d+", label)[0])

    def passes(self, tests):
        """Whether every test holds, or None if one can't be read."""
        results = [
            self._holds(test.strip()) for test in tests.split("&") if test.strip()
        ]
        return None if None in results else all(results)

    def _holds(self, test):
        if match := TEST.fullmatch(test):
            book, chapter = match["book"].upper(), match["chapter"]
            if match["verse"] == "TextBeforeV1":
                return ((book, chapter) in self.titled) == (match["is"] == "Exist")
            label = match["verse"]
            if match["is"] == "Last":
                return self.last.get((book, chapter)) == int(label)
            if match["part"]:
                label += chr(ord("a") + int(match["part"]) - 1)
            return ((book, chapter, label) in self.length) == (match["is"] == "Exist")
        sides = re.split(r"([<>])", test)
        if len(sides) != 3:
            return None
        lengths = [self._sum(side) for side in (sides[0], sides[2])]
        if None in lengths:
            return None
        return lengths[0] < lengths[1] if sides[1] == "<" else lengths[0] > lengths[1]

    def _sum(self, side):
        total = 0
        for term in side.split("+"):
            match = TERM.fullmatch(term.strip())
            if match is None:
                return None
            book, chapter, verse, times = match.groups()
            # A verse the Bible lacks has no length to compare.
            total += self.length.get((book.upper(), chapter, verse), 0) * int(
                times or 1
            )
        return total


def account(bible, books):
    """The table's account of a Bible's books: each verse's standard verses,
    by every row it passes, as {verse: [(standard verses, row), ...]}.

    A row about a part of a verse, as "1Ki.2:35!a", is about the lettered
    verse if the Bible letters it, and otherwise about the verse it is part
    of. Books map the Bible's codes to the table's names for them.
    """
    found, _ = rows()
    names = {name: code for code, listed in books.items() for name in listed}
    result = collections.defaultdict(list)
    for row in found:
        if len(row.source) != 1 or row.source[0][0] not in names:
            continue
        book, chapter, number, part = row.source[0]
        if number == TITLE or not chapter.isdigit() or not bible.passes(row.tests):
            continue
        lettered = (book, chapter, f"{number}{part}") in bible.length
        verse = Verse(
            names[book],
            int(chapter),
            number,
            part if lettered and part.isalpha() and len(part) == 1 else "",
        )
        standard = tuple(
            Verse(b, int(c), v) for b, c, v, _ in row.standard if c.isdigit()
        )
        result[verse].append((standard, row))
    return dict(result)
