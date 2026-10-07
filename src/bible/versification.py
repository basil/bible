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

from __future__ import annotations

import functools
from collections.abc import Callable, Iterable, Mapping

import bible.policy
import bible.references
from bible.checks import require
from bible.policy_schema import ByzantineStructure, Run
from bible.references import Verse, parse_passage, parse_passages, runs, verses_of

# What a run rests on: the table's account of a Bible numbered like this one,
# the words of both translations, its place between verses that they fix, or
# the editor's reading of both, which gives its reason.
WITNESSES = {"table", "words", "place", "reading"}
# A psalm's title stands before its first verse, as its verse 0.
TITLE = 0


def kjv_book(code: str, *, policy: bible.policy.Policy) -> str:
    """The King James Bible's code for one of the edition's books: the Old
    Testament's by the table of names, and the New Testament's its own."""
    if code in policy.versification["old_testament"]:
        return policy.versification["books"].get(code, code)
    require(
        any(u["id"] == code and u["source"] == "kjv" for u in policy.scripture),
        f"No King James counterpart: {code}",
    )
    return code


@functools.cache
def kjv_books(*, policy: bible.policy.Policy) -> dict[str, str]:
    """The edition's code for each book of the King James Bible."""
    return {
        kjv_book(code, policy=policy): code
        for code in (
            *policy.versification["old_testament"],
            *(u["id"] for u in policy.scripture if u["source"] == "kjv"),
        )
    }


def byzantine_runs(structure: ByzantineStructure) -> dict[str, list[Run]]:
    """Where the New Testament's verses stand in the King James Bible: every
    verse at its own number, but for those the Byzantine text lacks or
    places elsewhere (edition/byzantine.json, structure), each a run with
    the decision's reason. Only the books with such runs are listed."""
    found: dict[str, list[tuple[Verse, Run]]] = {}
    for passage, entry in structure["moved"].items():
        ours = parse_passage(entry["to"])
        found.setdefault(ours.first.book, []).append(
            (
                ours.first,
                {
                    "edition": str(ours),
                    "kjv": str(parse_passage(passage)),
                    "by": "reading",
                    "why": entry["why"],
                },
            )
        )
    for passage in structure["omitted"]:
        theirs = parse_passage(passage)
        found.setdefault(theirs.first.book, []).append(
            (theirs.first, {"edition": None, "kjv": str(theirs)})
        )
    return {
        code: [
            run
            for _, run in sorted(
                listed, key=lambda item: (item[0].chapter, item[0].number)
            )
        ]
        for code, listed in sorted(found.items())
    }


def verses(passages: str | None) -> list[bible.references.Verse]:
    """The verses of a list of passages; of none, where a run has no side."""
    return verses_of(parse_passages(passages)) if passages else []


def run_verses(run: Run) -> tuple[list[Verse], list[Verse]]:
    """A run's verses on either side: the edition's, and the King James Bible's."""
    return verses(run["edition"]), verses(run["kjv"])


def run_pairs(run: Run) -> list[tuple[list[Verse], list[Verse]]]:
    """A run's correspondences, including explicitly declared partial overlaps."""
    ours, theirs = run_verses(run)
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
def apocryphal(*, policy: bible.policy.Policy) -> frozenset[bible.references.Verse]:
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
def _maps(
    *, policy: bible.policy.Policy
) -> tuple[dict[Verse, tuple[Verse, ...]], dict[Verse, tuple[Verse, ...]]]:
    """Each listed verse's counterparts, both ways, every run checked.

    Checked whole, so that a run is refused whether or not a reference
    reaches it, and two that claim one verse can't shadow each other.
    """
    # The runs are worked out once the edition's books are assembled.
    require("kjv" in policy.versification, "The verses are not yet placed")
    to_kjv: dict[Verse, tuple[Verse, ...]] = {}
    from_kjv: dict[Verse, tuple[Verse, ...]] = {}
    for code, listed in policy.versification["kjv"].items():
        kjv = kjv_book(code, policy=policy)
        for run in listed:
            ours, theirs = run_verses(run)
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
            reverse: dict[Verse, list[Verse]] = {}
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


def to_kjv(
    verse: bible.references.Verse, *, policy: bible.policy.Policy
) -> tuple[bible.references.Verse, ...]:
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


def from_kjv(
    verse: bible.references.Verse, *, policy: bible.policy.Policy
) -> tuple[bible.references.Verse, ...]:
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


def _mapped(
    passage: bible.references.Passage, counterparts: Callable[[Verse], Iterable[Verse]]
) -> list[bible.references.Passage]:
    found = []
    for verse in passage.verses:
        found += [v for v in counterparts(verse) if v not in found]
    return runs(found)


def kjv_passages(
    passage: bible.references.Passage, *, policy: bible.policy.Policy
) -> list[bible.references.Passage]:
    """An edition passage as the King James Bible numbers it: verse by verse,
    since a passage may be carried into more than one place."""
    return _mapped(passage, lambda v: to_kjv(v, policy=policy))


def edition_passages(
    passage: bible.references.Passage, *, policy: bible.policy.Policy
) -> list[bible.references.Passage]:
    """A King James passage as the edition numbers it."""
    return _mapped(passage, lambda v: from_kjv(v, policy=policy))


@functools.cache
def relabelled(*, policy: bible.policy.Policy) -> dict[Verse, Verse]:
    """Each verse the edition relabels, by Brenton's label for it."""
    found: dict[Verse, Verse] = {}
    for source, printed in policy.versification["relabel"].items():
        labels, targets = verses(source), verses(printed["edition"])
        require(len(labels) == len(targets), f"Misaligned relabelling: {source}")
        found.update(zip(labels, targets))
    return found


def new_chapters(
    code: str, *, policy: bible.policy.Policy
) -> list[tuple[list[Verse], list[Verse], str]]:
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
def _excepted_verses(*, policy: bible.policy.Policy) -> dict[Verse, Verse]:
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


def lxx_to_edition(
    verse: bible.references.Verse, *, policy: bible.policy.Policy
) -> bible.references.Verse:
    """Map one Turpie/Brenton Septuagint verse to the printed edition."""
    return _excepted_verses(policy=policy).get(verse, verse)


def mapped_passages(
    passage: bible.references.Passage, *, policy: bible.policy.Policy
) -> list[bible.references.Passage]:
    """A Septuagint passage's printed Brenton verses, as same-chapter ranges.

    A mapping exception can carry part of a passage into another chapter, so
    one source passage may print as more than one range. A lettered verse
    prints alone.
    """
    return runs(lxx_to_edition(verse, policy=policy) for verse in passage.verses)


def unused_exceptions(
    passages: Iterable[bible.references.Passage], *, policy: bible.policy.Policy
) -> list[str]:
    """The exceptions that no verse of the passages reaches."""
    reached = set(verses_of(passages))
    return sorted(
        source
        for source in policy.quotations["lxx_to_edition"]
        if not reached.intersection(parse_passage(source).verses)
    )
