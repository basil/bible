"""Brenton's footnotes from CCEL's transcription, where eBible's lacks them.

CCEL's HTML edition of Brenton (sources/ccel-brenton-lxx.zip) transcribes
the text worse than eBible's archive and the notes far more fully. The build
reads it for the notes alone, and never for a word of the text: each page's
words are read with the note callers among them and parted into the runs of
one chapter each; a run's chapter is found among eBible's by the words, since
the archive's page names, contents, and chapter markup mislead: of the chapters
that share the run's rarer words, the one whose words the run's align with
best, and the build stops where two align alike and would set the notes
differently; and each note is set in eBible's verse before the word its
caller stands before, as Brenton's callers stand. A note eBible's verse
already has is passed over.

Legacy SIL Galatia Greek and unpointed SIL Ezra Hebrew are decoded from
SIL's published tables below. The reader preserves their raw font codes
before UTF-8 decoding, retains already Unicode words, composes Greek marks
to NFC, and reverses Hebrew phrases into logical order with final letters.
The note's source markup remains available to corrections and review;
decoding does not emend its transcription or supply words from another text.

What the reader does not understand is left out and listed in the review,
never guessed at: a body with undecodable characters or an unsupported font,
a bare Greek letter standing for a note set elsewhere on the page, an empty body, markup the reader does not know, a run
whose chapter the words do not find, a caller the alignment does not place.
A note that mentions Codex Alexandrinus or the Appendix is held back until
edition/alexandrinus.json decides it, as every such note of Brenton's must
be. edition/ccel-notes.json corrects a note's transcription, places a note
the words do not, or leaves one out.
"""

from __future__ import annotations

import bisect
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType

from lxml import etree, html

import bible.policy
from bible import (
    alignment,
    assembly,
    citations,
    lemmas,
    notes,
    references,
    repairs,
    scripture,
    terminology,
    usfm,
    usj,
    versification,
)
from bible.alexandrinus import ALEX, APPENDIX
from bible.checks import CheckFailed, require, require_used
from bible.policy_schema import CcelNote, Correction
from bible.sources import Content
from bible.usj import Document, Node

# How much of a run's weighted vocabulary a chapter must have to be aligned
# with the run, and how many of the run's words must then be matched in runs
# of two or more with the chapter and its neighbours, for the run to be read
# as that chapter's; of the chapters that pass, the best aligned.
CHAPTER_SHARE = 0.5
MATCHED_SHARE = 0.5

# Elements whose edges part words.
BLOCKS = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "td", "tr", "li", "hr"}
# Elements holding no words of the text: scripts, the navigation bars, the
# printed page numbers and CCEL's footer, all in tables or centred.
SKIPPED = {"script", "style", "table", "center"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
BARE_LETTER = re.compile(r"[α-ω]")
STOP = re.compile(r"\s+([.,;:?!])")
# A letter of each alphabet, with its combining marks.
GREEK_LETTER = re.compile(f"[{usfm.COMBINING}{usfm.GREEK}]")
HEBREW_LETTER = re.compile(f"[{usfm.HEBREW}]")


# SIL's published conversion tables, consulted 2026-10-13:
# https://github.com/silnrsi/wsresources/blob/master/scripts/Grek/legacy/sil-galatia/mappings/SILGreek.map
# SILGreek.map 1.0b5 (2004-04-27), display forms and basic alphabet.
# https://software.sil.org/downloads/r/ezra/EzraSIL-2.51-MappingFiles.zip
# HebrewMappings/SILEzratoUni50.map version 58 (2010-08-17), consonants.
# CCEL's Hebrew is unpointed. Unhandled codes remain undecodable rather
# than guessing at vowels or cantillation. No conversion tool runs at build time.
GALATIA = dict(zip("abgdezjqiklmnxoprstufcywv", "αβγδεζηθικλμνξοπρστυφχψως"))
GALATIA.update(
    {key.upper(): value.upper() for key, value in GALATIA.items() if key != "v"}
)
GALATIA.update(
    zip(
        map(chr, range(0x80, 0x100)),
        (
            "άὰᾶἁἅἃἇἀἄἂἆᾳᾴᾲᾷᾁ"
            "ᾅᾃᾇᾀᾄᾂ��ᾆέὲἑἕἐἔἓ"
            "�ᾥᾣᾧ�ᾠᾤᾢᾦ�������"
            "ίὶῖἱἵἷ��ἰἴἶϊΐῒἳῥ"
            "ύὺῦὑὕὓὗὐὔὒὖϋΰῢὂῤ"
            "ήὴῆἡἥἣἧἠἤἢἦῃῄῂῇᾑ"
            "ᾕᾓᾗᾐᾔᾒᾖόὸὁὅὃὀὄ��"
            "ώὼῶὡὥὣὧὠὤὢὦῳῴῲῷᾡ"
        ),
    )
)
GALATIA.update(
    {
        "H": "\u0313",
        "h": "\u0314",
        "'": "\u0301",
        "`": "\u0300",
        "^": "\u0342",
        "_": "\u0345",
        '"': "\u0308",
        "@": "’",
        ";": "·",
        "?": ";",
        "~": "—",
        "#": "\u00a0",
        "$": "«",
        "%": "»",
        "\x96": "–",
        "\x97": "—",
        "\xa0": "\u00a0",
        "\xa4": "¤",
        "\xac": "¬",
        "\xb6": "¶",
        "\xb7": "•",
        "\xa9": "\u0314\u0301",
        "\xaa": "\u0314\u0300",
        "\xab": "\u0314\u0342",
        "\xad": "\u0313\u0301",
        "\xae": "\u0313\u0300",
        "\xaf": "\u0313\u0342",
        "\xee": "\u0308\u0301",
        "\xef": "\u0308\u0300",
    }
)
EZRA = dict(zip("'bgdhwzxXyklmnsvpcqrSt", "אבגדהוזחטיכלמנסעפצקרשת"))
EZRA.update(zip(map(chr, range(162, 167)), "ךםןףץ"))
FINAL_HEBREW = str.maketrans("כמנפצ", "ךםןףץ")
LEGACY_FONT = re.compile(
    rb'(<font\b[^>]*\bface\s*=\s*[\'"]SIL (?:Galatia|Ezra)[\'"][^>]*>)(.*?)(</font\s*>)',
    re.IGNORECASE | re.DOTALL,
)


def page_text(data: bytes) -> str:
    """Keep invalid UTF-8 bytes in recognized font spans as Latin-1 codes.

    Valid UTF-8 survives, including iii.49's Unicode Greek in Galatia.
    Elsewhere damaged UTF-8 still becomes a replacement character. Font
    decoding happens only when reading a note, leaving its source markup
    and legacy codes available to corrections and review.
    """

    def preserve(match: re.Match[bytes]) -> bytes:
        text = match[2].decode("utf-8", errors="surrogateescape")
        text = "".join(
            chr(ord(c) - 0xDC00) if 0xDC80 <= ord(c) <= 0xDCFF else c for c in text
        )
        return match[1] + text.encode("utf-8") + match[3]

    return LEGACY_FONT.sub(preserve, data).decode("utf-8", errors="replace")


def font_words(element: html.HtmlElement) -> str:
    """Decode the declared font, preserving Unicode and transcription errors."""
    face = (element.get("face") or "").casefold()
    require(face in {"sil galatia", "sil ezra"}, f"unsupported font {face!r}")
    text = element.text_content()
    if face == "sil ezra":
        # Only legacy runs are reversed: Unicode Hebrew already has logical
        # order. Reverse words and their order together, keeping punctuation
        # surrounding the phrase in place (yhxh. ends in a period).
        letters = re.escape("".join(EZRA))
        pattern = rf"[{letters}]+(?:[\s.,;:!?-]+[{letters}]+)*"

        def hebrew(match: re.Match[str]) -> str:
            parts = re.split(rf"([{letters}]+)", match[0])
            decoded = "".join(
                "".join(EZRA[c] for c in part[::-1]) if i % 2 else part
                for i, part in reversed(list(enumerate(parts)))
            )
            return re.sub(
                r"[כמנפצ](?![א-ת])", lambda m: m[0].translate(FINAL_HEBREW), decoded
            )

        text = re.sub(pattern, hebrew, text)
        require(
            not any(
                (c.isalpha() or ord(c) > 127) and not HEBREW_LETTER.fullmatch(c)
                for c in text
            ),
            "undecodable SIL Ezra characters",
        )
        return text
    # Basic Galatia's sigma has a final form at a word boundary, before a
    # space or a stop, its own codes for these among them (# no-break space,
    # % closing guillemet, ~ and \x96 \x97 dashes); the display encoding also
    # supplies it explicitly as v. Unicode stays literal.
    text = re.sub(r"s(?=$|[\s.,;:!?()\[\]{}#%~\x96\x97])", "v", text)
    decoded = "".join(
        GALATIA.get(
            c,
            (
                c
                if c.isspace()
                or c in "!&()*+,-./0123456789:<=>[]{}"
                or GREEK_LETTER.fullmatch(c)
                else "�"
            ),
        )
        for c in text
    )
    # Basic Galatia puts breathings before vowels (or a diphthong) and rho,
    # which never opens a diphthong.
    decoded = re.sub(
        r"([\u0313\u0314][\u0300\u0301\u0342]*)([ΑΕΗΙΟΥΩαεηιουω](?:[ιυ](?!\u0308))?|[Ρρ])",
        r"\2\1",
        decoded,
    )
    require("�" not in decoded, "undecodable SIL Galatia characters")
    return unicodedata.normalize("NFC", decoded)


@dataclass(frozen=True)
class Caller:
    """A note caller on a page: its number there, the index of the run word
    it stands before (the run's length, at its end), and whether it closes
    its verse."""

    number: str
    index: int
    closing: bool


@dataclass(frozen=True)
class Run:
    """The words of one chapter on a page, in order, with the callers among
    them."""

    page: str
    words: tuple[str, ...]
    callers: tuple[Caller, ...]


@dataclass(frozen=True)
class Body:
    """A note's body: its source key (page and number), its content on
    eBible's conventions, its plain words, its inner HTML as the page has it
    for a correction to name, and why it cannot be read, if it cannot."""

    key: str
    content: tuple[Node, ...]
    text: str
    source: str
    problem: str | None = None


@dataclass(frozen=True)
class Listed:
    """A note the edition does not print, for the review: its source key,
    why, where it would stand (its would-be key, or the verse the words
    suggest, or nothing), its words, and its inner HTML."""

    key: str
    reason: str
    place: str
    text: str
    source: str


@dataclass(frozen=True)
class Duplicate:
    """A CCEL note accounted for by an existing source note, with both callers."""

    key: str
    retained: str
    place: str
    offset: int
    retained_offset: int
    scope: str
    retained_scope: str
    text: str
    other: str
    reason: str
    source: str


@dataclass(frozen=True)
class Report:
    pages: int
    bodies: int
    inserted: int
    held: tuple[Listed, ...]
    left_out: tuple[Listed, ...]
    matched: tuple[Duplicate, ...]
    deferred: tuple[Body, ...] = ()
    # The deferred notes once set, by their CCEL key and the key they print under.
    supplied: tuple[tuple[str, str], ...] = ()
    # How many keys each verse's placed notes took, whatever became of them,
    # so that a note set after promotion is numbered after them all.
    numbered: tuple[tuple[str, int], ...] = ()

    @property
    def duplicates(self) -> int:
        """How many notes eBible already had."""
        return len(self.matched)


# Reading the pages.


class Page:
    """A page's runs and bodies, read in document order."""

    def __init__(self, stem: str, corrections: Mapping[str, Correction]) -> None:
        self.stem = stem
        self.corrections = corrections
        self.runs: list[Run] = []
        self.bodies: dict[str, Body] = {}
        self.text: list[str] = []
        self.length = 0
        self.callers: list[tuple[str, int]] = []
        self.opening: set[str] = set()
        self.closing: set[str] = set()
        self.block = 0
        self.verse: int | None = None

    def add(self, text: str | None) -> None:
        if text:
            self.text.append(text)
            self.length += len(text)

    def close(self) -> None:
        """Mark the callers that close their verse, no word of the verse
        following them; one that opens its paragraph opens the next verse."""
        text = "".join(self.text)
        for number, at in self.callers:
            if number not in self.opening and not scripture.WORD.search(text, at):
                self.closing.add(number)

    def flush(self) -> None:
        self.close()
        if self.text or self.callers:
            spans = scripture.word_spans("".join(self.text))
            starts = [start for _, start, _ in spans]
            words = tuple(word for word, _, _ in spans)
            callers = tuple(
                Caller(number, bisect.bisect_left(starts, at), number in self.closing)
                for number, at in self.callers
            )
            if words or callers:
                self.runs.append(Run(self.stem, words, callers))
        self.text, self.length, self.callers, self.verse = [], 0, [], None
        self.opening, self.closing, self.block = set(), set(), 0

    def visit(self, element: html.HtmlElement) -> None:
        tag = element.tag
        if not isinstance(tag, str):  # a comment or processing instruction
            self.add(element.tail)
            return
        classes = (element.get("class") or "").split()
        if tag in HEADINGS or tag == "center":
            # An unclosed heading/centre in CCEL can swallow the rest of a
            # chapter. Its block children remain scripture, while its own
            # words (including the printed gloss band) remain excluded.
            if tag in HEADINGS:
                self.flush()
            scripture_started = False
            for child in element:
                if child.tag in (BLOCKS - {"table", "hr"}) or child.tag == "center":
                    scripture_started = True
                if scripture_started:
                    self.visit(child)
        elif tag in SKIPPED or (tag == "p" and "Center" in classes):
            pass
        elif tag == "div" and "Note" in classes:
            self.body(element)
        elif tag == "a" and "Note" in classes:
            match = re.fullmatch(r"_fnb(\d+)", element.get("name") or "")
            if match:
                self.callers.append((match[1], self.length))
                if not scripture.WORD.search("".join(self.text), self.block):
                    self.opening.add(match[1])
        elif (
            tag == "sup"
            and not len(element)
            and (element.text or "").strip().isdecimal()
        ):
            number = int((element.text or "").strip())
            self.close()
            if self.verse is not None and number <= self.verse:
                self.flush()
            self.verse = number
        else:
            if tag == "div" and element.get("type") in ("Chapter", "Book"):
                self.flush()
            if tag in BLOCKS:
                self.add(" ")
                self.block = self.length
            self.add(element.text)
            for child in element:
                self.visit(child)
            if tag in BLOCKS:
                self.add(" ")
                self.block = self.length
        self.add(element.tail)

    def body(self, element: html.HtmlElement) -> None:
        match = re.fullmatch(r"_fnf(\d+)", element.get("id") or "")
        paragraphs = [child for child in element if child.tag == "p"]
        if not match or len(paragraphs) != 1:
            return
        number = match[1]
        key = f"{self.stem}#{number}"
        paragraph = paragraphs[0]
        # The body's words follow the caller that leads back to the text.
        anchors = [child for child in paragraph if child.tag == "a"]
        if anchors and anchors[0] is paragraph[0]:
            back = anchors[0]
            paragraph.text = (paragraph.text or "") + (back.tail or "")
            paragraph.remove(back)
        source = etree.tostring(paragraph, encoding="unicode", with_tail=False)
        if key in self.corrections:
            source = repairs.corrected(
                source, self.corrections[key], "CCEL note correction", key
            )
            paragraph = html.fragment_fromstring(source)
        require(number not in self.bodies, f"CCEL note numbered twice: {key}")
        self.bodies[number] = read_body(key, paragraph, source)


def read_body(key: str, paragraph: html.HtmlElement, source: str) -> Body:
    """A note's body on eBible's conventions: a label or cited words in
    italic are fqa, references xt, the rest ft. Greek and Hebrew stand as
    plain words, as eBible's do. Legacy SIL Galatia display/basic forms and
    SIL Ezra consonants are decoded; already Unicode words are retained.
    Unsupported font codes are reported rather than emended."""
    pieces: list[tuple[str, str]] = []
    problem: str | None = None

    def piece(kind: str, text: str | None) -> None:
        if text:
            pieces.append((kind, text))

    def visit(element: html.HtmlElement, kind: str = "text") -> None:
        nonlocal problem
        piece(kind, element.text)
        for child in element:
            tag = child.tag
            if not isinstance(tag, str):  # a comment holds no words of the note
                pass
            elif tag in {"i", "scripref", "span"}:
                visit(child, {"i": "label", "scripref": "ref"}.get(tag, kind))
            elif tag == "br":
                piece(kind, " ")
            elif tag == "font":
                try:
                    require(
                        all(
                            node.tag in {"i", "span"}
                            for node in child.iterdescendants()
                        ),
                        "unknown markup within a font",
                    )
                    piece(kind, font_words(child))
                except CheckFailed as error:
                    problem = str(error)
                    piece(kind, child.text_content())
            else:
                if problem is None:
                    problem = f"unknown markup <{tag}>"
                piece(kind, child.text_content())
            piece(kind, child.tail)

    visit(paragraph)
    plain = scripture.plain("".join(text for _, text in pieces))
    if "\ufffd" in plain:
        problem = "undecodable characters"
    elif BARE_LETTER.fullmatch(plain):
        problem = "a letter standing for a note set elsewhere"
    elif problem is None and not scripture.words_of(plain):
        problem = "empty"
    if problem:
        return Body(key, (), plain, source, problem)
    pieces = normalized(pieces)
    plain = scripture.plain("".join(text for _, text in pieces))
    prose = scripture.plain(
        "".join(text if kind != "ref" else " " for kind, text in pieces)
    )
    if terminology.NUMBER_STOP.search(prose):
        # What edition/prose.json would have to decide for a note of
        # eBible's: "after 5. shillings".
        return Body(key, (), plain, source, "a number with a period within a sentence")
    content = tuple(
        usj.char({"label": "fqa", "ref": "xt"}.get(kind, "ft"), text)
        for kind, text in pieces
    )
    return Body(key, content, plain, source)


def normalized(pieces: Sequence[tuple[str, str]]) -> list[tuple[str, str]]:
    """The pieces with their transcription's slips of spacing mended, and
    nothing of their wording: one space between words, none before a stop,
    the stop or comma after a label as the label's, a double hyphen as the
    dash eBible sets, and a chapter and verse parted as eBible parts them."""
    result: list[tuple[str, str]] = []
    for kind, text in pieces:
        text = re.sub(r"\s+", " ", text).replace("--", "—")
        # A chapter and verse, and the abbreviations i. e. and q. d., spaced
        # as eBible's transcription sets them.
        text = re.sub(r"(\d):(\d)", r"\1. \2", text)
        text = re.sub(r"\b([iq])\.([ed])\.", r"\1. \2.", text)
        if not result:
            text = text.lstrip(" ")
        else:
            previous_kind, previous = result[-1]
            if previous_kind == "label" and text.lstrip(" ")[:1] in {".", ","}:
                # The stop or comma after a label is the label's, as eBible
                # sets it (Hebraism. and Or,), unless the label has its own.
                mark = text.lstrip(" ")[0]
                text = text.lstrip(" ")[1:]
                if not previous.endswith(mark):
                    previous += mark
            if text.startswith(" "):
                # A space between pieces ends the piece before, as eBible
                # sets a label (Gr. ) before the words it introduces.
                text = text.lstrip(" ")
                if not previous.endswith(" "):
                    previous += " "
            if text[:1] and text[0] in ".,;:?!":
                # No space before a stop, whichever piece holds the stop.
                previous = previous.rstrip(" ")
            result[-1] = (previous_kind, previous)
            if previous_kind == kind == "text":
                result[-1] = (kind, previous + text)
                continue
        if text:
            result.append((kind, text))
    if result:
        kind, text = result[-1]
        result[-1] = (kind, text.rstrip())
    return [(kind, STOP.sub(r"\1", text)) for kind, text in result if text]


def read_pages(
    pages: Content, corrections: Mapping[str, Correction]
) -> tuple[list[Run], dict[str, Body], int]:
    """Every page's runs and bodies, the pages in name order."""
    runs: list[Run] = []
    bodies: dict[str, Body] = {}
    unused = dict(corrections)
    count = 0
    for path in pages.glob("*.htm"):
        if path.stem == "TOC":
            continue
        count += 1
        page = Page(path.stem, corrections)
        text = page_text(path.read_bytes())
        root = html.document_fromstring(text)
        body = root.find("body")
        page.visit(body if body is not None else root)
        page.flush()
        runs += page.runs
        for found in page.bodies.values():
            bodies[found.key] = found
            unused.pop(found.key, None)
    require(not unused, f"Unused CCEL note corrections: {sorted(unused)}")
    return runs, bodies, count


# Finding each run's chapter in eBible's books.


@dataclass(frozen=True)
class Chapter:
    """A chapter of eBible's: its words in order, each with the verse it
    stands in and its offset there."""

    number: str
    words: tuple[str, ...]
    places: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class Book:
    """A book of eBible's: its verses, and its chapters' words."""

    code: str
    verses: Mapping[str, scripture.Verse]
    chapters: tuple[Chapter, ...]

    def window(self, index: int) -> Chapter:
        """A chapter with its neighbours, as one: a run of CCEL's chapter
        can cross eBible's chapter division, which follows another."""
        around = self.chapters[max(0, index - 1) : index + 2]
        return Chapter(
            self.chapters[index].number,
            tuple(w for c in around for w in c.words),
            tuple(p for c in around for p in c.places),
        )


def books_of(documents: Mapping[str, Document]) -> dict[str, Book]:
    result = {}
    for code, doc in documents.items():
        if code == APPENDIX:
            continue
        verses = scripture.verses(doc)
        by_chapter: dict[str, list[str]] = {}
        for reference in verses:
            by_chapter.setdefault(reference.split(":")[0], []).append(reference)
        chapters = []
        for number, references in by_chapter.items():
            words, places = [], []
            for reference in references:
                for word, start, _ in scripture.word_spans(verses[reference].text):
                    words.append(word)
                    places.append((reference, start))
            chapters.append(Chapter(number, tuple(words), tuple(places)))
        result[code] = Book(code, verses, tuple(chapters))
    return result


def bag(words: Iterable[str]) -> set[str]:
    return {alignment.stem(w) for w in words if w not in alignment.STOP_WORDS}


class Finder:
    """Which chapters a run may belong to, by the rarer words they share:
    those that have enough of the run's, by weight, since a run may be a
    fragment of its chapter. The run's chapter is the one of them whose
    words the run's align with best."""

    def __init__(self, books: Mapping[str, Book], runs: Sequence[Run]) -> None:
        self.chapters = [
            (book, index)
            for book in books.values()
            for index in range(len(book.chapters))
        ]
        self.bags = [bag(book.chapters[index].words) for book, index in self.chapters]
        self.weight = alignment.weights(
            dict(enumerate([*self.bags, *(bag(r.words) for r in runs)]))
        )
        self.index: dict[str, list[int]] = {}
        for i, words in enumerate(self.bags):
            for word in words:
                self.index.setdefault(word, []).append(i)

    def candidates(self, run: Run) -> list[tuple[Book, int, float]]:
        """Every chapter that shares a word of the run's vocabulary, with its
        book and how much of the vocabulary it has, by weight, the likest
        first."""
        # In a fixed order, whatever the hash seed, so that the sums and the
        # order of chapters that tie are the same on every build.
        words = sorted(bag(run.words))
        total = sum(self.weight[w] for w in words)
        shared: dict[int, float] = {}
        for word in words:
            for i in self.index.get(word, ()):
                shared[i] = shared.get(i, 0) + self.weight[word]
        if not total:
            return []
        # Ranked by share, not by the weight shared: a word every bag has
        # weighs less than nothing, and so may the whole vocabulary.
        share = {i: weight / total for i, weight in shared.items()}
        ranked = sorted(sorted(share), key=lambda i: -share[i])
        return [(*self.chapters[i], share[i]) for i in ranked]


# Placing the notes.


@dataclass(frozen=True)
class Candidate:
    body: Body
    code: str
    reference: str
    offset: int


def anchored(book: Book, verse: str, phrase: str, key: str) -> int:
    """The offset in a verse at which a decision's anchor words stand once."""
    require(
        verse in book.verses, f"CCEL note decision names no verse of its book: {key}"
    )
    spans = scripture.word_spans(book.verses[verse].text)
    wanted = scripture.words_of(phrase)
    found = lemmas.occurrences(spans, wanted)
    require(
        bool(wanted) and len(found) == 1,
        f"CCEL note anchor not met once in its verse: {key}: {phrase!r}",
    )
    return spans[found[0]][1]


def caller_position(caller: Caller, aligned: alignment.Alignment) -> int | None:
    """Where a caller before a run word stands in the chapter's words: before
    the match of that word, or after the match of the word before it, a
    word matched alone counting only near a run of matches; after the word
    before it alone where it closes its verse, since the word it stands
    before is the next verse's. None where neither is matched."""
    index = caller.index
    first = None if caller.closing else aligned.anchored(index)
    if first is not None:
        return first
    before = aligned.anchored(index - 1) if index > 0 else None
    return before + 1 if before is not None else None


Place = tuple[str, str, int] | None


def destinations(
    run: Run, chapter: Chapter, aligned: alignment.Alignment, book: Book
) -> list[tuple[Place, str]]:
    """Where each caller of the run stands in eBible's verses by the words
    of a window: the verse and offset, or None with why not."""
    result: list[tuple[Place, str]] = []
    previous: int | None = None
    for caller in run.callers:
        position = caller_position(caller, aligned)
        if position is None:
            result.append((None, "caller the words do not place"))
        elif previous is not None and position < previous:
            result.append((None, "caller out of order"))
        else:
            previous = position
            # A caller that closes its verse stays in the verse of the
            # word before it, at its end, though the next word begins
            # another.
            if position < len(chapter.places) and not (
                caller.closing
                and chapter.places[position][0] != chapter.places[position - 1][0]
            ):
                reference, offset = chapter.places[position]
            else:
                reference, _ = chapter.places[position - 1]
                offset = len(book.verses[reference].text)
            result.append(((book.code, reference, offset), ""))
    return result


def chapter_of(run: Run, finder: Finder) -> tuple[str, list[tuple[Place, str]] | None]:
    """The chapter the run's words place it in, as the review names it, and
    where they set its callers: of the chapters that share enough of its
    vocabulary, the one its words align with best. Two that align alike must
    set the callers alike, or the build stops: it does not choose between
    them."""
    candidates = finder.candidates(run)
    aligned: list[tuple[int, str, list[tuple[Place, str]]]] = []
    for book, index, share in candidates:
        if share < CHAPTER_SHARE:
            break
        window = book.window(index)
        matched = alignment.Alignment.of(run.words, window.words)
        if len(matched.solid) >= MATCHED_SHARE * len(run.words):
            places = destinations(run, window, matched, book)
            aligned.append((len(matched.solid), f"{book.code} {window.number}", places))
    if not aligned:
        if not candidates:
            return "", None
        book, index, _ = candidates[0]
        return f"{book.code} {book.chapters[index].number}", None
    best = max(count for count, _, _ in aligned)
    tied = [(label, places) for count, label, places in aligned if count == best]
    # Where the notes are set, not why one is not.
    settings = {tuple(place for place, _ in places) for _, places in tied}
    keys = ", ".join(f"{run.page}#{caller.number}" for caller in run.callers)
    require(
        len(settings) == 1,
        f"CCEL run's chapter is ambiguous: {keys}: "
        f"{', '.join(label for label, _ in tied)} align alike and place its notes differently",
    )
    return tied[0]


def place_run(
    run: Run,
    bodies: Mapping[str, Body],
    finder: Finder,
    books: Mapping[str, Book],
    decisions: Mapping[str, CcelNote],
    taken: set[str],
    listed: list[Listed],
) -> list[Candidate]:
    """Each note of a run at its place in eBible's verse, by the words."""
    if not run.callers:
        return []
    # The words place the callers that have a body, but not those a decision
    # sets on supplied words, which eBible's verses lack.
    placed = tuple(
        caller
        for caller in run.callers
        if (key := f"{run.page}#{caller.number}") in bodies
        and not (key in decisions and decisions[key].get("supplied"))
    )
    guess, places = chapter_of(replace(run, callers=placed), finder)
    found = dict(zip(placed, places or ()))
    result = []
    for caller in run.callers:
        key = f"{run.page}#{caller.number}"
        body = bodies.get(key)
        if body is None:
            listed.append(Listed(key, "caller without a body", guess, "", ""))
            continue
        decision = decisions.get(key)
        if decision is not None:
            taken.add(key)
            if decision.get("supplied"):
                continue
        place, problem = found.get(caller, (None, "run of no chapter"))
        if decision is not None and "verse" in decision:
            book_code, _, label = decision["verse"].partition(" ")
            require(book_code in books, f"CCEL note decision names no book: {key}")
            at = anchored(books[book_code], label, decision["anchor"], key)
            require(
                place != (book_code, label, at),
                f"CCEL note decision places the note as the words do: {key}",
            )
            place = (book_code, label, at)
        if place is None:
            require(
                decision is None or "duplicate" not in decision,
                f"CCEL duplicate decision's caller cannot be placed: {key}",
            )
            # A note the words do not place is left out anyway: omitting it
            # would change nothing.
            require(
                decision is None,
                f"CCEL note decision omits a note the words do not place: {key}",
            )
            listed.append(
                Listed(key, body.problem or problem, guess, body.text, body.source)
            )
            continue
        result.append(Candidate(body, *place))
    return result


# Punctuation that opens the word it precedes, which a caller stands before.
OPENING = "‘“'\"([«"


def outside_styles(doc: Document, verse: scripture.Verse, offset: int) -> int:
    """The offset, or the start of the character style it falls inside, or
    of the punctuation that opens the word there: a caller stands before a
    supplied word, never among the words of its style, as eBible sets
    Brenton's, and before a quotation mark rather than after it."""
    while offset > 0 and verse.text[offset - 1] in OPENING:
        offset -= 1
    at = 0
    for block, lo, hi, _ in verse.parts:
        for item in doc["content"][block]["content"][lo:hi]:
            if isinstance(item, str):
                at += len(item)
            elif "content" in item and not usj.is_note(item):
                # Any span the words count, as usj.split does, so that the
                # offsets stay the verse's.
                end = at + len(usj.text_of(item["content"]))
                if at < offset < end:
                    return at
                at = end
        at += 1
    return offset


def note_words(note: Node) -> str:
    """A note's complete text after its origin, preserving Unicode and labels."""
    return usj.text_of([item for item in note["content"] if not usj.is_origin(item)])


def canonical_note(text: str) -> str:
    """Only encoding, spacing, and typographic quote differences are immaterial."""
    return scripture.plain(
        unicodedata.normalize("NFC", text).translate(str.maketrans("‘’“”", "''\"\""))
    )


def note_form(
    text: str, code: str, reference: str, key: str, policy: bible.policy.Policy
) -> list[str]:
    """A note's words as two transcriptions of it share them: what its
    citations name rather than how they write it, without punctuation or
    capitals."""
    try:
        found = citations.parse(
            text,
            citations.dialect("brenton", policy=policy),
            references.verse_at(code, reference),
            key,
            None,
            policy=policy,
        )
    except CheckFailed:
        found = []
    for citation in reversed(found):
        text = f"{text[: citation.start]} {citation.targets} {text[citation.end :]}"
    return "".join(
        " " if unicodedata.category(c)[0] in "PZ" else c
        for c in unicodedata.normalize("NFC", text).casefold()
    ).split()


def same_notes(
    verse: scripture.Verse,
    offsets: Iterable[int],
    body: Body,
    key: str,
    policy: bible.policy.Policy,
) -> tuple[list[tuple[int, Node]], str]:
    """The verse's notes at the caller's word, where the words place it or
    where it would print, that give the same note as the body, and in what
    way they are the same."""
    starts = [start for _, start, _ in scripture.word_spans(verse.text)]
    words = {bisect.bisect_left(starts, offset) for offset in offsets}
    here = [
        (at, note)
        for at, note in verse.notes
        if bisect.bisect_left(starts, at) in words
    ]
    same = [
        (at, note)
        for at, note in here
        if canonical_note(note_words(note)) == canonical_note(body.text)
    ]
    if same:
        return same, "Same Unicode text at the same caller word"
    code, _, reference = key.partition(" CCEL")[0].partition(" ")
    form = note_form(body.text, code, reference, key, policy)
    return (
        [
            (at, note)
            for at, note in here
            if note_form(
                note_words(note), code, reference, note.get("x-key", key), policy
            )
            == form
        ],
        "Same words at the same caller word; only punctuation, capitals or citation form differ",
    )


def caller_scope(verse: scripture.Verse, offset: int) -> str:
    """The words following a caller, for reading its placement in the review."""
    return " ".join(verse.text[offset:].split()[:5]) or "(end of verse)"


SEE = re.compile(r"\s*(?:[Ss]ee)?[\s;,.]*")


def finished_note(
    body: Body,
    code: str,
    reference: str,
    key: str,
    terms: terminology.Registry,
    policy: bible.policy.Policy,
) -> tuple[Node | None, str]:
    """The note as eBible's transcription would set it: a cross-reference
    where it is nothing but "See" and what it cites, as eBible sets
    Brenton's references; otherwise a footnote. None, with the reason, where
    it cites a passage in a form the edition cannot read, or abbreviates in
    a form the edition does not print and no term renders: such a note is
    left out, for a correction to bring in, rather than stopping the build
    as a note of eBible's would. What a citation names is resolved when the
    notes are set, as for any note, where a citation decision answers for it,
    and a prose decision on the note's words answers for its abbreviations
    the same way: the forms printed are checked once the notes are finished.
    """
    text = notes.text_of(notes.source_pieces(usj.note("f", *body.content)))
    rest = text
    for term in sorted(terminology.recognize(text, terms), key=lambda t: -t.start):
        rest = rest[: term.start] + rest[term.end :]
    # The finished note lowers its first letter where it runs on after its
    # lemma, so an abbreviation that opens the note counts as well.
    if key not in notes.note_prose(policy) and (
        terminology.UNPRINTED.search(rest)
        or terminology.UNPRINTED.search(rest[:1].lower() + rest[1:])
    ):
        return None, "abbreviation in a form the edition does not print"
    extra = usj.Extra({"x-key": key})
    footnote = usj.note(
        "f", usj.char("fr", f"{reference} "), *body.content, caller="+", **extra
    )
    try:
        found = citations.parse(
            text,
            citations.dialect("brenton", policy=policy),
            references.verse_at(code, reference),
            key,
            None,
            policy=policy,
        )
    except CheckFailed:
        # A decision on the note's citations answers for them, and is
        # carried out, or refused, when the notes are set.
        if citations.decisions(key, policy=policy):
            return footnote, ""
        return None, "citation the edition cannot read"
    rest = text
    for citation in reversed(found):
        rest = rest[: citation.start] + rest[citation.end :]
    if found and SEE.fullmatch(rest):
        cited = re.sub(r"^\s*[Ss]ee\s+", "", text)
        return (
            usj.note(
                "x",
                usj.char("xo", f"{reference} "),
                usj.char("xt", cited),
                caller="+",
                **extra,
            ),
            "",
        )
    return footnote, ""


def decided_alexandrine(policy: bible.policy.Policy, key: str) -> bool:
    """Whether alexandrinus.json decides a note of this key."""
    data = policy.alexandrinus
    consumed = {
        k for entry in data["passages"].values() for k in entry.get("source_notes", ())
    }
    return key in data["readings"] or key in data["kept"] or key in consumed


def supplemented(
    documents: Mapping[str, Document], pages: Content, policy: bible.policy.Policy
) -> tuple[MappingProxyType[str, Document], Report]:
    """eBible's books with the notes CCEL's pages have and they lack."""
    corrections = policy.ccel_notes["corrections"]
    decisions = policy.ccel_notes["notes"]
    terms = terminology.registry(policy)
    runs, bodies, count = read_pages(pages, corrections)
    for body in bodies.values():
        require(
            not (body.problem and ALEX.search(body.text)),
            f"Unreadable Alexandrinus/Appendix CCEL note {body.key}: "
            f"{body.problem}; add a verified CCEL transcription correction",
        )
    wanted = {
        code
        for entry in policy.scripture
        if entry.get("source") == "brenton"
        for code in assembly.source_codes(entry)
    }
    books = books_of({code: doc for code, doc in documents.items() if code in wanted})
    deferred: list[Body] = []
    for key, supplied_decision in decisions.items():
        if not supplied_decision.get("supplied"):
            continue
        require(key in bodies, f"Supplied CCEL note has no source body: {key}")
        body = bodies[key]
        require(not body.problem, f"Unreadable supplied CCEL note: {key}")
        require(
            not ALEX.search(body.text),
            f"Supplied CCEL note needs an Alexandrinus decision before promotion: {key}",
        )
        code, _, reference = supplied_decision["verse"].partition(" ")
        require(code in books, f"Supplied CCEL note names no source book: {key}")
        # A note on supplied words waits for them: a verse promotion
        # supplies, or words it adds to a verse that lacks them now.
        verse = books[code].verses.get(reference)
        require(
            verse is None
            or not lemmas.occurrences(
                scripture.word_spans(verse.text),
                scripture.words_of(supplied_decision["anchor"]),
            ),
            f"Supplied CCEL note already has its words before promotion: {key}",
        )
        deferred.append(body)
    finder = Finder(books, runs)
    listed: list[Listed] = []
    taken: set[str] = {body.key for body in deferred}
    candidates: list[Candidate] = []
    for run in runs:
        candidates += place_run(run, bodies, finder, books, decisions, taken, listed)
    called = {f"{run.page}#{caller.number}" for run in runs for caller in run.callers}
    for key in bodies.keys() - called:
        if key in taken:
            continue
        body = bodies[key]
        listed.append(
            Listed(
                key,
                body.problem or "body without a readable caller",
                "",
                body.text,
                body.source,
            )
        )
    require_used(decisions, taken, "CCEL note decisions")
    # The notes of a verse, in the order of their places, each with its key;
    # Every placed candidate is numbered before its disposition is decided,
    # including duplicates and omissions: changing one cannot rename another.
    by_verse: dict[tuple[str, str], list[Candidate]] = {}
    for candidate in candidates:
        by_verse.setdefault((candidate.code, candidate.reference), []).append(candidate)
    changes: dict[str, list[tuple[scripture.Verse, int, int, usj.Content]]] = {}
    held: list[Listed] = []
    matched: list[Duplicate] = []
    inserted = 0
    # eBible's notes that a decision sets in another verse, where a CCEL note
    # there is the same note. The decision names that verse as the edition
    # numbers the note's unit, and a candidate stands in eBible's verse of its
    # file, so both are compared where the edition prints them.
    relabelled = versification.relabelled(policy=policy)
    undivided = versification.undivided(policy=policy)

    def printed_at(code: str, reference: str) -> references.Verse | None:
        verse = assembly.unit_verse(policy, code, reference)
        if verse is None or verse in undivided:
            return None
        return relabelled.get(verse, verse)

    moved_in: dict[references.Verse, list[Node]] = {}
    for note_key, override in policy.brenton_notes["notes"].items():
        if "verse" not in override or references.book_of(note_key) not in books:
            continue
        code, _, noted = note_key.partition("#")[0].partition(" ")
        unit = assembly.unit_verse(policy, code, noted)
        if noted in books[code].verses and unit is not None:
            moved_in.setdefault(
                references.verse_at(unit.book, override["verse"]), []
            ).extend(
                note
                for _, note in books[code].verses[noted].notes
                if note.get("x-key") == note_key
            )
    for (code, reference), found in by_verse.items():
        verse = books[code].verses[reference]
        for number, candidate in enumerate(sorted(found, key=lambda c: c.offset), 1):
            key = f"{code} {reference} CCEL" + (f"#{number}" if number > 1 else "")
            body = candidate.body
            decision = decisions.get(body.key)
            if body.problem:
                # An unreadable body is left out anyway: a decision on it
                # would change nothing printed.
                require(
                    decision is None,
                    f"CCEL note decision on an unreadable body: {body.key}",
                )
                listed.append(
                    Listed(body.key, body.problem, key, body.text, body.source)
                )
                continue
            # Where it would print: a note already there is the same note.
            printed = outside_styles(documents[code], verse, candidate.offset)
            same, reason = same_notes(
                verse, (candidate.offset, printed), body, key, policy
            )
            if not same and moved_in:
                here = printed_at(code, reference)
                same = [
                    (candidate.offset, note)
                    for note in (moved_in.get(here, []) if here is not None else [])
                    if canonical_note(note_words(note)) == canonical_note(body.text)
                ]
                if same:
                    reason = "Same Unicode text, which a decision sets in this verse"
            if decision is not None and decision.get("omitted"):
                require(
                    not same, f"CCEL note decision omits a note eBible has: {body.key}"
                )
                listed.append(
                    Listed(body.key, "omitted by decision", key, body.text, body.source)
                )
                continue
            retained = decision.get("duplicate") if decision is not None else None
            require(
                retained is None or not same,
                f"CCEL duplicate decision matches automatically: {body.key}",
            )
            if retained is not None:
                assert decision is not None
                same = [
                    (at, note)
                    for at, note in verse.notes
                    if note.get("x-key") == retained
                ]
                require(
                    len(same) == 1,
                    f"CCEL duplicate target not met once in its verse: {body.key}: {retained}",
                )
                reason = decision["why"]
            if same:
                at, existing_note = same[0]
                matched.append(
                    Duplicate(
                        body.key,
                        existing_note["x-key"],
                        key,
                        candidate.offset,
                        at,
                        caller_scope(verse, candidate.offset),
                        caller_scope(verse, at),
                        body.text,
                        note_words(existing_note),
                        reason,
                        body.source,
                    )
                )
                continue
            if ALEX.search(body.text) and not decided_alexandrine(policy, key):
                held.append(
                    Listed(
                        body.key,
                        "awaiting an Alexandrine decision",
                        key,
                        body.text,
                        body.source,
                    )
                )
                continue
            note, reason = finished_note(body, code, reference, key, terms, policy)
            if note is None:
                listed.append(Listed(body.key, reason, key, body.text, body.source))
                continue
            changes.setdefault(code, []).append((verse, printed, printed, [note]))
            inserted += 1
    result = {
        code: scripture.edited(doc, changes[code]) if code in changes else doc
        for code, doc in documents.items()
    }
    report = Report(
        count,
        len(bodies),
        inserted,
        tuple(held),
        tuple(sorted(listed, key=lambda item: item.key)),
        tuple(matched),
        tuple(deferred),
        numbered=tuple(
            (f"{code} {reference}", len(found))
            for (code, reference), found in by_verse.items()
        ),
    )
    return MappingProxyType(result), report


def supplied(
    documents: Mapping[str, Document], report: Report, policy: bible.policy.Policy
) -> tuple[MappingProxyType[str, Document], Report]:
    """Attach notes whose verified target verses promotion has supplied.

    Their bodies were decoded at Read. Only their unique anchor is resolved
    now, against the source wording promotion supplied, before revision.
    """
    if not report.deferred:
        return MappingProxyType(dict(documents)), report
    terms = terminology.registry(policy)
    # The books the decisions name, read for their verses and words.
    named = {
        references.book_of(policy.ccel_notes["notes"][body.key]["verse"])
        for body in report.deferred
    }
    books = books_of({code: documents[code] for code in named if code in documents})
    candidates: dict[tuple[str, str], list[Candidate]] = {}
    for body in report.deferred:
        decision = policy.ccel_notes["notes"][body.key]
        code, _, reference = decision["verse"].partition(" ")
        require(code in books, f"Supplied CCEL note names no promoted book: {body.key}")
        offset = anchored(books[code], reference, decision["anchor"], body.key)
        candidates.setdefault((code, reference), []).append(
            Candidate(body, code, reference, offset)
        )
    changes: dict[str, list[tuple[scripture.Verse, int, int, usj.Content]]] = {}
    attached: list[tuple[str, str]] = []
    numbered = dict(report.numbered)
    keys = {
        code: {n.get("x-key") for n in usj.notes_of(documents[code]["content"])}
        for code, _ in candidates
    }
    for (code, reference), found in candidates.items():
        verse = books[code].verses[reference]
        # Numbered after every note the words placed in the verse, set or
        # not, which keep their keys.
        first = 1 + numbered.get(f"{code} {reference}", 0)
        found.sort(key=lambda c: c.offset)
        require(
            all(
                at < found[0].offset
                for at, n in verse.notes
                if " CCEL" in n.get("x-key", "")
            ),
            f"Supplied CCEL note stands before the verse's source CCEL notes: {code} {reference}",
        )
        for number, candidate in enumerate(found, first):
            body = candidate.body
            key = f"{code} {reference} CCEL" + (f"#{number}" if number > 1 else "")
            require(
                key not in keys[code],
                f"Supplied CCEL note takes a key another note has: {key}",
            )
            keys[code].add(key)
            at = outside_styles(documents[code], verse, candidate.offset)
            require(
                not same_notes(verse, (candidate.offset, at), body, key, policy)[0],
                f"Supplied CCEL note duplicates an existing note: {body.key}",
            )
            note, reason = finished_note(body, code, reference, key, terms, policy)
            require(
                note is not None,
                f"Supplied CCEL note cannot be set: {body.key}: {reason}",
            )
            assert note is not None
            changes.setdefault(code, []).append((verse, at, at, [note]))
            attached.append((body.key, key))
    result = {
        code: scripture.edited(doc, changes[code]) if code in changes else doc
        for code, doc in documents.items()
    }
    return MappingProxyType(result), replace(
        report,
        inserted=report.inserted + len(attached),
        deferred=(),
        supplied=tuple(attached),
    )
