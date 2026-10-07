"""The edition's own pages, written from its files: the table of chapters and
verses, and what the editor's pages cite.

The table says where the chapters and verses of this Old Testament stand in
the King James Bible, for a reader who looks a verse up there. Every row is
written from the runs that the build works out (places.py), so that the table
can say no more and no less than they do: a chapter that stands whole
elsewhere is one row, a run of verses another, and what either Bible lacks is
said to be missing.

The editor's pages name a passage between braces, by its code, and the build
prints it as the edition cites, or as the King James Bible numbers it, so
that what the pages say of a number is what the runs say.
"""

from __future__ import annotations

import collections
import re
from collections.abc import Iterable, Mapping, Sequence

import bible.policy
import bible.references
from bible import scripture, terminology, usj, versification
from bible.checks import require
from bible.policy_schema import Run, VersificationApocrypha
from bible.references import EDITION, Verse, parse_passage
from bible.usj import Document, Node

# One side of a row: the chapters that stand whole, or verses; no verses,
# where that Bible lacks what the other side has.
type Side = range | list[Verse]

MISSING = "missing"
# A passage that the editor's pages name: "{PSA 33:13-17}", or with how it is
# to print before it, "{kjv bare PSA 33:13-17}".
NAMED = re.compile(r"\{((?:[a-z]+ )*)([1-4]?[A-Z]{2,3} [^{}]+)\}")
# What the table's page asks for, each on a line of its own.
TABLES = re.compile(r"^\{(names|psalms|books|readings)\}$", re.M)
# How a passage that the pages name may print.
WAYS = {"kjv", "brenton", "bare"}


def _letters(verses: list[bible.references.Verse]) -> str:
    """Verses within a chapter as they print: "5", "19–28", "2a–f", "5, 9a"."""
    printed, n = [], 0
    while n < len(verses):
        first = last = verses[n]
        while n + 1 < len(verses) and _next(last, verses[n + 1]):
            last = verses[n + 1]
            n += 1
        n += 1
        one = f"{first.number}{first.letter}"
        if first == last:
            printed.append(one)
        elif first.number == last.number:
            printed.append(f"{one}{EDITION.range}{last.letter}")
        else:
            printed.append(f"{one}{EDITION.range}{last.number}{last.letter}")
    return EDITION.verses.join(printed)


def _next(verse: bible.references.Verse, other: bible.references.Verse) -> bool:
    """Whether a verse follows another: the next number, or the next letter
    of the same."""
    if verse.chapter != other.chapter:
        return False
    if not (verse.letter or other.letter):
        return other.number == verse.number + 1
    return (
        other.number == verse.number
        and bool(verse.letter and other.letter)
        and ord(other.letter) == ord(verse.letter) + 1
    )


def within(verses: list[bible.references.Verse]) -> str:
    """Verses of one book as a table's cell prints them, chapter by chapter."""
    chapters: collections.defaultdict[int, list[Verse]] = collections.defaultdict(list)
    for verse in verses:
        chapters[verse.chapter].append(verse)
    return EDITION.passages.join(
        f"{chapter}{EDITION.chapter_verse}{_letters(listed)}"
        for chapter, listed in chapters.items()
    )


def numbered(run: Run) -> tuple[list[Verse], list[Verse]]:
    """A run's verses on either side, without a psalm's title, which the
    King James Bible doesn't number, and the verse that is one."""
    ours, theirs = versification.run_verses(run)
    if len(ours) == len(theirs):
        pairs = [
            (v, o) for v, o in zip(ours, theirs) if o.number != versification.TITLE
        ]
        return [v for v, _ in pairs], [o for _, o in pairs]
    return ours, [v for v in theirs if v.number != versification.TITLE]


def row_cells(sides: Iterable[tuple[Side, Side]]) -> list[tuple[str, str]]:
    """Rows as their cells print: (edition cell, King James cell)."""

    def cell(side: Side) -> str:
        if isinstance(side, range):
            return EDITION.stretch(side[0], side[-1])
        return within(side) if side else MISSING

    rows = ((cell(ours), cell(theirs)) for ours, theirs in sides)
    # A run that keeps its numbers, against the table or the words, tells
    # a reader nothing.
    return [row for row in rows if row[0] != row[1]]


class Table:
    """One book's chapters and verses beside the King James Bible's."""

    def __init__(
        self,
        code: str,
        inventory: Mapping[str, Mapping[str, Sequence[str]]],
        kjv_inventory: scripture.Inventory,
        *,
        policy: bible.policy.Policy,
    ) -> None:
        self.policy = policy
        self.code = code
        self.kjv = versification.kjv_book(code, policy=policy)
        self.ours = inventory[code]
        self.theirs = kjv_inventory[self.kjv]
        self.listed: Sequence[Run] = policy.versification["kjv"].get(code, [])

    def verses(self, chapter: str | int) -> list[Verse]:
        result = []
        for label in self.ours[str(chapter)]:
            match = re.fullmatch(r"(\d+)([a-z]?)", label)
            assert match is not None
            number, letter = match.groups()
            result.append(Verse(self.code, int(chapter), int(number), letter))
        return result

    def whole(self, chapter: str | int) -> int | None:
        """The King James chapter that an edition chapter is, verse for verse
        under the same numbers, if it is one and not the same chapter, and
        no other chapter of the edition holds any of it."""
        facing = set()
        for verse in self.verses(chapter):
            if verse in versification.apocryphal(policy=self.policy) or verse.letter:
                continue
            found = versification.to_kjv(verse, policy=self.policy)
            if len(found) != 1 or found[0].number != verse.number:
                return None
            facing.add(found[0].chapter)
        if len(facing) != 1 or facing == {int(chapter)}:
            return None
        there = facing.pop()
        for number in self.theirs[str(there)]:
            verse = Verse(self.kjv, there, int(number))
            held = versification.from_kjv(verse, policy=self.policy)
            if any(v.chapter != int(chapter) for v in held):
                return None
        return there

    def rows(self) -> list[tuple[str, str]]:
        """The book's rows as (edition cell, King James cell)."""
        return row_cells(self.sides())

    def sides(self) -> list[tuple[Side, Side]]:
        """The book's rows as (the edition's side, the King James Bible's),
        in the edition's order; what the edition lacks stands where the King
        James Bible has it, among the rows of its chapter."""
        moved = {
            int(chapter): there
            for chapter in self.ours
            if (there := self.whole(chapter)) is not None
        }
        order = {
            verse: n
            for n, verse in enumerate(
                verse for chapter in self.ours for verse in self.verses(chapter)
            )
        }
        found: list[tuple[float, Side, Side]] = []
        told: set[int] = set()
        listed: list[Run] = [
            {**run, "edition": ours, "kjv": theirs}
            for run in self.listed
            for ours, theirs in (
                run["pairs"].items()
                if "pairs" in run
                else [(run["edition"], run["kjv"])]
            )
        ]
        for run in listed:
            ours, theirs = numbered(run)
            if not ours and not theirs:
                # A title, which the King James Bible doesn't number.
                continue
            if ours and all(v.chapter in moved for v in ours):
                for chapter in {v.chapter for v in ours} - told:
                    told.add(chapter)
                    first, there = self.verses(chapter)[0], moved[chapter]
                    found.append(
                        (
                            order[first],
                            range(chapter, chapter + 1),
                            range(there, there + 1),
                        )
                    )
                continue
            if ours and not theirs and run["kjv"]:
                # A title, which the King James Bible doesn't number.
                continue
            if ours and not theirs and all(v.letter for v in ours):
                # Its letter says that the King James Bible lacks it.
                continue
            place = order[ours[0]] if ours else self._place(theirs[0], order)
            last = found[-1] if found else None
            if (
                last
                and isinstance(last[1], list)
                and isinstance(last[2], list)
                and len(ours) == len(theirs)
                and len(last[1]) == len(last[2])
                and last[1]
                and ours
                and _next(last[1][-1], ours[0])
                and _next(last[2][-1], theirs[0])
            ):
                # Lettered verses, which the runs list one by one, run on.
                last[1].extend(ours)
                last[2].extend(theirs)
                continue
            found.append((place, list(ours), list(theirs)))
        return [
            (ours, theirs) for _, ours, theirs in sorted(found, key=lambda row: row[0])
        ]

    def _place(self, verse: Verse, order: Mapping[Verse, int]) -> float:
        """Where a verse that the edition lacks would stand in it: after the
        edition's verse that holds the King James verse before it."""
        chapter = [
            Verse(self.kjv, verse.chapter, int(number))
            for number in self.theirs[str(verse.chapter)]
        ]
        for before in reversed(chapter[: chapter.index(verse)]):
            if held := versification.from_kjv(before, policy=self.policy):
                return min(order[v] for v in held) + 0.5
        # Nothing of its chapter before it: before the chapter's first verse.
        for after in chapter[chapter.index(verse) + 1 :]:
            if held := versification.from_kjv(after, policy=self.policy):
                return order[held[0]] - 0.5
        return len(order)


def table_rows(
    rows: Sequence[tuple[str, str]],
    names: tuple[str, str] | None = None,
    *,
    policy: bible.policy.Policy,
) -> Node:
    """A table: its headings, and a row for each pair of cells. A book's
    table is headed by both Bibles' names for the book, over the headings."""

    heads = (
        policy.title.rsplit(": ", 1)[-1],
        terminology.registry(policy).display("king-james-bible"),
    )

    def content(cell: str, style: str | None) -> list[str | Node]:
        if cell == MISSING:
            # Not a name or a number: set apart from them.
            return ["(", usj.char("it", cell), ")"]
        return [usj.char(style, cell) if style else cell]

    def row(kind: str, cells: tuple[str, ...], style: str | None = None) -> Node:
        return usj.row(
            *(
                usj.cell(f"{kind}{n}", *content(cell, style))
                for n, cell in enumerate(cells, 1)
            )
        )

    return {
        "type": "table",
        "content": [
            *([row("th", names, "bd")] if names else []),
            row("th", heads),
            *(row("tc", r) for r in rows),
        ],
    }


def books_tables(
    inventory: scripture.Inventory,
    facing: scripture.Inventory,
    ours: bible.references.Books,
    theirs: bible.references.Books,
    psalms: Sequence[Node],
    *,
    policy: bible.policy.Policy,
) -> list[Node]:
    """The books' tables in the manifest's book order, each headed by both
    Bibles' names for the book and set off by a blank line; the Psalms' table
    under the editor's words for it."""
    sections: list[Node] = []
    for entry in policy.scripture:
        code = entry["id"]
        if code not in inventory or code not in policy.versification["kjv"]:
            continue
        if code == "PSA":
            values = psalms_rows(inventory, facing, policy=policy)
        else:
            values = Table(code, inventory, facing, policy=policy).rows()
        if not values:
            continue
        names = (
            ours.names[code],
            theirs.names[versification.kjv_book(code, policy=policy)],
        )
        sections += [
            usj.para("ib"),
            *(psalms if code == "PSA" else ()),
            table_rows(values, names, policy=policy),
        ]
    return sections


def psalms_rows(
    inventory: scripture.Inventory,
    facing: scripture.Inventory,
    *,
    policy: bible.policy.Policy,
) -> list[tuple[str, str]]:
    """The Psalms' rows. A psalm that alone holds a King James psalm is
    one row, and such psalms that follow one another are a range of psalms;
    any other psalm is the rows of its verses."""
    table = Table("PSA", inventory, facing, policy=policy)
    found: list[tuple[Side, Side]] = []
    for ours, theirs in table.sides():
        last = found[-1] if found else None
        if (
            last
            and isinstance(ours, range)
            and isinstance(theirs, range)
            and isinstance(last[0], range)
            and isinstance(last[1], range)
            and last[0].stop == ours.start
            and last[1].stop == theirs.start
        ):
            found[-1] = (
                range(last[0].start, ours.stop),
                range(last[1].start, theirs.stop),
            )
        else:
            found.append((ours, theirs))
    apocryphal = versification.apocryphal(policy=policy)
    found += [
        (range(int(chapter), int(chapter) + 1), [])
        for chapter in table.ours
        if all(verse in apocryphal for verse in table.verses(chapter))
    ]
    return row_cells(found)


def names_table(
    printed: tuple[str, ...],
    facing: scripture.Inventory,
    ours: bible.references.Books,
    theirs: bible.references.Books,
    *,
    policy: bible.policy.Policy,
) -> Node:
    """The books that the King James Bible names otherwise, or sets apart in
    its Apocrypha, or lacks, and the parts of books that it sets apart; then
    the books of its Apocrypha that the edition lacks."""
    parts = policy.versification["apocrypha"]
    rows = []
    # The books of the King James Bible's Apocrypha that the edition's books
    # and parts are.
    held: set[str] = set()
    require(
        set(printed) <= set(ours.names),
        "Assembled books missing from the book-name registry",
    )
    for code in printed:
        name = ours.names[code]
        here = [part for part in parts if part["edition"].split(" ")[0] == code]
        held.update(part["kjv"] for part in here if part["kjv"])
        if policy.unit(code)["source"] == "kjv":
            continue
        whole = next((part for part in parts if part["edition"] == code), None)
        if code in policy.versification["old_testament"]:
            other = theirs.names[versification.kjv_book(code, policy=policy)]
            if name != other:
                rows.append((name, other))
        else:
            if whole is None:
                held.add(code)
            rows.append((name, _apocryphal(whole or {"kjv": code}, theirs)))
        rows += [
            (part["title"], _apocryphal(part, theirs))
            for part in here
            if "title" in part
        ]
    canonical = set(versification.kjv_books(policy=policy)) | {
        unit["id"] for unit in policy.scripture if unit["source"] == "kjv"
    }
    rows += [
        (MISSING, _apocryphal({"kjv": code}, theirs))
        for code in theirs.names
        # Its books have chapters; its prefaces have none.
        if code in facing and code not in held and code not in canonical
    ]
    return table_rows(rows, policy=policy)


def _apocryphal(part: VersificationApocrypha, theirs: bible.references.Books) -> str:
    """Where the King James Bible has what it sets apart, if it has it."""
    if part["kjv"] is None:
        return MISSING
    name = theirs.names[part["kjv"]]
    if "chapter" in part:
        name += f" {part['chapter']}"
    return f"{name}, in the Apocrypha"


def page(
    text: str,
    inventory: scripture.Inventory,
    facing: scripture.Inventory,
    ours: bible.references.Books,
    theirs: bible.references.Books,
    *,
    policy: bible.policy.Policy,
    readings: Sequence[Node] | None = None,
) -> Document:
    """One of the editor's pages as it prints: the passages it names between
    braces as the edition cites them, or as the King James Bible numbers
    them, and the tables it asks for, each on a line of its own: the three
    of chapters and verses together, or the readings of the Byzantine text,
    whose blocks the caller gives."""
    requested = TABLES.findall(text)
    require(
        sorted(requested) in ([], ["books", "names", "psalms"], ["readings"]),
        f"Tables asked for, not once each: {requested}",
    )
    require(
        (readings is not None) == (requested == ["readings"]),
        "Readings given to a page that asks for none, or asked for and not given",
    )

    def named(match: re.Match[str]) -> str:
        ways = frozenset(match[1].split())
        require(
            ways <= WAYS and not {"brenton", "kjv"} <= ways,
            f"Passage named to print no known way: {match[0]}",
        )
        passage = parse_passage(match[2])
        if "brenton" in ways:
            require(
                all(
                    v in versification.relabelled(policy=policy) for v in passage.verses
                ),
                f"Passage that the edition doesn't relabel: {match[0]}",
            )
        else:
            lacking = [
                str(v) for v in passage.verses if not scripture.has_verse(inventory, v)
            ]
            require(not lacking, f"Passage that the edition doesn't print: {lacking}")
        targets = (
            tuple(versification.kjv_passages(passage, policy=policy))
            if "kjv" in ways
            else (passage,)
        )
        require(targets, f"Passage that the King James Bible lacks: {match[0]}")
        if "bare" in ways:
            return EDITION.passages.join(EDITION.within(p) for p in targets)
        return EDITION.listed(targets, theirs if "kjv" in ways else ours)

    blocks: list[Node] = []
    # The editor's words for the Psalms stand after {books}, and {psalms}
    # ends them: they print over the Psalms' table, at Psalms' place among
    # the books. Any words after them stay at the end.
    psalms: list[Node] = []
    here = blocks
    for line in text.split("\n"):
        asked = TABLES.fullmatch(line)
        if asked:
            # Without its words, the Psalms' table would run on from the
            # table before it.
            require(
                bool(psalms) if asked[1] == "psalms" else here is blocks,
                "Words for the Psalms missing, or not alone, "
                "between {books} and {psalms}",
            )
            if asked[1] == "readings":
                assert readings is not None
                blocks.extend(readings)
            elif asked[1] == "names":
                blocks.append(
                    names_table(tuple(inventory), facing, ours, theirs, policy=policy)
                )
            elif asked[1] == "books":
                here = psalms
            else:
                blocks += books_tables(
                    inventory, facing, ours, theirs, psalms, policy=policy
                )
                here = blocks
        elif line.strip():
            line = NAMED.sub(named, line)
            require(
                "{" not in line and "}" not in line,
                "Braces left on one of the editor's pages",
            )
            here.extend(usj.parse(line)["content"])
    return usj.document(blocks)
