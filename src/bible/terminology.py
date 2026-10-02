"""The edition's terms and abbreviations (edition/terminology.json).

A term has one identity, one printed form and one meaning; the sources write
it many ways. "A. V.", "Eng. Ver." and "AV" are the Authorized Version, and
print so; "Sept." is "LXX"; "i. e." closes up, and takes a comma. A term is
recognized in a source's words and printed in the edition's form, in the form
The Chicago Manual of Style gives it. The same registry writes the rows that
complete Brenton's list of abbreviations (edition/abbreviations.json), so
that the list and the notes cannot disagree.

Recognizing a term decides nothing about the manuscripts: a run of "Heb.",
"Alex." and "Vat." stays a run of labels.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Literal

import bible.policy
from bible import usj
from bible.checks import require, require_fields
from bible.policy_schema import Terminology
from bible.usj import Content, Document, Node

ALIASES: tuple[Literal["period_forms", "note_forms", "source_forms"], ...] = (
    "period_forms",
    "note_forms",
    "source_forms",
)
# The end of a sentence, where an abbreviation's own period also closes it.
# What joins two witness labels that share a verb: "Heb. and Alex. add".
WITNESS_JOIN = re.compile(r",?\s+and\s+")
SENTENCE_END = re.compile(r"['’”)]*(?:\s+[A-Z]|[ \t]*(?:\n|$))")
ERA = re.compile(r"\b(?P<era>a\.d|b\.c)\.(?: (?P<year>\d+(?:[–-]\d+)?)\b)?")
# Latin in a meaning, italic as Brenton's "quasi dicat" is.
LATIN = re.compile(r"_([^_]+)_")
GLOSSARY = "FRT"
# The witnesses whose additions and omissions the sources mark with a sign.
WITNESSES = ("hebrew", "alexandrine", "vatican")


@dataclass(frozen=True)
class Term:
    """A term where a source writes it: its identity and its source's words."""

    identity: str
    lexeme: str
    start: int
    end: int
    form: str = "display"
    # Whether its period also ends a sentence.
    closure: bool = False
    year: str | None = None


@dataclass(frozen=True, eq=False)
class Registry:
    terms: Mapping[str, Terminology]

    def display(self, identity: str) -> str:
        require(identity in self.terms, f"Unknown term: {identity}")
        return self.terms[identity]["display"]

    def aliases(
        self, field: Literal["period_forms", "note_forms", "source_forms"]
    ) -> dict[str, str]:
        return {
            alias: identity
            for identity, term in self.terms.items()
            for alias in term[field]
        }

    def row(self, identities: Iterable[str]) -> tuple[str, str]:
        """A row of the list of abbreviations: the terms' forms and meanings."""
        return (
            ", ".join(self.display(i) for i in identities),
            ", ".join(self.terms[i]["meaning"] for i in identities),
        )


@functools.cache
def registry(policy: bible.policy.Policy) -> Registry:
    data = policy.terminology
    require(bool(data), "Invalid terminology registry")
    used: dict[str, set[str]] = {field: set() for field in ALIASES}
    for identity, entry in data.items():
        require_fields(
            entry, {"display", "meaning", *ALIASES}, {"plural"}, f"Term {identity}"
        )
        require(
            entry["display"] and entry["meaning"] and entry.get("plural", "plural"),
            f"Invalid term wording: {identity}",
        )
        for field in ALIASES:
            forms = entry[field]
            require(
                len(set(forms)) == len(forms) and not used[field].intersection(forms),
                f"Ambiguous term aliases: {identity}: {field}",
            )
            used[field].update(forms)
    return Registry(data)


def recognize(text: str, terms: Registry, *, note: bool = True) -> tuple[Term, ...]:
    return _recognized(text, terms, note)


@functools.lru_cache(maxsize=8192)
def _recognized(text: str, terms: Registry, note: bool) -> tuple[Term, ...]:
    """The terms a source's words name, each where it stands, longest first."""
    candidates = []

    def add(
        pattern: str, identity: str, form: str = "display", *, period: bool = False
    ) -> None:
        for m in re.finditer(pattern, text, re.M):
            closure = bool(
                period and m[0].endswith(".") and SENTENCE_END.match(text, m.end())
            )
            candidates.append(Term(identity, m[0], m.start(), m.end(), form, closure))

    if note:
        for alias, identity in terms.aliases("note_forms").items():
            add(r"\b" + re.escape(alias) + r"\b", identity)
    add(r"\bi\. ?e\.", "id-est", "comma")
    add(r"\bq\. d\.", "quasi-dicat")
    add(r"\bscil\.", "scilicet")
    add(r"\bScil\.", "scilicet", "capital")
    add(r"\bComp\.", "compare")
    add(r"\bcomp\.", "compare", "lower")
    add(r"\bAV\b", "authorized-version")
    add(r"&c\.", "et-cetera")
    add(r"&c\b", "et-cetera", "stem")
    for alias, identity in terms.aliases("period_forms").items():
        add(
            r"(?<![\w.])" + re.escape(alias) + r"\.?" + r"(?!\w)", identity, period=True
        )
    for m in ERA.finditer(text):
        candidates.append(
            Term(
                "anno-domini" if m["era"] == "a.d" else "before-christ",
                m[0],
                m.start(),
                m.end(),
                "era",
                bool(SENTENCE_END.match(text, m.end())),
                m["year"],
            )
        )
    # A form already the edition's is still the term. The longest spelling
    # wins: "p." cannot take the end of "pp.".
    forms = [
        (alias, identity, n)
        for identity, term in terms.terms.items()
        for n, alias in enumerate(term["source_forms"])
    ]
    for alias, identity, n in sorted(forms, key=lambda f: -len(f[0])):
        if identity in ("addition", "omission"):
            continue
        add(
            r"(?<![\w&])" + re.escape(alias) + r"(?!\w)",
            identity,
            "display" if n == 0 else "literal",
        )
    result: list[Term] = []
    for term in candidates:
        if not any(term.start < t.end and t.start < term.end for t in result):
            result.append(term)
    # A sign following a witness label introduces its added or omitted
    # words, and agrees with the labels before it: "Alex. adds", "Heb. and
    # Alex. add". Other dashes are punctuation, including "Heb.—מ". A sign
    # after any other term, or a sign of addition anywhere else, is not
    # understood.
    if note:
        witnesses = [t for t in result if t.identity in WITNESSES]
        signs = []
        for term in result:
            for identity in ("addition", "omission"):
                for alias in terms.terms[identity]["source_forms"]:
                    match = re.match(
                        r"\s*" + re.escape(alias) + r"(?=\s)", text[term.end :]
                    )
                    if not match:
                        continue
                    require(term in witnesses, f"Sign after no witness: {text}")
                    end = term.end + match.end()
                    several = any(
                        WITNESS_JOIN.fullmatch(text, w.end, term.start)
                        for w in witnesses
                    )
                    signs.append(
                        Term(
                            identity,
                            alias,
                            end - len(alias),
                            end,
                            "plural" if several else "display",
                        )
                    )
        for alias in terms.terms["addition"]["source_forms"]:
            for found in re.finditer(re.escape(alias), text):
                require(
                    any(s.start == found.start() for s in signs),
                    f"Sign after no witness: {text}",
                )
        result += signs
    return tuple(sorted(result, key=lambda t: t.start))


def render(term: Term, terms: Registry, text: str) -> str:
    """A term as the edition prints it where it stands."""
    display = terms.display(term.identity)
    if term.form == "literal":
        return text[term.start : term.end]
    if term.form == "capital":
        display = display.capitalize()
    elif term.form == "lower":
        display = display.lower()
    elif term.form == "upper":
        display = display.upper()
    elif term.form == "stem":
        display = display.removesuffix(".")
    elif term.form == "plural":
        display = terms.terms[term.identity]["plural"]
    elif term.form == "space":
        display += " "
    elif term.form == "comma":
        if text[term.end : term.end + 1] == " ":
            display += ","
    elif term.form == "era" and term.year:
        # "AD" before its year and "BC" after, as Chicago sets them.
        return (
            f"{term.year} {display}"
            if term.identity == "before-christ"
            else f"{display} {term.year}"
        )
    if term.closure and not display.endswith(".") and not term.year:
        display += "."
    return display


def _outline(
    content: Content,
) -> tuple[list[tuple[int, str, bool]], list[int], list[tuple[int, int]]]:
    """A paragraph's prose with what bounds its words: where each character
    style opens and closes, where a part of a note begins, and where the
    words of its notes lie."""
    styles: list[tuple[int, str, bool]] = []
    fields: list[int] = []
    noted: list[tuple[int, int]] = []
    at = 0

    def visit(items: Content, in_note: bool) -> None:
        nonlocal at
        for item in items:
            if isinstance(item, str):
                if in_note:
                    noted.append((at, at + len(item)))
                at += len(item)
            elif usj.is_label(item) or "content" not in item:
                continue
            elif item["type"] == "note":
                visit(item["content"], True)
            elif item["marker"] in usj.FIELDS:
                fields.append(at)
                visit(item["content"], in_note)
            else:
                styles.append((at, item["marker"], False))
                visit(item["content"], in_note)
                styles.append((at, item["marker"], True))

    visit(content, False)
    return styles, fields, noted


def found(content: Content, terms: Registry, *, note: bool) -> tuple[Term, ...]:
    """The terms in a paragraph of prose, or in an introduction set as a
    note, each where it stands in the paragraph's words. The words of a
    footnote within prose are read as a note's."""
    text = usj.text_of(content, skip=usj.is_label)
    styles, _, noted = _outline(content)
    result = list(recognize(text, terms, note=note))
    if noted and not note:
        known = {(t.start, t.end, t.identity) for t in result}
        result += [
            t
            for t in recognize(text, terms, note=True)
            if (t.start, t.end, t.identity) not in known
            and any(a <= t.start < b for a, b in noted)
        ]
    # The Translators to the Reader's saints: "S. \it Augustine\it*", and one
    # inside an italic quotation: "\it The doctrine of S\it*. John".
    for position, marker, closing in styles:
        if marker != "it":
            continue
        if not closing:
            m = re.search(r"\bS\. $", text[:position])
            if m and re.match("[A-Z]", text[position:]):
                result.append(Term("saint", m[0], m.start(), m.end(), "space"))
        else:
            m = re.search(r"\bS$", text[:position])
            if m and re.match(r"\. [A-Z]", text[position:]):
                result.append(Term("saint", m[0], m.start(), m.end(), "stem"))
    # A period that ends a footnote ends its sentence.
    note_ends = {
        b
        for n, (a, b) in enumerate(noted)
        if n + 1 == len(noted) or noted[n + 1][0] != b
    }
    return tuple(
        replace(t, closure=True) if t.end in note_ends and t.lexeme.endswith(".") else t
        for t in result
    )


def printed(content: Content, found_terms: Iterable[Term], terms: Registry) -> Content:
    """A paragraph with the terms found in it as the edition prints them."""
    text = usj.text_of(content, skip=usj.is_label)
    styles, fields, _ = _outline(content)
    edits, commas, eras = [], [], []
    for term in found_terms:
        # A source period outside italic is roman punctuation of its own, as
        # after the Reader's italic "&c".
        if (
            term.identity == "et-cetera"
            and term.lexeme == "&c."
            and any(at == term.end - 1 and closing for at, _, closing in styles)
        ):
            term = replace(term, lexeme="&c", end=term.end - 1, form="stem")
        # A capital that opens another part of a note or an italic run is a
        # name as often as not, and ends no sentence.
        capital = re.match(r"\s+([A-Z])", text[term.end :])
        if term.closure and capital:
            end = term.end + capital.end()
            if any(term.end <= at < end for at in fields) or any(
                term.end <= at < end and not closing for at, _, closing in styles
            ):
                term = replace(term, closure=False)
        value = render(term, terms, text)
        if term.form == "era":
            eras.append(term)
        if value == term.lexeme:
            continue
        # A comma after an italic "i.e." is roman, with what follows.
        outside = (
            term.form == "comma"
            and value.endswith(",")
            and any(
                at == term.end and marker == "it" and closing
                for at, marker, closing in styles
            )
        )
        edits.append((term.start, term.end, value[:-1] if outside else value))
        if outside:
            commas.append(term.end)
    # Small capitals belong to the source's "a.d.", not to "AD".
    unwrap, opened = [], []
    for at, marker, closing in styles:
        if not closing:
            opened.append(at)
            continue
        start = opened.pop()
        if marker == "sc" and any(
            t.start <= edge <= t.end for t in eras for edge in (start, at)
        ):
            unwrap.append((start, at))
    if not edits and not unwrap:
        return content
    content = usj.substituted(content, edits, skip=usj.is_label, unwrap=unwrap)
    if commas:
        # Each comma stands where its term ended, as the words now run.
        placed = [
            (
                at + sum(len(v) - (e - s) for s, e, v in edits if e <= at),
                at + sum(len(v) - (e - s) for s, e, v in edits if e <= at),
                ",",
            )
            for at in commas
        ]
        content = usj.substituted(content, placed, skip=usj.is_label, right=True)
    return content


def glossary_rows(policy: bible.policy.Policy) -> list[tuple[str, str]]:
    """The rows the edition adds to Brenton's list, as (abbreviation, meaning)."""
    terms = registry(policy)
    return [terms.row(identities) for identities in policy.abbreviations["added"]]


def check_abbreviations(policy: bible.policy.Policy) -> None:
    data, terms = policy.abbreviations, registry(policy)
    require_fields(
        data,
        {"why", "added", "expanded", "meanings", "source_rows"},
        (),
        "Abbreviations",
    )
    require_fields(data["expanded"], {"why", "removed"}, (), "Removed abbreviations")
    added = [identity for row in data["added"] for identity in row]
    for identity in (*added, *data["source_rows"].values()):
        terms.display(identity)
    require(len(set(added)) == len(added), "Duplicate glossary terms")
    removed = data["expanded"]["removed"]
    require(
        len(set(removed)) == len(removed) and set(removed) <= set(data["source_rows"]),
        "Duplicate or unbound glossary removal",
    )
    require(
        len(set(data["source_rows"].values())) == len(data["source_rows"])
        and not set(added).intersection(data["source_rows"].values()),
        "Duplicate source/added glossary terms",
    )
    require(
        data["why"] and data["expanded"]["why"] and data["meanings"].get("why"),
        "Abbreviation decisions without a why",
    )


def glossary_table(doc: Document) -> Node:
    tables = [b for b in doc["content"] if b["type"] == "table"]
    require(
        len(tables) == 1 and doc["content"][-1] is tables[0],
        "Brenton's list of abbreviations doesn't end with its table",
    )
    return tables[0]


def dropped_rows(doc: Document, policy: bible.policy.Policy) -> set[int]:
    """The rows of Brenton's list for what the edition prints in full, by
    their place in his table as its source has it."""
    data = policy.abbreviations
    labels = []
    for row in usj.objects(glossary_table(doc)["content"]):
        require(len(row["content"]) == 2, "Source glossary row has no pair of cells")
        labels.append(
            usj.text_of(list(usj.objects(row["content"]))[0]["content"]).strip()
        )
    require(
        sorted(labels) == sorted(data["source_rows"]),
        "Source glossary disagrees with bound rows",
    )
    return {n for n, label in enumerate(labels) if label in data["expanded"]["removed"]}


def completed_glossary(
    doc: Document, dropped: set[int], policy: bible.policy.Policy
) -> Document:
    """Brenton's list of abbreviations without the rows dropped, and with the
    edition's rows after his, set as his are: the abbreviation in italic, and
    "for" its meaning, without a final full stop."""
    table = glossary_table(doc)
    rows: Content = []
    for n, row in enumerate(usj.objects(table["content"])):
        if n in dropped:
            continue
        label, meaning_cell = list(usj.objects(row["content"]))
        meaning_text = usj.text_of(meaning_cell["content"]).rstrip()
        require(meaning_text.endswith("."), "Source glossary meaning has no full stop")
        content = usj.substituted(
            meaning_cell["content"], [(len(meaning_text) - 1, len(meaning_text), "")]
        )
        rows.append({**row, "content": [label, {**meaning_cell, "content": content}]})
    for abbreviation, meaning in glossary_rows(policy):
        cells: Content = ["for "]
        at = 0
        for match in LATIN.finditer(meaning):
            cells += [meaning[at : match.start()], usj.char("it", match[1])]
            at = match.end()
        cells.append(meaning[at:])
        rows.append(
            {
                "type": "table:row",
                "marker": "tr",
                "content": [
                    _cell("tc1", [usj.char("it", abbreviation)]),
                    _cell("tc2", usj.joined(cells)),
                ],
            }
        )
    return usj.with_blocks(doc, [*doc["content"][:-1], {**table, "content": rows}])


def _cell(marker: str, content: Content) -> Node:
    return {
        "type": "table:cell",
        "marker": marker,
        "align": "start",
        "content": content,
    }


def check_glossary(doc: Document, policy: bible.policy.Policy) -> None:
    """Every row the list prints must agree with the registry."""
    data, terms = policy.abbreviations, registry(policy)
    table = next(b for b in doc["content"] if b["type"] == "table")
    printed_rows = [
        (
            usj.text_of(list(usj.objects(row["content"]))[0]["content"]).strip(),
            usj.text_of(list(usj.objects(row["content"]))[1]["content"]).strip(),
        )
        for row in usj.objects(table["content"])
    ]

    def expected(rows: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
        return [(a, "for " + LATIN.sub(r"\1", m)) for a, m in rows]

    kept = [
        terms.row((identity,))
        for source, identity in data["source_rows"].items()
        if source not in data["expanded"]["removed"]
    ]
    added = glossary_rows(policy)
    require(
        len(printed_rows) == len(kept) + len(added)
        and sorted(printed_rows[: len(kept)]) == sorted(expected(kept))
        and printed_rows[len(kept) :] == expected(added),
        "Printed glossary disagrees with terminology registry",
    )


# Source forms that must not be left once the terms are printed, including
# the abbreviations that edition/prose.json prints in full where they stand.
# "Rom." is Brenton's Roman edition, unless a chapter follows: then it is the
# edition's abbreviation for Romans.
UNPRINTED = re.compile(
    r"\bi\. e\.|\bq\. d\.|\b[Ss]cil\.|\bSept\b|\b[Cc]omp\.|\d AD\b|&c\b|\b[ab]\.[dc]\."
    r"|(?<![\w.])(?:[ON]\. ?T|A\. V|Ald|Complut|Vulg)(?!\w)|\bAV\b"
    r"|\b(?:App|Chrysost|Gram|Qu|om|nom|voc|absol|infin|imper|pl|qy|viz|niph"
    r"|fem|ob)\.|\bRom\.(?! \d)|\bCateches\b|\bult\b|\b4to\b|\bEng\. Ver\b|\d\.(?:li|[sd])\b"
)
# A number with a period within a note's sentence, which edition/prose.json
# must decide: "after 5. shillings".
NUMBER_STOP = re.compile(r"\d\. +[a-z]")


def check_forms(code: str, text: str, *, note: bool) -> None:
    left = [m[0] for m in UNPRINTED.finditer(text)]
    require(not left, f"Abbreviations not in Chicago's forms: {code}: {left}")
    if note:
        stops = [m[0] for m in NUMBER_STOP.finditer(text)]
        require(
            not stops, f"Number with a period within a note's sentence: {code} {stops}"
        )
