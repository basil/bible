"""Where the edition's chapters and verses stand in other numberings
(edition/versification.json).

Two numberings meet the edition's. Brenton's own, as eBible labels it, which
the edition relabels in a few places, as Malachias 3:19-24; and the King
James Bible's, which a reader's other Bible follows, and in which some of the
edition's sources cite the Old Testament.

A verse the file doesn't list keeps its number in the King James Bible,
unless Brenton letters it: a lettered verse is a Septuagint addition, and has
no counterpart unless the file gives one. A run of verses faces a run as long
verse for verse; runs of different lengths face each other whole, as where
Brenton divides one verse in two.

Turpie's Septuagint column normally numbers chapters and verses as Brenton
does, Psalm superscriptions included; where he numbers a verse the English
way instead, edition/quotations.json names it as an exception, which must be
used.
"""

import functools

from bible import edition, paths
from bible.checks import require
from bible.files import read_json
from bible.references import Verse, parse_passage, parse_passages, runs
from bible.usfm import inventory

DATA = read_json(paths.EDITION_DIR / "versification.json")
EXCEPTIONS = read_json(paths.EDITION_DIR / "quotations.json")["lxx_to_edition"]
# What a run rests on: the table's account of a Bible numbered like this one,
# the words of both translations, its place between verses that they fix, or
# the editor's reading of both, which gives its reason.
WITNESSES = {"table", "words", "place", "reading"}
# A psalm's title stands before its first verse, as its verse 0.
TITLE = 0


def kjv_book(code):
    """The King James Old Testament's code for one of the edition's books."""
    require(code in DATA["old_testament"], f"No King James counterpart: {code}")
    return DATA["books"].get(code, code)


@functools.cache
def kjv_books():
    """The edition's code for each book of the King James Old Testament."""
    return {kjv_book(code): code for code in DATA["old_testament"]}


def verses(passages):
    return [verse for passage in parse_passages(passages) for verse in passage.verses]


@functools.cache
def apocryphal():
    """The verses of the edition's Old Testament books that the King James
    Bible sets apart in its Apocrypha, or lacks, and so doesn't number among
    the books they stand in here."""
    return frozenset(
        verse
        for span in DATA["apocrypha"]
        # A span of verses, not a book or its lettered verses as a whole.
        if ":" in span["edition"]
        for verse in verses(span["edition"])
    )


@functools.cache
def _maps():
    """Each listed verse's counterparts, both ways, every run checked.

    Checked whole, so that a run is refused whether or not a reference
    reaches it, and two that claim one verse can't shadow each other.
    """
    to_kjv, from_kjv = {}, {}
    books = {kjv_book(code): code for code in DATA["old_testament"]}
    for code, listed in DATA["kjv"].items():
        kjv = kjv_book(code)
        for run in listed:
            ours = verses(run["edition"]) if run["edition"] else []
            theirs = verses(run["kjv"]) if run["kjv"] else []
            name = run["edition"] or run["kjv"]
            require(ours or theirs, f"Empty versification run in {code}")
            require(
                not apocryphal().intersection(ours),
                f"Versification run within the Apocrypha: {name}",
            )
            require(
                all(v.book == code for v in ours)
                and all(v.book == kjv for v in theirs),
                f"Versification run outside its book: {name}",
            )
            require(
                (run.get("by") in WITNESSES) == bool(ours),
                f"Versification run without its witness: {name}",
            )
            require(
                bool(run.get("why")) == (run.get("by") == "reading"),
                f"A reading gives its reason, and no other run does: {name}",
            )
            if len(ours) == len(theirs):
                pairs = [([v], [o]) for v, o in zip(ours, theirs)]
            else:
                pairs = [(ours, theirs)]
            for near, far in pairs:
                for verse in near:
                    require(verse not in to_kjv, f"Two runs for {verse}")
                    to_kjv[verse] = tuple(far)
                for verse in far:
                    require(verse not in from_kjv, f"Two runs reach {verse}")
                    from_kjv[verse] = tuple(near)
    return to_kjv, from_kjv, books


def to_kjv(verse):
    """The King James verses that hold an edition verse's words, if any."""
    listed = _maps()[0]
    if verse in listed:
        return listed[verse]
    kjv = Verse(kjv_book(verse.book), verse.chapter, verse.number)
    if verse.letter or verse in apocryphal():
        return ()
    # A verse that loses its place to another is listed, with what it faces.
    require(kjv not in _maps()[1], f"Another verse has the place of {verse}")
    return (kjv,)


def from_kjv(verse):
    """The edition's verses that hold a King James verse's words, if any."""
    listed, books = _maps()[1], _maps()[2]
    if verse in listed:
        return listed[verse]
    require(verse.book in books, f"No edition counterpart: {verse}")
    ours = Verse(books[verse.book], verse.chapter, verse.number)
    return () if ours in _maps()[0] or ours in apocryphal() else (ours,)


def _mapped(passage, counterparts):
    found = []
    for verse in passage.verses:
        found += [v for v in counterparts(verse) if v not in found]
    return runs(found)


def kjv_passages(passage):
    """An edition passage as the King James Bible numbers it: verse by verse,
    since a passage may be carried into more than one place."""
    return _mapped(passage, to_kjv)


def edition_passages(passage):
    """A King James passage as the edition numbers it."""
    return _mapped(passage, from_kjv)


@functools.cache
def relabelled():
    """Each verse the edition relabels, by Brenton's label for it."""
    found = {}
    for source, printed in DATA["relabel"].items():
        labels, targets = verses(source), verses(printed["edition"])
        require(len(labels) == len(targets), f"Misaligned relabelling: {source}")
        found.update(zip(labels, targets))
    return found


def new_chapters(code):
    """The chapters a book's relabelling opens, as (Brenton's verses, the
    printed ones, the words the first opens with).

    The edition relabels only the close of a chapter, as a chapter of its
    own; the words witness that the verse is the one meant.
    """
    found = []
    for source, printed in DATA["relabel"].items():
        labels, targets = verses(source), verses(printed["edition"])
        if labels[0].book != code:
            continue
        require(
            printed.get("opens")
            and [v.number for v in targets] == list(range(1, len(targets) + 1))
            and targets[0].chapter == labels[0].chapter + 1,
            f"Relabelling that opens no chapter: {source}",
        )
        found.append((labels, targets, printed["opens"]))
    return found


@functools.lru_cache(maxsize=512)
def source_chapters(text):
    """A source book's chapters and verse labels, read once however often a
    book or page asks: each book's preparation asks for every book's."""
    return {
        chapter: tuple(labels)
        for chapter, labels in inventory(text)["chapters"].items()
    }


def edition_inventory(archives):
    """Every printed book's chapters and verse labels, as preparation will
    print them, from the sources and what the edition does to their labels:
    the chapters it selects and numbers from 1, Susanna and Bel and the
    Dragon beside Daniel, and the verses it relabels.

    Known before any book is prepared, so that a citation read while one is
    can be held to the verses of another.
    """
    found = {}
    for unit in edition.MANIFEST["scripture"]:
        code = unit["id"]
        source = archives[unit["source"]]
        chapters = source_chapters(source[edition.source_id(unit)])
        if "chapters" in unit:
            first, last = unit["chapters"]
            chapters = {
                str(int(chapter) - first + 1): labels
                for chapter, labels in chapters.items()
                if first <= int(chapter) <= last
            }
        elif code == edition.DANIEL_PARTS[1]:
            susanna, bel = (
                source_chapters(source[part])["1"]
                for part in (edition.DANIEL_PARTS[0], edition.DANIEL_PARTS[2])
            )
            chapters = {"0": susanna, **chapters, str(len(chapters) + 1): bel}
        chapters = {chapter: list(labels) for chapter, labels in chapters.items()}
        for label, printed in relabelled().items():
            if label.book == code:
                chapters[str(label.chapter)].remove(str(label.number))
                chapters.setdefault(str(printed.chapter), []).append(
                    str(printed.number)
                )
        found[code] = chapters
    return found


def _excepted_verses():
    """Each excepted verse's printed verse, every exception checked.

    Checked whole, so an exception is refused whether or not a reference
    reaches it, and two that claim one verse can't shadow each other. An
    exception that says only that Turpie numbers as the King James Bible
    does takes its printed verses from the file.
    """
    mapped = {}
    for source, exception in EXCEPTIONS.items():
        excepted = parse_passage(source).verses
        if exception.get("numbering") == "kjv":
            require("target" not in exception, f"Mapping given twice: {source}")
            kjv = kjv_book(excepted[0].book)
            targets = [
                target
                for verse in excepted
                for target in from_kjv(Verse(kjv, verse.chapter, verse.number))
            ]
        else:
            targets = parse_passage(exception.get("target", "")).verses
        require(
            exception.get("why") and len(targets) == len(excepted),
            f"Unjustified or misaligned mapping: {source}",
        )
        for verse, target in zip(excepted, targets):
            require(verse not in mapped, f"Overlapping mappings of {verse}")
            require(verse != target, f"Mapping that changes nothing: {source}")
            mapped[verse] = target
    return mapped


def lxx_to_edition(verse):
    """Map one Turpie/Brenton Septuagint verse to the printed edition."""
    return _excepted_verses().get(verse, verse)


def mapped_passages(passage):
    """A Septuagint passage's printed Brenton verses, as same-chapter ranges.

    A mapping exception can carry part of a passage into another chapter, so
    one source passage may print as more than one range. A lettered verse
    prints alone.
    """
    return runs(lxx_to_edition(verse) for verse in passage.verses)


def unused_exceptions(passages):
    """The exceptions that no verse of the passages reaches."""
    reached = {verse for passage in passages for verse in passage.verses}
    return sorted(
        source
        for source in EXCEPTIONS
        if not reached.intersection(parse_passage(source).verses)
    )
