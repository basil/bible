"""Pierpont's *Some Improvements to the King James Version from the Majority
Greek Manuscripts* (revised June 1990), read from its transcription.

Each row of the textual-notes tables is an instruction: a KJV quotation with
the changed words underlined (or a + where words are added), and the change.
`read` keeps every row with its weight and Berry locator;
`instructions` interprets the simple and the few explicit combined forms and
binds each edit to the words of the pinned KJV. Weights are evidence of
manuscript support, not of translatability; they become tags later.
"""

from __future__ import annotations

import html
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher
from typing import Any, TypedDict

from bible.byzantine import BOOKS, BOOKS_BY_NAME, PIERPONT
from bible.byzantine.crosswire import SPELLINGS, edit_offsets, spans, words
from bible.byzantine.greek import occurrences
from bible.byzantine.rows import (
    Instruction,
    InstructionEdit,
    PierpontRow,
    PierpontTable,
)

ALIASES = dict(BOOKS_BY_NAME)
ALIASES.update(
    dict(
        zip(
            "MT|MK|LK|JN|ACTS|RO|1 COR|2 COR|GAL|EPH|PHIL|COL|1 TH|2 TH|1 TIM|2 TIM|TITUS|PHM|HEB|JAS|1 PET|2 PET|1 JN|2 JN|3 JN|JUDE|REV".split(
                "|"
            ),
            BOOKS,
            strict=True,
        )
    )
)
ALIASES.update(
    {"ROM": "ROM", "1 THESS": "1TH", "2 THESS": "2TH", "1 PT": "1PE", "2 PT": "2PE"}
)
REFERENCE = re.compile(r"(?:(\d+):)?(\d+)([ab]?)(?:[-–](?:(\d+):)?(\d+)([ab]?))?")


class Inventory(TypedDict):
    """The booklet as read: its lines, its tables and every row of them."""

    source_lines: list[str]
    tables: list[PierpontTable]
    rows: list[PierpontRow]


def markup(raw: str) -> dict[str, Any]:
    """Offsets address the decoded quotation, with + marks still present.

    Underscores encode original underlines, not supplied-word italics.
    Parentheses and punctuation remain source characters.
    """
    text, start = "", None
    ranges: list[list[int]] = []
    errors: list[str] = []
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == "\\" and i + 1 < len(raw) and raw[i + 1] in "_*|\\":
            text += raw[i + 1]
            i += 2
            continue
        if c == "_":
            if start is None:
                start = len(text)
            else:
                ranges.append([start, len(text)])
                start = None
        else:
            text += c
        i += 1
    if start is not None:
        errors.append("unclosed underline")
    return {
        "raw": raw,
        "text": text,
        "underlines": ranges,
        "insertions": [m.start() for m in re.finditer(r"\+", text)],
        "errors": errors,
    }


def references(
    raw: str, book: str | None, chapters: Mapping[tuple[str, int], int]
) -> tuple[list[str], str | None, str | None]:
    """Expand printed ranges without confusing an informational ( with a verse.

    Suffixes a/b remain in raw; refs address complete verses for comparison.
    Book and chapter inheritance is local to this table, never guessed globally.
    """
    source = re.sub(r"[_*]", "", raw).strip().lstrip("(").strip()
    source = source.replace("--", "–")
    explicit = None
    for name in sorted(ALIASES, key=len, reverse=True):
        if re.match(re.escape(name) + r"\.?\s+", source, re.I):
            explicit = ALIASES[name]
            source = re.sub(
                re.escape(name) + r"\.?\s+", "", source, count=1, flags=re.I
            )
            book = explicit
            break
    if not book:
        return [], book, "missing book"
    result: list[str] = []
    chapter: int | None = None
    for part in source.strip().rstrip(";").split(","):
        m = REFERENCE.fullmatch(part.strip())
        if not m:
            return result, book, "unrecognized reference syntax"
        chapter = (
            int(m[1])
            if m[1]
            else chapter or (1 if book in {"PHM", "2JN", "3JN", "JUD"} else None)
        )
        if chapter is None:
            return result, book, "missing chapter"
        end_chapter = int(m[4]) if m[4] else chapter
        end = int(m[5]) if m[5] else int(m[2])
        if end_chapter < chapter or end_chapter == chapter and end < int(m[2]):
            return result, book, "reversed verse range"
        for ch in range(chapter, end_chapter + 1):
            last = end if ch == end_chapter else chapters.get((book, ch), 0)
            first = int(m[2]) if ch == chapter else 1
            if last - first > 200:
                return result, book, "implausible verse range"
            result += [f"{book} {ch}:{v}" for v in range(first, last + 1)]
    return result, book, None


def weight(raw: str, revelation: bool = False) -> dict[str, Any]:
    m = re.fullmatch(r"(['‘’]?)(\d+|[bcd])(\.?)?([+-]?)", raw)
    value: dict[str, Any] = {
        "raw": raw,
        "scale": "revelation-percent" if revelation else "byzantine-band",
    }
    if not m:
        return {**value, "error": "unrecognized weight"}
    number = int(m[2]) if m[2].isdigit() else None
    value.update(
        value=number,
        category=m[2] if number is None else None,
        q_group=bool(m[1]),
        period=bool(m[3]),
        modifier=m[4],
    )
    if revelation:
        valid = (
            number is not None
            and 40 <= number <= 100
            and number % 5 == 0
            and (not m[3] or number == 100)
        ) or (m[2] in {"b", "c", "d"} and not m[1] and not m[3])
    else:
        valid = (
            (number in range(1, 6) or m[2] in {"b", "c", "d"}) and not m[1] and not m[3]
        )
    if not valid:
        value["error"] = "weight does not fit this book's declared scale"
    return value


def berry(raw: str) -> dict[str, Any]:
    text = markup(raw)["text"]
    return {
        "raw": raw,
        "text": text,
        "locators": re.findall(r"[A-Za-z]+|\d+|\*", text),
        "main_text": any(c in text for c in "'‘’"),
        "qualified": "." in text,
        "not_in_berry": "*" in text,
    }


def read(text: str, kjv: Mapping[str, str]) -> Inventory:
    """Every table row of the booklet, with its role and cells."""
    lines = text.splitlines(keepends=True)
    chapters: defaultdict[tuple[str, int], int] = defaultdict(int)
    for ref in kjv:
        b, chv = ref.split()
        ch, v = map(int, chv.split(":"))
        chapters[b, ch] = max(chapters[b, ch], v)
    section, heading, table = "prose", "", 0
    book: str | None = None
    columns: list[str] | None = None
    rows: list[PierpontRow] = []
    tables: list[PierpontTable] = []
    for line_number, original in enumerate(lines, 1):
        line = original.rstrip("\r\n")
        if line.startswith("## "):
            title = re.sub(r"[_*]", "", line[3:])
            if title == "Textual Notes":
                section = "directives"
            elif title.upper().startswith("READINGS WHERE"):
                section = "kjv-agrees"
            elif title.startswith("Examples of Some"):
                section = "alexandrian-examples"
            elif title == "Is Your Bible Missing Verses?":
                section = "fatz"
            else:
                section = "prose"
            book, columns = None, None
        if line.startswith("### "):
            heading = re.sub(r"[_*]", "", line[4:]).strip()
            book = ALIASES.get(heading, book)
            columns = None
        if section == "fatz" and line.startswith(
            "The King James New Testament as well"
        ):
            heading = "Phrases Listed as Missing"
        if not line.startswith("|"):
            continue
        cells = [html.unescape(c.strip()) for c in re.split(r"(?<!\\)\|", line)[1:-1]]
        if cells and all(re.fullmatch(r"[: -]+", c) for c in cells):
            continue
        if columns is None or cells[0] in {
            "Reference",
            "Reference (OCR)",
            "Book (OCR)",
            "Book",
            "Weight",
            "Manuscript type",
        }:
            columns = cells
            table += 1
            tables.append(
                {
                    "table": table,
                    "line": line_number,
                    "columns": columns,
                    "section": section,
                    "heading": heading,
                }
            )
            continue
        role = section
        if columns[0] in {"Weight", "Manuscript type"}:
            role = "statistics"
        elif section == "fatz":
            role = (
                "fatz-reference-list"
                if columns[0] in {"Book (OCR)", "Book"}
                else (
                    "fatz-additions"
                    if heading == "Phrases Listed as Missing"
                    else "fatz-omissions"
                )
            )
        row: PierpontRow = {
            "entry": len(rows) + 1,
            "line": line_number,
            "table": table,
            "role": role,
            "heading": heading,
            "source_original": line,
            "columns": columns,
            "cells": cells,
            "issues": [],
        }
        if any(mark in line for mark in ("{?}", "{illegible}")):
            row["issues"].append(
                {
                    "cause": "unreadable-marker",
                    "detail": "the transcription explicitly marks an unresolved scan character",
                }
            )
        if len(cells) != len(columns):
            row["issues"].append(
                {
                    "cause": "table-columns",
                    "detail": f"{len(cells)} cells under {len(columns)} headings",
                }
            )
        if role not in {"statistics", "prose"}:
            refs, current, error = references(cells[0], book, chapters)
            if role == "fatz-reference-list":
                refs, current, error = (
                    [],
                    ALIASES.get(cells[0].rstrip(".").upper()),
                    None,
                )
                for part in cells[1].split(";"):
                    if part.strip():
                        more, _, fail = references(part.strip(), current, chapters)
                        refs += more
                        error = error or fail
            if current:
                book = current
            row["refs"] = refs
            row["ref"] = refs[0] if refs else None
            row["reference_raw"] = cells[0]
            row["informational"] = cells[0].lstrip().startswith("(")
            if error and cells[0]:
                row["issues"].append({"cause": "reference", "detail": error})
            if role == "directives" and len(cells) in {4, 5}:
                pieces = cells[1].split(maxsplit=1)
                w = pieces[0] if pieces else ""
                loc = (
                    cells[2]
                    if len(cells) == 5
                    else pieces[1] if len(pieces) > 1 else ""
                )
                row["weight"] = weight(w, book == "REV")
                row["berry"] = berry(loc)
                row["quotation"] = markup(cells[-2])
                row["change"] = markup(cells[-1])
                if row["weight"].get("error") and cells[0]:
                    row["issues"].append(
                        {"cause": "weight", "detail": row["weight"]["error"]}
                    )
            elif len(cells) >= 3 and role in {"kjv-agrees", "alexandrian-examples"}:
                row["quotation"] = markup(cells[-2])
                row["change"] = markup(cells[-1])
                if role == "kjv-agrees":
                    row["berry"] = berry(cells[2] if len(cells) == 5 else cells[1])
            elif role in {"fatz-additions", "fatz-omissions"}:
                row["quotation"] = markup(cells[-1])
        for field, decoded in (
            ("quotation", row.get("quotation", {})),
            ("change", row.get("change", {})),
        ):
            for error in decoded.get("errors", []):
                row["issues"].append({"cause": "markup", "detail": f"{field}: {error}"})
        if (
            role == "directives"
            and not row.get("reference_raw")
            and rows
            and rows[-1]["role"] == "directives"
        ):
            row["continuation_of"] = rows[-1]["entry"]
            row["context_ref"] = rows[-1].get("ref")
        rows.append(row)
    return {
        "source_lines": lines,
        "tables": tables,
        "rows": rows,
    }


def operations(row: PierpontRow) -> dict[str, Any]:
    """Interpret only explicit simple instructions; keep complex ones intact."""
    quote, change = row["quotation"], row["change"]
    target = change["text"].strip()
    flag = re.search(r"\(([TE])\b", target)
    if flag:
        target = target[: flag.start()].strip()
    result: dict[str, Any] = {
        "raw": change["raw"],
        "annotation": flag[1] if flag else None,
        "edits": [],
    }
    if not row["ref"]:
        return {**result, "status": "continuation"}
    if any(
        word in quote["text"].lower() + target.lower()
        for word in ["verse", "reverse the order", "ch. 16", "would now be"]
    ):
        return {**result, "status": "structural"}
    marked = quote["underlines"]
    if target.lower() == "omit" and marked:
        result["edits"] = [
            {"kind": "delete", "range": r, "old": quote["text"][r[0] : r[1]], "new": ""}
            for r in marked
        ]
    elif target.startswith("+") and quote["insertions"] and not marked:
        additions = [s.strip().rstrip(",").strip() for s in target.split("+")[1:]]
        if len(additions) == len(quote["insertions"]):
            result["edits"] = [
                {"kind": "insert", "range": [at, at], "old": "", "new": new}
                for at, new in zip(quote["insertions"], additions, strict=True)
            ]
    elif (
        len(marked) > 1
        and not quote["insertions"]
        and len(target.split(",")) == len(marked)
    ):
        replacements = [p.strip() for p in target.split(",")]
        if all(p and not re.search(r"[+{}]|\bor\b", p) for p in replacements):
            result["edits"] = [
                {
                    "kind": "delete" if new.lower() == "omit" else "replace",
                    "range": [a, b],
                    "old": quote["text"][a:b],
                    "new": "" if new.lower() == "omit" else new,
                }
                for (a, b), new in zip(marked, replacements, strict=True)
            ]
    elif (
        len(marked) == 1
        and not quote["insertions"]
        and target
        and not re.search(r"\b(?:omit|times)\b|[+{}_]", target, re.I)
        and (target.lower() == "or" or not re.search(r"\bor\b", target, re.I))
    ):
        a, b = marked[0]
        old = quote["text"][a:b]
        result["edits"] = [
            {
                "kind": (
                    "transpose"
                    if words(old) != words(target)
                    and sorted(words(old)) == sorted(words(target))
                    else "replace"
                ),
                "range": [a, b],
                "old": old,
                "new": target,
            }
        ]
    if result["edits"]:
        return {**result, "status": "simple"}
    if target and not marked and not quote["insertions"]:
        return {**result, "status": "missing-scope"}
    return {**result, "status": "complex"}


def explicit_operations(row: PierpontRow) -> dict[str, Any]:
    """The seven printed combined/descriptive forms, with source alternatives."""
    result = operations(row)
    if result["status"] != "complex":
        return result
    quote = row["quotation"]
    text, target = quote["text"], row["change"]["text"].strip()
    marked = quote["underlines"]

    def edit(kind: str, extent: Sequence[int], new: str = "") -> dict[str, Any]:
        a, b = extent
        return {"kind": kind, "range": [a, b], "old": text[a:b], "new": new}

    if target == "omit or the" and len(marked) == 1:
        result.update(
            edits=[edit("delete", marked[0])],
            alternatives=[{"kind": "replace", "new": "the"}],
            resolution="RP omits tauta; the printed alternative adds an article absent at this boundary",
        )
    elif target == "(show) + me" and len(quote["insertions"]) == 1:
        at = quote["insertions"][0]
        result.update(
            edits=[edit("insert", [at, at], "me")],
            translation_gloss="show",
            resolution="Parenthesized show glosses prove; the plus licenses me",
        )
    elif target == "in a manner unworthy of the Lord" and len(marked) == 1:
        a, b = marked[0]
        result.update(
            edits=[edit("replace", [a, b - int(text[b - 1 : b] == "+")], target)],
            construction="unworthily-of-the-Lord",
        )
    elif (
        re.fullmatch(r"\.\s*\(Period\) \+ And", target)
        and len(quote["insertions"]) == 1
    ):
        at = quote["insertions"][0]
        result["edits"] = [edit("insert", [at, at], "And")]
        result["stop"] = "."
    elif target == "Holy 9 times" and len(marked) == 1:
        result["edits"] = [edit("replace", marked[0], ", ".join(["Holy"] * 9) + ",")]
        result["construction"] = "nine-holies"
    elif (
        target == "omit, + : (colon)"
        and len(marked) == 1
        and len(quote["insertions"]) == 1
    ):
        at = quote["insertions"][0]
        result["edits"] = [edit("delete", marked[0]), edit("insert", [at, at], ":")]
    elif (
        target == "omit, (+ was)" and len(marked) == 1 and len(quote["insertions"]) == 1
    ):
        at = quote["insertions"][0]
        result["edits"] = [edit("delete", marked[0]), edit("insert", [at, at], "[was]")]
    if result["edits"]:
        result["status"] = "explicit"
    return result


def comparison_words(text: str) -> list[str]:
    spelled = (SPELLINGS.get(w, w) for w in words(text))
    return [{"farther": "further"}.get(w, w) for w in spelled]


def bind(row: PierpontRow, kjv: Mapping[str, str]) -> dict[str, Any]:
    """Locate the quotation in the pinned KJV and each edit's words inside it."""
    q = row["quotation"]
    text = q["text"]
    source = spans(text)
    phrase = comparison_words(text)
    text_refs = [(ref, kjv[ref]) for ref in row["refs"] if ref in kjv]
    # Cross-verse quotations have real joins, including the source's verse digits.
    joined = " ".join(t for _, t in text_refs)
    tokens = comparison_words(joined)
    hits = occurrences(tokens, phrase)
    result: dict[str, Any] = {
        "status": "unique" if len(hits) == 1 else "ambiguous" if hits else "absent",
        "context_hits": hits,
        "kjv": joined,
        "bindings": [],
    }
    if not phrase:
        return {**result, "status": "empty"}
    if len(hits) != 1:
        matcher = SequenceMatcher(None, phrase, tokens, autojunk=False)
        result["context_similarity"] = round(matcher.ratio(), 3)
        result["context_differences"] = [
            {"source": phrase[a:b], "kjv": tokens[c:d]}
            for tag, a, b, c, d in matcher.get_opcodes()
            if tag != "equal"
        ]
    for edit in row.get("instruction", {}).get("edits", []):
        a, b = edit["range"]
        indices = [
            i for i, (_, start, end) in enumerate(source) if start < b and end > a
        ]
        if edit["kind"] == "insert":
            i = sum(end <= a for _, _, end in source)
            j = i
        elif indices:
            i, j = indices[0], indices[-1] + 1
        else:
            continue
        matched = (
            [hits[0] + i]
            if len(hits) == 1
            else (
                occurrences(tokens, comparison_words(edit["old"]))
                if edit["old"]
                else []
            )
        )
        if len(matched) != 1:
            result["bindings"].append(
                {**edit, "status": "ambiguous" if matched else "absent"}
            )
            continue
        lo, hi = matched[0], matched[0] + j - i
        binding: dict[str, Any] = {
            **edit,
            "status": "unique",
            "word_range": [lo, hi],
            "context_exact": len(hits) == 1,
            "context_word_range": (
                [hits[0], hits[0] + len(phrase)] if len(hits) == 1 else None
            ),
        }
        if len(text_refs) == 1:
            binding["ref"] = text_refs[0][0]
        else:
            offset = 0
            for ref, content in text_refs:
                count = len(words(content))
                if offset <= lo <= hi <= offset + count:
                    binding.update(ref=ref, word_range=[lo - offset, hi - offset])
                    if binding["context_word_range"]:
                        ca, cb = binding["context_word_range"]
                        binding["context_word_range"] = [
                            max(0, ca - offset),
                            min(count, cb - offset),
                        ]
                    break
                offset += count
            if "ref" not in binding and edit["kind"] == "delete":
                offset = 0
                for ref, content in text_refs:
                    count = len(words(content))
                    if lo < offset + count and offset < hi:
                        extent = [
                            max(lo, offset) - offset,
                            min(hi, offset + count) - offset,
                        ]
                        local = {
                            **binding,
                            "ref": ref,
                            "word_range": extent,
                            "source_word_range": [lo, hi],
                            "no_effect": False,
                        }
                        if binding["context_word_range"]:
                            ca, cb = binding["context_word_range"]
                            local["context_word_range"] = [
                                max(0, ca - offset),
                                min(count, cb - offset),
                            ]
                        result["bindings"].append(local)
                    offset += count
                continue
        if edit["kind"] == "insert":
            added = comparison_words(edit["new"])
            # The plus belongs to the preceding word when the quoted stop
            # follows it; when that stop precedes + it belongs to the next.
            following = source[i][1] if i < len(source) else len(text)
            binding["side"] = (
                "after"
                if i
                and (any(c in ",;:.!?" for c in text[a:following]) or i == len(source))
                else "before"
            )
            binding["already_present"] = bool(added) and (
                tokens[lo : lo + len(added)] == added
                or tokens[max(0, lo - len(added)) : lo] == added
            )
        binding["no_effect"] = edit["kind"] != "insert" and edit["old"] == edit["new"]
        result["bindings"].append(binding)
    return result


def strength(w: Mapping[str, Any] | None, informational: bool) -> str | None:
    """Pierpont's weight as evidence strength: mandatory, strong, weak or None.

    Matthew to Jude: 5, 4 and the letters b, c, d (which he calls mandatory)
    are mandatory; 3 is strong; 2 and 1 are minority readings. Revelation uses
    the percentage of manuscripts: 70 and above he says "should certainly be
    made"; below 60 is a minority. A leading ( marks a merely informational row.
    """
    if informational:
        return "weak"
    if not w or w.get("error"):
        return None
    if w.get("category") in {"b", "c", "d"}:
        return "mandatory"
    value = w.get("value")
    if value is None:
        return None
    if w["scale"] == "revelation-percent":
        return "mandatory" if value >= 70 else "strong" if value >= 60 else "weak"
    return "mandatory" if value >= 4 else "strong" if value == 3 else "weak"


def instructions(inventory: Inventory, kjv: Mapping[str, str]) -> list[Instruction]:
    """The textual-notes rows and the KJV-agrees rows as bound instructions.

    Each has `edits`, one per operation, with the status of its binding to
    the pinned KJV; `role` is "instruction" or "agrees"; `status` says what
    the parser made of the printed change (simple, explicit, structural,
    complex, continuation, missing-scope).
    """
    result: list[Instruction] = []
    for row in inventory["rows"]:
        if row["role"] not in {"directives", "kjv-agrees"}:
            continue
        interpreted: dict[str, Any] = (
            explicit_operations(row)
            if row.get("quotation")
            else {"status": "complex", "edits": []}
        )
        candidate: PierpontRow = {**row, "instruction": interpreted}
        binding: dict[str, Any] = (
            bind(candidate, kjv)
            if row.get("quotation")
            else {"status": "empty", "bindings": []}
        )
        edits: list[InstructionEdit] = []
        for b in binding["bindings"]:
            if b["status"] != "unique" or not b.get("ref"):
                edits.append(
                    {
                        "kind": b["kind"],
                        "old": b["old"],
                        "new": b["new"],
                        "bind": b["status"],
                    }
                )
                continue
            text = kjv[b["ref"]]
            lo, hi = edit_offsets(text, b)
            new = re.sub(r"\(([^()]*)\)", r"[\1]", b["new"])
            # The booklet prints a transliterated quotation in capitals (ELI,
            # ELI, LAMA SABACHTANI); the KJV does not. Case the new word as
            # the KJV cases the word it replaces.
            old_quoted, old_kjv = b.get("old", ""), text[lo:hi]
            if (
                new.isupper()
                and old_quoted.isupper()
                and old_kjv
                and not old_kjv.isupper()
            ):
                new = new.capitalize() if old_kjv[0].isupper() else new.lower()
            # A period closing the change cell is the table's, not the text's,
            # when the words are added inside a sentence.
            if (
                b["kind"] == "insert"
                and new.endswith(".")
                and text[hi:].strip()
                and not text[hi:].strip()[0].isupper()
            ):
                new = new.rstrip(".")
            edit: InstructionEdit = {
                "kind": b["kind"],
                "ref": b["ref"],
                "word_range": list(b["word_range"]),
                # The KJV's own characters for the span; the new words with
                # Pierpont's parenthesized supplied words as KJV brackets.
                "old": old_kjv,
                "new": new,
                "quoted_old": b["old"],
                "bind": "already" if b.get("already_present") else "unique",
                "no_effect": b.get("no_effect", False),
                "context_exact": b.get("context_exact", False),
            }
            if b["kind"] == "insert":
                edit["side"] = b.get("side", "before")
                edit["quoted_context"] = row.get("quotation", {}).get("text", "")
            edits.append(edit)
        if interpreted.get("stop") and edits:
            edits[0]["stop"] = interpreted["stop"]
        if edits and all(e["bind"] == "unique" for e in edits):
            bound = "unique"
        elif edits and all(e["bind"] in {"unique", "already"} for e in edits):
            bound = "already"
        elif edits:
            bound = next(
                e["bind"] for e in edits if e["bind"] not in {"unique", "already"}
            )
        else:
            bound = (
                binding["status"]
                if interpreted["status"] in {"simple", "explicit"}
                else interpreted["status"]
            )
        result.append(
            {
                "source": PIERPONT,
                "entry": row["entry"],
                "role": "agrees" if row["role"] == "kjv-agrees" else "instruction",
                "ref": row.get("ref"),
                "refs": row.get("refs", []),
                "raw": row["source_original"],
                "line": row["line"],
                "status": interpreted["status"],
                "weight": row.get("weight"),
                "strength": strength(
                    row.get("weight"), row.get("informational", False)
                ),
                "informational": row.get("informational", False),
                "berry": row.get("berry"),
                "quotation": row.get("quotation", {}).get("text"),
                "change": row.get("change", {}).get("text"),
                "construction": interpreted.get("construction"),
                "alternatives": interpreted.get("alternatives", []),
                "context": binding["status"],
                "bind": bound,
                "edits": edits,
                "issues": row.get("issues", []),
            }
        )
    return result
