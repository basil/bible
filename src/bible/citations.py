"""The citations in the edition's notes and front and back matter, read as
each source writes them (edition/citations.json).

Brenton writes "Rom. 4. 7,8", the margin of 1611 "Mat. 18.28", Brenton's
preface "Gen. xlvii. 31", and each names the books its own way: Brenton's
"1 Kings" is the First Book of Kingdoms, and the King James Bible's the
Third. A dialect is a source's way of writing: its names for the books, its
numerals and stops, and the numbering it cites by. A citation is read once,
where its source is read, into the books, chapters and verses of this
edition; what prints is written from those.

The grammar reads what is regular. What isn't is decided in the file, each
decision with its reason: a citation by another numbering than its source's,
one that names no verse to be found, figures that are no citation. Nothing
that looks like a citation goes unread, and no decision unused.
"""

import functools
import re
import string
from dataclasses import dataclass

from bible import paths, versification
from bible.checks import require
from bible.files import read_json
from bible.references import (
    EDITION,
    VERSE_LABEL,
    Passage,
    Verse,
    parse_passages,
    roman,
)

DATA = read_json(paths.EDITION_DIR / "citations.json")
# How a source may number what it cites: as Brenton does, which the edition
# relabels in places; as the King James Bible does; as the Hebrew does, whose
# psalms are the King James Bible's; or by Brenton's chapter and the King James
# Bible's verse, as Brenton cites a psalm whose title he counts.
NUMBERINGS = {"brenton", "kjv", "hebrew", "kjv-verses"}
# What a decision may say, by what it decides.
DECISIONS = {
    "not_a_citation": {"source", "not_a_citation", "why"},
    "unprinted": {"source", "unprinted", "print", "why"},
    "numbering": {"source", "numbering", "why"},
    "passages": {"source", "passages", "print", "relative", "why"},
}
NUMERALS = {
    "arabic": r"\d+",
    "roman": r"[IVXLC]+",
    "roman-lower": r"[ivxlc]+",
    # Brenton's preface numbers chapters in Roman, and its notes in Arabic.
    "either": r"\d+|[ivxlc]+",
}
# What prints nothing of a paragraph's own words: a note's origin, the label of
# a verse that a supplied passage prints, and the markers, each of which takes
# the space after it unless it closes a span.
UNPRINTED = re.compile(r"\\(?:fr|xo) \S+ ?|\\vp [^\\]*\\vp\*|\\\+?[\w-]+(?:\*| ?)")
OPENING = re.compile(r"\\(\+?[\w-]+) ?")
CLOSING = re.compile(r"\\(\+?[\w-]+)\*")
# One verse, a range, or a list of either: "7", "6-9", "7,8", "10,12-14".
RANGE = r"\d+(?:\s?(?:[-–]|\bto\b)\s?\d+)?"
VERSES = rf"{RANGE}(?:,\s?{RANGE})*"
# The words by which a note names a verse or chapter of its own book, which
# a stop or a space parts from the number: "children" names no chapter 49.
VERSE_WORD = r"(?:[Vv]erses?|[Vv]er|[Vv]v|[Vv])(?:\.\s?|\s)"
CHAPTER_WORD = r"(?:[Cc]hapter|[Cc]hap|[Cc]h)(?:\.\s?|\s)"
# What a citation looks like, whatever its dialect: figures on either side of
# a stop or colon, or a word for a verse or chapter before a figure.
SHAPE = re.compile(
    rf"(?<![\w.])(?:\d+|[ivxlc]+|[IVXLC]+)(?:\.\s?|:)\d+"
    rf"|(?<![\w.])(?:{VERSE_WORD}|{CHAPTER_WORD})\d+"
)


@dataclass(frozen=True)
class Item:
    """A chapter, or a stretch of its verses, that a citation names."""

    chapter: int
    first: int | None = None
    last: int | None = None
    letter: str = ""

    def passage(self, book):
        """The item's verses, if it names any."""
        if self.first is None:
            return None
        return Passage(
            Verse(book, self.chapter, self.first, self.letter),
            Verse(book, self.chapter, self.last, self.letter),
        )


@dataclass(frozen=True)
class Citation:
    """A citation as its source writes it, and what it names in the edition."""

    start: int
    end: int
    source: str
    book: str
    # Runs of items: those of a run are of one chapter, as "4:7, 8".
    items: tuple
    numbering: str
    # What it names in other books, where a decision reads several as one.
    others: tuple = ()
    # A citation of the note's own book names only a "verse" or "chapter".
    relative: str | None = None
    # What prints, where a decision says, instead of what the items would.
    printed: str | None = None
    # The source's name for the book, where the dialect's grammar read it.
    name: str | None = None

    @property
    def targets(self):
        """What the citation names, book by book."""
        return ((self.book, self.items), *self.others)

    @property
    def passages(self):
        return [
            passage
            for book, runs in self.targets
            for run in runs
            for item in run
            if (passage := item.passage(book))
        ]

    @property
    def verses(self):
        return [verse for passage in self.passages for verse in passage.verses]


@dataclass(frozen=True)
class Dialect:
    name: str
    numbering: str
    books: dict
    numerals: str
    # The stop between a chapter and its verses, as a pattern.
    chapter_verse: str

    @functools.cached_property
    def pattern(self):
        # A dialect of no names reads no book: "(?!)" matches nothing.
        names = (
            "|".join(
                re.escape(name).replace(r"\ ", r"\s")
                for name in sorted(self.books, key=len, reverse=True)
            )
            or "(?!)"
        )
        chapter = rf"(?:{NUMERALS[self.numerals]})(?![a-z])"
        item = rf"{chapter}(?:{self.chapter_verse}{VERSES}|\.?\s?ult\b)?"
        # An item after a semicolon is of the same book, unless a book's name
        # stands there: "Rom. 9. 12; 1 Cor. 2. 9".
        more = rf"(?:;\s?(?:and\s|also\s)?(?!(?:{names})\.?\s){item})*"
        # A run of dashes is no range: what is cited ends before no "-9".
        end = r"(?![-–]\s?\d)"
        return re.compile(
            rf"(?<![\w.])(?P<book>{names})(?P<stop>\.?)(?!\w)\s*"
            rf"(?P<cited>{item}{more}){end}"
            rf"|(?<![\w.])(?P<chapter>{CHAPTER_WORD})(?P<within>{item}{more}){end}"
            rf"|(?<![\w.])(?P<verse>{VERSE_WORD})(?P<verses>{VERSES}){end}"
        )

    def number(self, numeral):
        return int(numeral) if numeral.isdigit() else roman(numeral.upper())


def dialect(name):
    """A source's way of writing citations, or that of one that writes none."""
    if name is None:
        return Dialect("none", "brenton", {}, "arabic", r"\.\s?")
    found = DATA["dialects"][name]
    require(
        found.get("numbering") in NUMBERINGS and found.get("numerals") in NUMERALS,
        f"Dialect without its numbering or numerals: {name}",
    )
    return Dialect(
        name,
        found["numbering"],
        found["books"],
        found["numerals"],
        found["chapter_verse"],
    )


def _ranges(verses):
    """The stretches a list of verses names, as (first, last)."""
    found = []
    for stretch in re.split(r",\s?", verses):
        first, *last = re.split(r"\s?(?:[-–]|\bto\b)\s?", stretch)
        found.append((int(first), int(last[0]) if last else int(first)))
    return found


def _items(cited, tongue, last_verse):
    """The runs of items a citation's figures name, chapter by chapter."""
    found = []
    for part in re.split(r";\s?(?:and\s|also\s)?", cited):
        match = re.fullmatch(
            rf"(?P<chapter>(?:{NUMERALS[tongue.numerals]}))(?![a-z])"
            rf"(?:{tongue.chapter_verse}(?P<verses>{VERSES})|(?P<ult>\.?\s?ult))?",
            part,
        )
        chapter = tongue.number(match["chapter"])
        if match["verses"]:
            stretches = _ranges(match["verses"])
        elif match["ult"]:
            # The last verse of the chapter, which the Bible knows.
            stretches = [(last_verse(chapter),) * 2]
        else:
            stretches = [(None, None)]
        found.append(tuple(Item(chapter, first, last) for first, last in stretches))
    return tuple(found)


def _carried(book, passage):
    """A King James passage's items in the edition, which may be in more
    than one place."""
    found = versification.edition_passages(passage)
    require(found, f"Verses the edition lacks: {passage}")
    return [
        Item(p.first.chapter, p.first.number, p.last.number, p.first.letter)
        for p in found
    ]


def _kjv_chapter(book, chapter):
    """The King James chapter that holds an edition chapter's verses."""
    labels = versification.verses(f"{book} {chapter}:1-3")
    found = [kjv for verse in labels for kjv in _counterparts(verse)]
    require(found, f"Chapter the King James Bible lacks: {book} {chapter}")
    return next(v for v in found if v.number != versification.TITLE).chapter


def _counterparts(verse):
    try:
        return versification.to_kjv(verse)
    except RuntimeError:
        return ()


def _edition(book, items, numbering):
    """A book's items as the edition numbers them, from a source's numbering.

    Brenton's verse is the edition's unless the edition relabels it. The King
    James Bible's is carried verse by verse, and may come to rest in more than
    one place, or none.
    """
    if numbering == "brenton":
        relabelled = versification.relabelled()
        runs = []
        for run in items:
            moved = []
            for item in run:
                if item.first is None:
                    moved.append(item)
                    continue
                ends = [
                    relabelled.get(
                        Verse(book, item.chapter, n), Verse(book, item.chapter, n)
                    )
                    for n in (item.first, item.last)
                ]
                require(
                    ends[0].chapter == ends[1].chapter,
                    f"Citation across a relabelled chapter: {book} {item}",
                )
                moved.append(Item(ends[0].chapter, ends[0].number, ends[1].number))
            runs.append(tuple(moved))
        return book, tuple(runs)
    if numbering == "kjv-verses":
        ours, theirs = book, versification.kjv_book(book)
    elif book not in versification.kjv_books():
        # A book the King James Old Testament lacks is numbered as it stands.
        return book, items
    else:
        ours, theirs = versification.kjv_books()[book], book
    runs = []
    for run in items:
        moved = []
        for item in run:
            chapter = item.chapter
            if numbering == "kjv-verses":
                chapter = _kjv_chapter(ours, chapter)
            if item.first is None:
                # A chapter is where its first verse is.
                found = versification.from_kjv(Verse(theirs, chapter, 1))
                require(found, f"Chapter the edition lacks: {theirs} {chapter}")
                moved.append(Item(found[0].chapter))
                continue
            require(
                numbering != "hebrew",
                f"Verses by the Hebrew's numbering: {book} {item}",
            )
            moved += _carried(
                ours,
                Passage(
                    Verse(theirs, chapter, item.first),
                    Verse(theirs, chapter, item.last),
                ),
            )
        # Verses carried into another chapter open a run of their own.
        for n, item in enumerate(moved):
            if n and runs[-1][-1].chapter == item.chapter:
                runs[-1] = (*runs[-1], item)
            else:
                runs.append((item,))
    return ours, tuple(runs)


class Names(string.Formatter):
    """What a decision or a change of name prints, with the edition's names
    for the books it names by their codes: "{ISA} 2:6", or in capitals,
    "{ISA:upper} 2:6"."""

    def format_field(self, value, spec):
        return value.upper() if spec == "upper" else super().format_field(value, spec)


def named(words, names):
    return Names().vformat(words, (), names)


def decisions(key):
    """The decisions on a note's citations, in the file's order."""
    found = DATA["decisions"].get(key, [])
    return found if isinstance(found, list) else [found]


def unit_decisions(unit, plain):
    """The decisions on a paragraph of a unit without verses, by key.

    Such a decision is keyed by its unit and the words it decides, as "XXB
    Psalm iv. 4", which must be the unit's once.
    """
    found = {}
    for key, decision in DATA["decisions"].items():
        code, _, words = key.partition(" ")
        if code == unit and not re.fullmatch(rf"\d+:{VERSE_LABEL}.*", words):
            source = decision.get("source", words)
            if source in plain:
                found[key] = {**decision, "source": source}
    return found


def _decided(decision, plain, tongue, home, key, inventory):
    """Where a decision's words stand, and its citation, if it decides that
    there is one."""
    source = decision.get("source", "")
    require(
        decision.get("why") and plain.count(source) == 1,
        f"Citation decision without a reason, or not found once: {key} ({source})",
    )
    kinds = [kind for kind in DECISIONS if decision.get(kind)]
    require(
        len(kinds) == 1 and decision.keys() <= DECISIONS[kinds[0]],
        f"Citation decision that decides nothing, or too much: {key} ({source})",
    )
    start, (kind,) = plain.index(source), kinds
    end = start + len(source)
    if kind == "not_a_citation":
        return start, end, None
    if kind == "unprinted":
        # What the edition doesn't print, as a verse its Greek lacks.
        require(decision.get("print"), f"Citation decision prints nothing: {key}")
        book, items, relative = home.book, (), None
    elif kind == "numbering":
        match = tongue.pattern.fullmatch(source)
        require(
            match is not None
            and match["book"]
            and decision["numbering"] in NUMBERINGS - {tongue.numbering},
            f"Citation decision of no other numbering: {key} ({source})",
        )
        items = _items(
            match["cited"],
            tongue,
            lambda chapter: _last_verse(inventory, book, chapter),
        )
        book, items = _edition(
            tongue.books[match["book"]], items, decision["numbering"]
        )
        relative = None
    else:
        require(decision.get("print"), f"Citation decision prints nothing: {key}")
        named = []
        for passage in parse_passages(decision["passages"]):
            first, last = passage.first, passage.last
            item = Item(first.chapter, first.number, last.number, first.letter)
            if named and named[-1][0] == first.book:
                named[-1][1].append((item,))
            else:
                named.append((first.book, [(item,)]))
        (book, items), *others = ((book, tuple(runs)) for book, runs in named)
        relative = decision.get("relative")
    return (
        start,
        end,
        Citation(
            start,
            end,
            source,
            book,
            items,
            decision.get("numbering", tongue.numbering),
            tuple(others) if kind == "passages" else (),
            relative,
            decision.get("print"),
        ),
    )


def _last_verse(inventory, book, chapter):
    """The last verse of a chapter, which a citation names as "ult."."""
    labels = inventory.get(book, {}).get(str(chapter))
    require(labels, f"No such chapter: {book} {chapter}")
    return int(re.match(r"\d+", labels[-1])[0])


def missing(citation, inventory):
    """What a citation names that the edition doesn't print."""
    found = []
    for book, runs in citation.targets:
        chapters = inventory.get(book, {})
        for item in (item for run in runs for item in run):
            labels = chapters.get(str(item.chapter))
            if labels is None:
                found.append(f"{book} {item.chapter}")
            elif item.first is not None:
                found += [
                    f"{book} {item.chapter}:{number}{item.letter}"
                    for number in range(item.first, item.last + 1)
                    if f"{number}{item.letter}" not in labels
                ]
    return found


def scan(plain, tongue, home, key, inventory, decided=None, before=None):
    """The citations in a stretch of plain text, in order.

    home is the verse the text stands at, whose book and chapter a citation
    names that names none. Where the text stands at no verse, they are those
    of the citation before it, in the text or before the text. Whatever a
    citation names must be among the edition's chapters and verses, the
    inventory. The decisions are the note's, by its key, unless they are
    given.
    """
    taken, found = [], []
    for decision in decisions(key) if decided is None else decided:
        start, end, citation = _decided(
            decision, plain, tongue, home or Verse("", 0, 0), key, inventory
        )
        require(
            not any(s < end and start < e for s, e in taken),
            f"Citation decisions that overlap: {key}",
        )
        taken.append((start, end))
        if citation:
            found.append(citation)
    standing = home or before
    for match in tongue.pattern.finditer(plain):
        earlier = [
            c for c in found if c.end <= match.start() and c.items and not c.relative
        ]
        if home is None and earlier:
            last = max(earlier, key=lambda citation: citation.end)
            standing = Verse(last.book, last.items[-1][-1].chapter, 1)
        if any(s < match.end() and match.start() < e for s, e in taken):
            continue
        require(
            match["book"] or standing is not None,
            f"Citation of no book: {key} ({match[0]})",
        )
        relative = None
        if match["book"]:
            book, numbering = tongue.books[match["book"]], tongue.numbering
            cited = match["cited"]
        elif match["chapter"]:
            book, numbering, relative = standing.book, "edition", "chapter"
            cited = match["within"]
        else:
            book, numbering, relative = standing.book, "edition", "verse"
            cited = None
        if cited is not None:
            items = _items(
                cited, tongue, lambda chapter: _last_verse(inventory, book, chapter)
            )
        else:
            items = (
                tuple(
                    Item(standing.chapter, first, last)
                    for first, last in _ranges(match["verses"])
                ),
            )
        if numbering != "edition":
            book, items = _edition(book, items, numbering)
        found.append(
            Citation(
                match.start(),
                match.end(),
                match[0],
                book,
                items,
                tongue.numbering,
                relative=relative,
                name=match["book"],
            )
        )
        taken.append((match.start(), match.end()))
    unread = [
        match[0]
        for match in SHAPE.finditer(plain)
        if not any(s <= match.start() and match.end() <= e for s, e in taken)
    ]
    require(not unread, f"Citation that can't be read: {key} ({'; '.join(unread)})")
    for citation in found:
        lacking = missing(citation, inventory)
        require(
            not lacking,
            f"Citation of what the edition doesn't print: {key} "
            f"({citation.source}: {', '.join(lacking)})",
        )
    return sorted(found, key=lambda citation: citation.start)


def printed(citation, books, style=EDITION):
    """A citation as the edition prints it: under the edition's name for the
    book, or as a verse or chapter of the note's own book, which it names as
    its source does, by no name."""
    if citation.printed is not None:
        # A decision names the books by their codes, and the edition's names
        # for them print.
        names = {
            book: books.name(book, [item.chapter for run in runs for item in run])
            for book, runs in citation.targets
        }
        return named(citation.printed, names)
    chapters = [item.chapter for run in citation.items for item in run]
    verses = [item for run in citation.items for item in run if item.first is not None]
    if citation.relative == "verse":
        (run,) = citation.items
        word = "verse" if len(run) == 1 and run[0].first == run[0].last else "verses"
        body = style.verses.join(
            style.stretch(item.first, item.last, item.letter) for item in run
        )
    else:
        runs = []
        for run in citation.items:
            chapter = str(run[0].chapter)
            if run[0].first is not None:
                chapter += style.chapter_verse + style.verses.join(
                    style.stretch(item.first, item.last, item.letter) for item in run
                )
            runs.append(chapter)
        body = style.passages.join(runs)
        if citation.relative == "chapter":
            word = "chapter" if verses or len(chapters) == 1 else "chapters"
        else:
            return f"{books.name(citation.book, chapters)} {body}"
    # A note that opens with the word keeps its capital.
    if citation.source[0].isupper():
        word = word.capitalize()
    return f"{word} {body}"


def normalized(pieces, found, books):
    """A note's pieces with each citation as the edition prints it, as a
    reference of its own.

    A citation that names nothing the edition prints is no reference for a
    reader to follow, and stays among the words it stands in. The pieces
    with their citations as the source has them must be the pieces given.
    """
    plain = "".join(text for _, text in pieces)
    result, offset, cursor, joined = [], 0, 0, False
    pending = sorted(found, key=lambda citation: citation.start)
    for kind, text in pieces:
        end = offset + len(text)
        while cursor < end:
            citation = next((c for c in pending if c.end > cursor), None)
            if citation is None or citation.start >= end:
                stop = end
            elif citation.start > cursor:
                stop = citation.start
            else:
                stop = None
            if stop is not None:
                if joined and result[-1][0] == kind:
                    result[-1] = (kind, result[-1][1] + plain[cursor:stop])
                else:
                    result.append((kind, plain[cursor:stop]))
                cursor = stop
            elif citation.items:
                result.append(("xt", printed(citation, books)))
                cursor = citation.end
            else:
                # Among its words: of their kind, and not apart from them.
                words = printed(citation, books)
                if result and result[-1][0] == kind and cursor > offset:
                    result[-1] = (kind, result[-1][1] + words)
                else:
                    result.append((kind, words))
                cursor = citation.end
                joined = True
                continue
            joined = False
        offset = end
    restored, at = "", 0
    for kind, text in result:
        restored += text
    for citation in pending:
        at = restored.index(printed(citation, books), at)
        restored = (
            restored[:at]
            + citation.source
            + restored[at + len(printed(citation, books)) :]
        )
        at += len(citation.source)
    require(restored == plain, f"Citations that don't restore their note: {plain}")
    return [(kind, text) for kind, text in result if text]


def renamed(unit, text, books):
    """A unit's text with the edition's names for what its source names
    otherwise, where that is no citation: a heading, or words that were true
    of another printing. Each change gives its reason, and is met once."""
    changes = []
    for change in DATA["names"].get(unit, []):
        old, new = change.get("from"), change.get("to")
        require(
            change.get("why") and old and new is not None,
            f"Change of name without its words or reason: {unit} ({old})",
        )
        words = re.compile(rf"(?<!\w){re.escape(old)}(?!\w)")
        require(
            len(words.findall(text)) == 1,
            f"Change of name not met once: {unit} ({old})",
        )
        printed_as = named(new, books.names)
        text = words.sub(lambda match: printed_as, text)
        changes.append({"from": old, "to": printed_as})
    return text, changes


def printable(usfm):
    """A paragraph's printed characters, and where each stands in its USFM."""
    offsets, last = [], 0
    for match in UNPRINTED.finditer(usfm):
        offsets += range(last, match.start())
        last = match.end()
    offsets += range(last, len(usfm))
    return "".join(usfm[i] for i in offsets), offsets


def rewritten(usfm, tongue, home, key, inventory, books, decided=None, before=None):
    """A paragraph of USFM with each citation as the edition prints it, and
    the citations read.

    Markup within a citation goes with the source's way of writing it, as the
    italic of "\\it John\\it* 5. 39"; a span that the citation opens or closes
    goes whole, so that none is left open.
    """
    plain, offsets = printable(usfm)
    found = scan(plain, tongue, home, key, inventory, decided, before)
    for citation in reversed(found):
        start, end = offsets[citation.start], offsets[citation.end - 1] + 1
        inside = usfm[start:end]
        opened = [m[1] for m in OPENING.finditer(CLOSING.sub("", inside))]
        closed = [m[1] for m in CLOSING.finditer(inside)]
        for marker in closed:
            if marker in opened:
                opened.remove(marker)
                continue
            # The span opens just before the citation.
            opening = re.search(rf"\\{re.escape(marker)} ?$", usfm[:start])
            require(
                opening is not None,
                f"Citation across markup: {key} ({citation.source})",
            )
            start = opening.start()
        for marker in opened:
            closing = re.match(rf"\\{re.escape(marker)}\*", usfm[end:])
            require(
                closing is not None,
                f"Citation across markup: {key} ({citation.source})",
            )
            end += closing.end()
        usfm = usfm[:start] + printed(citation, books) + usfm[end:]
    return usfm, found


def unused(read):
    """What the file has that nothing read has met: the keys of its
    decisions, and each dialect's names for books, by dialect.

    read is the log of every unit's citations, as read_citations writes it.
    """
    decided = {key for entry in read for key in entry["decided"]}
    named = {
        (entry["dialect"], citation["name"])
        for entry in read
        for citation in entry["citations"]
    }
    return sorted(set(DATA["decisions"]) - decided), sorted(
        (name, book)
        for name, tongue in DATA["dialects"].items()
        for book in tongue["books"]
        if (name, book) not in named
    )
