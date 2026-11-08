"""The words of each quotation: Turpie's printed English found in the
edition's verses.

Turpie prints the English of every quotation on both sides of his tables:
the Authorised Version's words of the New Testament passage, with the
introductory formula in brackets, and Brenton's words of the Septuagint
passage. Those are the words of this edition's sources, so each quotation is
found in the prepared verses by aligning Turpie's words with the passage's.
The link then stands at the first of them, and the quotation milestones
around them all. Where alignment would mark the wrong boundaries, a decision
in edition/quotations.json (`extents`) gives them in the edition's words.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence, Set
from dataclasses import dataclass

from bible import scripture
from bible.alignment import Alignment, stem
from bible.checks import require, require_fields
from bible.policy_schema import QuotationsExtent
from bible.references import Passage, Verse, parse_passage

# The share of Turpie's words the passage must have, in his order, for the
# extent to stand without a decision: he corrected Brenton's English "when
# required", and the King James verses have changed with the Byzantine text.
PLACED_SHARE = 0.7
# How many words of the passage an end word may stand from the next placed
# word, where it is matched alone.
APART = 3
# The introductory formula, which Turpie brackets.
BRACKETED = re.compile(r"\[[^\[\]]*\]")
# Turpie's note callers, and the verse numbers set in his text.
UNSPOKEN = re.compile(r"[*†‡§¶]|\d+")
# His marks of omission between the words he quotes: dots, a dash, "etc."
OMISSION = re.compile(r"(?:\.\s*){2,}|—|\betc\.")

# A book's verses by their labels, as scripture.verses gives them.
type Verses = Mapping[str, Mapping[str, scripture.Verse]]


@dataclass(frozen=True)
class Extent:
    """The quoted words of one passage as the edition prints it: from a word
    of one of its verses to a word of a later one or the same, each by its
    index among the words of its verse. A verse of the passage before the
    first or after the last holds Turpie's formula and no quoted words."""

    passage: Passage
    first: Verse
    start: int
    last: Verse
    end: int
    # How the words were found, and Turpie's words the alignment did not
    # place, for the review.
    rule: str
    unplaced: tuple[str, ...] = ()


def decision_key(row: str, passages: Iterable[Passage]) -> str:
    """An extent decision's key: the row and the passages of its heading
    the decision is about, as "Q052 HEB 2:13"."""
    return f"{row} {'; '.join(map(str, passages))}"


def _spoken(quoted: str) -> str:
    """Turpie's text without the formula he brackets, his note callers, and
    his verse numbers."""
    return UNSPOKEN.sub(" ", BRACKETED.sub(" ", quoted))


def _words(text: str) -> list[str]:
    """The words of his text, without his marks of omission: "etc." stands
    for words of the passage, and is none of them."""
    return scripture.words_of(OMISSION.sub(" ", text))


def quoted_words(quoted: str) -> list[str]:
    """Turpie's words of a quotation: without the formula he brackets, his
    note callers, his verse numbers, and his marks of omission."""
    return _words(_spoken(quoted))


def omissions(quoted: str) -> set[int]:
    """The indices of Turpie's words that a mark of omission precedes: words
    of the passage are left out before them."""
    text = _spoken(quoted)
    return {len(_words(text[: mark.start()])) for mark in OMISSION.finditer(text)}


def tagged_words(
    passages: Sequence[Passage], verses: Verses
) -> list[tuple[Verse, int, str]]:
    """The words of some passages in order, each with its verse and its
    index among the verse's words."""
    return [
        (verse, index, word)
        for passage in passages
        for verse in passage.verses
        for index, (word, _, _) in enumerate(
            scripture.word_spans(verses[verse.book][verse.label].text)
        )
    ]


def canon(word: str) -> str:
    """A word without the commonest inflexions and a final e, so that his
    "receiveth" meets Brenton's "receives", and "peoples" "people"."""
    stemmed = stem(word)
    return stemmed[:-1] if len(stemmed) >= 4 and stemmed.endswith("e") else stemmed


@dataclass(frozen=True)
class Aligned:
    """Where Turpie's first and last words stand among a passage's (None
    where the alignment places too little), every place of the passage a
    word of his was placed at, and his words the alignment left unplaced."""

    first: int | None
    last: int | None
    places: frozenset[int]
    unplaced: tuple[str, ...]


def aligned(turpie: Sequence[str], words: Sequence[str], gaps: Set[int]) -> Aligned:
    """Where Turpie's first and last words stand among a passage's, and his
    words the alignment left unplaced.

    The passage's words that are his, in his order, place his. An end word
    of his is placed by the nearest run of two or more matched words: where
    the alignment set it, if that is within reach of the run, and otherwise
    where it stands nearest the run within reach, as a word of the passage
    or as words it writes together ("today" for "to day"); the reach is the
    words of his between them and APART more, or any distance where one of
    his marks of omission stands between (gaps: the indices of his words
    such a mark precedes). An end is None where the alignment places too
    little: less than PLACED_SHARE of his words, or no place for the end
    word.
    """
    stems, found = [canon(w) for w in turpie], [canon(w) for w in words]
    matched = Alignment.of(stems, found)
    placed = matched.mapped
    anchors = set(matched.solid) or set(placed)
    last_index = len(turpie) - 1

    def parted(index: int, other: int) -> bool:
        """Whether a mark of omission stands between two of his words."""
        return bool(gaps & set(range(min(index, other) + 1, max(index, other) + 1)))

    def reached(index: int, step: int) -> int | None:
        """Where an end word of his stands, by the nearest run."""
        stop = last_index + 1 if step > 0 else -1
        after = next((i for i in range(index + step, stop, step) if i in anchors), None)
        if after is None:
            return placed.get(index)
        anchor, limit = placed[after], abs(after - index) + APART
        if index in placed and (
            abs(anchor - placed[index]) <= limit or parted(index, after)
        ):
            return placed[index]
        # From the run outwards, the nearest place where his word stands.
        for distance in range(1, limit + 1):
            at = anchor - distance if step > 0 else anchor + distance
            if not 0 <= at < len(words):
                break
            if found[at] == stems[index]:
                return at
            # The words between the run and here, which his one word joins:
            # it begins here, or ends here.
            run = words[at:anchor] if step > 0 else words[anchor + 1 : at + 1]
            if canon("".join(run)) == stems[index]:
                return at
        return None

    first = reached(0, 1) if turpie else None
    last = reached(last_index, -1) if turpie else None
    ends = {i: at for i, at in ((0, first), (last_index, last)) if at is not None}
    counted = set(placed) | set(ends)
    unplaced = tuple(word for i, word in enumerate(turpie) if i not in counted)
    places = frozenset({*placed.values(), *ends.values()})
    if not turpie or len(counted) < PLACED_SHARE * len(turpie):
        return Aligned(None, None, places, unplaced)
    return Aligned(first, last, places, unplaced)


def once(words: Sequence[str], phrase: str, key: str) -> tuple[int, int]:
    """Where a decision's words stand among a passage's, found once."""
    tokens = scripture.words_of(phrase)
    hits = [
        i
        for i in range(len(words) - len(tokens) + 1)
        if list(words[i : i + len(tokens)]) == tokens
    ]
    require(
        bool(tokens) and len(hits) == 1,
        f"Extent decision's words not found once in the passage: {key}: {phrase}",
    )
    return hits[0], hits[0] + len(tokens) - 1


def spanning(quoted: str, ranges: Sequence[Passage], verses: Verses) -> bool:
    """Whether one text Turpie prints under several headings runs through
    their passages in turn, with his marks of omission between, rather than
    giving the words of each: aligned with them all, it places enough of
    his words, and every passage has some of them placed in it, as located
    reads each passage's extent."""
    tagged = tagged_words(ranges, verses)
    words = [word for _, _, word in tagged]
    found = aligned(quoted_words(quoted), words, omissions(quoted))
    if found.first is None or found.last is None:
        return False
    reached = {
        tagged[place][0] for place in found.places if found.first <= place <= found.last
    }
    return all(reached & set(passage.verses) for passage in ranges)


def located(
    key: str,
    quoted: str,
    ranges: Sequence[Passage],
    verses: Verses,
    decision: QuotationsExtent | None,
) -> list[Extent]:
    """The extents of one passage of Turpie's heading, as the edition prints
    it in one range or more, or of several passages one text of his runs
    through: Turpie's words aligned with the ranges' words, or the decision's
    first and last words found in them."""
    added: set[Verse] = set()
    if decision is not None:
        require_fields(
            decision, {"first", "last", "why"}, {"passage"}, f"Extent decision {key}"
        )
        require(bool(decision["why"]), f"Unexplained extent decision: {key}")
        if "passage" in decision:
            expanded = parse_passage(decision["passage"])
            require(
                len(ranges) == 1 and set(ranges[0].verses) < set(expanded.verses),
                f"Extent passage does not extend one printed range: {key}",
            )
            added = set(expanded.verses) - set(ranges[0].verses)
            require(
                all(v.label in verses.get(v.book, {}) for v in expanded.verses),
                f"Extent passage has an unprinted verse: {key}",
            )
            ranges = [expanded]
    # Each range's words, in turn.
    own = [tagged_words([passage], verses) for passage in ranges]
    tagged = [word for words in own for word in words]
    words = [word for _, _, word in tagged]
    turpie = quoted_words(quoted)
    require(bool(turpie), f"Quotation without words: {key}")
    found = aligned(turpie, words, omissions(quoted))
    first, last, unplaced = found.first, found.last, found.unplaced
    if decision is not None:
        start, _ = once(words, decision["first"], key)
        _, end = once(words, decision["last"], key)
        require(start <= end, f"Extent decision ends before it begins: {key}")
        require(
            bool(added) or (first, last) != (start, end),
            f"Extent decision the build finds alike without it: {key}",
        )
        require(
            added <= {verse for verse, _, _ in tagged[start : end + 1]},
            f"Extent passage adds an unquoted verse: {key}",
        )
        rule, unplaced = "decided", ()
        # Deciding the outer ends does not make the unquoted edges of an
        # intervening passage part of the quotation.
        places = found.places | {start, end}
    else:
        require(
            first is not None and last is not None,
            f"Quotation words not found in their passage, so an extent decision"
            f" is needed: {key}: unplaced {' '.join(unplaced)!r}",
        )
        assert first is not None and last is not None
        start, end, rule = first, last, "aligned"
        places = found.places
    # Each passage's words from the first placed in it to the last: a text
    # running through several passages leaves out words at their edges.
    extents = []
    at = 0
    for passage, its in zip(ranges, own, strict=True):
        size = len(its)
        within = [p for p in places if max(start, at) <= p <= min(end, at + size - 1)]
        require(bool(within), f"Quotation skips a passage of its heading: {key}")
        lo, hi = min(within), max(within)
        extents.append(
            Extent(
                passage,
                tagged[lo][0],
                tagged[lo][1],
                tagged[hi][0],
                tagged[hi][1],
                rule,
                unplaced,
            )
        )
        at += size
    return extents
