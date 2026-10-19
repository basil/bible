"""The edition's books, assembled from the sources' (edition/manifest.json):
a book's chapters selected from a file that holds two, Daniel grouped with
Susanna and Bel and the Dragon, its verses numbered as the Septuagint numbers
them where eBible numbers them otherwise (edition/versification.json,
docs/numbering.md), the label a verse prints set where it is not its own, and
each book under the edition's name and heading.

What the edition prints is read from the assembled books themselves: nothing
predicts which chapters and verses a manuscript decision or a grouping leaves.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Container, Iterator, Mapping
from typing import Literal

import bible.policy
import bible.references
from bible import scripture, usfm, usj, versification
from bible.checks import present, require
from bible.policy import source_id
from bible.policy_schema import Entry
from bible.references import Books, Verse
from bible.scripture import HIDDEN
from bible.usj import Content, Document, Node

# The paragraphs of prose that a continued paragraph can go on in.
PROSE_PARAGRAPHS = frozenset({"p", "m", "nb"})
NAME_MARKERS = {"title": "toc1", "short_title": "toc2", "abbreviation": "toc3"}
NAME_ATTRIBUTES = {"abbreviation": "abbr", "short_title": "short", "title": "long"}
# Daniel's parts that the Greek sets about it, each under a heading.
DANIEL = (("SUS", "0", "Susanna"), ("BEL", "13", "Bel and the Dragon"))
# The Song of the Three Children: the verse and words it is headed before,
# and the verse and words at which the narrative resumes after it.
SONG = (
    ("25", "Then Azarias stood up, and prayed on this manner"),
    ("91", "And Nabuchodonosor"),
)
SONG_TITLE = "The Song of the Three Children"


def colophon(doc: Document) -> Document:
    """Keep a source's terminal subscription outside its scripture verses."""
    blocks = doc["content"]
    last = blocks[-1]
    text = usj.text_of(last["content"])
    if usj.book_code(doc) == "ACT" and usj.paragraph(last) == "d":
        require(text == "The end of the Acts of the Apostles.", "Acts colophon changed")
    elif not (usj.paragraph(last) == "mi" and text.startswith("¶")):
        return doc
    at = len(blocks) - 1
    if at and usj.paragraph(blocks[at - 1]) == "b":
        at -= 1
    return usj.with_blocks(
        doc,
        [
            *blocks[:at],
            {
                "type": "sidebar",
                "marker": "esb",
                "category": "colophon",
                "content": [{**last, "marker": "p"}],
            },
        ],
    )


def divided_before(
    blocks: list[Node],
    boundary: tuple[str, str],
    inserted: list[Node],
    *,
    resumed: str | None = None,
) -> list[Node]:
    """A chapter's blocks with the inserted blocks set before a verse, whose
    words the boundary gives, the paragraph it stood in closing before them
    and resuming after, under its own marker or the one given."""
    number, opens = boundary
    found = [
        (index, n)
        for index, block in enumerate(blocks)
        if block["type"] == "para"
        for n, item in enumerate(block["content"])
        if usj.is_type(item, "verse") and item["number"] == number
    ]
    require(len(found) == 1, f"Daniel 3 boundary changed: verse {number}")
    index, n = found[0]
    block = blocks[index]
    require(
        usj.text_of(block["content"][n + 1 :]).startswith(opens),
        f"Daniel 3 boundary changed: verse {number}",
    )
    before: Node = {**block, "content": block["content"][:n]}
    after: Node = {
        **block,
        "marker": resumed or block["marker"],
        "content": block["content"][n:],
    }
    return [
        *blocks[:index],
        *([before] if n else []),
        *inserted,
        after,
        *blocks[index + 1 :],
    ]


def header(doc: Document, marker: str) -> str:
    """The words of a document's first header paragraph of a kind."""
    block = present(
        next((b for b in doc["content"] if usj.is_type(b, "para", marker)), None),
        f"Missing source {marker} marker",
    )
    return usj.text_of(block["content"]).strip()


def source_codes(entry: Entry) -> tuple[str, ...]:
    """The source files a unit is assembled from: its own, and for Daniel
    the files of the parts the Greek sets about it."""
    code = source_id(entry)
    if entry["id"] == "DAG":
        return (code, *(part for part, _, _ in DANIEL))
    return (code,)


def names(entry: Entry, doc: Document) -> dict[str, str]:
    """The contents title, running-head title, and abbreviation of an entry,
    from its header where the manifest gives none.

    The edition's names replace the source's. Front matter that the edition
    does not rename keeps its source names, as preparation prints them.
    """
    if "title" not in entry and "section" not in entry:
        return {field: header(doc, marker) for field, marker in NAME_MARKERS.items()}
    require(entry.get("title"), f"Missing title: {entry['id']}")
    return {
        "title": entry["title"],
        "short_title": entry.get("short_title") or header(doc, "toc2"),
        "abbreviation": entry.get("abbreviation") or header(doc, "toc3"),
    }


def books(
    policy: bible.policy.Policy, documents: Mapping[str, Document]
) -> bible.references.Books:
    """The edition's books, in its order, under their running-head names,
    the names by which one of a book's chapters is cited, and the
    abbreviations of both that citations print."""
    found = {
        unit["id"]: names(unit, documents[unit["id"]]) for unit in policy.scripture
    }
    return Books(
        ((code, name["short_title"]) for code, name in found.items()),
        _singly(policy, "cited_singly"),
        Books(
            ((code, name["abbreviation"]) for code, name in found.items()),
            _singly(policy, "abbreviated_singly"),
        ),
    )


def kjv_books(
    policy: bible.policy.Policy, texts: Mapping[str, str]
) -> bible.references.Books:
    """The King James Bible's books, in its order, under its own names for
    them, which a reader's other Bible has: read from every file's text by
    the read stage, which parses only the books the edition needs."""
    return Books(
        (
            (code, usfm.header(text, "toc2"))
            for code, text in texts.items()
            if re.search(r"^\\toc2\s", text, re.M)
        ),
        _singly(policy, "cited_singly"),
    )


def _singly(
    policy: bible.policy.Policy,
    field: Literal["cited_singly", "abbreviated_singly"],
) -> Iterator[tuple[str, str]]:
    """Each book's name, or its abbreviation, for one of its chapters."""
    return ((unit["id"], unit[field]) for unit in policy.scripture if field in unit)


def heading_lines(entry: Entry, found: Mapping[str, str]) -> list[tuple[str, str]]:
    """The mt lines printed over a book, as (marker, text) pairs.

    As in the Cambridge KJV, the heading is the contents title itself. The
    manifest's optional "heading" says how to break it into lines and which
    line is the main one; without it the whole title is one mt1 line. The
    edition sets its titles in two sizes, so a line is mt1 or mt2, never mt3.
    """
    lines = entry.get("heading", (("mt1", found["title"]),))
    require(
        all(
            len(line) == 2
            and line[0] in ("mt1", "mt2")
            and isinstance(line[1], str)
            and line[1].strip() == line[1] != ""
            for line in lines
        )
        and sum(marker == "mt1" for marker, _ in lines) == 1,
        f"Invalid heading: {entry['id']}",
    )
    require(
        " ".join(text for _, text in lines) == found["title"],
        f"Heading lines do not spell the contents title: {entry['id']}",
    )
    # One line can only be the whole title as mt1, which is the default.
    require(
        "heading" not in entry or len(lines) > 1,
        f"Heading that changes nothing: {entry['id']}",
    )
    return [(marker, text) for marker, text in lines]


def named(entry: Entry, doc: Document) -> Document:
    """A document with the edition's names and heading in place of the source's."""
    found = names(entry, doc)
    replacements = {
        "h": found["short_title"],
        **{marker: found[field] for field, marker in NAME_MARKERS.items()},
    }
    blocks, seen = [], set()
    for index, block in enumerate(doc["content"]):
        if block["type"] == "chapter":
            blocks += doc["content"][index:]
            break
        marker = block.get("marker")
        if marker in replacements:
            blocks.append({**block, "content": [replacements[marker]]})
            seen.add(marker)
        elif marker == "mt1":
            blocks += [usj.para(m, value) for m, value in heading_lines(entry, found)]
            seen.add(marker)
        elif marker not in ("mt2", "mt3"):
            # The whole heading is replaced, so the source's subtitle lines go.
            blocks.append(block)
    require(
        seen == {*replacements, "mt1"},
        f"Missing book header fields: {entry['id']}: {sorted(seen)}",
    )
    return usj.with_blocks(doc, blocks)


def chapters_of(doc: Document) -> tuple[list[Node], list[list[Node]]]:
    """A document's blocks before its first chapter, and each chapter's blocks."""
    starts = [i for i, block in enumerate(doc["content"]) if block["type"] == "chapter"]
    require(bool(starts), f"Source has no chapters: {usj.book_code(doc)}")
    return doc["content"][: starts[0]], [
        doc["content"][a:b] for a, b in zip(starts, [*starts[1:], len(doc["content"])])
    ]


def relabelled(
    blocks: list[Node], number: int | str, pubnumber: str | None = None
) -> list[Node]:
    """A chapter's blocks under another number, and the one it prints if
    that is another again."""
    chapter, *rest = blocks
    head: Node = {**chapter, "number": str(number)}
    if pubnumber is not None:
        head["pubnumber"] = pubnumber
    return [head, *rest]


def daniel(doc: Document, brenton: Mapping[str, Document]) -> Document:
    """Daniel with Susanna before it and Bel and the Dragon after, each a
    chapter that prints no number under its heading, and the Song of the Three
    Children headed where it begins."""
    header, chapters = chapters_of(doc)
    require(len(chapters) == 12, "Daniel source boundaries changed")
    parts = {}
    for code, number, title in DANIEL:
        _, found = chapters_of(brenton[code])
        require(len(found) == 1, "Daniel source boundaries changed")
        chapter, *body = relabelled(found[0], number, pubnumber=HIDDEN)
        parts[code] = [chapter, usj.para("cl", title), *body]
    (opening, ending), third = SONG, chapters[2]
    # The paragraph the Song's first verse stood in closes before its heading,
    # and the unheaded return to Daniel's narrative closes the addition, at
    # the same level as that heading.
    third = divided_before(third, opening, [usj.para("s1", SONG_TITLE)], resumed="p")
    chapters[2] = divided_before(third, ending, [usj.para("sd1")])
    blocks = [*header, *parts["SUS"], *(b for c in chapters for b in c), *parts["BEL"]]
    return usj.with_blocks(doc, blocks)


@functools.cache
def verse_at(code: str, chapter: int | None, number: str) -> Verse:
    """The verse a marker numbers in its chapter."""
    return bible.references.verse_at(
        code, f"{present(chapter, 'Verse before a chapter')}:{number}"
    )


def markers(doc: Document) -> list[tuple[Verse, int, int]]:
    """Every verse marker of a book, with its block and its place in it."""
    code = usj.book_code(doc)
    found = []
    chapter: int | None = None
    for b, block in enumerate(doc["content"]):
        if block["type"] == "chapter":
            chapter = int(block["number"])
        elif block["type"] == "para":
            for i, item in enumerate(block["content"]):
                if usj.is_type(item, "verse"):
                    found.append((verse_at(code, chapter, item["number"]), b, i))
    return found


def divided(
    doc: Document, division: versification.Break, placed: Container[int]
) -> tuple[Document, dict[int, Verse]]:
    """A book with the words of some verses divided again, each part opening
    at the words its decision gives, and each new marker by its printed verse.

    The first part keeps the first marker, and must open where it stands; no
    part opens inside a character style.
    """
    first_verse = division.source[0]
    every = markers(doc)
    # A marker another division set is already printed, not eBible's.
    places = [
        (v, b, i)
        for v, b, i in every
        if id(doc["content"][b]["content"][i]) not in placed
    ]
    names = [v for v, _, _ in places]
    at = names.index(first_verse) if first_verse in names else -1
    after = at + len(division.source)
    require(
        at >= 0 and tuple(names[at:after]) == division.source,
        f"Verses to divide not found together: {first_verse}",
    )
    start, last = places[at][1:], places[after - 1][1:]
    # The verses end at the next marker, whichever division set it.
    end: tuple[int, int | None] = next(
        (place[1:] for place in every if place[1:] > last),
        (len(doc["content"]) - 1, None),
    )
    # The words of the verses, paragraph by paragraph, from their first marker
    # to the marker after them, without the headings set among them.
    spans: dict[int, tuple[int, str]] = {}
    for b in range(start[0], end[0] + 1):
        block = doc["content"][b]
        if block["type"] != "para" or block["marker"] in usj.HEADINGS:
            continue
        words_of = block["content"]
        text = usj.text_of(words_of)
        low = len(usj.text_of(words_of[: start[1]])) if b == start[0] else 0
        high = len(usj.text_of(words_of[: end[1]])) if b == end[0] else len(text)
        spans[b] = (low, text[low:high])
    found: list[tuple[int, int]] = []
    for verse, words in division.printed:
        # The words as words of their own, not the end of a longer one.
        opening = re.compile(
            (r"(?<!\w)" if re.match(r"\w", words) else "")
            + re.escape(words)
            + (r"(?!\w)" if re.search(r"\w$", words) else "")
        )
        hits = [
            (b, low + m.start())
            for b, (low, text) in spans.items()
            for m in opening.finditer(text)
        ]
        require(len(hits) == 1, f"Words that don't open one place: {verse}: {words!r}")
        found.extend(hits)
    low, text = spans[start[0]]
    require(
        found[0] == (start[0], low + len(text) - len(text.lstrip()))
        and found == sorted(found)
        and len(set(found)) == len(found),
        f"Verse division out of order: {first_verse}",
    )
    require(
        [v for v, _ in division.printed] != list(division.source)
        or found
        != [
            (b, len(usj.text_of(doc["content"][b]["content"][:i])))
            for _, b, i in places[at:after]
        ],
        f"Verse division that changes nothing: {first_verse}",
    )
    old = {id(doc["content"][b]["content"][i]) for _, b, i in places[at + 1 : after]}
    # An eBible marker that stands where a part opens: the part's marker takes
    # its place, so that a note closing the verse before stays in it.
    standing = {
        (b, len(usj.text_of(doc["content"][b]["content"][:i]))): (
            doc["content"][b]["content"][i]
        )
        for _, b, i in places[at + 1 : after]
    }
    kept = doc["content"][start[0]]["content"][start[1]]
    marked = {id(kept): division.printed[0][0]}
    blocks = list(doc["content"])
    for b in spans:
        content: Content = list(blocks[b]["content"])
        for (where, offset), (verse, _) in reversed(
            list(zip(found[1:], division.printed[1:]))
        ):
            if where == b:
                node: Node = {
                    "type": "verse",
                    "marker": "v",
                    "number": f"{verse.number}{verse.letter}",
                }
                marked[id(node)] = verse
                if (b, offset) in standing:
                    replaced = standing[(b, offset)]
                    content = [node if item is replaced else item for item in content]
                    continue
                # A note at the words glosses the first of them, so it opens
                # the verse too.
                content = usj.inserted(content, offset, [node], after_notes=False)
        # A verse joined to the one before is parted from it by a space,
        # which eBible's line break gave; the paragraph's spaces are then as
        # the parser leaves them.
        kept_items: Content = []
        for item in content:
            if id(item) not in old:
                kept_items.append(item)
            elif kept_items:
                kept_items.append(" ")
        blocks[b] = {**blocks[b], "content": usj.trimmed(usj.joined(kept_items))}
    return usj.with_blocks(doc, blocks), marked


def renumbered(
    code: str, doc: Document, policy: bible.policy.Policy, *, words: bool = True
) -> Document:
    """A book under the edition's numbers where they are not eBible's: its
    verses divided anew and relabelled, and each chapter begun before its
    first verse, a paragraph divided there if need be.

    A chapter begun at a relabelled verse that began none in eBible names the
    words it opens with, as a division does. Of another text numbered like
    eBible, as the Updated Brenton, only the labels are read: a verse divided
    is its first part, and verses joined are the first of them.
    """
    numbering = versification.renumbering(code, policy=policy)
    if not numbering.labels and not numbering.breaks:
        return doc
    before: dict[str, list[str]] = {}
    marked: dict[int, Verse] = {}
    crossing: set[Verse] = set()
    if words:
        before = usj.inventory(doc)
        labels: Mapping[Verse, Verse] = numbering.labels
        for division in numbering.breaks:
            doc, placed = divided(doc, division, marked)
            marked.update(placed)
    else:
        labels = numbering.relabelled()
        # Words that a division sets in another chapter stay in their own,
        # so a poem's lines could not be placed in them.
        crossing = {
            v
            for division in numbering.breaks
            if len({t.chapter for t, _ in division.printed}) > 1
            for v in division.source
        }
    blocks: list[Node] = []
    held: list[Node] = []
    pending: Node | None = None
    chapter: int | None = None
    current: int | None = None
    seen: set[Verse] = set()
    used: set[Verse] = set()
    continued = False
    opened: set[Verse] = set()
    # The verse whose words run on into a paragraph that opens without a number.
    running: Verse | None = None

    def unpoetic(block: Node, source: Verse | None) -> None:
        """Refuse a poem's line that holds words a division sets in another
        chapter."""
        require(
            source not in crossing or not block["marker"].startswith("q"),
            f"Verse divided across a chapter in a poem of a text numbered "
            f"like eBible: {source}",
        )

    def close(block: Node, content: Content) -> None:
        """Set a paragraph down, or run it on in the paragraph before where it
        went on across a chapter break the edition does not make, its spaces
        then as the parser leaves them."""
        nonlocal continued
        if continued:
            last = blocks.pop()
            block, content = last, usj.trimmed([*last["content"], " ", *content])
            continued = False
        blocks.append({**block, "content": usj.joined(content)})

    for block in doc["content"]:
        if block["type"] == "chapter":
            if pending is not None:
                blocks.append(pending)
            blocks.extend(held)
            held.clear()
            pending, chapter = block, int(block["number"])
            continue
        if crossing and block["type"] == "para":
            first = next(
                (
                    n
                    for n, item in enumerate(block["content"])
                    if usj.is_type(item, "verse")
                ),
                len(block["content"]),
            )
            if usj.text_of(block["content"][:first]).strip():
                unpoetic(block, running)
        if block["type"] != "para" or not any(
            usj.is_type(item, "verse") for item in block["content"]
        ):
            (held if pending is not None else blocks).append(block)
            continue
        content: list[str | Node] = []
        items = block["content"]
        for n, item in enumerate(items):
            if not usj.is_type(item, "verse"):
                content.append(item)
                continue
            source = running = verse_at(code, chapter, item["number"])
            unpoetic(block, source)
            if id(item) in marked:
                # A division's marker, by its printed verse: no relabelling
                # applies to it.
                target = marked[id(item)]
            else:
                target = labels.get(source, source)
                if source in labels:
                    used.add(source)
            if target in seen:
                require(not words, f"Verse printed twice: {target}")
                # A verse joined to the one before is parted from it by a
                # space, as a division parts it.
                if content:
                    content.append(" ")
                continue
            seen.add(target)
            if target.chapter != current:
                if (
                    words
                    and pending is None
                    and source in labels
                    and id(item) not in marked
                ):
                    opens = numbering.opens.get(target)
                    require(
                        opens is not None
                        and usj.text_of(items[n + 1 :]).lstrip().startswith(opens),
                        f"{code} chapter {target.chapter} boundary changed",
                    )
                    opened.add(target)
                head: Node = {
                    **(pending or {"type": "chapter", "marker": "c"}),
                    "number": str(target.chapter),
                }
                if usj.text_of(content).strip() or usj.notes_of(content):
                    close(block, content)
                    content = []
                blocks.extend([head, *held])
                held.clear()
                current = target.chapter
            elif pending is not None:
                # A paragraph that went on across a chapter break the edition
                # does not make goes on in the paragraph before it.
                continued = (
                    not held
                    and block["marker"] == "nb"
                    and not usj.text_of(content).strip()
                    and bool(blocks)
                    and blocks[-1]["type"] == "para"
                    and blocks[-1]["marker"] in PROSE_PARAGRAPHS
                )
                blocks.extend(held)
                held.clear()
            pending = None
            content.append({**item, "number": f"{target.number}{target.letter}"})
        close(block, content)
    if pending is not None:
        blocks.append(pending)
    blocks.extend(held)
    doc = usj.with_blocks(doc, blocks)
    if not words:
        return doc
    require(
        used == set(labels) and opened == set(numbering.opens),
        f"{code} relabelling that matches nothing: "
        f"{sorted(map(str, (set(labels) - used) | (set(numbering.opens) - opened)))}",
    )
    expected: dict[str, list[str]] = {}
    divisions = {d.source[0]: d for d in numbering.breaks}
    joined = {v for d in numbering.breaks for v in d.source[1:]}
    for number, verses in before.items():
        for label in verses:
            verse = verse_at(code, int(number), label)
            if verse in joined:
                continue
            found_division = divisions.get(verse)
            for target in (
                [v for v, _ in found_division.printed]
                if found_division
                else [labels.get(verse, verse)]
            ):
                expected.setdefault(str(target.chapter), []).append(
                    f"{target.number}{target.letter}"
                )
    found = usj.inventory(doc)
    first = int(next(iter(found)))
    require(
        list(found.items()) == list(expected.items())
        and list(found) == [str(c) for c in range(first, first + len(found))],
        f"Wrong {code} verse labels after renumbering",
    )
    return doc


def scripture_unit(
    entry: Entry,
    brenton: Mapping[str, Document],
    kjv: Mapping[str, Document],
    policy: bible.policy.Policy,
) -> Document:
    """One of the edition's books, from its source's chapters, before its
    name and its notes."""
    code = entry["id"]
    doc = (brenton if entry["source"] == "brenton" else kjv)[source_id(entry)]
    if "chapters" in entry:
        # Part of a source file that holds more than one book, numbered from 1.
        first, last = entry["chapters"]
        header, chapters = chapters_of(doc)
        require(
            0 < first <= last <= len(chapters),
            f"Manifest chapters outside the source: {code}",
        )
        doc = usj.with_blocks(
            doc,
            [
                *header,
                *(
                    block
                    for n, chapter in enumerate(chapters[first - 1 : last], 1)
                    for block in relabelled(chapter, n)
                ),
            ],
        )
        require(
            list(usj.inventory(doc)) == [str(c) for c in range(1, last - first + 2)],
            f"Wrong chapter selection: {code}",
        )
    elif code == "DAG":
        doc = daniel(doc, brenton)
        require(
            list(usj.inventory(doc)) == [str(i) for i in range(14)],
            "Wrong chapter grouping: DAG",
        )
    # A book printed from a file that holds another is a unit of its own.
    doc = renumbered(code, usj.with_code(doc, code), policy)
    if code == "SIR":
        header, chapters = chapters_of(doc)
        chapter, title, *paragraphs = chapters[0]
        if paragraphs and usj.is_type(paragraphs[-1], "para", "b"):
            require(
                not paragraphs[-1]["content"], "Text in Sirach's closing blank line"
            )
            paragraphs = paragraphs[:-1]
        require(
            chapter["number"] == "0"
            and usj.paragraph(title) == "d"
            and all(usj.is_type(p, "para", "p") for p in paragraphs)
            and list(usj.inventory(usj.document(chapters[0])).items())
            == [("0", ["1"])],
            "Sirach Prologue title changed",
        )
        introduction: list[Node] = [{**title, "marker": "imt1"}]
        for paragraph in paragraphs:
            introduction.append(
                {
                    **paragraph,
                    "marker": "ip",
                    "content": [
                        n for n in paragraph["content"] if not usj.is_type(n, "verse")
                    ],
                }
            )
        doc = usj.with_blocks(
            doc, [*header, *introduction, *(b for c in chapters[1:] for b in c)]
        )
    return printed(code, without_stubs(code, doc, policy), policy)


def unit_verse(policy: bible.policy.Policy, code: str, reference: str) -> Verse | None:
    """A verse of one of Brenton's files, by eBible's reference, in the unit
    that prints its chapter, still numbered as eBible numbers it; none where
    no unit prints it."""
    for part, number, _ in DANIEL:
        if code == part:
            return bible.references.verse_at(
                "DAG", f"{number}:{reference.split(':')[1]}"
            )
    chapter, _, verse = reference.partition(":")
    for unit in policy.scripture:
        if source_id(unit) != code or unit["source"] != "brenton":
            continue
        first, last = unit.get("chapters", (1, 10**6))
        if first <= int(chapter) <= last:
            return bible.references.verse_at(
                unit["id"], f"{int(chapter) - first + 1}:{verse}"
            )
    return None


def printed(code: str, doc: Document, policy: bible.policy.Policy) -> Document:
    """A book with the label each verse prints where it is not the verse's
    own (edition/versification.json): a passage the Greek sets in another
    order than the Hebrew under the Hebrew's numbers (`relocations`), its
    first verse with its chapter, as is the verse after it back in its own
    chapter; and no label for a verse the Greek prints unnumbered
    (`unnumbered`), nor for a chapter all of whose verses are unnumbered."""
    relocations = versification.relocations(code, policy=policy)
    unnumbered = {
        reference: entry
        for reference, entry in policy.versification.get("unnumbered", {}).items()
        if not isinstance(entry, str) and bible.references.book_of(reference) == code
    }
    if not relocations and not unnumbered:
        return doc
    order = [verse for verse, _, _ in markers(doc)]
    labels: dict[Verse, str] = {}
    passages: list[list[Verse]] = []
    for reference, relocation in relocations.items():
        theirs = bible.references.parse_passage(reference).verses
        first = bible.references.parse_verse(relocation["to"])
        require(first in order, f"Relocated passage not printed: {reference}")
        at = order.index(first)
        ours = order[at : at + len(theirs)]
        require(
            len(ours) == len(theirs) and all(v.chapter == first.chapter for v in ours),
            f"Relocated passage runs past its chapter: {reference}",
        )
        for n, (verse, hebrew) in enumerate(zip(ours, theirs)):
            require(verse not in labels, f"Verse printed under two labels: {verse}")
            labels[verse] = hebrew.label if n == 0 else str(hebrew.number)
        passages.append(ours)
    for ours in passages:
        at = order.index(ours[-1]) + 1
        if at < len(order) and order[at].chapter == ours[0].chapter:
            labels.setdefault(order[at], order[at].label)
    for reference, entry in unnumbered.items():
        require(
            bool(entry.get("why")),
            f"Unnumbered verse without its reason: {reference}",
        )
        verse = bible.references.parse_verse(reference)
        require(verse in order, f"Unnumbered verse not printed: {reference}")
        require(verse not in labels, f"Verse printed under two labels: {verse}")
        labels[verse] = HIDDEN
    hidden = {v.chapter for v in order} - {
        v.chapter for v in order if labels.get(v) != HIDDEN
    }
    blocks: list[Node] = []
    chapter: int | None = None
    for block in doc["content"]:
        if block["type"] == "chapter":
            chapter = int(block["number"])
            if chapter in hidden:
                block = {**block, "pubnumber": HIDDEN}
        elif block["type"] == "para":
            content: Content = []
            for item in block["content"]:
                if (
                    usj.is_type(item, "verse")
                    and (shown := labels.get(verse_at(code, chapter, item["number"])))
                    is not None
                ):
                    item = {**item, "pubnumber": shown}
                content.append(item)
            block = {**block, "content": content}
        blocks.append(block)
    return usj.with_blocks(doc, blocks)


def without_stubs(code: str, doc: Document, policy: bible.policy.Policy) -> Document:
    """A book without a chapter its transcription numbers but gives no words,
    where the edition's versification says the source has none (as eBible's
    empty Proverbs 30): the chapter and its one empty verse go, with any
    remark of the transcriber's in it. A stub that has words is refused."""
    for reference, entry in policy.versification.get("stubs", {}).items():
        if isinstance(entry, str) or bible.references.book_of(reference) != code:
            continue
        require(bool(entry.get("why")), f"Stub without its reason: {reference}")
        address = reference.split()[1]
        verses = scripture.verses(doc)
        require(address in verses, f"Stub verse missing: {reference}")
        verse = verses[address]
        require(not scripture.plain(verse.text), f"Stub verse has words: {reference}")
        chapter, number = address.split(":")
        require(
            usj.inventory(doc).get(chapter) == [number],
            f"Stub verse is not its chapter's only verse: {reference}",
        )
        held = {block for block, *_ in verse.parts}
        blocks = [
            block
            for index, block in enumerate(doc["content"])
            if index not in held
            and not (block["type"] == "chapter" and block["number"] == chapter)
        ]
        doc = usj.with_blocks(doc, blocks)
    return doc


def check_divided(
    policy: bible.policy.Policy, documents: Mapping[str, Mapping[str, Document]]
) -> None:
    """A source divided between units must be printed whole, each chapter
    once; the sources' documents by their family, as read."""
    divided: dict[tuple[str, str], list[str]] = {}
    for unit in policy.scripture:
        if "chapters" in unit:
            first, last = unit["chapters"]
            divided.setdefault((unit["source"], source_id(unit)), []).extend(
                str(c) for c in range(first, last + 1)
            )
    for (source, code), chapters in divided.items():
        found = list(usj.inventory(documents[source][code]))
        require(chapters == found, f"Divided source not printed whole: {source}/{code}")
