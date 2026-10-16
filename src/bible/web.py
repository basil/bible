"""Prepared scripture as USJ for the website, without PTXprint's font runs."""

import shutil
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NotRequired, TypedDict

from fontTools.ttLib import TTFont

from bible import (
    assembly,
    export,
    files,
    paths,
    pipeline,
    references,
    scripture,
    usj,
    versification,
)
from bible.checks import present, require

FONT_STYLES = ("Regular", "Italic", "Bold", "BoldItalic")


def write_fonts(directory: Path) -> None:
    """Wrap the complete installed faces in WOFF.
    The command checks the image before it prepares the edition."""
    installed = paths.FONTS / "olebfont"
    for style in FONT_STYLES:
        source = installed / f"OLEBFont-{style}.otf"
        require(
            source.is_file(),
            f"Missing installed font input {source.name}; run make bootstrap",
        )
        directory.mkdir(parents=True, exist_ok=True)
        with TTFont(source, recalcTimestamp=False, recalcBBoxes=False) as font:
            font.flavor = "woff"
            font.save(directory / f"OLEBFont-{style}.woff")


# The headings that stand for an unnumbered chapter's number: a section's,
# as Susanna's, or a title's, as Sirach's Prologue's.
TITLES = ("s1", "d")


def label(chapter: usj.Node, blocks: list[usj.Node]) -> str:
    """The number a chapter prints, or the heading that stands for it."""
    shown = chapter.get("pubnumber", chapter["number"])
    if shown != scripture.HIDDEN:
        return shown
    heading = present(
        next((block for block in blocks if block.get("marker") in TITLES), None),
        f"Unnumbered chapter has no heading: {chapter}",
    )
    return scripture.plain(usj.text_of(heading.get("content", [])))


class Span(TypedDict):
    text: str
    changed: bool


class Compared(TypedDict):
    reference: str
    kjvReference: str
    kjv: list[Span]
    oleb: list[Span]
    osb: NotRequired[list[Span]]


def spans(text: str, phrases: Sequence[str]) -> list[Span]:
    """A quotation in runs, each marked whether a highlighted phrase: a phrase
    must occur exactly once, and takes the punctuation that closes it."""
    ranges = []
    for phrase in phrases:
        start = text.find(phrase)
        require(
            bool(phrase) and start >= 0 and text.find(phrase, start + 1) < 0,
            f"Comparison highlight must occur exactly once: {phrase}",
        )
        end = start + len(phrase)
        while end < len(text) and unicodedata.category(text[end]).startswith("P"):
            end += 1
        ranges.append((start, end))
    result: list[Span] = []
    at = 0
    for start, end in sorted(ranges):
        require(start >= at, f"Comparison highlights overlap: {phrases}")
        if start > at:
            result.append({"text": text[at:start], "changed": False})
        result.append({"text": text[start:end], "changed": True})
        at = end
    if at < len(text):
        result.append({"text": text[at:], "changed": False})
    return result


def comparisons(
    edition: pipeline.Edition, documents: Mapping[str, usj.Document]
) -> list[Compared]:
    """The comparison page's passages: each quoted in full from the edition
    and from the King James Bible at the place the edition's verses hold
    there, both named as the edition cites them, and from the editor's OSB
    quotation where the decision gives one, each with its highlights."""
    policy = edition.policy
    ours, theirs = edition.books, edition.read.kjv_books
    kjv: dict[str, dict[str, scripture.Verse]] = {}
    result: list[Compared] = []
    for entry in policy.comparisons["passages"]:
        passage = references.parse_passage(entry["passage"])
        versification.require_own_labels(
            passage.verses, f"Comparison {entry['passage']}", policy=policy
        )
        verses = scripture.verses(documents[passage.first.book])
        placed = list(
            dict.fromkeys(
                verse
                for ours_verse in passage.verses
                for verse in versification.to_kjv(ours_verse, policy=policy)
            )
        )
        require(placed, f"No King James counterpart: {entry['passage']}")
        for verse in placed:
            if verse.book not in kjv:
                kjv[verse.book] = scripture.verses(
                    present(
                        edition.read.kjv.get(verse.book),
                        f"King James book not read: {verse.book}",
                    )
                )
        quote = " ".join(
            scripture.plain(
                present(verses.get(v.label), f"No verse {v} to compare").text
            )
            for v in passage.verses
        )
        counterpart = " ".join(
            scripture.plain(
                present(kjv[v.book].get(v.label), f"No King James verse {v}").text
            )
            for v in placed
        )
        compared: Compared = {
            "reference": references.EDITION.listed([passage], ours),
            "kjvReference": references.EDITION.listed(references.runs(placed), theirs),
            "kjv": spans(counterpart, entry["kjv"]),
            "oleb": spans(quote, entry["oleb"]),
        }
        if "osb" in entry:
            compared["osb"] = spans(entry["osb"]["text"], entry["osb"]["highlights"])
        result.append(compared)
    return result


def write(edition: pipeline.Edition, directory: Path) -> None:
    """Write one document per chapter, each opening with its book, their
    ordered chapter inventory, with the book's names and whether a heading
    stands for a chapter's number, and the comparison page's passages."""
    if directory.exists():
        shutil.rmtree(directory)
    write_fonts(directory / "fonts")
    documents = dict(pipeline.view(edition, "pdf"))
    files.write_json(directory / "comparisons.json", comparisons(edition, documents))
    books = []
    for unit in edition.policy.scripture:
        code = unit["id"]
        doc = export.with_printed_origins(documents[code])
        (book, *header), parts = pipeline.headed_chapters(doc)
        # A book's introduction is a note on its opening; before the first
        # chapter stand only the book's names, which the manifest carries.
        require(
            book["type"] == "book"
            and all(node.get("marker") in usj.BOOK_PARAGRAPHS for node in header),
            f"Document does not open with its book and its names alone: {code}",
        )
        names = {
            node["marker"]: usj.text_of(node.get("content", [])) for node in header
        }
        chapters = []
        for blocks in parts:
            chapter = next(block for block in blocks if block["type"] == "chapter")
            number = chapter["number"]
            chapters.append(
                {
                    "number": number,
                    "label": label(chapter, blocks),
                    "titled": chapter.get("pubnumber") == scripture.HIDDEN,
                    "verses": edition.inventory[code][number],
                }
            )
            files.write_json(
                directory / "books" / code / f"{number}.json",
                usj.with_blocks(doc, [book, *blocks]),
            )
        books.append(
            {
                "id": code,
                "section": unit["section"],
                "title": names[assembly.NAME_MARKERS["title"]],
                "short": names[assembly.NAME_MARKERS["short_title"]],
                "chapters": chapters,
            }
        )
    files.write_json(directory / "manifest.json", {"books": books})
