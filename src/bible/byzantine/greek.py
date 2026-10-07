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
from bible.byzantine.rows import Token
from bible.sources import BYZTXT_BOOKS, Content
from bible.usfm import GREEK

# A Greek text's words, by "BOOK c:v"; and a parsed text's tokens.
Text = dict[str, list[str]]
Tags = dict[str, list[Token]]


class PrintedVerse(TypedDict):
    """A verse of the printed RP2026: its unaccented forms, its accented
    words, and its page (none for a verse the text omits)."""

    Greek: list[str]
    accented: list[str]
    page: int | None


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
        if chunks[0].strip():
            raise ValueError(f"Unparsed Scrivener header: {filename}")
        for ref, body in zip(chunks[1::2], chunks[2::2], strict=True):
            body = body.lower().translate(str.maketrans("vycqx", "sqxyc"))
            if re.search(r"[^a-z\s]", body):
                raise ValueError(f"Unparsed Scrivener verse: {book} {ref}")
            key = f"{book} {ref}"
            if key in result:
                raise ValueError(f"Duplicate Scrivener verse: {key}")
            result[key] = body.split()
    if len(result) != 7957:
        raise ValueError(f"Scrivener inventory: {len(result)}, expected 7957")
    return result


def accent_letters(text: str) -> list[str]:
    """Lowercase letters with their combining marks, without punctuation.
    Lunate sigma and the numeral stigma use the pinned text's sigma form."""
    result: list[str] = []
    for letter in unicodedata.normalize("NFD", text.lower()):
        if unicodedata.combining(letter):
            if not result:
                raise ValueError(f"Greek mark without a letter: {text}")
            result[-1] += letter
        elif letter.isalpha():
            result.append(letter.replace("ϲ", "σ").replace("ϛ", "ς"))
        elif not letter.isspace() and letter not in ",.;··:!?ʼ’'᾽—-()´":
            raise ValueError(f"Unknown Greek character: {text}")
    if any(ord(c[0]) not in LATIN for c in result):
        raise ValueError(f"Unknown Greek letters: {text}")
    return result


def with_accents(words: Sequence[str], accented: Sequence[str]) -> list[str]:
    """Transfer only marks onto the pinned letters and word boundaries.
    The caller has checked any final ν/ς difference before transferring."""
    letters = accent_letters(" ".join(accented))
    plain = "".join(words)
    forms = "".join(ascii_greek(c) for c in letters)
    if forms != plain:
        if forms in (plain + "n", plain + "s"):
            letters.pop()
        elif plain in (forms + "n", forms + "s"):
            letters.append(greek_letters([plain[-1]])[0])
        else:
            raise ValueError(f"Cannot transfer Greek accents: {words} / {accented}")
    result = []
    at = 0
    for word, greek in zip(words, greek_letters(words), strict=True):
        marked = "".join(
            base + "".join(c for c in letter if unicodedata.combining(c))
            for base, letter in zip(greek, letters[at : at + len(word)], strict=True)
        )
        result.append(unicodedata.normalize("NFC", marked))
        at += len(word)
    return result


def accented_scrivener(path: Content, tr: Mapping[str, list[str]]) -> Text:
    """Align Honza's accented transcription within each book, ignoring verse
    boundaries. Only a two-word division or a single final ν/ς may differ;
    no words may be inserted, dropped or substituted. Refuse ambiguous local
    alignments, and name both sources' verse addresses in diagnostics."""
    source: Text = {}
    for row in json.loads(path.read_text()):
        ref = f"{row['book_name_short']} {row['chapter']}:{row['verse']}"
        if ref in source:
            raise ValueError(f"Duplicate accented Scrivener verse: {ref}")
        source[ref] = [
            unicodedata.normalize("NFC", "".join(accent_letters(w["greek"])))
            for w in row["words"]
        ]
        if any(not w for w in source[ref]):
            raise ValueError(f"Empty accented Scrivener word: {ref}")
    if set(source) != set(tr):
        raise ValueError(
            "Accented Scrivener verse inventory differs from the pinned TR"
        )
    result: Text = {ref: [] for ref in tr}
    for book in BOOKS:
        target = [
            (ref, w) for ref, ws in tr.items() if ref.split()[0] == book for w in ws
        ]
        supplied = [
            (ref, w) for ref, ws in source.items() if ref.split()[0] == book for w in ws
        ]
        forms = [ascii_greek(w) for _, w in supplied]
        i = j = 0
        while i < len(target) and j < len(supplied):
            matches: list[tuple[int, int]] = []
            for a, b in ((1, 1), (1, 2), (2, 1)):
                if i + a > len(target) or j + b > len(supplied):
                    continue
                left = "".join(w for _, w in target[i : i + a])
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
                raise ValueError(
                    f"{kind} accented Scrivener alignment at {target[i][0]} / "
                    f"{supplied[j][0]}: {target[i:i+2]} / {supplied[j:j+2]}"
                )
            a, b = matches[0]
            marked = with_accents(
                [w for _, w in target[i : i + a]],
                [w for _, w in supplied[j : j + b]],
            )
            for (ref, _), word in zip(target[i : i + a], marked, strict=True):
                result[ref].append(word)
            i, j = i + a, j + b
        if i != len(target) or j != len(supplied):
            raise ValueError(
                f"Unaligned accented Scrivener tail in {book}: "
                f"{target[i:i+2]} / {supplied[j:j+2]}"
            )
    return result


BP5_LINE = re.compile(r"(\d+)\.(\d+)\s*(.*)")
BP5_TOKEN = re.compile(r"([a-z]+)\s+((?:(?:\d+|\{[^}]+\})\s*)+)")
BP5_PARSE = re.compile(r"\{([^}]+)\}")
BP5_NUMBER = re.compile(r"\d+")


def bp5_line(line: str) -> tuple[str, list[Token]]:
    match = BP5_LINE.fullmatch(line)
    if not match:
        raise ValueError(f"Unparsed BP5 line: {line}")
    body = match[3]
    tokens: list[Token] = []
    at = 0
    for word in BP5_TOKEN.finditer(body):
        if body[at : word.start()].strip():
            raise ValueError(f"Unparsed BP5 token: {body[at:word.start()]}")
        parses = BP5_PARSE.findall(word[2])
        strong = [int(n) for n in BP5_NUMBER.findall(BP5_PARSE.sub("", word[2]))]
        if not parses or not strong:
            raise ValueError(f"Missing BP5 annotation: {word[0]}")
        tokens.append({"word": word[1], "strong": strong, "parse": parses})
        at = word.end()
    if body[at:].strip():
        raise ValueError(f"Unparsed BP5 tail: {body[at:]}")
    return f"{int(match[1])}:{int(match[2])}", tokens


def rp2018(folder: Content) -> tuple[Text, Tags]:
    text: Text = {}
    tags: Tags = {}
    for number, book in enumerate(BOOKS, 1):
        paths = list(folder.glob(f"{number:02d}_*.BP5"))
        if len(paths) != 1:
            raise ValueError(f"Expected one BP5 file for {book}: {paths}")
        for line in paths[0].read_text().splitlines():
            ref, tokens = bp5_line(line)
            key = f"{book} {ref}"
            if key in text:
                raise ValueError(f"Duplicate RP verse: {key}")
            text[key] = [t["word"] for t in tokens]
            tags[key] = tokens
    if len(text) != 7957:
        raise ValueError("Unexpected RP2018 verse inventory")
    return text, tags


def rp2026(text: Mapping[str, list[str]], printed: Mapping[str, PrintedVerse]) -> Text:
    """RP2018 with the Appendix A patches, which must equal the printed text."""
    result = dict(text)
    for ref, (old, new) in PATCHES.items():
        positions = occurrences(text[ref], old)
        if len(positions) != 1:
            raise ValueError(f"Stale Appendix A patch: {ref}")
        at = positions[0]
        result[ref] = text[ref][:at] + new + text[ref][at + len(old) :]
    differences = [
        ref
        for ref in result
        if ref not in printed or result[ref] != printed[ref]["Greek"]
    ]
    if differences or set(printed) != set(result):
        raise ValueError(
            f"RP2026 disagrees with the printed Guardian text: {differences[:10]}"
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
        if chunks[0].strip():
            raise ValueError(f"Unparsed UTR header: {filename}")
        for ref, body in zip(chunks[1::2], chunks[2::2], strict=True):
            if "[" in body:
                body = body[: body.index("[")]
            body = body.translate(str.maketrans("vxc", "scx"))
            _, tokens = bp5_line(ref.replace(":", ".") + " " + " ".join(body.split()))
            key = f"{book} {ref}"
            if key in text:
                raise ValueError(f"Duplicate UTR verse: {key}")
            text[key], tags[key] = [t["word"] for t in tokens], tokens
    if len(text) != 7957:
        raise ValueError(f"UTR inventory: {len(text)}, expected 7957")
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
    path: Content, omitted: frozenset[str], last: str
) -> tuple[dict[str, PrintedVerse], list[Diacritic]]:
    """The printed RP2026: per verse, ascii forms, accented words and page; and
    the same-letter accent contrasts its apparatus prints against the TR. The
    text ends with its last verse, which RP2018 also ends with."""
    root = tree(path)
    spec = root.find(".//fontspec[@id='25']")
    if (
        spec is None
        or spec.get("size") != "17"
        or not (spec.get("family") or "").endswith("+RPTimesNewRoman")
    ):
        raise ValueError("Changed Guardian scripture font")
    book = -1
    ref: str | None = None
    ch = 0
    pending_ch: int | None = None
    chunks: collections.defaultdict[str, list[str]] = collections.defaultdict(list)
    pages: dict[str, int] = {}
    for page in root.findall("page"):
        nodes = page.findall("text")
        for index, node in enumerate(nodes):
            font = node.get("font")
            text = "".join(node.itertext()).strip()
            if font == "23" and re.search("[Α-Ω]", text):
                book += 1
                if book >= len(BOOKS):
                    raise ValueError("Unexpected additional Guardian book heading")
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
                    if text != "1":
                        raise ValueError("Chapter boundary lacks expected verse 1")
                    ch = pending_ch
                    pending_ch = None
                ref = f"{BOOKS[book]} {ch}:{int(text)}"
                pages[ref] = int(cast(str, page.get("number")))
            elif font == "25" and ref is not None:
                chunks[ref].append(text)
    if book != 26:
        raise ValueError(f"Expected 27 book openings, got {book + 1}")
    result: dict[str, PrintedVerse] = {}
    for ref, pieces in chunks.items():
        raw = re.sub(rf"-\s+(?=[{GREEK}])", "", " ".join(pieces))
        raw = "".join(c if c.isalpha() or c.isspace() else " " for c in raw)
        words = re.findall(rf"[{GREEK}]+", raw)
        forms = [ascii_greek(w.replace("ϲ", "σ").replace("Ϲ", "Σ")) for w in words]
        if any(not re.fullmatch("[a-z]+", w) for w in forms):
            raise ValueError(f"Unknown Greek letters at {ref}")
        result[ref] = {"Greek": forms, "accented": words, "page": pages[ref]}
    for ref in omitted:
        if ref in result:
            raise ValueError(f"Unexpected printed omitted verse: {ref}")
        result[ref] = {"Greek": [], "accented": [], "page": None}
    if len(result) != 7957:
        raise ValueError(f"Printed RP2026 inventory: {len(result)}, expected 7957")
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
        if len(paths) != 1:
            raise ValueError(f"Expected one CCAT file for {book}: {paths}")
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
