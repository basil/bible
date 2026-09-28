"""Each quotation link lands on the verses whose words it quotes.

Existence checks can't see a link that is off by a verse: a Psalm title
counted or not, a chapter renumbered, a Septuagint addition that Brenton
letters. Words can. A quotation's KJV passage should share more of its rarer
words with its Brenton target than with a window of the same size a few
verses either way, so a misplaced target is outscored by the true one beside
it. A reviewed target that a neighbour outscores, and one that shares too
little with its quotation for the comparison to mean anything, are listed in
edition/quotations.json with the reason.
"""

import collections

import pytest

from bible import quotations, versification
from bible.alignment import Verses
from bible.references import Passage, Verse

# How far a neighbour must outscore a target to flag it.
MARGIN = 0.05
# A target scoring below this can't outscore a neighbour by the margin, so
# the check can't vouch for it.
UNSCORED = 2 * MARGIN
SHIFTS = (-3, -2, -1, 1, 2, 3)


@pytest.fixture(scope="module")
def verses(scripture):
    return Verses(scripture)


def passages(row):
    return quotations.nt_verses(row["nt"]), quotations.brenton_verses(row["ot"])


def alignments(verses, rows, move=0):
    """Each row's score at its target, moved by `move` verses, and its best rival's.

    A neighbour that another quotation links from one of the row's New
    Testament verses is its sibling, not its rival: the commandments of the
    Decalogue are quoted together.
    """
    rows = [(row, *passages(row)) for row in rows]
    linked = collections.defaultdict(lambda: collections.defaultdict(set))
    for row, nt, ot in rows:
        for verse in nt:
            linked[verse][row["id"]].update(ot)
    result = {}
    for row, nt, ot in rows:
        if move and (ot := verses.shifted(ot, move)) is None:
            continue
        siblings = {
            verse
            for v in nt
            for other, targets in linked[v].items()
            if other != row["id"]
            for verse in targets
        } - set(ot)
        quotation = verses.bag(nt)
        rivals = [
            verses.score(quotation, verses.bag(window))
            for k in SHIFTS
            if (window := verses.shifted(ot, k)) and not siblings & set(window)
        ]
        result[row["id"]] = (
            verses.score(quotation, verses.bag(ot)),
            max(rivals, default=0),
        )
    return result


def outscored(scores):
    return {rid for rid, (target, rival) in scores.items() if rival > target + MARGIN}


def test_every_link_lands_on_the_words_it_quotes(verses):
    scores = alignments(verses, quotations.reviewed_rows())
    reviewed = quotations.DECISIONS["alignment"]
    for kind in ("outscored", "unscored"):
        assert all(reviewed[kind].values()), f"Unexplained {kind} alignment"
    assert outscored(scores) == set(reviewed["outscored"])
    assert {rid for rid, (target, _) in scores.items() if target < UNSCORED} == set(
        reviewed["unscored"]
    )


@pytest.mark.parametrize("move", [-1, 1])
def test_a_link_off_by_a_verse_is_caught(verses, move):
    # The check must still tell a verse from its neighbour: most targets, moved
    # one verse, are outscored by the true one.
    scores = alignments(verses, quotations.reviewed_rows(), move)
    assert len(outscored(scores)) >= 0.9 * len(scores)


def test_a_misplaced_link_is_outscored(verses, patched):
    # 2 Corinthians 9:7 quotes Brenton's lettered Proverbs 22:8a; without its
    # mapping exception, the link would land on 22:8.
    [row] = [r for r in quotations.reviewed_rows() if r["id"] == "Q216"]
    assert alignments(verses, [row])["Q216"][0] >= UNSCORED
    del patched(versification, "EXCEPTIONS")["PRO 22:8"]
    target, rival = alignments(verses, [row])["Q216"]
    assert rival > target + MARGIN


def waived(rows):
    """The rows whose whole alignment is reviewed, and so need no finer check."""
    reviewed = quotations.DECISIONS["alignment"]
    return {row["id"] for row in rows} & {*reviewed["outscored"], *reviewed["unscored"]}


def each_passage(rows):
    """A row for each Septuagint passage of a row that cites several.

    The row's other passages are its siblings, not its rivals, and its own
    score would let a well-placed first passage carry a misplaced second.
    """
    return [
        {**row, "id": f"{row['id']} {passage}", "ot": [passage]}
        for row in rows
        if len(row["ot"]) > 1 and row["id"] not in waived(rows)
        for passage in row["ot"]
    ]


def test_every_passage_of_a_link_lands_on_the_words_it_quotes(verses):
    scores = alignments(verses, each_passage(quotations.reviewed_rows()))
    reviewed = quotations.DECISIONS["alignment"]["passages"]
    assert all(reviewed.values()), "Unexplained passage alignment"
    flagged = outscored(scores) | {
        key for key, (target, _) in scores.items() if target < UNSCORED
    }
    assert flagged == set(reviewed)


def range_ends(verses, rows):
    """How much of each range's first and last verse the other side quotes.

    A range that runs a verse too far, into context the quotation doesn't
    reach, ends on a verse that shares little with it. The verse is measured
    by its own words, since a quotation may take few of a long range's.
    """
    result = {}
    skip = waived(rows)
    for row in rows:
        if row["id"] in skip:
            continue
        nt, ot = passages(row)
        sides = (
            ([p.verses for p in row["nt"]], verses.bag(ot)),
            ([quotations.brenton_verses([p]) for p in row["ot"]], verses.bag(nt)),
        )
        for spans, other in sides:
            for span in spans:
                for verse in {span[0], span[-1]} if len(span) > 1 else ():
                    result[f"{row['id']} {verse}"] = verses.score(
                        verses.words[verse], other
                    )
    return result


def test_every_range_ends_on_quoted_words(verses):
    scores = range_ends(verses, quotations.reviewed_rows())
    reviewed = quotations.DECISIONS["alignment"]["range_ends"]
    assert all(reviewed.values()), "Unexplained range end"
    assert {key for key, score in scores.items() if score < UNSCORED} == set(reviewed)


@pytest.mark.parametrize("side", ["nt", "ot"])
def test_a_range_run_a_verse_too_far_is_caught(verses, side):
    # Most ranges, run on a verse, end on one the other side doesn't quote.
    rows = quotations.reviewed_rows()
    caught = total = 0
    for row in rows:
        for i, passage in enumerate(row[side]):
            if passage.first.letter or row["id"] in waived(rows):
                continue
            last = passage.last
            next_verse = Verse(last.book, last.chapter, last.number + 1)
            beyond = next_verse
            if side == "ot":
                beyond = versification.lxx_to_edition(beyond)
            if beyond not in verses.words:
                continue
            run_on = {**row, side: [*row[side]]}
            run_on[side][i] = Passage(passage.first, next_verse)
            total += 1
            caught += range_ends(verses, [run_on])[f"{row['id']} {beyond}"] < UNSCORED
    assert caught >= 0.6 * total
