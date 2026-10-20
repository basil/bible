"""USFM for PTXprint, written once from a view of the edition, with the few
things only the typesetter needs: its blank lines, the
label it prints before a chapter's number, the margin origins of the notes
without their chapter, the notes edition/margin.json sets below the text,
and the Greek and Hebrew tagged for their fonts. Only the form of what
prints changes here, never its substance."""

from __future__ import annotations

import itertools
import re
from collections.abc import Mapping, Sequence

from bible import notes, peripherals, pipeline, scripture, usfm, usj
from bible.checks import require, require_used
from bible.pipeline import Edition
from bible.policy_schema import Entry
from bible.usj import Content, Document, Node

ORIGIN = re.compile(r"^\d+:")


# Neither Greek face (GFS Didot, GFS Heraklit) encodes U+02BC, the Greek
# elision mark; both encode the typographic apostrophe.
ELISION = re.compile(f"(?<=[{usfm.GREEK}])\u02bc")
# A run of Greek or of Hebrew words, by the character style that sets its
# font. The Greek apostrophe stays in the Greek font.
FONT_RUNS = re.compile(
    "|".join(
        f"(?P<{marker}>{word}(?: +{word})*)"
        for marker, word in (
            ("wh", f"[{usfm.HEBREW}][{usfm.COMBINING}{usfm.HEBREW}]*"),
            ("wg", f"[{usfm.GREEK}][{usfm.COMBINING}\u2019{usfm.GREEK}]*"),
        )
    )
)


def font_runs(content: Content) -> Content:
    """Content as PTXprint's fonts need it: every run of Greek and Hebrew in
    the style of its font, single letters too, which PTXprint's own heuristic
    misses. Only the form of what prints changes, never its substance."""
    result: Content = []
    for item in content:
        if isinstance(item, str):
            item, at = ELISION.sub("\u2019", item), 0
            for run in FONT_RUNS.finditer(item):
                assert run.lastgroup is not None
                result += [item[at : run.start()], usj.char(run.lastgroup, run[0])]
                at = run.end()
            result.append(item[at:])
        elif "content" in item:
            result.append({**item, "content": font_runs(item["content"])})
        else:
            result.append(item)
    return [item for item in result if item != ""]


def spaced(doc: Document) -> Document:
    """Keep stanza breaks and prose/poetry transitions, never heading padding."""
    blocks = doc["content"]
    result: list[Node] = []
    for at, block in enumerate(blocks):
        marker = usj.paragraph(block)
        before = usj.paragraph(result[-1]) if result else None
        following = blocks[at + 1] if at + 1 < len(blocks) else None
        after = usj.paragraph(following)
        if marker == "b":
            if (
                before in usj.BODY
                and after in usj.BODY
                and before != "qr"
                and (before in usj.POEM or after in usj.POEM)
            ):
                result.append(block)
            continue
        if (marker in usj.POEM and before in usj.PROSE) or (
            marker in usj.PROSE and before in usj.POEM and before != "qr"
        ):
            result.append(usj.para("b"))
        result.append(block)
    return usj.with_blocks(doc, result)


def labelled(doc: Document, entry: Entry) -> Document:
    """The chapter label the manifest asks for, by which the book cites a
    chapter singly, set once before the first chapter: PTXprint prints it
    before every chapter's number in place of the figure."""
    if not entry.get("labelled_chapters"):
        return doc
    blocks = doc["content"]
    at = next(i for i, block in enumerate(blocks) if usj.is_type(block, "chapter"))
    label = usj.para("cl", entry["cited_singly"])
    return usj.with_blocks(doc, [*blocks[:at], label, *blocks[at:]])


def printed_origin(value: str, labels: Mapping[str, str]) -> str:
    """A note's origin under the label its verse prints, where that is not
    the verse's own; an origin the printed labels cannot name is refused."""
    address = value.strip()
    if address in labels:
        require(bool(labels[address]), f"Note at an unnumbered verse: {address}")
        return value.replace(address, labels[address])
    first, _, last = address.partition("-")
    chapter, _, _ = first.rpartition(":")
    require(
        first not in labels and f"{chapter}:{last}" not in labels,
        f"Note origin over verses with printed labels: {address}",
    )
    return value


def printed_labels(doc: Document) -> dict[str, str]:
    """The label each verse of a book prints, where it is not the verse's
    own. A verse that prints its own label in full, as 24:23 after the
    passages, is named as it always is."""
    return {
        address: label
        for address, label in scripture.printed(doc).items()
        if label != address
    }


def named_in_full(doc: Document) -> set[str]:
    """The verses of a book whose printed label names a chapter, as "30:1"
    does in Proverbs 24, by their own."""
    found = set()
    chapter = None
    for block in doc["content"]:
        if block["type"] == "chapter":
            chapter = block["number"]
        elif block["type"] == "para":
            found |= {
                f"{chapter}:{item['number']}"
                for item in block["content"]
                if usj.is_type(item, "verse") and ":" in item.get("pubnumber", "")
            }
    return found


def with_printed_origins(doc: Document) -> Document:
    """A book with each note's origin under the label its verse prints,
    where that is not the verse's own."""
    labels = printed_labels(doc)
    if not labels:
        return doc

    def origin(item: Node) -> Node:
        if item["type"] != "char" or not usj.is_origin(item):
            return item
        return {
            **item,
            "content": [printed_origin(usj.text_of(item["content"]), labels)],
        }

    return usj.with_content(doc, lambda items: usj.mapped(items, origin))


def document(code: str, doc: Document, edition: Edition) -> Document:
    """A document as PTXprint takes it: under its project id; its notes'
    margin origins without their chapter, which the chapter figure and running
    head supply, unless the verse's printed label names one, and bottom notes
    under their callers alone; its chapter label, where the manifest asks for
    one, set once before its first chapter as PTXprint takes it; its blank lines set; and its Greek
    and Hebrew tagged for their fonts.
    The edition's own pages are sent as the editor wrote them, except that
    a peripheral unit's citations keep their words without their links,
    which PTXprint would take as scripture to import. A note at a
    verse that prints another label than its own is set under that label."""

    def bottom(item: Node) -> Node:
        if usj.is_type(item, "note", "f") and item.get("caller") == "+":
            return {
                **item,
                "content": [p for p in item["content"] if not usj.is_origin(p)],
            }
        return item

    def origin(item: Node) -> Node | Content:
        # In peripheral modules PTXprint treats \ref as an instruction to
        # import scripture, parsing the printed book name instead of loc.
        # Keep the citation's words; its resolved links belong to the web.
        if item["type"] == "ref" and code not in edition.scripture:
            return item["content"]
        if item["type"] == "char" and usj.is_origin(item):
            values = item["content"]
            assert all(isinstance(v, str) for v in values)
            value = "".join(v for v in values if isinstance(v, str))
            shown = printed_origin(value, labels)
            if value.strip() not in full:
                shown = ORIGIN.sub("", shown)
            return {**item, "content": [shown]}
        return item

    def content(items: Content) -> Content:
        # A note's children are mapped before it, so a bottom note's origin,
        # which does not print, goes before any origin is set as it prints.
        return usj.mapped(usj.mapped(items, bottom), origin)

    labels = printed_labels(doc) if code in edition.scripture else {}
    full = named_in_full(doc) if code in edition.scripture else set()
    if code in edition.scripture:
        doc = labelled(doc, edition.policy.unit(code))
    if code not in edition.authored:
        doc = spaced(doc)
    # A unit printed from a file that holds another, or under an id that
    # PTXprint would take for its own front matter, is a unit of its own.
    doc = fonted(edition, code, usj.with_content(doc, content))
    return usj.with_code(doc, code)


def fonted(edition: Edition, code: str, doc: Document) -> Document:
    """The document with its Greek and Hebrew tagged for their fonts as the
    typesetter has them; the editor's pages stay as the editor wrote them."""
    return doc if code in edition.authored else usj.with_content(doc, font_runs)


def notes_below(edition: Edition) -> dict[str, frozenset[str]]:
    """The notes edition/margin.json sets below the text, by the book each
    stands in; a placement that names no note of the edition is refused. A
    note is keyed by its source's book, which need not be the unit's:
    Nehemias's notes are keyed as 2 Esdras's."""
    wanted = set(edition.policy.margin["below"])
    found: dict[str, frozenset[str]] = {}
    for code in edition.scripture:
        here = wanted & {
            note.get("x-key")
            for note in usj.notes_of(edition.documents[code]["content"])
        }
        if here:
            found[code] = frozenset(here)
    require_used(wanted, set[str]().union(*found.values()), "note placements")
    return found


def prepared(edition: Edition, mode: str) -> list[tuple[str, Document]]:
    """Every document of a view as PTXprint takes it, by its project id, in
    order, with the notes edition/margin.json sets below the text so set:
    the page whose margin a note relieves is PTXprint's, so the placement is
    made for it alone, and the sample prints the notes of its chapters."""
    below = notes_below(edition)
    result = []
    for code, doc in pipeline.view(edition, mode):
        if code in below:
            here = below[code] & {
                note.get("x-key") for note in usj.notes_of(doc["content"])
            }
            doc = notes.set_below(doc, here)
        result.append((code, document(code, doc, edition)))
    return result


def grouped(
    edition: Edition, documents: Sequence[tuple[str, Document]]
) -> list[tuple[str, Document]]:
    """The prepared documents as PTXprint's files: each scripture book its
    own, and each run of front matter packaged as the divisions of its
    section's document."""

    def container(code: str) -> tuple[str, str]:
        return (
            (code, code)
            if code in edition.scripture
            else (edition.policy.sections[code], peripherals.book(code))
        )

    result: list[tuple[str, Document]] = []
    for (_, code), run in itertools.groupby(documents, key=lambda cd: container(cd[0])):
        units = list(run)
        if code in edition.scripture:
            result.extend(units)
        else:
            book: Node = {"type": "book", "marker": "id", "code": code, "content": []}
            divisions = [
                peripherals.division(unit, doc, edition.names[unit]["title"])
                for unit, doc in units
            ]
            result.append((units[0][0], usj.document([book, *divisions])))
    return result


def export(edition: Edition, mode: str) -> list[tuple[str, str]]:
    """Every file of a view as USFM, by its project id, in order."""
    documents = grouped(edition, prepared(edition, mode))
    return [(code, usj.serialize(doc)) for code, doc in documents]
