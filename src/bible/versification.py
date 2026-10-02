"""Where the edition's chapters and verses stand in other numberings
(edition/versification.json, and the runs the build works out in places.py).

Two numberings meet the edition's. Brenton's own, as eBible labels it, which
the edition relabels in a few places, as Malachias 3:19-24; and the King
James Bible's, which a reader's other Bible follows, and in which some of the
edition's sources cite the Old Testament.

A verse that no run lists keeps its number in the King James Bible, unless
Brenton letters it: a lettered verse is a Septuagint addition, and has no
counterpart unless a run gives it one. A run of verses faces a run as long
verse for verse; runs of different lengths face each other whole, as where
Brenton divides one verse in two. Explicit pairs describe partial overlaps
within a run without assigning its unchanged clauses to the wrong verse.

Turpie's Septuagint column normally numbers chapters and verses as Brenton
does, Psalm superscriptions included; where he numbers a verse the English
way instead, edition/quotations.json names it as an exception, which must be
used.
"""

import functools
from collections.abc import Mapping

from bible.checks import require
from bible.references import Verse, parse_passage, parse_passages, runs

# What a run rests on: the table's account of a Bible numbered like this one,
# the words of both translations, its place between verses that they fix, or
# the editor's reading of both, which gives its reason.
WITNESSES = {"table", "words", "place", "reading"}
# A psalm's title stands before its first verse, as its verse 0.
TITLE = 0


def kjv_book(code, *, policy):
    """The King James Old Testament's code for one of the edition's books."""
    require(
        code in policy.versification["old_testament"],
        f"No King James counterpart: {code}",
    )
    return policy.versification["books"].get(code, code)


@functools.cache
def kjv_books(*, policy):
    """The edition's code for each book of the King James Old Testament."""
    return {
        kjv_book(code, policy=policy): code
        for code in policy.versification["old_testament"]
    }


def verses(passages):
    return [verse for passage in parse_passages(passages) for verse in passage.verses]


def run_pairs(run):
    """A run's correspondences, including explicitly declared partial overlaps."""
    ours = verses(run["edition"]) if run["edition"] else []
    theirs = verses(run["kjv"]) if run["kjv"] else []
    if "pairs" in run:
        declared = run["pairs"]
        require(
            isinstance(declared, Mapping)
            and set(declared) == set(map(str, ours))
            and all(isinstance(v, str) and v.strip() for v in declared.values()),
            f"Invalid verse pairs: {run['edition']}",
        )
        pairs = [([verse], verses(declared[str(verse)])) for verse in ours]
        targets = [v for _, far in pairs for v in far]
        require(
            set(targets) == set(theirs)
            and all(far and len(far) == len(set(far)) for _, far in pairs),
            f"Verse pairs do not cover their run: {run['edition']}",
        )
        return pairs
    if len(ours) == len(theirs):
        return [([v], [o]) for v, o in zip(ours, theirs)]
    return [(ours, theirs)]


@functools.cache
def apocryphal(*, policy):
    """The verses of the edition's Old Testament books that the King James
    Bible sets apart in its Apocrypha, or lacks, and so doesn't number among
    the books they stand in here."""
    return frozenset(
        verse
        for span in policy.versification["apocrypha"]
        # A span of verses, not a book or its lettered verses as a whole.
        if ":" in span["edition"]
        for verse in verses(span["edition"])
    )


@functools.cache
def _maps(*, policy):
    """Each listed verse's counterparts, both ways, every run checked.

    Checked whole, so that a run is refused whether or not a reference
    reaches it, and two that claim one verse can't shadow each other.
    """
    # The runs are worked out once the edition's books are assembled.
    require("kjv" in policy.versification, "The verses are not yet placed")
    to_kjv, from_kjv = {}, {}
    for code, listed in policy.versification["kjv"].items():
        kjv = kjv_book(code, policy=policy)
        for run in listed:
            ours = verses(run["edition"]) if run["edition"] else []
            theirs = verses(run["kjv"]) if run["kjv"] else []
            name = run["edition"] or run["kjv"]
            require(ours or theirs, f"Empty versification run in {code}")
            require(
                not apocryphal(policy=policy).intersection(ours),
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
            reverse = {}
            for near, far in run_pairs(run):
                for verse in near:
                    require(verse not in to_kjv, f"Two runs for {verse}")
                    to_kjv[verse] = tuple(far)
                for verse in far:
                    reverse.setdefault(verse, []).extend(near)
            for verse, near in reverse.items():
                require(verse not in from_kjv, f"Two runs reach {verse}")
                from_kjv[verse] = tuple(near)
    return to_kjv, from_kjv


def to_kjv(verse, *, policy):
    """The King James verses that hold an edition verse's words, if any."""
    listed = _maps(policy=policy)[0]
    if verse in listed:
        return listed[verse]
    kjv = Verse(kjv_book(verse.book, policy=policy), verse.chapter, verse.number)
    if verse.letter or verse in apocryphal(policy=policy):
        return ()
    # A verse that loses its place to another is listed, with what it faces.
    require(
        kjv not in _maps(policy=policy)[1],
        f"Another verse has the place of {verse}",
    )
    return (kjv,)


def from_kjv(verse, *, policy):
    """The edition's verses that hold a King James verse's words, if any."""
    listed, books = _maps(policy=policy)[1], kjv_books(policy=policy)
    if verse in listed:
        return listed[verse]
    require(verse.book in books, f"No edition counterpart: {verse}")
    ours = Verse(books[verse.book], verse.chapter, verse.number)
    return (
        ()
        if ours in _maps(policy=policy)[0] or ours in apocryphal(policy=policy)
        else (ours,)
    )


def _mapped(passage, counterparts):
    found = []
    for verse in passage.verses:
        found += [v for v in counterparts(verse) if v not in found]
    return runs(found)


def kjv_passages(passage, *, policy):
    """An edition passage as the King James Bible numbers it: verse by verse,
    since a passage may be carried into more than one place."""
    return _mapped(passage, lambda v: to_kjv(v, policy=policy))


def edition_passages(passage, *, policy):
    """A King James passage as the edition numbers it."""
    return _mapped(passage, lambda v: from_kjv(v, policy=policy))


@functools.cache
def relabelled(*, policy):
    """Each verse the edition relabels, by Brenton's label for it."""
    found = {}
    for source, printed in policy.versification["relabel"].items():
        labels, targets = verses(source), verses(printed["edition"])
        require(len(labels) == len(targets), f"Misaligned relabelling: {source}")
        found.update(zip(labels, targets))
    return found


def new_chapters(code, *, policy):
    """The chapters a book's relabelling opens, as (Brenton's verses, the
    printed ones, the words the first opens with).

    The edition relabels only the close of a chapter, as a chapter of its
    own; the words witness that the verse is the one meant.
    """
    found = []
    for source, printed in policy.versification["relabel"].items():
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


@functools.cache
def _excepted_verses(*, policy):
    """Each excepted verse's printed verse, every exception checked.

    Checked whole, so an exception is refused whether or not a reference
    reaches it, and two that claim one verse can't shadow each other. An
    exception that says only that Turpie numbers as the King James Bible
    does takes its printed verses from the runs.
    """
    mapped = {}
    for source, exception in policy.quotations["lxx_to_edition"].items():
        excepted = parse_passage(source).verses
        if exception.get("numbering") == "kjv":
            require("target" not in exception, f"Mapping given twice: {source}")
            kjv = kjv_book(excepted[0].book, policy=policy)
            targets = [
                target
                for verse in excepted
                for target in from_kjv(
                    Verse(kjv, verse.chapter, verse.number), policy=policy
                )
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


def lxx_to_edition(verse, *, policy):
    """Map one Turpie/Brenton Septuagint verse to the printed edition."""
    return _excepted_verses(policy=policy).get(verse, verse)


def mapped_passages(passage, *, policy):
    """A Septuagint passage's printed Brenton verses, as same-chapter ranges.

    A mapping exception can carry part of a passage into another chapter, so
    one source passage may print as more than one range. A lettered verse
    prints alone.
    """
    return runs(lxx_to_edition(verse, policy=policy) for verse in passage.verses)


def unused_exceptions(passages, *, policy):
    """The exceptions that no verse of the passages reaches."""
    reached = {verse for passage in passages for verse in passage.verses}
    return sorted(
        source
        for source in policy.quotations["lxx_to_edition"]
        if not reached.intersection(parse_passage(source).verses)
    )
