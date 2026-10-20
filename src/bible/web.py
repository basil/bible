"""Prepared scripture as USJ for the website, with the Greek and Hebrew
tagged for their fonts as the typesetter has them, the front matter the
book prints, the website-only numbering tables and textual variants, and
the fonts the edition is set in.
"""

import itertools
import shutil
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NotRequired, TypedDict

from fontTools.ttLib import TTFont

import bible.policy
from bible import (
    assembly,
    export,
    files,
    peripherals,
    pipeline,
    references,
    scripture,
    terminology,
    typeface,
    usj,
    versification,
)
from bible.byzantine.variants import Lane
from bible.checks import present, require


def font_file(face: Path) -> str:
    """The WOFF the website serves a face from, named as the face is."""
    return face.with_suffix(".woff").name


def font_face(face: Path) -> str:
    """The @font-face rule that declares a face under its family's name."""
    weight, slant = typeface.style(face)
    return (
        "@font-face {\n"
        f'  font-family: "{typeface.family(face)}";\n'
        f'  src: url("./{font_file(face)}") format("woff");\n'
        f"  font-weight: {weight};\n"
        f"  font-style: {slant};\n"
        "  font-display: swap;\n"
        "}\n"
    )


def font_stylesheet(faces: Sequence[Path]) -> str:
    """The stylesheet the website imports: every face installed for the
    edition, and the families to set the Latin, Greek and Hebrew in."""
    families = {
        "latin": typeface.family(typeface.faces(typeface.LATIN)[0]),
        "greek": typeface.greek_family(),
        "hebrew": typeface.family(typeface.HEBREW),
    }
    return (
        "/* The fonts the edition is set in, in print and here: written by the\n"
        "   build (bible.web) from the faces the image installed, never by hand. */\n"
        + "".join(font_face(face) for face in faces)
        + ":root {\n"
        + "".join(
            f'  --edition-font-{script}: "{family}";\n'
            for script, family in families.items()
        )
        + "}\n"
    )


def write_fonts(directory: Path) -> None:
    """Wrap every installed face in WOFF, with the stylesheet that declares
    them. The command checks the image before it prepares the edition."""
    faces = typeface.installed()
    directory.mkdir(parents=True, exist_ok=True)
    for face in faces:
        with TTFont(face, recalcTimestamp=False, recalcBBoxes=False) as font:
            font.flavor = "woff"
            font.save(directory / font_file(face))
    (directory / "fonts.css").write_text(font_stylesheet(faces), encoding="utf-8")


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


class Variant(TypedDict):
    chapter: str
    verse: str
    # The King James Bible's number, where it differs.
    kjv: NotRequired[str]
    lanes: list[Lane]


class VariantsBook(TypedDict):
    id: str
    entries: list[Variant]


class Terms(TypedDict):
    # The King James Bible, whose number an entry carries where it differs.
    kjv: str
    # The apparatus, whose accents a lane gives where they differ.
    apparatus: str


class Variants(TypedDict):
    title: str
    intro: list[usj.Node]
    terms: Terms
    books: list[VariantsBook]


def variants(edition: pipeline.Edition) -> Variants:
    """The textual variants for the website: the title and the prose of the
    page that opens them, then their entries by book, each the verse it is
    about, for the site to anchor and link, with the King James number where
    it differs and its lanes; and the terms the site labels them with, from
    the registry. The page's own names and each book's heading and names are
    left to the site, which prints them from the manifest."""
    terms = terminology.registry(edition.policy)
    page = edition.variants_page
    intro = [
        block
        for block in page["content"]
        if block["type"] != "book" and block.get("marker") not in usj.BOOK_PARAGRAPHS
    ]
    books: list[VariantsBook] = []
    for row, lanes in edition.variants:
        verse = references.parse_verse(row.reference)
        if not books or books[-1]["id"] != verse.book:
            books.append({"id": verse.book, "entries": []})
        entry: Variant = {
            "chapter": str(verse.chapter),
            "verse": f"{verse.number}{verse.letter}",
            "lanes": lanes,
        }
        if row.source != row.reference:
            entry["kjv"] = references.parse_verse(row.source).label
        books[-1]["entries"].append(entry)
    return {
        "title": assembly.header(page, "mt1"),
        "intro": intro,
        "terms": {
            "kjv": terms.display("king-james-version"),
            "apparatus": terms.display("apparatus"),
        },
        "books": books,
    }


# The names the manifest carries; a unit's title lines (mt1, mt2) print.
NAMES = frozenset({"h", *assembly.NAME_MARKERS.values()})


class Unit(TypedDict):
    id: str
    section: str
    title: str
    short: str


def matter(
    edition: pipeline.Edition, documents: Mapping[str, usj.Document]
) -> list[tuple[Unit, usj.Document]]:
    """The front matter the book prints, with the website-only numbering
    page after the editor's introduction, in reading order: the project's
    own pages, then each testament's before its books, without the
    dividers, which print a title alone; each the whole unit but for the names the
    manifest carries, opening with its book and its printed title, with its
    Greek and Hebrew tagged for their fonts as the typesetter has them, and
    the editor's pages as the editor wrote them."""
    result: list[tuple[Unit, usj.Document]] = []
    front = edition.policy.front_matter
    # Keep the website-only numbering page beside the introduction.
    at = (
        next(i for i, (_, entry) in enumerate(front) if entry == bible.policy.EDITOR)
        + 1
    )
    units = (*front[:at], ("front", bible.policy.NUMBERING), *front[at:])
    for section, entry in units:
        code = entry["id"]
        names: Mapping[str, str]
        if entry == bible.policy.NUMBERING:
            doc = edition.numbering_page
            names = assembly.names(entry, doc)
        else:
            # Under the names the book prints it under.
            doc = export.fonted(edition, code, documents[code])
            names = edition.names[code]
        book, *blocks = doc["content"]
        rest = list(itertools.dropwhile(lambda b: b.get("marker") in NAMES, blocks))
        # The site anchors a unit at its one printed title.
        require(
            book["type"] == "book"
            and all(b.get("marker") not in NAMES for b in rest)
            and sum(b.get("marker") == "mt1" for b in rest) == 1,
            f"Front matter does not open with its book, its names and one title: {code}",
        )
        unit: Unit = {
            "id": peripherals.UNITS[code].slug,
            "section": section,
            "title": names["title"],
            "short": names["short_title"],
        }
        division = peripherals.division(code, usj.with_blocks(doc, rest), unit["title"])
        group = peripherals.book(code)
        result.append((unit, usj.document([{**book, "code": group}, division])))
    return result


def write(edition: pipeline.Edition, directory: Path) -> None:
    """Write one document per chapter, each opening with its book, their
    ordered chapter inventory, with the book's names and whether a heading
    stands for a chapter's number, one document per unit of front matter,
    listed in the inventory with its section and names, the comparison
    page's passages, and the textual variants."""
    if directory.exists():
        shutil.rmtree(directory)
    write_fonts(directory / "fonts")
    documents = dict(pipeline.view(edition, "pdf"))
    files.write_json(directory / "comparisons.json", comparisons(edition, documents))
    files.write_json(directory / "variants.json", variants(edition))
    books = []
    for unit in edition.policy.scripture:
        code = unit["id"]
        # The Greek elision mark is set as its font has it.
        doc = export.fonted(edition, code, export.with_printed_origins(documents[code]))
        (book, *header), parts = pipeline.headed_chapters(doc)
        introduction = [n for n in header if n.get("marker") not in usj.BOOK_PARAGRAPHS]
        header = [n for n in header if n.get("marker") in usj.BOOK_PARAGRAPHS]
        # Before the first chapter stand only the book's names, which the
        # manifest carries.
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
                    "label": scripture.chapter_label(chapter, blocks),
                    "titled": chapter.get("pubnumber") == scripture.HIDDEN,
                    "verses": edition.inventory[code][number],
                }
            )
            files.write_json(
                directory / "books" / code / f"{number}.json",
                usj.with_blocks(doc, [book, *blocks]),
            )
        listed_book: dict[str, object] = {
            "id": code,
            "section": unit["section"],
            "title": names[assembly.NAME_MARKERS["title"]],
            "short": names[assembly.NAME_MARKERS["short_title"]],
            # The name one of its chapters is cited by.
            "cited": edition.books.name(code, chapters=(1,)),
            "chapters": chapters,
        }
        if introduction:
            title = present(
                next((n for n in introduction if n.get("marker") == "imt1"), None),
                f"Book introduction without its title: {code}",
            )
            require(
                all(n.get("marker") in {"imt1", "ip"} for n in introduction),
                f"Unexpected book introduction: {code}",
            )
            listed_book["introduction"] = {
                "title": usj.text_of(title["content"]),
                "slug": "prologue",
            }
            files.write_json(
                directory / "books" / code / "prologue.json",
                usj.with_blocks(doc, [book, *introduction]),
            )
        books.append(listed_book)
    units = []
    for listed, doc in matter(edition, documents):
        files.write_json(directory / "matter" / f"{listed['id']}.json", doc)
        units.append(listed)
    files.write_json(directory / "manifest.json", {"books": books, "matter": units})
