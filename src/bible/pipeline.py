"""The edition, prepared: every stage in the order its inputs allow.

    read        the pinned sources, their transcription corrected, as USJ
    promote     the Alexandrine and Byzantine readings in their source texts
    assemble    the edition's books from the sources' chapters
    place       where each verse stands in the King James Bible
    line        Old Testament poetry, retaining Scrivener's New Testament
    matter      the translations' front and back matter
    annotate    notes, quotation links and the notes of Brenton's Appendix
    revise      the translations' spelling and punctuation
    authored    the edition's own pages, quoting the revised translations,
                and the textual variants for the website
    view        the full edition, or the sample's chapters, with typography
    export      USFM for PTXprint

Each stage is a function of the stages before it and of the policy. Nothing
is read after the first, and no document is changed in place. Revision finishes
the translations after source-dependent decisions; authored pages consume that
text and receive their own punctuation finishing pass.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

import bible.policy
import bible.references
import bible.sources
from bible import (
    alexandrinus,
    annotate,
    assembly,
    byzantine,
    ccel,
    crossrefs,
    lines,
    matter,
    numbering,
    places,
    psalter,
    quotations,
    renderings,
    repairs,
    revision,
    scripture,
    terminology,
    tvtms,
    typography,
    usfm,
    usj,
    versification,
)
from bible.byzantine import stages, variants
from bible.checks import present, require, require_used
from bible.policy import source_id
from bible.usj import Content, Document, Node

type MetValue = str | tuple[str | None, ...]
type Met = Mapping[str, frozenset[MetValue]]


EXPECTED_NT_MARGINAL_NOTES = 775


@dataclass(frozen=True)
class Read:
    """The sources as documents: Brenton's files and the King James Bible's
    by their codes, the notes that corrections mend, George's listing of
    the 1611 margin by book, the parsed versification table, and the report
    of the notes CCEL's transcription supplied."""

    brenton: MappingProxyType[str, Document]
    kjv: MappingProxyType[str, Document]
    # The Updated Brenton, read for the division of its poetry into lines.
    updated_brenton: MappingProxyType[str, Document]
    mended: MappingProxyType[str, frozenset[str]]
    marginal: MappingProxyType[str, tuple[Mapping[str, str], ...]]
    versification: tuple[tvtms.Row, ...]
    # What came of CCEL's notes: how many were set in Brenton's verses, and
    # which were held back or left out, and why.
    ccel: ccel.Report
    # The King James Bible's books under its names, and every book's
    # chapters, for the table of chapters and verses: read from the files'
    # text, since only the books the edition needs are parsed.
    kjv_books: bible.references.Books
    kjv_chapters: MappingProxyType[str, Mapping[str, Sequence[str]]]
    # The editor's own pages, filled in and parsed by the authored stage.
    authored: MappingProxyType[str, str]
    # The New Testament's Greek texts and witnesses, for the reconciliation.
    byzantine: MappingProxyType[str, bible.sources.Content]
    # Boyd's Gospel colophons, by book, which the matter stage appends.
    colophons: MappingProxyType[str, Node]


# Words Brenton brackets within a run of text.
SUPPLIED = re.compile(r"\[([^\[\]]+)\]")


def note_key(code: str, reference: str, number: int) -> str:
    """A Brenton note's key: its verse, then after its verse's first note, its
    number there."""
    return f"{code} {reference}" + (f"#{number}" if number > 1 else "")


def note_origin(note: Node) -> str:
    """The verse a note names as its own, in its first part."""
    return usj.text_of(note["content"][:1]).strip()


def keyed(code: str, doc: Document) -> Document:
    """A source book with each note keyed by its source verse."""
    seen: dict[str, int] = {}
    verses = scripture.verses(doc)
    noted: list[tuple[Node, str]] = []
    for reference, verse in verses.items():
        for _, note in verse.notes:
            origin = note_origin(note)
            require(
                origin == reference,
                f"Note reference disagrees with its verse: {code} {origin}",
            )
            seen[reference] = seen.get(reference, 0) + 1
            noted.append((note, note_key(code, reference, seen[reference])))
    if not noted:
        return doc
    return usj.replaced_by_identity(
        doc, {id(note): {**note, "x-key": key} for note, key in noted}
    )


def bracketed(code: str, doc: Document, policy: bible.policy.Policy) -> Document:
    """A source book with the words Brenton brackets in a book the Hebrew
    lacks read as supplied: English with no Greek behind it, which the
    Authorized Version prints in italics in the books it has, as the
    translators' other supplied words are. In a book the Hebrew has, his
    brackets mark the Greek it lacks, a passage that may run on over verses
    and chapters, and revision drops them. Both by the one rule of
    revisions.json, which leaves them all in print without it."""
    if (
        revision.BRACKETS not in policy.revisions["punctuation"]
        or code in policy.versification["old_testament"]
        or not any(usj.is_type(block, "chapter") for block in doc["content"])
    ):
        return doc
    found = False

    def supplied(content: Content) -> Content:
        nonlocal found
        result: Content = []
        for item in content:
            parts = SUPPLIED.split(item) if isinstance(item, str) else [item]
            found = found or len(parts) > 1
            for n, part in enumerate(parts):
                usj.extended(result, [usj.char("add", part) if n % 2 else part])
        return result

    result = usj.with_content(doc, supplied)
    for block in result["content"]:
        text = usj.text_of(block.get("content", ()))
        at = next((n for n, mark in enumerate(text) if mark in "[]"), -1)
        require(
            at < 0,
            f"Bracket around more than a run of words in {code}: "
            f"{text[max(0, at - 30) : at + 30]}",
        )
    return result if found else doc


def marginal_notes(
    text: str, policy: bible.policy.Policy
) -> MappingProxyType[str, tuple[Mapping[str, str], ...]]:
    """The 1611 translators' New Testament marginal notes, by book, in source
    order, with their corrections.

    George's listing gives a reference, the words the note glosses (the
    lemma), and the note. The Old Testament entries belong to the Hebrew Old
    Testament, which this edition does not print, so they are never read.
    """
    require(
        text.count("\nMatthew 1:11 ") == 1,
        "Marginal notes New Testament boundary changed",
    )
    books = policy.citations["dialects"]["george"]["entries"]
    entry_pattern = re.compile(
        "(" + "|".join(map(re.escape, books)) + r") (\d+):(\d+) (.+?): (.+)"
    )
    corrections = dict(policy.kjv_notes["corrections"])
    result: dict[str, list[Mapping[str, str]]] = {}
    seen: dict[str, int] = {}
    for paragraph in re.split(r"\n\s*\n", text[text.index("\nMatthew 1:11 ") :]):
        # The Markdown wraps long entries; a continuation line joins its entry.
        entry = scripture.plain(paragraph)
        if not entry:
            continue
        match = present(
            entry_pattern.fullmatch(entry), f"Unparsed marginal note: {entry}"
        )
        book, chapter, verse, lemma, note = match.groups()
        code = books[book]
        key = f"{code} {chapter}:{verse} {lemma}"
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            key += f"#{seen[key]}"
        if key in corrections:
            note = repairs.corrected(
                note, corrections.pop(key), "Marginal note correction", key
            )
        require(
            "[" not in note and "]" not in note,
            f"Transcriber's remark left in marginal note: {key}",
        )
        result.setdefault(code, []).append(
            MappingProxyType(
                dict(key=key, reference=f"{chapter}:{verse}", lemma=lemma, note=note)
            )
        )
    require(not corrections, f"Unused marginal note corrections: {sorted(corrections)}")
    keys = {n["key"] for listed in result.values() for n in listed}
    require_used(policy.kjv_notes["notes"], keys, "marginal note exceptions")
    require(
        len(keys) == EXPECTED_NT_MARGINAL_NOTES,
        f"Expected {EXPECTED_NT_MARGINAL_NOTES} New Testament marginal notes, found {len(keys)}",
    )
    units = {u["id"] for u in policy.scripture if u["source"] == "kjv"}
    require(
        set(result) <= units, "Marginal notes name a book outside the KJV New Testament"
    )
    return MappingProxyType({code: tuple(listed) for code, listed in result.items()})


def read(sources: bible.sources.Sources, policy: bible.policy.Policy) -> Read:
    """Parse the sources once, with the corrections to their transcription."""
    corrections = policy.brenton_notes["corrections"]
    printed = {
        code
        for e in (*policy.entries, *policy.unprinted)
        if e.get("source") == "brenton"
        for code in assembly.source_codes(e)
    }
    unprinted = sorted({bible.references.book_of(k) for k in corrections} - printed)
    require(
        not unprinted,
        f"Brenton corrections name a source the edition doesn't read: {unprinted}",
    )
    # Every source file is taken by an entry or excluded, and an exclusion
    # names a file that exists and that no entry takes. An excluded file is
    # still parsed with the rest; the edition takes nothing from it.
    excluded = set(policy.manifest["excluded"]["brenton"])
    stale = sorted((excluded - set(sources.brenton)) | (excluded & printed))
    require(not stale, f"Excluded Brenton sources missing or read: {stale}")
    unread = sorted(set(sources.brenton) - printed - excluded)
    require(not unread, f"Brenton sources neither read nor excluded: {unread}")
    brenton, mended = {}, {}
    for code, text in sources.brenton.items():
        text, mended[code] = repairs.brenton(code, text, corrections)
        brenton[code] = keyed(code, bracketed(code, usj.parse(text), policy))
    # Of the King James Bible, only what the edition prints or borrows, and
    # the Old Testament, in which its own is placed.
    wanted = (
        {source_id(e) for e in policy.entries if e.get("source") == "kjv"}
        | {
            bible.references.book_of(key)
            for key, e in policy.alexandrinus["passages"].items()
            if "kjv" in e
        }
        | set(versification.kjv_books(policy=policy))
    )
    kjv = {
        code: assembly.colophon(usj.parse(sources.kjv[code])) for code in sorted(wanted)
    }
    for unit in policy.scripture:
        if unit["source"] == "kjv":
            require(
                not usj.notes_of(kjv[unit["id"]]["content"]),
                f"Cambridge text already has footnotes: {unit['id']}",
            )
    # The notes eBible's transcription lacks, from CCEL's, set in its verses
    # after its own notes are keyed, so that their keys never shift.
    supplemented, ccel_report = ccel.supplemented(brenton, sources.ccel, policy)
    # Its books have chapters; its prefaces have none.
    facing = {
        code: chapters
        for code, text in sources.kjv.items()
        if (chapters := usfm.inventory(text)["chapters"])
    }
    return Read(
        brenton=supplemented,
        kjv=MappingProxyType(kjv),
        updated_brenton=MappingProxyType(
            {code: usj.parse(text) for code, text in sources.updated_brenton.items()}
        ),
        mended=MappingProxyType(mended),
        marginal=marginal_notes(sources.marginal, policy),
        versification=tvtms.rows(sources.versification)[0],
        ccel=ccel_report,
        kjv_books=assembly.kjv_books(policy, sources.kjv),
        kjv_chapters=MappingProxyType(facing),
        authored=sources.authored,
        byzantine=sources.byzantine,
        colophons=matter.read_colophons(sources.byzantine, policy),
    )


@dataclass(frozen=True)
class Promoted:
    """The sources with the edition's readings in them: Brenton's books with
    the Alexandrine decisions carried out, and the King James books conformed
    to the Byzantine text, with what the reconciliation worked out."""

    brenton: MappingProxyType[str, Document]
    kjv: MappingProxyType[str, Document]
    alexandrine: tuple[int, int]
    byzantine: stages.Reconciliation
    # What came of CCEL's notes, with those set in the verses the promotion
    # supplied.
    ccel: ccel.Report


def promote(sources: Read, policy: bible.policy.Policy) -> Promoted:
    """Brenton's books with the Alexandrine decisions carried out, and the
    King James books with the Byzantine readings in them: in each, the
    chosen text goes into the verse and the displaced reading becomes a
    note that names its witness."""
    unused = sorted(
        key
        for key in policy.brenton_notes.get("renderings", {})
        if bible.references.book_of(key) not in sources.brenton
        or bible.references.book_of(key) == alexandrinus.APPENDIX
    )
    require(not unused, f"Unused Brenton renderings: {unused}")
    counts = alexandrinus.check(policy, sources.brenton)
    terms = terminology.registry(policy)
    found = byzantine.reconciled(
        sources.byzantine,
        {code: sources.kjv[code] for code in byzantine.BOOKS},
        bible.policy.thaw(policy.byzantine),
        bible.policy.thaw(policy.byzantine_placements),
    )
    brenton = {
        code: renderings.brenton(
            code,
            alexandrinus.promoted(code, doc, policy, sources.kjv, sources.brenton),
            policy.brenton_notes.get("renderings", {}),
        )
        for code, doc in sources.brenton.items()
        if code != alexandrinus.APPENDIX
    }
    # The CCEL notes on words the promotion supplies, which waited for them.
    supplied, report = ccel.supplied(brenton, sources.ccel, policy)
    return Promoted(
        supplied,
        MappingProxyType(
            {
                code: (
                    byzantine.promoted(code, found, terms)
                    if code in byzantine.BOOKS
                    else doc
                )
                for code, doc in sources.kjv.items()
            }
        ),
        counts,
        found,
        report,
    )


def lined(
    units: Mapping[str, Document],
    read_sources: Read,
    policy: bible.policy.Policy,
) -> MappingProxyType[str, Document]:
    """Brenton's poems set in the update's lines where Scrivener sets the
    verse as verse too or has no say, with their pauses, descriptive titles
    and acrostic headings. Each chapter's prose opens a new paragraph in
    both testaments. After the verses are placed, through which the witnesses
    are read."""
    lines.check(policy)
    old_testament = {
        code: doc for code, doc in units.items() if code not in policy.kjv_units
    }
    unknown = sorted(
        key
        for key in (
            set(policy.lines["breaks"])
            | set(policy.lines.get("prose", {}))
            | set(policy.lines.get("unspaced", {}))
        )
        if key[:3] not in old_testament
    )
    require(
        not unknown,
        f"Line decisions in no Old Testament book the edition prints: {unknown}",
    )
    # The update numbers its verses as eBible does.
    update = {
        code: assembly.renumbered(code, doc, policy, words=False)
        for code, doc in read_sources.updated_brenton.items()
    }
    brenton = lines.old_testament(
        old_testament,
        update,
        policy,
        lines.scrivener(read_sources.kjv, policy),
    )
    # Chapters open their paragraphs first, so that a paragraph decision at a
    # chapter's opening is checked against, and departs from, that rule.
    brenton = lines.paragraphs(
        {code: lines.opened(doc) for code, doc in brenton.items()}, policy
    )
    for doc in brenton.values():
        lines.unspaced(doc, policy.lines.get("unspaced", {}))
    require("PSA" in brenton, "Psalter decisions without the Psalms")
    require("LAM" in brenton, "Acrostic names without Lamentations")
    brenton = {
        code: lines.descriptive_titles(lines.pauses(doc))
        for code, doc in brenton.items()
    }
    brenton["LAM"] = lines.acrostics(brenton["LAM"], lines.within_verse(policy))
    brenton["PSA"] = psalter.divided(brenton["PSA"], policy.psalter)
    return MappingProxyType(
        {
            code: brenton[code] if code in brenton else lines.opened(doc)
            for code, doc in units.items()
        }
    )


def assemble(
    promoted: Promoted, policy: bible.policy.Policy, read_sources: Read
) -> MappingProxyType[str, Document]:
    """The edition's books under their names, and what they print."""
    assembly.check_divided(
        policy, {"brenton": read_sources.brenton, "kjv": read_sources.kjv}
    )
    units = {
        unit["id"]: matter.structured(
            unit["id"],
            assembly.named(
                unit,
                assembly.scripture_unit(unit, promoted.brenton, promoted.kjv, policy),
            ),
            policy,
            standalone=False,
        )
        for unit in policy.scripture
    }
    # A numbering decision is carried out book by book, so one that names no
    # book the edition prints would match nothing unnoticed.
    numbered = {
        *versification.renumberings(policy=policy),
        *(
            bible.references.book_of(reference)
            for reference in policy.versification.get("unnumbered", {})
            if reference != "why"
        ),
        *(
            bible.references.parse_verse(entry["to"]).book
            for entry in policy.versification.get("relocations", {}).values()
            if not isinstance(entry, str)
        ),
    }
    unknown = sorted(numbered - set(units))
    require(
        not unknown, f"Numbering decisions in no book the edition prints: {unknown}"
    )
    return MappingProxyType(units)


def placed(
    units: Mapping[str, Document],
    read_sources: Read,
    policy: bible.policy.Policy,
) -> bible.policy.Policy:
    """The policy with every verse's place in the King James Bible, which the
    notes, the links and the table of chapters and verses then read: the Old
    Testament's worked out from the table and the words, the New Testament's
    from the verses the Byzantine text lacks or places elsewhere."""
    runs = places.placed(
        units, read_sources.kjv, read_sources.versification, policy=policy
    )
    runs.update(versification.byzantine_runs(policy.byzantine["structure"]))
    return policy.replace(versification={**policy.versification, "kjv": runs})


def quotation_links(ctx: annotate.Context) -> dict[str, list[crossrefs.Link]]:
    """The reviewed quotation links, by book, each side in the edition."""
    policy = ctx.policy
    relations = crossrefs.quotation_relations(
        quotations.reviewed_rows(policy=policy), policy=policy
    )
    for relation in relations:
        for passage in (*relation.nt, *relation.ot):
            for verse in passage.verses:
                require(
                    scripture.has_verse(ctx.inventory, verse),
                    f"Quotation verse missing from assembled edition: {relation.id}: {verse}",
                )
            versification.require_own_labels(
                passage.verses, f"Quotation {relation.id}", policy=policy
            )
    return crossrefs.planned_links(relations, ctx.books, policy=policy)


def context(
    units: Mapping[str, Document], policy: bible.policy.Policy
) -> annotate.Context:
    """What reading a note needs: the policy, what the edition prints, and
    its books under the names the assembled units carry."""
    return annotate.Context(
        policy,
        {code: usj.inventory(doc) for code, doc in units.items()},
        assembly.books(policy, units),
    )


def front_and_back(read_sources: Read, ctx: annotate.Context) -> tuple[
    dict[str, Document],
    dict[str, list[Content]],
    annotate.Report,
]:
    """The translations' front and back matter, with Brenton's list of
    abbreviations, which the introduction tables, and the notes of
    Brenton's Appendix, which is read for them and printed nowhere, by the
    verse each goes to."""
    policy, report = ctx.policy, annotate.Report()
    docs, appendix_notes = {}, {}
    for entry in (*policy.entries, *policy.unprinted):
        if "file" in entry or "section" in entry:
            continue
        family, code = entry["source"], source_id(entry)
        source = (
            read_sources.brenton[code]
            if family == "brenton"
            else read_sources.kjv[code]
        )
        # Of the Appendix, the notes alone: the books print its passages.
        appendix = entry["id"] == policy.appendix["source"]
        doc = alexandrinus.appendix_notes(source) if appendix else source
        doc, moved = matter.unit(entry, doc, ctx, report)
        if appendix:
            appendix_notes.update(moved)
        else:
            docs[entry["id"]] = doc
    front = {
        source_id(e)
        for e in policy.entries
        if "section" not in e and e.get("source") == "brenton"
    }
    # The Appendix's notes print at their verses, and the list of
    # abbreviations in the introduction, so printed as well either
    # would print twice.
    twice = sorted(front & {source_id(e) for e in policy.unprinted})
    require(not twice, f"Brenton sources printed as well as sent: {twice}")
    return docs, appendix_notes, report


def linked(
    code: str,
    doc: Document,
    appendix_notes: Mapping[str, Sequence[Content]],
    links: Sequence[crossrefs.Link],
    ctx: annotate.Context,
) -> Document:
    """A book with its quotation links, each at the start of its verse, and
    the notes of Brenton's Appendix, each at the words its decision names."""
    policy = ctx.policy
    verses = scripture.verses(doc)
    placed: dict[str, Content] = {}
    require(
        all(link.origin.book == code for link in links),
        f"Links for another book passed to {code}",
    )
    cited = {v.label for link in links for v in link.passage.verses}
    require(
        cited <= set(verses), f"Quotation verse missing from prepared scripture: {code}"
    )
    for reference, notes in crossrefs.link_notes(links, ctx.books, ctx.terms).items():
        placed.setdefault(reference, []).extend(notes)
    if placed:
        doc = annotate.at_verse_starts(doc, verses, placed)
        verses = scripture.verses(doc)
    # At the words the decision names, found once, or at the verse's start or
    # end, after the notes already there.
    sent = {
        key: paragraphs
        for key, paragraphs in appendix_notes.items()
        if key.startswith(f"{code} ")
    }
    if not sent:
        return doc
    anchored: list[tuple[scripture.Verse, int, int, Content]] = []
    for key, paragraphs in sent.items():
        reference = key.removeprefix(f"{code} ")
        require(reference in verses, f"Appendix note verse missing: {key}")
        note = matter.appendix_note(paragraphs, key + matter.APPENDIX)
        decision, verse = policy.appendix["notes"][key], verses[reference]
        if "before" in decision:
            at = alexandrinus.anchor(verse, decision["before"], key)
        else:
            at = 0 if decision["at"] == "start" else len(verse.text)
        anchored.append((verse, at, at, [note]))
    return scripture.edited(doc, anchored)


def annotated(
    units: Mapping[str, Document],
    read_sources: Read,
    appendix_notes: Mapping[str, Sequence[Content]],
    ctx: annotate.Context,
) -> tuple[dict[str, Document], dict[str, annotate.Report]]:
    """The books with their notes and quotation links."""
    policy = ctx.policy
    links = quotation_links(ctx)
    docs, reports = {}, {}
    for unit in policy.scripture:
        code = unit["id"]
        if unit["source"] == "kjv":
            doc, report = annotate.george(
                code,
                units[code],
                read_sources.marginal.get(code, ()),
                ctx,
                original=read_sources.kjv[code],
            )
        else:
            mended = frozenset[str]().union(
                *(read_sources.mended[c] for c in assembly.source_codes(unit))
            )
            doc, report = annotate.brenton(
                code,
                annotate.with_relocation_notes(
                    code, units[code], read_sources.kjv, ctx
                ),
                links.get(code, ()),
                mended,
                ctx,
            )
        docs[code] = linked(code, doc, appendix_notes, links.get(code, ()), ctx)
        reports[code] = report
    annotate.check_notes(policy, reports.values())
    return docs, reports


@dataclass(frozen=True)
class Revised:
    """The translations revised: every unit of front matter and every book
    as it prints; the books as their names alone were respelled, which the
    kept-name check and the textual variants read; and the revisions
    met, which the authored pages' own finishing pass adds to."""

    finished: MappingProxyType[str, Document]
    named: MappingProxyType[str, Document]
    met: revision.MetRevisions


def finished_book(
    code: str, doc: Document, policy: bible.policy.Policy, met: revision.MetRevisions
) -> tuple[Document, Document]:
    """A book as revised, and as its names alone were respelled: the names
    come first, then the declared changes to its verses and notes, then the
    source's brackets and the small capitals of selective emphasis go, then
    the systematic spelling and punctuation; a kept name must survive them.
    The ligatures are written out last, once every decision written in the
    source's letters has been carried out and checked."""
    named = revision.named(
        code, revision.named_colophon(code, doc, policy, met), policy, met
    )
    doc = revision.revised(code, named, policy, met)
    doc = revision.passages(code, doc, policy, met)
    doc = typography.small_caps(revision.unbracketed(doc, policy, met))
    doc = revision.punctuated(revision.respelled(doc, policy, met), policy, met)
    revision.check_kept(code, named, doc, policy)
    return revision.unligatured(doc, policy, met), named


def finished_matter(
    code: str, doc: Document, policy: bible.policy.Policy, met: revision.MetRevisions
) -> Document:
    """A unit of front or back matter as revised: its names respelled where
    their decisions list the unit, then without the small capitals of
    selective emphasis, its declared passages, then the systematic spelling
    and punctuation, and its ligatures written out."""
    doc = revision.named_matter(code, doc, policy, met)
    doc = revision.passages(code, typography.small_caps(doc), policy, met)
    doc = revision.punctuated(
        revision.respelled(doc, policy, met, book=False), policy, met
    )
    return revision.unligatured(doc, policy, met)


def revise(
    front: Mapping[str, Document],
    books: Mapping[str, Document],
    policy: bible.policy.Policy,
) -> Revised:
    """The translations' spelling and punctuation revised, and the small
    capitals of selective emphasis gone, after the source-dependent
    decisions and before the edition's own pages, which quote the books as
    they print."""
    met: revision.MetRevisions = set()
    finished = {
        code: finished_matter(code, doc, policy, met) for code, doc in front.items()
    }
    named = {}
    for code, doc in books.items():
        finished[code], named[code] = finished_book(code, doc, policy, met)
    return Revised(MappingProxyType(finished), MappingProxyType(named), met)


# An entry of the textual variants: its verse's row and its lanes, as the
# website publishes them.
Entry = tuple[variants.Row, list[variants.Lane]]


def authored(
    ctx: annotate.Context,
    read_sources: Read,
    revised: Revised,
    found: stages.Reconciliation,
    glossary: Node,
) -> tuple[dict[str, Document], Document, Document, tuple[Entry, ...]]:
    """The edition's own pages, with the passages and tables they ask for,
    among them the list of abbreviations, Brenton's as revised: the pages
    the book prints, by id; the numbering and textual variants pages, which
    the website publishes; and the variants’ entries, each its row and its
    lanes, for the website to publish by its verse."""
    policy = ctx.policy
    # The variants quote the King James books before the readings and the
    # New Testament after them with the same systematic spelling and
    # punctuation, before the verse-specific revisions, so that it shows the
    # readings' differences alone. The names are the edition's verses' and
    # are not applied to the King James books, so a respelled name shows in
    # the variants beside the reading it stands near.
    rows = variants.rows(
        found,
        {
            code: revision.regularized(doc, policy)
            for code, doc in found.english.documents.items()
        },
        {
            code: revision.regularized(doc, policy)
            for code, doc in revised.named.items()
            if code in policy.kjv_units
        },
    )
    entries = tuple((row, variants.lanes(row, ctx.terms)) for row in rows)
    pages = {}
    for entry in (*policy.entries, bible.policy.NUMBERING, bible.policy.VARIANTS):
        if "file" not in entry:
            continue
        text = read_sources.authored[entry["file"]]
        require(
            text.startswith(f"\\id {source_id(entry)}\n"),
            f"Wrong id in {entry['file']}",
        )
        pages[entry["id"]] = numbering.page(
            text,
            ctx.inventory,
            read_sources.kjv_chapters,
            ctx.books,
            read_sources.kjv_books,
            glossary=glossary,
            policy=policy,
        )
    # These pages discuss source names, so retain their spelling. Finish
    # punctuation after their passages and tables have been filled in, and
    # write out the ligatures, as everywhere the edition prints.
    docs = {
        code: revision.unligatured(
            revision.punctuated(doc, policy, revised.met), policy, revised.met
        )
        for code, doc in pages.items()
    }
    variants_page = docs.pop(bible.policy.VARIANTS["id"])
    numbering_page = docs.pop(bible.policy.NUMBERING["id"])
    return docs, numbering_page, variants_page, entries


@dataclass(frozen=True)
class Edition:
    """The whole edition, prepared: every unit by its id, in the order it
    prints, before the typography and the selection that a view makes."""

    # The decisions, with the places of the verses that the build works out.
    policy: bible.policy.Policy
    # The sources as read, which the review and the website quote.
    read: Read
    documents: MappingProxyType[str, Document]
    # Which units are books of scripture, and which are the edition's own pages.
    scripture: frozenset[str]
    authored: frozenset[str]
    # Every unit's contents title, running-head title and abbreviation, and
    # the books of scripture under the names citations print.
    names: MappingProxyType[str, Mapping[str, str]]
    books: bible.references.Books
    inventory: MappingProxyType[str, Mapping[str, Sequence[str]]]
    # A row of the review for every note, by book, and a summary of the sources.
    notes: MappingProxyType[str, tuple[annotate.NoteRow, ...]]
    summary: MappingProxyType[str, int]
    # What reading the sources met: the citation decisions, each dialect's
    # names for books, and the revisions of spelling and punctuation.
    met: Met
    # What the reconciliation of the New Testament with the Byzantine text
    # worked out, for the review and the textual variants.
    byzantine: stages.Reconciliation
    # The website-only numbering and textual variants pages, the variants
    # entries, and Brenton's list of abbreviations completed from the
    # registry, which the introduction tables.
    numbering_page: Document
    variants_page: Document
    variants: tuple[Entry, ...]
    glossary: Node
    # What came of CCEL's notes, with those set in the verses promotion
    # supplied.
    ccel: ccel.Report


def check_met(policy: bible.policy.Policy, met: Met) -> None:
    """Every citation decision, every name a dialect has for a book, and
    every revision must have been met: one that nothing meets would
    go stale unnoticed."""
    require_used(policy.citations["decisions"], met["decisions"], "citation decisions")
    names = sorted(
        (name, book)
        for name, tongue in policy.citations["dialects"].items()
        for book in tongue["books"]
        if (name, book) not in met["names"]
    )
    require(not names, f"Unused names for books: {names}")
    revision.check_met(policy, met["revisions"])


def check_document(
    code: str, doc: Document, *, scripture_unit: bool, authored_page: bool
) -> None:
    """What every prepared document must hold to."""
    if scripture_unit:
        # A note in the margin has no caller: any caller, "*" as well as "+",
        # would stand in the text. A note at the foot of the page has its
        # caller, and only that.
        require(
            all(
                note["caller"] == ("+" if matter.is_appendix(note) else "-")
                for note in usj.notes_of(doc["content"])
            ),
            f"Note with a caller left in the text, or a footnote without one: {code}",
        )
        for reference, verse in scripture.verses(doc).items():
            for _, note in verse.notes:
                # Only the Appendix's notes name no verse; a note moved
                # below the text still names its own.
                named = bool(note["content"]) and usj.is_origin(note["content"][0])
                origin = note_origin(note)
                require(
                    (matter.is_appendix(note) and not named) or origin == reference,
                    f"Note reference disagrees with its verse: {code} {origin}",
                )
    if authored_page:
        return
    for block in doc["content"]:
        for _, content in matter.regions(block):
            if not scripture_unit:
                terminology.check_forms(code, usj.unlabelled(content), note=False)
            # A footnote among prose is a note like any other.
            for note in usj.notes_of(content):
                terminology.check_forms(
                    code, usj.unlabelled(note["content"]), note=True
                )


def prepare(sources: bible.sources.Sources, policy: bible.policy.Policy) -> Edition:
    """The fixed order of the stages; each takes what the ones before it made."""
    revision.check(policy)
    read_sources = read(sources, policy)
    promoted = promote(read_sources, policy)
    units = assemble(promoted, policy, read_sources)
    policy = placed(units, read_sources, policy)
    units = lined(units, read_sources, policy)
    units = matter.colophons(units, policy, read_sources.colophons)
    ctx = context(units, policy)
    front, appendix_notes, front_report = front_and_back(read_sources, ctx)
    books, reports = annotated(units, read_sources, appendix_notes, ctx)
    revised = revise(front, books, policy)
    # Brenton's list of abbreviations is finished and checked as the front
    # matter is, and the introduction tables it.
    unit = bible.policy.GLOSSARY["id"]
    check_document(
        unit, revised.finished[unit], scripture_unit=False, authored_page=False
    )
    glossary = terminology.glossary_table(revised.finished[unit])
    pages, numbering_page, variants_page, entries = authored(
        ctx, read_sources, revised, promoted.byzantine, glossary
    )
    prepared = {**pages, **revised.finished}
    documents: dict[str, Document] = {}
    for entry in policy.entries:
        code = entry["id"]
        check_document(
            code,
            prepared[code],
            scripture_unit=code in books,
            authored_page=code in pages,
        )
        documents[code] = prepared[code]
    # A row of the review for every note, read from the books as finished.
    note_rows = {
        code: annotate.finished_rows(
            revised.finished[code], reports[code].rows, policy.brenton_notes["notes"]
        )
        for code in books
    }
    read_reports = [front_report, *reports.values()]
    met: Met = MappingProxyType(
        dict(
            decisions=frozenset[str]().union(*(r.decided for r in read_reports)),
            names=frozenset[tuple[str, str | None]]().union(
                *(r.names for r in read_reports)
            ),
            revisions=frozenset(revised.met),
        )
    )
    check_met(policy, met)
    units_of = Counter(u["source"] for u in policy.scripture)
    applied = [
        row
        for row in promoted.byzantine.verified.dispositions
        if row.get("execution") == "applied"
    ]
    summary = dict(
        alexandrine_notes=promoted.alexandrine[0],
        alexandrine_appendix_paragraphs=promoted.alexandrine[1],
        byzantine_units=len(promoted.byzantine.greek.units),
        byzantine_edits=sum(1 for row in applied if row["disposition"] != "shared"),
        kjv_corrections=sum(1 for row in applied if row["disposition"] == "shared"),
        byzantine_notes=sum(
            len(usj.notes_of(doc["content"]))
            for code, doc in promoted.kjv.items()
            if code in byzantine.BOOKS
        ),
        scripture_units=len(policy.scripture),
        brenton_units=units_of["brenton"],
        kjv_units=units_of["kjv"],
        kjv_marginal_notes=sum(len(n) for n in read_sources.marginal.values()),
        printed_notes=sum(len(rows) for rows in note_rows.values()),
        verses=sum(len(v) for c in ctx.inventory.values() for v in c.values()),
    )
    return Edition(
        policy=policy,
        read=read_sources,
        documents=MappingProxyType(documents),
        scripture=frozenset(books),
        authored=frozenset(pages),
        names=MappingProxyType(
            {
                entry["id"]: assembly.names(entry, documents[entry["id"]])
                for entry in policy.entries
            }
        ),
        books=ctx.books,
        inventory=MappingProxyType(ctx.inventory),
        notes=MappingProxyType({code: tuple(rows) for code, rows in note_rows.items()}),
        summary=MappingProxyType(summary),
        met=met,
        byzantine=promoted.byzantine,
        numbering_page=numbering_page,
        variants_page=variants_page,
        variants=entries,
        glossary=glossary,
        ccel=promoted.ccel,
    )


def headed_chapters(doc: Document) -> tuple[list[Node], list[list[Node]]]:
    """A book's header and each chapter's blocks, a heading set just before a
    chapter (Susanna, Bel and the Dragon, a stasis rule, a kathisma) opening
    that chapter."""
    header, chapters = assembly.chapters_of(doc)
    parts = [list(header), *(list(chapter) for chapter in chapters)]
    for index in range(len(parts) - 1):
        blocks = parts[index]
        at = len(blocks)
        # Not a \d paragraph, which is its own chapter's and may hold verses.
        while at > 0 and blocks[at - 1].get("marker") in usj.HEADINGS:
            at -= 1
        parts[index + 1] = blocks[at:] + parts[index + 1]
        parts[index] = blocks[:at]
    return parts[0], parts[1:]


def sample_chapters(code: str, doc: Document, wanted: Sequence[int]) -> Document:
    """The header and the wanted chapters of a book, for the typesetting sample.

    A heading that opens a chapter is kept or dropped with it. Chapter
    openings already begin their own paragraphs in the full edition.
    """
    header, chapters = headed_chapters(doc)
    kept, seen = [*header], set()
    for blocks in chapters:
        at = next(i for i, block in enumerate(blocks) if block["type"] == "chapter")
        number = int(blocks[at]["number"])
        if number in wanted:
            seen.add(number)
            kept += blocks
    require(seen == set(wanted), f"Sample chapters missing from {code}: {list(wanted)}")
    return usj.with_blocks(doc, kept)


def view(edition: Edition, mode: str) -> list[tuple[str, Document]]:
    """The documents a build prints, as (id, document), in order: the whole
    edition, or the sample's chapters; with their typography and their lines
    of verse indented."""
    require(mode in ("pdf", "sample"), f"Unknown output mode: {mode}")
    sample = edition.policy.sample
    result: list[tuple[str, Document]] = []
    for code, doc in edition.documents.items():
        if code in edition.scripture and mode == "sample":
            if code not in sample:
                continue
            doc = sample_chapters(code, doc, sample[code])
        if code not in edition.authored:
            doc = typography.typographic(doc)
        result.append((code, indented(doc)))
    return result


def indented(doc: Document) -> Document:
    """Poetry indented: a line that opens a verse, a poem or a stanza at the
    first level, and a line that goes on with a verse at the second. The line
    stage uses q1; Scrivener's existing markers survive it. An acrostic
    heading starts the following line at the first level."""
    result: list[Node] = []
    for block in doc["content"]:
        first = next(iter(block.get("content", [])), None)
        if (
            usj.is_type(block, "para", "q1")
            and result
            and usj.paragraph(result[-1]) in usj.POEM
            and not usj.is_type(first, "verse")
        ):
            block = {**block, "marker": "q2"}
        result.append(block)
    return usj.with_blocks(doc, result)
