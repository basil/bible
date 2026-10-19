"""USFM for PTXprint, written once from a view of the edition, with the few
things only the typesetter needs: its blank lines and chapter openings, the
label it prints before a chapter's number, the margin origins of the notes
without their chapter, the notes edition/margin.json sets below the text,
and the Greek and Hebrew tagged for their fonts. Only the form of what
prints changes here, never its substance."""

from __future__ import annotations

import re
from collections.abc import Mapping

from bible import notes, pipeline, scripture, usfm, usj
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
    """Blank lines for PTXprint: a poem gets one where it begins after prose
    and where prose resumes after it, and a title where it follows the body
    and before its own words, so that it stands as far from them as from
    those before it. A chapter that opens with a poem or a title gets one
    before it, and so does a chapter where prose resumes after a poem. A
    heading supplies its own space, so a blank line directly before one goes.
    An acrostic heading opens its poem as a line would, and adds no space
    within the poem; existing blanks remain. Only the form of what prints
    changes, never the words."""
    blocks = doc["content"]
    result: list[Node] = []
    for at, block in enumerate(blocks):
        marker = usj.paragraph(block)
        before = usj.paragraph(result[-1]) if result else None
        after = usj.paragraph(blocks[at + 1]) if at + 1 < len(blocks) else None
        if marker == "b":
            blank = after not in usj.HEADINGS and after != "d"
        elif usj.is_type(block, "chapter"):
            blank = before in usj.BODY and (
                after in usj.OPENING
                or after == "d"
                or (before in usj.POEM and after in usj.PROSE)
            )
        elif marker == "d":
            blank = before in usj.BODY
        elif marker in usj.OPENING:
            blank = before in usj.PROSE or before == "d"
        elif marker in usj.PROSE:
            blank = before in usj.POEM or before == "d"
        else:
            blank = False
        if blank and before != "b":
            result.append(usj.para("b"))
        if marker != "b":
            result.append(block)
    return usj.with_blocks(doc, result)


def opened(doc: Document) -> Document:
    """Each chapter opening in a paragraph of its own, as the Berean Standard
    Bible sets it: a chapter that goes on with its source's paragraph, or
    opens one flush left, opens it as any other. The chapter figure sets its
    first line alike either way."""
    blocks = doc["content"]
    return usj.with_blocks(
        doc,
        [
            (
                {**block, "marker": "p"}
                if at
                and usj.is_type(blocks[at - 1], "chapter")
                and usj.paragraph(block) in ("m", "nb")
                else block
            )
            for at, block in enumerate(blocks)
        ],
    )


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


def exported(code: str, doc: Document, edition: Edition) -> str:
    """A document as PTXprint takes it: under its project id; its notes'
    margin origins without their chapter, which the chapter figure and running
    head supply, unless the verse's printed label names one, and bottom notes
    under their callers alone; its chapters opened in paragraphs of their own
    and its blank lines set; its chapter label, where the manifest asks for
    one, set once before its first chapter as PTXprint takes it; and its
    Greek and Hebrew tagged for their fonts.
    The edition's own pages are sent as the editor wrote them. A note at a
    verse that prints another label than its own is set under that label."""

    def bottom(item: Node) -> Node:
        if usj.is_type(item, "note", "ef"):
            return {
                **item,
                "content": [p for p in item["content"] if not usj.is_origin(p)],
            }
        return item

    def origin(item: Node) -> Node:
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
    if code not in edition.authored:
        doc = spaced(opened(doc))
    if code in edition.scripture:
        doc = labelled(doc, edition.policy.unit(code))
    # A unit printed from a file that holds another, or under an id that
    # PTXprint would take for its own front matter, is a unit of its own.
    doc = fonted(edition, code, usj.with_content(doc, content))
    return usj.serialize(usj.with_code(doc, code))


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


def export(edition: Edition, mode: str) -> list[tuple[str, str]]:
    """Every document of a view as USFM, by its project id, in order, with
    the notes edition/margin.json sets below the text so set: the page whose
    margin a note relieves is PTXprint's, so the placement is made for it
    alone, and the sample prints the notes of its chapters."""
    below = notes_below(edition)
    result = []
    for code, doc in pipeline.view(edition, mode):
        if code in below:
            here = below[code] & {
                note.get("x-key") for note in usj.notes_of(doc["content"])
            }
            doc = notes.set_below(doc, here)
        result.append((code, exported(code, doc, edition)))
    return result
