"""The translations' own front and back matter: Brenton's list of
abbreviations, preface and introduction, the introduction to the Apocrypha,
the King James translators' dedication and preface, and Brenton's appendix.

Each prints under the edition's names, citing as the edition cites, with its
abbreviations in the edition's forms. The introduction to the Apocrypha is
taken apart (edition/book-introductions.json): its account of each book is a
footnote on the book's first verse, and only its general paragraphs stay at
the front.

A paragraph is read once, as its source writes it: what it cites, and the
terms it uses. What is read is carried through each declared change of its
words, so that nothing is read again from words the edition has rewritten.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, replace
from difflib import SequenceMatcher

import bible.annotate
import bible.policy
import bible.references
import bible.terminology
from bible import assembly, citations, notes, repairs, scripture, terminology, usj
from bible.checks import CheckFailed, require
from bible.policy import source_id
from bible.policy_schema import Entry, WordingChange
from bible.references import Verse, verse_at
from bible.usj import Content, Document, Node

type Address = tuple[int, int] | None
type Unit = list[tuple[Node, dict[Address, Reading]]]


# The titles and headings that drop a closing full stop. Not mt2: the Epistle
# Dedicatory's are its address ("ETC.") and salutation.
PERIOD_FREE = ("h", "toc1", "mt1", "is1", "is2")
# An editorial gloss, which the edition's introduction says is bracketed.
GLOSS = re.compile(r" ?\[[^\[\]]+\]")


@dataclass(frozen=True)
class Reading:
    """What was read in a paragraph: the words as they then stood, and the
    citations and terms found in them, by their offsets in those words."""

    text: str
    citations: tuple[citations.Citation | citations.UnresolvedCitation, ...] = ()
    terms: tuple[terminology.Term, ...] = ()
    decisions: tuple[str, ...] = ()
    # Where an introduction's paragraph goes: a book, or "book@verse".
    destination: str | None = None
    key: str | None = None
    # Why its citations couldn't be read, which matters only if it prints.
    issue: str | None = None


def is_introduction(entry: Entry, policy: bible.policy.Policy) -> bool:
    return (entry["source"], source_id(entry)) == (
        "brenton",
        policy.introductions["source"],
    )


def is_glossary(entry: Entry) -> bool:
    return (entry["source"], source_id(entry)) == ("brenton", terminology.GLOSSARY)


def words(content: Iterable[str | Node]) -> str:
    return usj.text_of(content, skip=usj.is_label)


def rebased(reading: Reading, text: str) -> Reading:
    """A reading carried to the paragraph's words as they now stand."""
    if text == reading.text:
        return reading
    changes = SequenceMatcher(None, reading.text, text, autojunk=False).get_opcodes()

    def at(position: int, ending: bool = False) -> int:
        for kind, a, b, c, d in changes:
            if a <= position < b or ending and a < position <= b:
                return c + position - a if kind == "equal" else d if ending else c
        return len(text)

    return replace(
        reading,
        text=text,
        citations=tuple(
            replace(c, start=at(c.start), end=at(c.end, True))
            for c in reading.citations
        ),
        terms=tuple(
            replace(t, start=at(t.start), end=at(t.end, True)) for t in reading.terms
        ),
    )


def regions(block: Node) -> list[tuple[Address, Content]]:
    """The stretches of prose a block holds, each with its address in it: a
    paragraph is one, and a table has one for each cell."""
    if block["type"] == "para":
        return [(None, block["content"])]
    if block["type"] == "table":
        return [
            ((r, c), cell["content"])
            for r, row in enumerate(usj.objects(block["content"]))
            for c, cell in enumerate(usj.objects(row["content"]))
        ]
    return []


def with_region(block: Node, address: Address, content: Content) -> Node:
    if address is None:
        return {**block, "content": content}
    r, c = address
    rows = list(block["content"])
    row = rows[r]
    assert isinstance(row, dict)
    cells = list(row["content"])
    cell = cells[c]
    assert isinstance(cell, dict)
    cells[c] = {**cell, "content": content}
    rows[r] = {**row, "content": cells}
    return {**block, "content": rows}


def destinations(policy: bible.policy.Policy) -> dict[str, str]:
    """Where each paragraph of the introduction to the Apocrypha goes, by its
    opening words."""
    data = policy.introductions
    found = {key: book for book, keys in data["books"].items() for key in keys}
    for book, sections in data["sections"].items():
        for verse, section in sections.items():
            require(
                set(section) == {"heading", "paragraphs"},
                f"Book introduction section with missing or unknown fields: {book}@{verse}",
            )
            found.update({key: f"{book}@{verse}" for key in section["paragraphs"]})
    return found


def read(
    code: str, doc: Document, entry: Entry, ctx: bible.annotate.Context
) -> tuple[Unit, citations.Dialect]:
    """A unit's blocks, each with what was read in its prose."""
    policy = ctx.policy
    require(
        code in policy.citations["units"], f"Unit whose citations nothing reads: {code}"
    )
    tongue = citations.dialect(policy.citations["units"][code], policy=policy)
    introduction = is_introduction(entry, policy)
    places = destinations(policy) if introduction else {}
    # A paragraph that names no book is of the book last cited: a correction's
    # account of it follows its citation, in a paragraph of its own.
    standing: citations.Citation | None = None
    unit: Unit = []
    for block in doc["content"]:
        readings: dict[Address, Reading] = {}
        for address, content in regions(block):
            text = words(content)
            if not text.strip():
                continue
            destination = next(
                (
                    where
                    for key, where in places.items()
                    if text.strip().startswith(key)
                ),
                None,
            )
            book = destination.split("@")[0] if destination else None
            home = (
                verse_at(book or "", (destination or "").split("@")[1])
                if "@" in (destination or "")
                else Verse(book, 0, 1) if book else None
            )
            decisions = citations.unit_decisions(code, text, book, policy=policy)
            issue = None
            try:
                found = tuple(
                    citations.parse(
                        text,
                        tongue,
                        home,
                        code,
                        list(decisions.values()),
                        standing,
                        policy=policy,
                    )
                )
            except CheckFailed as failure:
                found, issue = (), str(failure)
            for citation in found:
                if citation.items and not citation.relative:
                    standing = citation
            readings[address] = Reading(
                text,
                found,
                terminology.found(content, ctx.terms, note=bool(destination)),
                tuple(decisions),
                destination,
                issue=issue,
            )
        unit.append((block, readings))
    return unit, tongue


def changed(unit: Unit, index: int, address: Address, content: Content) -> Unit:
    """A unit with one stretch of prose rewritten, what was read in it
    carried to its new words."""
    block, readings = unit[index]
    unit = list(unit)
    unit[index] = (
        with_region(block, address, content),
        {**readings, address: rebased(readings[address], words(content))},
    )
    return unit


def rewritten(
    content: Content,
    before: str,
    after: str,
    key: str,
    *,
    start: int | None = None,
    unwrap: Iterable[tuple[int, int]] = (),
) -> Content:
    """Content with words changed without disturbing its character styles,
    but for those whose words lie wholly within a stretch to unwrap."""
    text = words(content)
    if start is None:
        require(
            text.count(before) == 1, f"Decision does not apply once: {key}: {before}"
        )
        start = text.index(before)
    require(
        text[start : start + len(before)] == before, f"Decision's words changed: {key}"
    )
    edits = [
        (start + a, start + b, after[c:d])
        for kind, a, b, c, d in SequenceMatcher(
            None, before, after, autojunk=False
        ).get_opcodes()
        if kind != "equal"
    ]
    return usj.substituted(content, edits, skip=usj.is_label, right=True, unwrap=unwrap)


def once_in_words(text: str, wanted: str) -> bool:
    """Whether the words occur once in the text, and not as part of a longer word."""
    return (
        text.count(wanted) == 1
        and re.search(rf"(?<!\w){re.escape(wanted)}(?!\w)", text) is not None
    )


def placed(unit: Unit, policy: bible.policy.Policy) -> Unit:
    """The unit that is the introduction to the Apocrypha with each of its
    paragraphs placed, glossed and renamed as the file declares.

    Every paragraph must be placed or explicitly omitted exactly once, and
    every gloss and change of name must apply once.
    """
    data = policy.introductions
    paragraphs = [
        index
        for index, (block, _) in enumerate(unit)
        if usj.is_type(block, "para", "ip")
    ]
    bodies = [words(unit[index][0]["content"]).strip() for index in paragraphs]
    require(
        not any("[" in body or "]" in body for body in bodies),
        "Book introduction brackets not a gloss's",
    )
    placements = [("front", key) for key in data["front"]] + [
        (place, key) for key, place in destinations(policy).items()
    ]
    require(all(data["omit"].values()), "Omitted book introductions need a reason")
    accounted = placements + [(None, key) for key in data["omit"]]
    books = {u["id"] for u in policy.scripture if u["source"] == "brenton"}
    unknown = sorted((set(data["books"]) | set(data["sections"])) - books)
    require(not unknown, f"Book introductions for books outside the edition: {unknown}")
    indices = []
    for _, key in accounted:
        matches = [n for n, body in enumerate(bodies) if body.startswith(key)]
        require(
            len(matches) == 1, f"Book introduction key names no one paragraph: {key}"
        )
        indices.append(matches[0])
    require(
        len(set(indices)) == len(indices), "Book introduction paragraphs placed twice"
    )
    require(
        set(indices) == set(range(len(paragraphs))),
        "Book introduction paragraphs not placed",
    )
    keys = {key for _, key in placements}
    require(not set(data["glosses"]) - keys, "Glosses on no placed paragraph")
    require(not set(data["names"]) - keys, "Name changes on no placed paragraph")
    require(
        all(data["glosses"].values()) and all(data["names"].values()),
        "Glosses or name changes that change nothing",
    )
    places = {
        "front",
        *data["books"],
        *(f"{c}@{v}" for c, sections in data["sections"].items() for v in sections),
    }
    empty = sorted(places - {place for place, _ in placements})
    require(not empty, f"Book introductions with no paragraphs: {empty}")
    for destination in places:
        order = [i for (where, _), i in zip(accounted, indices) if where == destination]
        require(
            order == sorted(order),
            f"Book introduction out of source order: {destination}",
        )
    for (place, key), n in zip(accounted, indices):
        index = paragraphs[n]
        block, readings = unit[index]
        unit = list(unit)
        unit[index] = (block, {None: replace(readings[None], key=key)})
        if place is None:
            continue
        original = bodies[n]
        for gloss in data["glosses"].get(key, ()):
            require(gloss.get("why"), f"Gloss without a why: {key}")
            require(
                GLOSS.fullmatch(gloss.get("insert", "")),
                f"Gloss is not one bracketed insertion: {key}",
            )
            # A gloss follows the source's words, or replaces them. Once in
            # the source as well, so that no gloss falls inside another.
            replaces = "replace" in gloss
            before = gloss.get("replace") if replaces else gloss.get("after")
            content = unit[index][0]["content"]
            require(
                replaces != ("after" in gloss)
                and before
                and once_in_words(original, before)
                and once_in_words(words(content), before),
                f"Gloss does not apply: {key}",
            )
            assert before is not None
            require(
                gloss["insert"].startswith(" ") != replaces,
                f"Gloss and the space before it disagree: {key}",
            )
            after = gloss["insert"] if replaces else before + gloss["insert"]
            unit = changed(unit, index, None, rewritten(content, before, after, key))
        for name in data["names"].get(key, ()):
            require(name.get("why"), f"Name change without a why: {key}")
            require(
                name.get("from") and name.get("to") and name["from"] != name["to"],
                f"Name change that changes nothing: {key}",
            )
            # A name is written with its source's styling, which stays.
            old_content, new_content = (
                usj.parse(name[side], fragment=True) for side in ("from", "to")
            )
            require(
                [n["marker"] for n in usj.walk(old_content)]
                == [n["marker"] for n in usj.walk(new_content)],
                f"Name change alters the markup: {key}",
            )
            before, after = usj.text_of(old_content), usj.text_of(new_content)
            content = unit[index][0]["content"]
            # The source's words, so that no change alters or removes a gloss.
            require(
                once_in_words(original, before)
                and once_in_words(words(content), before),
                f"Name change does not apply once: {key}",
            )
            # The editor's own words are bracketed, and only a gloss adds them.
            require(
                "[" not in after and "]" not in after,
                f"Name change adds brackets, which are a gloss's: {key}",
            )
            unit = changed(unit, index, None, rewritten(content, before, after, key))
    return unit


def edited(
    unit: Unit,
    code: str,
    changes: Iterable[WordingChange],
    name: str,
    *,
    right: bool = False,
) -> Unit:
    """A unit with each declared change to its words, which must be its once.
    Words that are only added join the words before them, or, from the right,
    the words after them."""
    for change in changes:
        require(
            change["from"] and change["from"] != change["to"],
            f"{name} changes nothing: {code}: {change['from']}",
        )
        found = [
            (index, address)
            for index, (block, readings) in enumerate(unit)
            for address, content in regions(block)
            if address in readings and change["from"] in words(content)
        ]
        require(
            len(found) == 1
            and words(dict(regions(unit[found[0][0]][0]))[found[0][1]]).count(
                change["from"]
            )
            == 1,
            f"{name} not met once: {code} {change['from']}",
        )
        index, address = found[0]
        content = dict(regions(unit[index][0]))[address]
        # One stretch gives way, so that what replaces it stays in the style
        # of the words it replaces.
        prefix, removed, added = repairs.change(change["from"], change["to"])
        start = words(content).index(change["from"]) + prefix
        unit = changed(
            unit,
            index,
            address,
            usj.substituted(
                content,
                [(start, start + len(removed), added)],
                skip=usj.is_label,
                right=right,
            ),
        )
    return unit


def resolved(
    unit: Unit, code: str, inventory: scripture.Inventory, policy: bible.policy.Policy
) -> Unit:
    """A unit's citations as the edition numbers them. A paragraph that
    introduces a book cites as from the book's first verse, or its section's."""
    result: Unit = []
    for block, readings in unit:
        settled = {}
        for address, reading in readings.items():
            require(reading.issue is None, reading.issue or "")
            home = None
            if reading.destination:
                book, _, reference = reading.destination.partition("@")
                if reference:
                    home = verse_at(book, reference)
                else:
                    chapter = next(iter(inventory[book]))
                    home = verse_at(book, f"{chapter}:{inventory[book][chapter][0]}")
            found: list[citations.Citation] = []
            for citation in reading.citations:
                assert isinstance(citation, citations.UnresolvedCitation)
                if (
                    home is not None
                    and citation.relative
                    and isinstance(citation.context, Verse)
                ):
                    items = citation.items
                    if citation.relative == "verse":
                        items = tuple(
                            tuple(replace(item, chapter=home.chapter) for item in run)
                            for run in items
                        )
                    citation = replace(
                        citation, book=home.book, items=items, context=home
                    )
                found.append(
                    citations.resolve(citation, inventory, code, policy=policy)
                )
            settled[address] = replace(reading, citations=tuple(found))
        result.append((block, settled))
    return result


def cited(
    content: Content, reading: Reading, books: bible.references.Books, code: str
) -> Content:
    """Content with what it cites as the edition prints it. The source's
    italics within a citation give way to the edition's way of citing."""
    text = words(content)
    reading = rebased(reading, text)
    edits, unwrap = [], []
    for citation in reading.citations:
        edits.append((citation.start, citation.end, citations.printed(citation, books)))
        unwrap.append((citation.start, citation.end))
    if not edits:
        return content
    # A style that only part of a citation lies in can be neither kept nor dropped.
    at = 0

    def spans(items: Content) -> Iterator[tuple[int, int]]:
        nonlocal at
        for item in items:
            if isinstance(item, str):
                at += len(item)
            elif "content" in item and not usj.is_label(item):
                start = at
                yield from spans(item["content"])
                if item["type"] == "char" and item["marker"] not in usj.FIELDS:
                    yield start, at

    for opened, closed in spans(content):
        for start, end in unwrap:
            require(
                not (opened < start < closed < end or start < opened < end < closed),
                f"Citation across markup: {code} ({text[start:end]})",
            )
    return usj.substituted(content, edits, skip=usj.is_label, unwrap=unwrap)


def renamed(
    unit: Unit, code: str, books: bible.references.Books, policy: bible.policy.Policy
) -> Unit:
    """A unit with the names that are changed where a book is named but not
    cited (edition/citations.json), each met once."""
    for declaration in policy.citations["names"].get(code, ()):
        before = usj.text_of(usj.parse(declaration.get("from", ""), fragment=True))
        require(
            before and declaration.get("to") is not None and declaration.get("why"),
            f"Change of name without its words or reason: {code} ({before})",
        )
        pattern = re.compile(
            (r"(?<!\w)" if before[0].isalnum() else "")
            + re.escape(before)
            + (r"(?!\w)" if before[-1].isalnum() else "")
        )
        found = [
            (index, address, match)
            for index, (block, _) in enumerate(unit)
            for address, content in regions(block)
            for match in pattern.finditer(words(content))
        ]
        require(len(found) == 1, f"Change of name not met once: {code} ({before})")
        index, address, match = found[0]
        block, readings = unit[index]
        content = dict(regions(block))[address]
        after = citations.named(declaration["to"], books.names)
        require(before != after, f"Change of name changes nothing: {code} ({before})")
        # The name's own styling gives way to what the edition's name has.
        unit = list(unit)
        unit[index] = (
            with_region(
                block,
                address,
                rewritten(
                    content,
                    before,
                    after,
                    key=f"{code} ({before})",
                    start=match.start(),
                    unwrap=[match.span()],
                ),
            ),
            readings,
        )
    return unit


def unpunctuated(unit: Unit) -> Unit:
    """A unit whose titles and headings drop their closing full stops."""
    result: Unit = []
    for block, readings in unit:
        if block.get("marker") in PERIOD_FREE:
            # The stop that closes its words, not one that ends a string
            # before a style or within a note.
            stop = re.search(r"\.\s*$", usj.text_of(block["content"]))
            if stop:
                block = {
                    **block,
                    "content": usj.substituted(
                        block["content"], [(stop.start(), stop.start() + 1, "")]
                    ),
                }
        result.append((block, readings))
    return result


def with_terms(unit: Unit, registry: bible.terminology.Registry) -> Unit:
    """A unit with the terms read in its prose as the edition prints them."""
    result: Unit = []
    for block, readings in unit:
        for address, content in regions(block):
            reading = readings.get(address)
            if reading is None:
                continue
            reading = rebased(reading, words(content))
            block = with_region(
                block, address, terminology.printed(content, reading.terms, registry)
            )
        result.append((block, readings))
    return result


def unit(
    entry: Entry,
    doc: Document,
    source: Document,
    text: str,
    ctx: bible.annotate.Context,
    report: bible.annotate.Report,
) -> tuple[Document, dict[str, list[Content]]]:
    """One unit of front or back matter as the edition prints it, and the
    introductions it sends to the books, by where each goes.

    The unit is read as its source has it. A paragraph of the source that the
    document no longer holds, as a passage of the appendix that a book now
    prints, is read too, for what it settles for the paragraphs after it, and
    then left out: the document's blocks must be the source's own.
    """
    code, policy = entry["id"], ctx.policy
    read_unit, tongue = read(code, source, entry, ctx)
    # A change is made to the source's own paragraph, printed or not.
    originals = [block for block, _ in read_unit]
    kept = {id(block) for block in doc["content"]}
    introduction = is_introduction(entry, policy)
    if introduction:
        read_unit = placed(read_unit, policy)
    changes = [
        c
        for group in policy.prose.values()
        for c in group["changes"]
        if c.get("unit") == code
    ]
    read_unit = edited(read_unit, code, changes, "Prose change")
    if is_glossary(entry):
        terminology.check_abbreviations(policy)
        # What a meaning adds takes the style of the words after it, so that
        # an English gloss after italic Latin stays roman.
        read_unit = edited(
            read_unit,
            code,
            policy.abbreviations["meanings"]["changes"],
            "Prose change",
            right=True,
        )
    read_unit = [
        pair for pair, original in zip(read_unit, originals) if id(original) in kept
    ]
    read_unit = resolved(read_unit, code, ctx.inventory, policy)
    for _, readings in read_unit:
        for reading in readings.values():
            report.names.update((tongue.name, c.name) for c in reading.citations)
            report.decided.update(reading.decisions)
    used = [
        d for _, readings in read_unit for r in readings.values() for d in r.decisions
    ]
    doubled = sorted(d for d in set(used) if used.count(d) > 1)
    require(not doubled, f"Citation decisions met more than once: {doubled}")
    shown = []
    for block, readings in read_unit:
        for address, content in regions(block):
            if address in readings:
                block = with_region(
                    block, address, cited(content, readings[address], ctx.books, code)
                )
        shown.append((block, readings))
    introductions = {}
    if introduction:
        front: Unit = []
        moved: dict[str, list[tuple[Node, Reading]]] = {}
        for block, readings in shown:
            current_reading = readings.get(None)
            if usj.is_type(block, "para") and block["marker"].startswith("is"):
                # The books' titles replace the chapter's headings.
                continue
            if usj.is_type(block, "para", "ip"):
                require(
                    current_reading is not None and current_reading.key is not None,
                    "Unaccounted introduction paragraph",
                )
                assert current_reading is not None
                if current_reading.destination:
                    moved.setdefault(current_reading.destination, []).append(
                        (block, current_reading)
                    )
                    continue
                if current_reading.key not in policy.introductions["front"]:
                    continue
            front.append((block, readings))
        shown = front
        introductions = {
            place: [
                terminology.printed(
                    block["content"],
                    rebased(reading, words(block["content"])).terms,
                    ctx.terms,
                )
                for block, reading in paragraphs
            ]
            for place, paragraphs in moved.items()
        }
    if "title" in entry:
        named = assembly.named(
            entry, usj.with_blocks(doc, [block for block, _ in shown]), text
        )
        by_id = {id(block): readings for block, readings in shown}
        shown = [(block, by_id.get(id(block), {})) for block in named["content"]]
    shown = unpunctuated(shown)
    shown = renamed(shown, code, ctx.books, policy)
    shown = with_terms(shown, ctx.terms)
    result = usj.with_blocks(doc, [block for block, _ in shown])
    if is_glossary(entry):
        result = terminology.completed_glossary(
            result, terminology.dropped_rows(source, policy), policy
        )
        terminology.check_glossary(result, policy)
    return result, introductions


def introduction_note(paragraphs: Sequence[Content]) -> Node:
    """A book's introduction as a footnote without a caller, set below the
    text among the extended notes while the ordinary notes keep the margin."""
    content: Content = []
    for paragraph in paragraphs:
        content = usj.joined(content, [" "] if content else [], paragraph)
    return usj.note("ef", usj.char("ft", *notes.prose(content)))
