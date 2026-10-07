"""The appendix of readings: every verse of the New Testament where the
Byzantine text differs from the Received Text, with the Greek of both and,
where the English changes, the King James Bible's words and the edition's.

The rows are read from what the reconciliation worked out and from the
books as the edition prints them; the blocks are USJ for the editor's page
that asks for them (content/byzantine.sfm), each verse's entry a run of
blocks, so that the sample can print the entries of its chapters alone.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import bible.references
from bible import scripture, usj
from bible.byzantine.decisions import ref_key
from bible.byzantine.english import verses_of, without_subscriptions
from bible.byzantine.greek import ascii_greek, with_accents
from bible.byzantine.stages import Context
from bible.references import parse_verse
from bible.usj import Document, Node


@dataclass(frozen=True)
class Unit:
    """One difference of the Greek texts within a verse, with diacritics:
    the Received Text's words and the Byzantine text's, and their printed
    accented forms where the difference is one of accent alone."""

    tr: str
    rp: str
    accented: tuple[str, str] | None = None


@dataclass(frozen=True)
class Row:
    """One verse of the appendix: where the edition prints it, where the
    King James Bible has it, the Greek of both texts, the English before
    and after where it changes, and how the verse stands: changed, the
    same in English, or omitted."""

    reference: str
    source: str
    kind: str
    greek_tr: str
    greek_rp: str
    units: tuple[Unit, ...]
    kjv: str | None = None
    oleb: str | None = None

    @property
    def book(self) -> str:
        return self.reference.split()[0]

    @property
    def chapter(self) -> int:
        return parse_verse(self.reference).chapter


def rows(
    found: Context,
    kjv_documents: Mapping[str, Document],
    documents: Mapping[str, Document],
) -> list[Row]:
    """Every verse with a Greek difference, a changed English, or a place
    other than the King James Bible's, in the order the edition prints them;
    the verses the Byzantine text lacks stand where the King James Bible has
    them. The English of both Bibles is read from their books as the edition
    spells them: the King James books before the Byzantine readings, and the
    books as printed, so that only the readings differ."""
    structure = found["structure"]
    tr = {ref: list(words) for ref, words in found["tr_accented"].items()}
    rp = {
        ref: with_accents(found["rp"][ref], verse["accented"])
        for ref, verse in found["printed"].items()
    }
    # Keep the established contrasts, even where the additional transcription
    # accents the TR differently. These also belong in full-verse comparisons.
    for unit in found["units"]:
        if unit["class"] == "accent":
            for text, plain, ref, span, marked in (
                (tr, found["tr"], unit["ref"], unit["tr_range"], unit["tr_accented"]),
                (
                    rp,
                    found["rp"],
                    unit["target_ref"],
                    unit["rp_range"],
                    unit["rp_accented"],
                ),
            ):
                if " … " in marked:
                    # Mark's three numerals/prepositions are quoted with
                    # ellipses; the words between them retain their own marks.
                    parts = marked.split(" … ")
                    forms = {ascii_greek(part) for part in parts}
                    positions = [at for at in range(*span) if plain[ref][at] in forms]
                    if len(forms) != 1 or len(positions) != len(parts):
                        raise ValueError(f"Ambiguous appendix accent scope: {ref}")
                    for at, part in zip(positions, parts, strict=True):
                        text[ref][at] = with_accents([plain[ref][at]], [part])[0]
                else:
                    text[ref][slice(*span)] = with_accents(
                        plain[ref][slice(*span)], [marked]
                    )
    kjv = {ref: verse.text for ref, verse in verses_of(kjv_documents).items()}
    units_at: dict[str, list[Unit]] = {}
    accents: dict[str, list[Unit]] = {}
    for unit in found["units"]:
        if unit["class"] == "structural":
            continue
        listed = accents if unit["class"] == "accent" else units_at
        listed.setdefault(unit["target_ref"], []).append(
            Unit(
                " ".join(tr[unit["ref"]][slice(*unit["tr_range"])]),
                " ".join(rp[unit["target_ref"]][slice(*unit["rp_range"])]),
                (
                    (unit["tr_accented"], unit["rp_accented"])
                    if unit["class"] == "accent"
                    else None
                ),
            )
        )
    # Both without the epistles' subscriptions, which no verse holds.
    printed = {
        ref: scripture.plain(verse.text)
        for ref, verse in verses_of(
            {code: without_subscriptions(doc) for code, doc in documents.items()}
        ).items()
    }
    result = []
    for ref in sorted(printed, key=ref_key):
        source = structure.kjv_ref(ref)
        before = kjv.get(source)
        after = printed[ref]
        units = (*units_at.get(ref, ()), *accents.get(ref, ()))
        if before is None:
            continue
        if not units and source == ref and scripture.plain(before) == after:
            continue
        kind = (
            "changed" if scripture.plain(before) != after or source != ref else "same"
        )
        result.append(
            Row(
                ref,
                source,
                kind,
                " ".join(tr.get(source, [])),
                " ".join(rp.get(ref, [])),
                tuple(units),
                scripture.plain(before) if kind == "changed" else None,
                after if kind == "changed" else None,
            )
        )
    for ref in sorted(structure.omitted, key=ref_key):
        result.append(
            Row(
                ref,
                ref,
                "omitted",
                " ".join(tr[ref]),
                "",
                (),
                scripture.plain(kjv[ref]),
                None,
            )
        )
    return sorted(result, key=lambda row: ref_key(row.reference))


def greek(text: str) -> Node | str:
    return usj.char("wg", text) if text else ""


def blocks(
    listed: Sequence[Row],
    books: bible.references.Books,
    labels: Mapping[str, str],
) -> tuple[list[Node], list[tuple[Row, int, int]]]:
    """The appendix's blocks: a heading for each book, and under it one
    entry per verse. A verse whose English changes gives both texts' Greek
    and both Bibles' English, each on a line; a verse whose English stands
    gives the Greek words that differ, on one line. Returns the blocks and
    each entry's run of them, for the sample to choose by chapter."""
    result: list[Node] = []
    spans: list[tuple[Row, int, int]] = []
    current = None
    tr, rp, kjv, oleb, omits = (labels[k] for k in ("tr", "rp", "kjv", "oleb", "omits"))
    omits_verse = f"{omits} the verse"
    for row in listed:
        if row.book != current:
            current = row.book
            result.append(usj.para("is1", books.names[current]))
        start = len(result)
        # Under its book's heading, a verse is its chapter and number alone.
        heading: list[Node | str] = [usj.char("bd", parse_verse(row.reference).label)]
        if row.source != row.reference:
            heading.append(f" ({kjv} {parse_verse(row.source).label})")
        if row.kind == "same":
            parts: list[Node | str] = []
            # A word that differs twice in one verse (David's name) is listed once.
            distinct = {
                (ascii_greek(u.tr), ascii_greek(u.rp), u.accented): u for u in row.units
            }
            for unit in distinct.values():
                if parts:
                    parts.append("; ")
                if unit.accented:
                    parts += [
                        f"{tr} ",
                        greek(unit.accented[0]),
                        f", {rp} ",
                        greek(unit.accented[1]),
                    ]
                elif not unit.rp:
                    parts += [f"{tr} ", greek(unit.tr), f", {rp} {omits}"]
                elif not unit.tr:
                    parts += [f"{tr} {omits}, {rp} ", greek(unit.rp)]
                else:
                    parts += [f"{tr} ", greek(unit.tr), f", {rp} ", greek(unit.rp)]
            result.append(usj.para("im", *heading, " ", *parts))
        else:
            result.append(usj.para("im", *heading))
            result.append(
                usj.para("ili1", f"{tr} ", greek(row.greek_tr) or omits_verse)
            )
            result.append(
                usj.para("ili1", f"{rp} ", greek(row.greek_rp) or omits_verse)
            )
            result.append(usj.para("ili1", f"{kjv} {row.kjv}"))
            result.append(
                usj.para(
                    "ili1",
                    f"{oleb} {row.oleb}" if row.oleb else f"{oleb} {omits_verse}",
                )
            )
        spans.append((row, start, len(result)))
    return result, spans
