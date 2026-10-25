"""The notes of the assembled books, set as the edition prints them: Brenton's
notes and cross-references and the 1611 margin as footnotes that name the
words they are about, and the quotation links at their verses.

A note is read once, against the verse it stands in as the edition numbers
it. Everything it needs is in the assembled book and the policy.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import TypedDict

import bible.policy
import bible.references
import bible.terminology
from bible import (
    citations,
    crossrefs,
    lemmas,
    notes,
    repairs,
    scripture,
    usj,
    versification,
)
from bible.checks import present, require, require_used
from bible.policy_schema import NoteOverride, WordingChange
from bible.references import verse_at
from bible.scripture import word_spans, words_of
from bible.usj import Content, Document, Node


class NoteDerivation(TypedDict):
    """How a note was read: recorded as it is set, for its row of the review."""

    key: str
    reference: str
    rule: str
    # The words glossed, which a lemma widens until they occur once, and the
    # rendering that measured them.
    glossed: str | None
    reading: str | None
    source: str
    style: str


class NoteRow(NoteDerivation):
    """A note's row of the review, with the verse, the lemma, and the note as
    the finished book prints them."""

    verse: str
    lemma: str | None
    note: str


@dataclass(frozen=True)
class Context:
    """What reading a note needs beside its book."""

    policy: bible.policy.Policy
    # What the edition prints, which a citation must name.
    inventory: scripture.Inventory
    books: bible.references.Books

    @property
    def terms(self) -> bible.terminology.Registry:
        return bible.terminology.registry(self.policy)

    @property
    def prose(self) -> Mapping[str, Sequence[WordingChange]]:
        """Each note's declared changes of wording, by its key."""
        return notes.note_prose(self.policy)


@dataclass
class Report:
    """What a stage met while it worked, for the checks that span the
    edition and for the review."""

    # Each citation read, as (dialect, the source's name for the book).
    names: set[tuple[str, str | None]] = field(default_factory=set)
    # The keys of the citation decisions and prose changes that were met.
    decided: set[str] = field(default_factory=set)
    edited: list[str] = field(default_factory=list)
    # Every printed or omitted note's key, which a decision may name, and
    # how each printed note was read, for the review.
    keys: set[str] = field(default_factory=set)
    rows: list[NoteDerivation] = field(default_factory=list)
    # The keys of the source notes a decision leaves out.
    omitted: list[str] = field(default_factory=list)
    # The keys of the edition's rendering notes a reversed 1611 margin
    # stands for.
    covered: list[str] = field(default_factory=list)

    def read(
        self,
        tongue: citations.Dialect,
        key: str,
        found: Sequence[citations.Citation],
        policy: bible.policy.Policy,
    ) -> None:
        self.names.update((tongue.name, c.name) for c in found)
        if citations.decisions(key, policy=policy):
            self.decided.add(key)


def printed(
    read: notes.Read,
    span: lemmas.Span | None,
    glossed: lemmas.Span | None,
    rule: str,
    exception: NoteOverride,
    ctx: Context,
    report: Report,
) -> Node:
    """A note as the edition prints it, and how it was read for its row of
    the review (finished_rows)."""
    key, verse, words = read.key, read.verse, read.words
    body = notes.with_terms(read.body, ctx.terms)
    for edit in ctx.prose.get(key, ()):
        body = notes.edited(body, edit["from"], edit["to"], key)
        report.edited.append(key)
    lemma = lemmas.lemma_text(verse.text, words, span) if span else None
    # A changed boundary stop belongs to the scope the note declares, not to
    # its printed lemma (notes.boundary_stop): it follows the words declared,
    # so a lemma widened past them takes in none.
    boundary = ""
    if span and glossed and span[1] == glossed[1]:
        stop, end = notes.boundary_stop(read.scope), words[span[1]][2]
        if stop and verse.text[end : end + 1] == stop:
            boundary = stop
    runs, terms, original = notes.displayed(
        body, *lemmas.echoes(verse.text, words, span, glossed), books=ctx.books
    )
    runs = notes.finished(runs, terms, lemma, exception.get("sentence"), ctx.terms, key)
    report.keys.add(key)
    report.rows.append(
        dict(
            key=key,
            reference=read.reference,
            rule=rule,
            glossed=lemmas.lemma_text(verse.text, words, glossed) if glossed else None,
            reading=read.body.alternative,
            source=scripture.plain(read.source),
            style=body.rule,
        )
    )
    extra = usj.Extra({"x-key": key})
    if read.category:
        extra["category"] = read.category
    if boundary:
        assert lemma is not None
        extra["x-scope"] = {"declared": lemma + boundary}
    return notes.linked(
        notes.footnote(read.reference, lemma, runs, **extra), body, ctx.books
    )


def brenton(
    code: str,
    doc: Document,
    links: Sequence[crossrefs.Link],
    mended: frozenset[str],
    ctx: Context,
) -> tuple[Document, Report]:
    """A book of Brenton's with his notes and cross-references set as
    notes, each naming its lemma. A cross-reference becomes a note of "See"
    and what it cites; those the quotation links replace are left out."""
    policy, report = ctx.policy, Report()
    tongue = citations.dialect("brenton", policy=policy)
    exceptions = policy.brenton_notes["notes"]
    found = []
    verses = scripture.verses(doc)
    for source_reference, source_verse in verses.items():
        for offset, note in source_verse.notes:
            key = note["x-key"]
            exception = exceptions.get(key, {})
            if exception.get("omitted"):
                report.keys.add(key)
                report.omitted.append(key)
                continue
            override = exception.get("note")
            reference, verse = source_reference, source_verse
            if "verse" in exception:
                # A note eBible has in the wrong verse is read in the right one.
                reference = exception["verse"]
                require(
                    reference in verses
                    and reference != source_reference
                    and "x-scope" not in note,
                    f"Note moved to no other verse of its book: {key}",
                )
                verse = verses[reference]
            home = verse_at(code, reference)
            if note.get("category") == "edition":
                body = notes.authored_body(
                    note, override, key, quotation=exception.get("quotation", False)
                )
                source = text = body.plain
                cited = citations.scan(
                    text, tongue, home, key, ctx.inventory, policy=policy
                )
                body = notes.bound(body, cited, key)
            else:
                pieces = notes.source_pieces(note)
                source = ("See " if note["marker"] == "x" else "") + notes.source_text(
                    note
                )
                text = notes.text_of(pieces)
                cited = citations.scan(
                    text, tongue, home, key, ctx.inventory, policy=policy
                )
                body = notes.source_body(
                    pieces,
                    cited,
                    override,
                    key,
                    source,
                    quotation=exception.get("quotation", False),
                )
            report.read(tongue, key, cited, policy)
            found.append(
                notes.Read(
                    key,
                    note["marker"],
                    reference,
                    verse,
                    word_spans(verse.text),
                    offset,
                    body,
                    tuple(cited),
                    source,
                    text,
                    note.get("x-scope"),
                    note.get("category"),
                )
            )
    merged = crossrefs.merged_notes(code, found, links, policy=policy)
    # A merged note doesn't print, so an exception or a correction to it
    # would go unused unnoticed, unless the exception only moved the note to
    # the verse of the link that replaces it, saying it is about no words.
    excepted = sorted(
        key
        for key in merged
        if (excepting := exceptions.get(key))
        and not (
            "verse" in excepting
            and excepting.get("lemma") is None
            and not set(excepting) - {"verse", "lemma", "why"}
        )
    )
    require(
        not excepted, f"Brenton note exception for a note a link replaces: {excepted}"
    )
    corrected = sorted(k for k in merged if k.partition(" ")[2] in mended)
    require(not corrected, f"Brenton correction to a note a link replaces: {corrected}")
    replacements: dict[str, Node | None] = {key: None for key in report.omitted}
    moved: list[tuple[str, int, Node]] = []
    for read in found:
        if read.key in merged:
            replacements[read.key] = None
            if read.key in exceptions:
                report.keys.add(read.key)
            continue
        key, verse, words = read.key, read.verse, read.words
        exception = exceptions.get(key, {})
        # A moved or deliberately narrow note stands at its named words.
        relocated = "verse" in exception or exception.get("widen") is False
        if relocated:
            require(
                read.scope is None,
                f"Alexandrine lemma also has a Brenton exception: {key}",
            )
            # A note about no words is moved onto the link that replaces it.
            require(
                exception.get("lemma") is not None,
                f"Note moved about no words with no link to replace it: {key}",
            )
            span, glossed, rule = lemmas.overridden_lemma(
                verse.text,
                words,
                exception,
                None,
                None,
                None,
                key,
                exception.get("occurrence"),
            )
        elif read.scope is None:
            span, glossed, rule = lemmas.inferred(
                read.kind,
                verse.text,
                words,
                read.offset,
                read.body.alternative,
                exception,
                key,
                addition=read.body.addition,
            )
        elif "declared" in read.scope:
            require(
                "lemma" not in exception,
                f"Alexandrine lemma also has a Brenton exception: {key}",
            )
            span, glossed, rule = lemmas.declared(
                verse.text, words, read.offset, read.scope["declared"], key
            )
        else:
            span, glossed, rule = lemmas.preserved(
                words, read.scope["lemma"], read.scope["glossed"], key
            )
        note = printed(read, span, glossed, rule, exception, ctx, report)
        # Declared words also determine placement, before any context added
        # to make the printed lemma unique. Inferred and null lemmas keep
        # their caller.
        if isinstance(exception.get("lemma"), str) and glossed is not None:
            at = words[glossed[0]][1]
            if relocated or at != read.offset:
                replacements[key] = None
                moved.append((read.reference, at, note))
                continue
        # A moved note left here would stand in the verse it was moved from.
        assert not relocated, key
        replacements[key] = note

    def change(item: Node) -> Node | Content | None:
        if item["type"] == "note":
            require(
                item.get("x-key") in replacements, f"Note outside any verse: {code}"
            )
            return replacements[item["x-key"]]
        if item["type"] == "char" and item["marker"] not in usj.FIELDS:
            return outside(item)
        return item

    doc = usj.with_content(doc, lambda content: usj.mapped(content, change))
    if moved:
        verses = scripture.verses(doc)
        doc = scripture.edited(
            doc,
            [(verses[reference], at, at, [note]) for reference, at, note in moved],
            split_styles=True,
        )
    return doc, report


def outside(span: Node) -> Node | Content:
    """A character style with the notes that open it set before it: a caller
    just inside "\\add" belongs to the word, not to its styling. A note
    anywhere else within a style is refused."""
    content = span["content"]
    leading = 0
    while leading < len(content) and usj.is_type(content[leading], "note"):
        leading += 1
    rest = content[leading:]
    stray = [n.get("x-key") for n in usj.notes_of(rest)]
    require(not stray, f"Note inside a character span: {stray}")
    if not leading:
        return span
    return [*content[:leading], {**span, "content": rest}]


def anchor_category(lemma: list[str], anchor: list[str]) -> str | None:
    """How the anchor's words differ from the lemma's, or None if by more than
    one category allows: words joined or parted, or one word's letter slip."""
    if "".join(lemma) == "".join(anchor):
        return "word division"
    differing = [(x, y) for x, y in zip(lemma, anchor) if x != y]
    if len(lemma) == len(anchor) and len(differing) == 1:
        _, old, new = repairs.change(*differing[0])
        return repairs.letter_slip(old, new)
    return None


def george(
    code: str,
    doc: Document,
    listed: Sequence[Mapping[str, str]],
    ctx: Context,
    *,
    original: Document,
) -> tuple[Document, Report]:
    """A book of the Cambridge text with the 1611 marginal notes set on it as
    notes.

    Each note is anchored at George's lemma, or at the Cambridge words recorded
    for it in edition/kjv-notes.json where the spelling differs, the lemma
    occurs more than once, or the reference is wrong. The note names the words
    it is anchored at, widened until they occur only once in the verse, and
    its renderings take in the same words. Where the text now prints the
    margin's alternative, a former-reading decision turns the note round to
    give the King James words it replaced, on a unique current-text anchor.
    """
    policy, report = ctx.policy, Report()
    tongue = citations.dialect("george", policy=policy)
    # The notes the edition wrote on the words it changed stand in the book
    # already: they are printed first, and the 1611 notes set among them. A
    # margin turned round stands for the edition's own note on the same
    # correction.
    doc = without_covered_renderings(doc, listed, policy, report)
    doc = with_edition_notes(code, doc, tongue, ctx, report)
    verses = scripture.verses(doc)
    original_verses = scripture.verses(original)
    changes: list[tuple[scripture.Verse, int, int, Content]] = []
    for note in listed:
        key = note["key"]
        override = policy.kjv_notes["notes"].get(key, {})
        former = override.get("former")
        if former is not None:
            conflicts = set(override) & {
                "omitted",
                "lemma",
                "occurrence",
                "widen",
                "quotation",
                "verse",
            }
            require(
                not conflicts,
                f"Marginal note former conflicts with {sorted(conflicts)}: {key}",
            )
            require(
                "anchor" in override, f"Marginal note former needs an anchor: {key}"
            )
            source_verse = original_verses.get(note["reference"])
            require(
                former
                and source_verse is not None
                and source_verse.text.count(former) == 1
                and len(
                    lemmas.occurrences(word_spans(source_verse.text), words_of(former))
                )
                == 1,
                f"Marginal note former not found exactly once in original verse: {key}",
            )
            require(
                words_of(former) != words_of(override["anchor"]),
                f"Marginal note former changes nothing: {key}",
            )
        if override.get("omitted"):
            # A note whose reading the Byzantine text prints, or which glosses
            # words of the Received Text the edition no longer has.
            report.omitted.append(key)
            continue
        reference = override.get("verse", note["reference"])
        require(reference in verses, f"Marginal note verse missing: {key}")
        verse = verses[reference]
        words = word_spans(verse.text)
        anchor = words_of(override.get("anchor", note["lemma"]))
        if "anchor" in override and former is None:
            lemma = words_of(note["lemma"])
            require(anchor != lemma, f"Marginal note anchor changes nothing: {key}")
            repairs.check_category(
                anchor_category(lemma, anchor),
                override,
                "Marginal note anchor",
                key,
                what="difference",
            )
        span, glossed, rule, first = lemmas.anchored(
            verse.text, words, anchor, override.get("occurrence"), override, key
        )
        text = note["note"]
        cited = citations.scan(
            text, tongue, verse_at(code, reference), key, ctx.inventory, policy=policy
        )
        if former is not None:
            text, cited = reversed_margin(text, cited, former, anchor, key)
        report.read(tongue, key, cited, policy)
        body = notes.source_body(
            notes.labelled_pieces(text),
            cited,
            override.get("note"),
            key,
            text,
            quotation=override.get("quotation", False),
        )
        if former is not None:
            body = replace(body, rule="editorial reversal")
        read = notes.Read(
            key,
            "f",
            reference,
            verse,
            words,
            words[first][1],
            body,
            tuple(cited),
            note["note"],
            text,
        )
        footnote = printed(read, span, glossed, rule, override, ctx, report)
        changes.append((verse, read.offset, read.offset, [footnote]))
    return scripture.edited(doc, changes), report


def covers(
    lemma: list[str], former: list[str], anchor: list[str], old: list[str]
) -> bool:
    """Whether a rendering note, whose lemma the former King James words
    replace, says what a reversed margin says: the margin's anchor with the
    note's lemma turned back is the margin's former words, or the note's
    lemma with the anchor turned back is the note's former words."""

    def turned(text: list[str], part: list[str], into: list[str]) -> list[str] | None:
        at = found(text, part)
        return None if at is None else text[:at] + into + text[at + len(part) :]

    return turned(anchor, lemma, former) == old or turned(lemma, anchor, old) == former


def without_covered_renderings(
    doc: Document,
    listed: Sequence[Mapping[str, str]],
    policy: bible.policy.Policy,
    report: Report,
) -> Document:
    """The book without the rendering notes that a 1611 margin turned round
    stands for: where its verse has such notes, a former-reading decision
    must cover one of them, saying the same, and that note is left out. (The
    margin's own checks hold its words to the text either way.) Each such
    note is covered by one margin at most."""
    reversed_margins = [
        (note["key"], note, override)
        for note in listed
        for override in [policy.kjv_notes["notes"].get(note["key"], {})]
        # The margin's own checks name what is missing.
        if override.get("former") is not None and "anchor" in override
    ]
    if not reversed_margins:
        return doc
    verses = scripture.verses(doc)
    covered: list[str] = []
    for key, note, override in reversed_margins:
        former = override["former"]
        verse = present(
            verses.get(note["reference"]), f"Marginal note verse missing: {key}"
        )
        anchor, old = words_of(str(override["anchor"])), words_of(str(former))
        renderings = [
            n
            for _, n in verse.notes
            if n.get("category") == "edition"
            and n.get("x-key", "").split(" ")[-1].startswith("rendering")
        ]
        if not renderings:
            continue
        found = [
            n
            for n in renderings
            if covers(
                words_of(str(n["x-scope"]["declared"])),
                words_of(
                    usj.text_of(
                        next(
                            (
                                c["content"]
                                for c in n["content"]
                                if isinstance(c, dict) and c.get("marker") == "fqa"
                            ),
                            [],
                        )
                    )
                ),
                anchor,
                old,
            )
        ]
        require(
            len(found) == 1,
            f"Marginal note former covers no rendering note, or more than one: {key}",
        )
        require(
            found[0]["x-key"] not in covered,
            f"Marginal note former covers a rendering note another covers: {key}",
        )
        covered.append(found[0]["x-key"])
    report.covered.extend(covered)
    if not covered:
        return doc
    return scripture.map_notes(doc, lambda n: None if n.get("x-key") in covered else n)


def reversed_margin(
    text: str,
    cited: Sequence[citations.Citation],
    former: str,
    anchor: list[str],
    key: str,
) -> tuple[str, list[citations.Citation]]:
    """A 1611 note whose alternative the text now prints, turned round to
    give the King James words it replaced: "Or," and the former words in
    place of its label and alternative, and its citations kept after them.
    Where the alternative the text prints is not the note's first, the
    former words are given first, as another alternative, and the note's
    own words follow; a prose change can then drop the adopted one."""
    pieces = notes.labelled_pieces(text)
    require(
        bool(pieces) and pieces[0][0] == "label",
        f"Marginal note former has no label: {key}",
    )
    start = len(pieces[0][1])
    end = cited[0].start if cited else len(text)
    alternative = text[start:end].rstrip(" ,.")
    if contains(anchor, words_of(alternative)):
        turned = f"Or, {former}{text[start + len(alternative):]}"
    else:
        require(
            contains(words_of(alternative), anchor),
            f"Marginal note former: the text does not print the margin's alternative: {key}",
        )
        turned = f"Or, {former}; or, {text[start:]}"
    shift = len(turned) - len(text)
    return turned, [replace(c, start=c.start + shift, end=c.end + shift) for c in cited]


def found(words: list[str], wanted: list[str]) -> int | None:
    """Where the words first hold the wanted words together, in order."""
    if not wanted:
        return None
    return next(
        (
            i
            for i in range(len(words) - len(wanted) + 1)
            if words[i : i + len(wanted)] == wanted
        ),
        None,
    )


def contains(words: list[str], wanted: list[str]) -> bool:
    """Whether the words hold the wanted words together, in order."""
    return found(words, wanted) is not None


def with_relocation_notes(
    code: str, doc: Document, kjv: Mapping[str, Document], ctx: Context
) -> Document:
    """A book with a note where the Hebrew, which the King James Bible
    follows, has passages that the Greek sets in another order
    (edition/versification.json, relocations): at the verse after which the
    Hebrew has them, which passages are printed elsewhere, and in what
    chapter. Their verses print the Hebrew's labels where they stand (see
    assembly.printed), so no note at them says so again. Each decision is
    held to the runs the place stage worked out: the Hebrew passage's
    verses must stand here, beginning at the verse it names."""
    policy = ctx.policy
    label = ctx.terms.display("hebrew")
    found: list[tuple[bible.references.Passage, list[bible.references.Verse]]] = []
    relocations = versification.relocations(code, policy=policy)
    if not relocations:
        return doc
    shown = scripture.printed(doc)
    for reference, entry in relocations.items():
        require(bool(entry.get("why")), f"Relocation without its reason: {reference}")
        theirs = bible.references.parse_passage(reference)
        held = [
            v
            for verse in theirs.verses
            for v in versification.from_kjv(verse, policy=policy)
        ]
        first = bible.references.parse_verse(entry["to"])
        require(
            bool(held)
            and all(v.book == code and v.chapter == first.chapter for v in held)
            and held[0] == first,
            f"Relocated passage does not begin where it is said to: {reference}",
        )
        # The labels its verses print are the Hebrew's verses the runs put
        # them at, one by one.
        require(
            [shown.get(v.label) for v in held] == [v.label for v in theirs.verses],
            f"Relocated passage printed under other labels than its runs give: "
            f"{reference}",
        )
        found.append((theirs, held))
    verses = scripture.verses(doc)
    changes: list[tuple[scripture.Verse, int, int, Content]] = []
    # Where the Hebrew has them: after the King James verse before the first
    # of a run of passages that follow one another there.
    chapters = usj.inventory(kjv[versification.kjv_book(code, policy=policy)])
    starts = {theirs.first: theirs for theirs, _ in found}
    ends = {theirs.last: held for theirs, held in found}
    for theirs, held in sorted(
        found, key=lambda item: (item[0].first.chapter, item[0].first.number)
    ):
        first = theirs.first
        if first.number > 1:
            before = bible.references.Verse(first.book, first.chapter, first.number - 1)
        else:
            last = chapters[str(first.chapter - 1)][-1]
            before = bible.references.Verse(first.book, first.chapter - 1, int(last))
        if before in ends:
            continue
        printed = [notes.spanned(list(theirs.verses))]
        chapters_held = {held[0].chapter}
        end = theirs.last
        while True:
            after = bible.references.Verse(end.book, end.chapter, end.number + 1)
            if str(after.number) not in chapters.get(str(end.chapter), []):
                after = bible.references.Verse(end.book, end.chapter + 1, 1)
            if after not in starts:
                break
            following = starts[after]
            printed.append(notes.spanned(list(following.verses)))
            chapters_held.add(ends[following.last][0].chapter)
            end = following.last
        listed = (
            " and ".join(printed)
            if len(printed) <= 2
            else ", ".join(printed[:-1]) + ", and " + printed[-1]
        )
        anchor = versification.from_kjv(before, policy=policy)
        require(bool(anchor), f"Relocated passage follows no verse here: {theirs}")
        address = anchor[-1].label
        require(
            len(chapters_held) == 1,
            f"Relocated passages printed in more than one chapter: {theirs}",
        )
        note = notes.relocation_note(
            code,
            address,
            label,
            f"has here {listed}, printed in chapter {chapters_held.pop()}.",
        )
        verse = verses[address]
        changes.append((verse, len(verse.text), len(verse.text), [note]))
    return scripture.edited(doc, changes)


def with_edition_notes(
    code: str, doc: Document, tongue: citations.Dialect, ctx: Context, report: Report
) -> Document:
    """A book with the notes the edition wrote on it printed: each read as
    an authored note, cited, its declared lemma anchored where it stands,
    and set in the edition's form in its place."""
    policy = ctx.policy
    replacements: dict[str, Node] = {}
    for reference, verse in scripture.verses(doc).items():
        words = word_spans(verse.text)
        for offset, note in verse.notes:
            if note.get("category") != "edition":
                continue
            key = note["x-key"]
            body = notes.authored_body(note, None, key)
            cited = citations.scan(
                body.plain,
                tongue,
                verse_at(code, reference),
                key,
                ctx.inventory,
                policy=policy,
            )
            body = notes.bound(body, cited, key)
            report.read(tongue, key, cited, policy)
            read = notes.Read(
                key,
                "f",
                reference,
                verse,
                words,
                offset,
                body,
                tuple(cited),
                body.plain,
                body.plain,
                note.get("x-scope"),
                note["category"],
            )
            scope = present(read.scope, f"Edition note without its scope: {key}")
            span, glossed, rule = lemmas.declared(
                verse.text, words, offset, scope.get("declared"), key
            )
            replacements[key] = printed(read, span, glossed, rule, {}, ctx, report)
    if not replacements:
        return doc

    return scripture.map_notes(
        doc, lambda note: replacements.get(note.get("x-key", ""), note)
    )


def at_verse_starts(
    doc: Document, verses: Mapping[str, scripture.Verse], placed: Mapping[str, Content]
) -> Document:
    """The document with content set at the start of its verses, before the
    notes there, by each verse's reference."""
    blocks = list(doc["content"])
    for reference in sorted(placed, key=lambda r: verses[r].parts[0][:2], reverse=True):
        block, at, _, _ = verses[reference].parts[0]
        content = blocks[block]["content"]
        blocks[block] = {
            **blocks[block],
            "content": usj.joined(content[:at], placed[reference], content[at:]),
        }
    return usj.with_blocks(doc, blocks)


def check_notes(policy: bible.policy.Policy, reports: Iterable[Report]) -> None:
    """Every exception and declared change must have met its note."""
    keys = set().union(*(r.keys for r in reports))
    require_used(policy.brenton_notes["notes"], keys, "Brenton note exceptions")
    edited = Counter(key for r in reports for key in r.edited)
    declared = Counter(
        {key: len(changes) for key, changes in notes.note_prose(policy).items()}
    )
    require(
        edited == declared,
        f"Prose changes to notes not met once each: {sorted((declared - edited) + (edited - declared))}",
    )


def marked(text: str, offset: int, span: tuple[int, int] | None) -> str:
    """The verse for the review: ‸ where the note stands, and ** about the
    words it is about."""
    marks = {offset: "‸"}
    if span:
        start, end = span
        marks[start] = marks.get(start, "") + "**"
        marks[end] = "**" + marks.get(end, "")
    for at in sorted(marks, reverse=True):
        text = text[:at] + marks[at] + text[at:]
    return text


def scope_span(
    text: str,
    words: lemmas.Words,
    offset: int,
    note: Node,
    occurrence: int | None = None,
) -> tuple[int, int]:
    """The words a finished note is about, as offsets of its verse: its
    lemma, which occurs once (or at the named occurrence, where a deliberately
    narrow note stands), and the boundary stop its scope declares."""
    key = note.get("x-key")
    lemma = present(notes.lemma_of(note), f"Finished note without a lemma: {key}")
    tokens = words_of(lemma)
    hits = lemmas.occurrences(words, tokens)
    if occurrence is not None:
        require(
            0 < occurrence <= len(hits) and words[hits[occurrence - 1]][1] == offset,
            f"Finished narrow note lost its occurrence: {key}",
        )
        first = hits[occurrence - 1]
    else:
        require(len(hits) == 1, f"Finished note lemma is not unique: {key}")
        first = hits[0]
    start, end = words[first][1], words[first + len(tokens) - 1][2]
    stop = notes.boundary_stop(note.get("x-scope"))
    require(
        not stop or text[end : end + 1] == stop,
        f"Finished note boundary stop is missing: {key}",
    )
    require(
        scripture.plain(text[start:end]) == scripture.plain(lemma),
        f"Finished note lemma does not match its verse: {key}",
    )
    return start, end + len(stop)


def finished_rows(
    document: Document,
    rows: Sequence[NoteDerivation],
    exceptions: Mapping[str, NoteOverride] | None = None,
) -> list[NoteRow]:
    """The rows of the review, each note's verse, lemma, and text read from
    the finished book, with how annotation read it. A finished lemma must
    still identify one passage, with any boundary stop it declares."""
    by_key = {row["key"]: row for row in rows}
    found: dict[str, NoteRow] = {}
    for reference, verse in scripture.verses(document).items():
        # The verse's words, read once if a note of it has a lemma.
        words: lemmas.Words | None = None
        for offset, note in verse.notes:
            key = note.get("x-key")
            if key not in by_key:
                continue
            require(key not in found, f"Duplicate finished note: {key}")
            lemma = notes.lemma_of(note)
            span = None
            if lemma:
                words = word_spans(verse.text) if words is None else words
                decision = (exceptions or {}).get(key, {})
                occurrence = (
                    decision["occurrence"] if decision.get("widen") is False else None
                )
                span = scope_span(verse.text, words, offset, note, occurrence)
            # A marker takes the space after it, so a reading's field ends
            # with the space before the next words; the row gives it back.
            runs: list[tuple[str, str]] = []
            for n in note["content"]:
                if not isinstance(n, dict) or n.get("marker") in {"fr", "fq"}:
                    continue
                value = usj.text_of(n["content"])
                if n.get("marker") != "fqa":
                    for part in n["content"]:
                        if usj.is_type(part, "char", "it"):
                            runs.append(("quotation", usj.text_of(part["content"])))
                        else:
                            runs.append(("commentary", usj.text_of([part])))
                    continue
                kept = value.rstrip()
                runs.append(("reading", kept))
                if kept != value:
                    runs.append(("commentary", value[len(kept) :]))
            found[key] = {
                **by_key[key],
                "reference": reference,
                "verse": scripture.plain(marked(verse.text, offset, span)),
                "lemma": lemma,
                "note": notes.underscored(runs),
            }
    require(
        set(found) == set(by_key),
        f"Finished notes lost: {sorted(set(by_key) - set(found))}",
    )
    return [found[row["key"]] for row in rows]
