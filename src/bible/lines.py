"""The poetry set in lines, after the Updated Brenton.

A passage is set in lines where Adam Boyd's Updated Brenton (the pinned
englxxup archive) sets it in lines, and divided where it divides it. Its
words never reach the edition: each of its chapters is aligned word by word
with the source's, and a line of the update begins a line of the edition
where its first word is matched, or after the matched last word of the line
before. A break the words do not place, or place two ways, is given in
edition/lines.json or stops the build; a decision there may also set a line
where the words would place it otherwise, keep a verse in prose, or change
or join a prose paragraph at an existing boundary.

After alignment, terminal “Pause.” instructions stand in right-aligned
lines, Brenton’s existing small-cap Lamentations acrostic names in
headings, and a prose paragraph's opening small-cap title that ends in a
period in a descriptive title (d). All preserve the source wording, notes and verse nodes; qa
supplies the acrostic names' style in place of inline small capitals.

The New Testament keeps Scrivener's paragraphs and poetry unchanged.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cached_property

import bible.policy
from bible import scripture, usj, versification
from bible.alignment import Alignment
from bible.checks import CheckFailed, require, require_fields
from bible.policy_schema import Paragraph
from bible.references import Verse, book_of, verse_at
from bible.usj import Content, Document, Node

# Whether a second witness sets a verse of a book in lines: True or False
# where it has the verse, None where it has no counterpart of the verse.
type Witness = Callable[[str, str], bool | None]

# The paragraph markers of a line and of a stanza break, and of the prose
# that resumes where a second witness or a decision sets the update's lines
# as prose, without a paragraph of its own: a new paragraph, within a verse
# too. At the end of the update's poem, prose resumes under its marker.
LINE, STANZA, RESUMED = "q1", "b", "p"
# A decision's verse key.
VERSE_KEY = re.compile(r"[1-4A-Z]{3} \d+:\d+[a-z]?")
# A block whose marker these are keeps it whatever the update has: a psalm's
# title, a heading.
FIXED = frozenset({"d", "cl", "s1", "ms1"})
# What opens a line with its first word: a quotation mark or a bracket.
OPENING = "“‘\"'(["


@dataclass(frozen=True)
class Word:
    text: str
    block: int  # index in the document's content
    start: int  # offsets in the block's words


@dataclass(frozen=True)
class Chapter:
    """A chapter's words in order, with where its blocks and verses begin."""

    number: str
    blocks: tuple[int, ...]
    words: tuple[Word, ...]
    first_words: Mapping[int, int]  # block -> index of its first word
    verse_starts: Mapping[str, int]  # verse label -> index of its first word

    @cached_property
    def texts(self) -> list[str]:
        return [w.text for w in self.words]

    def block_of(self, index: int) -> tuple[int, int]:
        """The block a word begins, and the word's offset in it."""
        word = self.words[index]
        return word.block, word.start

    def opens_block(self, index: int) -> bool:
        return self.first_words.get(self.words[index].block) == index

    def verse_end(self, start: int) -> int:
        """Where the verse beginning at a word ends."""
        return min(
            (s for s in self.verse_starts.values() if s > start),
            default=len(self.words),
        )

    def verse_of(self, index: int) -> str:
        """The label of the verse a word stands in."""
        return max(
            (label for label, start in self.verse_starts.items() if start <= index),
            key=lambda label: self.verse_starts[label],
            default="",
        )


def chapters(doc: Document) -> dict[str, Chapter]:
    """Every chapter of a document, by its number."""
    result: dict[str, Chapter] = {}
    number: str | None = None
    blocks: list[int] = []
    words: list[Word] = []
    first_words: dict[int, int] = {}
    verse_starts: dict[str, int] = {}
    # A verse whose number has been met and whose first word has not.
    pending: str | None = None

    def close() -> None:
        if number is not None:
            result[number] = Chapter(
                number,
                tuple(blocks),
                tuple(words),
                dict(first_words),
                dict(verse_starts),
            )

    for index, block in enumerate(doc["content"]):
        if block["type"] == "chapter":
            close()
            number = block["number"]
            blocks, words, first_words, verse_starts = [], [], {}, {}
            pending = None
        elif block["type"] == "para" and number is not None:
            blocks.append(index)
            for label, at, text in _segments(block["content"]):
                if label is not None:
                    pending = label
                for word, start, _ in scripture.word_spans(text):
                    if pending is not None:
                        verse_starts[pending] = len(words)
                        pending = None
                    first_words.setdefault(index, len(words))
                    words.append(Word(word, index, at + start))
    close()
    return result


def _segments(content: Content) -> list[tuple[str | None, int, str]]:
    """A block's words between one verse number and the next: the number
    (None before the first), the offset, and the words."""
    segments: list[tuple[str | None, int, str]] = [(None, 0, "")]
    at = 0
    for item in content:
        if isinstance(item, str):
            text = item
        elif usj.is_type(item, "verse"):
            segments.append((item["number"], at, ""))
            continue
        elif "content" in item and not usj.is_note(item):
            text = usj.text_of(item["content"])
        else:
            continue
        label, start, words = segments[-1]
        segments[-1] = (label, start, words + text)
        at += len(text)
    return segments


@dataclass(frozen=True)
class Span:
    """A poem in a chapter's words: where its first line begins, its other
    lines, and where prose resumes, with the marker it resumes under (None
    where the block there keeps its own)."""

    start: int
    lines: tuple[tuple[int, bool], ...]  # (word index, stanza before it)
    end: int | None
    resume: str | None
    stanza: bool = False


# Placing the update's breaks.


class Unplaced(Exception):
    """A break the words do not place."""


class Disordered(Exception):
    """A break the words place at or before the line already begun."""


def placed(index: int, alignment: Alignment, previous: int | None) -> int:
    """Where a break before an update word stands in the source: before the
    match of that word, or after the match of the word before it. A word
    matched alone counts only near a run, as anchored defines. Refused
    where neither is matched, or both are and words stand between them, or
    the source sets words of the new line before it."""
    first, before = alignment.anchored(index), alignment.anchored(index - 1)
    if first is not None and (before is None or before + 1 == first):
        position = first
    elif first is None and before is not None:
        position = before + 1
    else:
        raise Unplaced()
    if previous is not None:
        if position <= previous:
            raise Disordered()
        if any(alignment.back.get(j, -1) >= index for j in range(previous, position)):
            raise Unplaced()
    return position


@dataclass(frozen=True)
class Decision:
    verse: str  # the source verse the line opens
    follows: tuple[str, ...]  # the first words of the update line being followed
    line: str | None  # the words the source's line begins with; None, no line


@dataclass
class Decisions:
    """The lines edition/lines.json places: each named by the update's line
    being followed and the source verse it opens, and taken where the words
    fail to place that line, or place it otherwise."""

    entries: list[Decision]
    taken: set[Decision] = field(default_factory=set)

    @classmethod
    def of(cls, policy: bible.policy.Policy, codes: Iterable[str]) -> Decisions:
        wanted = set(codes)
        return cls(
            [
                Decision(key, tuple(scripture.words_of(e["follows"])), e["line"])
                for key, entries in policy.lines["breaks"].items()
                if key[:3] in wanted
                for e in entries
            ],
        )

    def find(
        self, code: str, chapter: Chapter, words: Sequence[str], index: int
    ) -> Decision | None:
        """The decision by the first words of the update line beginning at a
        word, within the chapter: the update's verse numbering can differ
        from the source's."""
        found = [
            d
            for d in self.entries
            if book_of(d.verse) == code
            and d.verse.split(" ")[1].split(":")[0] == chapter.number
            and tuple(words[index : index + len(d.follows)]) == d.follows
        ]
        require(
            len(found) <= 1,
            f"Two line decisions for one line: {code} {words[index : index + 12]}",
        )
        return found[0] if found else None

    def take(self, decision: Decision, chapter: Chapter) -> int | None:
        """The chapter word index where the decided line begins: its words,
        met once in the verse the decision names. None where the decision
        says the source has no such line: words of the update's the edition
        prints without, by a reading from Codex Alexandrinus."""
        require(
            decision not in self.taken,
            f"Line decision taken more than once: {decision.verse}: {decision.follows}",
        )
        label = decision.verse.split(":")[1]
        require(
            label in chapter.verse_starts,
            f"Line decision at a verse the source lacks: {decision.verse}",
        )
        if decision.line is None:
            self.taken.add(decision)
            return None
        lo = chapter.verse_starts[label]
        hi = chapter.verse_end(lo)
        wanted = scripture.words_of(decision.line)
        texts = chapter.texts[lo:hi]
        found = [
            lo + i
            for i in range(len(texts) - len(wanted) + 1)
            if texts[i : i + len(wanted)] == wanted
        ]
        require(
            bool(wanted) and len(found) == 1,
            f"Line decision not met once in its verse: {decision.verse}: {decision.line!r}",
        )
        self.taken.add(decision)
        return found[0]

    def check_all_taken(self) -> None:
        left = sorted(
            f"{d.verse}: {' '.join(d.follows)!r}"
            for d in self.entries
            if d not in self.taken
        )
        require(not left, f"Line decisions no line takes: {left}")


def place_break(
    index: int,
    source: Chapter,
    target: Chapter,
    alignment: Alignment,
    previous: int | None,
    code: str,
    decisions: Decisions,
) -> int | None:
    """Where an update line beginning at a word begins in the source, or
    None where a decision says the source has no such line."""
    line = source.texts[index : index + 12]
    decision = decisions.find(code, target, source.texts, index)
    position: int | None = None
    disordered = False
    try:
        position = placed(index, alignment, previous)
    except Unplaced:
        pass
    except Disordered:
        disordered = True
    # A line that opens a verse opens the verse of that number, where its
    # first words are matched there, or a word or two of the source's stand
    # before them: Brenton's Hebrew letters in Lamentations head their verses
    # whatever the update left out, and a respelt name opens its verse. Never
    # at or before the line already begun.
    label = source.verse_of(index)
    if (
        not disordered
        and source.verse_starts.get(label) == index
        and label in target.verse_starts
        and (previous is None or target.verse_starts[label] > previous)
    ):
        start = target.verse_starts[label]
        end = target.verse_end(start)
        near = [
            alignment.mapped[i]
            for i in range(index, index + 3)
            if i in alignment.mapped
        ]
        if position is None and near and all(start <= n < end for n in near):
            position = start
        elif position is not None and start < position <= start + 2:
            position = start
    if decision is not None:
        decided = decisions.take(decision, target)
        require(
            decided is None or decided != position,
            f"Line decision the words place alike: {decision.verse}: {decision.line!r}",
        )
        require(
            decided is None or previous is None or decided > previous,
            f"Line decision at or before the line already begun: {decision.verse}",
        )
        return decided
    if disordered:
        raise Disordered()
    at = target.verse_of(previous) if previous is not None else source.verse_of(index)
    require(
        position is not None,
        "Line the words do not place, and no decision does: "
        f"{code} {target.number}:{at}: line {' '.join(line)!r}",
    )
    assert position is not None
    return position


# The Old Testament.


def update_spans(chapter: Chapter, doc: Document) -> list[Span]:
    """The poems of an update chapter, in its own words: each run of lines,
    with the stanza breaks among them and the prose that resumes after."""
    spans: list[Span] = []
    lines: list[tuple[int, bool]] = []
    stanza = False
    # Whether words have been met: a stanza break before a chapter's first
    # words parts nothing (Proverbs 19).
    opened = False
    start: int | None = None
    start_stanza = False
    for block in chapter.blocks:
        marker = doc["content"][block]["marker"]
        first = chapter.first_words.get(block)
        if marker == STANZA:
            require(first is None, f"Stanza break with words: chapter {chapter.number}")
            stanza = opened
            continue
        if first is None:
            continue
        opened = True
        if marker == LINE:
            if start is None:
                start, start_stanza = first, stanza
            else:
                lines.append((first, stanza))
        else:
            require(
                not marker.startswith("q"),
                f"Unsupported line marker \\{marker}: chapter {chapter.number}",
            )
            if start is not None:
                resume = None if marker in FIXED else marker
                spans.append(Span(start, tuple(lines), first, resume, start_stanza))
                start, lines = None, []
        stanza = False
    if start is not None:
        spans.append(Span(start, tuple(lines), None, None, start_stanza))
    return spans


def place_spans(
    spans: Iterable[Span],
    source: Chapter,
    target: Chapter,
    code: str,
    decisions: Decisions,
) -> list[Span]:
    """The update's poems in the source's words."""
    alignment = Alignment.of(source.texts, target.texts)
    result = []
    previous: int | None = None

    def place(index: int) -> int | None:
        nonlocal previous
        try:
            found = place_break(
                index, source, target, alignment, previous, code, decisions
            )
        except Disordered:
            raise CheckFailed(
                f"Lines out of order: {code} {source.number}: "
                f"update line {' '.join(source.texts[index : index + 6])!r}"
            ) from None
        if found is not None:
            previous = found
        return found

    for span in spans:
        start = place(span.start)
        require(start is not None, f"Poem with no first line: {code} {source.number}")
        assert start is not None
        lines = []
        for index, stanza in span.lines:
            found = place(index)
            if found is not None:
                lines.append((found, stanza))
        end = None
        if span.end is not None:
            end = place(span.end)
            require(end is not None, f"Poem with no end: {code} {source.number}")
        result.append(Span(start, tuple(lines), end, span.resume, span.stanza))
    return result


def scrivener(kjv: Mapping[str, Document], policy: bible.policy.Policy) -> Witness:
    """Scrivener's King James Bible as a witness to which verses are verse:
    whether its counterpart of an edition verse stands in his lines or his
    prose; None for a verse without a counterpart, and in the Apocrypha,
    whose lines are the update's alone: the table does not place their
    verses, and the King James Tobit and Sirach follow another text and
    order. A Septuagint addition lettered to a verse
    (Job 42:17a) goes as that verse goes; a lettered verse the table gives
    a counterpart of its own (Proverbs 24:22f, the Hebrew's 30:1) goes as
    that counterpart goes."""
    # Read before the verses are placed, every verse would have no say.
    require("kjv" in policy.versification, "The verses are not yet placed")
    lined: dict[str, set[str]] = {}
    for code, doc in kjv.items():
        found = {
            label
            for label, verse in scripture.verses(doc).items()
            if any(
                doc["content"][block]["marker"].startswith("q")
                for block, _, _, _ in verse.parts
            )
        }
        lined[code] = found

    def witness(code: str, label: str) -> bool | None:
        if code not in policy.versification["old_testament"]:
            return None
        verse = verse_at(code, label)
        try:
            counterparts = versification.to_kjv(verse, policy=policy)
            if not counterparts and verse.letter:
                # A Septuagint addition lettered to a verse goes with that verse.
                counterparts = versification.to_kjv(
                    Verse(verse.book, verse.chapter, verse.number), policy=policy
                )
        except CheckFailed:
            # A verse whose place another verse has: no counterpart to read.
            return None
        if not counterparts:
            return None
        verses = lined[counterparts[0].book]
        return any(v.label in verses for v in counterparts)

    return witness


def witnessed(
    spans: Sequence[Span], chapter: Chapter, keep: Callable[[int], bool]
) -> list[Span]:
    """The poems' lines that a second witness sets as verse too: each run
    of them a poem, with prose resuming after it under the source's own
    paragraph where one begins there, or a new one where none does. A
    poem that opens after a dropped line opens without the stanza break
    that followed it, which stood between two lines of verse."""
    result: list[Span] = []
    for span in spans:
        positions = [(span.start, span.stanza), *span.lines]
        run: list[tuple[int, bool]] = []
        dropped = False
        for position, stanza in positions:
            if keep(position):
                run.append((position, stanza and not (dropped and not run)))
                continue
            dropped = True
            if run:
                resume = None if chapter.opens_block(position) else RESUMED
                result.append(
                    Span(run[0][0], tuple(run[1:]), position, resume, run[0][1])
                )
                run = []
        if run:
            result.append(
                Span(run[0][0], tuple(run[1:]), span.end, span.resume, run[0][1])
            )
    return result


def old_testament(
    documents: Mapping[str, Document],
    update: Mapping[str, Document],
    policy: bible.policy.Policy,
    witness: Witness = lambda code, label: None,
) -> dict[str, Document]:
    """Brenton's books with the update's poems set in lines, where a second
    witness sets the verse as verse too or has no say, except for declared
    prose verses. Each exception must suppress otherwise retained poetry."""
    decisions = Decisions.of(policy, documents)
    prose = {key for key in policy.lines.get("prose", {}) if book_of(key) in documents}
    taken: set[str] = set()
    result = dict(documents)
    for code, doc in documents.items():
        if code not in update:
            continue
        source = chapters(update[code])
        target: dict[str, Chapter] | None = None
        spans: dict[str, list[Span]] = {}
        for number, chapter in source.items():
            found = update_spans(chapter, update[code])
            if not found:
                continue
            # Half of the books have no poem: their chapters are never read.
            if target is None:
                target = chapters(doc)
            require(
                number in target, f"Update chapter the source lacks: {code} {number}"
            )
            placed_spans = place_spans(found, chapter, target[number], code, decisions)

            def keep(position: int, _target: Chapter = target[number]) -> bool:
                label = f"{_target.number}:{_target.verse_of(position)}"
                if witness(code, label) is False:
                    return False
                key = f"{code} {label}"
                if key in prose:
                    taken.add(key)
                    return False
                return True

            spans[number] = witnessed(placed_spans, target[number], keep)
        spans = {number: found for number, found in spans.items() if found}
        if not spans or target is None:
            continue
        result[code] = relined(doc, target, spans)
    decisions.check_all_taken()
    require(
        prose == taken,
        f"Prose decisions suppress no poetry: {', '.join(sorted(prose - taken))}",
    )
    return result


def paragraphs(
    documents: Mapping[str, Document], policy: bible.policy.Policy
) -> dict[str, Document]:
    """Apply declared marker changes and joins to existing prose blocks.

    Anchors are exact, apart from whitespace, in an assembled verse's words
    before revision. All targets are checked against the unchanged document;
    verse markers, notes and styles remain in their original content order.
    """
    grouped: dict[str, list[tuple[str, Paragraph]]] = {}
    for key, entries in policy.lines.get("paragraphs", {}).items():
        code, reference = key.split()
        require(
            code in documents, f"Paragraph decision in no Old Testament book: {key}"
        )
        grouped.setdefault(code, []).extend((reference, entry) for entry in entries)
    result = dict(documents)
    for code, book_entries in grouped.items():
        doc = documents[code]
        verses = scripture.verses(doc)
        edits: dict[int, str] = {}
        for reference, entry in book_entries:
            label = f"Paragraph decision {code} {reference}: {entry['at']!r}"
            require(reference in verses, f"{label}: missing verse")
            pattern = re.compile(r"(?<!\w)" + re.escape(entry["at"]) + r"(?!\w)")
            found = [
                (block, lo, match.start())
                for block, lo, hi, _ in verses[reference].parts
                for match in pattern.finditer(
                    scripture.plain(
                        usj.text_of(doc["content"][block]["content"][lo:hi])
                    )
                )
            ]
            require(len(found) == 1, f"{label}: anchor not met once")
            block, lo, offset = found[0]
            node = doc["content"][block]
            require(
                offset == 0 and not usj.text_of(node["content"][:lo]).strip(),
                f"{label}: anchor does not open a paragraph",
            )
            require(
                node["marker"] == entry["from"], f"{label}: expected {entry['from']}"
            )
            require(entry["to"] != entry["from"], f"{label}: changes nothing")
            require(block not in edits, f"{label}: conflicting paragraph decisions")
            if entry["to"] == "join":
                require(
                    block > 0
                    and usj.paragraph(doc["content"][block - 1]) in {"p", "m"},
                    f"{label}: join must follow ordinary prose in the same chapter",
                )
            edits[block] = entry["to"]
        blocks: list[Node] = []
        for index, node in enumerate(doc["content"]):
            marker = edits.get(index)
            if marker == "join":
                # Joined as the parser would have read them: one space
                # between, and none before a verse number.
                previous = blocks[-1]
                blocks[-1] = {
                    **previous,
                    "content": usj.trimmed(
                        usj.joined(previous["content"], [" "], node["content"])
                    ),
                }
            else:
                blocks.append({**node, "marker": marker} if marker else node)
        result[code] = usj.with_blocks(doc, blocks)
    return result


# Setting the lines.


def relined(
    doc: Document,
    by_chapter: Mapping[str, Chapter],
    spans_by_chapter: Mapping[str, Sequence[Span]],
) -> Document:
    """The document, whose chapters are given, with its poems set in lines."""
    # Each block's cuts: an offset in its words, the marker of what begins
    # there, and whether a stanza break stands before it.
    cuts: dict[int, list[tuple[int, str, bool]]] = {}
    dropped: set[int] = set()
    for number, spans in spans_by_chapter.items():
        chapter = by_chapter[number]
        for span in spans:
            end = len(chapter.words) if span.end is None else span.end
            for index, stanza in ((span.start, span.stanza), *span.lines):
                block, offset = chapter.block_of(index)
                cuts.setdefault(block, []).append((offset, LINE, stanza))
            if span.end is not None:
                block, offset = chapter.block_of(span.end)
                if span.resume is not None:
                    cuts.setdefault(block, []).append((offset, span.resume, False))
                else:
                    require(
                        chapter.opens_block(span.end),
                        f"Prose resumes inside a paragraph: {usj.book_code(doc)} {number}",
                    )
            # Within a poem the source's own paragraphs give way: each must
            # begin at a line, and a blank line among them goes.
            placed_at = {index for index, _ in span.lines} | {span.start}
            for block in chapter.blocks:
                first = chapter.first_words.get(block)
                if first is None:
                    position = _position(chapter, block)
                    if doc["content"][block].get("marker") in usj.HEADINGS:
                        continue
                    if span.start < position <= end:
                        require(
                            doc["content"][block]["marker"] == STANZA,
                            f"Empty paragraph in a poem: {usj.book_code(doc)} {number}",
                        )
                        dropped.add(block)
                elif span.start < first < end:
                    require(
                        first in placed_at,
                        "Source divides the poem where the update does not: "
                        f"{usj.book_code(doc)} {number}: "
                        f"{' '.join(chapter.texts[first : first + 6])!r}",
                    )
    blocks: list[Node] = []
    for index, node in enumerate(doc["content"]):
        if index in dropped:
            continue
        if index not in cuts:
            blocks.append(node)
            continue
        require(
            node["marker"] not in FIXED,
            f"Line inside a \\{node['marker']}: {usj.book_code(doc)}",
        )
        for marker, stanza, content in _pieces(node["content"], sorted(cuts[index])):
            if not content:
                continue
            if marker is None:
                blocks.append({**node, "content": content})
                continue
            if stanza:
                blocks.append(usj.para(STANZA))
            blocks.append(usj.para(marker, *content))
    return usj.with_blocks(doc, blocks)


def _position(chapter: Chapter, block: int) -> int:
    """Where a block without words stands: at the first word that follows it."""
    return min(
        (first for b, first in chapter.first_words.items() if b > block),
        default=len(chapter.words),
    )


def _pieces(
    content: Content, cuts: Sequence[tuple[int, str, bool]]
) -> list[tuple[str | None, bool, Content]]:
    """The content divided at its cuts, each taken back over the quotation
    mark or bracket that opens its first word: what stands before the first
    cut keeps its own marker (None)."""
    text = usj.text_of(content)
    pieces: list[tuple[str | None, bool, Content]] = []
    rest = list(content)
    at = 0
    previous: tuple[str | None, bool] = (None, False)
    for offset, marker, stanza in cuts:
        while offset > at and text[offset - 1] in OPENING:
            offset -= 1
        require(offset >= at, "Cuts out of order")
        left, rest = usj.split(rest, offset - at, notes_left=False)
        # A note at the cut stands with the word it is set against: after a
        # space, before the line's first word, it glosses that word, as
        # Brenton's callers stand before their words, and goes with the
        # line; set close against the last word before the cut, it stays.
        while len(left) >= 2 and isinstance(left[-1], str) and not left[-1].strip():
            note = left[-2]
            before = left[-3] if len(left) >= 3 else " "
            if not (
                isinstance(note, dict)
                and usj.is_note(note)
                and isinstance(before, str)
                and before.endswith(" ")
            ):
                break
            left = left[:-2]
            rest = [note, *rest]
        while (
            rest
            and isinstance(rest[0], dict)
            and usj.is_note(rest[0])
            and left
            and isinstance(left[-1], str)
            and not left[-1].endswith(" ")
        ):
            left = [*left, rest[0]]
            rest = rest[1:]
        # A note before the number of the verse the line opens is the verse
        # before's, and stays on its line (Psalm 9:27).
        lead = 0
        while lead < len(rest) and usj.is_type(rest[lead], "note"):
            lead += 1
        if lead and lead < len(rest) and usj.is_type(rest[lead], "verse"):
            left, rest = [*left, *rest[:lead]], rest[lead:]
        pieces.append((*previous, usj.trimmed(left)))
        previous = (marker, stanza)
        at = offset
    pieces.append((*previous, usj.trimmed(rest)))
    return pieces


def _divided(block: Node, cuts: Sequence[tuple[int, str, bool]]) -> list[Node]:
    """A block divided at its cuts, each piece under the marker of its cut."""
    return [
        {**block, "marker": marker or block["marker"], "content": content}
        for marker, _, content in _pieces(block["content"], cuts)
        if content
    ]


# Source instructions and acrostic names, after the lines have been placed.


# The instructions Brenton leaves within their verses, which stay inline.
INLINE_PAUSES = frozenset({"PSA 67:8"})


def _verses_at(content: Content) -> list[tuple[int, str]]:
    """Where each verse of some content begins among its words."""
    return [
        (start, label)
        for label, start, _ in _segments(content)[1:]
        if label is not None
    ]


def pauses(doc: Document) -> Document:
    """Set a terminal Pause instruction on its own right-aligned line.

    Only a standalone sentence in poetry qualifies; a song's attribution,
    prose and notes keep their form. The existing caller stays with Pause.
    Refuse any other Pause in the words unless its verse is declared to keep
    it inline, and a declaration in the document's chapters that no Pause
    meets.
    """
    book = usj.book_code(doc)
    blocks: list[Node] = []
    chapter, verse = "", ""
    kept: set[str] = set()
    chapters: set[str] = set()
    # The blocks, by their place in the result, that keep a declared Pause.
    inline: set[int] = set()
    for block in doc["content"]:
        if usj.is_type(block, "chapter"):
            chapter, verse = block["number"], ""
            chapters.add(f"{book} {chapter}")
        content = block.get("content", [])
        text = usj.text_of(content)
        starts = _verses_at(content)
        cut, declared_here = None, False
        for match in re.finditer(r"\bPause\b", text):
            number = next(
                (v for at, v in reversed(starts) if at <= match.start()), verse
            )
            here = f"{book} {chapter}:{number}"
            before = text[: match.start()].rstrip()
            terminal = re.fullmatch(r"Pause\.\s*", text[match.start() :])
            if before.endswith("A song of") or (
                block.get("marker") == "qr" and terminal and not before
            ):
                continue
            if (
                block.get("marker") in {"q1", "q2"}
                and terminal
                and (not before or before[-1] in ".!?")
            ):
                cut = match.start()
            elif here in INLINE_PAUSES:
                kept.add(here)
                declared_here = True
            else:
                require(False, f"Unexpected Pause instruction: {here}")
        if starts:
            verse = starts[-1][1]
        start = len(blocks)
        blocks += _divided(block, [(cut, "qr", False)]) if cut is not None else [block]
        if declared_here:
            inline.update(range(start, len(blocks)))
    declared = {key for key in INLINE_PAUSES if key.split(":")[0] in chapters}
    require(
        kept == declared,
        f"Inline Pause declarations no Pause meets: {sorted(declared - kept)}",
    )
    marked: list[Node] = []
    for index, block in enumerate(blocks):
        if usj.paragraph(block) == "qr" or index in inline:
            text = usj.text_of(block["content"])
            for match in reversed(list(re.finditer(r"\bPause[.:]", text))):
                content = block["content"]
                head, rest = usj.split(content, match.start(), notes_left=False)
                words, tail = usj.split(rest, match.end() - match.start())
                # A verse consisting entirely of the instruction still has
                # its milestone in the paragraph, outside its character style.
                while words and usj.is_type(words[0], "verse"):
                    head = usj.joined(head, words[:1])
                    words = words[1:]
                if len(words) == 1 and usj.is_type(words[0], "char", "qs"):
                    continue
                block = {
                    **block,
                    "content": usj.joined(head, [usj.char("qs", *words)], tail),
                }
        marked.append(block)
    return usj.with_blocks(doc, marked)


# These are Brenton's spellings and placements, including the repeated Teth
# in chapter 3 and the names inside verses. They describe the pinned source,
# not a reconstructed Hebrew alphabet; no absent label is supplied.
ACROSTIC_NAMES = tuple(
    "Aleph. Beth. Gimel. Daleth. He. Vau. Zain. Heth. Teth. Jod. "
    "Chaph. Lamed. Mem. Nun. Samech. Ain. Phe. Tsade. Koph. Rhechs. "
    "Chsen. Thau.".split()
)


def acrostic_inventory(chapter: str) -> list[tuple[str, str]]:
    """Brenton's acrostic names in a chapter, with their verses: none
    outside Lamentations 1–4."""
    if chapter not in ("1", "2", "3", "4"):
        return []
    names = list(ACROSTIC_NAMES)
    labels = [str(n) for n in range(1, 23)]
    if chapter == "3":
        names[19] = "Rechs."
        names.insert(9, "Teth.")
        labels = (
            "1 5 8 9 12 15 19 22 25 27 30 32 34 39 40 43 45 49 52 55 58 61 65".split()
        )
    elif chapter == "4":
        names[19] = "Rechs."
        labels = "1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 17 18 20 21 22".split()
    return list(zip(labels, names, strict=True))


# The names Brenton sets inside their verses rather than at their openings.
WITHIN_VERSE = frozenset(
    {("3", "45", "Ain."), ("4", "17", "Tsade."), ("4", "18", "Koph.")}
)


def acrostics(doc: Document) -> Document:
    """Give the existing small-cap names of Lamentations 1–4 qa headings.

    Split at word offsets, keeping each verse node before the words it
    governed. Headings add no stanza breaks; qa supplies their style.
    Refuse a changed inventory, an unexpected placement in its verse, or a
    declared placement that is no longer met.
    """
    blocks: list[Node] = []
    chapter, verse = "", ""
    expected: list[tuple[str, str]] = []
    seen: list[tuple[str, str]] = []
    within: set[tuple[str, str, str]] = set()
    # Whether the verse's words have begun before the place reached.
    begun = False

    def label(text: str) -> None:
        address = f"LAM {chapter}:{verse}"
        require(
            (verse, text) in expected,
            f"Unexpected acrostic label: {address}: {text!r}",
        )
        seen.append((verse, text))
        if begun:
            within.add((chapter, verse, text))

    def check_chapter() -> None:
        require(
            seen == expected,
            f"Unexpected acrostic inventory: LAM {chapter}:{verse}: {seen!r}",
        )
        declared = {name for name in WITHIN_VERSE if name[0] == chapter}
        require(
            within == declared,
            "Unexpected acrostic placement: "
            + ", ".join(f"LAM {c}:{v}: {t!r}" for c, v, t in sorted(within ^ declared)),
        )

    for block in doc["content"]:
        if usj.is_type(block, "chapter"):
            check_chapter()
            chapter, verse = block["number"], ""
            expected = acrostic_inventory(chapter)
            seen, within, begun = [], set(), False
        if block.get("marker") == "qa":
            for item in block["content"]:
                if usj.is_type(item, "verse"):
                    verse, begun = item["number"], False
            label(usj.text_of(block["content"]))
            begun = True
            blocks.append(block)
            continue
        cuts: list[tuple[int, str, bool]] = []
        offset = 0
        for item in block.get("content", []):
            if usj.is_type(item, "verse"):
                verse, begun = item["number"], False
            elif isinstance(item, str):
                offset += len(item)
                begun = begun or bool(item.strip())
            elif "content" in item and not usj.is_note(item):
                text = usj.text_of(item["content"])
                if item.get("marker") == "sc" and verse:
                    label(text)
                    require(
                        block.get("marker") in {"q1", "q2"},
                        f"Acrostic outside poetry: LAM {chapter}:{verse}",
                    )
                    cuts.extend(
                        [
                            (offset, "qa", False),
                            (offset + len(text), block["marker"], False),
                        ]
                    )
                offset += len(text)
                begun = begun or bool(text.strip())
        blocks += _divided(block, cuts) if cuts else [block]
    check_chapter()
    return usj.with_blocks(
        doc,
        (
            (
                {
                    **block,
                    "content": usj.mapped(
                        block["content"],
                        lambda node: (
                            node["content"] if usj.is_type(node, "char", "sc") else node
                        ),
                    ),
                }
                if block.get("marker") == "qa"
                else block
            )
            for block in blocks
        ),
    )


def descriptive_titles(doc: Document) -> Document:
    """Give a complete source title d, leaving highlighted prose fragments
    in their sentences. A title ends with a period, whether it fills its
    prose paragraph or the prose resumes after it, as Concerning Damascus
    does; one that runs on into what it introduces, as with saying, stays
    prose. Existing descriptive titles retain their structure and verse
    nodes.
    """
    blocks: list[Node] = []
    for block in doc["content"]:
        cuts: list[tuple[int, str, bool]] = []
        if block.get("marker") == "p":
            for item in block["content"]:
                if usj.is_type(item, "verse") or usj.is_type(item, "note"):
                    continue
                if usj.is_type(item, "char", "sc"):
                    title = usj.text_of(item["content"])
                    if title.endswith("."):
                        cuts = [(0, "d", False), (len(title), "p", False)]
                break
        blocks += _divided(block, cuts) if cuts else [block]
    return usj.with_blocks(doc, blocks)


def check(policy: bible.policy.Policy) -> None:
    data = policy.lines
    require_fields(data, {"why", "breaks"}, {"paragraphs", "prose"}, "Lines file")
    for key, why in data.get("prose", {}).items():
        require(
            VERSE_KEY.fullmatch(key) is not None,
            f"Prose decision at what is not a verse: {key}",
        )
        require(
            isinstance(why, str) and bool(why.strip()),
            f"Prose decision without a why: {key}",
        )
    for key, entries in data["breaks"].items():
        require(
            VERSE_KEY.fullmatch(key) is not None,
            f"Line decision at what is not a verse: {key}",
        )
        require(bool(entries), f"Line decision without a line: {key}")
        for entry in entries:
            require_fields(
                entry, {"follows", "line", "why"}, (), f"Line decision {key}"
            )
            require(
                bool(scripture.words_of(entry["follows"]))
                and (entry["line"] is None or bool(scripture.words_of(entry["line"])))
                and bool(entry["why"]),
                f"Line decision without words or a why: {key}",
            )
    for key, paragraph_entries in data.get("paragraphs", {}).items():
        require(
            VERSE_KEY.fullmatch(key) is not None,
            f"Paragraph decision at what is not a verse: {key}",
        )
        require(bool(paragraph_entries), f"Paragraph decision without an entry: {key}")
        for paragraph_entry in paragraph_entries:
            label = f"Paragraph decision {key}"
            require_fields(paragraph_entry, {"at", "from", "to", "why"}, (), label)
            at, why = paragraph_entry["at"], paragraph_entry["why"]
            require(
                isinstance(at, str)
                and bool(at)
                and at == scripture.plain(at)
                and isinstance(why, str)
                and bool(why.strip()),
                f"{label}: needs an anchor with normal spaces and a why",
            )
            require(
                paragraph_entry["from"] in ("p", "m")
                and paragraph_entry["to"] in ("p", "m", "join"),
                f"{label}: unsupported paragraph marker",
            )
