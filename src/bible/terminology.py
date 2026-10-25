"""The edition's terms and abbreviations (edition/terminology.json).

A term has one identity, one printed form, and one meaning; the sources write
it many ways. "A. V.", "Eng. Ver.", and "AV" name the Authorized Version,
which a note calls by its note term, KJV; "Sept." is "LXX"; "i. e." closes up,
and takes a comma.
A term is recognized in a source's words and printed in the edition's form, in the form
The Chicago Manual of Style gives it. The same registry writes the rows that
complete Brenton's list of abbreviations (edition/abbreviations.json), so
that the list and the notes cannot disagree.

Recognizing a term decides nothing about the manuscripts: a run of "Heb.",
"Alex." and "Vat." stays a run of labels.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Iterable, Mapping, Sequence
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
# Latin or a title in a meaning, italic as Brenton's "quasi dicat" is.
LATIN = re.compile(r"_([^_]+)_")
# The witnesses whose additions and omissions the sources mark with a sign.
WITNESSES = ("hebrew", "alexandrine", "vatican")
# The labels that introduce what follows them, so that their stop never ends
# a sentence: "Gr. lit. them" continues the label, and so does "Sept. lit.".
LABELS = (
    *WITNESSES,
    "greek",
    "septuagint",
    "vulgate",
    "authorized-version",
    "king-james-version",
    "complutensian",
    "aldine",
    "scilicet",
    "id-est",
    "quasi-dicat",
)
# The witnesses a New Testament note names (byzantine.received.labels): the
# Received Text, the printed editions the King James translators followed,
# and the King James Version, whose words it gives.
NEW_TESTAMENT = (
    "textus-receptus",
    "beza",
    "erasmus",
    "stephanus-1549",
    "complutensian",
    "aldine",
    "king-james-version",
)
# A sentence's end before a word: a stop, with any closing quotes, and space.
BEFORE_SENTENCE = re.compile(r"[.?!]['’”)]*\s+$")


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
            entry,
            {"display", "meaning", *ALIASES},
            {"plural", "note_term"},
            f"Term {identity}",
        )
        require(
            entry.get("note_term", identity) in data,
            f"Unknown note term: {identity}",
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


@functools.lru_cache(maxsize=8192)
def recognize(text: str, terms: Registry, *, note: bool = True) -> tuple[Term, ...]:
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
    # wins: "Complutensian" cannot take the start of "Complutensian Text".
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
    if note:
        # A term with a note term is called by it in a note, however the
        # source writes it; the period of its form still ends a sentence
        # ("Eng. Ver. The"), as an abbreviation's does.
        result = [
            (
                replace(
                    t,
                    identity=other,
                    form="display",
                    closure=bool(
                        t.lexeme.endswith(".") and SENTENCE_END.match(text, t.end)
                    ),
                )
                if (other := terms.terms[t.identity].get("note_term"))
                else t
            )
            for t in result
        ]
    result = list(literally_decided(text, result))
    # A sign following a witness label, spaced on both sides as Brenton sets
    # it, introduces its added or omitted words, and agrees with the labels
    # before it: "Alex. adds", "Heb. and Alex. add". Other dashes are
    # punctuation, including "Heb.—מ", which he closes up. A sign
    # after any other term, or a sign of addition anywhere else, is not
    # understood.
    if note:
        witnesses = [t for t in result if t.identity in WITNESSES]
        signs = []
        for term in result:
            for identity in ("addition", "omission"):
                for alias in terms.terms[identity]["source_forms"]:
                    match = re.match(
                        r"\s+" + re.escape(alias) + r"(?=\s)", text[term.end :]
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
                if any(s.start == found.start() for s in signs):
                    continue
                if any(w.end == found.start() for w in witnesses):
                    reason = "Sign closed up to its witness"
                elif any(text[w.end : found.start()].isspace() for w in witnesses):
                    reason = "Sign closed up to its words"
                else:
                    reason = "Sign after no witness"
                require(False, f"{reason}: {text}")
        result += signs
    return tuple(sorted(result, key=lambda t: t.start))


def literally_decided(text: str, terms: Sequence[Term]) -> tuple[Term, ...]:
    """The terms with "lit." as it prints where it now stands. "lit." is
    lowercase, as Chicago sets it, and capitalized only where it begins a
    sentence, after a stop that is no label's. Brenton capitalizes it after
    "Gr.", which it continues, and lowercases it after a full stop, so the
    source's capital decides nothing, except at the start of a note, whose
    first word the note's opening sets. A label's stop that "lit." continues
    ends no sentence either, whatever capital the source gives "lit."."""
    result = list(terms)
    ordered = sorted(terms, key=lambda t: t.start)
    for n, term in enumerate(result):
        if term.identity == "literally":
            result[n] = replace(term, form=_literally_form(text, term, terms))
        elif term.identity in LABELS and term.closure:
            following = next((t for t in ordered if t.start >= term.end), None)
            if (
                following is not None
                and following.identity == "literally"
                and text[term.end : following.start].isspace()
            ):
                result[n] = replace(term, closure=False)
    return tuple(result)


def _literally_form(text: str, term: Term, others: Sequence[Term]) -> str:
    """How "lit." prints where it stands: as the source has it at the start
    of the text, capitalized after a sentence's end that is not a label's
    stop, and lowercase elsewhere."""
    before = text[: term.start]
    if not before.strip():
        return "literal"
    end = BEFORE_SENTENCE.search(before)
    if not end:
        return "display"
    # The stop itself, before any closing quote or bracket: "(Heb.) lit."
    # continues the label.
    stop = end.start() + 1
    labelled = any(
        t.identity in LABELS and t.end == stop for t in others if t is not term
    )
    return "display" if labelled else "capital"


def _literally_placed(
    text: str, notes: Sequence[tuple[int, int]], terms: Iterable[Term]
) -> list[Term]:
    """A paragraph's terms with "lit." decided where it now stands: in its
    prose, and in the words of each footnote, read on their own."""
    result = list(terms)
    parts: dict[tuple[int, int], list[int]] = {}
    for n, term in enumerate(result):
        part = next(((a, b) for a, b in notes if a <= term.start < b), (0, len(text)))
        parts.setdefault(part, []).append(n)
    for (a, b), members in parts.items():
        decided = literally_decided(
            text[a:b],
            [
                replace(result[n], start=result[n].start - a, end=result[n].end - a)
                for n in members
            ],
        )
        for n, term in zip(members, decided, strict=True):
            result[n] = replace(term, start=term.start + a, end=term.end + a)
    return result


def render(term: Term, terms: Registry, text: str) -> str:
    """A term as the edition prints it where it stands."""
    display = terms.display(term.identity)
    if term.form == "literal":
        return text[term.start : term.end]
    if term.form == "capital":
        display = display.capitalize()
    elif term.form == "lower":
        display = display.lower()
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
    words of each of its notes lie."""
    styles: list[tuple[int, str, bool]] = []
    fields: list[int] = []
    noted: list[tuple[int, int]] = []
    at = 0

    def visit(items: Content) -> None:
        nonlocal at
        for item in items:
            if isinstance(item, str):
                at += len(item)
            elif usj.is_label(item) or "content" not in item:
                continue
            elif item["type"] == "ref":
                visit(item["content"])
            elif item["type"] == "note":
                start = at
                visit(item["content"])
                if at > start:
                    noted.append((start, at))
            elif item["marker"] in usj.FIELDS:
                fields.append(at)
                visit(item["content"])
            else:
                styles.append((at, item["marker"], False))
                visit(item["content"])
                styles.append((at, item["marker"], True))

    visit(content)
    return styles, fields, noted


def found(content: Content, terms: Registry, *, note: bool) -> tuple[Term, ...]:
    """The terms in a paragraph of prose, or in one sent to a verse as a
    note, each where it stands in the paragraph's words. The words of a
    footnote within prose are read as a note's."""
    text = usj.unlabelled(content)
    # Each footnote's words are read on their own.
    _, _, spans = _outline(content)
    result = [
        t
        for t in recognize(text, terms, note=note)
        if not any(a <= t.start < b for a, b in spans)
    ]
    for a, b in spans:
        result += [
            replace(t, start=t.start + a, end=t.end + a)
            for t in recognize(text[a:b], terms, note=True)
        ]
    # The Translators to the Reader's saints, in roman or italic type.
    for match in re.finditer(r"\bS\. (?=[A-Z])", text):
        result.append(Term("saint", match[0], match.start(), match.end(), "space"))
    # A period that ends a footnote ends its sentence.
    note_ends = {b for _, b in spans}
    return tuple(
        replace(t, closure=True) if t.end in note_ends and t.lexeme.endswith(".") else t
        for t in result
    )


def printed(content: Content, found_terms: Iterable[Term], terms: Registry) -> Content:
    """A paragraph with the terms found in it as the edition prints them,
    "lit." as it prints where the words now stand."""
    text = usj.unlabelled(content)
    styles, fields, noted = _outline(content)
    edits, commas, eras = [], [], []
    for term in _literally_placed(text, noted, found_terms):
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
            (moved, moved, ",")
            for at in commas
            if (moved := at + sum(len(v) - (e - s) for s, e, v in edits if e <= at))
            is not None
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


def glossary_terms(doc: Document, policy: bible.policy.Policy) -> list[str | None]:
    """The term each row of Brenton's list stands for, by its place in his
    table as its source has it, or None where the edition prints the term in
    full and drops the row."""
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
    return [
        None if label in data["expanded"]["removed"] else data["source_rows"][label]
        for label in labels
    ]


def alphabetical(abbreviation: str) -> str:
    """The order of the list of abbreviations: by their letters alone."""
    letters = "".join(c for c in abbreviation.casefold() if c.isalpha())
    require(bool(letters), f"A sign in the list of abbreviations: {abbreviation}")
    return letters


def completed_glossary(
    doc: Document, identities: list[str | None], policy: bible.policy.Policy
) -> Document:
    """Brenton's list of abbreviations without the rows dropped, each of his
    labelled as the registry prints it, and with the edition's rows set as
    his are: the abbreviation in italic and "for" its meaning, without a
    final full stop. The rows are in alphabetical order."""
    terms = registry(policy)
    table = glossary_table(doc)

    rows: list[tuple[str, Node]] = []
    for identity, row in zip(identities, usj.objects(table["content"]), strict=True):
        if identity is None:
            continue
        label_cell, meaning_cell = list(usj.objects(row["content"]))
        abbreviation = terms.display(identity)
        label_cell = {**label_cell, "content": [usj.char("it", abbreviation)]}
        meaning_text = usj.text_of(meaning_cell["content"]).rstrip()
        require(meaning_text.endswith("."), "Source glossary meaning has no full stop")
        content = usj.substituted(
            meaning_cell["content"], [(len(meaning_text) - 1, len(meaning_text), "")]
        )
        rows.append(
            (
                abbreviation,
                {**row, "content": [label_cell, {**meaning_cell, "content": content}]},
            )
        )
    for abbreviation, meaning in glossary_rows(policy):
        cells: Content = ["for "]
        at = 0
        for match in LATIN.finditer(meaning):
            cells += [meaning[at : match.start()], usj.char("it", match[1])]
            at = match.end()
        cells.append(meaning[at:])
        rows.append(
            (
                abbreviation,
                usj.row(
                    usj.cell("tc1", usj.char("it", abbreviation)),
                    usj.cell("tc2", *usj.joined(cells)),
                ),
            )
        )
    rows.sort(key=lambda labelled: alphabetical(labelled[0]))
    return usj.with_blocks(
        doc, [*doc["content"][:-1], {**table, "content": [row for _, row in rows]}]
    )


def check_glossary(doc: Document, policy: bible.policy.Policy) -> None:
    """Every row the list prints must agree with the registry."""
    data, terms = policy.abbreviations, registry(policy)
    table = glossary_table(doc)
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
        sorted(printed_rows) == sorted(expected([*kept, *added])),
        "Printed glossary disagrees with terminology registry",
    )


# Source forms that must not be left once the terms are printed, including
# the abbreviations that edition/prose.json prints in full where they stand.
# "Rom." is Brenton's Roman edition, unless a chapter follows: then it is the
# edition's abbreviation for Romans.
UNPRINTED = re.compile(
    r"\bi\. e\.|\bq\. d\.|\b[Ss]cil\.|\bSept\b|\b[Cc]omp\.|\d AD\b|&c\b|\b[ab]\.[dc]\."
    r"|(?<![\w.])(?:[ON]\. ?T|A\. V|Ald|Complut|Vulg)(?!\w)|\bAV\b"
    r"|\b(?:App|Chrysost|Gram|Qu|om|nom|voc|absol|infin|imper|pl|pp?|qy|viz|niph"
    r"|fem|ob|sing|fut|Conf)\.|\bRom\.(?! \d)|\bCateches\b|\bult\b|\b4to\b|\bEng\. Ver\b|\d\.(?:li|[sd])\b"
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
