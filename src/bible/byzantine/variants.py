"""The textual variants: every verse of the New Testament where the
Byzantine text differs from the Received Text, with the Greek of both and,
where the English changes, the King James Bible's words and the edition's.

The rows are read from what the reconciliation worked out and from the
books as the edition prints them. The website publishes each verse's lanes:
the Greek of both texts and, where the English changes, the words of both
Bibles, each lane the words the two witnesses share and, where they differ,
both readings. The book prints none of it.
"""

from __future__ import annotations

import itertools
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal, NotRequired, TypedDict, cast

import bible.terminology
from bible import scripture
from bible.byzantine import received
from bible.byzantine.crosswire import presentation_bridge
from bible.byzantine.decisions import ref_key
from bible.byzantine.english import verses_of
from bible.byzantine.greek import ascii_greek, letter_key, occurrences
from bible.byzantine.notes import source_range
from bible.byzantine.presentation import corresponding, diff_spans, passage_spans
from bible.byzantine.stages import Reconciliation
from bible.checks import require
from bible.scripture import Verse
from bible.usj import Document


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
    """One verse of the variants: where the edition prints it, where the
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
    # Whether the apparatuses establish the Received Text's reading at every
    # difference of the verse (received.status), or only Scrivener's.
    received: bool = True
    # The Greek both texts share that a correction of the English is about,
    # as the correction cites it.
    about: tuple[str, ...] = ()


# A lane of a verse's entry, as the website publishes it: the source witness
# and the adopted one, the language of their words, and their segments: a
# string of words both have, a gap where words in agreement are left out,
# a reading, the source's words (from) and the adopted text's (to), one of
# them missing where that witness has nothing there, or words both have that
# a correction of the English is about.
Gap = TypedDict("Gap", {"gap": Literal[True]})
Reading = TypedDict("Reading", {"from": str, "to": str}, total=False)
About = TypedDict("About", {"about": str})
Segment = str | Gap | Reading | About
Lane = TypedDict(
    "Lane",
    {
        "from": str,
        "to": str,
        "language": Literal["grc", "en"],
        "segments": list[Segment],
        # The accented forms as the apparatus quotes them, where they differ
        # from the printed texts'.
        "apparatus": NotRequired[Literal[True]],
    },
)

PreparedGreek = tuple[
    dict[str, list[str]], dict[str, list[str]], dict[str, tuple[str, str]]
]


def prepare_greek(found: Reconciliation) -> PreparedGreek:
    """Prepare both texts and accent-only contrasts for display, without
    changing the sources or their token boundaries."""
    tr = {ref: list(words) for ref, words in found.greek.tr_alignment.text.items()}
    rp = {ref: list(verse["accented"]) for ref, verse in found.greek.printed.items()}
    contrasts: dict[str, tuple[str, str]] = {}
    for unit in found.greek.units:
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
                plain = found.greek.tr if side == "tr" else found.greek.rp
                positions = [at for at in range(*span) if plain[ref][at] in forms]
                require(
                    len(forms) == 1 and len(positions) == len(quoted.split(" … ")),
                    f"Ambiguous accent scope in the variants: {ref}",
                )
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
    found: Reconciliation, side: str, ref: str, span: Sequence[int]
) -> tuple[int, int]:
    """Source word offsets, including a whole joined word at either edge."""
    alignment = found.greek.tr_alignment if side == "tr" else found.greek.rp_alignment
    return alignment.project(ref, span)


def passage_ranges(
    found: Reconciliation, ref: str, target: str, left: str, right: str
) -> tuple[tuple[int, int, int, int], ...]:
    """Project ledger units into faithful passages for both consumers."""
    lo = [m.start() for m in re.finditer(r"\S+", left)] + [len(left)]
    ro = [m.start() for m in re.finditer(r"\S+", right)] + [len(right)]
    ranges = []
    verse_units = (
        u
        for u in found.greek.units
        if u["ref"] == ref and u["target_ref"] == target and u["class"] != "structural"
    )
    for u in sorted(verse_units, key=lambda u: (u["tr_range"][0], u["rp_range"][0])):
        a, b = projected(found, "tr", ref, u["tr_range"])
        c, d = projected(found, "rp", target, u["rp_range"])
        ranges.append((lo[a], lo[b], ro[c], ro[d]))
    return tuple(ranges)


def selections(
    found: Reconciliation,
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
        for row in found.verified.dispositions
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
            for row in found.verified.dispositions
            if row["ref"] == ref and row["disposition"] == "structural"
        ]
        if ref != target or structural:
            if not (
                found.greek.structure.moved.get(ref) == target
                and len(structural) == 1
                and structural[0].get("action") == "move"
                and structural[0].get("target_ref") == target
                and structural[0].get("execution") == "applied"
                and "old" in structural[0]
            ):
                return texts, whole, ()
        if not greek_only:
            original = found.english.kjv[ref]
            bridge = found.english.aligned.get(ref)
            if bridge is None:
                tagged = found.english.crosswire[ref]
                bridge = presentation_bridge(tagged, found.greek.tr[ref], original)
                # Absent tags can leave bounded gaps; contradictory evidence
                # must not become an apparently harmless gap in the bridge.
                for link in tagged["links"]:
                    if len(link["src"]) != len(link["forms"]) or any(
                        not p.isdigit()
                        or not 0 < int(p) <= len(found.greek.tr[ref])
                        or ascii_greek(form) != found.greek.tr[ref][int(p) - 1]
                        for p, form in zip(link["src"], link["forms"])
                    ):
                        invalid.append(project(tagged["text"], before, link["range"]))
            prepared = (
                prepared_verses
                if prepared_verses is not None
                else verses_of(
                    {target.split()[0]: found.edited.prepared[target.split()[0]]}
                )
            )[target].text
            # A verse with a correction of shared Greek was quoted whole above,
            # so every edit here is a reading's, with its TR note or none.
            edits = [
                edit
                for row in found.verified.dispositions
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
            for position in range(len(found.greek.tr[ref]))
            for x, y in [projected(found, "tr", ref, (position, position + 1))]
        ]
        greek_targets: list[list[int]] = [[] for _ in greek_words]
        for word_index, positions in enumerate(bridge["positions"]):
            for position in positions:
                require(
                    0 <= position < len(greek_words), "Invalid correspondence position"
                )
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
    found: Reconciliation,
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
    structure = found.greek.structure
    tr, rp, contrasts = prepare_greek(found)
    kjv = {ref: verse.text for ref, verse in verses_of(kjv_documents).items()}
    units_at: dict[str, list[Unit]] = {}
    accents: dict[str, list[Unit]] = {}
    evidence = received.rows(found.greek.tcgnt, found.greek.apparatus)
    # A unit of a kind the apparatuses do not record (inventory_absence),
    # and on which they say nothing, says nothing either way. The verses are
    # the edition's, where the units are listed (target_ref); an omitted
    # verse keeps its own number there.
    statuses = {u["id"]: received.status(u, evidence) for u in found.greek.units}
    unreceived = {
        unit["target_ref"]
        for unit in found.greek.units
        if statuses[unit["id"]] != "TR"
        and not (statuses[unit["id"]] is None and unit.get("inventory_absence"))
    }
    for unit in found.greek.units:
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
    # A subscription is a sidebar, which no verse holds.
    printed = {
        ref: scripture.plain(verse.text) for ref, verse in verses_of(documents).items()
    }
    prepared_verses = verses_of(found.edited.prepared)
    # The Greek each correction of the English where the texts agree cites,
    # by the King James verse it corrects.
    about: dict[str, tuple[str, ...]] = {}
    for override in found.decisions.overrides:
        if not override["unit_ids"]:
            for edit in override["edits"]:
                cited = about.get(edit["ref"], ())
                if edit["greek"] not in cited:
                    about[edit["ref"]] = (*cited, edit["greek"])
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
                ref not in unreceived,
                about.get(source, ()),
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
                received=ref not in unreceived,
            )
        )
    return sorted(result, key=lambda row: ref_key(row.reference))


def accent_key(text: str) -> str:
    """Compare diacritics without case, punctuation, or grave/acute variation."""
    return acute(letter_key(text.replace("…", "")))


def acute(text: str) -> str:
    """The words with a grave accent read as the acute it stands for."""
    return unicodedata.normalize(
        "NFC", unicodedata.normalize("NFD", text).replace("\u0300", "\u0301")
    )


def joined_spans(
    texts: Sequence[str],
    selected: Sequence[Sequence[tuple[int, int]]],
    side: int,
    anchors: Sequence[tuple[int, int, int, int]],
) -> list[tuple[str, str]]:
    """The selected passages' lossless spans joined, with the words left out
    around and between them marked as gaps: the markers passage_spans sets,
    never ellipses in the source wording, one separator between passages."""
    spans: list[tuple[str, str]] = []
    for index, passage in enumerate(selected):
        parts = passage_spans(texts, passage, side, anchors, greek=side == 0)
        a, b = passage[side]
        if a:
            parts[0] = ("gap", parts[0][1])
        if b < len(texts[side]):
            parts[-1] = ("gap", parts[-1][1])
        if index and a:
            parts.pop(0)
        if index < len(selected) - 1 and b < len(texts[side]):
            parts.pop()
        if index:
            spans.append(("gap", " … "))
        spans.extend(parts)
    return spans


def segments(spans: Sequence[tuple[str, str]]) -> list[Segment]:
    """The spans as the website publishes them: words the witnesses share
    joined, a gap for each omission marker with its spaces kept as words,
    and a reading for each run of differences, the source's words on one
    side and the adopted text's on the other. Spaces and marks both sides
    of a reading open or close with are words they share."""
    result: list[Segment] = []

    def shared(text: str) -> None:
        if text and result and isinstance(result[-1], str):
            result[-1] += text
        elif text:
            result.append(text)

    def reading(before: str, after: str) -> None:
        while before and after and before[0] == after[0] and not before[0].isalnum():
            shared(before[0])
            before, after = before[1:], after[1:]
        end = 0
        while (
            end < min(len(before), len(after))
            and before[-end - 1] == after[-end - 1]
            and not before[-end - 1].isalnum()
        ):
            end += 1
        before, after, trailing = (
            before[: len(before) - end],
            after[: len(after) - end],
            before[len(before) - end :],
        )
        words: Reading = {}
        if before:
            words["from"] = before
        if after:
            words["to"] = after
        if words:
            result.append(words)
        shared(trailing)

    before = after = ""
    for kind, text in (*spans, ("equal", "")):
        if kind in {"delete", "insert"}:
            if kind == "delete":
                before += text
            else:
                after += text
            continue
        if before or after:
            reading(before, after)
            before = after = ""
        if kind == "equal":
            shared(text)
        else:
            require(kind == "gap", f"Unknown span kind: {kind}")
            lead, _, trail = text.partition("…")
            shared(lead)
            result.append({"gap": True})
            shared(trail)
    return result


def witness(segments: Sequence[Segment], side: Literal["from", "to"]) -> str:
    """One witness's words of a lane, with an ellipsis for each gap."""

    def words(segment: Segment) -> str:
        if isinstance(segment, str):
            return segment
        if "gap" in segment:
            return "…"
        if "about" in segment:
            return cast(About, segment)["about"]
        return segment.get(side, "")

    return "".join(map(words, segments))


def marked(result: list[Segment], cited: Sequence[str]) -> list[Segment]:
    """The segments with the words both witnesses share of each cited phrase
    set apart. A phrase is RP2026's, so it is found once in the adopted
    text, read without case or punctuation, as its decision was checked; a
    reading within it, of a movable ν, a breathing, or the punctuation, stays
    a reading, and a gap breaks it. Words an earlier phrase set apart are
    this one's too."""
    result = list(result)
    for phrase in cited:
        # The adopted text's words, with where each segment starts in them.
        text = witness(result, "to")
        lengths = [len(witness([segment], "to")) for segment in result]
        starts = list(itertools.accumulate(lengths, initial=0))[:-1]
        words = list(re.finditer(r"\S+", text))
        hits = occurrences(
            [letter_key(word.group().replace("…", "")) for word in words],
            [letter_key(word) for word in phrase.split()],
        )
        require(len(hits) == 1, f"Greek of a correction not once in its lane: {phrase}")
        a, b = words[hits[0]].start(), words[hits[0] + len(phrase.split()) - 1].end()
        marks: list[Segment] = []
        shared = False
        for start, segment in zip(starts, result, strict=True):
            if not isinstance(segment, str):
                if "about" in segment:
                    end = start + len(cast(About, segment)["about"])
                    shared |= start < b and a < end
                marks.append(segment)
                continue
            lo, hi = max(a - start, 0), min(b - start, len(segment))
            # The spaces and punctuation around the words are not theirs.
            while lo < hi and not lettered(segment[lo]):
                lo += 1
            while lo < hi and not lettered(segment[hi - 1]):
                hi -= 1
            if lo >= hi:
                marks.append(segment)
                continue
            shared = True
            marks += [segment[:lo]] if lo else []
            marks.append({"about": segment[lo:hi]})
            marks += [segment[hi:]] if hi < len(segment) else []
        require(shared, f"Greek of a correction shares no words in its lane: {phrase}")
        result = marks
    return result


def lettered(character: str) -> bool:
    """A letter, or a mark that belongs to the letter before it."""
    return unicodedata.category(character)[0] in "LM"


def apparatus_differs(unit: Unit) -> bool:
    """Whether the apparatus accents a unit otherwise than the printed texts."""
    if unit.apparatus is None or unit.accented is None:
        return False
    return tuple(map(accent_key, unit.apparatus)) != tuple(
        map(accent_key, unit.accented)
    )


def lane(
    source: str,
    target: str,
    language: Literal["grc", "en"],
    spans: Sequence[tuple[str, str]],
    *,
    apparatus: bool = False,
    about: Sequence[str] = (),
) -> Lane:
    """One lane: the witnesses' spans as segments, with the words of the
    phrases a correction of the English is about set apart."""
    result: Lane = {
        "from": source,
        "to": target,
        "language": language,
        "segments": marked(segments(spans), about),
    }
    if apparatus:
        result["apparatus"] = True
    return result


def lanes(row: Row, terms: bible.terminology.Registry) -> list[Lane]:
    """A verse's lanes: the Greek of the Received Text, or Scrivener's where
    the apparatuses do not establish it, against the Byzantine text; the
    King James words against the edition's where they change; and the
    apparatus's accents where they differ from the printed texts'. The Greek
    and the English compare the selected passages, the words left out around
    and between them marked as gaps."""
    tr, rp, kjv, oleb, scrivener = (
        terms.display(k)
        for k in (
            "textus-receptus",
            "robinson-pierpont",
            "king-james-version",
            "orthodox-liturgical-english-bible",
            "scrivener",
        )
    )
    texts = (row.greek_tr, row.greek_rp, row.kjv or "", row.oleb or "")
    selected = row.passages or (tuple((0, len(t)) for t in texts),)
    result = [
        lane(
            tr if row.received else scrivener,
            rp,
            "grc",
            joined_spans(texts, selected, 0, row.greek_ranges),
            about=row.about,
        )
    ]
    if row.kjv is not None:
        result.append(
            lane(kjv, oleb, "en", joined_spans(texts, selected, 2, row.english_ranges))
        )
    for unit in row.units:
        if apparatus_differs(unit):
            assert unit.apparatus is not None
            # The apparatus quotes words apart with an ellipsis between them,
            # which marks words left out, as a gap between passages does.
            spans = [
                ("gap" if kind == "equal" and part == "…" else kind, part)
                for kind, text in diff_spans(*unit.apparatus, greek=True)
                for part in (re.split("(…)", text) if kind == "equal" else [text])
                if part
            ]
            result.append(lane(tr, rp, "grc", spans, apparatus=True))
    return result
