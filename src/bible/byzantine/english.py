"""The English texts, read through the USJ document model.

The pinned KJV (Cambridge Paragraph Bible, eBible) is the text being edited;
the Revised Version of 1881, the ASV of 1901, and Boyd's ASV conformed to
RP2018 are witnesses. Every reader checks its verse inventory.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from html import escape
from typing import TypedDict, cast

from lxml import html

from bible import scripture, usj
from bible.byzantine import BOOKS
from bible.checks import CheckFailed, require
from bible.sources import Content


class Citation(TypedDict):
    """A verse's words with single spaces, and the spans of its supplied
    words in them."""

    text: str
    supplied: list[tuple[int, int]]


def verses_of(documents: Mapping[str, usj.Document]) -> dict[str, scripture.Verse]:
    return {
        f"{book} {ref}": verse
        for book, document in documents.items()
        for ref, verse in scripture.verses(document).items()
    }


MARKUP_TAGS = {
    "add": "i",
    "it": "i",
    "+add": "i",
    "+it": "i",
    "fqa": "i",
    "bd": "b",
    "+bd": "b",
}


def usj_markup(content: Iterable[str | usj.Node], *, italic: bool = False) -> str:
    """Display source italics and emphasis without serializing USFM or notes."""
    result = ""
    for node in content:
        if isinstance(node, str):
            result += escape(node)
        elif node.get("type") != "note":
            tag = MARKUP_TAGS.get(node.get("marker", ""))
            value = usj_markup(node.get("content", []), italic=italic or tag == "i")
            if italic and tag == "i":
                tag = None
            result += f"<{tag}>{value}</{tag}>" if tag else value
    return result


def verse_markup(document: usj.Document, verse: scripture.Verse) -> str:
    return " ".join(
        usj_markup(document["content"][block]["content"][lo:hi])
        for block, lo, hi, _ in verse.parts
    ).strip()


def supplied_spans(
    document: usj.Document, verse: scripture.Verse
) -> list[tuple[int, int, str]]:
    """Read supplied words at their original verse offsets, excluding notes."""
    found: list[tuple[int, int, str]] = []

    def walk(
        content: Iterable[str | usj.Node], offset: int, supplied: bool = False
    ) -> int:
        for item in content:
            if isinstance(item, str):
                if supplied and item:
                    found.append((offset, offset + len(item), item))
                offset += len(item)
            elif item.get("type") != "note":
                offset = walk(
                    item.get("content", []),
                    offset,
                    supplied or item.get("marker") == "add",
                )
        return offset

    offset = 0
    for block, lo, hi, length in verse.parts:
        content = document["content"][block]["content"][lo:hi]
        require(
            usj.text_of(content) == verse.text[offset : offset + length],
            f"Supplied-word context differs at {verse.reference}",
        )
        end = walk(content, offset)
        require(
            end == offset + length, f"Supplied-word offsets differ at {verse.reference}"
        )
        offset = end + 1
    return found


def citation_metadata(document: usj.Document, verse: scripture.Verse) -> Citation:
    """Normalize verse words and their USJ supplied spans together.

    A space is supplied only between two supplied words, so a span never
    begins or ends with the space a source keeps inside its markup (the RV's
    `\\add of God \\add*in`)."""
    supplied = [False] * len(verse.text)
    for lo, hi, _ in supplied_spans(document, verse):
        supplied[lo:hi] = [True] * (hi - lo)
    chunks: list[str] = []
    flags: list[bool] = []
    previous: int | None = None
    for match in re.finditer(r"\S+", verse.text):
        if previous is not None:
            flags.append(
                flags[-1]
                and supplied[match.start()]
                and all(supplied[previous : match.start()])
            )
        chunks.append(match.group())
        flags.extend(supplied[match.start() : match.end()])
        previous = match.end()
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for i, marked in enumerate([*flags, False]):
        if marked and start is None:
            start = i
        elif not marked and start is not None:
            spans.append((start, i))
            start = None
    return {"text": " ".join(chunks), "supplied": spans}


def without_subscriptions(document: usj.Document) -> usj.Document:
    """Subscriptions are matter, not the epistle's last verse."""
    return usj.with_blocks(
        document,
        [
            n
            for n in document["content"]
            if not (n.get("type") == "sidebar" and n.get("category") == "colophon")
        ],
    )


def kjv(
    documents: Mapping[str, usj.Document],
) -> tuple[
    dict[str, usj.Document], dict[str, scripture.Verse], dict[str, list[usj.Node]]
]:
    """The King James books without their subscriptions, which are matter and
    not the epistles' last verses, and the blocks taken off each: the
    promotion puts them back after the verses are edited."""
    clean: dict[str, usj.Document] = {}
    taken: dict[str, list[usj.Node]] = {}
    for book in BOOKS:
        document = documents[book]
        kept = without_subscriptions(document)
        removed = len(document["content"]) - len(kept["content"])
        if removed:
            tail = document["content"][-removed:]
            require(
                all(n.get("type") == "sidebar" for n in tail),
                f"{book}: subscription is not the book's close",
            )
            taken[book] = tail
        clean[book] = kept
    verses = verses_of(clean)
    require(
        len(verses) == 7957 and len(taken) == 15,
        f"KJV inventory: {len(verses)} verses, {len(taken)} subscriptions",
    )
    return clean, verses, taken


def surface_words(source: str) -> str:
    """USFM without its lexical metadata, which the document model excludes."""
    return re.sub(r"\\(\+?)w ([^\\|]*)\|[^\\]*\\\1w\*", r"\2", source)


def surface_usfm(
    folder: Content, name: str, source: Callable[[str], str] = lambda text: text
) -> tuple[dict[str, usj.Document], dict[str, scripture.Verse]]:
    """Read a pinned USFM translation; discard lexical metadata, preserving
    surface words."""
    documents: dict[str, usj.Document] = {}
    for book in BOOKS:
        paths = list(folder.glob(f"*-{book}*.usfm"))
        require(len(paths) == 1, f"Expected one pinned {name} book: {book}")
        text = paths[0].read_text(encoding="utf-8-sig")
        # Unrecognized or malformed metadata still reaches the strict parser.
        documents[book] = usj.parse(source(surface_words(text)))
    verses = verses_of(documents)
    require(
        len(verses) == 7957
        and sum(not verse.text.strip() for verse in verses.values()) == 16,
        f"{name} inventory: expected 7,957 markers with sixteen empty verses",
    )
    return documents, verses


def rv(folder: Content) -> tuple[dict[str, usj.Document], dict[str, scripture.Verse]]:
    """Read the RV of 1881."""
    return surface_usfm(folder, "RV")


# Paragraph styles of the ASV that the production model lacks. Only the
# layout changes; every word and verse marker reaches the strict parser.
ASV_PARAGRAPHS = {"q2": "q1", "q3": "q1", "pi1": "p"}


def asv(
    folder: Content,
) -> tuple[dict[str, usj.Document], dict[str, scripture.Verse]]:
    """Read the 1901 ASV, the base of Boyd's revision, for its words."""
    return surface_usfm(
        folder,
        "ASV",
        lambda text: re.sub(
            r"\\(q2|q3|pi1)(?=\s)", lambda m: f"\\{ASV_PARAGRAPHS[m[1]]}", text
        ),
    )


def boyd_paragraph(node: html.HtmlElement) -> usj.Node:
    """A closed HTML scripture paragraph, with verse numbers and supplied words.

    Navigation and matter are excluded by the chapter reader, not by deleting
    unfamiliar children here. Unknown scripture markup stops the reader.
    """
    marker = {"p": "p", "q": "q1", "m": "m", "mi": "mi", "nb": "nb"}.get(
        node.get("class")
    )
    if node.tag != "div" or marker is None:
        raise CheckFailed("Unknown Boyd scripture paragraph")

    def content(element: html.HtmlElement) -> usj.Content:
        items: usj.Content = []
        if element.text:
            items.append(re.sub(r"\s+", " ", element.text))
        for child in element:
            require(child.tag == "span", f"Unknown Boyd scripture child: {child.tag}")
            if child.get("class") == "verse":
                match = re.fullmatch(r"V([1-9]\d*)", child.get("id", ""))
                if not match or len(child) or child.text_content().strip() != match[1]:
                    raise CheckFailed("Malformed Boyd verse marker")
                items.append({"type": "verse", "marker": "v", "number": match[1]})
            elif child.get("class") == "add":
                items.append(usj.char("add", *content(child)))
            else:
                raise CheckFailed(f'Unknown Boyd scripture span: {child.get("class")}')
            if child.tail:
                items.append(re.sub(r"\s+", " ", child.tail))
        return items

    return usj.para(marker, *content(node))


def boyd_asv(
    folder: Content,
) -> tuple[dict[str, usj.Document], dict[str, scripture.Verse]]:
    """Read the 260 chapter pages of the February 2021 RP2018 revision."""
    documents = {
        book: usj.document(
            [{"type": "book", "marker": "id", "code": book, "content": []}]
        )
        for book in BOOKS
    }
    count = 0
    for path in folder.glob("*.htm"):
        match = re.fullmatch(r"([A-Z0-9]{3})(\d{2})", path.stem)
        if not match or match[1] not in documents:
            continue
        chapter = int(match[2])
        require(chapter >= 1, f"Invalid Boyd chapter: {path.name}")
        roots = cast(
            list[html.HtmlElement],
            html.fromstring(path.read_bytes()).xpath('//div[@class="main"]'),
        )
        require(len(roots) == 1, f"Expected one Boyd main region: {path.name}")
        root = roots[0]
        doc = documents[match[1]]
        doc["content"].append(
            {"type": "chapter", "marker": "c", "number": str(chapter)}
        )
        seen = 0
        for node in root:
            if node.tag == "div" and node.get("class") in {"p", "q", "m", "mi", "nb"}:
                doc["content"].append(boyd_paragraph(node))
                seen += len(node.xpath('.//span[@class="verse"]'))
            elif (
                node.tag == "div"
                and node.get("class")
                in {"mt", "mt2", "b", "chapterlabel", "footnote", "copyright"}
            ) or (node.tag == "ul" and node.get("class") == "tnav"):
                continue
            else:
                raise CheckFailed(
                    f'Unknown Boyd main block: {path.name}: {node.tag} {node.get("class")}'
                )
        require(
            seen == len(root.xpath('.//span[@class="verse"]')) and seen,
            f"Unconsumed Boyd verse markers: {path.name}",
        )
        count += 1
    verses = verses_of(documents)
    require(
        count == 260
        and len(verses) == 7953
        and not any(not verse.text.strip() for verse in verses.values()),
        f"Boyd ASV inventory: {count} chapters, {len(verses)} verses",
    )
    return documents, verses
