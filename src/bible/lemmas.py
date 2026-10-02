"""The words a note is about: its lemma.

No note leaves a caller in the text. Each is set as a footnote that opens with
its verse's number and names the words it glosses: "25:20 I doubted of such
manner of questions: or, I was doubtful how to enquire hereof". The rules
here find those words from the place of Brenton's caller, or of George's
lemma, and the rendering the note gives; edition/brenton-notes.json and
edition/kjv-notes.json say what to print where they go wrong.

A verse is read as scripture.Verse gives it: its words without its notes,
each paragraph or line parted from the next by a newline. Words are named by
their index in the verse, and a span by its first and last word.
"""

from __future__ import annotations

import re

from bible.checks import require
from bible.policy_schema import NoteOverride
from bible.scripture import plain, words_of

type Span = tuple[int, int]
type Words = list[tuple[str, int, int]]


# Words that never end a lemma alone: they want the word after them.
LINKING_WORDS = {
    *("a", "an", "the", "of", "to", "and", "in", "on", "at", "by", "for", "from"),
    *("with", "as", "or", "unto", "upon", "into", "nor", "but"),
}
OPEN_WORDS = LINKING_WORDS | {
    *("thy", "his", "her", "my", "their", "your", "our", "its"),
    *("this", "these", "those", "every", "all", "some", "any", "own"),
    *("thou", "he", "she", "we", "ye", "they", "i"),
}
# Words that open a clause, where a lemma stops unless the rendering has them.
CLAUSE_WORDS = {
    *("that", "which", "who", "whom", "whose", "when", "where", "because"),
    *("if", "lest", "whereas", "while", "until"),
}
# Pronouns whose relative clause belongs to them: "those who ...", "he that ...".
ANTECEDENTS = {"those", "these", "he", "she", "they", "them", "him", "all", "one"}
CONJUNCTIONS = {"and", "but", "or", "nor"}
ARTICLES = {"a", "an", "the"}
POSSESSIVES = {
    *("thy", "thine", "his", "her", "my", "mine", "their", "your", "our", "its"),
}
PREPOSITIONS = {
    *("of", "to", "in", "on", "at", "by", "for", "from", "with", "unto", "upon"),
    *("into", "among", "amongst", "above", "under", "over", "before", "after"),
    *("against", "toward", "towards", "through", "within", "without", "about"),
}
# A note that measures nothing glosses its clause, or the clause's first words.
CLAUSE_LEMMA_WORDS = 6
# A cross-reference shows where the quotation begins, so it takes a longer clause.
XREF_CLAUSE_LEMMA_WORDS = 8
# How far "those who ..." reaches into its clause.
RELATIVE_LEMMA_WORDS = 8
DEFAULT_LEMMA_WORDS = 4
# Punctuation that ends the words a note can gloss.
CLAUSE_END = re.compile(r"[,;:.?!()—]")


def occurrences(words: Words, phrase: list[str]) -> list[int]:
    return [
        i
        for i in range(len(words) - len(phrase) + 1)
        if [w for w, _, _ in words[i : i + len(phrase)]] == phrase
    ]


def ends_clause(verse: str, words: Words, i: int) -> bool:
    """Whether punctuation between words[i] and the next word ends a clause."""
    return bool(CLAUSE_END.search(plain(verse[words[i][2] : words[i + 1][1]])))


def crosses_clause(verse: str, words: Words, first: int, last: int) -> bool:
    return any(ends_clause(verse, words, i) for i in range(first, last))


def whole_compounds(verse: str, words: Words, first: int, last: int) -> Span:
    """The span widened to whole hyphenated words (flood-gates, seven-fold)."""
    while first > 0 and verse[words[first - 1][2] : words[first][1]] == "-":
        first -= 1
    while last + 1 < len(words) and verse[words[last][2] : words[last + 1][1]] == "-":
        last += 1
    return first, last


def unique_span(
    verse: str, words: Words, first: int, last: int, lone: bool = False
) -> Span:
    """The shortest widening of words[first..last] that occurs once in the verse.

    A widening that stays within its clause and does not end on a word like
    "the" or "his" is preferred, even at up to two words longer; of equally
    good ones, the shortest, then the one to the right. Words that already
    occur once are left as they are, unless they end on "the" or "of"; a lone
    word the note is about (lone) stands even then ("for: Or, unto").
    """

    def unique(span: Span) -> bool:
        return (
            len(occurrences(words, [w for w, _, _ in words[span[0] : span[1] + 1]]))
            == 1
        )

    def awkwardness(span: Span) -> int:
        return 2 * crosses_clause(verse, words, *span) + (
            words[span[1]][0] in OPEN_WORDS
        )

    span = whole_compounds(verse, words, first, last)
    if unique(span) and (
        words[span[1]][0] not in LINKING_WORDS or (lone and span[0] == span[1])
    ):
        return span
    best = None
    for extra in range(1, len(words)):
        if best and (awkwardness(best[1]) == 0 or extra > best[0] + 2):
            break
        for left in range(extra + 1):
            if first - left < 0 or last + extra - left >= len(words):
                continue
            span = whole_compounds(verse, words, first - left, last + extra - left)
            if unique(span) and (
                best is None or awkwardness(span) < awkwardness(best[1])
            ):
                best = extra, span
    return best[1] if best else (first, last)


def phrase_span(
    words: Words, phrase: str, key: str, occurrence: int | None = None
) -> Span:
    """The place in the verse where an exception's lemma occurs: its one
    occurrence, or the one the exception names if it occurs more than once."""
    tokens = words_of(phrase)
    hits = occurrences(words, tokens)
    # A lemma of no words would be found everywhere, and span nothing.
    require(
        tokens
        and (
            len(hits) == 1
            if occurrence is None
            else len(hits) > 1 and 0 < occurrence <= len(hits)
        ),
        (
            f"Lemma override not found exactly once: {key} ({len(hits)})"
            if occurrence is None
            else f"Lemma override occurrence not found, or not needed: {key} ({len(hits)})"
        ),
    )
    first = hits[(occurrence or 1) - 1]
    return first, first + len(tokens) - 1


def overridden_lemma(
    verse: str,
    words: Words,
    exception: NoteOverride,
    span: Span | None,
    glossed: Span | None,
    rule: str | None,
    key: str,
    occurrence: int | None = None,
) -> tuple[Span | None, Span | None, str]:
    """The lemma's span, the span of the words it glosses, and the rule, or
    those of the exception's lemma if it has one.

    An exception's lemma is the words the note glosses. One that occurs more
    than once in the verse comes with its occurrence, and is widened like any
    other lemma.
    """
    if "lemma" not in exception:
        assert rule is not None
        return span, glossed, rule
    if exception["lemma"] is None:
        chosen = widened = None
    elif occurrence is None:
        chosen = widened = phrase_span(words, exception["lemma"], key)
    else:
        chosen = phrase_span(words, exception["lemma"], key, occurrence)
        widened = unique_span(verse, words, *chosen)
    # A lemma the same as the widened one still changes what the rendering echoes.
    require(
        (widened, chosen) != (span, glossed), f"Lemma override changes nothing: {key}"
    )
    return widened, chosen, "override"


def same_word(a: str, b: str) -> bool:
    # Every way of stripping a suffix, so "executes" (execute-s) meets "execute".
    def stems(word: str) -> set[str]:
        return {word} | {
            word[: -len(suffix)]
            for suffix in ("ings", "ing", "eth", "est", "ed", "es", "s", "d", "ly")
            if word.endswith(suffix) and len(word) - len(suffix) >= 3
        }

    return a == b or bool(stems(a) & stems(b))


def clause_after(verse: str, words: Words, first: int, other: list[str]) -> list[int]:
    """The words from first to the end of their clause, as a note can gloss them."""
    clause = [first]
    for i in range(first + 1, len(words)):
        if ends_clause(verse, words, i - 1):
            break
        # "those who had in them divining spirits" is one phrase.
        if (
            words[i][0] in CLAUSE_WORDS
            and words[i][0] not in other
            and words[i - 1][0] not in OPEN_WORDS
        ):
            break
        clause.append(i)
    return clause


def clause_before(verse: str, words: Words, last: int) -> list[int]:
    """The words from the start of their clause to last."""
    first = last
    while first > 0 and not ends_clause(verse, words, first - 1):
        first -= 1
    return list(range(first, last + 1))


def measured(
    words: Words, clause: list[int], other: list[str], backward: bool = False
) -> tuple[int, str]:
    """How many words of the clause a rendering stands for, and the rule that said so.

    Forward, the words run from the caller to the rendering's last word. Backward
    they end at the caller, so they run from the rendering's first word, counted
    back from its last, to the caller.
    """
    if other[-1] not in LINKING_WORDS:
        near = clause[::-1] if backward else clause
        for j, i in enumerate(near[: len(other) + 3]):
            if same_word(words[i][0], other[-1]):
                return (j + len(other) if backward else j + 1), "last-word"
    size = len(other)
    # The word the lemma would start with, which the rendering's article stands for.
    edge = clause[-min(size, len(clause))] if backward else clause[0]
    if size > 1 and other[0] in ARTICLES and words[edge][0] not in ARTICLES:
        size -= 1
    return size, "length"


def inferred_lemma(
    kind: str,
    verse: str,
    words: Words,
    offset: int,
    alternative: str | None,
    widen: bool = True,
) -> tuple[Span | None, str]:
    """The words a Brenton note or cross-reference glosses, and the rule that found them.

    Brenton's caller stands before the glossed words, or after the first of them
    if the rendering begins with it. A rendering measures how far they reach, by
    its last word or its length; otherwise the clause, or its first few words,
    stands for the place. A caller at the end of a verse or a line glosses the
    words before it if the note renders them, and otherwise the whole verse
    (None). Unless widen is false, the words are widened until they occur once.
    """

    def unique(
        verse: str, words: Words, first: int, last: int, lone: bool = False
    ) -> Span:
        if widen:
            return unique_span(verse, words, first, last, lone)
        return first, last

    after = [i for i, (_, start, _) in enumerate(words) if start >= offset]
    # A rendering with figures ("Alex. 187 years") cannot be measured by its words.
    if alternative and re.search(r"\d", alternative):
        alternative = None
    other = words_of(alternative or "")
    if kind == "x" and after and after[0] <= 3:
        return None, "xref-verse"
    if not after or ends_line(verse, offset):
        before = [i for i, (_, _, end) in enumerate(words) if end <= offset]
        if not other or kind == "x" or not before:
            return None, "verse-level"
        clause = clause_before(verse, words, before[-1])
        size, rule = measured(words, clause, other, backward=True)
        span = clause[-min(size, len(clause))], clause[-1]
        return unique(verse, words, *span), rule + " before"
    clause = clause_after(verse, words, after[0], other)
    # "and tents" for Alex. "cattle": the conjunction is not what the note renders.
    if (
        len(clause) > 1
        and words[clause[0]][0] in CONJUNCTIONS
        and (not other or other[0] not in CONJUNCTIONS)
    ):
        clause = clause[1:]
    if other and kind != "x":
        size, rule = measured(words, clause, other)
    else:
        rule = "xref-opening" if kind == "x" else "explanatory"
        whole = XREF_CLAUSE_LEMMA_WORDS if kind == "x" else CLAUSE_LEMMA_WORDS
        size = len(clause) if len(clause) <= whole else DEFAULT_LEMMA_WORDS
    # "his: Alex. their", "into: Gr. upon": a possessive, preposition or
    # conjunction rendered by one of its kind glosses it alone.
    alone = len(other) == 1 and any(
        other[0] in group and words[clause[0]][0] in group
        for group in (POSSESSIVES, PREPOSITIONS | CONJUNCTIONS)
    )

    def rounded(size: int) -> int:
        # Never end on a word like "the" or "his" while the clause goes on.
        size = min(size, len(clause))
        while (
            not alone
            and size < len(clause)
            and words[clause[size - 1]][0] in OPEN_WORDS
        ):
            size += 1
        return size

    size = rounded(size)
    # "those who" wants the rest of its clause.
    if (
        size > 1
        and words[clause[size - 1]][0] in CLAUSE_WORDS
        and words[clause[size - 2]][0] in ANTECEDENTS
    ):
        size = rounded(max(size + 2, RELATIVE_LEMMA_WORDS))
    if CLAUSE_END.search(plain(verse[offset : words[after[0]][1]])):
        rule += " after punctuation"
    span = whole_compounds(verse, words, clause[0], clause[size - 1])
    first, last = unique(verse, words, *span, lone=alone)
    # "the Evite: Alex. the Chorrhæan", "a consecration: Gr. an accomplishment":
    # the caller follows the word the rendering begins with.
    if (
        other
        and first == clause[0]
        and first > 0
        and indefinite(words[first - 1][0]) == indefinite(other[0])
        and indefinite(other[0]) != indefinite(words[first][0])
        and not ends_clause(verse, words, first - 1)
    ):
        first -= 1
    return (first, last), rule


def indefinite(word: str) -> str:
    """The word, with "an" as "a"."""
    return "a" if word == "an" else word


def ends_line(verse: str, offset: int) -> bool:
    """Whether nothing but space stands between an offset and the end of its
    paragraph or line."""
    line = verse.find("\n", offset)
    return line >= 0 and not verse[offset:line].strip()


def lemma_text(verse: str, words: Words, span: Span) -> str:
    first, last = span
    return plain(verse[words[first][1] : words[last][2]])


def echoes(
    verse: str, words: Words, span: Span | None, glossed: Span | None
) -> tuple[str, str]:
    """The lemma's words before and after the words the note glosses: those it
    took in to occur once in the verse, which a rendering takes in as well
    ("of your Father: or, with your Father")."""
    if span is None or span == glossed:
        return "", ""
    assert glossed is not None
    require(
        span[0] <= glossed[0] and glossed[1] <= span[1],
        "Lemma does not contain the words it glosses: "
        + lemma_text(verse, words, span),
    )
    narrow = lemma_text(verse, words, glossed)
    head = lemma_text(verse, words, (span[0], glossed[1]))
    tail = lemma_text(verse, words, (glossed[0], span[1]))
    return head[: len(head) - len(narrow)], tail[len(narrow) :]


def inferred(
    kind: str,
    verse: str,
    words: Words,
    offset: int,
    alternative: str | None,
    exception: NoteOverride,
    key: str,
) -> tuple[Span | None, Span | None, str]:
    """A Brenton note's lemma, the words it glosses, and the rule that found
    them, with the exception file's say."""
    span, rule = inferred_lemma(kind, verse, words, offset, alternative)
    glossed, _ = inferred_lemma(kind, verse, words, offset, alternative, widen=False)
    return overridden_lemma(
        verse, words, exception, span, glossed, rule, key, exception.get("occurrence")
    )


def declared(
    verse: str, words: Words, offset: int, phrase: str | None, key: str
) -> tuple[Span | None, Span | None, str]:
    """The lemma a manuscript decision declares: the precise changed words,
    widened only where they occur more than once, when the one at the caller
    is meant. A complete phrase can end in a preposition ("asked for");
    widening it would assign retained words to an omission."""
    if phrase is None:
        return None, None, "Alexandrine reading"
    hits = occurrences(words, words_of(phrase))
    occurrence = None
    if len(hits) > 1:
        anchored = [i for i, hit in enumerate(hits, 1) if words[hit][1] == offset]
        require(len(anchored) == 1, f"Alexandrine lemma not anchored once: {key}")
        occurrence = anchored[0]
    glossed = phrase_span(words, phrase, key, occurrence)
    span = unique_span(verse, words, *glossed) if len(hits) > 1 else glossed
    return span, glossed, "Alexandrine reading"


def preserved(
    words: Words, lemma: str | None, glossed: str | None, key: str
) -> tuple[Span | None, Span | None, str]:
    """The lemma and gloss a note had before a manuscript reading changed the
    words around it, found again in the verse as it now stands."""
    return (
        phrase_span(words, lemma, key) if lemma is not None else None,
        phrase_span(words, glossed, key) if glossed is not None else None,
        "preserved passage note",
    )


def anchored(
    verse: str,
    words: Words,
    anchor: list[str],
    occurrence: int | None,
    exception: NoteOverride,
    key: str,
) -> tuple[Span | None, Span | None, str, int]:
    """A 1611 note's lemma: George's, found in the verse or at the anchor the
    exception file records for it, widened until it occurs once. Returns the
    lemma, the words glossed, the rule, and the word the note stands at."""
    hits = occurrences(words, anchor)
    # An anchor of no words would be found everywhere, and span nothing.
    require(
        anchor
        and (len(hits) == 1 if occurrence is None else 0 < occurrence <= len(hits)),
        f"Marginal note anchor not found exactly once: {key} ({len(hits)})",
    )
    first = hits[(occurrence or 1) - 1]
    glossed: Span | None = whole_compounds(verse, words, first, first + len(anchor) - 1)
    # George's lemma of one word stands if it occurs once, even "for".
    assert glossed is not None
    span: Span | None = unique_span(
        verse, words, *glossed, lone=anchor[0] not in ARTICLES
    )
    rule = "anchor" if span == (first, first + len(anchor) - 1) else "widened"
    # A 1611 note's occurrence is its anchor's, not its lemma override's.
    span, glossed, rule = overridden_lemma(
        verse, words, exception, span, glossed, rule, key
    )
    # A lemma clear of George's anchor says where the note belongs, so the
    # footnote follows it. A null lemma, for a note on the whole verse, leaves
    # the note at the anchor.
    if span and (span[1] < first or first + len(anchor) - 1 < span[0]):
        first = span[0]
    return span, glossed, rule, first


# How many words longer than its rendering a lemma may be before it is read.
MISSHAPEN = 3


def misshapen(glossed: str | None, reading: str | None) -> bool:
    """Whether the words a rule found for a note are so much longer than the
    rendering that measured them that the rendering may not be of them: "Gr.
    hands" on a clause of seven words. A rendering longer than its words is
    no sign of anything: the Greek often takes more words than the English.
    A rendering with figures measures nothing."""
    if not glossed or not reading or re.search(r"\d", reading):
        return False
    return len(words_of(glossed)) - len(words_of(reading)) >= MISSHAPEN
