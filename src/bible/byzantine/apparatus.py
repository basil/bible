"""The modern-English apparatuses as reports attached to Greek units.

Boyd's TCENT notes are paired with his TCGNT Greek notes by order and sigla;
Thomason's FAA carries its own Greek beside its English, so its contrasts are
placed where that Greek matches Scrivener and RP2026; MSB and WEB are
placed only where their English contrast equals one already placed by its
Greek. A report says that a difference shows in English and how a modern
translation words it. It never supplies KJV wording.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from html import escape
from typing import Any, Unpack, cast

from lxml import html

from bible import scripture, usj
from bible.byzantine import BOOKS, BOOKS_BY_NAME, FAA, MSB, TCENT, WEB
from bible.byzantine.crosswire import attach_sole, equal_positions, spans, words
from bible.byzantine.english import surface_words, usj_markup, verse_markup
from bible.byzantine.greek import Structure, greek_words, occurrences
from bible.byzantine.rows import BoydNote, FaaRow, Report, SelectedListRow, Unit
from bible.sources import Content
from bible.usfm import GREEK


def signature(row: Mapping[str, Any]) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(sorted(v["sigla"])) for v in row["variants"])


def boyd_partition_subset(
    greek: Mapping[str, Any], english: Mapping[str, Any]
) -> list[int] | None:
    """Return omitted Greek groups for a closed ordered English subset.

    Every TR/SCR-bearing group must be retained. English can merge whole
    Greek groups, or omit a non-TR group, but cannot split a group.
    Nothing here compares or judges English wording.
    """
    gs, es = signature(greek), signature(english)
    if gs == es:
        return []
    for sigs in (gs, es):
        flat = [edition for group in sigs for edition in group]
        if any(not group for group in sigs) or len(flat) != len(set(flat)):
            return None
    matched: set[int] = set()
    for group in es:
        indices = [i for i, part in enumerate(gs) if set(part) <= set(group)]
        if {s for i in indices for s in gs[i]} != set(group):
            return None
        matched.update(indices)
    if any({"TR", "SCR"} & set(gs[i]) for i in range(len(gs)) if i not in matched):
        return None
    return [i for i in range(len(gs)) if i not in matched]


def ordered_pairs(candidates: Sequence[Iterable[int]]) -> dict[int, int]:
    """Return only pairs shared by every strictly increasing assignment.

    Empty candidate sets remain unpaired. They cannot supply order evidence.
    Forward/backward reachability avoids enumerating an exponential product.
    """
    active = [(i, sorted(set(c))) for i, c in enumerate(candidates) if c]
    if not active:
        return {}
    forward: list[set[int]] = []
    backward: list[set[int]] = [set() for _ in active]
    for n, (_, choices) in enumerate(active):
        forward.append(
            {c for c in choices if n == 0 or any(p < c for p in forward[n - 1])}
        )
    for n in range(len(active) - 1, -1, -1):
        backward[n] = {
            c
            for c in active[n][1]
            if n == len(active) - 1 or any(c < p for p in backward[n + 1])
        }
    if not forward[-1]:
        return {}
    pairs: dict[int, int] = {}
    for n, (i, _) in enumerate(active):
        viable = forward[n] & backward[n]
        if len(viable) == 1:
            pairs[i] = next(iter(viable))
    return pairs


def source_fields(row: BoydNote) -> Report:
    """The fields of a TCENT note that quote its source, for its report."""
    fields: Report = {}
    if "source_original" in row:
        fields["source_original"] = row["source_original"]
    if "source_original_html" in row:
        fields["source_original_html"] = row["source_original_html"]
    if "source_main_html" in row:
        fields["source_main_html"] = row["source_main_html"]
    if "source_address" in row:
        fields["source_address"] = row["source_address"]
    if "source_main_passages" in row:
        fields["source_main_passages"] = row["source_main_passages"]
    return fields


# Closed plain-English apparatus readings only. An omission is
# explicit; structural descriptions and unusual glyphs abstain.
def plain(value: str | None) -> str | None:
    if value == "---":
        return ""
    if value is None or not re.fullmatch(r"[A-Za-z0-9\s’'\"“”‘’,.;:!?—–-]+", value):
        return None
    return value


def tcent_reports(
    english: Iterable[BoydNote],
    greek: Iterable[BoydNote],
    units: Sequence[Unit],
    structure: Structure,
) -> list[Report]:
    by_ref: defaultdict[str, list[BoydNote]] = defaultdict(list)
    attachments: defaultdict[int, list[tuple[Unit, str]]] = defaultdict(list)
    for row in greek:
        by_ref[row["target_ref"]].append(row)
    for unit in units:
        for evidence in unit["inventories"]:
            if evidence["inventory"] == "tcgnt":
                attachments[evidence["entry"]].append((unit, evidence["scope"]))
    english_refs: defaultdict[str, list[BoydNote]] = defaultdict(list)
    for row in english:
        english_refs[row["target_ref"]].append(row)
    result: list[Report] = []
    for ref, rows in english_refs.items():
        passage_refs = {ref}
        for row in rows:
            passage_refs.update(row.get("source_main_passages", {}))
        source = sorted(
            (g for passage_ref in passage_refs for g in by_ref[passage_ref]),
            key=lambda g: g["entry"],
        )
        candidates = [
            [
                i
                for i, g in enumerate(source)
                if (
                    g["fr"] == e["fr"]
                    or len(e.get("source_main_passages", {})) > 1
                    and g["target_ref"] in e["source_main_passages"]
                )
                and boyd_partition_subset(g, e) is not None
            ]
            for e in rows
        ]

        def shape(
            row: BoydNote, tokenize: Callable[[str], list[str]]
        ) -> tuple[bool, bool, bool] | None:
            readings = row.get("tr", [])
            if len(readings) != 1 or row.get("rp") is None:
                return None
            old, new = tokenize(readings[0]["reading"]), tokenize(row["rp"])
            return (bool(old), bool(new), old != new and sorted(old) == sorted(new))

        for n, choices in enumerate(candidates):
            exact = [i for i in choices if source[i]["fr"] == rows[n]["fr"]]
            if exact:
                choices = candidates[n] = exact
            if len(choices) > 1:
                english_shape = shape(rows[n], words)
                compatible = [
                    i for i in choices if shape(source[i], greek_words) == english_shape
                ]
                if compatible:
                    candidates[n] = compatible
        pairs = ordered_pairs(candidates)
        for n, row in enumerate(rows):
            report: Report = {
                "witness": TCENT,
                "entry": row["entry"],
                "ref": structure.kjv_ref(ref),
                "target_ref": ref,
                "raw": row["raw"],
                **source_fields(row),
                "units": [],
                "scope": "verse",
            }
            readings = row.get("tr", [])
            old = readings[0]["reading"] if len(readings) == 1 else None
            new = row.get("rp")
            report["old"], report["new"] = plain(old), plain(new)
            if n not in pairs:
                report["reason"] = (
                    "no compatible Greek edition partition/reference"
                    if not candidates[n]
                    else "ambiguous or conflicting apparatus order"
                )
            else:
                g = source[pairs[n]]
                report["ref"] = structure.kjv_ref(g["target_ref"])
                report["target_ref"] = g["target_ref"]
                report["greek_entry"] = g["entry"]
                omitted = boyd_partition_subset(g, row)
                # A candidate is a partition subset, or it is not paired.
                assert omitted is not None
                report["pairing"] = (
                    "coarsened-partitions"
                    if any(s not in signature(g) for s in signature(row))
                    else (
                        "ordered-partition-subset"
                        if omitted
                        else "identical-partitions"
                    )
                )
                report["omitted_greek_variants"] = [
                    {"group": i + 1, **g["variants"][i]} for i in omitted
                ]
                found = attachments[g["entry"]]
                report["units"] = [
                    {"unit": u["id"], "scope": scope} for u, scope in found
                ]
                report["scope"] = "greek" if found else "verse"
                if not found:
                    report["reason"] = "paired Greek note has no reconciled unit"
            result.append(report)
    return attach_sole(sorted(result, key=lambda r: r["entry"]), units)


VARIANT = re.compile(r"\{([^:{}\[\]]*):([^{}\[\]]*)\}|\[([^:{}\[\]]*):([^{}\[\]]*)\]")


def faa_reading(text: str, witness: str) -> tuple[str, list[dict[str, Any]]]:
    """Resolve FAA labels separately in every group, retaining its offsets."""
    matches = list(VARIANT.finditer(text))
    batches: list[list[re.Match[str]]] = []
    at = 0
    while at < len(matches):
        batch = [matches[at]]
        at += 1
        while (
            at < len(matches)
            and matches[at][0].startswith("[")
            and not text[batch[-1].end() : matches[at].start()].strip()
        ):
            batch.append(matches[at])
            at += 1
        batches.append(batch)
    output: list[str] = []
    groups: list[dict[str, Any]] = []
    cursor = length = 0
    for batch in batches:
        prefix = text[cursor : batch[0].start()]
        output.append(prefix)
        length += len(prefix)
        variants: list[dict[str, Any]] = [
            {
                "sigla": (m[1] or m[3]).split(),
                "reading": (m[2] if m[1] is not None else m[4]).strip(),
            }
            for m in batch
        ]
        priority = ("RP2018", "RP-text", "RP") if witness == "RP" else ("S1894", "TR")
        selector = next(
            (p for p in priority if any(p in v["sigla"] for v in variants)), None
        )
        if selector is None:
            raise ValueError(f"FAA group has no {witness} reading: {batch[0][0]}")
        chosen = [v["reading"] for v in variants if selector in v["sigla"]]
        # FAA splits Luke 17:36's one reading into adjacent labelled chunks.
        value = " ".join(v for v in chosen if v not in {"-", "–", "—"})
        groups.append(
            {
                "variants": variants,
                "selector": selector,
                "reading": value,
                "range": [length, length + len(value)],
            }
        )
        output.append(value)
        length += len(value)
        cursor = batch[-1].end()
    output.append(text[cursor:])
    resolved = "".join(output)
    if re.search(r"[{}\[\]]", resolved):
        raise ValueError(f"Unparsed FAA markup: {resolved}")
    return resolved, groups


def faa_side(
    text: str, witness: str
) -> tuple[str | None, list[dict[str, Any]], str | None]:
    """One witness's reading of an FAA cell, its groups, and why it is
    unavailable if FAA gives that witness no reading."""
    try:
        resolved, groups = faa_reading(text, witness)
    except ValueError as error:
        if "group has no" not in str(error):
            raise
        return None, [], str(error)
    return resolved, groups, None


def faa(path: Content) -> dict[str, FaaRow]:
    names = "Matt|Mark|Luke|John|Acts|Rom|1 Cor|2 Cor|Gal|Eph|Phil|Col|1 Thes|2 Thes|1 Tim|2 Tim|Titus|Phmon|Heb|James|1 Pet|2 Pet|1 John|2 John|3 John|Jude|Rev".split(
        "|"
    )
    books = dict(zip(names, BOOKS, strict=True))
    result: dict[str, FaaRow] = {}
    for node in cast(
        list[html.HtmlElement], html.fromstring(path.read_bytes()).xpath("//tr")
    ):
        source_cells = cast(list[html.HtmlElement], node.xpath("./td"))
        cells = [" ".join("".join(td.itertext()).split()) for td in source_cells]
        if len(cells) != 4 or cells[0] == "VERSE":
            continue
        match = re.fullmatch(r"(.+) (\d+:\d+)", cells[0])
        if not match or match[1] not in books:
            raise ValueError(f"Unparsed FAA address: {cells[0]}")
        ref = books[match[1]] + " " + match[2]
        if ref in result:
            raise ValueError(f"Duplicate FAA address: {ref}")
        row: FaaRow = {
            "raw_Greek": cells[1],
            "raw_English": cells[2],
            "source_English_html": cast(
                str, html.tostring(source_cells[2], encoding="unicode")
            ),
            "source_notes": cells[3],
            "source_table_html": cast(str, html.tostring(node, encoding="unicode")),
            "source_table_text": "\n".join(cells),
        }
        resolved, groups, unavailable = faa_side(cells[1], "TR")
        if unavailable is not None:
            row["TR_Greek_unavailable"] = unavailable
        row["TR_Greek"], row["TR_Greek_groups"] = resolved, groups
        resolved, groups, unavailable = faa_side(cells[1], "RP")
        if unavailable is not None:
            row["RP_Greek_unavailable"] = unavailable
        row["RP_Greek"], row["RP_Greek_groups"] = resolved, groups
        resolved, groups, unavailable = faa_side(cells[2], "TR")
        if unavailable is not None:
            row["TR_English_unavailable"] = unavailable
        row["TR_English"], row["TR_English_groups"] = resolved, groups
        resolved, groups, unavailable = faa_side(cells[2], "RP")
        if unavailable is not None:
            row["RP_English_unavailable"] = unavailable
        row["RP_English"], row["RP_English_groups"] = resolved, groups
        result[ref] = row
    if len(result) != 7960:
        raise ValueError(
            f"FAA inventory: {len(result)}, expected 7960 (both doxology locations)"
        )
    return result


def contains(outer: Sequence[int], inner: Sequence[int]) -> bool:
    return (
        outer == inner
        if outer[0] == outer[1]
        else outer[0] <= inner[0] <= inner[1] <= outer[1]
    )


def overlaps(a: Sequence[int], b: Sequence[int]) -> bool:
    if a[0] == a[1]:
        return b[0] <= a[0] <= b[1]
    if b[0] == b[1]:
        return a[0] <= b[0] <= a[1]
    return max(a[0], b[0]) < min(a[1], b[1])


def faa_reports(
    rows: Mapping[str, FaaRow],
    tr: Mapping[str, list[str]],
    rp: Mapping[str, list[str]],
    units: Sequence[Unit],
    structure: Structure,
) -> list[Report]:
    """Attach paired contrasts where FAA's own Greek agrees with both streams.

    A group's words must match the placed Scrivener and RP2026 words where it
    stands; the rest of the verse need not (F2). Unmatched groups abstain.
    English contrasts without a pair remain verse-level alarms.
    No FAA silence disposition is inferred here.
    """
    by_ref: defaultdict[str, list[Unit]] = defaultdict(list)
    for unit in units:
        if unit.get("kind") != "relocation":
            by_ref[unit["ref"]].append(unit)
    result: list[Report] = []
    for ref, row in rows.items():
        if any(k.endswith("_unavailable") for k in row):
            result.append(
                {
                    "witness": FAA,
                    "entry": ref + "#unavailable",
                    "ref": ref,
                    "units": [],
                    "scope": "verse",
                    "reason": "FAA lacks an explicit Scrivener/RP selector; no silence claim",
                }
            )
            continue
        # Every reading is available here: none is None.
        tr_greek, rp_greek = row["TR_Greek"], row["RP_Greek"]
        assert tr_greek is not None and rp_greek is not None
        source_words = [greek_words(tr_greek), greek_words(rp_greek)]
        target_words = [tr.get(ref, []), rp.get(structure.rp_ref(ref), [])]
        maps = [equal_positions(a, b) for a, b in zip(source_words, target_words)]
        gg, eg = row["TR_Greek_groups"], row["TR_English_groups"]
        partition_candidates = [
            [i for i, g in enumerate(gg) if signature(g) == signature(e)] for e in eg
        ]
        ordered = ordered_pairs(partition_candidates)
        candidates: list[list[int]] = []
        for n, e in enumerate(eg):
            choices = partition_candidates[n]
            if len(choices) > 1:
                shape = (
                    bool(e["reading"]),
                    bool(row["RP_English_groups"][n]["reading"]),
                )
                compatible = [
                    i
                    for i in choices
                    if (
                        bool(greek_words(gg[i]["reading"])),
                        bool(greek_words(row["RP_Greek_groups"][i]["reading"])),
                    )
                    == shape
                ]
                # Shared English context can keep an omission or addition
                # nonempty on both sides ("looked, and behold" -> "saw").
                # Only an explicitly empty English side constrains that
                # side of the Greek; nonempty phrases cannot rule it out.
                if compatible and not all(shape):
                    choices = compatible
            candidates.append(choices)
        pairs = ordered_pairs(candidates)
        # One Greek contrast can be expressed by several English groups.
        pairs.update(
            {n: choices[0] for n, choices in enumerate(candidates) if len(choices) == 1}
        )
        # English can omit a word inside a nonempty Greek group. Its empty
        # contrast must not displace a pair fixed by the editions' order.
        pairs.update(ordered)

        for n, e in enumerate(eg):
            new = row["RP_English_groups"][n]["reading"]
            if e["reading"] == new:
                continue
            report: Report = {
                "witness": FAA,
                "entry": f"{ref}#{n + 1}",
                "ref": ref,
                "old": e["reading"],
                "new": new,
                "units": [],
                "scope": "verse",
            }
            if n not in pairs:
                report["reason"] = (
                    "English group has no unique ordered Greek edition partition"
                )
            else:
                i = pairs[n]
                ranges: list[list[int] | None] = []
                groups: list[set[int]] = []
                for side, (text, text_groups) in enumerate(
                    (
                        (tr_greek, row["TR_Greek_groups"]),
                        (rp_greek, row["RP_Greek_groups"]),
                    )
                ):
                    start, end = text_groups[i]["range"]
                    a, b = len(greek_words(text[:start])), len(greek_words(text[:end]))
                    mapping = maps[side]
                    matched = {mapping[p] for p in range(a, b) if p in mapping}
                    groups.append(matched)
                    if a < b:
                        ranges.append(
                            [min(matched), max(matched) + 1] if matched else None
                        )
                    else:
                        left = mapping.get(a - 1, -1 if a == 0 else None)
                        right = mapping.get(
                            a,
                            (
                                len(target_words[side])
                                if a == len(source_words[side])
                                else None
                            ),
                        )
                        ranges.append(
                            [right, right]
                            if left is not None
                            and right is not None
                            and right == left + 1
                            else None
                        )
                tr_range, rp_range = ranges
                if tr_range is None or rp_range is None:
                    report["reason"] = (
                        "FAA Greek streams do not both equal placed Scrivener/RP2026"
                    )
                    result.append(report)
                    continue
                report["greek_group"] = i + 1
                report["tr_range"], report["rp_range"] = tr_range, rp_range
                overlapping = []
                for u in by_ref[ref]:
                    # Both ranges must enclose the complete unit. A zero-width
                    # side must be at the same insertion/deletion boundary.
                    if (
                        contains(tr_range, u["tr_range"])
                        and contains(rp_range, u["rp_range"])
                        and set(range(*u["tr_range"])) <= groups[0]
                        and set(range(*u["rp_range"])) <= groups[1]
                        and (
                            u["tr_range"][0] != u["tr_range"][1]
                            or u["rp_range"][0] != u["rp_range"][1]
                        )
                    ):
                        report["units"].append({"unit": u["id"], "scope": "unit"})
                    touches = [
                        (
                            bool(group & set(range(*span)))
                            if outer[0] != outer[1] and span[0] != span[1]
                            else overlaps(outer, span)
                        )
                        for group, outer, span in zip(
                            groups, (tr_range, rp_range), (u["tr_range"], u["rp_range"])
                        )
                    ]
                    if all(touches):
                        overlapping.append(u)
                if not report["units"] and len(overlapping) == 1:
                    report["units"] = [
                        {"unit": overlapping[0]["id"], "scope": "constituent"}
                    ]
                report["scope"] = "greek" if report["units"] else "verse"
                if not report["units"]:
                    report["reason"] = (
                        "paired Greek group does not enclose a complete ledger unit"
                    )
            result.append(report)
        # FAA leaves this tense contrast outside its bracketed English groups,
        # but spells out both translations in the Greek explanatory note.
        # Read only this explicit form; weights supply no compatibility proof.
        explanation = re.search(
            rf"(?P<rp>[{GREEK}\s]+), "
            r"the dragon the \(one who\) (?P<new>had given) \(all dative\), "
            r"RP P1904 F1859=\d+/\d+ vs\. "
            rf"(?P<tr>[{GREEK}\s]+), "
            r"the dragon \(accusative\) who (?P<old>gave), TR F1859=\d+/\d+",
            row["source_notes"],
        )
        if explanation:
            located: list[list[int] | None] = []
            for side, witness in enumerate(("tr", "rp")):
                reading = greek_words(explanation[witness])
                starts = occurrences(target_words[side], reading)
                located.append(
                    [starts[0], starts[0] + len(reading)] if len(starts) == 1 else None
                )
            tr_span, rp_span = located
            placed = (
                [
                    u
                    for u in by_ref[ref]
                    if contains(u["tr_range"], tr_span)
                    and contains(u["rp_range"], rp_span)
                ]
                if tr_span is not None and rp_span is not None
                else []
            )
            if tr_span is not None and rp_span is not None and len(placed) == 1:
                result.append(
                    {
                        "witness": FAA,
                        "entry": ref + "#note1",
                        "ref": ref,
                        "old": explanation["old"],
                        "new": explanation["new"],
                        "source_notes": explanation[0].strip(),
                        "source_table_html": row["source_table_html"],
                        "greek_note": True,
                        "tr_range": tr_span,
                        "rp_range": rp_span,
                        "units": [{"unit": placed[0]["id"], "scope": "constituent"}],
                        "scope": "greek",
                    }
                )
    return attach_sole(result, units)


# MSB and WEB: selected lists placed by exact English contrast.


def report(
    witness: str,
    entry: int | str,
    target_ref: str,
    raw: str,
    structure: Structure,
    /,
    **fields: Unpack[SelectedListRow],
) -> SelectedListRow:
    return {
        "witness": witness,
        "entry": entry,
        "ref": structure.kjv_ref(target_ref),
        "target_ref": target_ref,
        "raw": raw,
        "units": [],
        "scope": "verse",
        **fields,
    }


def msb_contrast(source: str, english: str) -> tuple[str | None, str | None]:
    """Read one closed contrast with a generic or Scrivener TR label.

    Joint edition labels say the same thing as a lone TR label. MT-shared
    mentions, Stephanus-only readings, alternatives and explanations abstain.
    Separate fully labelled edition readings may include a third reading;
    each edition must occur only once, and exactly one clause must name TR.
    A parsed pair still needs both sides to match Greek-bound FAA evidence.
    """
    edition = r"(?:Scrivener TR|TR|CT|GOC|ALT|HF|NA|NA28|NA27|SBL|WH|NE|F35|TH|ECM|Tischendorf)"
    labels = edition + r"(?:(?:,\s*(?:and\s+)?|\s+and\s+)" + edition + r")*"
    if ";" in source:
        seen: set[str] = set()
        tr: list[str] = []
        for clause in source.split(";"):
            match = re.fullmatch(
                r"(" + labels + r")\s+<i>([^<]+)</i>\.?", clause.strip()
            )
            if not match:
                return None, None
            editions = re.findall(edition, match[1])
            if len(editions) != len(set(editions)) or seen.intersection(editions):
                return None, None
            seen.update(editions)
            if any(label in {"TR", "Scrivener TR"} for label in editions):
                tr.append(match[2])
        if len(tr) != 1:
            return None, None
        return tr[0], english
    match = re.fullmatch(
        r"("
        + labels
        + r")\s+(?:(includes?|(?:do|does) not include) )?<i>([^<]+)</i>\.?",
        source,
    )
    if not match or not re.search(r"\bTR\b", match[1]):
        return None, None
    if match[2]:
        return ("", match[3]) if match[2].startswith("do") else (match[3], "")
    return match[3], english


def msb_reading(old: str | None, token_reading: str | None, context: str) -> str | None:
    """Recover a closed phrase ending at the footnote's translated token.

    Transpositions have exactly the same words. Otherwise both unchanged
    edge words must delimit exactly one phrase without crossing a new clause
    boundary or cutting supplied-word brackets. No synonyms or approximate
    word counts establish a scope; retain the token reading when it is open.
    """
    if not old or not token_reading:
        return token_reading
    before, tokens = words(old), spans(context)
    after = [word for word, _, _ in tokens]
    if not after:
        return token_reading
    start = None
    reordered = len(after) >= len(before) and sorted(after[-len(before) :]) == sorted(
        before
    )
    if reordered:
        start = len(after) - len(before)
    elif len(before) > 2 and before[-1] == after[-1]:
        starts = [i for i, word in enumerate(after) if word == before[0]]
        if len(starts) == 1:
            start = starts[0]
    if start is None:
        return token_reading
    candidate = context[tokens[start][1] : tokens[-1][2]]
    # Shared edge words can occur in an earlier clause (1 Cor 15:49,
    # Rev 22:19); they do not establish that the whole intervening text
    # renders the footnote. Reorderings above retain their printed stops.
    if not reordered and any(
        candidate.count(stop) > old.count(stop) for stop in ".,;:!?"
    ):
        return token_reading
    stack: list[str] = []
    for char in candidate:
        if char in "[{":
            stack.append(char)
        elif char in "]}":
            if not stack or stack.pop() != {"]": "[", "}": "{"}[char]:
                return token_reading
    if stack:
        return token_reading
    return candidate


def msb_text(chunks: Iterable[str]) -> str:
    surface = cast(
        str, html.fromstring("<div>" + "".join(chunks) + "</div>").text_content()
    )
    return " ".join(re.sub(r"(?<!\w)-(?!\w)", "", surface).split())


def msb(main: Content, tables: Content, structure: Structure) -> list[SelectedListRow]:
    rows: list[SelectedListRow] = []
    current: str | None = None
    chunks: list[str] = []
    verse_text: dict[str, list[str]] = {}
    main_text: dict[str, str] = {}
    for record in main.read_text(encoding="cp1252").splitlines():
        address, tab, text = record.partition("\t")
        match = re.fullmatch(r"(.+) (\d+:\d+)", address)
        if tab and match and match[1] in BOOKS_BY_NAME:
            ref = BOOKS_BY_NAME[match[1]] + " " + match[2]
            if ref in main_text:
                raise ValueError(f"Duplicate MSB main passage: {ref}")
            main_text[ref] = text
    if len(main_text) != 7957:
        raise ValueError("MSB main text: expected 7,957 NT source verse markers")
    with tables.open_text(newline="") as stream:
        source = csv.reader(stream, delimiter="\t")
        next(source)
        for line, cells in enumerate(source, 2):
            if len(cells) != 23:
                raise ValueError(f"MSB line {line}: expected 23 columns")
            if cells[12]:
                match = re.fullmatch(r"(.+) (\d+:\d+)", cells[12])
                if not match or match[1] not in BOOKS_BY_NAME:
                    raise ValueError(f"MSB address: {cells[12]}")
                current = BOOKS_BY_NAME[match[1]] + " " + match[2]
                chunks = []
            chunks.append("".join(cells[16:21]))
            if current is not None:
                verse_text[current] = chunks
            if not re.search(r"\bTR\b", cells[21]):
                continue
            if current is None:
                raise ValueError(f"MSB note without verse at {line}")
            raw = " ".join(
                cast(
                    str, html.fromstring("<div>" + cells[21] + "</div>").text_content()
                ).split()
            )
            token_reading = cast(
                str, html.fromstring("<div>" + chunks[-1] + "</div>").text_content()
            ).strip()
            context = msb_text(chunks)
            old, new = msb_contrast(cells[21], token_reading)
            new = msb_reading(old, new, context)
            rows.append(
                report(
                    MSB,
                    line,
                    current,
                    raw,
                    structure,
                    old=old,
                    new=new,
                    source_original_html=cells[21],
                    english_context=context,
                    greek=cells[6],
                    greek_order=cells[5],
                    english=token_reading,
                    new_scope=(
                        "unavailable"
                        if old is None or new is None
                        else (
                            "explicit"
                            if old == "" or new == ""
                            else "phrase" if new != token_reading else "footnoted-token"
                        )
                    ),
                    reason="selected TR mention has no verified two-sided English contrast",
                )
            )
    return [
        {
            **row,
            "source_main_text": main_text.get(row["target_ref"]),
            "source_main_html": (
                escape(main_text[row["target_ref"]])
                if row["target_ref"] in main_text
                else None
            ),
            "source_table_transcription": msb_text(verse_text[row["target_ref"]]),
        }
        for row in rows
    ]


def web_contrast(raw: str) -> tuple[str | None, str | None]:
    """Read closed note forms, including joint TR/NU labels and omissions.

    Explanations and shared MT readings remain alarms. These words locate
    evidence only; they never supply KJV wording.
    """
    labels = r"(?:TR(?: and NU| & NU|, NU)?|NU(?: and TR| & TR|, TR))"
    contrast = re.fullmatch(
        labels + r" (?:reads?|have) “([^“”]+)” instead of “([^“”]+)”\.?", raw
    )
    if contrast:
        return contrast[1], contrast[2]
    listed = re.fullmatch(r"\+ MT: ([^;]+); TR and NU: ([^;]+)", raw)
    if listed:
        return listed[2], listed[1]
    omitted = re.fullmatch(
        r"Reading from " + labels + r"(?:;|\.) MT omits “([^“”]+)”\.?", raw
    )
    if omitted:
        return omitted[1], ""
    bracketed = re.fullmatch(r"NU \(in brackets\) and TR add “([^“”]+)”\.?", raw)
    if bracketed:
        return bracketed[1], ""
    change = re.fullmatch(labels + r" (add(?:s)?|omit(?:s)?) “(.+)”\.?", raw)
    if change:
        return (change[2], "") if change[1].startswith("add") else ("", change[2])
    return None, None


def web(folder: Content, structure: Structure) -> list[SelectedListRow]:
    rows: list[SelectedListRow] = []
    for path in folder.glob("*.usfm"):
        match = re.search(r"-([A-Z0-9]{3})", path.name)
        if not match or match[1] not in BOOKS:
            continue
        book = match[1]
        source = path.read_text(encoding="utf-8-sig")
        # Encoding metadata is outside the production parser's document model.
        source = re.sub(r"^\\ide UTF-8\s*$", "", source, flags=re.M)
        # Lexical annotations are metadata; retain their surface words.
        source = surface_words(source)
        # This reader needs words and notes, not paragraph depth or display styles.
        source = re.sub(r"\\q2\b", r"\\q1", source)
        source = re.sub(r"\\ili\b", r"\\ip", source)
        source = re.sub(r"\\(?:wj|bk|k)(\*?)", r"\\it\1", source)
        document = usj.parse(source)
        for address, verse in scripture.verses(document).items():
            for index, (_, note) in enumerate(verse.notes, 1):
                body = [
                    n
                    for n in note["content"]
                    if isinstance(n, dict) and n.get("marker") in {"ft", "fq", "fqa"}
                ]
                raw = " ".join(usj.text_of(body).split())
                if not re.search(r"\bTR\b", raw):
                    continue
                old, new = web_contrast(raw)
                rows.append(
                    report(
                        WEB,
                        f"{book} {address}#{index}",
                        f"{book} {address}",
                        raw,
                        structure,
                        old=old,
                        new=new,
                        source_main_text=scripture.plain(verse.text),
                        source_original_html=usj_markup(body),
                        source_main_html=verse_markup(document, verse),
                    )
                )
    return rows


def attach_contrasts(
    rows: Iterable[SelectedListRow | Report],
    faa_reports: Iterable[Report],
    boyd_reports: Iterable[Report] = (),
) -> list[Report]:
    """Require both complete English readings and a unique Greek-bound match.

    No phrase containment, synonyms, word-count similarity or verse-only
    co-occurrence. An empty reading is explicit; an unavailable one is None.
    Optional/supplied notation is retained and prevents an attachment.
    Rows are the readers' own; an attached row is refused, since attaching
    again starts from the source row and its reason.
    """
    by_ref: defaultdict[str, list[Report]] = defaultdict(list)
    for anchor in (*faa_reports, *boyd_reports):
        if anchor["units"] and anchor.get("method", "greek") in {"greek", "hand"}:
            by_ref[anchor["ref"]].append(anchor)
    result: list[Report] = []
    for row in rows:
        if row.get("method") == "english":
            raise ValueError(
                f"{row['witness']} {row['entry']} is already attached by English"
            )
        found = []
        old, new = row.get("old"), row.get("new")
        if (
            old is not None
            and new is not None
            and not re.search(r"[{}\[\]_]", old + new)
            and not any(c.isalpha() and not c.isascii() for c in old + new)
            and all(not text.strip() or words(text) for text in (old, new))
        ):
            for other in by_ref[row["ref"]]:
                a, b = other.get("old"), other.get("new")
                if (
                    a is not None
                    and b is not None
                    and not any(c.isalpha() and not c.isascii() for c in a + b)
                    and all(not text.strip() or words(text) for text in (a, b))
                    and words(old) == words(a)
                    and words(new) == words(b)
                    and words(old) != words(new)
                ):
                    found.append(other)
        item: Report = {**row}
        locations = {
            tuple(sorted((a["unit"], a["scope"]) for a in r["units"])) for r in found
        }
        witnesses = [r["witness"] for r in found]
        # Independent witnesses may confirm the same location. Repeated reports
        # within one witness or different Greek scopes remain ambiguous.
        if found and len(locations) == 1 and len(witnesses) == len(set(witnesses)):
            item["units"] = [{**u} for u in found[0]["units"]]
            item["scope"] = "greek"
            item["method"] = "english"
            item["via"] = {"witness": found[0]["witness"], "entry": found[0]["entry"]}
            item["contrast_evidence"] = [
                {"witness": r["witness"], "entry": r["entry"]} for r in found
            ]
            item.pop("reason", None)
        else:
            item["reason"] = (
                "ambiguous exact English contrasts"
                if found
                else row.get(
                    "reason", "no exact two-sided Greek-bound English contrast"
                )
            )
        result.append(item)
    return result
