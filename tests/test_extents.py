"""Each quotation's words are found in the edition's verses from the English
Turpie prints, or from an extent decision where his words cannot be placed."""

from __future__ import annotations

import pytest
from conftest import book

from bible import extents, lemmas, scripture
from bible.checks import CheckFailed
from bible.policy_schema import QuotationsExtent
from bible.references import parse_passage, parse_passages

PSALM = book(
    "PSA",
    "\\v 2 O Lord, our Lord, how wonderful is thy name in all the earth!\n"
    "\\v 3 Out of the mouth of babes and sucklings hast thou perfected praise,"
    " because of thine enemies; that thou mightest put down the enemy and avenger.\n"
    "\\v 4 For I will regard the heavens, the work of thy fingers.",
)
VERSES = {"PSA": scripture.verses(PSALM)}
WORDS = scripture.words_of(VERSES["PSA"]["99:3"].text)
THIRD = parse_passage("PSA 99:3").first


def located(
    quoted: str, passage: str = "PSA 99:3", decision: QuotationsExtent | None = None
) -> list[extents.Extent]:
    return extents.located(
        f"Q999 {passage}", quoted, parse_passages(passage), VERSES, decision
    )


def test_turpies_words_are_read_without_his_formula_callers_and_numbers() -> None:
    assert extents.quoted_words(
        "[Have ye never read,] 3Out of the *mouth of babes¶ and 4sucklings?"
    ) == ["out", "of", "the", "mouth", "of", "babes", "and", "sucklings"]
    # His "etc." stands for words of the passage, and is none of them.
    quoted = "Out of the mouth etc. perfected praise"
    assert extents.quoted_words(quoted) == [
        "out",
        "of",
        "the",
        "mouth",
        "perfected",
        "praise",
    ]
    assert extents.omissions(quoted) == {4}


def test_a_quotation_is_placed_at_its_words() -> None:
    [found] = located(
        "[Have ye never read,] Out of the mouth of babes and sucklings thou hast"
        " perfected praise?"
    )
    assert (found.start, found.end, found.rule) == (0, WORDS.index("praise"), "aligned")
    assert (found.first, found.last) == (THIRD, THIRD)
    # A difference of wording within the share is tolerated and listed.
    assert found.unplaced and set(found.unplaced) <= {"thou", "hast"}
    assert WORDS[found.start : found.end + 1] == scripture.words_of(
        "Out of the mouth of babes and sucklings hast thou perfected praise"
    )


def test_a_quotation_within_a_verse_begins_and_ends_at_its_own_words() -> None:
    [found] = located("that thou mightest put down the enemy")
    assert (found.start, found.end) == (WORDS.index("that"), WORDS.index("enemy"))


def test_a_quotation_across_verses_ends_in_the_last() -> None:
    [found] = located(
        "because of thine enemies; that thou mightest put down the enemy and"
        " avenger. 4For I will regard the heavens,",
        "PSA 99:3-4",
    )
    assert found.passage == parse_passage("PSA 99:3-4")
    assert (found.first, found.start) == (THIRD, WORDS.index("because"))
    assert (found.last, found.end) == (
        parse_passage("PSA 99:4").first,
        scripture.words_of(VERSES["PSA"]["99:4"].text).index("heavens"),
    )


def test_a_verse_division_can_put_quoted_words_before_the_heading() -> None:
    # As Isaiah's commission is at the end of Brenton's preceding verse,
    # rather than the verse where Turpie's heading places it.
    [found] = located(
        "how wonderful is thy name ... Out of the mouth of babes and sucklings"
        " hast thou perfected praise",
        decision={
            "passage": "PSA 99:2-3",
            "first": "how wonderful",
            "last": "perfected praise",
            "why": "The printed verse division precedes the heading's",
        },
    )
    assert found.passage == parse_passage("PSA 99:2-3")
    assert (found.first, found.start) == (parse_passage("PSA 99:2").first, 4)
    assert (found.last, found.end) == (THIRD, WORDS.index("praise"))
    assert found.rule == "decided"


@pytest.mark.parametrize("passage", ["PSA 99:3", "PSA 99:4", "ISA 99:2-3"])
def test_a_decided_passage_must_extend_its_printed_range(passage: str) -> None:
    with pytest.raises(CheckFailed, match="does not extend one printed range"):
        located(
            "Out of the mouth of babes",
            decision={
                "passage": passage,
                "first": "Out of the mouth",
                "last": "babes",
                "why": "An invalid passage",
            },
        )


def test_a_wider_decided_passage_must_use_its_added_verses() -> None:
    with pytest.raises(CheckFailed, match="adds an unquoted verse"):
        located(
            "Out of the mouth of babes",
            decision={
                "passage": "PSA 99:2-3",
                "first": "Out of the mouth",
                "last": "babes",
                "why": "The added verse contains no quoted words",
            },
        )


def test_an_end_word_is_found_by_its_stem_or_as_words_written_together() -> None:
    # His "praises" for "praise", as "receiveth" for "receives".
    [found] = located(
        "Out of the mouth of babes and sucklings hast thou perfected praises"
    )
    assert (found.start, found.end) == (0, WORDS.index("praise"))
    assert found.unplaced == ()
    # His "Outof" for "Out of", as "today" for "to day".
    [found] = located(
        "Outof the mouth of babes and sucklings hast thou perfected praise"
    )
    assert (found.start, found.end) == (0, WORDS.index("praise"))
    # And at the end, where it ends at the last of the words it joins.
    [found] = located(
        "Out of the mouth of babes and sucklings hast thou perfected praise,"
        " becauseof"
    )
    assert (found.start, found.end) == (0, WORDS.index("because") + 1)
    # An end word the alignment set elsewhere stands where it is nearest
    # the matched run: "that" is also the verse's fourth word.
    [found] = located("that thou mightest put down the enemy and avenger")
    assert (found.start, found.end) == (WORDS.index("that"), len(WORDS) - 1)


def test_a_quotation_may_begin_after_a_verse_of_its_heading() -> None:
    # The heading's first verse holds the formula alone.
    [found] = located("that thou mightest put down the enemy", "PSA 99:2-3")
    assert (found.first, found.last) == (THIRD, THIRD)
    assert (found.start, found.end) == (WORDS.index("that"), WORDS.index("enemy"))


def test_words_the_alignment_cannot_place_need_a_decision() -> None:
    with pytest.raises(CheckFailed, match="extent decision is needed.*unplaced"):
        located("Out of the mouth of infants and nurslings thou hast founded strength")
    # An end word with no counterpart leaves the extent unknown.
    with pytest.raises(CheckFailed, match="extent decision is needed"):
        located(
            "Out of the mouth of babes and sucklings hast thou perfected praise amen"
        )
    # So does an end word matched alone and far from the rest.
    with pytest.raises(CheckFailed, match="extent decision is needed"):
        located(
            "Out of thine enemies; that thou mightest put down the enemy and avenger"
        )
    decision: QuotationsExtent = {
        "first": "Out of the mouth",
        "last": "perfected praise",
        "why": "Turpie's wording is his own",
    }
    [found] = located(
        "Out of the mouth of infants and nurslings thou hast founded strength",
        decision=decision,
    )
    assert (found.start, found.end, found.rule) == (0, WORDS.index("praise"), "decided")
    # A decision the build finds alike without it is refused as unused.
    with pytest.raises(CheckFailed, match="finds alike without it"):
        located(
            "Out of the mouth of babes and sucklings hast thou perfected praise",
            decision=decision,
        )
    # A decision's words are found once.
    with pytest.raises(CheckFailed, match="not found once"):
        located("nothing here", decision={**decision, "first": "thou"})
    with pytest.raises(CheckFailed, match="not found once"):
        located("nothing here", decision={**decision, "last": "strength"})
    with pytest.raises(CheckFailed, match="Quotation without words"):
        located("[Have ye never read,]")


def test_one_text_under_several_headings_runs_through_them_or_serves_each() -> None:
    passages = parse_passages("PSA 99:2; PSA 99:4")
    # Turpie's marks of omission between the words of each passage.
    spanning = "how wonderful is thy name .. work of thy fingers"
    assert extents.spanning(spanning, passages, VERSES)
    # The same words under two headings, as the Decalogue's in Exodus and
    # Deuteronomy, which each passage has for itself.
    assert not extents.spanning("For I will regard the heavens", passages, VERSES)
    # Each passage's extent runs from the first of his words placed in it
    # to the last, leaving out the words his mark of omission stands for.
    found = located(spanning, "PSA 99:2; PSA 99:4")
    assert [(e.passage, e.first, e.start, e.last, e.end) for e in found] == [
        (passages[0], passages[0].first, 4, passages[0].first, 8),
        (passages[1], passages[1].first, 7, passages[1].first, 10),
    ]


def test_deciding_outer_ends_keeps_each_passages_matched_edges() -> None:
    passages = "PSA 99:2; PSA 99:3; PSA 99:4"
    found = located(
        "how glorious is thy name ... babes and sucklings hast thou perfected"
        " praise ... For I will regard the heavens",
        passages,
        {
            "first": "how wonderful",
            "last": "work of thy fingers",
            "why": "The outer passages differ from the quoted wording",
        },
    )
    assert [(e.start, e.end) for e in found] == [
        (4, 8),
        (WORDS.index("babes"), WORDS.index("praise")),
        (0, 10),
    ]
    assert all(e.rule == "decided" for e in found)


def test_a_quotation_lemma_opens_the_quotation_within_the_verse() -> None:
    text = VERSES["PSA"]["99:3"].text
    words = scripture.word_spans(text)
    # A quotation that opens the verse names no words.
    assert lemmas.quotation_lemma(text, words, 0, 5) is None
    # The clause from the first quoted word, within the quotation.
    first = WORDS.index("because")
    span = lemmas.quotation_lemma(text, words, first, len(words) - 1)
    assert span is not None
    assert lemmas.lemma_text(text, words, span) == "because of thine enemies"
    # A clause of a word runs on, past a word like "thine" while the
    # quotation goes on.
    first = WORDS.index("praise")
    span = lemmas.quotation_lemma(text, words, first, len(words) - 1)
    assert span is not None
    assert lemmas.lemma_text(text, words, span) == "praise, because of thine enemies"
    # A long clause gives its first few words.
    first = WORDS.index("that")
    span = lemmas.quotation_lemma(text, words, first, len(words) - 1)
    assert span is not None
    assert lemmas.lemma_text(text, words, span) == "that thou mightest put"
    # Never past the quotation's last word in the verse.
    first = WORDS.index("that")
    span = lemmas.quotation_lemma(text, words, first, first + 2)
    assert span is not None
    assert lemmas.lemma_text(text, words, span) == "that thou mightest"
    # Words the verse repeats are widened to the right alone: the note
    # stands before the lemma's first word, the quotation's.
    text = "The Lord is good. And the Lord is good for ever."
    words = scripture.word_spans(text)
    span = lemmas.quotation_lemma(text, words, 5, 8)
    assert span is not None
    assert lemmas.lemma_text(text, words, span) == "the Lord is good for ever"


def test_one_text_spans_its_passages_only_where_each_has_words_of_it() -> None:
    # The middle passage holds none of his words: the text cannot run
    # through it, so each passage is read for its own.
    passages = parse_passages("PSA 99:2; PSA 99:3; PSA 99:4")
    assert not extents.spanning(
        "how wonderful is thy name ... nothing here ... work of thy fingers",
        passages,
        VERSES,
    )
