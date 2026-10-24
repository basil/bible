"""The pinned Greek texts, with their token addresses, and the printed RP2026.

Scrivener 1894 (unaccented), the parsed Scrivener from the UTR file, RP2018
from the BP5 files, RP2026 as RP2018 with the Appendix A patches, checked
against the Guardian Press PDF (as `pdftohtml -xml` output).
"""

from __future__ import annotations

import collections
import dataclasses
import functools
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, Sequence
from typing import TypedDict, cast

from bible.byzantine import BOOKS
from bible.byzantine.rows import BoydNote, BoydReading, Token
from bible.checks import CheckFailed, present, require
from bible.scripture import plain
from bible.sources import BYZTXT_BOOKS, Content
from bible.usfm import GREEK

# A Greek text's words, by "BOOK c:v"; and a parsed text's tokens.
Text = dict[str, list[str]]
Tags = dict[str, list[Token]]


class PrintedVerse(TypedDict):
    """A verse of the printed RP2026: its unaccented forms, its accented
    words, and its page (none for a verse the text omits); and where the
    callers of its apparatus entries stand, as "page letter" to the number
    of its words before them."""

    Greek: list[str]
    accented: list[str]
    page: int | None
    callers: dict[str, int]


Diacritic = TypedDict(
    "Diacritic",
    {"ref": str, "from": str, "to": str, "page": int, "apparatus": str, "listed": bool},
    total=False,
)
"""An accent contrast with the TR: printed in RP2026's apparatus, or listed."""


class MarginalAlternate(TypedDict):
    """One of RP's marginal readings: the RP2018 token range of the main
    words, the main words, and the alternate."""

    range: list[int]
    main: list[str]
    alternate: list[str]


@dataclasses.dataclass(frozen=True, eq=False)
class Structure:
    """What the Byzantine text does with whole verses of the Received Text:
    the verses it lacks, and the addresses at which it prints verses the
    King James Bible numbers otherwise (edition/byzantine.json, structure).
    The omitted verses are read from RP2018 itself; the moves are the
    editor's decisions, checked against both texts' inventories."""

    moved: Mapping[str, str]
    omitted: frozenset[str]

    @functools.cached_property
    def inverse(self) -> dict[str, str]:
        return {target: ref for ref, target in self.moved.items()}

    def rp_ref(self, ref: str) -> str:
        """The address at which RP2026 prints the KJV's verse."""
        return self.moved.get(ref, ref)

    def kjv_ref(self, ref: str) -> str:
        """The address at which the KJV prints RP2026's verse."""
        return self.inverse.get(ref, ref)

    @functools.cached_property
    def exchanged(self) -> frozenset[str]:
        """The verses that exchange places, each with the other (Matthew
        23:13-14), rather than move as a passage."""
        return frozenset(
            ref for ref, target in self.moved.items() if self.moved.get(target) == ref
        )


def empty_verses(text: Mapping[str, list[str]]) -> frozenset[str]:
    """The verses a text numbers but gives no words: those it omits."""
    return frozenset(ref for ref, words in text.items() if not words)


# Appendix A of the RP2026 volume: the main-text changes 2018 -> 2026 that an
# unaccented comparison can see. PHP 3:5 (accent only) is a supplementary unit.
PATCHES = {
    "MAT 26:29": (["gennhmatos"], ["genhmatos"]),
    "ROM 13:9": (["seauton"], ["eauton"]),
    "PHM 1:1": (["xristou", "ihsou"], ["ihsou", "xristou"]),
    "REV 11:16": (
        ["enwpion", "tou", "qronou", "tou", "qeou"],
        ["enwpion", "tou", "qeou"],
    ),
    "REV 13:14": (["thn", "plhghn"], ["plhghn"]),
}


# The BP5 transliteration back into Greek letters, unaccented.
GREEK_LETTERS = str.maketrans("abgdezhqiklmncoprstufxyw", "αβγδεζηθικλμνξοπρστυφχψω")


def greek_letters(words: Iterable[str]) -> list[str]:
    """The pinned transliteration in unaccented Greek letters, with a final
    sigma where a word ends."""
    return [re.sub("σ$", "ς", word.translate(GREEK_LETTERS)) for word in words]


LATIN = str.maketrans(
    "αβγδεζηθικλμνξοπρσςτυφχψωϲ", "abgdezhqiklmn coprsstufxyws".replace(" ", "")
)


@functools.cache
def ascii_greek(text: str) -> str:
    letters = "".join(
        c
        for c in unicodedata.normalize("NFD", text.lower())
        if not unicodedata.combining(c)
    )
    return letters.translate(LATIN)


def greek_words(text: str) -> list[str]:
    return re.findall(r"[a-z]+", ascii_greek(text))


def occurrences(stream: list[str], phrase: list[str]) -> list[int]:
    if not phrase:
        return []
    return [
        i
        for i in range(len(stream) - len(phrase) + 1)
        if stream[i : i + len(phrase)] == phrase
    ]


def scrivener(folder: Content) -> Text:
    result: Text = {}
    for book, filename in zip(BOOKS, BYZTXT_BOOKS, strict=True):
        raw = (folder / f"{filename}.SCV").read_text()
        raw = re.sub(r"\[[^]]*\]", "", raw)
        chunks = re.split(r"(\d+:\d+)", raw)
        require(not chunks[0].strip(), f"Unparsed Scrivener header: {filename}")
        for ref, body in zip(chunks[1::2], chunks[2::2], strict=True):
            body = body.lower().translate(str.maketrans("vycqx", "sqxyc"))
            require(
                not re.search(r"[^a-z\s]", body),
                f"Unparsed Scrivener verse: {book} {ref}",
            )
            key = f"{book} {ref}"
            require(key not in result, f"Duplicate Scrivener verse: {key}")
            result[key] = body.split()
    require(len(result) == 7957, f"Scrivener inventory: {len(result)}, expected 7957")
    return result


def corrected(
    text: Text, corrections: Mapping[str, Mapping[str, str]], accented: bool = False
) -> Text:
    """A Scrivener text with the editor's corrections of its transcription
    (edition/byzantine.json, scrivener): in each verse named, the words from
    stand once and become the words to. The unaccented text compares them by
    their letters, the accented as written."""
    result = dict(text)
    for ref, correction in corrections.items():
        old, new = (
            (
                unicodedata.normalize("NFC", correction[side]).split()
                if accented
                else greek_words(correction[side])
            )
            for side in ("from", "to")
        )
        words = present(result.get(ref), f"Scrivener correction of no verse: {ref}")
        found = occurrences(words, old)
        require(len(found) == 1, f"Scrivener correction does not fit its verse: {ref}")
        at = found[0]
        result[ref] = [*words[:at], *new, *words[at + len(old) :]]
    return result


# Lunate sigma and the numeral stigma, in the pinned text's sigma form.
SIGMAS = str.maketrans("ϲϛϹϚ", "σςΣΣ")


@functools.cache
def accent_letters(text: str) -> tuple[str, ...]:
    """Cased letters with their combining marks, without punctuation.
    Lunate sigma and the numeral stigma use the pinned text's sigma form.
    Repeated source words share an immutable, checked result."""
    result: list[str] = []
    for letter in unicodedata.normalize("NFD", text):
        if unicodedata.combining(letter):
            if not result:
                raise CheckFailed(f"Greek mark without a letter: {text}")
            result[-1] += letter
        elif letter.isalpha():
            result.append(letter.translate(SIGMAS))
        elif not letter.isspace() and letter not in ",.;··∙:!?ʼ’'᾽—-()´":
            raise CheckFailed(f"Unknown Greek character: {text}")
    if any(ord(c[0].lower()) not in LATIN for c in result):
        raise CheckFailed(f"Unknown Greek letters: {text}")
    return tuple(result)


def letter_key(text: str) -> str:
    """The letters with their diacritics, for comparing Greek without case
    or punctuation: a grave accent is not the acute it stands for."""
    # lower(), not casefold(): casefold erases iota subscripts.
    return unicodedata.normalize("NFC", "".join(accent_letters(text))).lower()


@dataclasses.dataclass(frozen=True)
class Alignment:
    """Checked projection of comparison tokens onto complete source words."""

    text: Text
    spans: dict[str, list[tuple[int, int]]]
    addresses: dict[str, list[str]]

    def project(self, ref: str, span: Sequence[int]) -> tuple[int, int]:
        a, b = span
        offsets = self.spans[ref]
        require(0 <= a <= b <= len(offsets), f"Invalid Greek token range: {ref} {span}")
        if a == b:
            at = offsets[a][0] if a < len(offsets) else len(self.text[ref])
            return at, at
        return offsets[a][0], offsets[b - 1][1]


def align(
    source: Mapping[str, list[str]], target: Mapping[str, list[str]]
) -> Alignment:
    """Align within books, permitting bounded split/join and final ν/ς only.

    Keep the source words intact, even when a ledger boundary cuts a joined
    word. Repeated words are consumed in source order; ambiguous local groups
    and unsupported differences are refused with both source addresses.
    """
    text: Text = {ref: [] for ref in target}
    spans: dict[str, list[tuple[int, int]]] = {ref: [] for ref in target}
    addresses: dict[str, list[str]] = {ref: [] for ref in target}
    by_book: collections.defaultdict[
        str, tuple[list[tuple[str, str]], list[tuple[str, str]]]
    ] = collections.defaultdict(lambda: ([], []))
    for side, words in enumerate((target, source)):
        for ref, ws in words.items():
            by_book[ref.split()[0]][side].extend((ref, w) for w in ws)
    for book in BOOKS:
        tokens, supplied = by_book[book]
        forms = [ascii_greek("".join(accent_letters(w))) for _, w in supplied]
        require(all(forms), f"Empty Greek source word in {book}")
        # Callers address the words by their whitespace-separated offsets.
        require(
            all(len(w.split()) == 1 for _, w in supplied),
            f"Greek source word with a space in {book}",
        )
        i = j = 0
        # One joined source word can project into two ledger verses.
        included: dict[str, dict[int, int]] = {ref: {} for ref, _ in tokens}
        while i < len(tokens) and j < len(supplied):
            matches = []
            for a, b in ((1, 1), (1, 2), (2, 1)):
                if i + a > len(tokens) or j + b > len(supplied):
                    continue
                left = "".join(w for _, w in tokens[i : i + a])
                right = "".join(forms[j : j + b])
                if left == right or (
                    a == b == 1
                    and (
                        left in (right + "n", right + "s")
                        or right in (left + "n", left + "s")
                    )
                ):
                    matches.append((a, b))
            if len(matches) != 1:
                kind = "Ambiguous" if matches else "Unsupported"
                raise CheckFailed(
                    f"{kind} Greek alignment at {tokens[i][0]} / {supplied[j][0]}: {tokens[i:i+2]} / {supplied[j:j+2]}"
                )
            a, b = matches[0]
            for ref, _ in tokens[i : i + a]:
                for k in range(j, j + b):
                    if k not in included[ref]:
                        included[ref][k] = len(text[ref])
                        text[ref].append(supplied[k][1])
                        addresses[ref].append(supplied[k][0])
                spans[ref].append((included[ref][j], included[ref][j + b - 1] + 1))
            i, j = i + a, j + b
        require(
            i == len(tokens) and j == len(supplied),
            f"Unaligned Greek tail in {book}: {tokens[i:i+2]} / {supplied[j:j+2]}",
        )
    return Alignment(text, spans, addresses)


def accented_scrivener(
    path: Content,
    tr: Mapping[str, list[str]],
    corrections: Mapping[str, Mapping[str, str]] | None = None,
) -> Alignment:
    """Read the accented transcription faithfully, with the editor's
    corrections of it (corrected), and check its alignment."""
    source: Text = {}
    for row in json.loads(path.read_text()):
        ref = f"{row['book_name_short']} {row['chapter']}:{row['verse']}"
        require(ref not in source, f"Duplicate accented Scrivener verse: {ref}")
        source[ref] = [
            unicodedata.normalize("NFC", plain(w["greek"])) for w in row["words"]
        ]
    require(
        set(source) == set(tr),
        "Accented Scrivener verse inventory differs from the pinned TR",
    )
    return align(corrected(source, corrections or {}, accented=True), tr)


BP5_LINE = re.compile(r"(\d+)\.(\d+)\s*(.*)")
BP5_TOKEN = re.compile(r"([a-z]+)\s+((?:(?:\d+|\{[^}]+\})\s*)+)")
BP5_PARSE = re.compile(r"\{([^}]+)\}")
BP5_NUMBER = re.compile(r"\d+")


def bp5_line(line: str) -> tuple[str, list[Token]]:
    match = present(BP5_LINE.fullmatch(line), f"Unparsed BP5 line: {line}")
    body = match[3]
    tokens: list[Token] = []
    at = 0
    for word in BP5_TOKEN.finditer(body):
        if body[at : word.start()].strip():
            raise CheckFailed(f"Unparsed BP5 token: {body[at:word.start()]}")
        parses = BP5_PARSE.findall(word[2])
        strong = [int(n) for n in BP5_NUMBER.findall(BP5_PARSE.sub("", word[2]))]
        if not parses or not strong:
            raise CheckFailed(f"Missing BP5 annotation: {word[0]}")
        tokens.append({"word": word[1], "strong": strong, "parse": parses})
        at = word.end()
    require(not body[at:].strip(), f"Unparsed BP5 tail: {body[at:]}")
    return f"{int(match[1])}:{int(match[2])}", tokens


def rp2018(folder: Content) -> tuple[Text, Tags]:
    text: Text = {}
    tags: Tags = {}
    for number, book in enumerate(BOOKS, 1):
        paths = list(folder.glob(f"{number:02d}_*.BP5"))
        require(len(paths) == 1, f"Expected one BP5 file for {book}: {paths}")
        for line in paths[0].read_text().splitlines():
            ref, tokens = bp5_line(line)
            key = f"{book} {ref}"
            require(key not in text, f"Duplicate RP verse: {key}")
            text[key] = [t["word"] for t in tokens]
            tags[key] = tokens
    require(len(text) == 7957, "Unexpected RP2018 verse inventory")
    return text, tags


def rp2026(text: Mapping[str, list[str]], printed: Mapping[str, PrintedVerse]) -> Text:
    """RP2018 with the Appendix A patches, which must equal the printed text."""
    result = dict(text)
    for ref, (old, new) in PATCHES.items():
        positions = occurrences(text[ref], old)
        require(len(positions) == 1, f"Stale Appendix A patch: {ref}")
        at = positions[0]
        result[ref] = text[ref][:at] + new + text[ref][at + len(old) :]
    differences = [
        ref
        for ref in result
        if ref not in printed or result[ref] != printed[ref]["Greek"]
    ]
    require(
        not differences and set(printed) == set(result),
        f"RP2026 disagrees with the printed Guardian text: {differences[:10]}",
    )
    return result


def parsed_scrivener(folder: Content) -> tuple[Text, Tags]:
    """Read UTR's second alternative (Scrivener), retaining shared tags.

    Parenthetical verse labels refer to Stephanus; bracketed subscriptions
    are outside the scripture. Compare with the SCV text before using annotations.
    """
    text: Text = {}
    tags: Tags = {}
    for book, filename in zip(BOOKS, BYZTXT_BOOKS, strict=True):
        raw = (folder / f"{filename}.UTR").read_text()
        raw = re.sub(r"\(\d+:\d+\)", "", raw)
        raw = re.sub(r"\|([^|]*)\|([^|]*)\|", lambda m: m[2], raw)
        chunks = re.split(r"(\d+:\d+)", raw)
        require(not chunks[0].strip(), f"Unparsed UTR header: {filename}")
        for ref, body in zip(chunks[1::2], chunks[2::2], strict=True):
            if "[" in body:
                body = body[: body.index("[")]
            body = body.translate(str.maketrans("vxc", "scx"))
            _, tokens = bp5_line(ref.replace(":", ".") + " " + plain(body))
            key = f"{book} {ref}"
            require(key not in text, f"Duplicate UTR verse: {key}")
            text[key], tags[key] = [t["word"] for t in tokens], tokens
    require(len(text) == 7957, f"UTR inventory: {len(text)}, expected 7957")
    return text, tags


# The printed RP2026, read from the Guardian Press PDF's font-separated XML.


def apparatus_diacritics(root: ET.Element) -> list[Diacritic]:
    """Supplement the letter collation from explicit printed TR contrasts.

    This reads only same-letter contrasts actually printed in the apparatus;
    it does not invent an accented Scrivener text from unaccented files.
    """
    book = -1
    found: list[Diacritic] = []
    for page in root.findall("page"):
        nodes = page.findall("text")
        for node in nodes:
            if node.get("font") == "23" and re.search(
                "[Α-Ω]", "".join(node.itertext())
            ):
                book += 1
        at = 0
        while at < len(nodes):
            if nodes[at].get("font") != "11":
                at += 1
                continue
            end = at + 1
            while end < len(nodes) and nodes[end].get("font") != "11":
                end += 1
            batch, at = nodes[at:end], end
            refs = ["".join(n.itertext()) for n in batch if n.get("font") == "4"]
            if len(refs) != 1:
                continue
            text = " ".join("".join(n.itertext()) for n in batch[2:])
            parts = text.split("¦")
            base = parts[0].strip()
            for part in parts[1:]:
                match = re.search(
                    rf"\bTR\s+([{GREEK}][{GREEK}\s]*)",
                    part,
                )
                if match:
                    source = match[1].strip()
                    if ascii_greek(base) == ascii_greek(source) and base != source:
                        found.append(
                            {
                                "ref": f"{BOOKS[book]} {refs[0]}",
                                "from": source,
                                "to": base,
                                "page": int(cast(str, page.get("number"))),
                                "apparatus": text,
                            }
                        )
    return found


# An apparatus entry's letter: a to z, then aa, bb; c and j as the font maps them.
CALLER = "[a-zϲϳ]{1,2}"
# The printed apparatus's fonts: an entry's letter, its reference, the
# editions' sigla, its Greek, and its italic (om.).
APPARATUS_FONTS = {
    "11": "RPTimesNewRoman",
    "4": "RPTimesNewRomanBold",
    "27": "Gentium",
    "3": "RPTimesNewRoman",
    "9": "RPTimesNewRomanItalic",
}


def apparatus(root: ET.Element, verses: Mapping[str, PrintedVerse]) -> list[BoydNote]:
    """The printed apparatus's entries that give the Received Text a reading
    (TR or SCR), in the shape of Boyd's notes (inventories.boyd): the reference
    and the main text's words, each other reading with its sigla, the page,
    and the place of the entry's caller among its verse's printed words (as
    printed reads them). An entry opens with its letter and reference; the
    manuscript apparatus below it names no edition and so gives no such
    reading."""
    called = {key: ref for ref, verse in verses.items() for key in verse["callers"]}
    for code, family in APPARATUS_FONTS.items():
        spec = root.find(f".//fontspec[@id='{code}']")
        require(
            spec is not None and (spec.get("family") or "").endswith("+" + family),
            f"Changed Guardian apparatus font: {code}",
        )
    book = -1
    entries: list[tuple[str, str, str, list[tuple[bool, str]]]] = []
    for page in root.findall("page"):
        nodes = page.findall("text")
        current: list[tuple[bool, str]] | None = None
        for index, node in enumerate(nodes):
            font, words = node.get("font"), "".join(node.itertext()).strip()
            if font == "23" and re.search("[Α-Ω]", words):
                book += 1
                current = None
                continue
            following = nodes[index + 1].get("font") if index + 1 < len(nodes) else None
            if font == "11" and following == "4" and book >= 0:
                current = []
                ref = "".join(nodes[index + 1].itertext()).strip()
                entries.append(
                    (BOOKS[book], ref, f"{page.get('number')} {words}", current)
                )
            elif current is None or font == "4" and not current:
                continue
            elif font == "27":
                current.extend((True, s) for s in words.split())
            elif (
                font == "11"
                and words == "mg"
                and current
                and current[-1] == (True, "RP")
            ):
                current[-1] = (True, "RPmg")
            elif font in ("3", "9"):
                current.extend((False, t) for t in words.replace("¦", " ¦ ").split())
            elif font in ("24", "25", "26"):
                current = None
    rows: list[BoydNote] = []
    for book_code, ref, caller, tokens in entries:
        parts: list[list[tuple[bool, str]]] = [[]]
        for is_siglum, token in joined(tokens):
            if not is_siglum and token == "¦":
                parts.append([])
            else:
                parts[-1].append((is_siglum, token))
        if len(parts) < 2:
            continue
        variants: list[BoydReading] = [
            {"reading": reading(part), "sigla": [t for s, t in part if s]}
            for part in parts[1:]
        ]
        tr = [v for v in variants if {"TR", "SCR"}.intersection(v["sigla"])]
        if not tr:
            continue
        require(
            re.fullmatch(r"\d+:\d+(?:–\d+(?::\d+)?)?", ref),
            f"Unparsed RP2026 apparatus reference: {book_code} {ref}",
        )
        at = called.get(caller)
        rows.append(
            {
                "entry": len(rows) + 1,
                "position": (
                    None
                    if at is None
                    else {
                        "ref": at,
                        "words": verses[at]["Greek"],
                        "offset": verses[at]["callers"][caller],
                    }
                ),
                "target_ref": f"{book_code} {ref.split('–')[0]}",
                "fr": ref,
                "rp": reading(parts[0]),
                "variants": variants,
                "tr": tr,
                "raw": " ".join(t for _, t in tokens),
                "page": int(caller.split()[0]),
            }
        )
    return rows


def joined(tokens: list[tuple[bool, str]]) -> list[tuple[bool, str]]:
    """An entry's words, with those broken at a line end put together."""
    result: list[tuple[bool, str]] = []
    for is_siglum, token in tokens:
        if (
            result
            and not is_siglum
            and not result[-1][0]
            and result[-1][1].endswith("-")
        ):
            result[-1] = (False, result[-1][1][:-1] + token)
        else:
            result.append((is_siglum, token))
    return result


def reading(part: list[tuple[bool, str]]) -> str:
    """A reading of the printed apparatus as Boyd writes his: its words without
    the editors' sigla, brackets, or remarks, an omission as ---, and the
    numeral sign as Boyd's."""
    words = " ".join(t for s, t in part if not s)
    # Square brackets mark an edition that brackets the words; a remark in
    # parentheses refers the reader elsewhere.
    words = re.sub(r"\[+\s*\]+|\(\s*(?:ϲf\.|See)[^)]*\)", "", words).strip()
    # A verse's number stands bare among Boyd's words, and a letter that may
    # stand is in parentheses.
    words = re.sub(r"\[(\d+)\]", r"\1", words)
    words = re.sub(r"\(([νς])\)", r"\1", words)
    words = re.sub("[\u0374\u02b9]", "\u0384", words)
    return "---" if words == "om." else words


def tree(path: Content) -> ET.Element:
    """The Guardian PDF as pdftohtml XML."""
    return ET.fromstring(path.read_bytes())


def pages(path: Content) -> dict[int, ET.Element]:
    return {int(cast(str, p.get("number"))): p for p in tree(path).findall("page")}


def page_text(pages: Iterable[ET.Element], main: bool = True) -> str:
    """The scripture (font 25) or the apparatus of pages, hyphenation joined."""
    return " ".join(
        "".join(n.itertext())
        for p in pages
        for n in p.findall("text")
        if (n.get("font") == "25") == main
    ).replace("- ", "")


def printed(
    root: ET.Element, omitted: frozenset[str], last: str
) -> tuple[dict[str, PrintedVerse], list[Diacritic]]:
    """The printed RP2026: per verse, ascii forms, accented words, and page; and
    the same-letter accent contrasts its apparatus prints against the TR. The
    text ends with its last verse, which RP2018 also ends with."""
    spec = root.find(".//fontspec[@id='25']")
    require(
        spec is not None
        and spec.get("size") == "17"
        and (spec.get("family") or "").endswith("+RPTimesNewRoman"),
        "Changed Guardian scripture font",
    )
    book = -1
    ref: str | None = None
    ch = 0
    pending_ch: int | None = None
    chunks: collections.defaultdict[str, list[str]] = collections.defaultdict(list)
    pages: dict[str, int] = {}
    for page in root.findall("page"):
        nodes = page.findall("text")
        number = int(cast(str, page.get("number")))
        below = False
        for index, node in enumerate(nodes):
            font = node.get("font")
            text = "".join(node.itertext()).strip()
            following = nodes[index + 1].get("font") if index + 1 < len(nodes) else None
            # The apparatus begins with its first entry; no caller stands
            # below it, though its Greek has the same font.
            below |= font == "11" and following == "4"
            if (
                font == "3"
                and not below
                and ref is not None
                and re.fullmatch(CALLER, text)
            ):
                # An entry's caller, in the text before the words it is about.
                chunks[ref].append(f"\0{number} {text}\0")
            elif font == "23" and re.search("[Α-Ω]", text):
                book += 1
                require(
                    book < len(BOOKS), "Unexpected additional Guardian book heading"
                )
                ch = 0
                ref = None
            elif font == "24" and re.fullmatch("[0-9]+", text):
                # A drop cap is sometimes printed beside the preceding
                # chapter's closing line. The explicit verse-1 numeral,
                # where present, is the actual scripture boundary.
                next_verse = next(
                    (
                        "".join(n.itertext()).strip()
                        for n in nodes[index + 1 :]
                        if n.get("font") in ("24", "26")
                    ),
                    None,
                )
                if next_verse == "1":
                    pending_ch = int(text)
                    continue
                ch = int(text)
                ref = f"{BOOKS[book]} {ch}:1"
                pages[ref] = int(cast(str, page.get("number")))
            elif font == "26" and re.fullmatch("[0-9]+", text):
                # The back matter after the last verse prints numerals in
                # the verse font; the text ended with that verse.
                if ref == last and chunks[ref]:
                    continue
                if pending_ch is not None:
                    require(text == "1", "Chapter boundary lacks expected verse 1")
                    ch = pending_ch
                    pending_ch = None
                ref = f"{BOOKS[book]} {ch}:{int(text)}"
                pages[ref] = int(cast(str, page.get("number")))
            elif font == "25" and ref is not None:
                chunks[ref].append(text)
    require(book == 26, f"Expected 27 book openings, got {book + 1}")
    result: dict[str, PrintedVerse] = {}
    # Where the text omits a verse or moves it away, it may print its number
    # and the caller of the entry that gives its words, and nothing else.
    held: dict[str, dict[str, int]] = {}
    for ref, pieces in chunks.items():
        marked = re.sub(rf"-\s+(?=[{GREEK}])", "", " ".join(pieces))
        # The text and the callers alternate; c and j map to Greek letters.
        pieces = re.split("\0([^\0]*)\0", marked)
        callers: dict[str, int] = {}
        for at in range(1, len(pieces), 2):
            callers[pieces[at]] = len(
                re.findall(rf"[{GREEK}]+", " ".join(pieces[0:at:2]))
            )
        raw = " ".join(pieces[0::2])
        forms = [
            ascii_greek("".join(accent_letters(w)))
            for w in re.findall(rf"[{GREEK}]+", raw)
        ]
        words = unicodedata.normalize("NFC", raw).split()
        if not words:
            held[ref] = callers
            continue
        if any(not re.fullmatch("[a-z]+", w) for w in forms):
            raise CheckFailed(f"Unknown Greek letters at {ref}")
        result[ref] = {
            "Greek": forms,
            "accented": words,
            "page": pages[ref],
            "callers": callers,
        }
    for ref in omitted:
        require(ref not in result, f"Unexpected printed omitted verse: {ref}")
        result[ref] = {
            "Greek": [],
            "accented": [],
            "page": None,
            "callers": held.get(ref, {}),
        }
    require(
        len(result) == 7957, f"Printed RP2026 inventory: {len(result)}, expected 7957"
    )
    return result, apparatus_diacritics(root)


# RP's own marginal alternates, from the CCAT files.

BETA = str.maketrans("", "", "/\\=()|*+'?:;.,·-—[]")


def beta_words(text: str) -> list[str]:
    """Upper-case Beta code to the BP5 ascii alphabet, accents and stops gone."""
    return [w for w in text.translate(BETA).lower().split() if w.isalpha()]


def marginal_alternates(folder: Content) -> dict[str, list[MarginalAlternate]]:
    """Each verse's `{B main > alternate}` groups: RP's marginal readings,
    where the Byzantine manuscripts are divided. Positions are RP2018 token
    offsets of the main words, located nearest the group's place in the line.
    """
    result: dict[str, list[MarginalAlternate]] = {}
    for number, book in enumerate(BOOKS, 1):
        paths = list(folder.glob(f"{number:02d}_*.TXT"))
        require(len(paths) == 1, f"Expected one CCAT file for {book}: {paths}")
        for line in paths[0].read_text(encoding="latin-1").splitlines():
            m = re.match(r"(\d+):(\d+)\s*(.*)", line)
            if not m or "{B" not in m[3]:
                continue
            ref = f"{book} {int(m[1])}:{int(m[2])}"
            body = m[3]
            main_text = beta_words(re.sub(r"\{[^}]*\}", " ", body))
            groups: list[MarginalAlternate] = []
            for g in re.finditer(r"\{B([^}>]*)>([^}]*)\}", body):
                main, alt = beta_words(g[1]), beta_words(g[2])
                if not main:
                    continue
                at = len(beta_words(re.sub(r"\{[^}]*\}", " ", body[: g.start()])))
                starts = occurrences(main_text, main)
                if not starts:
                    continue
                start = min(
                    starts, key=lambda s: min(abs(s - at), abs(s + len(main) - at))
                )
                groups.append(
                    {
                        "range": [start, start + len(main)],
                        "main": main,
                        "alternate": alt,
                    }
                )
            if groups:
                result[ref] = groups
    return result
