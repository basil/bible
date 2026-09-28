"""The introduction's numbering table gives the King James number of every
psalm and of every other linked Brenton verse that is numbered differently.

Where Brenton's numbering departs from the King James Bible's, words show it:
a verse shares more of its rarer words with its King James counterpart than
with the verse numbered like it. So the table is checked both ways against
the King James Old Testament, which the Cambridge archive also holds: a
linked verse has a row exactly when its words find a counterpart numbered
differently, and the row names that counterpart. Psalms are compared whole,
since the table numbers them by chapter.
"""

import collections
import functools
import itertools
import math
import re

import pytest

from bible import edition, paths, quotations, versification
from bible.crossrefs import _alias_key, _aliases
from bible.references import EDITION, Passage, parse_passage
from bible.alignment import Verses

# How far a counterpart must outscore the verse numbered like it.
MARGIN = 0.1
# Brenton's table among the appendices sets out the Septuagint's order of
# Jeremias from chapter 25, and the introduction refers the reader to it.
BRENTON_TABLE = ("JER", 25)
# The table's Brenton passage, and its King James one: "Joel 3:1–5" or
# "Psalms 10–112".
PASSAGE = re.compile(r"(.+?) (\d+)(?::(\d+))?(?:–(\d+))?")


def chapter_of(verse):
    return verse.book, verse.chapter


def lettered(verse):
    return bool(verse.letter)


def in_brenton_table(verse):
    code, chapter = chapter_of(verse)
    return code == BRENTON_TABLE[0] and chapter >= BRENTON_TABLE[1]


@pytest.fixture(scope="module")
def introduction():
    return (paths.CONTENT_DIR / "introduction.sfm").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def table(archives, introduction):
    """The table's psalm rows, as chapter lists, and its other rows, by verse."""
    names = edition.books(archives).names
    brenton_codes = {name: code for code, name in names.items()}
    kjv_codes = _aliases(archives)
    psalms, verses = [], {}
    for brenton, kjv in re.findall(
        r"^\\tr \\tc1 (.+?) \\tc2 (.+)$", introduction, re.M
    ):
        name, chapter, first, last = PASSAGE.fullmatch(brenton).groups()
        kjv_name, kjv_chapter, kjv_first, kjv_last = PASSAGE.fullmatch(kjv).groups()
        if first is None:
            assert {name, kjv_name} <= {"Psalm", "Psalms"}, brenton
            psalms.append(
                (
                    list(range(int(chapter), int(last or chapter) + 1)),
                    list(range(int(kjv_chapter), int(kjv_last or kjv_chapter) + 1)),
                )
            )
            continue
        code = brenton_codes[name]
        assert kjv_codes[_alias_key(kjv_name)] == code, kjv
        passage = parse_passage(
            f"{code} {chapter}:{first}" + (f"-{last}" if last else "")
        )
        kjv_passage = parse_passage(
            f"{code} {kjv_chapter}:{kjv_first}" + (f"-{kjv_last}" if kjv_last else "")
        )
        pairs = list(zip(passage.verses, kjv_passage.verses, strict=True))
        assert not set(verses) & {b for b, _ in pairs}, f"Two rows for {brenton}"
        verses.update(pairs)
    return psalms, verses


@pytest.fixture(scope="module")
def linked():
    """Every printed Brenton verse that a quotation link stands for."""
    return {
        verse
        for row in quotations.reviewed_rows()
        for verse in quotations.brenton_verses(row["ot"])
    }


class Counterparts:
    """Brenton's verses and the King James Bible's, compared by their rarer words."""

    def __init__(self, brenton, kjv):
        self.sides = (brenton, kjv)
        bags = [*brenton.values(), *kjv.values()]
        frequency = collections.Counter(w for ws in bags for w in ws)
        self.weight = {w: math.log(len(bags) / (1 + n)) for w, n in frequency.items()}
        self.chapters = []
        for side in self.sides:
            chapters = collections.defaultdict(list)
            for verse in side:
                chapters[chapter_of(verse)].append(verse)
            self.chapters.append(chapters)
        # Cached on the instance, which a class-level cache would keep alive.
        self.pairing = functools.cache(self.pairing)

    def similarity(self, a, b):
        """The weight of the words two bags share, as a share of both bags'."""
        weights = sum(self.weight[w] for w in a) * sum(self.weight[w] for w in b)
        return sum(self.weight[w] for w in a & b) / math.sqrt(weights) if weights else 0

    def pairing(self, code, chapter):
        """Brenton's verses in and beside a chapter, each paired with at most one
        King James verse there, the likest pairs first.

        One to one, so a verse whose own counterpart shares few words, as
        "murder" and "kill" in Deuteronomy 5:17, isn't drawn to a neighbour
        that another verse matches better.
        """
        brenton, kjv = self.sides
        near = [
            [
                v
                for c in range(chapter - 1, chapter + 2)
                for v in side.get((code, c), ())
            ]
            for side in self.chapters
        ]
        pairs = sorted(
            (
                (self.similarity(brenton[b], kjv[k]), b, k)
                for b, k in itertools.product(*near)
            ),
            # Equal scores fall back on the references as written.
            key=lambda pair: (pair[0], str(pair[1]), str(pair[2])),
            reverse=True,
        )
        result, taken = {}, set()
        for score, b, k in pairs:
            if score and b not in result and k not in taken:
                result[b] = k
                taken.add(k)
        return result

    def counterpart(self, verse):
        """The King James verse a Brenton verse's words show to be numbered
        differently, or None."""
        brenton, kjv = self.sides
        match = self.pairing(*chapter_of(verse)).get(verse)
        if match in (None, verse):
            return None
        gain = self.similarity(brenton[verse], kjv[match]) - self.similarity(
            brenton[verse], kjv.get(verse, set())
        )
        return match if gain > MARGIN else None

    def chapter(self, side, code, chapter):
        """A whole chapter's words."""
        verses = self.sides[side]
        return set().union(
            *(verses[v] for v in self.chapters[side].get((code, chapter), ()))
        )


@pytest.fixture(scope="module")
def counterparts(archives, scripture, linked, table):
    codes = {"PSA"} | {v.book for v in [*linked, *table[1]]}
    return Counterparts(
        Verses({code: scripture[code] for code in codes}).words,
        Verses({code: archives["kjv"][code] for code in codes}).words,
    )


def test_the_table_numbers_every_linked_verse_numbered_differently(
    counterparts, table, linked
):
    rows = table[1]
    checked = {
        verse
        for verse in linked
        if not lettered(verse) and verse.book != "PSA" and not in_brenton_table(verse)
    }
    # The table numbers linked verses only.
    assert set(rows) <= checked
    for verse in sorted(checked, key=str):
        assert rows.get(verse) == counterparts.counterpart(verse), str(verse)


def test_the_table_numbers_every_psalm(counterparts, table):
    # Psalm 151, which the King James Bible lacks, has no row.
    psalms = range(1, 151)
    expected = {c: {c} for c in psalms}
    for brenton, kjv in table[0]:
        pairs = (
            [(b, {k}) for b, k in zip(brenton, kjv)]
            if len(brenton) == len(kjv)
            else [(b, set(kjv)) for b in brenton]
        )
        for b, ks in pairs:
            assert expected[b] == {b}, f"Two rows for Psalm {b}"
            expected[b] = ks
    brenton = {c: counterparts.chapter(0, "PSA", c) for c in psalms}
    kjv = {c: counterparts.chapter(1, "PSA", c) for c in psalms}

    def nearest(bag, chapters, c):
        near = [n for n in range(c - 2, c + 3) if n in chapters]
        return max(near, key=lambda n: counterparts.similarity(bag, chapters[n]))

    # Each way, so that a psalm the other side divides or joins is found whole.
    found = collections.defaultdict(set)
    for c in psalms:
        found[c].add(nearest(brenton[c], kjv, c))
        found[nearest(kjv[c], brenton, c)].add(c)
    assert dict(found) == expected


def test_a_linked_lettered_verse_is_named_but_has_no_row(
    archives, introduction, table, linked
):
    # A Septuagint addition that Brenton letters has no King James number.
    books = edition.books(archives)
    for verse in filter(lettered, linked):
        assert EDITION.passage(Passage(verse, verse), books) in introduction, verse
        assert verse not in table[1], verse


def test_the_table_is_as_the_file_has_it(table):
    # Until the file prints the table, the table typed here must agree with it.
    psalms, rows = table
    for verse, kjv in rows.items():
        assert versification.to_kjv(verse) == (kjv,), str(verse)
    for brenton, kjv in psalms:
        found = {
            counterpart.chapter
            for psalm in brenton
            # Every psalm has a second verse, which is never its title alone
            # in both Bibles.
            for verse in versification.verses(f"PSA {psalm}:2")
            for counterpart in versification.to_kjv(verse)
        }
        assert found <= set(kjv), brenton


def test_every_exception_is_a_row(table):
    # Each exception pairs Turpie's English number with Brenton's, so it is
    # exactly a row of the table, unless it names a lettered verse.
    for source in versification.EXCEPTIONS:
        excepted = parse_passage(source).verses
        targets = [versification.lxx_to_edition(verse) for verse in excepted]
        if not lettered(targets[0]):
            assert [table[1].get(t) for t in targets] == excepted, source
