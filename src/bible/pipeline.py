"""The edition, prepared: every stage in the order its inputs allow.

    read        the pinned sources, their transcription corrected, as USJ
    promote     the Alexandrine readings, in Brenton's own numbering
    assemble    the edition's books from the sources' chapters
    place       where each Old Testament verse stands in the King James Bible
    matter      the translations' front and back matter
    annotate    notes, quotation links and book introductions
    authored    the edition's own pages
    revise      the edition's spelling and punctuation
    view        the full edition, or the sample's chapters, with typography
    export      USFM for PTXprint

Each stage is a function of the stages before it and of the policy. Nothing
is read after the first, and no document is changed in place.
"""

import re
from dataclasses import dataclass
from types import MappingProxyType

from bible import (
    alexandrinus,
    annotate,
    assembly,
    crossrefs,
    matter,
    numbering,
    places,
    quotations,
    repairs,
    revision,
    scripture,
    terminology,
    typography,
    usfm,
    usj,
    versification,
)
from bible.checks import require
from bible.policy import source_id

EXPECTED_NT_MARGINAL_NOTES = 775


@dataclass(frozen=True)
class Read:
    """The sources as documents: Brenton's files and the King James Bible's
    by their codes, the notes that corrections mend, and George's listing of
    the 1611 margin by book."""

    brenton: MappingProxyType
    kjv: MappingProxyType
    mended: MappingProxyType
    marginal: MappingProxyType


def note_key(code, reference, number):
    """A Brenton note's key: its verse, then after its verse's first note, its
    number there."""
    return f"{code} {reference}" + (f"#{number}" if number > 1 else "")


def keyed(code, doc):
    """A source book with each note keyed by its source verse."""
    seen = {}
    verses = scripture.verses(doc)
    keys = {}
    for reference, verse in verses.items():
        for _, note in verse.notes:
            origin = usj.text_of(note["content"][:1]).strip()
            require(
                origin == reference,
                f"Note reference disagrees with its verse: {code} {origin}",
            )
            seen[reference] = seen.get(reference, 0) + 1
            keys[id(note)] = note_key(code, reference, seen[reference])
    if not keys:
        return doc

    def with_key(item):
        return {**item, "x-key": keys[id(item)]} if id(item) in keys else item

    def visit(content):
        return [
            (
                with_key(item)
                if isinstance(item, dict) and item["type"] == "note"
                else (
                    {**item, "content": visit(item["content"])}
                    if isinstance(item, dict) and "content" in item
                    else item
                )
            )
            for item in content
        ]

    return usj.with_blocks(
        doc,
        [
            (
                {**block, "content": visit(block["content"])}
                if block["type"] == "para"
                else block
            )
            for block in doc["content"]
        ],
    )


def marginal_notes(text, policy):
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
    result, seen = {}, {}
    for paragraph in re.split(r"\n\s*\n", text[text.index("\nMatthew 1:11 ") :]):
        # The Markdown wraps long entries; a continuation line joins its entry.
        entry = " ".join(paragraph.split())
        if not entry:
            continue
        match = entry_pattern.fullmatch(entry)
        require(match is not None, f"Unparsed marginal note: {entry}")
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
    unused = set(policy.kjv_notes["notes"]) - keys
    require(not unused, f"Unused marginal note exceptions: {sorted(unused)}")
    require(
        len(keys) == EXPECTED_NT_MARGINAL_NOTES,
        f"Expected {EXPECTED_NT_MARGINAL_NOTES} New Testament marginal notes, found {len(keys)}",
    )
    units = {u["id"] for u in policy.scripture if u["source"] == "kjv"}
    require(
        set(result) <= units, "Marginal notes name a book outside the KJV New Testament"
    )
    return MappingProxyType({code: tuple(listed) for code, listed in result.items()})


def read(sources, policy):
    """Parse the sources once, with the corrections to their transcription."""
    corrections = policy.brenton_notes["corrections"]
    printed = {source_id(e) for e in policy.entries if e.get("source") == "brenton"} | {
        part for part, _, _ in assembly.DANIEL
    }
    unprinted = sorted({k.split(" ")[0] for k in corrections} - printed)
    require(
        not unprinted,
        f"Brenton corrections name a source the edition doesn't print: {unprinted}",
    )
    brenton, mended = {}, {}
    for code, text in sources.brenton.items():
        text, mended[code] = repairs.brenton(code, text, corrections)
        brenton[code] = keyed(code, usj.parse(text))
    # Of the King James Bible, only what the edition prints or borrows, and
    # the Old Testament, in which its own is placed.
    wanted = (
        {source_id(e) for e in policy.entries if e.get("source") == "kjv"}
        | {
            key.split()[0]
            for key, e in policy.alexandrinus["passages"].items()
            if "kjv" in e
        }
        | set(versification.kjv_books(policy=policy))
    )
    kjv = {code: usj.parse(sources.kjv[code]) for code in sorted(wanted)}
    for unit in policy.scripture:
        if unit["source"] == "kjv":
            require(
                not any(
                    usj.notes_of(b.get("content", ()))
                    for b in kjv[unit["id"]]["content"]
                ),
                f"Cambridge text already has footnotes: {unit['id']}",
            )
    return Read(
        MappingProxyType(brenton),
        MappingProxyType(kjv),
        MappingProxyType(mended),
        marginal_notes(sources.marginal, policy),
    )


def promote(sources, policy):
    """Brenton's books with the Alexandrine decisions carried out."""
    counts = alexandrinus.check(policy, sources.brenton)
    return (
        MappingProxyType(
            {
                code: alexandrinus.promoted(code, doc, policy, sources.kjv)
                for code, doc in sources.brenton.items()
                if code != alexandrinus.APPENDIX
            }
        ),
        counts,
    )


def assemble(read_sources, promoted, policy, sources):
    """The edition's books under their names, and what they print."""
    assembly.check_divided(policy, sources)
    units = {
        unit["id"]: assembly.named(
            unit,
            assembly.scripture_unit(unit, promoted, read_sources.kjv, policy),
            assembly.source_text(unit, sources),
        )
        for unit in policy.scripture
    }
    return MappingProxyType(units)


def placed(units, read_sources, policy):
    """The policy with every Old Testament verse's place in the King James
    Bible, which the notes, the links and the table of chapters and verses
    then read."""
    runs = places.placed(units, read_sources.kjv, policy=policy)
    return policy.replace(versification={**policy.versification, "kjv": runs})


def note_prose(policy):
    """The declared changes to the words of notes, by the note's key."""
    found = {}
    for group in policy.prose.values():
        for change in group["changes"]:
            if "note" in change:
                found.setdefault(change["note"], []).append(change)
    return found


def quotation_links(policy, inventory):
    """The reviewed quotation links, by book, each side in the edition."""
    relations = crossrefs.quotation_relations(
        quotations.reviewed_rows(policy=policy), policy=policy
    )
    for relation in relations:
        for passage in (*relation.nt, *relation.ot):
            for verse in passage.verses:
                require(
                    f"{verse.number}{verse.letter}"
                    in inventory.get(verse.book, {}).get(str(verse.chapter), ()),
                    f"Quotation verse missing from assembled edition: {relation.id}: {verse}",
                )
    return crossrefs.planned_links(relations, tuple(inventory), policy=policy)


def context(units, policy, sources):
    return annotate.Context(
        policy,
        assembly.inventory(units),
        assembly.books(policy, sources),
        terminology.registry(policy),
        note_prose(policy),
    )


def front_and_back(read_sources, ctx, sources):
    """The translations' front and back matter, and the introductions it
    sends to the books, by where each goes."""
    policy, report = ctx.policy, annotate.Report()
    docs, introductions = {}, {}
    for entry in policy.entries:
        if "file" in entry or "section" in entry:
            continue
        family, code = entry["source"], source_id(entry)
        source = (
            read_sources.brenton[code]
            if family == "brenton"
            else read_sources.kjv[code]
        )
        # The appendix prints without the passages the books now print.
        appendix = (family, code) == ("brenton", alexandrinus.APPENDIX)
        doc = alexandrinus.pruned_appendix(source, policy) if appendix else source
        docs[entry["id"]], moved = matter.unit(
            entry, doc, source, assembly.source_text(entry, sources), ctx, report
        )
        introductions.update(moved)
    front = [
        source_id(e)
        for e in policy.entries
        if "section" not in e and e.get("source") == "brenton"
    ]
    # Its general paragraphs print only in its own front matter, so without
    # that entry they would vanish while the books' notes still printed.
    require(
        front.count(policy.introductions["source"]) == 1,
        "The introduction to the Apocrypha is not printed once as front matter",
    )
    return docs, introductions, report


def introduced(code, doc, introductions, links, ctx):
    """A book with its introduction, and its sections', as footnotes on their
    opening verses, and its quotation links, each at the start of its verse."""
    policy = ctx.policy
    verses = scripture.verses(doc)
    placed = {}
    for place, paragraphs in introductions.items():
        book, _, reference = place.partition("@")
        if book != code:
            continue
        if reference:
            require(
                reference in verses,
                f"Book introduction verse missing: {code} {reference}",
            )
            expected = policy.introductions["sections"][code][reference]["heading"]
            block = verses[reference].parts[0][0]
            heading = next(
                (
                    usj.text_of(b["content"]).strip()
                    for b in reversed(doc["content"][:block])
                    if usj.is_type(b, "para", "s1")
                ),
                None,
            )
            require(
                heading == expected,
                f"Book introduction heading changed: {code} {reference}",
            )
        else:
            reference = next(iter(verses))
        placed.setdefault(reference, []).append(matter.introduction_note(paragraphs))
    require(
        all(link.origin.book == code for link in links),
        f"Links for another book passed to {code}",
    )
    cited = {
        v.label for link in links for passage in link.passages for v in passage.verses
    }
    require(
        cited <= set(verses), f"Quotation verse missing from prepared scripture: {code}"
    )
    for link in links:
        placed.setdefault(link.origin.label, []).append(
            crossrefs.link_note(link, ctx.books)
        )
    return annotate.at_verse_starts(doc, placed) if placed else doc


def annotated(units, read_sources, introductions, ctx):
    """The books with their notes, introductions and quotation links."""
    policy = ctx.policy
    links = quotation_links(policy, ctx.inventory)
    docs, reports = {}, {}
    for unit in policy.scripture:
        code = unit["id"]
        if unit["source"] == "kjv":
            doc, report = annotate.george(
                code, units[code], read_sources.marginal.get(code, ()), ctx
            )
        else:
            mended = read_sources.mended[source_id(unit)]
            if code == "DAG":
                mended = mended.union(
                    *(read_sources.mended[part] for part, _, _ in assembly.DANIEL)
                )
            doc, report = annotate.brenton(
                code, units[code], links.get(code, ()), mended, ctx
            )
        docs[code] = introduced(code, doc, introductions, links.get(code, ()), ctx)
        reports[code] = report
    annotate.check_notes(policy, reports.values())
    return docs, reports


def authored(ctx, sources):
    """The edition's own pages, with the passages and tables they ask for."""
    policy = ctx.policy
    facing = {
        code: usfm.inventory(text)["chapters"]
        for code, text in sources.kjv.items()
        if re.search(r"^\\c ", text, re.M)
    }
    theirs = assembly.kjv_books(policy, sources)
    docs = {}
    for entry in policy.entries:
        if "file" not in entry:
            continue
        text = sources.authored[entry["file"]]
        require(
            text.startswith(f"\\id {entry['id']}\n"), f"Wrong id in {entry['file']}"
        )
        docs[entry["id"]] = numbering.page(
            text, ctx.inventory, facing, ctx.books, theirs, policy=policy
        )
    return docs


@dataclass(frozen=True)
class Edition:
    """The whole edition, prepared: every unit by its id, in the order it
    prints, before the typography and the selection that a view makes."""

    # The decisions, with the places of the verses that the build works out.
    policy: object
    documents: MappingProxyType
    # Which units are books of scripture, and which are the edition's own pages.
    scripture: frozenset
    authored: frozenset
    inventory: MappingProxyType
    # A row of the review for every note, by book, and a summary of the sources.
    notes: MappingProxyType
    summary: MappingProxyType
    # What reading the sources met: the citation decisions, each dialect's
    # names for books, and the revisions of spelling and punctuation.
    met: MappingProxyType


def check_met(policy, met):
    """Every citation decision, every name a dialect has for a book, and
    every revision must have been met: one that nothing meets would
    go stale unnoticed."""
    unused = sorted(set(policy.citations["decisions"]) - met["decisions"])
    require(not unused, f"Unused citation decisions: {unused}")
    names = sorted(
        (name, book)
        for name, tongue in policy.citations["dialects"].items()
        for book in tongue["books"]
        if (name, book) not in met["names"]
    )
    require(not names, f"Unused names for books: {names}")
    revision.check_met(policy, met["revisions"])


def check_document(code, doc, *, scripture_unit, authored_page):
    """What every prepared document must hold to."""
    notes = [
        (block, note)
        for block in doc["content"]
        if block["type"] == "para"
        for note in usj.notes_of(block["content"])
    ]
    if scripture_unit:
        # Any caller, "*" as well as "+"; only "-" sets none.
        require(
            all(note["caller"] == "-" for _, note in notes),
            f"Note with a caller left in the text: {code}",
        )
        for reference, verse in scripture.verses(doc).items():
            for _, note in verse.notes:
                origin = usj.text_of(note["content"][:1]).strip()
                require(
                    note["marker"] == "ef" or origin == reference,
                    f"Note reference disagrees with its verse: {code} {origin}",
                )
    if authored_page:
        return
    for block in doc["content"]:
        for _, content in matter.regions(block):
            if scripture_unit:
                for note in usj.notes_of(content):
                    terminology.check_forms(
                        code, usj.text_of(note["content"], skip=usj.is_label), note=True
                    )
            else:
                terminology.check_forms(code, matter.words(content), note=False)
                # A footnote among its words is a note like any other.
                for note in usj.notes_of(content):
                    terminology.check_forms(
                        code, usj.text_of(note["content"], skip=usj.is_label), note=True
                    )


def prepare(sources, policy):
    """The fixed order of the stages; each takes what the ones before it made."""
    revision.check(policy)
    read_sources = read(sources, policy)
    promoted, counts = promote(read_sources, policy)
    units = assemble(read_sources, promoted, policy, sources)
    policy = placed(units, read_sources, policy)
    ctx = context(units, policy, sources)
    front, introductions, front_report = front_and_back(read_sources, ctx, sources)
    books, reports = annotated(units, read_sources, introductions, ctx)
    pages = authored(ctx, sources)
    documents, revised = {}, set()
    for entry in policy.entries:
        code = entry["id"]
        doc = {**pages, **front, **books}[code]
        if code in books:
            doc = revision.revised(code, doc, policy, revised)
        if code not in pages:
            doc = revision.respelt(doc, policy, revised)
        check_document(
            code, doc, scripture_unit=code in books, authored_page=code in pages
        )
        documents[code] = doc
    read_reports = [front_report, *reports.values()]
    met = MappingProxyType(
        dict(
            decisions=frozenset().union(*(r.decided for r in read_reports)),
            names=frozenset().union(*(r.names for r in read_reports)),
            revisions=frozenset(revised),
        )
    )
    check_met(policy, met)
    units_of = lambda source: sum(u["source"] == source for u in policy.scripture)
    summary = dict(
        alexandrine_notes=counts[0],
        alexandrine_appendix_paragraphs=counts[1],
        scripture_units=len(policy.scripture),
        brenton_units=units_of("brenton"),
        kjv_units=units_of("kjv"),
        kjv_marginal_notes=sum(len(n) for n in read_sources.marginal.values()),
        printed_notes=sum(len(r.rows) for r in reports.values()),
        verses=sum(len(v) for c in ctx.inventory.values() for v in c.values()),
    )
    return Edition(
        policy,
        MappingProxyType(documents),
        frozenset(books),
        frozenset(pages),
        MappingProxyType(ctx.inventory),
        MappingProxyType({code: tuple(r.rows) for code, r in reports.items()}),
        MappingProxyType(summary),
        met,
    )


def sample_chapters(code, doc, wanted):
    """The header and the wanted chapters of a book, for the typesetting sample.

    A heading set just before a chapter (Susanna, Bel and the Dragon) opens
    that chapter, so it is kept or dropped with it. A chapter cannot continue
    the paragraph of an omitted chapter, so its nb becomes p.
    """
    header, chapters = assembly.chapters_of(doc)
    parts = [list(header), *(list(chapter) for chapter in chapters)]
    for index in range(len(parts) - 1):
        blocks = parts[index]
        at = len(blocks)
        # Not a \d paragraph, which is its own chapter's and may hold verses,
        # as the close of Psalm 71 does.
        while at > 0 and blocks[at - 1].get("marker") in ("s1", "ms1"):
            at -= 1
        parts[index + 1] = blocks[at:] + parts[index + 1]
        parts[index] = blocks[:at]
    kept, previous, seen = [*parts[0]], True, set()
    for blocks in parts[1:]:
        at = next(i for i, block in enumerate(blocks) if block["type"] == "chapter")
        number = int(blocks[at]["number"])
        if number in wanted:
            seen.add(number)
            if not previous and usj.is_type(blocks[at + 1], "para", "nb"):
                blocks = [
                    *blocks[: at + 1],
                    {**blocks[at + 1], "marker": "p"},
                    *blocks[at + 2 :],
                ]
            kept += blocks
        previous = number in wanted
    require(seen == set(wanted), f"Sample chapters missing from {code}: {list(wanted)}")
    return usj.with_blocks(doc, kept)


def view(edition, mode):
    """The documents a build prints, as (id, document), in order: the whole
    edition, or the sample's chapters; with their typography."""
    require(mode in ("pdf", "sample"), f"Unknown output mode: {mode}")
    sample = edition.policy.sample
    result = []
    for code, doc in edition.documents.items():
        if code in edition.scripture and mode == "sample":
            if code not in sample:
                continue
            doc = sample_chapters(code, doc, sample[code])
        if code not in edition.authored:
            doc = typography.typographic(doc)
        result.append((code, doc))
    return result


ORIGIN = re.compile(r"^\d+:")
EMPTY_ORIGIN = re.compile(r"\d+:0 ")


# GFS Didot does not encode U+02BC, the Greek elision mark; it does encode the
# typographic apostrophe.
ELISION = re.compile(f"(?<=[{usfm.GREEK}])\u02bc")
# A run of Greek or of Hebrew words, by the character style that sets its
# font. The Greek apostrophe stays in the Greek font.
FONT_RUNS = re.compile(
    "|".join(
        f"(?P<{marker}>{word}(?: +{word})*)"
        for marker, word in (
            ("wh", f"[{usfm.HEBREW}][\u0300-\u036f{usfm.HEBREW}]*"),
            ("wg", f"[{usfm.GREEK}][\u0300-\u036f\u2019{usfm.GREEK}]*"),
        )
    )
)


def font_runs(content):
    """Content as PTXprint's fonts need it: every run of Greek and Hebrew in
    the style of its font, single letters too, which PTXprint's own heuristic
    misses. Only the form of what prints changes, never its substance."""
    result = []
    for item in content:
        if isinstance(item, str):
            item, at = ELISION.sub("\u2019", item), 0
            for run in FONT_RUNS.finditer(item):
                result += [item[at : run.start()], usj.char(run.lastgroup, run[0])]
                at = run.end()
            result.append(item[at:])
        elif "content" in item:
            result.append({**item, "content": font_runs(item["content"])})
        else:
            result.append(item)
    return [item for item in result if item != ""]


def exported(code, doc, edition):
    """A document as PTXprint takes it: under its project id; its notes'
    origins without their chapter, which the chapter figure and running head
    supply; and its Greek and Hebrew tagged for their fonts. The edition's own
    pages are sent as the editor wrote them."""
    scripture_unit = code in edition.scripture

    def origin(item):
        if item["type"] == "char" and item["marker"] in ("fr", "xo"):
            value = "".join(item["content"])
            # Front matter has no verses, and its source gives its notes the
            # origin "1:0", which names nothing: they print under their callers.
            if not scripture_unit and EMPTY_ORIGIN.fullmatch(value):
                return None
            return {**item, "content": [ORIGIN.sub("", value)]}
        return item

    def content(items):
        items = usj.mapped(items, origin)
        return items if code in edition.authored else font_runs(items)

    # A unit printed from a file that holds another, or under an id that
    # PTXprint would take for its own front matter, is a unit of its own.
    book, *rest = usj.with_content(doc, content)["content"]
    return usj.serialize(usj.with_blocks(doc, [{**book, "code": code}, *rest]))


def export(edition, mode):
    """Every document of a view as USFM, by its project id, in order."""
    return [(code, exported(code, doc, edition)) for code, doc in view(edition, mode)]
