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

from __future__ import annotations

import functools
import re
import string
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

import bible.policy
import bible.references
from bible import scripture, versification
from bible.checks import require
from bible.policy_schema import CitationsDecisions
from bible.references import (
    EDITION,
    LAST_VERSE,
    VERSE_LABEL,
    Item,
    LastVerse,
    Passage,
    Style,
    Verse,
    parse_passages,
    roman,
)

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
class Citation:
    """A citation as its source writes it, and what it names in the edition."""

    start: int
    end: int
    source: str
    book: str
    # Runs of items: those of a run are of one chapter, as "4:7, 8".
    items: tuple[tuple[Item, ...], ...]
    numbering: str
    # What it names in other books, where a decision reads several as one.
    others: tuple[tuple[str, tuple[tuple[Item, ...], ...]], ...] = ()
    # A citation of the note's own book names only a "verse" or "chapter".
    relative: str | None = None
    # What prints, where a decision says, instead of what the items would.
    printed: str | None = None
    # The source's name for the book, where the dialect's grammar read it.
    name: str | None = None

    @property
    def targets(self) -> tuple[tuple[str, tuple[tuple[Item, ...], ...]], ...]:
        """What the citation names, book by book."""
        return ((self.book, self.items), *self.others)

    @property
    def passages(self) -> list[bible.references.Passage]:
        return [
            passage
            for book, runs in self.targets
            for run in runs
            for item in run
            if (passage := item.passage(book))
        ]

    @property
    def verses(self) -> list[bible.references.Verse]:
        return [verse for passage in self.passages for verse in passage.verses]


@dataclass(frozen=True)
class UnresolvedCitation(Citation):
    """Source coordinates and the context that supplies relative references.

    Parsing never consults an edition inventory. The context remains attached
    to this expression if its containing paragraph subsequently moves.
    """

    coordinate_numbering: str = "edition"
    context: Verse | Citation | None = None


@dataclass(frozen=True)
class Dialect:
    name: str
    numbering: str
    books: Mapping[str, str]
    numerals: str
    # The stop between a chapter and its verses, as a pattern.
    chapter_verse: str

    @functools.cached_property
    def pattern(self) -> re.Pattern[str]:
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

    def number(self, numeral: str) -> int:
        return int(numeral) if numeral.isdigit() else roman(numeral.upper())

    def book_name(self, matched: str) -> str:
        """The dialect's name for a book, as the pattern read it, whose words
        may stand apart by any space, as a tab or a no-break space."""
        return " ".join(matched.split())


@functools.cache
def dialect(name: str | None, *, policy: bible.policy.Policy) -> Dialect:
    """A source's way of writing citations, or that of one that writes none."""
    if name is None:
        return Dialect("none", "brenton", {}, "arabic", r"\.\s?")
    found = policy.citations["dialects"][name]
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


def _ranges(verses: str) -> list[tuple[int, int]]:
    """The stretches a list of verses names, as (first, last)."""
    found = []
    for stretch in re.split(r",\s?", verses):
        first, *last = re.split(r"\s?(?:[-–]|\bto\b)\s?", stretch)
        found.append((int(first), int(last[0]) if last else int(first)))
    return found


def _items(
    cited: str, tongue: Dialect
) -> tuple[tuple[bible.references.Item, ...], ...]:
    """The runs of items a citation's figures name, chapter by chapter."""
    found = []
    for part in re.split(r";\s?(?:and\s|also\s)?", cited):
        match = re.fullmatch(
            rf"(?P<chapter>(?:{NUMERALS[tongue.numerals]}))(?![a-z])"
            rf"(?:{tongue.chapter_verse}(?P<verses>{VERSES})|(?P<ult>\.?\s?ult))?",
            part,
        )
        assert match is not None
        chapter = tongue.number(match["chapter"])
        stretches: Sequence[tuple[int | LastVerse | None, int | LastVerse | None]]
        if match["verses"]:
            stretches = _ranges(match["verses"])
        elif match["ult"]:
            stretches = [(LAST_VERSE, LAST_VERSE)]
        else:
            stretches = [(None, None)]
        found.append(tuple(Item(chapter, first, last) for first, last in stretches))
    return tuple(found)


def _carried(
    passage: bible.references.Passage, *, policy: bible.policy.Policy
) -> list[bible.references.Item]:
    """A King James passage's items in the edition, which may be in more
    than one place."""
    found = versification.edition_passages(passage, policy=policy)
    require(found, f"Verses the edition lacks: {passage}")
    return [
        Item(p.first.chapter, p.first.number, p.last.number, p.first.letter)
        for p in found
    ]


def _kjv_chapter(book: str, chapter: int, *, policy: bible.policy.Policy) -> int:
    """The King James chapter that holds an edition chapter's verses."""
    labels = versification.verses(f"{book} {chapter}:1-3")
    # A psalm's title, which the King James Bible doesn't number, places no chapter.
    found = [
        kjv
        for verse in labels
        for kjv in _counterparts(verse, policy=policy)
        if kjv.number != versification.TITLE
    ]
    require(found, f"Chapter the King James Bible lacks: {book} {chapter}")
    return found[0].chapter


def _counterparts(
    verse: bible.references.Verse, *, policy: bible.policy.Policy
) -> tuple[bible.references.Verse, ...]:
    try:
        return versification.to_kjv(verse, policy=policy)
    except RuntimeError:
        return ()


def _edition(
    book: str,
    items: tuple[tuple[Item, ...], ...],
    numbering: str,
    *,
    policy: bible.policy.Policy,
) -> tuple[str, tuple[tuple[Item, ...], ...]]:
    """A book's items as the edition numbers them, from a source's numbering.

    Brenton's verse is the edition's unless the edition relabels it. The King
    James Bible's is carried verse by verse, and may come to rest in more than
    one place, or none.
    """
    if numbering == "brenton":
        relabelled = versification.relabelled(policy=policy)
        runs = []
        for run in items:
            moved = []
            for item in run:
                if item.first is None:
                    moved.append(item)
                    continue
                assert isinstance(item.first, int) and isinstance(item.last, int)
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
            runs += _by_chapter(moved)
        return book, tuple(runs)
    if numbering == "kjv-verses":
        ours, theirs = book, versification.kjv_book(book, policy=policy)
    elif book not in versification.kjv_books(policy=policy):
        # A book the King James Old Testament lacks is numbered as it stands.
        return book, items
    else:
        ours, theirs = versification.kjv_books(policy=policy)[book], book
    runs = []
    for run in items:
        moved = []
        for item in run:
            chapter = item.chapter
            if numbering == "kjv-verses":
                chapter = _kjv_chapter(ours, chapter, policy=policy)
            if item.first is None:
                # A chapter is where its first verse is.
                found = versification.from_kjv(Verse(theirs, chapter, 1), policy=policy)
                require(found, f"Chapter the edition lacks: {theirs} {chapter}")
                moved.append(Item(found[0].chapter))
                continue
            require(
                numbering != "hebrew",
                f"Verses by the Hebrew's numbering: {book} {item}",
            )
            assert isinstance(item.first, int) and isinstance(item.last, int)
            moved += _carried(
                Passage(
                    Verse(theirs, chapter, item.first),
                    Verse(theirs, chapter, item.last),
                ),
                policy=policy,
            )
        runs += _by_chapter(moved)
    return ours, tuple(runs)


def _by_chapter(moved: Iterable[Item]) -> list[tuple[Item, ...]]:
    """A run's items as the edition numbers them, as runs: verses carried or
    relabelled into another chapter open a run of their own."""
    runs: list[tuple[Item, ...]] = []
    for item in moved:
        if runs and runs[-1][-1].chapter == item.chapter:
            runs[-1] = (*runs[-1], item)
        else:
            runs.append((item,))
    return runs


def decisions(key: str, *, policy: bible.policy.Policy) -> list[CitationsDecisions]:
    """The decisions on a note's citations, in the file's order."""
    found = policy.citations["decisions"].get(key, ())
    return list(found) if isinstance(found, tuple) else [found]


def unit_decisions(
    unit: str, plain: str, book: str | None = None, *, policy: bible.policy.Policy
) -> dict[str, CitationsDecisions]:
    """The decisions on a paragraph of a unit without verses, by key.

    Such a decision is keyed by its unit and the words it decides, as "XXB
    Psalm iv. 4", which must be the unit's once. A unit read into each book in
    turn, as the introductions are, keys them by the book as well, as "OTH BAR
    3. 8", that the same words in another book's paragraph not be decided so.
    """
    found: dict[str, CitationsDecisions] = {}
    for key, decision in policy.citations["decisions"].items():
        code, _, words = key.partition(" ")
        if book is not None:
            within, _, words = words.partition(" ")
            if within != book:
                continue
        if code == unit and not re.fullmatch(rf"\d+:{VERSE_LABEL}.*", words):
            assert not isinstance(decision, tuple)
            source = decision.get("source", words)
            if _places(source, plain):
                found[key] = {**decision, "source": source}
    return found


def _places(source: str, plain: str) -> list[int]:
    """Where a decision's words stand in a text, as words of their own:
    "3. 8" is not the end of "13. 8", nor "Verse 8" the start of "Verse 80"."""
    return [
        match.start()
        for match in re.finditer(rf"(?<!\w){re.escape(source)}(?!\w)", plain)
    ]


def _decided(
    decision: CitationsDecisions,
    plain: str,
    tongue: Dialect,
    home: Verse | Citation | None,
    key: str,
    *,
    policy: bible.policy.Policy,
) -> tuple[int, int, UnresolvedCitation | None]:
    """Where a decision's words stand, and its citation, if it decides that
    there is one."""
    source = decision.get("source", "")
    places = _places(source, plain) if source else []
    require(
        decision.get("why") and len(places) == 1,
        f"Citation decision without a reason, or not found once: {key} ({source})",
    )
    kinds = [kind for kind in DECISIONS if decision.get(kind)]
    require(
        len(kinds) == 1 and decision.keys() <= DECISIONS[kinds[0]],
        f"Citation decision that decides nothing, or too much: {key} ({source})",
    )
    (start,), (kind,) = places, kinds
    end = start + len(source)
    items: tuple[tuple[Item, ...], ...]
    relative: str | None
    coordinates = "edition"
    if kind == "not_a_citation":
        return start, end, None
    if kind == "unprinted":
        # What the edition doesn't print, as a verse its Greek lacks.
        require(decision.get("print"), f"Citation decision prints nothing: {key}")
        assert home is not None
        book, items, relative = home.book, (), None
    elif kind == "numbering":
        match = tongue.pattern.fullmatch(source)
        require(
            match is not None
            and match["book"]
            and decision["numbering"] in NUMBERINGS - {tongue.numbering},
            f"Citation decision of no other numbering: {key} ({source})",
        )
        assert match is not None
        numbering = decision["numbering"]
        book = tongue.books[tongue.book_name(match["book"])]
        if (
            tongue.numbering == "brenton"
            and numbering in {"kjv", "hebrew"}
            and book in policy.versification["old_testament"]
        ):
            # The dialect names the edition's book, and the numbering is the
            # King James Bible's, whose code for it may be another: Daniel's.
            book = versification.kjv_book(book, policy=policy)
        items = _items(match["cited"], tongue)
        coordinates = numbering
        relative = None
    else:
        require(decision.get("print"), f"Citation decision prints nothing: {key}")
        named: list[tuple[str, list[tuple[Item, ...]]]] = []
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
        UnresolvedCitation(
            start,
            end,
            source,
            book,
            items,
            decision.get("numbering", tongue.numbering),
            tuple(others) if kind == "passages" else (),
            relative,
            decision.get("print"),
            coordinate_numbering=coordinates,
        ),
    )


def _last_verse(
    inventory: Mapping[str, Mapping[str, Sequence[str]]], book: str, chapter: int
) -> int:
    """The last verse of a chapter, which a citation names as "ult."."""
    labels = inventory.get(book, {}).get(str(chapter))
    require(labels, f"No such chapter: {book} {chapter}")
    assert labels
    match = re.match(r"\d+", labels[-1])
    assert match is not None
    return int(match[0])


def _last_verses(
    inventory: scripture.Inventory,
    book: str,
    numbering: str,
    *,
    policy: bible.policy.Policy,
) -> Callable[[int], int]:
    """The last verse of each of a book's chapters, as a citation by a
    numbering names it: the inventory is the edition's, and knows no chapter
    of the King James Bible's Old Testament."""

    def last(chapter: int) -> int:
        require(
            numbering in {"brenton", "edition"}
            or (
                numbering != "kjv-verses"
                and book not in versification.kjv_books(policy=policy)
            ),
            f"Last verse by the King James Bible's numbering: {book} {chapter}",
        )
        return _last_verse(inventory, book, chapter)

    return last


def missing(
    citation: Citation,
    inventory: Mapping[str, Mapping[str, Sequence[str]]],
) -> list[str]:
    """What a citation names that the edition doesn't print."""
    found = []
    for book, runs in citation.targets:
        chapters = inventory.get(book, {})
        for item in (item for run in runs for item in run):
            labels = chapters.get(str(item.chapter))
            if labels is None:
                found.append(f"{book} {item.chapter}")
            elif item.first is not None:
                assert isinstance(item.first, int) and isinstance(item.last, int)
                found += [
                    f"{book} {item.chapter}:{number}{item.letter}"
                    for number in range(item.first, item.last + 1)
                    if f"{number}{item.letter}" not in labels
                ]
    return found


def parse(
    plain: str,
    tongue: Dialect,
    home: Verse | None,
    key: str,
    decided: Sequence[CitationsDecisions] | None = None,
    before: Citation | None = None,
    *,
    policy: bible.policy.Policy,
) -> list[UnresolvedCitation]:
    """Interpret source expressions without needing an edition inventory.

    ``home`` and ``before`` are immutable semantic context, not the location
    at which an introduction or annotation eventually prints.
    """
    taken: list[tuple[int, int]] = []
    found: list[UnresolvedCitation] = []
    for decision in decisions(key, policy=policy) if decided is None else decided:
        start, end, citation = _decided(
            decision, plain, tongue, home or Verse("", 0, 0), key, policy=policy
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
            # Resolving reads the last book it names, where a decision reads
            # several as one.
            standing = max(earlier, key=lambda citation: citation.end)
        if any(s < match.end() and match.start() < e for s, e in taken):
            continue
        require(
            match["book"] or standing is not None,
            f"Citation of no book: {key} ({match[0]})",
        )
        relative = None
        name = tongue.book_name(match["book"]) if match["book"] else None
        if name:
            book, numbering = tongue.books[name], tongue.numbering
            cited = match["cited"]
        elif match["chapter"]:
            assert standing is not None
            book, numbering, relative = standing.book, "edition", "chapter"
            cited = match["within"]
        else:
            assert standing is not None
            book, numbering, relative = standing.book, "edition", "verse"
            cited = None
        if cited is not None:
            items = _items(cited, tongue)
        else:
            assert standing is not None
            items = (
                tuple(
                    Item(
                        (
                            standing.chapter
                            if isinstance(standing, Verse)
                            else standing.targets[-1][1][-1][-1].chapter
                        ),
                        first,
                        last,
                    )
                    for first, last in _ranges(match["verses"])
                ),
            )
        found.append(
            UnresolvedCitation(
                match.start(),
                match.end(),
                match[0],
                book,
                items,
                tongue.numbering,
                relative=relative,
                name=name,
                coordinate_numbering=numbering,
                context=standing if relative else None,
            )
        )
        taken.append((match.start(), match.end()))
    unread = [
        match[0]
        for match in SHAPE.finditer(plain)
        if not any(s <= match.start() and match.end() <= e for s, e in taken)
    ]
    require(not unread, f"Citation that can't be read: {key} ({'; '.join(unread)})")
    return sorted(found, key=lambda citation: citation.start)


def resolve(
    expression: UnresolvedCitation,
    inventory: Mapping[str, Mapping[str, Sequence[str]]],
    *,
    policy: bible.policy.Policy,
) -> Citation:
    """Resolve one source expression against actual assembled content."""
    book, items = expression.book, expression.items
    if expression.relative and isinstance(expression.context, UnresolvedCitation):
        previous = resolve(expression.context, inventory, policy=policy)
        book, previous_runs = previous.targets[-1]
        if expression.relative == "verse":
            chapter = previous_runs[-1][-1].chapter
            items = tuple(
                tuple(Item(chapter, i.first, i.last, i.letter) for i in run)
                for run in items
            )
    resolved = []
    for run in items:
        values = []
        for item in run:
            if isinstance(item.first, LastVerse):
                last = _last_verses(
                    inventory,
                    book,
                    expression.coordinate_numbering,
                    policy=policy,
                )(item.chapter)
                item = Item(item.chapter, last, last)
            values.append(item)
        resolved.append(tuple(values))
    items = tuple(resolved)
    if expression.coordinate_numbering != "edition":
        book, items = _edition(
            book, items, expression.coordinate_numbering, policy=policy
        )
    return Citation(
        expression.start,
        expression.end,
        expression.source,
        book,
        items,
        expression.numbering,
        expression.others,
        expression.relative,
        expression.printed,
        expression.name,
    )


def scan(
    plain: str,
    tongue: Dialect,
    home: Verse | None,
    key: str,
    inventory: scripture.Inventory,
    decided: Sequence[CitationsDecisions] | None = None,
    before: Citation | None = None,
    *,
    policy: bible.policy.Policy,
) -> list[Citation]:
    """Parse then resolve; retained convenience API for source-note consumers."""
    found = [
        resolve(expression, inventory, policy=policy)
        for expression in parse(
            plain, tongue, home, key, decided, before, policy=policy
        )
    ]
    for citation in found:
        lacking = missing(citation, inventory)
        require(
            not lacking,
            f"Citation of what the edition doesn't print: {key} "
            f"({citation.source}: {', '.join(lacking)})",
        )
    return found


def source_pieces(
    pieces: Sequence[tuple[str, str]], found: Sequence[Citation]
) -> list[tuple[str, str]]:
    """A note's pieces with each citation as the edition prints it, as a
    reference of its own.

    A citation that names nothing the edition prints is no reference for a
    reader to follow, and stays among the words it stands in. The pieces
    with their citations as the source has them must be the pieces given.
    """
    plain = "".join(text for _, text in pieces)
    result: list[tuple[str, str]] = []
    offset, cursor, joined = 0, 0, False
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
            elif citation is not None and citation.items:
                result.append(("xt", citation.source))
                cursor = citation.end
            else:
                # Among its words: of their kind, and not apart from them.
                assert citation is not None
                words = citation.source
                if result and result[-1][0] == kind and cursor > offset:
                    result[-1] = (kind, result[-1][1] + words)
                else:
                    result.append((kind, words))
                cursor = citation.end
                joined = True
                continue
            joined = False
        offset = end
    require(
        "".join(value for _, value in result) == plain,
        f"Source citation segmentation lost text: {plain}",
    )
    return [(kind, text) for kind, text in result if text]


class Names(string.Formatter):
    """What a decision or a change of name prints, with the edition's names
    for the books it names by their codes: "{ISA} 2:6", or in capitals,
    "{ISA:upper} 2:6"."""

    def format_field(self, value: object, spec: str) -> str:
        assert isinstance(value, str)
        return value.upper() if spec == "upper" else super().format_field(value, spec)


def named(words: str, names: Mapping[str, str]) -> str:
    return Names().vformat(words, (), names)


def printed(
    citation: Citation,
    books: bible.references.Books,
    style: bible.references.Style = EDITION,
) -> str:
    """A citation as the edition prints it: under the edition's name for the
    book, or as a verse or chapter of the note's own book, which it names as
    its source does, by no name."""
    if citation.printed is not None:
        # A decision names the books by their codes, and the edition's names
        # for them print. What a page without verses doesn't print stands in
        # no book.
        names = {
            book: books.name(book, [item.chapter for run in runs for item in run])
            for book, runs in citation.targets
            if book
        }
        return named(citation.printed, names)
    chapters = [item.chapter for run in citation.items for item in run]
    verses = [item for run in citation.items for item in run if item.first is not None]
    if citation.relative == "verse":
        (run,) = citation.items
        word = "verse" if len(run) == 1 and run[0].first == run[0].last else "verses"
        body = style.verses.join(_printed_item(item, style) for item in run)
    else:
        runs: list[str] = []
        for run in citation.items:
            chapter = str(run[0].chapter)
            if run[0].first is not None:
                chapter += style.chapter_verse + style.verses.join(
                    _printed_item(item, style) for item in run
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


def _printed_item(item: Item, style: Style) -> str:
    assert isinstance(item.first, int) and isinstance(item.last, int)
    return style.stretch(item.first, item.last, item.letter)
