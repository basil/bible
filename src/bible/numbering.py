"""The edition's own pages, written from its files: the table of chapters and
verses, and what the editor's pages cite.

The table says where the chapters and verses of this Old Testament stand in
the King James Bible, for a reader who looks a verse up there. Every row is
written from the runs that the build works out (places.py), so that the table
can say no more and no less than they do: a chapter that stands whole
elsewhere is one row, a run of verses another, and what either Bible lacks is
said to be wanting.

The editor's pages name a passage between braces, by its code, and the build
prints it as the edition cites, or as the King James Bible numbers it, so
that what the pages say of a number is what the runs say.
"""

from __future__ import annotations

import collections
import re
from collections.abc import Mapping, Sequence
from typing import TypedDict

import bible.policy
import bible.references
from bible import scripture, usj, versification
from bible.checks import require
from bible.policy_schema import Run, VersificationApocrypha
from bible.references import EDITION, Verse, parse_passage
from bible.usj import Document, Node


class PsalmGroup(TypedDict):
    psalms: list[int]
    facing: list[int]
    step: int | None


WANTING = "wanting"
# A passage that the editor's pages name: "{PSA 33:13-17}", or with how it is
# to print before it, "{kjv bare PSA 33:13-17}".
NAMED = re.compile(r"\{((?:[a-z]+ )*)([1-4]?[A-Z]{2,3} [^{}]+)\}")
# What the table's page asks for, each on a line of its own.
TABLES = re.compile(r"^\{(names|psalm numbers|psalm verses|psalm rows|books)\}$", re.M)
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
    ours = versification.verses(run["edition"]) if run["edition"] else []
    theirs = versification.verses(run["kjv"]) if run["kjv"] else []
    if len(ours) == len(theirs):
        pairs = [
            (v, o) for v, o in zip(ours, theirs) if o.number != versification.TITLE
        ]
        return [v for v, _ in pairs], [o for _, o in pairs]
    return ours, [v for v in theirs if v.number != versification.TITLE]


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
        under the same numbers, if it is one and not the same chapter."""
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
        return facing.pop()

    def rows(self) -> list[tuple[str, str]]:
        """The book's rows as (edition cell, King James cell), in the
        edition's order; what the edition lacks stands where the King James
        Bible has it, among the rows of its chapter."""
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
        found: list[tuple[float, str | list[Verse], str | list[Verse]]] = []
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
                    first = self.verses(chapter)[0]
                    found.append((order[first], str(chapter), str(moved[chapter])))
                continue
            if ours and not theirs and run["kjv"]:
                # A title, which the King James Bible doesn't number.
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
        cells = [
            (
                place,
                ours if isinstance(ours, str) else within(ours) if ours else WANTING,
                (
                    theirs
                    if isinstance(theirs, str)
                    else within(theirs) if theirs else WANTING
                ),
            )
            for place, ours, theirs in found
        ]
        # A run that keeps its numbers, against the table or the words, tells
        # a reader nothing.
        return [
            (ours, theirs)
            for _, ours, theirs in sorted(cells, key=lambda row: row[0])
            if ours != theirs
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
                return order[held[-1]] + 0.5
        # Nothing of its chapter before it: before the chapter's first verse.
        for after in chapter[chapter.index(verse) + 1 :]:
            if held := versification.from_kjv(after, policy=self.policy):
                return order[held[0]] - 0.5
        return len(order)


def table_rows(rows: Sequence[tuple[str, str]], heads: tuple[str, str]) -> Node:
    """A table: its headings, and a row for each pair of cells."""

    def row(kind: str, cells: tuple[str, ...]) -> Node:
        return {
            "type": "table:row",
            "marker": "tr",
            "content": [
                {
                    "type": "table:cell",
                    "marker": f"{kind}{n}",
                    "align": "start",
                    "content": [cell],
                }
                for n, cell in enumerate(cells, 1)
            ],
        }

    return {
        "type": "table",
        "content": [row("th", heads), *(row("tc", r) for r in rows)],
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
    """The numbering sections in the manifest's book order."""
    sections: list[Node] = []
    for entry in policy.scripture:
        code = entry["id"]
        if code not in inventory or code not in policy.versification["old_testament"]:
            continue
        if code == "PSA":
            sections.extend(psalms)
            continue
        values = Table(code, inventory, facing, policy=policy).rows()
        if not values:
            continue
        name, other = (
            ours.names[code],
            theirs.names[versification.kjv_book(code, policy=policy)],
        )
        heading = name if name == other else f"{name} ({other})"
        heads = ("This edition", "King James Bible") if name == other else (name, other)
        sections.extend((usj.para("is1", heading), table_rows(values, heads)))
    return sections


def _spans(numbers: list[int]) -> str:
    """Numbers as they print in a list: "3–8, 11, 17–21"."""
    spans: list[list[int]] = []
    numbers = sorted(numbers)
    for number in numbers:
        if spans and spans[-1][1] == number - 1:
            spans[-1][1] = number
        else:
            spans.append([number, number])
    return EDITION.verses.join(
        str(a) if a == b else f"{a}{EDITION.range}{b}" for a, b in spans
    )


class Psalter:
    """The Psalms, which differ from the King James Bible's in nearly every
    psalm, and mostly in one of three ways: in the psalm's number, in the
    count of its verses by one for its title, or by two."""

    def __init__(
        self,
        facing: scripture.Inventory,
        *,
        printed: scripture.Inventory,
        policy: bible.policy.Policy,
    ) -> None:
        self.policy = policy
        inventory = printed
        self.table = Table("PSA", inventory, facing, policy=policy)
        self.psalms: dict[int, tuple[list[int], set[int | None | str]]] = {}
        for chapter in self.table.ours:
            counts: collections.Counter[int] = collections.Counter()
            steps: set[int | str | None] = set()
            for verse in self.table.verses(chapter):
                if verse in versification.apocryphal(policy=policy):
                    continue
                found = [
                    v
                    for v in versification.to_kjv(verse, policy=policy)
                    if v.number != versification.TITLE
                ]
                if len(found) != 1:
                    steps.add(None if found else "title")
                    continue
                counts[found[0].chapter] += 1
                steps.add(verse.number - found[0].number)
            self.psalms[int(chapter)] = (sorted(counts), steps - {"title"})

    def numbers(self) -> list[tuple[str, str]]:
        """Rows of psalm numbers: runs of psalms that are each one King
        James psalm, by the same difference; psalms that are together one;
        and a psalm that is more than one, or none."""
        # Psalms that are together one King James psalm stand together first,
        # so that the first of them doesn't run on with the psalms before it.
        together: list[PsalmGroup] = []
        for psalm, (facing, _) in self.psalms.items():
            last = together[-1] if together else None
            if (
                last
                and len(facing) == 1
                and last["facing"] == facing
                and last["psalms"][-1] == psalm - 1
            ):
                last["psalms"].append(psalm)
            else:
                together.append(
                    {"psalms": [psalm], "facing": list(facing), "step": None}
                )
        groups: list[PsalmGroup] = []
        for unit in together:
            psalms, facing = unit["psalms"], unit["facing"]
            # Each one King James psalm, so many from its own number.
            step = facing[0] - psalms[0] if len(psalms) == len(facing) == 1 else None
            last = groups[-1] if groups else None
            if (
                last
                and step is not None
                and last["step"] == step
                and last["psalms"][-1] == psalms[0] - 1
            ):
                last["psalms"].append(psalms[0])
                last["facing"].append(facing[0])
            else:
                groups.append({"psalms": psalms, "facing": facing, "step": step})
        rows = [
            (
                _psalms(group["psalms"][0], group["psalms"][-1]),
                (
                    _psalms(group["facing"][0], group["facing"][-1])
                    if group["facing"]
                    else WANTING
                ),
            )
            for group in groups
        ]
        return [row for row in rows if row[0] != row[1]]

    def steps(self) -> tuple[dict[int, list[int]], list[int]]:
        """The psalms whose verses are each so many higher than the King
        James Bible's, by how many, and the psalms whose verses differ by no
        one number."""
        by_step: collections.defaultdict[int, list[int]] = collections.defaultdict(list)
        uneven: list[int] = []
        for psalm, (facing, steps) in self.psalms.items():
            if steps <= {0} or not facing:
                continue
            (step,) = steps if len(steps) == 1 else (None,)
            if isinstance(step, int) and step in STEPS:
                by_step[step].append(psalm)
            else:
                uneven.append(psalm)
        return dict(sorted(by_step.items())), uneven

    def uneven_rows(self) -> list[tuple[str, str]]:
        """The rows of the psalms whose verses differ by no one number."""
        _, uneven = self.steps()
        rows = []
        for run in self.table.listed:
            ours, theirs = numbered(run)
            if ours and ours[0].chapter in uneven and theirs:
                rows.append((within(ours), within(theirs)))
        return rows


def _psalms(first: int, last: int) -> str:
    if first == last:
        return f"Psalm {first}"
    return f"Psalms {first}{EDITION.range}{last}"


# A title of one verse, or of two.
STEPS = {1: "one lower", 2: "two lower"}


def names_table(
    printed: tuple[str, ...],
    ours: bible.references.Books,
    theirs: bible.references.Books,
    *,
    policy: bible.policy.Policy,
) -> Node:
    """The books that the King James Bible names otherwise, or sets apart in
    its Apocrypha, or lacks, and the parts of books that it sets apart."""
    parts = policy.versification["apocrypha"]
    rows = []
    require(
        set(printed) <= set(ours.names),
        "Assembled books missing from the book-name registry",
    )
    for code in printed:
        name = ours.names[code]
        if policy.unit(code)["source"] == "kjv":
            continue
        whole = next((part for part in parts if part["edition"] == code), None)
        if code in policy.versification["old_testament"]:
            other = theirs.names[versification.kjv_book(code, policy=policy)]
            if name != other:
                rows.append((name, other))
        else:
            rows.append((name, _apocryphal(whole or {"kjv": code}, theirs)))
        rows += [
            (part["title"], _apocryphal(part, theirs))
            for part in parts
            if part["edition"].split(" ")[0] == code and "title" in part
        ]
    return table_rows(rows, ("This edition", "King James Bible"))


def _apocryphal(part: VersificationApocrypha, theirs: bible.references.Books) -> str:
    """Where the King James Bible has what it sets apart, if it has it."""
    if part["kjv"] is None:
        return WANTING
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
    psalms: str = "",
) -> Document:
    """One of the editor's pages as it prints: the passages it names between
    braces as the edition cites them, or as the King James Bible numbers
    them, and the tables it asks for, each on a line of its own."""
    requested = TABLES.findall(text)
    require(
        not requested
        or sorted(requested)
        in (
            ["books", "names"],
            ["psalm numbers", "psalm rows", "psalm verses"],
        ),
        f"Tables asked for, not once each: {requested}",
    )
    tables: dict[str, list[Node]] = {}
    if "books" in requested:
        require(bool(psalms), "Missing Psalms numbering section")
        psalm_section = page(psalms, inventory, facing, ours, theirs, policy=policy)
        tables = {
            "names": [names_table(tuple(inventory), ours, theirs, policy=policy)],
            "books": books_tables(
                inventory,
                facing,
                ours,
                theirs,
                list(usj.objects(psalm_section["content"])),
                policy=policy,
            ),
        }
    elif requested:
        psalter = Psalter(facing, printed=inventory, policy=policy)
        steps, _ = psalter.steps()
        tables = {
            "psalm numbers": [
                table_rows(psalter.numbers(), ("This edition", "King James Bible"))
            ],
            "psalm verses": [
                table_rows(
                    [(_spans(numbers), STEPS[step]) for step, numbers in steps.items()],
                    ("Psalms", "King James verse"),
                )
            ],
            "psalm rows": [
                table_rows(psalter.uneven_rows(), ("Psalms", "King James Bible"))
            ],
        }

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
                str(v)
                for v in passage.verses
                if f"{v.number}{v.letter}"
                not in inventory.get(v.book, {}).get(str(v.chapter), ())
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

    blocks = []
    for line in text.split("\n"):
        asked = TABLES.fullmatch(line)
        if asked:
            blocks += tables[asked[1]]
        elif line.strip():
            line = NAMED.sub(named, line)
            require(
                "{" not in line and "}" not in line,
                "Braces left on one of the editor's pages",
            )
            blocks += usj.parse(line)["content"]
    return usj.document(blocks)
