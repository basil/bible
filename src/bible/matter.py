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
from bible.policy_schema import Entry, ProseReference, WordingChange
from bible.references import Item, parse_passage, parse_verse
from bible.usj import Content, Document, Node

type Address = tuple[int, int] | None
type Unit = list[tuple[Node, dict[Address, Reading]]]


# The titles and headings that drop a closing full stop. Not mt2: the Epistle
# Dedicatory's are its address ("ETC.").
PERIOD_FREE = ("h", "toc1", "mt1", "s1", "s2")
# How standalone prose prints: the sources' introduction markers as the
# ordinary paragraphs and headings of a unit of its own.
STANDALONE = {"ip": "p", "im": "m", "imi": "mi", "is1": "s1", "is2": "s2"}
# The origin eBible gives a note of its front matter, which has no verses:
# it names nothing.
EMPTY_ORIGIN = re.compile(r"\d+:0 ")


def with_colophon(doc: Document, content: Content) -> Document:
    """A book whose terminal subscription's first paragraph has the content
    given."""
    blocks = doc["content"]
    paragraph, *rest = blocks[-1]["content"]
    assert not isinstance(paragraph, str)
    return usj.with_blocks(
        doc,
        [
            *blocks[:-1],
            {**blocks[-1], "content": [{**paragraph, "content": content}, *rest]},
        ],
    )


def unpilcrowed(doc: Document) -> Document:
    """A book whose terminal subscription opens without the pilcrow the
    source's epistles open theirs with."""
    blocks = doc["content"]
    if not blocks or blocks[-1].get("category") != "colophon":
        return doc
    paragraph = blocks[-1]["content"][0]
    assert not isinstance(paragraph, str)
    text = usj.text_of(paragraph["content"])
    if not text.startswith("¶"):
        return doc
    pilcrow = len(text) - len(text[1:].lstrip())
    return with_colophon(doc, usj.substituted(paragraph["content"], [(0, pilcrow, "")]))


def colophons(
    books: Mapping[str, Document], policy: bible.policy.Policy
) -> MappingProxyType[str, Document]:
    """Terminal source subscriptions, outside scripture, without their
    pilcrow and with their declared edits."""
    result = {code: unpilcrowed(doc) for code, doc in books.items()}
    for name, group in policy.prose.items():
        for change in group.get("colophons", ()):
            code = change["book"]
            label = f"Colophon change in {name}: {code}"
            require(code in result, f"{label}: missing book")
            doc = result[code]
            blocks = doc["content"]
            found = [i for i, b in enumerate(blocks) if b.get("category") == "colophon"]
            require(
                found == [len(blocks) - 1], f"{label}: expected one terminal colophon"
            )
            content = blocks[-1]["content"]
            require(
                len(content) == 1 and usj.is_type(content[0], "para", "p"),
                f"{label}: expected one colophon paragraph",
            )
            paragraph = content[0]
            assert not isinstance(paragraph, str)
            text = usj.text_of(paragraph["content"])
            before, after = change["from"], change["to"]
            require(
                text.count(before) == 1, f"{label}: words do not match exactly once"
            )
            if text == before and not after:
                result[code] = usj.with_blocks(doc, blocks[:-1])
            else:
                # One stretch gives way, so that what replaces it stays in the
                # style of the words it replaces, as a prose change does.
                prefix, removed, added = repairs.change(before, after)
                start = text.index(before) + prefix
                edited = usj.substituted(
                    paragraph["content"], [(start, start + len(removed), added)]
                )
                result[code] = with_colophon(doc, edited)
    return MappingProxyType(result)


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
    glossary = bible.policy.GLOSSARY
    return (entry["source"], source_id(entry)) == (
        glossary["source"],
        source_id(glossary),
    )


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
    """A unit whose titles and headings drop their closing full stops, but
    not the period of an abbreviation read there, as "etc."."""
    result: Unit = []
    for block, readings in unit:
        if block.get("marker") in PERIOD_FREE:
            # The stop that closes its words, not one that ends a string
            # before a style or within a note.
            words = usj.text_of(block["content"])
            stop = re.search(r"\.\s*$", words)
            terms = readings[None].terms if None in readings else ()
            if stop and not any(
                t.lexeme.endswith(".") and words.rstrip().endswith(t.lexeme)
                for t in terms
            ):
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


def supplemented(code: str, doc: Document, policy: bible.policy.Policy) -> Document:
    """Restore declared paragraphs after their exact, unique source paragraph,
    in the order they are declared."""
    after: dict[int, list[Node]] = {}
    for name, group in policy.prose.items():
        for addition in group.get("additions", ()):
            if addition["unit"] != code:
                continue
            found = [
                index
                for index, block in enumerate(doc["content"])
                if usj.is_type(block, "para", "ip")
                and usj.unlabelled(block["content"]).strip() == addition["after"]
            ]
            require(len(found) == 1, f"Prose addition not met once: {code}: {name}")
            after.setdefault(found[0], []).extend(
                bible.policy.thaw(addition["paragraphs"])
            )
    blocks: list[Node] = []
    for index, block in enumerate(doc["content"]):
        blocks.append(block)
        blocks.extend(after.get(index, ()))
    return usj.with_blocks(doc, blocks)


def roman(content: Content) -> Content:
    """Content without its italics, except within its notes, which keep
    their own."""
    result: Content = []
    for item in content:
        if usj.is_type(item, "char", "it"):
            usj.extended(result, roman(item["content"]))
        elif isinstance(item, dict) and "content" in item and not usj.is_note(item):
            result.append({**item, "content": roman(item["content"])})
        else:
            usj.extended(result, [item])
    return result


def presented(code: str, doc: Document, policy: bible.policy.Policy) -> Document:
    """Declared italics and section breaks, matched in the source's words.

    Every group's notes are moved first, then its italics set, then its
    sections opened, so that each is matched in the source's paragraphs
    whichever group declares it. A section may begin within a source
    paragraph. Only that paragraph is split; its words and character styles
    stay where they were.
    """
    blocks = list(doc["content"])
    groups = policy.prose.values()
    for caller in [
        c for g in groups for c in g.get("callers", ()) if c["unit"] == code
    ]:
        notes_found = [
            (i, note)
            for i, block in enumerate(blocks)
            for note in usj.notes_of(block.get("content", []))
            if usj.unlabelled(note["content"]).strip() == caller["note"]
        ]
        label = f"Prose caller: {code}: {caller['note']}"
        require(len(notes_found) == 1, f"{label}: note not met once")
        i, note = notes_found[0]
        block = blocks[i]
        words = usj.text_of(block["content"])
        require(words.count(caller["after"]) == 1, f"{label}: anchor not met once")
        at = words.index(caller["after"]) + len(caller["after"])
        content = usj.mapped(block["content"], lambda n: None if n == note else n)
        content = usj.inserted(content, at, [note])
        require(content != block["content"], f"{label}: changes nothing")
        blocks[i] = {**block, "content": content}
    for italic in [
        d for g in groups for d in g.get("italics", ()) if d["unit"] == code
    ]:
        found = [
            i
            for i, b in enumerate(blocks)
            if b.get("marker") in {"ip", "im"}
            and usj.text_of(b["content"]).startswith(italic["opening"])
        ]
        label = f"Prose italics: {code}: {italic['opening']}"
        require(len(found) == 1, f"{label}: paragraph not met once")
        i = found[0]
        original = blocks[i]["content"]
        content = roman(original)
        words = usj.text_of(content)
        spans = []
        for span in italic["spans"]:
            phrase = span if isinstance(span, str) else span["text"]
            context = words if isinstance(span, str) else span["within"]
            offset = 0
            if not isinstance(span, str):
                require(
                    words.count(context) == 1,
                    f"{label}: context not met once: {context}",
                )
                offset = words.index(context)
                end = offset + len(context)
                require(
                    not re.fullmatch(r"\w\w", words[max(offset - 1, 0) : offset + 1])
                    and not re.fullmatch(r"\w\w", words[end - 1 : end + 1]),
                    f"{label}: context within a word: {context}",
                )
            matches = list(
                re.finditer(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", context)
            )
            require(len(matches) == 1, f"{label}: span not met once: {phrase}")
            start = offset + matches[0].start()
            spans.append((start, start + len(phrase)))
        spans.sort()
        require(
            all(b <= c for (_, b), (c, _) in zip(spans, spans[1:])),
            f"{label}: overlapping spans",
        )
        for start, end in reversed(spans):
            # A note at either edge of a span stays outside its italics.
            head, rest = usj.split(content, start)
            inner, tail = usj.split(rest, end - start, notes_left=False)
            content = usj.joined(head, [usj.char("it", *inner)], tail)
        require(content != original, f"{label}: changes nothing")
        blocks[i] = {**blocks[i], "content": content}
    for section in [
        d for g in groups for d in g.get("sections", ()) if d["unit"] == code
    ]:
        phrase = section["before"]
        breaks = [
            (i, m.start())
            for i, b in enumerate(blocks)
            if b.get("marker") in {"ip", "im"}
            for m in re.finditer(re.escape(phrase), usj.text_of(b["content"]))
        ]
        require(len(breaks) == 1, f"Prose section not met once: {code}: {phrase}")
        i, at = breaks[0]
        block = blocks[i]
        head, tail = usj.split(block["content"], at)
        replacement = [usj.para("s1", section["heading"])]
        if head:
            replacement.insert(0, {**block, "content": usj.trimmed(head)})
        replacement.append(
            {
                **block,
                "marker": "ip" if head else block["marker"],
                "content": usj.trimmed(tail),
            }
        )
        blocks[i : i + 1] = replacement
    return usj.with_blocks(doc, blocks)


def cited_places(citation: citations.Citation) -> list[object]:
    """What a citation names, in its order: each verse, and each chapter it
    names whole, which has no verses to compare."""
    places: list[object] = []
    for book, runs in citation.targets:
        for run in runs:
            for item in run:
                passage = item.passage(book)
                places.extend(passage.verses if passage else [(book, item.chapter)])
    return places


def referenced(unit: Unit, code: str, ctx: bible.annotate.Context) -> Unit:
    """Explicit references in prose, placed at exact words as margin notes.

    Existing inline citations are read and checked before they are moved.
    New references name King James coordinates and use the same resolver as
    the source's citations, including chapter-only references. Callers follow
    the anchor's punctuation and closing delimiters, except for dashes
    (Chicago Manual of Style 13.29). An anchor ends where a word does, so
    that no caller splits one, as before a possessive's "’s"; nor does a
    caller stand within a citation.
    """
    anchored: dict[tuple[int, Address], list[tuple[int, ProseReference]]] = {}
    for group in ctx.policy.prose.values():
        for decision in group.get("references", ()):
            if decision["unit"] != code:
                continue
            phrase = decision["after"]
            pattern = re.escape(phrase) + (
                r"(?!['’]?\w)" if phrase[-1].isalnum() else ""
            )
            found = [
                (i, address, m.end())
                for i, (_, readings) in enumerate(unit)
                for address, reading in readings.items()
                for m in re.finditer(pattern, reading.text)
            ]
            label = f"Prose reference: {code}: {phrase}"
            require(len(found) == 1, f"{label}: anchor not met once")
            i, address, at = found[0]
            reading = unit[i][1][address]
            text = reading.text
            while at < len(text) and text[at] in ".,;:!?)]}\"'’”":
                at += 1
            require(
                not any(c.start < at < c.end for c in reading.citations),
                f"{label}: caller within a citation",
            )
            anchored.setdefault((i, address), []).append((at, decision))
    result = list(unit)
    for (i, address), decisions in anchored.items():
        block, readings = result[i]
        reading = readings[address]
        content = dict(regions(block))[address]
        require(
            not list(usj.notes_of(content)),
            f"Prose references require unnoted prose: {code}",
        )
        edits: list[tuple[int, int, Content]] = []
        removed_citations = []
        removed_terms: list[terminology.Term] = []
        for at, decision in decisions:
            label = f"Prose reference: {code}: {decision['after']}"
            # Consecutive passages of one book are one citation, which names
            # its book once, as the edition's lists of passages do.
            by_book: list[tuple[str, list[str], list[Item]]] = []
            for reference in decision["passages"].split("; "):
                book, _, numbers = reference.partition(" ")
                if ":" in numbers:
                    passage = parse_passage(reference)
                    first, last = passage.first, passage.last
                    item = Item(first.chapter, first.number, last.number, first.letter)
                else:
                    require(
                        numbers.isdigit() and int(numbers) > 0,
                        f"{label}: invalid chapter: {reference}",
                    )
                    item = Item(int(numbers), None, None)
                if by_book and by_book[-1][0] == book:
                    by_book[-1][1].append(reference)
                    by_book[-1][2].append(item)
                else:
                    by_book.append((book, [reference], [item]))
            linked: Content = []
            targets: list[object] = []
            for book, sources, items in by_book:
                expression = citations.UnresolvedCitation(
                    0,
                    0,
                    "; ".join(sources),
                    book,
                    tuple((item,) for item in items),
                    "kjv",
                    coordinate_numbering="kjv",
                )
                citation = citations.resolve(
                    expression, ctx.inventory, label, policy=ctx.policy
                )
                targets.extend(cited_places(citation))
                if linked:
                    linked.append(bible.references.EDITION.passages)
                linked.extend(citations.linked(citation, ctx.books))
            remove = decision.get("remove")
            if remove is not None:
                require(
                    reading.text.count(remove) == 1,
                    f"{label}: inline citation not met once",
                )
                start = reading.text.index(remove)
                end = start + len(remove)
                require(at <= start, f"{label}: removal precedes anchor")
                removed = [
                    c for c in reading.citations if start <= c.start and c.end <= end
                ]
                require(bool(removed), f"{label}: removal contains no citation")
                require(
                    [p for c in removed for p in cited_places(c)] == targets,
                    f"{label}: moved citation changes its target",
                )
                require(
                    not any(
                        c.start < end and start < c.end and c not in removed
                        for c in reading.citations
                    ),
                    f"{label}: removal cuts a citation",
                )
                residue = remove
                for citation in reversed(removed):
                    residue = (
                        residue[: citation.start - start]
                        + residue[citation.end - start :]
                    )
                require(
                    re.fullmatch(r"(?:[\s.;,]|See\b|and\b)*", residue),
                    f"{label}: removal changes prose outside its citation",
                )
                edits.append((start, end, []))
                removed_citations.extend(removed)
                removed_terms.extend(t for t in reading.terms if start <= t.start < end)
            note = usj.note("x", usj.char("xt", *linked), caller="+")
            edits.append((at, at, [note]))
        edits.sort(key=lambda edit: (edit[0], edit[1]))
        # A caller at the very end of a removal would go with the words removed.
        require(
            all(
                b <= c and a != c and (b < c or c < d)
                for (a, b, _), (c, d, _) in zip(edits, edits[1:])
            ),
            f"Overlapping prose references: {code}",
        )
        for start, end, replacement in reversed(edits):
            content = usj.replaced(content, start, end, replacement)
        reading = replace(
            reading,
            citations=tuple(c for c in reading.citations if c not in removed_citations),
            terms=tuple(t for t in reading.terms if t not in removed_terms),
        )
        result[i] = (
            with_region(block, address, content),
            {**readings, address: rebased(reading, usj.unlabelled(content))},
        )
    return result


def structured(
    code: str, doc: Document, policy: bible.policy.Policy, *, standalone: bool = True
) -> Document:
    """A unit's blocks as standalone prose. A paragraph a decision describes
    (edition/prose.json, markers), by its unit, marker, and opening words,
    takes the marker the decision gives; a blank line a decision describes,
    by the words of the paragraph after it, becomes the division it gives,
    or the heading with the words it gives, and every other goes, the
    typesetter spacing headings and lists itself;
    and the sources' introduction markers become the ordinary ones. A
    decision that describes no paragraph, or two, stops the build."""
    decisions = [
        (f"{name}: {marker.get('opening', marker.get('before'))}", marker)
        for name, group in policy.prose.items()
        for marker in group.get("markers", ())
        if marker["unit"] == code
    ]
    if not decisions and not standalone:
        return doc
    # Counted by decision, since two may share their words.
    met = [0] * len(decisions)
    source = doc["content"]
    blocks: list[Node] = []
    for at, block in enumerate(source):
        marker = usj.paragraph(block)
        if marker is None:
            blocks.append(block)
            continue
        candidates = [n for n, (_, d) in enumerate(decisions) if d["from"] == marker]
        # A blank line is known by the words after it, a paragraph by its own.
        known: Node | None = block
        if marker == "ib":
            known = source[at + 1] if at + 1 < len(source) else None
        words = (
            usj.unlabelled(known["content"]).strip()
            if candidates and usj.is_type(known, "para")
            else ""
        )
        found = [
            n
            for n in candidates
            if words.startswith(
                decisions[n][1]["before" if marker == "ib" else "opening"]
            )
        ]
        require(
            len(found) <= 1,
            "Paragraph that two marker decisions describe: "
            f"{[decisions[n][0] for n in found]}",
        )
        if found:
            met[found[0]] += 1
            decision = decisions[found[0]][1]
            if marker != "ib":
                block = {**block, "marker": decision["to"]}
            elif "heading" in decision:
                block = usj.para(decision["to"], decision["heading"])
            else:
                block = usj.para(decision["to"])
        elif marker == "ib" and standalone:
            continue
        elif marker in STANDALONE and standalone:
            block = {**block, "marker": STANDALONE[marker]}
        blocks.append(block)
    unmet = sorted(label for (label, _), count in zip(decisions, met) if count != 1)
    require(not unmet, f"Marker decisions not met once: {unmet}")
    return usj.with_blocks(doc, blocks)


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
    doc = supplemented(code, doc, policy)
    doc = presented(code, doc, policy)
    taken_apart = placements(entry, policy)
    if taken_apart:
        doc = unlabelled(doc, taken_apart)
    else:
        doc = structured(code, doc, policy)
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
    read_unit = referenced(read_unit, code, ctx)
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
    shown = with_terms(shown, ctx.terms)
    result = numbered_notes(usj.with_blocks(doc, [block for block, _ in shown]))
    if is_glossary(entry):
        result = terminology.completed_glossary(
            result, terminology.glossary_terms(source, policy), policy
        )
        terminology.check_glossary(result, policy)
    return result, sent


# What the key of a note of Brenton's Appendix ends with: `2SA 5:18 Appendix`.
APPENDIX = " Appendix"


def is_appendix(note: Node) -> bool:
    """Whether a note is one of Brenton's Appendix, set below the text."""
    return note.get("x-key", "").endswith(APPENDIX)


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
    return usj.note("f", usj.char("ft", *content), caller="+", **extra)
