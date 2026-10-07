"""The published Greek variation inventories: Robinson's collation of Scrivener
against RP2018, Boyd's TCGNT apparatus (and the TCENT English apparatus, which
shares its syntax), and Boyd's Appendix C word breaks. Readers keep every entry
and fail on a changed count."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from html import escape
from typing import Any

from bible.byzantine import BOOKS
from bible.byzantine.greek import ascii_greek, greek_words
from bible.byzantine.rows import BoydNote, BoydReading, CollationRow
from bible.sources import Content
from bible.usfm import GREEK

HEADINGS = [
    "ΚΑΤΑ ΜΑΤΘΑΙΟΝ",
    "ΚΑΤΑ ΜΑΡΚΟΝ",
    "ΚΑΤΑ ΛΟΥΚΑΝ",
    "ΚΑΤΑ ΙΩΑΝΝΗΝ",
    "ΠΡΑΞΕΙΣ ΑΠΟΣΤΟΛΩΝ",
    "ΠΡΟΣ ΡΩΜΑΙΟΥΣ",
    "ΠΡΟΣ ΚΟΡΙΝΘΙΟΥΣ Α",
    "ΠΡΟΣ ΚΟΡΙΝΘΙΟΥΣ Β",
    "ΠΡΟΣ ΓΑΛΑΤΑΣ",
    "ΠΡΟΣ ΕΦΕΣΙΟΥΣ",
    "ΠΡΟΣ ΦΙΛΙΠΠΗΣΙΟΥΣ",
    "ΠΡΟΣ ΚΟΛΟΣΣΑΕΙΣ",
    "ΠΡΟΣ ΘΕΣΣΑΛΟΝΙΚΕΙΣ Α",
    "ΠΡΟΣ ΘΕΣΣΑΛΟΝΙΚΕΙΣ Β",
    "ΠΡΟΣ ΤΙΜΟΘΕΟΝ Α",
    "ΠΡΟΣ ΤΙΜΟΘΕΟΝ Β",
    "ΠΡΟΣ ΤΙΤΟΝ",
    "ΠΡΟΣ ΦΙΛΗΜΟΝΑ",
    "ΠΡΟΣ ΕΒΡΑΙΟΥΣ",
    "ΙΑΚΩΒΟΥ",
    "ΠΕΤΡΟΥ Α",
    "ΠΕΤΡΟΥ Β",
    "ΙΩΑΝΝΟΥ Α",
    "ΙΩΑΝΝΟΥ Β",
    "ΙΩΑΝΝΟΥ Γ",
    "ΙΟΥΔΑ",
    "ΑΠΟΚΑΛΥΨΙΣ ΙΩΑΝΝΟΥ",
]
SIGLA = r"(?:ANT|BYZ|CT|ECM[*†]?|HF|NA(?: ?2[78])?|PCK|SBL|SCR|ST|TH|TR|WH|K|Αν)"
# Boyd's TCENT prints ACT once, at Jas 5:11, where his TCGNT note on the same
# reading has ANT. The reader corrects it there; `tcent` refuses a changed count.
TCENT_ERRATA = {("JAS", "5:11"): ("ACT", "ANT")}


def reading_words(reading: str) -> list[str] | None:
    """Read a plain quotation, optional nu, and labelled parenthetical variant.

    Ellipses and structural descriptions require their own matching; refuse
    them here. Keep the raw reading in the inventory for review.
    """
    reading = reading.replace("(ν)", "ν")
    # Boyd writes these numeral abbreviations with the Greek numeral sign;
    # the electronic Scrivener keeps the letters without that sign.
    reading = re.sub(r"\b(ιβ|ρμδ|χξς|κδ)΄", r"\1", reading)
    reading = re.sub(rf"\([^()]*\s{SIGLA}(?:\s{SIGLA})*\)", "", reading)
    words = ascii_greek(reading).replace("---", "").split()
    if any(not word.isalpha() or not word.isascii() for word in words):
        return None
    return words


def word_breaks(path: Content) -> dict[str, list[str]]:
    """Boyd's Appendix C splits, for locating quotations only.

    Every alias preserves every letter. The numeral spelling difference
    remains a difference; only its explicitly described word break is used.
    """
    root = ET.fromstring(path.read_bytes())
    splits: dict[str, list[str]] = {}
    for row in root.iter("row"):
        readings: list[list[str] | None] = []
        for cell in row:
            # A footnote explains one homograph; it is not a table reading.
            text = (cell.text or "") + "".join(
                ("" if c.tag == "note" else "".join(c.itertext())) + (c.tail or "")
                for c in cell
            )
            readings.extend(reading_words(r) for r in text.split("|"))
        words = [r for r in readings if r is not None]
        if len(words) != len(readings) or len({"".join(r) for r in words}) != 1:
            raise ValueError("Unparsed Appendix C word break")
        canonical = max(words, key=len)
        for reading in words:
            if len(reading) == 1 and len(canonical) > 1:
                word = reading[0]
                if word in splits and splits[word] != canonical:
                    raise ValueError(f"Ambiguous Appendix C split: {word}")
                splits[word] = canonical
    prose = " ".join(" ".join(p.itertext()) for p in root.iter("para"))
    match = re.search(
        r"The word (\S+) in editions of the Textus Receptus is written as (\S+ \S+) for the purposes of comparison",
        prose,
    )
    if not match:
        raise ValueError("Missing Appendix C numeral explanation")
    word, divided = ascii_greek(match[1]), reading_words(match[2])
    if divided is None or word != "".join(divided):
        raise ValueError("Changed Appendix C numeral explanation")
    splits[word] = divided
    if len(list(root.iter("row"))) != 38:
        raise ValueError("Changed Appendix C table inventory")
    return splits


def collation(path: Content) -> list[CollationRow]:
    headings = dict(zip(HEADINGS, BOOKS, strict=True))
    rows: list[CollationRow] = []
    book: str | None = None
    ref: str | None = None
    pending = ""

    def finish() -> None:
        nonlocal pending
        if not pending:
            return
        if pending.count("]") != 1 or not ref:
            raise ValueError(f"Unparsed collation entry: {pending}")
        raw = pending
        pending = ""
        if "(RP 2005)" in raw:
            return
        text = re.sub(r"\([^)]*\)", "", raw)
        rp, tr = [s.strip().replace("―", "") for s in text.split("]")]
        forms = [ascii_greek(s).split() for s in (tr, rp)]
        if any(re.search(r"[^a-z\s]", ascii_greek(s)) for s in (tr, rp)):
            raise ValueError(f"Unparsed collation reading: {raw}")
        rows.append(
            {
                "entry": len(rows) + 1,
                "target_ref": ref,
                "tr": forms[0],
                "rp": forms[1],
                "raw": raw,
            }
        )

    for line in path.read_text().replace("\f", "").splitlines():
        line = line.strip()
        if line in headings:
            finish()
            book, ref = headings[line], None
            continue
        if not book or not line or line == "- end -":
            continue
        match = re.match(r"^(\d+:\d+)\s*(.*)$", line)
        if match:
            finish()
            ref, pending = f"{book} {match[1]}", match[2]
        elif "]" in line and "]" in pending:
            finish()
            pending = line
        else:
            pending = (pending + " " + line).strip()
    finish()
    if len(rows) != 1885:
        raise ValueError(f"Collation inventory: {len(rows)}, expected 1885")
    return rows


def note_positions(root: ET.Element) -> dict[int, dict[str, Any]]:
    """Keep note locations in the main text, including paragraph continuations.

    Notes precede their reading in Boyd's USX. Apparatus text never contributes
    words to the main-text position.
    """
    positions: dict[int, tuple[str, int]] = {}
    verses: dict[str, list[str]] = {}
    current: str | None = None

    def text(value: str | None) -> None:
        if current and value:
            verses[current].extend(greek_words(value))

    def walk(node: ET.Element) -> None:
        nonlocal current
        if node.tag == "verse":
            current = node.get("sid")
            if current:
                verses.setdefault(current, [])
            return
        if node.tag == "note":
            if current:
                positions[id(node)] = (current, len(verses[current]))
            return
        text(node.text)
        for child in node:
            walk(child)
            text(child.tail)

    walk(root)
    return {
        key: {"ref": ref, "offset": offset, "words": verses[ref]}
        for key, (ref, offset) in positions.items()
    }


def boyd_markup(node: ET.Element, *, notes: bool = False) -> str:
    """Source USX inline formatting for display, excluding apparatus from passages."""
    if node.tag in {"verse", "chapter"} or (node.tag == "note" and not notes):
        return ""
    value = escape(node.text or "")
    for child in node:
        value += boyd_markup(child, notes=notes) + escape(child.tail or "")
    tag = {"it": "i", "add": "i", "bd": "b", "+it": "i", "+bd": "b"}.get(
        node.get("style", "")
    )
    return f"<{tag}>{value}</{tag}>" if tag else value


def boyd_passages(root: ET.Element) -> dict[str, str]:
    """Collect source verses and paragraph continuations without their notes."""
    passages: dict[str, str] = {}
    current: str | None = None

    def append(value: str) -> None:
        if current and value:
            passages[current] = passages.get(current, "") + value

    def walk(node: ET.Element) -> None:
        nonlocal current
        if node.tag == "verse":
            current = node.get("sid")
            if current:
                passages.setdefault(current, "")
            return
        if node.tag == "chapter":
            current = None
            return
        if node.tag == "note":
            return
        if node.tag == "para":
            if node.get("style") not in {"p", "q", "q1", "q2", "m", "nb", "b"}:
                return
            if node.get("vid"):
                current = node.get("vid")
            append(" ")
        if node.tag == "char":
            append(boyd_markup(node))
            return
        append(escape(node.text or ""))
        for child in node:
            walk(child)
            append(escape(child.tail or ""))

    walk(root)
    return {ref: " ".join(value.split()) for ref, value in passages.items()}


def boyd(folder: Content, *, greek: bool = True) -> list[BoydNote]:
    """Read Boyd's Greek or English USX apparatus, retaining its sigla.

    English notes do not acquire Greek token positions. Both publications use
    the same apparatus syntax; their wording is retained without translation.
    """
    rows: list[BoydNote] = []
    for book in BOOKS:
        paths = list(folder.glob(f"*{book}.usx"))
        if len(paths) != 1:
            raise ValueError(f"{folder}: expected one Boyd USX file: {book}")
        try:
            root = ET.fromstring(paths[0].read_bytes())
        except ET.ParseError as error:
            raise ValueError(f"{paths[0]}: {error}") from error
        positions = note_positions(root) if greek else {}
        passages = {} if greek else boyd_passages(root)
        for note in root.iter("note"):
            if note.get("style") != "f":
                continue
            fields = [c for c in note if c.get("style") == "fr"]
            if not fields:
                continue
            fr = "".join(fields[0].itertext()).strip()
            # Structural notes have verse-number fields followed by bare tails.
            # Reading only ft elements silently drops their TR/SCR sigla.
            body = (note.text or "") + "".join(
                ("" if c.get("style") == "fr" else "".join(c.itertext()))
                + (c.tail or "")
                for c in note
            )
            body = re.sub(r"\s+", " ", body).strip()
            original = body
            body = re.sub(r"[\[{]Note:.*?[\]}]", "", body).strip()
            if "¦" not in body:
                continue
            main, *parts = body.split("¦")
            if not greek:
                # Coalesced English readings can carry several Greek edition
                # support figures. They are apparatus metadata, not English.
                # Remove the closed annotations before stripping the final
                # figure; otherwise that strip leaves a truncated brace group.
                main = re.sub(
                    rf"\s*[\[{{](?:(?:{SIGLA}|[\d.]+%)\s*)+[\]}}]",
                    "",
                    main,
                )
            variants: list[BoydReading] = []
            erratum = None if greek else TCENT_ERRATA.get((book, fr))
            for part in parts:
                if erratum:
                    part = re.sub(rf"(?<!\w){erratum[0]}(?!\w)", erratum[1], part)
                sigla = re.findall(rf"(?<!\w){SIGLA}(?!\w)", part)
                tail = rf"(?:\s+(?:{SIGLA}|[\[{{]?[\d.]+%[\]}}]?))+\s*$"
                reading = re.sub(tail, "", part).strip()
                variants.append({"reading": reading, "sigla": sigla})
            # A labelled spelling alternative can stand inside the main
            # reading, rather than after a separator (Acts 10:30). Its
            # preceding token supplies the exact replacement boundary.
            inset = re.compile(
                rf"(?P<word>[{GREEK}]+)\s+"
                rf"\((?P<reading>[{GREEK}]+)\s+"
                rf"(?P<sigla>{SIGLA}(?:\s+{SIGLA})*)\)"
            )
            matches = list(inset.finditer(main)) if greek else []
            if any({"TR", "SCR"} & set(m["sigla"].split()) for m in matches):
                clean = inset.sub(lambda m: m["word"], main)
                for match in matches:
                    sigla = match["sigla"].split()
                    if not {"TR", "SCR"} & set(sigla):
                        continue
                    before = inset.sub(lambda m: m["word"], main[: match.start()])
                    after = inset.sub(lambda m: m["word"], main[match.end() :])
                    reading = before + match["reading"] + after
                    variants.append(
                        {
                            "reading": re.sub(
                                r"\s*[\[{]?[\d.]+%[\]}]?$", "", reading.strip()
                            ).strip(),
                            "sigla": sigla,
                        }
                    )
                main = clean
            tr = [v for v in variants if {"TR", "SCR"}.intersection(v["sigla"])]
            if not tr:
                continue
            if not re.fullmatch(r"\d+:\d+(?:[–\-,]\d+)*", fr):
                raise ValueError(f"Unparsed Boyd reference: {book} {fr}")
            target = f"{book} {re.split('[–,-]', fr)[0]}"
            passage_refs = [target]
            if not greek and re.fullmatch(r"\d+:\d+[–-]\d+", fr):
                chapter, interval = fr.split(":")
                first, last = map(int, re.split("[–-]", interval))
                passage_refs = [f"{book} {chapter}:{n}" for n in range(first, last + 1)]
            elif not greek and "," in fr:
                chapter, numbers = fr.split(":")
                passage_refs = [f"{book} {chapter}:{n}" for n in numbers.split(",")]
            row: BoydNote = {
                "entry": len(rows) + 1,
                "position": positions.get(id(note)),
                "target_ref": target,
                "fr": fr,
                "rp": re.sub(r"\s*[\[{]?[\d.]+%[\]}]?$", "", main.strip()).strip(),
                "variants": variants,
                "tr": tr,
                "raw": body,
                "source_original": original,
                "source_original_html": boyd_markup(note, notes=True),
            }
            if not greek:
                row["source_main_html"] = passages.get(target)
                row["source_address"] = fr
                row["source_main_passages"] = {
                    ref: passages.get(ref) for ref in passage_refs
                }
            row["hf"] = (
                "TR"
                if any("HF" in v["sigla"] for v in tr)
                else "other" if any("HF" in v["sigla"] for v in variants) else "RP"
            )
            row["rp_alternate"] = any("BYZ" in v["sigla"] for v in tr)
            row["patriarchal"] = any("ANT" in v["sigla"] for v in tr)
            rows.append(row)
    return rows


def tcent(folder: Content) -> list[BoydNote]:
    rows = boyd(folder, greek=False)
    if len(rows) != 552 or len({r["target_ref"] for r in rows}) != 489:
        raise ValueError("Changed TCENT inventory: expected 552 notes in 489 verses")
    for (book, fr), (wrong, _) in TCENT_ERRATA.items():
        found = [
            (r["target_ref"], r["fr"])
            for r in rows
            if re.search(rf"(?<!\w){wrong}(?!\w)", r["raw"])
        ]
        if found != [(f"{book} {fr}", fr)]:
            raise ValueError(f"Changed TCENT erratum {wrong}: found at {found}")
    return rows
