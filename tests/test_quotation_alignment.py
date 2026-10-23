"""Each quotation link lands on the verses whose words it quotes.

Existence checks can't see a link that is off by a verse: a Psalm title
counted or not, a chapter renumbered, a Septuagint addition that Brenton
letters. Words can. A quotation's KJV passage should share more of its rarer
words with its Brenton target than with a window of the same size a few
verses either way, so a misplaced target is outscored by the true one beside
it. A reviewed target that a neighbour outscores, and one that shares too
little with its quotation for the comparison to mean anything, are listed
below with the reason; the build reads none of this.
"""

from __future__ import annotations

import collections
import re
from collections.abc import Mapping
from typing import Literal

import pytest
from conftest import changed

import bible.alignment
import bible.pipeline
import bible.policy
from bible import quotations, versification
from bible.alignment import Verses
from bible.references import Passage, Verse, verse_at, verses_of

# How far a neighbour must outscore a target to flag it.
MARGIN = 0.05
# A target scoring below this can't outscore a neighbour by the margin, so
# the check can't vouch for it.
UNSCORED = 2 * MARGIN
SHIFTS = (-3, -2, -1, 1, 2, 3)

# The targets a neighbour outscores, each reviewed and explained.
OUTSCORED_TARGETS = {
    "Q103": (
        "John 8:17 gives the sense of the law of two witnesses, 'the testimony of two men is true'; Deuteronomy 19:17's 'two men' belong to the next provision, and share the words by chance."
    ),
    "Q222": (
        "James 5:20's 'hide a multitude of sins' follows the Hebrew, where Brenton's Proverbs 10:12 has 'affection covers all that do not love strife' (Turpie's class E); 10:14 shares only 'hide', by chance."
    ),
}

# The targets that share too little with their quotation to be scored.
UNSCORED_TARGETS = {
    "Q058": (
        "2 Timothy 2:19's 'the Lord knoweth them that are his' is Brenton's 'God has visited and known those that are his': knoweth and known don't meet, and the words they share are common."
    ),
    "Q116": (
        "Hebrews 12:21's 'I exceedingly fear and quake' renders what Brenton gives as 'I was greatly terrified', in other words."
    ),
    "Q125": (
        "Matthew 2:23's 'He shall be called a Nazarene' rests on the Hebrew netzer, the branch of Isaiah 11:1, which Brenton renders 'blossom'; the pun has no English words in common."
    ),
    "Q128": (
        "1 Corinthians 1:31's 'he that glorieth, let him glory' is Brenton's 'let him that boasts boast', in other words."
    ),
    "Q197": (
        "Matthew 8:17's 'Himself took our infirmities, and bare our sicknesses' follows the Hebrew, where Brenton's Isaiah 53:4 has 'He bears our sins and is pained for us' (Turpie's class E)."
    ),
    "Q214": (
        "Romans 12:19 shares only 'vengeance' with Brenton's 'In the day of vengeance I will recompense', and its exhortation around the quotation outweighs it."
    ),
    "Q222": (
        "James 5:20 follows the Hebrew 'love covers all sins', where Brenton's Proverbs 10:12 has 'affection covers all that do not love strife' (Turpie's class E), with no word in common."
    ),
}

# A passage of a row citing several that does not score alone.
UNSCORED_PASSAGES = {
    "Q108 GEN 12:3": (
        "Galatians 3:8's preface, 'the scripture, foreseeing that God would justify the heathen through faith, preached before the gospel unto Abraham', outweighs 'in thee shall all nations be blessed', so the promise does not score alone; with Genesis 18:18, which names Abraham, the two pass together."
    ),
}

# The ends of ranges that the other side quotes no words of.
UNSCORED_RANGE_ENDS = {
    "Q065 EXO 20:17": (
        "Mark 10:19's 'Defraud not' stands for the tenth commandment, 'Thou shalt not covet', as Turpie argues on page 65; it shares no word with it."
    ),
    "Q065 DEU 5:21": (
        "As at Exodus 20:17: Turpie reads Mark 10:19's 'Defraud not' as the tenth commandment."
    ),
    "Q107 LEV 26:11": (
        "2 Corinthians 6:16's 'I will dwell in them' is Brenton's 'I will set my tabernacle among you', in other words; Turpie prints the verse, abridged to that clause."
    ),
    "Q133 ISA 52:12": (
        "Turpie heads Isaiah 52:11-12 and prints verse 12's first clause, 'for the Lord shall go first before you', though 2 Corinthians 6:17 takes no words from it."
    ),
    "Q250 ISA 59:21": (
        "Romans 11:27 takes only 'this is my covenant unto them' from the long verse, and Turpie prints no more of it."
    ),
    "Q256 1PE 3:14": (
        "The quotation begins partway through the verse, after 'if ye suffer for righteousness' sake, happy are ye', and its 'be not afraid of their terror, neither be troubled' is Brenton's 'fear not ye their fear, neither be dismayed', in other words."
    ),
    "Q268 MAT 27:10": (
        "Matthew 27:10's 'gave them for the potter's field' follows the Hebrew, where Brenton's Zacharias 11:13 has 'cast them into the furnace' (Turpie's class E)."
    ),
    "Q273 ACT 7:26": (
        "Stephen's 'Sirs, ye are brethren; why do ye wrong one to another?' gives Moses' 'Wherefore smitest thou thy neighbour?' in other words; Turpie prints it as quoted, 'If verse 26 be reckoned as cited' (page 284)."
    ),
}


@pytest.fixture(scope="module")
def verses(edition: bible.pipeline.Edition) -> bible.alignment.Verses:
    """The words of every verse the edition prints, in both testaments."""
    return Verses({code: edition.documents[code] for code in edition.scripture})


@pytest.fixture(scope="module")
def rows(policy: bible.policy.Policy) -> list[quotations.ReviewedRow]:
    return quotations.reviewed_rows(policy=policy)


def passages(
    row: quotations.ReviewedRow, policy: bible.policy.Policy
) -> tuple[list[Verse], list[Verse]]:
    return (
        verses_of(row["nt"]),
        quotations.brenton_verses(row["ot"], policy=policy),
    )


def alignments(
    verses: bible.alignment.Verses,
    rows: list[quotations.ReviewedRow],
    policy: bible.policy.Policy,
    move: int = 0,
) -> dict[str, tuple[float, float]]:
    """Each row's score at its target, moved by `move` verses, and its best rival's.

    A neighbour that another quotation links from one of the row's New
    Testament verses is its sibling, not its rival: the commandments of the
    Decalogue are quoted together.
    """
    parsed = [(row, *passages(row, policy)) for row in rows]
    linked: collections.defaultdict[Verse, collections.defaultdict[str, set[Verse]]] = (
        collections.defaultdict(lambda: collections.defaultdict(set))
    )
    for row, nt, ot in parsed:
        for verse in nt:
            linked[verse][row["id"]].update(ot)
    result = {}
    for row, nt, ot in parsed:
        if move:
            shifted = verses.shifted(ot, move)
            if shifted is None:
                continue
            ot = shifted
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


def flagged(scores: Mapping[str, tuple[float, float]]) -> tuple[set[str], ...]:
    """The targets that a neighbour outscores, and those that score too
    little for the comparison to mean anything."""
    return (
        {key for key, (target, rival) in scores.items() if rival > target + MARGIN},
        {key for key, (target, _) in scores.items() if target < UNSCORED},
    )


def test_every_link_lands_on_the_words_it_quotes(
    verses: bible.alignment.Verses,
    rows: list[quotations.ReviewedRow],
    policy: bible.policy.Policy,
) -> None:
    outscored, unscored = flagged(alignments(verses, rows, policy))
    assert outscored == set(OUTSCORED_TARGETS)
    assert unscored == set(UNSCORED_TARGETS)


@pytest.mark.parametrize("move", [-1, 1])
def test_a_link_off_by_a_verse_is_caught(
    verses: bible.alignment.Verses,
    rows: list[quotations.ReviewedRow],
    policy: bible.policy.Policy,
    move: int,
) -> None:
    # The check must still tell a verse from its neighbour: most targets, moved
    # one verse, are outscored by the true one.
    scores = alignments(verses, rows, policy, move)
    assert len(flagged(scores)[0]) >= 0.9 * len(scores) > 0


def test_a_misplaced_link_is_outscored(
    verses: bible.alignment.Verses,
    rows: list[quotations.ReviewedRow],
    policy: bible.policy.Policy,
) -> None:
    # 2 Corinthians 9:7 quotes Brenton's lettered Proverbs 22:8a; without its
    # mapping exception, the link would land on 22:8.
    row = [next(row for row in rows if row["id"] == "Q216")]
    assert alignments(verses, row, policy)["Q216"][0] >= UNSCORED
    unmapped = changed(
        policy, "quotations", lambda data: data["lxx_to_edition"].pop("PRO 22:8")
    )
    assert flagged(alignments(verses, row, unmapped))[0] == {"Q216"}


def unwaived(rows: list[quotations.ReviewedRow]) -> list[quotations.ReviewedRow]:
    """The rows whose whole alignment isn't reviewed, and so need a finer check."""
    waived = {*OUTSCORED_TARGETS, *UNSCORED_TARGETS}
    return [row for row in rows if row["id"] not in waived]


def test_every_passage_of_a_link_lands_on_the_words_it_quotes(
    verses: bible.alignment.Verses,
    rows: list[quotations.ReviewedRow],
    policy: bible.policy.Policy,
) -> None:
    # A row for each Septuagint passage of a row that cites several. The row's
    # other passages are its siblings, not its rivals, and its own score would
    # let a well-placed first passage carry a misplaced second.
    each: list[quotations.ReviewedRow] = [
        {**row, "id": f"{row['id']} {passage}", "ot": [passage]}
        for row in unwaived(rows)
        if len(row["ot"]) > 1
        for passage in row["ot"]
    ]
    outscored, unscored = flagged(alignments(verses, each, policy))
    assert outscored | unscored == set(UNSCORED_PASSAGES)


def range_ends(
    verses: bible.alignment.Verses,
    rows: list[quotations.ReviewedRow],
    policy: bible.policy.Policy,
) -> dict[str, float]:
    """How much of each range's first and last verse the other side quotes.

    A range that runs a verse too far, into context the quotation doesn't
    reach, ends on a verse that shares little with it. The verse is measured
    by its own words, since a quotation may take few of a long range's.
    """
    result = {}
    for row in rows:
        nt, ot = passages(row, policy)
        sides = (
            ([p.verses for p in row["nt"]], verses.bag(ot)),
            (
                [quotations.brenton_verses([p], policy=policy) for p in row["ot"]],
                verses.bag(nt),
            ),
        )
        for spans, other in sides:
            for span in spans:
                for verse in {span[0], span[-1]} if len(span) > 1 else ():
                    result[f"{row['id']} {verse}"] = verses.score(
                        verses.words[verse], other
                    )
    return result


def test_every_range_ends_on_quoted_words(
    verses: bible.alignment.Verses,
    rows: list[quotations.ReviewedRow],
    policy: bible.policy.Policy,
) -> None:
    scores = range_ends(verses, unwaived(rows), policy)
    assert {key for key, score in scores.items() if score < UNSCORED} == set(
        UNSCORED_RANGE_ENDS
    )


@pytest.mark.parametrize("side", ["nt", "ot"])
def test_a_range_run_a_verse_too_far_is_caught(
    verses: bible.alignment.Verses,
    rows: list[quotations.ReviewedRow],
    policy: bible.policy.Policy,
    side: Literal["nt", "ot"],
) -> None:
    # Most ranges, run on a verse, end on one the other side doesn't quote.
    caught = total = 0
    for row in unwaived(rows):
        for i, passage in enumerate(row[side]):
            last = passage.last
            next_verse = beyond = Verse(last.book, last.chapter, last.number + 1)
            if side == "ot":
                beyond = versification.lxx_to_edition(beyond, policy=policy)
            if passage.first.letter or beyond not in verses.words:
                continue
            run_on: quotations.ReviewedRow = {**row}
            passages = list(row[side])
            passages[i] = Passage(passage.first, next_verse)
            if side == "nt":
                run_on["nt"] = passages
            else:
                run_on["ot"] = passages
            ends = range_ends(verses, [run_on], policy)
            total += 1
            caught += ends[f"{row['id']} {beyond}"] < UNSCORED
    assert caught >= 0.6 * total > 0


# Turpie's rows at the verses the Byzantine text changes, Matthew 27:35's
# excluded. Each was read against the words that remain, which still quote
# the passage while the TR note gives the words lost (docs/edition.md,
# Quotations). A row new here is one to read the same way.
AT_CHANGED_VERSES = {
    "Q026", "Q027", "Q058", "Q061", "Q062", "Q066", "Q070", "Q085", "Q132",
    "Q165", "Q176", "Q199", "Q207", "Q208", "Q233", "Q245", "Q253", "Q255",
    "Q271", "Q275",
}  # fmt: skip


def test_rows_at_verses_the_byzantine_text_changes_are_reviewed(
    edition: bible.pipeline.Edition, rows: list[quotations.ReviewedRow]
) -> None:
    changed = {
        verse_at(code, row["reference"])
        for code in edition.scripture
        for row in edition.notes[code]
        if re.search(r" TR(#\d+)?$", row["key"])
    }
    at_changed = {row["id"] for row in rows if set(verses_of(row["nt"])) & changed}
    assert at_changed == AT_CHANGED_VERSES
