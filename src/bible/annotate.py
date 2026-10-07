"""The notes of the assembled books, set as the edition prints them: Brenton's
notes and cross-references and the 1611 margin as footnotes that name the
words they are about, the quotation links at their verses, and the
introductions to the books of the Apocrypha as footnotes on their openings.

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
from bible.checks import present, require
from bible.policy_schema import NoteOverride, WordingChange
from bible.references import verse_at
from bible.scripture import word_spans, words_of
from bible.usj import Content, Document, Node


class NoteRow(TypedDict):
    key: str
    reference: str
    rule: str
    verse: str
    lemma: str | None
    glossed: str | None
    reading: str | None
    note: str
    source: str
    style: str


@dataclass(frozen=True)
class Context:
    """What reading a note needs beside its book."""

    policy: bible.policy.Policy
    # What the edition prints, which a citation must name.
    inventory: scripture.Inventory
    books: bible.references.Books
    terms: bible.terminology.Registry
    # Each note's declared changes of wording, by its key.
    prose: Mapping[str, Sequence[WordingChange]]


@dataclass(frozen=True)
class Read:
    """A source note as read: where it stands and what it says."""

    key: str
    kind: str
    reference: str
    verse: scripture.Verse
    # The verse's words with their offsets, read once for every note in it.
    words: lemmas.Words
    offset: int
    body: notes.Body
    citations: tuple[citations.Citation, ...]
    source: str
    text: str
    scope: usj.Scope | None = None
    # The edition's own notes carry their category to the typesetter.
    category: str | None = None


@dataclass
class Report:
    """What a stage met while it worked, for the checks that span the
    edition and for the review."""

    # Each citation read, as (dialect, the source's name for the book).
    names: set[tuple[str, str | None]] = field(default_factory=set)
    # The keys of the citation decisions and prose changes that were met.
    decided: set[str] = field(default_factory=set)
    edited: list[str] = field(default_factory=list)
    # Every printed note's key, and one row of the review for each.
    keys: set[str] = field(default_factory=set)
    rows: list[NoteRow] = field(default_factory=list)
    # The keys of the source notes a decision leaves out.
    omitted: list[str] = field(default_factory=list)

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
    read: Read,
    span: lemmas.Span | None,
    glossed: lemmas.Span | None,
    rule: str,
    exception: NoteOverride,
    ctx: Context,
    report: Report,
) -> Node:
    """A note as the edition prints it, and its row of the review."""
    key, verse, words = read.key, read.verse, read.words
    body = notes.with_terms(read.body, ctx.terms)
    for edit in ctx.prose.get(key, ()):
        body = notes.edited(body, edit["from"], edit["to"], key)
        report.edited.append(key)
    lemma = lemmas.lemma_text(verse.text, words, span) if span else None
    runs, terms, original = notes.displayed(
        body, *lemmas.echoes(verse.text, words, span, glossed), books=ctx.books
    )
    runs = notes.finished(runs, terms, lemma, exception.get("sentence"), ctx.terms, key)
    report.keys.add(key)
    marks = {read.offset: "‸"}
    if span:
        first, last = words[span[0]][1], words[span[1]][2]
        marks[first] = marks.get(first, "") + "**"
        marks[last] = "**" + marks.get(last, "")
    shown = verse.text
    for at in sorted(marks, reverse=True):
        shown = shown[:at] + marks[at] + shown[at:]
    report.rows.append(
        dict(
            key=key,
            reference=read.reference,
            rule=rule,
            verse=scripture.plain(shown),
            lemma=lemma,
            # The words glossed, which a lemma widens until they occur once,
            # and the rendering that measured them.
            glossed=lemmas.lemma_text(verse.text, words, glossed) if glossed else None,
            reading=read.body.alternative,
            note=notes.underscored(runs),
            source=scripture.plain(read.source),
            style=body.rule,
        )
    )
    extra = usj.Extra({"x-key": key})
    if read.category:
        extra["category"] = read.category
    return notes.footnote(read.reference, lemma, runs, **extra)


def brenton(
    code: str,
    doc: Document,
    links: Sequence[crossrefs.Link],
    mended: frozenset[str],
    ctx: Context,
) -> tuple[Document, Report]:
    """A book of Brenton's with his notes and cross-references set as
    footnotes without callers, each naming its lemma. A cross-reference
    becomes a footnote of "See" and what it cites; those the quotation links
    replace are left out."""
    policy, report = ctx.policy, Report()
    tongue = citations.dialect("brenton", policy=policy)
    exceptions = policy.brenton_notes["notes"]
    found = []
    verses = scripture.verses(doc)
    for source_reference, source_verse in verses.items():
        for offset, note in source_verse.notes:
            key = note["x-key"]
            exception = exceptions.get(key, {})
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
                Read(
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
    # would go unused unnoticed.
    excepted = sorted(merged & set(exceptions))
    require(
        not excepted, f"Brenton note exception for a note a link replaces: {excepted}"
    )
    corrected = sorted(k for k in merged if k.partition(" ")[2] in mended)
    require(not corrected, f"Brenton correction to a note a link replaces: {corrected}")
    replacements: dict[str, Node | None] = {}
    moved: list[tuple[str, int, Node]] = []
    for read in found:
        if read.key in merged:
            replacements[read.key] = None
            continue
        key, verse, words = read.key, read.verse, read.words
        exception = exceptions.get(key, {})
        if "verse" in exception or exception.get("widen") is False:
            # A moved or deliberately narrow note stands at its named words.
            require(
                read.scope is None,
                f"Alexandrine lemma also has a Brenton exception: {key}",
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
            assert glossed is not None
            at = words[glossed[0]][1]
            read = replace(read, offset=at)
            note = printed(read, span, glossed, rule, exception, ctx, report)
            replacements[key] = None
            moved.append((read.reference, at, note))
            continue
        if read.scope is None:
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
        replacements[key] = printed(read, span, glossed, rule, exception, ctx, report)

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
            doc, [(verses[reference], at, at, [note]) for reference, at, note in moved]
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
    code: str, doc: Document, listed: Sequence[Mapping[str, str]], ctx: Context
) -> tuple[Document, Report]:
    """A book of the Cambridge text with the 1611 marginal notes set on it as
    footnotes without callers.

    Each note is anchored at George's lemma, or at the Cambridge words recorded
    for it in edition/kjv-notes.json where the spelling differs, the lemma
    occurs more than once, or the reference is wrong. The note names the words
    it is anchored at, widened until they occur only once in the verse, and
    its renderings take in the same words.
    """
    policy, report = ctx.policy, Report()
    tongue = citations.dialect("george", policy=policy)
    # The notes the edition wrote on the words it changed stand in the book
    # already: they are printed first, and the 1611 notes set among them.
    doc = with_edition_notes(code, doc, tongue, ctx, report)
    verses = scripture.verses(doc)
    changes: list[tuple[scripture.Verse, int, int, Content]] = []
    for note in listed:
        key = note["key"]
        override = policy.kjv_notes["notes"].get(key, {})
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
        if "anchor" in override:
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
        pieces = notes.labelled_pieces(note["note"])
        cited = citations.scan(
            note["note"],
            tongue,
            verse_at(code, reference),
            key,
            ctx.inventory,
            policy=policy,
        )
        report.read(tongue, key, cited, policy)
        read = Read(
            key,
            "f",
            reference,
            verse,
            words,
            words[first][1],
            notes.source_body(
                pieces,
                cited,
                override.get("note"),
                key,
                note["note"],
                quotation=override.get("quotation", False),
            ),
            tuple(cited),
            note["note"],
            note["note"],
        )
        footnote = printed(read, span, glossed, rule, override, ctx, report)
        changes.append((verse, read.offset, read.offset, [footnote]))
    return scripture.edited(doc, changes), report


def spanned(verses: Sequence[bible.references.Verse]) -> str:
    """A run of one chapter's verses as a note names it: "30:1–14", or, in
    lettered verses, "24:22f–t"."""
    first, last = verses[0], verses[-1]
    if first == last:
        return first.label
    if first.number == last.number:
        return f"{first.label}\u2013{last.letter}"
    return f"{first.label}\u2013{last.number}{last.letter}"


def relocation_note(code: str, address: str, label: str, sentence: str) -> Node:
    """A note the edition sets at a verse to say where a passage stands in
    another order: labelled with the text whose order it is, as the notes
    on the New Testament's moved verses are labelled TR, and saying what
    that text has there."""
    extra: usj.Extra = {
        "x-key": f"{code} {address} {label}",
        "category": "edition",
        "x-scope": {"declared": None},
    }
    return usj.note(
        "f",
        usj.char("fr", f"{address} "),
        usj.char("fl", f"{label} "),
        usj.char("ft", sentence),
        caller="+",
        **extra,
    )


def with_relocation_notes(
    code: str, doc: Document, kjv: Mapping[str, Document], ctx: Context
) -> Document:
    """A book with notes where a passage stands in another order than the
    Hebrew's, which the King James Bible follows (edition/versification.json,
    relocations), as the New Testament's are noted where they stand in
    another order than the Received Text's: at the passage's first verse,
    where the Hebrew has it; and at the verse after which the Hebrew has it,
    which passages are printed elsewhere. Each decision is held to the runs
    the place stage worked out: the Hebrew passage's verses must stand here,
    beginning at the verse it names."""
    policy = ctx.policy
    label = ctx.terms.display("hebrew")
    found: list[tuple[bible.references.Passage, list[bible.references.Verse]]] = []
    for reference, entry in policy.versification.get("relocations", {}).items():
        if isinstance(entry, str) or reference.split()[0] != code:
            continue
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
        found.append((theirs, held))
    if not found:
        return doc
    verses = scripture.verses(doc)
    changes: list[tuple[scripture.Verse, int, int, Content]] = []
    for theirs, held in found:
        where = spanned(list(theirs.verses))
        note = relocation_note(
            code, held[0].label, label, f"has this passage at {where}."
        )
        changes.append((verses[held[0].label], 0, 0, [note]))
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
        printed = [spanned(held)]
        end = theirs.last
        while True:
            after = bible.references.Verse(end.book, end.chapter, end.number + 1)
            if str(after.number) not in chapters.get(str(end.chapter), []):
                after = bible.references.Verse(end.book, end.chapter + 1, 1)
            if after not in starts:
                break
            following = starts[after]
            printed.append(spanned(ends[following.last]))
            end = following.last
        listed = (
            printed[0]
            if len(printed) == 1
            else ", ".join(printed[:-1]) + " and " + printed[-1]
        )
        anchor = versification.from_kjv(before, policy=policy)
        require(bool(anchor), f"Relocated passage follows no verse here: {theirs}")
        address = anchor[-1].label
        note = relocation_note(
            code, address, label, f"has here the verses printed at {listed}."
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
            read = Read(
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

    def change(item: Node) -> Node | Content | None:
        if item["type"] == "note" and item.get("x-key") in replacements:
            return replacements[item["x-key"]]
        return item

    return usj.with_content(doc, lambda content: usj.mapped(content, change))


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
    unused = sorted(set(policy.brenton_notes["notes"]) - keys)
    require(not unused, f"Unused Brenton note exceptions: {unused}")
    edited = Counter(key for r in reports for key in r.edited)
    declared = Counter(
        change["note"]
        for group in policy.prose.values()
        for change in group["changes"]
        if "note" in change
    )
    require(
        edited == declared,
        f"Prose changes to notes not met once each: {sorted((declared - edited) + (edited - declared))}",
    )
