"""The translations' own front and back matter: Brenton's list of
abbreviations, preface and introduction, the King James translators'
dedication and preface, and Brenton's appendix.

Each prints under the edition's names, citing as the edition cites, with its
abbreviations in the edition's forms. Brenton's appendix is taken apart
(edition/appendix.json): each of its notes is a footnote at the verse it
discusses, and nothing of it prints after Revelation.

A paragraph is read once, as its source writes it: what it cites, and the
terms it uses. What is read is carried through each declared change of its
words, so that nothing is read again from words the edition has rewritten.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from types import MappingProxyType

import bible.annotate
import bible.policy
import bible.references
from bible import assembly, citations, repairs, scripture, terminology, usj
from bible.checks import CheckFailed, require
from bible.policy import source_id
from bible.policy_schema import Entry, WordingChange
from bible.references import parse_verse
from bible.usj import Content, Document, Node

type Address = tuple[int, int] | None
type Unit = list[tuple[Node, dict[Address, Reading]]]


# The titles and headings that drop a closing full stop. Not mt2: the Epistle
# Dedicatory's are its address ("ETC.") and salutation.
PERIOD_FREE = ("h", "toc1", "mt1", "is1", "is2")
# The origin eBible gives a note of its front matter, which has no verses:
# it names nothing.
EMPTY_ORIGIN = re.compile(r"\d+:0 ")


@dataclass(frozen=True)
class Reading:
    """What was read in a paragraph: the words as they then stood, and the
    citations and terms found in them, by their offsets in those words."""

    text: str
    citations: tuple[citations.Citation | citations.UnresolvedCitation, ...] = ()
    terms: tuple[terminology.Term, ...] = ()
    decisions: tuple[str, ...] = ()
    # The verse a paragraph taken apart goes to, as its decision is keyed.
    destination: str | None = None
    # Why its citations couldn't be read, which matters only if it prints.
    issue: str | None = None


@dataclass(frozen=True)
class Placements:
    """Where a source's paragraphs go, by their opening words: a verse, as
    its decision is keyed ("EZK 16:44"); and the labels dropped from
    paragraphs before anything reads them."""

    destinations: Mapping[str, str]
    labels: Mapping[str, str] = MappingProxyType({})


def placements(entry: Entry, policy: bible.policy.Policy) -> Placements | None:
    """Where a unit's paragraphs go, if it is the one taken apart: Brenton's
    appendix."""
    if (entry["source"], source_id(entry)) != ("brenton", policy.appendix["source"]):
        return None
    found: dict[str, str] = {}
    labels = {}
    for place, note in policy.appendix["notes"].items():
        for key in note["paragraphs"]:
            require(key not in found, f"Appendix note paragraphs placed twice: {key}")
            found[key] = place
        if "label" in note:
            labels[note["paragraphs"][0]] = note["label"]
    return Placements(MappingProxyType(found), MappingProxyType(labels))


def is_glossary(entry: Entry) -> bool:
    return (entry["source"], source_id(entry)) == ("brenton", terminology.GLOSSARY)


def rebased(reading: Reading, text: str) -> Reading:
    """A reading carried to the paragraph's words as they now stand."""
    if text == reading.text:
        return reading
    # A change touches a few words of a long paragraph: only the words between
    # what the two texts share at either end need to be compared.
    before, after = reading.text, text
    head = 0
    while head < min(len(before), len(after)) and before[head] == after[head]:
        head += 1
    tail = 0
    while (
        tail < min(len(before), len(after)) - head
        and before[-1 - tail] == after[-1 - tail]
    ):
        tail += 1
    middle = SequenceMatcher(
        None,
        before[head : len(before) - tail],
        after[head : len(after) - tail],
        autojunk=False,
    ).get_opcodes()
    changes = [
        ("equal", 0, head, 0, head),
        *(
            (kind, head + a, head + b, head + c, head + d)
            for kind, a, b, c, d in middle
        ),
        ("equal", len(before) - tail, len(before), len(after) - tail, len(after)),
    ]

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


def unlabelled(doc: Document, places: Placements) -> Document:
    """The document with the labels dropped from the paragraphs that carry
    them, before anything reads them: a label names the verse the paragraph
    now stands at, and must open its one paragraph, before the words that
    place it."""
    blocks = list(doc["content"])
    for key, label in places.labels.items():
        found = [
            (index, text)
            for index, block in enumerate(blocks)
            if usj.is_type(block, "para", "ip")
            and (text := usj.unlabelled(block["content"])).lstrip().startswith(label)
            and text.lstrip()[len(label) :].lstrip(" ").startswith(key)
        ]
        require(len(found) == 1, f"Appendix label not found once: {label}")
        index, text = found[0]
        start = len(text) - len(text.lstrip())
        end = start + len(label)
        while text[end] == " ":
            end += 1
        blocks[index] = {
            **blocks[index],
            "content": usj.substituted(
                blocks[index]["content"], [(start, end, "")], skip=usj.is_label
            ),
        }
    return usj.with_blocks(doc, blocks)


def read(
    code: str,
    doc: Document,
    destinations: Mapping[str, str],
    ctx: bible.annotate.Context,
) -> tuple[Unit, citations.Dialect]:
    """A unit's blocks, each with what was read in its prose."""
    policy = ctx.policy
    require(
        code in policy.citations["units"], f"Unit whose citations nothing reads: {code}"
    )
    tongue = citations.dialect(policy.citations["units"][code], policy=policy)
    # A paragraph that names no book is of the book last cited: a correction's
    # account of it follows its citation, in a paragraph of its own.
    standing: citations.Citation | None = None
    unit: Unit = []
    for block in doc["content"]:
        readings: dict[Address, Reading] = {}
        for address, content in regions(block):
            text = usj.unlabelled(content)
            if not text.strip():
                continue
            destination = next(
                (
                    where
                    for key, where in destinations.items()
                    if text.strip().startswith(key)
                ),
                None,
            )
            home = parse_verse(destination) if destination else None
            decisions = citations.unit_decisions(code, text, policy=policy)
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
        {**readings, address: rebased(readings[address], usj.unlabelled(content))},
    )
    return unit


def check_placed(unit: Unit, places: Placements, policy: bible.policy.Policy) -> None:
    """Refuse a unit taken apart unless every paragraph is placed exactly
    once, in a book of the edition, and the paragraphs at one verse in their
    source's order."""
    paragraphs = [
        index
        for index, (block, _) in enumerate(unit)
        if usj.is_type(block, "para", "ip")
    ]
    bodies = [usj.unlabelled(unit[index][0]["content"]).strip() for index in paragraphs]
    listed = [(place, key) for key, place in places.destinations.items()]
    books = {u["id"] for u in policy.scripture if u["source"] == "brenton"}
    unknown = sorted({parse_verse(p).book for p, _ in listed} - books)
    require(not unknown, f"Paragraphs placed in books outside the edition: {unknown}")
    indices = []
    for _, key in listed:
        matches = [n for n, body in enumerate(bodies) if body.startswith(key)]
        require(len(matches) == 1, f"Placement key names no one paragraph: {key}")
        indices.append(matches[0])
    require(len(set(indices)) == len(indices), "Paragraphs placed twice")
    require(set(indices) == set(range(len(paragraphs))), "Paragraphs not placed")
    for destination in {place for place, _ in listed}:
        order = [i for (where, _), i in zip(listed, indices) if where == destination]
        require(
            order == sorted(order), f"Paragraphs out of source order: {destination}"
        )


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
            if address in readings and change["from"] in usj.unlabelled(content)
        ]
        require(
            len(found) == 1
            and usj.unlabelled(dict(regions(unit[found[0][0]][0]))[found[0][1]]).count(
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
        start = usj.unlabelled(content).index(change["from"]) + prefix
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
    """A unit's citations as the edition numbers them."""
    result: Unit = []
    for block, readings in unit:
        settled = {}
        for address, reading in readings.items():
            require(reading.issue is None, reading.issue or "")
            found: list[citations.Citation] = []
            for citation in reading.citations:
                assert isinstance(citation, citations.UnresolvedCitation)
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
    text = usj.unlabelled(content)
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
            for match in pattern.finditer(usj.unlabelled(content))
        ]
        require(len(found) == 1, f"Change of name not met once: {code} ({before})")
        index, address, match = found[0]
        block, readings = unit[index]
        content = dict(regions(block))[address]
        after = citations.named(declaration["to"], books.names)
        require(before != after, f"Change of name changes nothing: {code} ({before})")
        edits = [
            (match.start() + a, match.start() + b, after[c:d])
            for kind, a, b, c, d in SequenceMatcher(
                None, before, after, autojunk=False
            ).get_opcodes()
            if kind != "equal"
        ]
        # The name's own styling gives way to what the edition's name has.
        content = usj.substituted(
            content, edits, skip=usj.is_label, right=True, unwrap=[match.span()]
        )
        unit = list(unit)
        unit[index] = (with_region(block, address, content), readings)
    return unit


def numbered_notes(doc: Document) -> Document:
    """A unit whose notes use automatic numbered callers, without origins
    that name no verse: those notes print under their callers alone."""

    def numbered(item: Node) -> Node | None:
        if usj.is_type(item, "note"):
            return {**item, "caller": "+"}
        if usj.is_type(item, "char", "fr") and EMPTY_ORIGIN.fullmatch(
            usj.text_of(item["content"])
        ):
            return None
        return item

    return usj.with_content(doc, lambda content: usj.mapped(content, numbered))


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


def with_terms(unit: Unit, registry: terminology.Registry) -> Unit:
    """A unit with the terms read in its prose as the edition prints them."""
    result: Unit = []
    for block, readings in unit:
        for address, content in regions(block):
            reading = readings.get(address)
            if reading is None:
                continue
            reading = rebased(reading, usj.unlabelled(content))
            block = with_region(
                block, address, terminology.printed(content, reading.terms, registry)
            )
        result.append((block, readings))
    return result


def unit(
    entry: Entry,
    doc: Document,
    ctx: bible.annotate.Context,
    report: bible.annotate.Report,
) -> tuple[Document, dict[str, list[Content]]]:
    """One unit of front or back matter as the edition prints it, and the
    paragraphs it sends to the books, by where each goes."""
    code, policy = entry["id"], ctx.policy
    source = doc
    taken_apart = placements(entry, policy)
    if taken_apart:
        doc = unlabelled(doc, taken_apart)
    destinations = taken_apart.destinations if taken_apart else {}
    read_unit, tongue = read(code, doc, destinations, ctx)
    if taken_apart:
        check_placed(read_unit, taken_apart, policy)
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
    sent: dict[str, list[Content]] = {}
    if taken_apart:
        for block, readings in shown:
            if usj.is_type(block, "para", "ip"):
                # Every paragraph is placed, or the unit was refused.
                reading = readings[None]
                assert reading.destination is not None
                sent.setdefault(reading.destination, []).append(
                    terminology.printed(
                        block["content"],
                        rebased(reading, usj.unlabelled(block["content"])).terms,
                        ctx.terms,
                    )
                )
        shown = [(b, r) for b, r in shown if not usj.is_type(b, "para", "ip")]
    if "title" in entry:
        named = assembly.named(
            entry, usj.with_blocks(doc, [block for block, _ in shown])
        )
        by_id = {id(block): readings for block, readings in shown}
        shown = [(block, by_id.get(id(block), {})) for block in named["content"]]
    shown = unpunctuated(shown)
    shown = renamed(shown, code, ctx.books, policy)
    shown = with_terms(shown, ctx.terms)
    result = numbered_notes(usj.with_blocks(doc, [block for block, _ in shown]))
    if is_glossary(entry):
        result = terminology.completed_glossary(
            result, terminology.dropped_rows(source, policy), policy
        )
        terminology.check_glossary(result, policy)
    return result, sent


def appendix_note(paragraphs: Sequence[Content], key: str) -> Node:
    """A note of Brenton's appendix as a footnote with a numbered caller, set
    below the text among the extended notes while the ordinary notes keep the
    margin. Its words keep his italics, which mention words and gloss them in
    Latin; the numbers of the verses it supplies are its own."""

    def own_numbers(node: Node) -> Node:
        if usj.is_type(node, "char", "vp"):
            return usj.char("fv", *node["content"])
        return node

    joined: Content = []
    for paragraph in paragraphs:
        joined = usj.joined(joined, [" "] if joined else [], paragraph)
    content = usj.mapped(joined, own_numbers)
    extra: usj.Extra = {"x-key": key}
    return usj.note("ef", usj.char("ft", *content), caller="+", **extra)
