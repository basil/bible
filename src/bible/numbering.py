"""The edition's own pages, written from its files: the table of chapters and
verses, and what the editor's pages cite.

The table says where the chapters and verses of this Old Testament stand in
the King James Bible, for a reader who looks a verse up there. Every row is
written from edition/versification.json, so that the table can say no more
and no less than the file: a chapter that stands whole elsewhere is one row,
a run of verses another, and what either Bible lacks is said to be wanting.

The editor's pages name a passage between braces, by its code, and the build
prints it as the edition cites, or as the King James Bible numbers it, so
that what the pages say of a number is what the file says.
"""

import collections
import re

from bible import edition, versification
from bible.checks import require
from bible.references import EDITION, Passage, Verse, parse_passage, runs

WANTING = "wanting"
# A passage that the editor's pages name: "{PSA 33:13-17}", or with how it is
# to print before it, "{kjv bare PSA 33:13-17}".
NAMED = re.compile(r"\{((?:[a-z]+ )*)([1-4]?[A-Z]{2,3} [^{}]+)\}")
# What the table's page asks for, each on a line of its own.
TABLES = re.compile(r"^\{(names|psalm numbers|psalm verses|psalm rows|books)\}$", re.M)
# How a passage that the pages name may print.
WAYS = {"kjv", "brenton", "bare"}


def _letters(verses):
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


def _next(verse, other):
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


def within(verses):
    """Verses of one book as a table's cell prints them, chapter by chapter."""
    chapters = collections.defaultdict(list)
    for verse in verses:
        chapters[verse.chapter].append(verse)
    return EDITION.passages.join(
        f"{chapter}{EDITION.chapter_verse}{_letters(listed)}"
        for chapter, listed in chapters.items()
    )


def numbered(run):
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

    def __init__(self, code, inventory, kjv_inventory):
        self.code = code
        self.kjv = versification.kjv_book(code)
        self.ours = inventory[code]
        self.theirs = kjv_inventory[self.kjv]
        self.listed = versification.DATA["kjv"].get(code, [])

    def verses(self, chapter):
        return [
            Verse(self.code, int(chapter), int(number), letter)
            for number, letter in (
                re.fullmatch(r"(\d+)([a-z]?)", label).groups()
                for label in self.ours[str(chapter)]
            )
        ]

    def whole(self, chapter):
        """The King James chapter that an edition chapter is, verse for verse
        under the same numbers, if it is one and not the same chapter."""
        facing = set()
        for verse in self.verses(chapter):
            if verse in versification.apocryphal() or verse.letter:
                continue
            found = versification.to_kjv(verse)
            if len(found) != 1 or found[0].number != verse.number:
                return None
            facing.add(found[0].chapter)
        if len(facing) != 1 or facing == {int(chapter)}:
            return None
        return facing.pop()

    def rows(self):
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
        found, told = [], set()
        for run in self.listed:
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
                and len(ours) == len(theirs)
                and len(last[1]) == len(last[2])
                and last[1]
                and ours
                and _next(last[1][-1], ours[0])
                and _next(last[2][-1], theirs[0])
            ):
                # Lettered verses, which the file lists one by one, run on.
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

    def _place(self, verse, order):
        """Where a verse that the edition lacks would stand in it: after the
        edition's verse that holds the King James verse before it."""
        chapter = [
            Verse(self.kjv, verse.chapter, int(number))
            for number in self.theirs[str(verse.chapter)]
        ]
        for before in reversed(chapter[: chapter.index(verse)]):
            if held := versification.from_kjv(before):
                return order[held[-1]] + 0.5
        # Nothing of its chapter before it: before the chapter's first verse.
        for after in chapter[chapter.index(verse) + 1 :]:
            if held := versification.from_kjv(after):
                return order[held[0]] - 0.5
        return len(order)


def kjv_inventory(archives):
    """The King James Bible's chapters and verses, book by book."""
    from bible.usfm import inventory

    return {
        code: inventory(text)["chapters"]
        for code, text in archives["kjv"].items()
        if "\\c " in text
    }


def table_rows(rows, heads):
    return "".join(
        [f"\\tr \\th1 {heads[0]} \\th2 {heads[1]}\n"]
        + [f"\\tr \\tc1 {ours} \\tc2 {theirs}\n" for ours, theirs in rows]
    )


def books_tables(archives):
    """Every book's table that has rows, under both Bibles' names for it."""
    ours, theirs = edition.books(archives), edition.kjv_books(archives)
    inventory = versification.edition_inventory(archives)
    facing = kjv_inventory(archives)
    sections = []
    for code in versification.DATA["old_testament"]:
        if code == "PSA":
            continue
        rows = Table(code, inventory, facing).rows()
        if not rows:
            continue
        name, other = ours.names[code], theirs.names[versification.kjv_book(code)]
        heading = name if name == other else f"{name} ({other})"
        heads = ("This edition", "King James Bible") if name == other else (name, other)
        sections.append(f"\\is1 {heading}\n" + table_rows(rows, heads))
    return "".join(sections)


def _spans(numbers):
    """Numbers as they print in a list: "3–8, 11, 17–21"."""
    spans, numbers = [], sorted(numbers)
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

    def __init__(self, archives):
        inventory = versification.edition_inventory(archives)
        self.table = Table("PSA", inventory, kjv_inventory(archives))
        self.psalms = {}
        for chapter in self.table.ours:
            facing = collections.Counter()
            steps = set()
            for verse in self.table.verses(chapter):
                if verse in versification.apocryphal():
                    continue
                found = [
                    v
                    for v in versification.to_kjv(verse)
                    if v.number != versification.TITLE
                ]
                if len(found) != 1:
                    steps.add(None if found else "title")
                    continue
                facing[found[0].chapter] += 1
                steps.add(verse.number - found[0].number)
            self.psalms[int(chapter)] = (sorted(facing), steps - {"title"})

    def numbers(self):
        """Rows of psalm numbers: runs of psalms that are each one King
        James psalm, by the same difference; psalms that are together one;
        and a psalm that is more than one, or none."""
        groups = []
        for psalm, (facing, _) in self.psalms.items():
            last = groups[-1] if groups else None
            if (
                last
                and facing
                and last["psalms"][-1] == psalm - 1
                and (
                    # Of one King James psalm with the psalm before...
                    (last["facing"] == facing and len(facing) == 1)
                    # ...or of the next, as the psalm before is of its own.
                    or (
                        last["step"] is not None
                        and len(facing) == 1
                        and facing[0] - psalm == last["step"]
                        and facing[0] == last["facing"][-1] + 1
                    )
                )
            ):
                if last["facing"] == facing:
                    last["step"] = None
                else:
                    last["facing"].append(facing[0])
                last["psalms"].append(psalm)
            else:
                step = facing[0] - psalm if len(facing) == 1 else None
                groups.append({"psalms": [psalm], "facing": list(facing), "step": step})
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

    def steps(self):
        """The psalms whose verses are each so many higher than the King
        James Bible's, by how many, and the psalms whose verses differ by no
        one number."""
        by_step, uneven = collections.defaultdict(list), []
        for psalm, (facing, steps) in self.psalms.items():
            if steps <= {0} or not facing:
                continue
            (step,) = steps if len(steps) == 1 else (None,)
            if step in STEPS:
                by_step[step].append(psalm)
            else:
                uneven.append(psalm)
        return dict(sorted(by_step.items())), uneven

    def uneven_rows(self):
        """The rows of the psalms whose verses differ by no one number."""
        _, uneven = self.steps()
        rows = []
        for run in self.table.listed:
            ours, theirs = numbered(run)
            if ours and ours[0].chapter in uneven and theirs:
                rows.append((within(ours), within(theirs)))
        return rows


def _psalms(first, last):
    if first == last:
        return f"Psalm {first}"
    return f"Psalms {first}{EDITION.range}{last}"


# A title of one verse, or of two.
STEPS = {1: "one lower", 2: "two lower"}


def psalm_numbers(archives):
    return table_rows(Psalter(archives).numbers(), ("This edition", "King James Bible"))


def psalm_verses(archives):
    steps, _ = Psalter(archives).steps()
    return table_rows(
        [(_spans(psalms), STEPS[step]) for step, psalms in steps.items()],
        ("Psalms", "King James verse"),
    )


def psalm_rows(archives):
    return table_rows(Psalter(archives).uneven_rows(), ("Psalms", "King James Bible"))


def names_table(archives):
    """The books that the King James Bible names otherwise, or sets apart in
    its Apocrypha, or lacks, and the parts of books that it sets apart."""
    ours, theirs = edition.books(archives), edition.kjv_books(archives)
    parts = versification.DATA["apocrypha"]
    rows = []
    for code, name in ours.names.items():
        if edition.scripture_unit(code)["source"] == "kjv":
            continue
        whole = next((part for part in parts if part["edition"] == code), None)
        if code in versification.DATA["old_testament"]:
            other = theirs.names[versification.kjv_book(code)]
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


def _apocryphal(part, theirs):
    """Where the King James Bible has what it sets apart, if it has it."""
    if part["kjv"] is None:
        return WANTING
    name = theirs.names[part["kjv"]]
    if "chapter" in part:
        name += f" {part['chapter']}"
    return f"{name}, in the Apocrypha"


def tables(text, archives):
    """The table's page with its tables written in."""
    written = {
        "names": names_table,
        "psalm numbers": psalm_numbers,
        "psalm verses": psalm_verses,
        "psalm rows": psalm_rows,
        "books": books_tables,
    }
    asked = TABLES.findall(text)
    require(
        sorted(asked) == sorted(written), f"Tables asked for, not once each: {asked}"
    )
    return TABLES.sub(lambda match: written[match[1]](archives).rstrip("\n"), text)


def page(text, archives):
    """One of the editor's pages as it prints: its tables written in, if it
    asks for any, and the passages it names printed."""
    if TABLES.search(text):
        text = tables(text, archives)
    return cited(text, archives)


def cited(text, archives):
    """One of the editor's pages with the passages it names printed."""
    ours, theirs = edition.books(archives), edition.kjv_books(archives)
    inventory = versification.edition_inventory(archives)

    def printed(match):
        ways, written = set(match[1].split()), match[2]
        require(ways <= WAYS, f"Passage named to print no known way: {match[0]}")
        passage = parse_passage(written)
        books = ours
        if "brenton" in ways:
            # Brenton's label for what the edition relabels.
            require(
                all(v in versification.relabelled() for v in passage.verses),
                f"Passage that the edition doesn't relabel: {match[0]}",
            )
            passages = [passage]
        else:
            labels = inventory.get(passage.first.book, {}).get(
                str(passage.first.chapter), []
            )
            lacking = [
                str(v) for v in passage.verses if f"{v.number}{v.letter}" not in labels
            ]
            require(not lacking, f"Passage that the edition doesn't print: {lacking}")
            passages = [passage]
            if "kjv" in ways:
                passages = versification.kjv_passages(passage)
                require(passages, f"Passage that the King James Bible lacks: {written}")
                books = theirs
        if "bare" in ways:
            return EDITION.passages.join(EDITION.within(p) for p in passages)
        return EDITION.listed(passages, books)

    text = NAMED.sub(printed, text)
    require(
        "{" not in text and "}" not in text,
        "Braces left on one of the editor's pages",
    )
    return text
