"""The appendix of readings: every verse of the New Testament where the
Byzantine text differs from the Received Text, with the Greek of both and,
where the English changes, the King James Bible's words and the edition's.

The rows are read from what the reconciliation worked out and from the
books as the edition prints them; the blocks are USJ for the editor's page
that asks for them (content/byzantine.sfm), each verse's entry a run of
blocks, so that the sample can print the entries of its chapters alone.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

import bible.references
from bible import scripture, usj
from bible.byzantine.crosswire import presentation_bridge
from bible.byzantine.decisions import ref_key
from bible.byzantine.english import verses_of, without_subscriptions
from bible.byzantine.greek import accent_letters, ascii_greek
from bible.byzantine.notes import source_range
from bible.byzantine.presentation import (
    corresponding,
    diff_spans,
    greek_display,
    passage_spans,
)
from bible.byzantine.stages import Context
from bible.references import parse_verse
from bible.scripture import Verse
from bible.usj import Document, Node


class Uncertain(Exception):
    """A revised boundary that the words do not place uniquely."""


@dataclass(frozen=True)
class Unit:
    """One difference of the Greek texts within a verse, with diacritics:
    the Received Text's words and the Byzantine text's, and their printed
    accented forms where the difference is one of accent alone."""

    tr: str
    rp: str
    accented: tuple[str, str] | None = None
    apparatus: tuple[str, str] | None = None


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
    greek_ranges: tuple[tuple[int, int, int, int], ...] = ()
    passages: tuple[tuple[tuple[int, int], ...], ...] = ()
    english_ranges: tuple[tuple[int, int, int, int], ...] = ()

    @property
    def book(self) -> str:
        return self.reference.split()[0]

    @property
    def chapter(self) -> int:
        return parse_verse(self.reference).chapter


PreparedGreek = tuple[
    dict[str, list[str]], dict[str, list[str]], dict[str, tuple[str, str]]
]


def prepare_greek(found: Context) -> PreparedGreek:
    """Prepare both texts and accent-only contrasts for display, without
    changing the sources or their token boundaries."""
    tr = {ref: list(words) for ref, words in found["tr_accented"].items()}
    rp = {ref: list(verse["accented"]) for ref, verse in found["printed"].items()}
    contrasts: dict[str, tuple[str, str]] = {}
    for unit in found["units"]:
        if unit["class"] != "accent":
            continue
        pair = []
        for side, text, ref in (
            ("tr", tr, unit["ref"]),
            ("rp", rp, unit["target_ref"]),
        ):
            span = unit["tr_range"] if side == "tr" else unit["rp_range"]
            quoted = unit["tr_accented"] if side == "tr" else unit["rp_accented"]
            if " … " in quoted:
                forms = {ascii_greek(part) for part in quoted.split(" … ")}
                plain = found["tr"] if side == "tr" else found["rp"]
                positions = [at for at in range(*span) if plain[ref][at] in forms]
                if len(forms) != 1 or len(positions) != len(quoted.split(" … ")):
                    raise ValueError(f"Ambiguous appendix accent scope: {ref}")
                pair.append(
                    " … ".join(
                        " ".join(
                            text[ref][slice(*projected(found, side, ref, (at, at + 1)))]
                        )
                        for at in positions
                    )
                )
            else:
                pair.append(
                    " ".join(text[ref][slice(*projected(found, side, ref, span))])
                )
        contrasts[unit["id"]] = pair[0], pair[1]
    return tr, rp, contrasts


def projected(
    found: Context, side: str, ref: str, span: Sequence[int]
) -> tuple[int, int]:
    """Source word offsets, including a whole joined word at either edge."""
    return found["tr_alignment" if side == "tr" else "rp_alignment"].project(ref, span)


def passage_ranges(
    found: Context, ref: str, target: str, left: str, right: str
) -> tuple[tuple[int, int, int, int], ...]:
    """Project ledger units into faithful passages for both consumers."""
    lo = [m.start() for m in re.finditer(r"\S+", left)] + [len(left)]
    ro = [m.start() for m in re.finditer(r"\S+", right)] + [len(right)]
    ranges = []
    verse_units = (
        u
        for u in found["units"]
        if u["ref"] == ref and u["target_ref"] == target and u["class"] != "structural"
    )
    for u in sorted(verse_units, key=lambda u: (u["tr_range"][0], u["rp_range"][0])):
        a, b = projected(found, "tr", ref, u["tr_range"])
        c, d = projected(found, "rp", target, u["rp_range"])
        ranges.append((lo[a], lo[b], ro[c], ro[d]))
    return tuple(ranges)


def selections(
    found: Context,
    ref: str,
    target: str,
    left: str,
    right: str,
    before: str,
    after: str,
    prepared_verses: Mapping[str, Verse] | None = None,
) -> tuple[
    tuple[str, ...],
    tuple[tuple[tuple[int, int], ...], ...],
    tuple[tuple[int, int, int, int], ...],
]:
    """Corresponding display ranges, projected from the executed edition.

    Unchanged English needs only Greek correspondence. Paired passages use
    executed English constructions; revision boundaries must lie in unchanged
    character runs. Verified moves use the source KJV and destination edition.
    Uncertain projections and unsupported structural changes quote complete verses.
    """
    texts = (left, right, before, after)
    greek_only = before == after
    sides = 2 if greek_only else 4
    whole = (tuple((0, len(t)) for t in texts),)
    # A correction's "Or," note does not anchor a shortened comparison of the
    # Greek texts. Quote the verse whole so that every correction and variant
    # stays visible.
    if not greek_only and any(
        row["disposition"] == "shared"
        and any(edit["ref"] == ref for edit in row.get("edits", []))
        for row in found["dispositions"]
    ):
        return texts, whole, ()
    links: list[tuple[int, int, int, int, int, int]] = []
    seeds: list[list[tuple[int, int]]] = []
    english: list[tuple[int, int, int, int]] = []
    invalid: list[tuple[int, int]] = []

    projections: dict[tuple[str, str], list[tuple[int, int, int]]] = {}

    def collapsed(text: str, offset: int) -> int:
        # A raw offset in its verse's words with their spacing collapsed,
        # counting a space just before it.
        return len(scripture.plain(text[:offset] + "x")) - 1

    def project(source: str, revised: str, span: Sequence[int]) -> tuple[int, int]:
        if source == revised:
            return span[0], span[1]
        bounds = []
        key = (source, revised)
        if key not in projections:
            projections[key] = [
                (block.a, block.b, block.size)
                for block in SequenceMatcher(
                    None, source, revised, autojunk=False
                ).get_matching_blocks()
            ]
        matches = projections[key]
        for offset in span:
            candidates = {c + offset - a for a, c, n in matches if a <= offset <= a + n}
            if len(candidates) != 1:
                raise Uncertain(f"Uncertain revised boundary: {ref}")
            bounds.append(candidates.pop())
        return bounds[0], bounds[1]

    try:
        structural = [
            row
            for row in found["dispositions"]
            if row["ref"] == ref and row["disposition"] == "structural"
        ]
        if ref != target or structural:
            if not (
                found["structure"].moved.get(ref) == target
                and len(structural) == 1
                and structural[0].get("action") == "move"
                and structural[0].get("target_ref") == target
                and structural[0].get("execution") == "applied"
                and "old" in structural[0]
            ):
                return texts, whole, ()
        if not greek_only:
            original = found["kjv"][ref]
            bridge = found.get("aligned", {}).get(ref)
            if bridge is None:
                tagged = found["crosswire"][ref]
                bridge = presentation_bridge(tagged, found["tr"][ref], original)
                # Absent tags can leave bounded gaps; contradictory evidence
                # must not become an apparently harmless gap in the bridge.
                for link in tagged["links"]:
                    if len(link["src"]) != len(link["forms"]) or any(
                        not p.isdigit()
                        or not 0 < int(p) <= len(found["tr"][ref])
                        or ascii_greek(form) != found["tr"][ref][int(p) - 1]
                        for p, form in zip(link["src"], link["forms"])
                    ):
                        invalid.append(project(tagged["text"], before, link["range"]))
            prepared = (
                prepared_verses
                if prepared_verses is not None
                else verses_of(
                    {target.split()[0]: found["prepared"][target.split()[0]]}
                )
            )[target].text
            # A verse with a correction of shared Greek was quoted whole above,
            # so every edit here is a reading's, with its TR note or none.
            edits = [
                edit
                for row in found["dispositions"]
                for edit in row.get("edits", [])
                if edit["ref"] == ref
            ]
            for edit in edits:
                if "note" not in edit:
                    continue  # the supplied marking alone changed
                scope = edit.get("note_scope", {})
                if scope.get("ref", ref) != target or not scope.get("range"):
                    return texts, whole, ()
                span = scope["range"]
                assert span is not None
                if scope.get("source_range"):
                    a, b = scope["source_range"]
                elif edit["kind"] in {"insert", "delete"}:
                    a, b = source_range(span[0], span[1], edits)
                    lo, hi = edit["applied_range"]
                    a, b = min(a, lo), max(b, hi)
                else:
                    return texts, whole, ()
                c, d = span
                a, b = project(
                    scripture.plain(original),
                    before,
                    (collapsed(original, a), collapsed(original, b)),
                )
                c, d = project(
                    scripture.plain(prepared),
                    after,
                    (collapsed(prepared, c), collapsed(prepared, d)),
                )
                english.append((a, b, c, d))
            english = sorted(set(english))
        greek_ranges = passage_ranges(found, ref, target, left, right)
        comparisons = [(0, greek_ranges)]
        if not greek_only:
            comparisons.append((2, tuple(english)))
        for side, anchors in comparisons:
            for a, b, c, d in anchors:
                links.append((side, a, b, side + 1, c, d))
                seed = [(-1, -1)] * sides
                seed[side], seed[side + 1] = (a, b), (c, d)
                seeds.append(seed)
            # Match context separately between construction anchors.
            lo = ro = 0
            for a, b, c, d in [
                *anchors,
                (
                    len(texts[side]),
                    len(texts[side]),
                    len(texts[side + 1]),
                    len(texts[side + 1]),
                ),
            ]:
                old, new = texts[side][lo:a], texts[side + 1][ro:c]
                for op, x, y, z, w in SequenceMatcher(
                    None, old, new, autojunk=False
                ).get_opcodes():
                    if (
                        op == "equal"
                        or side == 0
                        and all(
                            k == "equal"
                            for k, _ in diff_spans(old[x:y], new[z:w], greek=True)
                        )
                        and y - x == w - z
                    ):
                        for word in re.finditer(r"\S+", old[x:y]):
                            start, end = x + word.start(), x + word.end()
                            links.append(
                                (
                                    side,
                                    lo + start,
                                    lo + end,
                                    side + 1,
                                    ro + z + start - x,
                                    ro + z + end - x,
                                )
                            )
                    else:
                        links.append((side, lo + x, lo + y, side + 1, ro + z, ro + w))
                        seed = [(-1, -1)] * sides
                        seed[side], seed[side + 1] = (lo + x, lo + y), (ro + z, ro + w)
                        seeds.append(seed)
                lo, ro = b, d
        if greek_only:
            selected = tuple(
                (*passage, whole[0][2], whole[0][3])
                for passage in corresponding(texts[:2], links, seeds)
            )
            return texts, selected, ()
        offsets = [m.start() for m in re.finditer(r"\S+", left)] + [len(left)]
        assert bridge is not None
        # The bridge's word ranges address the raw KJV verse, like the edits'.
        english_words = [
            project(
                scripture.plain(original),
                before,
                (collapsed(original, span[0]), collapsed(original, span[1])),
            )
            for span in bridge["word_ranges"]
        ]
        for (a, b), positions in zip(english_words, bridge["positions"], strict=True):
            for position in positions:
                x, y = projected(found, "tr", ref, (position, position + 1))
                links.append((0, offsets[x], offsets[y], 2, a, b))
        selected = tuple(corresponding(texts, links, seeds))
        greek_words = [
            (offsets[x], offsets[y])
            for position in range(len(found["tr"][ref]))
            for x, y in [projected(found, "tr", ref, (position, position + 1))]
        ]
        greek_targets: list[list[int]] = [[] for _ in greek_words]
        for word_index, positions in enumerate(bridge["positions"]):
            for position in positions:
                if not 0 <= position < len(greek_words):
                    raise ValueError("Invalid correspondence position")
                greek_targets[position].append(word_index)
        for passage in selected:
            if any(a < passage[2][1] and passage[2][0] < b for a, b in invalid):
                return texts, whole, tuple(english)
            for words, targets, paired, retained_span, paired_span in (
                (greek_words, greek_targets, english_words, passage[0], passage[2]),
                (
                    english_words,
                    bridge["positions"],
                    greek_words,
                    passage[2],
                    passage[0],
                ),
            ):
                if not _bounded_correspondence(
                    words, targets, paired, retained_span, paired_span
                ):
                    return texts, whole, tuple(english)
        return texts, selected, tuple(english)
    except Uncertain:
        return texts, whole, ()


def _bounded_correspondence(
    words: Sequence[tuple[int, int]],
    targets: Sequence[Sequence[int]],
    paired: Sequence[tuple[int, int]],
    span: tuple[int, int],
    paired_span: tuple[int, int],
) -> bool:
    """Unmapped words require mapped neighbours inside both retained passages."""
    selected = [
        ps
        for (a, b), ps in zip(words, targets, strict=True)
        if a < span[1] and span[0] < b
    ]
    # Mapped first and last words bound every interior gap without inventing
    # lexical correspondence. Every neighbour's targets must also be retained.
    return bool(selected and selected[0] and selected[-1]) and all(
        paired_span[0] <= paired[p][0] <= paired[p][1] <= paired_span[1]
        for ps in selected
        for p in ps
    )


def rows(
    found: Context,
    kjv_documents: Mapping[str, Document],
    documents: Mapping[str, Document],
) -> list[Row]:
    """Every verse with a Greek difference, a changed English, or a place
    other than the King James Bible's, in the order the edition prints them;
    the verses the Byzantine text lacks stand where the King James Bible has
    them. The English of both Bibles is read from their books as the edition
    spells them: the original King James books and the books before
    verse-specific punctuation, including corrections of the English where the Greek texts agree.
    """
    structure = found["structure"]
    tr, rp, contrasts = prepare_greek(found)
    kjv = {ref: verse.text for ref, verse in verses_of(kjv_documents).items()}
    units_at: dict[str, list[Unit]] = {}
    accents: dict[str, list[Unit]] = {}
    for unit in found["units"]:
        if unit["class"] == "structural":
            continue
        listed = accents if unit["class"] == "accent" else units_at
        listed.setdefault(unit["target_ref"], []).append(
            Unit(
                " ".join(
                    tr[unit["ref"]][
                        slice(*projected(found, "tr", unit["ref"], unit["tr_range"]))
                    ]
                ),
                " ".join(
                    rp[unit["target_ref"]][
                        slice(
                            *projected(
                                found, "rp", unit["target_ref"], unit["rp_range"]
                            )
                        )
                    ]
                ),
                (contrasts[unit["id"]] if unit["class"] == "accent" else None),
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
    prepared_verses = verses_of(found["prepared"])
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
        left = " ".join(tr.get(source, []))
        right = " ".join(rp.get(ref, []))
        ranges = passage_ranges(found, source, ref, left, right)
        _, selected, english_ranges = selections(
            found,
            source,
            ref,
            left,
            right,
            scripture.plain(before),
            after,
            prepared_verses,
        )
        result.append(
            Row(
                ref,
                source,
                kind,
                " ".join(tr.get(source, [])),
                " ".join(rp.get(ref, [])),
                tuple(units),
                scripture.plain(before) if scripture.plain(before) != after else None,
                after if scripture.plain(before) != after else None,
                ranges,
                selected,
                english_ranges,
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


def accent_key(text: str) -> str:
    """Compare diacritics without case, punctuation or grave/acute variation."""
    return acute("".join(accent_letters(text.replace("…", "")))).lower()


def acute(text: str) -> str:
    """The words with a grave accent read as the acute it stands for."""
    return unicodedata.normalize(
        "NFC", unicodedata.normalize("NFD", text).replace("\u0300", "\u0301")
    )


def greek(text: str) -> list[Node | str]:
    """Set Greek and its normalized punctuation in GFS Didot."""
    text = greek_display(text)
    if not text.strip():
        return [text] if text else []
    leading = text[: len(text) - len(text.lstrip())]
    trailing = text[len(text.rstrip()) :]
    result: list[Node | str] = []
    if leading:
        result.append(leading)
    result.append(usj.char("wg", text.strip()))
    if trailing:
        result.append(trailing)
    return result


def comparison(
    spans: Sequence[tuple[str, str]], *, is_greek: bool = False
) -> list[Node | str]:
    """Bracket former readings upright; italicize new English, embolden Greek.

    Greek stays upright in its own font, including normalized punctuation.
    Brackets are outside all character styles. Boundary spaces belong to
    the printed prose, not to either reading; the source spans stay lossless.
    """
    if all(kind == "equal" for kind, _ in spans):
        return [
            part
            for _, value in spans
            for part in (greek(value) if is_greek else [value])
        ]

    # Arrange the prose before making character styles. Keep internal spacing
    # and every non-whitespace character, including punctuation-only changes.
    printed: list[tuple[str, str]] = []
    previous = "equal"
    previous_value = ""
    space = False
    for kind, raw in spans:
        value = raw.strip()
        space |= bool(raw[:1].isspace())
        if value:
            word = kind != "equal" and any(c.isalnum() for c in value)
            previous_word = previous != "equal" and any(
                c.isalnum() for c in previous_value
            )
            separate = (
                (word and previous_value[-1:].isalnum())
                or (previous_word and value[:1].isalnum())
                or (previous_word and word)
            )
            if value[0] not in ",;:.?!··∙)]}”’»\"'":
                if printed and (space or separate):
                    printed.append(("equal", " "))
                space = False
            # Closing punctuation keeps the pending boundary space for the
            # next reading, while staying beside the preceding words.
            printed.append((kind, value))
            previous, previous_value = kind, value
        space |= bool(raw[-1:].isspace())

    result: list[Node | str] = []
    joined: list[tuple[str, str]] = []
    for kind, value in printed:
        if kind == "equal" and joined and joined[-1][0] == "equal":
            joined[-1] = (kind, joined[-1][1] + value)
        else:
            joined.append((kind, value))
    for kind, value in joined:
        content = greek(value) if is_greek and value.strip() else [value]
        if kind == "delete":
            result.append("[")
            result.extend(content)
            result.append("]")
        elif kind == "insert":
            result.append(usj.char("bd" if is_greek else "it", *content))
        else:
            result.extend(content)
    return result


def joined_comparison(
    texts: Sequence[str],
    selected: Sequence[Sequence[tuple[int, int]]],
    side: int,
    anchors: Sequence[tuple[int, int, int, int]],
) -> list[Node | str]:
    """Join selected passages, retaining only the outer omission markers."""
    spans: list[tuple[str, str]] = []
    for index, passage in enumerate(selected):
        parts = passage_spans(texts, passage, side, anchors, greek=side == 0)
        a, b = passage[side]
        # These are the separate markers generated by passage_spans, never
        # ellipses in the source wording. One separator replaces both.
        if index and a:
            parts.pop(0)
        if index < len(selected) - 1 and b < len(texts[side]):
            parts.pop()
        if index:
            spans.append(("equal", " … "))
        spans.extend(parts)
    return comparison(spans, is_greek=side == 0)


def blocks(
    listed: Sequence[Row],
    books: bible.references.Books,
    labels: Mapping[str, str],
) -> tuple[list[Node], list[tuple[Row, int, int]]]:
    """The appendix's blocks: a heading for each book, and under it one
    entry per verse, with a Greek comparison and, where its complete wording
    changes, an English comparison. Returns the blocks and each entry's run
    of them, for the sample to choose by chapter."""
    result: list[Node] = []
    spans: list[tuple[Row, int, int]] = []
    current = None
    tr, rp, kjv, oleb, apparatus = (
        labels[k] for k in ("tr", "rp", "kjv", "oleb", "apparatus")
    )
    for row in listed:
        if row.book != current:
            current = row.book
            result.append(usj.para("is1", books.names[current]))
        start = len(result)
        # Under its book's heading, a verse is its chapter and number alone.
        heading: list[Node | str] = [usj.char("bd", parse_verse(row.reference).label)]
        if row.source != row.reference:
            heading.append(f" ({kjv} {parse_verse(row.source).label})")
        result.append(usj.para("im", *heading))
        texts = (row.greek_tr, row.greek_rp, row.kjv or "", row.oleb or "")
        selected = row.passages or (tuple((0, len(t)) for t in texts),)
        result.append(
            usj.para(
                "ili1",
                f"{tr} → {rp} ",
                *joined_comparison(texts, selected, 0, row.greek_ranges),
            )
        )
        if row.kjv is not None:
            result.append(
                usj.para(
                    "ili1",
                    f"{kjv} → {oleb} ",
                    *joined_comparison(texts, selected, 2, row.english_ranges),
                )
            )
        for unit in row.units:
            if (
                unit.apparatus
                and unit.accented
                and tuple(map(accent_key, unit.apparatus))
                != tuple(map(accent_key, unit.accented))
            ):
                result.append(
                    usj.para(
                        "ili1",
                        f"{apparatus}: {tr} → {rp} ",
                        *comparison(
                            diff_spans(*unit.apparatus, greek=True), is_greek=True
                        ),
                    )
                )
        spans.append((row, start, len(result)))
    return result, spans
