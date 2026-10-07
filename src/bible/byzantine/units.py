"""The Greek unit ledger: every place Scrivener 1894 and RP2026 differ.

A token diff of the two texts, bounded by Robinson's collation entries and
checked against Boyd's TCGNT apparatus, gives one row per variation unit with
its class, the inventories that record it, and Hodges-Farstad's side. Whole
verse relocations and the accent-only differences the unaccented diff cannot
see are added as supplementary units. Unmatched inventory entries stay listed.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from copy import deepcopy
from difflib import SequenceMatcher

from bible.byzantine.greek import (
    PATCHES,
    Diacritic,
    PrintedVerse,
    Structure,
    ascii_greek,
    occurrences,
)
from bible.byzantine.inventories import reading_words
from bible.byzantine.rows import (
    BoydNote,
    CollationRow,
    Token,
    Unit,
    UnitInventory,
    Unmatched,
)

# The Greek texts' words, and their parsed tokens, by "BOOK c:v" (the RP
# text's tokens by its address, the TR's by "TR BOOK c:v").
Words = Mapping[str, list[str]]
Tagged = Mapping[str, list[Token]]
# A difference of two token streams: its opcode and its two ranges.
Opcode = tuple[str, int, int, int, int]

# Words the English transliterates (Matthew 27:46, Mark 15:34): a change of
# spelling shows, whatever the tags say.
TRANSLITERATED = {"lama", "lima"}

# Classes the English cannot show unless a witness says so: orthography only.
NEUTRAL_CLASSES = frozenset({"movable", "word-division", "spelling", "name-spelling"})

ARTICLES = set("o h to tou ths tw th ton thn oi ai ta twn tois tais tous tas".split())
PARTICLES = set("kai de gar oun te men an".split())
# Unambiguous first/second-person forms, not a lexicon-based synonym rule.
# Third-person forms and longer constructions retain their existing classes.
PERSONAL = set(
    "egw eme me emou mou emoi moi hmeis hmas hmwn hmin su se sou soi umeis umas umwn umin".split()
)
MOVABLE = {
    frozenset(p)
    for p in [
        ("esti", "estin"),
        ("outw", "outws"),
        ("dusi", "dusin"),
        ("eide", "eiden"),
        ("axri", "axris"),
        ("mexri", "mexris"),
        ("eikosi", "eikosin"),
    ]
}


def normal(words: list[str], forms: Mapping[str, str]) -> list[str]:
    return [forms.get(word, word) for word in words]


def quotation_forms(tags: Tagged) -> dict[str, str]:
    """Terminal nu in apparatus quotations, licensed by pinned RP parsing.

    These aliases locate quotations, and a difference in that nu alone is a
    movable unit. They do not authorize silence: each is still a unit. A noun's
    final nu is retained, except in the dative plural.
    """
    forms = {word: min(pair) for pair in MOVABLE for word in pair}
    for tokens in tags.values():
        for token in tokens:
            word = token["word"]
            base = word.removesuffix("n")
            if any(
                (
                    parse.startswith("V-")
                    and (
                        parse.removesuffix("-ATT").endswith("-3S")
                        and base.endswith("e")
                        or parse.removesuffix("-ATT").endswith("-3P")
                        and base.endswith("si")
                    )
                )
                or "-DP" in parse
                and base.endswith("si")
                for parse in token["parse"]
            ):
                forms[base] = forms[base + "n"] = base
    return forms


def patched(old: list[str], new: list[str]) -> tuple[list[str], list[str]]:
    """An Appendix A pair without the words its two readings share."""
    i = 0
    while i < min(len(old), len(new)) and old[i] == new[i]:
        i += 1
    j = 0
    while j < min(len(old), len(new)) - i and old[-j - 1] == new[-j - 1]:
        j += 1
    return old[i : len(old) - j], new[i : len(new) - j]


def record_side(unit: Unit, note: BoydNote | Unmatched) -> None:
    """Boyd excludes spelling: agreeing partial notes establish HF's side."""
    sides = {a["hf"] for a in unit["inventories"] if "hf" in a}
    unit["hf"] = "other" if len(sides) > 1 else next(iter(sides))
    unit["rp_alternate"] |= note["rp_alternate"]
    unit["patriarchal"] |= note["patriarchal"]


def classify(a: list[str], b: list[str]) -> str:
    """Only classify what the forms establish; no inferred spelling/parse."""
    if len(a) == len(b) == 1 and frozenset(a + b) in MOVABLE:
        return "movable"
    if a and b and "".join(a) == "".join(b):
        return "word-division"
    if a + b and set(a + b) <= ARTICLES:
        return "article"
    if a + b and set(a + b) <= PARTICLES:
        return "particle"
    if len(a) <= 1 and len(b) <= 1 and a + b and set(a + b) <= PERSONAL:
        return "pronoun"
    if a and b and Counter(a) == Counter(b):
        return "order"
    if not b:
        return "omission"
    if not a:
        return "addition"
    return "substitution"


PREPOSITIONS = "uper upo peri para pros pro kata meta dia apo anti epi sun sum sul sug sus ana eis ek ec en ap ep kat met par di".split()


def prefixes(word: str) -> tuple[list[str], str]:
    """The prepositions a verb is compounded with, from the front, in their
    unelided forms (ap- is apo-, sum- is sun-), and the stem that remains."""
    canonical = {
        "ap": "apo",
        "ep": "epi",
        "kat": "kata",
        "met": "meta",
        "par": "para",
        "di": "dia",
        "sum": "sun",
        "sul": "sun",
        "sug": "sun",
        "sus": "sun",
        "ec": "ek",
    }
    found: list[str] = []
    while True:
        for p in PREPOSITIONS:
            if word.startswith(p) and len(word) - len(p) >= 4:
                found.append(canonical.get(p, p))
                word = word[len(p) :]
                break
        else:
            return found, word


def annotated_class(unit: Unit, tr: Words, rp: Words, tags: Tagged) -> Unit:
    """Refine single-word classes only from exact-address, unambiguous tags.

    Strong's numbers identify the lemma here, not an English rendering.
    Multiple parses or lexical numbers abstain. UTR's additional conjugation
    numbers (PARSNUM.TXT, 5627–5773) are not lexical numbers. Keep the evidence so a
    later neutral disposition can be reviewed independently of this function.
    """
    # Unaccented eta names both the feminine article and disjunctive ἤ.
    # Only exact-address lexical and grammatical tags distinguish them.
    if unit["class"] == "article" and unit["tr"] + unit["rp"] == ["h"]:
        ref, target = unit["ref"], unit["target_ref"]
        left, right = tags.get("TR " + ref, []), tags.get(target, [])
        if [t["word"] for t in left] != tr[ref] or [t["word"] for t in right] != rp[
            target
        ]:
            return unit
        left_eta = left[slice(*unit["tr_range"])]
        right_eta = right[slice(*unit["rp_range"])]
        if all(
            t.get("strong") == [2228] and t.get("parse") == ["PRT"]
            for t in left_eta + right_eta
        ):
            return {
                **unit,
                "class": "particle",
                "classification_evidence": {
                    "tr": deepcopy(left_eta[0]) if left_eta else None,
                    "rp": deepcopy(right_eta[0]) if right_eta else None,
                    "basis": "exact-address Strong's and parsing",
                },
            }
        return unit
    if unit["class"] != "substitution":
        return unit
    if len(unit["tr"]) != 1 or len(unit["rp"]) != 1:
        return unit
    if set(unit["tr"] + unit["rp"]) & TRANSLITERATED:
        return unit
    ref, target = unit["ref"], unit["target_ref"]
    left, right = tags.get("TR " + ref, []), tags.get(target, [])
    if [t["word"] for t in left] != tr[ref] or [t["word"] for t in right] != rp[target]:
        return unit
    a, b = left[unit["tr_range"][0]], right[unit["rp_range"][0]]
    if any(
        n <= 0 or 5624 < n < 5627 or n > 5773
        for t in (a, b)
        for n in t.get("strong", [])
    ):
        return unit
    numbers = [{n for n in t.get("strong", []) if n <= 5624} for t in (a, b)]
    # PARSING.COD defines -ATT as an Attic form, not a changed inflection.
    parses = [{p.removesuffix("-ATT") for p in t["parse"]} for t in (a, b)]
    if any(len(s) != 1 for s in numbers + parses) or numbers[0] != numbers[1]:
        return unit
    pa, pb = [next(iter(s)) for s in parses]
    # Even shared lexical tags cannot neutralize a changed verbal prefix.
    wa, wb = a["word"], b["word"]
    if (
        pa.startswith("V-")
        and pb.startswith("V-")
        and (wa.endswith(wb) or wb.endswith(wa))
    ):
        return unit
    # A compound verb with other prepositions is another verb, whatever its
    # Strong's number (ACT 21:15 aposkeuasamenoi / episkeuasamenoi).
    # Both must be compounds on one stem; an augment is not a preposition.
    (ka, sa), (kb, sb) = prefixes(wa), prefixes(wb)
    if (
        pa.startswith("V-")
        and pb.startswith("V-")
        and ka
        and kb
        and ka != kb
        and sa == sb
    ):
        return {**unit, "class": "prefix"}
    category = (
        "name-spelling"
        if pa == pb == "N-PRI"
        else "spelling" if pa == pb else "inflection"
    )
    return {
        **unit,
        "class": category,
        "classification_evidence": {
            "tr": deepcopy(a),
            "rp": deepcopy(b),
            "basis": "exact-address Strong's and parsing",
        },
    }


def difference_ranges(
    a: list[str], b: list[str], forms: Mapping[str, str] | None = None
) -> Iterator[Opcode]:
    """Normalize the closed movable list before diffing; record every change.

    Equal normalized words still produce their own unit if their source forms
    differ. Offsets always refer to the original token streams.
    """
    if a == b:
        return
    forms = forms or quotation_forms({})
    for op, i, j, k, l in SequenceMatcher(
        None, normal(a, forms), normal(b, forms), autojunk=False
    ).get_opcodes():
        if op != "equal":
            yield op, i, j, k, l
        else:
            for x, z in zip(range(i, j), range(k, l), strict=True):
                if a[x] != b[z]:
                    yield "replace", x, x + 1, z, z + 1


def collation_ranges(
    a: list[str], b: list[str], entries: Iterable[CollationRow]
) -> list[tuple[int, int, int, int]]:
    """Let unique, exact collation quotations set the diff's boundaries.

    A free token diff can attach a repeated conjunction to the wrong side of
    a deletion, or swallow the next substitution in a transposition. Locate
    both published readings first and diff the gaps separately. Ambiguous,
    empty-sided and overlapping quotations remain for ordinary reconciliation.
    """
    ranges: list[tuple[int, int, int, int]] = []
    for entry in entries:
        qa, qb = entry["tr"], entry["rp"]
        ia, ib = occurrences(a, qa), occurrences(b, qb)
        if len(ia) != 1 or len(ib) != 1:
            continue
        i, k = ia[0], ib[0]
        j, l = i + len(qa), k + len(qb)
        while i < j and k < l and a[i] == b[k]:
            i, k = i + 1, k + 1
        while i < j and k < l and a[j - 1] == b[l - 1]:
            j, l = j - 1, l - 1
        if i != j or k != l:
            ranges.append((i, j, k, l))
    # Two entries can locate the same change; it is still one range.
    ranges = sorted(set(ranges))
    # Refuse overlapping or crossed ranges; no ordering score resolves them.
    return [
        r
        for r in ranges
        if all(
            r == other
            or r[1] <= other[0]
            and r[3] <= other[2]
            or other[1] <= r[0]
            and other[3] <= r[2]
            for other in ranges
        )
    ]


def blocks(
    tr: Words,
    rp: Words,
    structure: Structure,
    collation: Sequence[CollationRow] = (),
    tags: Tagged | None = None,
) -> list[Unit]:
    rows: list[Unit] = []
    bytarget: defaultdict[str, list[CollationRow]] = defaultdict(list)
    for entry in collation:
        bytarget[entry["target_ref"]].append(entry)
    for ref, words in tr.items():
        target = structure.rp_ref(ref)
        other = rp[target]
        anchors = collation_ranges(words, other, bytarget[target])
        # RP2018's inventories cannot bound a reading Appendix A introduced;
        # the printed pair does.
        if ref in PATCHES and not anchors and occurrences(other, PATCHES[ref][1]):
            old, new = PATCHES[ref]
            anchors = collation_ranges(words, other, [{"tr": old, "rp": new}])
        if words == other and not anchors:
            continue
        # Use annotations only at their checked address, never a homograph's
        # parsing borrowed from another verse. Patched RP verses may abstain.
        checked = {
            key: tokens
            for key, tokens, text in (
                (ref, (tags or {}).get("TR " + ref, []), words),
                (target, (tags or {}).get(target, []), other),
            )
            if [t["word"] for t in tokens] == text
        }
        forms = quotation_forms(checked)
        changed: list[Opcode] = []
        at, other_at = 0, 0
        for i, j, k, l in [*anchors, (len(words), len(words), len(other), len(other))]:
            changed.extend(
                (op, at + x, at + y, other_at + z, other_at + w)
                for op, x, y, z, w in difference_ranges(
                    words[at:i], other[other_at:k], forms
                )
            )
            if i != j or k != l:
                changed.append(("replace", i, j, k, l))
            at, other_at = j, l
        for _, i, j, k, l in changed:
            a, b = words[i:j], other[k:l]
            rows.append(
                {
                    "ref": ref,
                    "target_ref": target,
                    "tr": a,
                    "rp": b,
                    "tr_range": [i, j],
                    "rp_range": [k, l],
                    "class": (
                        "structural"
                        if ref in structure.omitted
                        else (
                            "movable"
                            if len(a) == len(b) == 1
                            and a != b
                            and forms.get(a[0], a[0]) == forms.get(b[0], b[0])
                            else classify(a, b)
                        )
                    ),
                    "found_in": ["diff"],
                    "inventories": [],
                    "hf": "unknown",
                    "rp_alternate": False,
                    "patriarchal": False,
                }
            )
    return rows


def matching_blocks(
    a: list[str],
    b: list[str],
    quoted_a: list[str],
    quoted_b: list[str],
    units: Sequence[Unit],
    rp_start: int | None = None,
    forms: Mapping[str, str] | None = None,
    constituents: bool = True,
    tr_start: int | None = None,
) -> list[int]:
    """Locate a complete region or a constituent of one collation unit.

    Context on both sides must locate the same region. When one side is
    empty, the other uniquely identifies the entire deletion or insertion.
    Repeated quotations need a verified main-text position or abstain.
    """
    if forms:
        a, b, quoted_a, quoted_b = [
            normal(side, forms) for side in (a, b, quoted_a, quoted_b)
        ]
    matches: list[list[int]] = []
    unique_a = len(occurrences(a, quoted_a)) == 1
    for i in occurrences(a, quoted_a) if quoted_a else [None]:
        if tr_start is not None and i is not None and i != tr_start:
            continue
        for k in occurrences(b, quoted_b) if quoted_b else [None]:
            if rp_start is not None and k is not None and k != rp_start:
                continue
            # Boyd can describe one constituent of a larger collation unit.
            # Both exact readings must be inside that same bounded unit.
            if quoted_a != quoted_b:
                for n, unit in enumerate(units):
                    x, y = unit["tr_range"]
                    z, w = unit["rp_range"]
                    # Repeated context can put a literal published deletion
                    # on a different token boundary from the collation's.
                    # Accept only when both splices yield exactly the same
                    # local text, with equal untouched words on both sides.
                    # This locates evidence; it does not move the unit.
                    if (
                        constituents
                        and i is not None
                        and k is not None
                        and quoted_a != quoted_b
                        and unique_a
                    ):
                        start, end = min(i, x), max(i + len(quoted_a), y)
                        other_start = k - (i - start)
                        other_end = k + len(quoted_b) + end - i - len(quoted_a)
                        if (
                            0 <= other_start <= z <= w <= other_end <= len(b)
                            and a[start:x] == b[other_start:z]
                            and a[y:end] == b[w:other_end]
                            and a[start:i] + quoted_b + a[i + len(quoted_a) : end]
                            == b[other_start:other_end]
                        ):
                            matches.append([n])
                    inside_a = i is not None and x <= i < i + len(quoted_a) <= y
                    inside_b = k is not None and z <= k < k + len(quoted_b) <= w
                    if inside_a and inside_b:
                        matches.append([n])
                    if (
                        constituents
                        and not quoted_a
                        and k is not None
                        and rp_start is not None
                        and x == y
                        and w - z == len(quoted_b)
                    ):
                        # A repeated retained word lets the diff put an
                        # insertion after it while the note puts it before.
                        # Locate only the published position, and prove that
                        # the local insertions have exactly the same result.
                        start, end = min(k, z), max(k + len(quoted_b), w)
                        left_start = x - (z - start)
                        left_end = x + end - w
                        inserted_at = left_start + k - start
                        if (
                            0 <= left_start <= inserted_at <= left_end <= len(a)
                            and a[left_start:inserted_at]
                            + quoted_b
                            + a[inserted_at:left_end]
                            == b[start:end]
                        ):
                            matches.append([n])
                    # A positioned Boyd addition may be one constituent of a
                    # replacement. Its location is evidence, not a claim that
                    # the whole published unit is an insertion. Require the
                    # quoted words to be absent from the TR side of this unit;
                    # otherwise an unchanged word could masquerade as added.
                    if (
                        not quoted_a
                        and inside_b
                        and rp_start is not None
                        and constituents
                        and not occurrences(a[x:y], quoted_b)
                    ):
                        matches.append([n])
                    if (
                        not quoted_b
                        and inside_a
                        and rp_start is not None
                        and z <= rp_start <= w
                        and constituents
                        and (
                            not occurrences(b[z:w], quoted_a)
                            or tr_start is not None
                            and i is not None
                            and i + len(quoted_a) == y
                            and rp_start == w
                        )
                    ):
                        # A complete, unique contextual quotation may name
                        # the final deleted conjunction of an order unit,
                        # even when another conjunction remains inside it.
                        matches.append([n])
            covered: list[int] = []
            for n, u in enumerate(units):
                x, y = u["tr_range"]
                z, w = u["rp_range"]
                if i is not None and not (i <= x <= y <= i + len(quoted_a)):
                    continue
                if k is not None and not (k <= z <= w <= k + len(quoted_b)):
                    continue
                if i is None and x != y or k is None and z != w:
                    continue
                if k is None and rp_start is not None and z != rp_start:
                    continue
                covered.append(n)
            if not covered:
                continue
            # Use the located boundaries, not common prefix/suffix letters:
            # a transposition may start or end with a retained equal word.
            first, last = units[covered[0]], units[covered[-1]]
            x, y = first["tr_range"][0], last["tr_range"][1]
            z, w = first["rp_range"][0], last["rp_range"][1]
            left_a = a[i:x] if i is not None else []
            left_b = b[k:z] if k is not None else []
            right_a = a[y : i + len(quoted_a)] if i is not None else []
            right_b = b[w : k + len(quoted_b)] if k is not None else []
            if left_a == left_b and right_a == right_b:
                matches.append(covered)
    if not matches and constituents:
        # Strip literal shared context only after locating the full quotations
        # on both streams. Retain their original offsets when stripping
        # context, so a repeated trimmed word cannot migrate to another unit.
        if (
            quoted_a
            and quoted_b
            and quoted_a != quoted_b
            and occurrences(a, quoted_a)
            and occurrences(b, quoted_b)
        ):
            old, new = list(quoted_a), list(quoted_b)
            prefix = 0
            while old and new and old[0] == new[0]:
                old.pop(0)
                new.pop(0)
                prefix += 1
            while old and new and old[-1] == new[-1]:
                old.pop()
                new.pop()
            left_starts = occurrences(a, quoted_a)
            right_starts = occurrences(b, quoted_b)
            anchored = (
                len(left_starts) == 1
                and (
                    len(right_starts) == 1
                    if rp_start is None
                    else rp_start in right_starts
                )
                and (tr_start is None or tr_start == left_starts[0])
            )
            if anchored and (old, new) != (quoted_a, quoted_b):
                found = matching_blocks(
                    a,
                    b,
                    old,
                    new,
                    units,
                    (right_starts[0] if rp_start is None else rp_start) + prefix,
                    constituents=True,
                    tr_start=left_starts[0] + prefix,
                )
                if found:
                    matches.append(found)
        # A Boyd note can quote a sub-edit plus context outside the collation
        # boundary. Split only for locating it; keep the published unit intact.
        atoms: list[Unit] = []
        parents: list[int] = []
        for n, unit in enumerate(units):
            x, y = unit["tr_range"]
            z, w = unit["rp_range"]
            for _, i, j, k, l in difference_ranges(a[x:y], b[z:w]):
                atoms.append({"tr_range": [x + i, x + j], "rp_range": [z + k, z + l]})
                parents.append(n)
        found = matching_blocks(
            a,
            b,
            quoted_a,
            quoted_b,
            atoms,
            rp_start,
            constituents=False,
            tr_start=tr_start,
        )
        if found:
            matches.append(sorted({parents[n] for n in found}))
    unique = {tuple(match) for match in matches}
    return list(next(iter(unique))) if len(unique) == 1 else []


def word_break_match(
    a: list[str],
    b: list[str],
    qa: list[str],
    qb: list[str],
    units: Sequence[Unit],
    entry: BoydNote,
    splits: Mapping[str, list[str]],
    forms: Mapping[str, str],
) -> tuple[list[int], set[int]]:
    """Locate a quotation through Appendix C; retain original unit ranges.

    Expanded token boundaries exist only inside this locator. A quotation
    covering part of a divided word remains constituent evidence.
    """

    def expanded(words: list[str]) -> tuple[list[str], list[int]]:
        out: list[str] = []
        boundaries = [0]
        for word in words:
            out.extend(splits.get(word, [word]))
            boundaries.append(len(out))
        return out, boundaries

    left, la = expanded(a)
    right, rb = expanded(b)
    old, _ = expanded(qa)
    new, _ = expanded(qb)
    located: list[Unit] = [
        {
            **u,
            "tr_range": [la[x] for x in u["tr_range"]],
            "rp_range": [rb[x] for x in u["rp_range"]],
        }
        for u in units
    ]
    position = entry.get("position")
    start = None
    if position and position["ref"] == entry["target_ref"]:
        source, boundaries = expanded(position["words"])
        if normal(source, forms) == normal(right, forms):
            start = boundaries[position["offset"]]
    found = matching_blocks(left, right, old, new, located, start, forms)
    whole: set[int] = set()
    left, right, old, new = [normal(s, forms) for s in (left, right, old, new)]
    for n in found:
        i, j = located[n]["tr_range"]
        k, l = located[n]["rp_range"]
        if (
            i == j
            and not old
            or any(x <= i <= j <= x + len(old) for x in occurrences(left, old))
        ) and (
            k == l
            and not new
            or any(x <= k <= l <= x + len(new) for x in occurrences(right, new))
        ):
            whole.add(n)
    return found, whole


def expanded_readings(
    reading: str, stream: list[str], forms: Mapping[str, str]
) -> list[list[str]]:
    """Expand printed ellipses only at literal, ordered fragment boundaries.

    This returns every possible span; reconciliation must still find exactly
    one. No ellipsis can license a changed word it did not quote: the paired
    expansions below must have identical interiors.
    """
    read = [reading_words(part) for part in reading.split("…")]
    parts = [part for part in read if part]
    if len(parts) != len(read):
        return []
    normalized = normal(stream, forms)
    spans = [
        (i, i + len(parts[0])) for i in occurrences(normalized, normal(parts[0], forms))
    ]
    for part in parts[1:]:
        starts = occurrences(normalized, normal(part, forms))
        spans = [(i, k + len(part)) for i, j in spans for k in starts if k > j]
    return [stream[i:j] for i, j in spans]


def ellipsis_pairs(
    left: str, right: str, a: list[str], b: list[str], forms: Mapping[str, str]
) -> list[tuple[list[str], list[str]]]:
    """Require every difference in an expansion to be in a printed fragment."""
    if "…" not in left + right or left.count("…") != right.count("…"):
        return []
    pairs: list[tuple[list[str], list[str]]] = []
    for qa in expanded_readings(left, a, forms):
        for qb in expanded_readings(right, b, forms):
            # Verify the omitted interiors separately rather than accepting
            # any text between two matching endpoints.
            def interiors(reading: str, words: list[str]) -> list[list[list[str]]]:
                # Every fragment was read when the reading was expanded.
                parts = [reading_words(p) or [] for p in reading.split("…")]
                norm = normal(words, forms)
                paths: list[tuple[int, list[list[str]]]] = [(len(parts[0]), [])]
                for part in parts[1:]:
                    starts = occurrences(norm, normal(part, forms))
                    paths = [
                        (k + len(part), gaps + [norm[j:k]])
                        for j, gaps in paths
                        for k in starts
                        if k > j
                    ]
                return [gaps for end, gaps in paths if end == len(words)]

            ga, gb = interiors(left, qa), interiors(right, qb)
            if len(ga) == len(gb) == 1 and ga == gb:
                pairs.append((qa, qb))
    return pairs


def cross_verse_attachments(
    units: list[Unit],
    unmatched: Iterable[Unmatched],
    tr: Words,
    rp: Words,
    forms: Mapping[str, str],
    structure: Structure,
) -> tuple[list[Unit], list[Unmatched]]:
    """Locate quoted passages across explicitly numbered verse boundaries.

    Verse numerals must name existing verses of the same chapter. The words
    still have to bind uniquely on both streams; proximity is not evidence.
    A chapter whose verses exchange places numbers them otherwise in each
    text, so its numerals locate nothing.
    """
    exchanging = {ref.rsplit(":", 1)[0] for ref in structure.exchanged}
    result = deepcopy(units)
    remaining: list[Unmatched] = []
    for row in unmatched:
        if row["inventory"] != "tcgnt" or len(row["tr"]) != 1:
            remaining.append(row)
            continue
        # A TCGNT row quotes its readings as text.
        reading, right = row["tr"][0], row["rp"]
        if isinstance(reading, str) or not isinstance(right, str):
            remaining.append(row)
            continue
        book, address = row["target_ref"].split()
        chapter, verse = map(int, address.split(":"))
        if f"{book} {chapter}" in exchanging or "{" in right:
            remaining.append(row)
            continue
        left = reading["reading"]
        declared = [verse]
        declared += [
            int(v) for v in re.findall(r"(?<!\S)\d+(?!\S)", left + " " + right)
        ]
        end = re.fullmatch(r"\d+:\d+–(\d+)", row.get("fr", address))
        if end:
            declared.append(int(end[1]))
        if len(set(declared)) == 1:
            remaining.append(row)
            continue
        refs = [
            f"{book} {chapter}:{v}" for v in range(min(declared), max(declared) + 1)
        ]
        if any(ref not in tr or ref not in rp for ref in refs):
            remaining.append(row)
            continue
        # Embedded numerals delimit verses. Preserve their locations in the
        # inventory; they do not become Greek words in either quoted reading.
        qa = reading_words(re.sub(r"(?<!\S)\d+(?!\S)", "", left))
        qb = reading_words(re.sub(r"(?<!\S)\d+(?!\S)", "", right))
        if qa is None or qb is None:
            remaining.append(row)
            continue
        a: list[str] = []
        b: list[str] = []
        located: list[Unit] = []
        parents: list[int] = []
        for ref in refs:
            for index, unit in enumerate(result):
                if unit["ref"] != ref:
                    continue
                i, j = unit["tr_range"]
                k, l = unit["rp_range"]
                located.append(
                    {
                        **unit,
                        "tr_range": [len(a) + i, len(a) + j],
                        "rp_range": [len(b) + k, len(b) + l],
                    }
                )
                parents.append(index)
            a.extend(tr[ref])
            b.extend(rp[ref])

        def numbered_boundaries(reading: str, words: list[str], texts: Words) -> bool:
            # Each printed numeral must fall exactly on its verse boundary,
            # not merely somewhere in a widened search window.
            segments = re.split(r"(?<!\S)(\d+)(?!\S)", reading)
            if len(segments) == 1:
                return True
            # The reading without its numerals was read above (qa, qb).
            clean = reading_words(re.sub(r"(?<!\S)\d+(?!\S)", "", reading)) or []
            norm = normal(words, forms)
            starts = occurrences(norm, normal(clean, forms))
            valid: list[int] = []
            for start in starts:
                consumed, okay = 0, True
                for index, segment in enumerate(segments):
                    if index % 2 == 0:
                        consumed += len(reading_words(segment) or [])
                    else:
                        boundary = sum(
                            len(texts[ref])
                            for ref in refs
                            if int(ref.split(":")[1]) < int(segment)
                        )
                        okay &= start + consumed == boundary
                if okay:
                    valid.append(start)
            return len(valid) == 1

        if not numbered_boundaries(left, a, tr) or not numbered_boundaries(
            right, b, rp
        ):
            remaining.append(row)
            continue
        match = matching_blocks(a, b, qa, qb, located, forms=forms)
        if not match:
            remaining.append(row)
            continue
        # Keep the unit/constituent distinction when a cross-verse quotation
        # covers just part of a collation unit.
        na, nb, nqa, nqb = [normal(s, forms) for s in (a, b, qa, qb)]
        for index in match:
            unit, positioned = result[parents[index]], located[index]
            i, j = positioned["tr_range"]
            k, l = positioned["rp_range"]
            whole = any(
                x <= i <= j <= x + len(qa) for x in occurrences(na, nqa)
            ) and any(x <= k <= l <= x + len(qb) for x in occurrences(nb, nqb))
            unit["inventories"].append(
                {
                    "inventory": "tcgnt",
                    "entry": row["entry"],
                    "scope": "unit" if whole else "constituent",
                    "hf": row["hf"],
                    "quotation_span": refs,
                }
            )
            if "tcgnt" not in unit["found_in"]:
                unit["found_in"].append("tcgnt")
                unit["found_in"].sort()
            record_side(unit, row)
    return result, remaining


def keyed_units(units: Iterable[Unit], ref: str, tr: str, rp: str) -> list[Unit]:
    """The units a decision's Greek key names: a verse and both readings."""
    return [
        u
        for u in units
        if u["ref"] == ref and " ".join(u["tr"]) == tr and " ".join(u["rp"]) == rp
    ]


def reconcile(
    tr: Words,
    rp: Words,
    collation: Sequence[CollationRow],
    boyd: Sequence[BoydNote],
    tags: Tagged | None = None,
    splits: Mapping[str, list[str]] | None = None,
    structure: Structure | None = None,
) -> tuple[list[Unit], list[Unmatched]]:
    """The units, with their inventory attachments, and the unmatched entries."""
    assert structure is not None
    forms = quotation_forms(tags or {})
    rows = blocks(tr, rp, structure, collation, tags)
    byref: defaultdict[str, list[Unit]] = defaultdict(list)
    for row in rows:
        byref[row["ref"]].append(row)
    unmatched: list[Unmatched] = []

    def place(
        witness: str,
        target: str,
        number: int,
        qa: list[str] | None,
        qb: list[str] | None,
        note: BoydNote | None,
    ) -> str | None:
        """Attach an inventory's entry (a collation row, or a TCGNT note with
        its one Scrivener reading) to the units it locates; or the reason it
        is unmatched."""
        break_scope: set[int] | None = None
        rp_start: int | None = None
        ref = structure.kjv_ref(target)
        units = byref[ref]
        if qa is None or qb is None:
            match: list[int] = []
            if note is not None:
                candidates: list[tuple[list[int], list[str], list[str]]] = []
                for expanded_a, expanded_b in ellipsis_pairs(
                    note["tr"][0]["reading"],
                    note["rp"],
                    tr.get(ref, []),
                    rp.get(target, []),
                    forms,
                ):
                    found = matching_blocks(
                        tr[ref],
                        rp[target],
                        expanded_a,
                        expanded_b,
                        units,
                        forms=forms,
                    )
                    if found:
                        candidates.append((found, expanded_a, expanded_b))
                if len(candidates) == 1:
                    match, qa, qb = candidates[0]
                    rp_start = None
        else:
            rp_start = None
            position = note.get("position") if note is not None else None
            if position and position["ref"] == target:
                source, actual = position["words"], rp.get(target, [])
                offset = position["offset"]
                # Boyd's main text is RP2018. Apply only Appendix A's
                # named pair to locate a note against RP2026, requiring
                # exact whole-verse agreement afterwards. A note inside
                # the changed pair has no transferable position.
                if target in PATCHES:
                    old, new = PATCHES[target]
                    normalized_source = normal(source, forms)
                    starts = occurrences(normalized_source, normal(old, forms))
                    if len(starts) == 1:
                        start = starts[0]
                        if offset <= start or offset >= start + len(old):
                            source = source[:start] + new + source[start + len(old) :]
                            if offset >= start + len(old):
                                offset += len(new) - len(old)
                # Token-for-token agreement establishes the address. Boyd
                # regularizes terminal nu; allowing that letter difference
                # here locates a note, never classifies a unit as neutral.
                if len(source) == len(actual) and all(
                    forms.get(x, x) == forms.get(y, y)
                    for x, y in zip(source, actual, strict=True)
                ):
                    rp_start = offset
                    # Some notes precede an article which the quotation
                    # leaves out. Check that one literal article in the
                    # main text; do not search ahead for a convenient word.
                    normalized_qb = normal(qb, forms)
                    normalized_actual = normal(actual, forms)
                    if (
                        qb
                        and actual[rp_start : rp_start + 1]
                        and actual[rp_start] in ARTICLES
                        and normalized_actual[rp_start : rp_start + len(qb)]
                        != normalized_qb
                        and normalized_actual[rp_start + 1 : rp_start + 1 + len(qb)]
                        == normalized_qb
                    ):
                        rp_start += 1
            match = matching_blocks(
                tr.get(ref, []),
                rp.get(target, []),
                qa,
                qb,
                units,
                rp_start,
                forms if witness == "tcgnt" else None,
            )
            if not match and note is not None and splits:
                match, break_scope = word_break_match(
                    tr.get(ref, []),
                    rp.get(target, []),
                    qa,
                    qb,
                    units,
                    note,
                    splits,
                    forms,
                )
        if not match or qa is None or qb is None:
            if ref in PATCHES:
                old, new = PATCHES[ref]
                return f"RP2026 Appendix A changed {' '.join(old)} to {' '.join(new) or '∅'}"
            return "no unique exact content match"
        located_tr, located_rp, located_qa, located_qb = [
            normal(side, forms) if witness == "tcgnt" else side
            for side in (tr[ref], rp[target], qa, qb)
        ]
        normalized = (
            witness == "tcgnt"
            and break_scope is None
            and not matching_blocks(tr[ref], rp[target], qa, qb, units, rp_start)
        )
        for index in match:
            unit = units[index]
            if witness not in unit["found_in"]:
                unit["found_in"].append(witness)
            x, y = unit["tr_range"]
            z, w = unit["rp_range"]
            whole = (
                x == y
                and not qa
                or any(
                    i <= x <= y <= i + len(qa)
                    for i in occurrences(located_tr, located_qa)
                )
            ) and (
                z == w
                and not qb
                or any(
                    k <= z <= w <= k + len(qb)
                    for k in occurrences(located_rp, located_qb)
                    if rp_start is None or k == rp_start
                )
            )
            if break_scope is not None:
                whole = index in break_scope
            attachment: UnitInventory = {
                "inventory": witness,
                "entry": number,
                "scope": "unit" if whole else "constituent",
            }
            if normalized:
                attachment["quotation_normalization"] = (
                    "closed movable endings and morphology-licensed nu"
                )
            if break_scope is not None:
                attachment["word_break_normalization"] = (
                    "Boyd Appendix C and closed movable quotation forms"
                )
            if note is not None:
                attachment["hf"] = note["hf"]
            unit["inventories"].append(attachment)
            if note is not None:
                record_side(unit, note)
        return None

    for entry in collation:
        reason = place(
            "collation",
            entry["target_ref"],
            entry["entry"],
            entry["tr"],
            entry["rp"],
            None,
        )
        if reason:
            unmatched.append(
                {
                    "inventory": "collation",
                    "entry": entry["entry"],
                    "target_ref": entry["target_ref"],
                    "tr": entry["tr"],
                    "rp": entry["rp"],
                    "raw": entry["raw"],
                    "reason": reason,
                }
            )
    for note in boyd:
        reason = (
            "multiple Scrivener readings"
            if len(note["tr"]) != 1
            else place(
                "tcgnt",
                note["target_ref"],
                note["entry"],
                reading_words(note["tr"][0]["reading"]),
                reading_words(note["rp"]),
                note,
            )
        )
        if reason:
            unmatched.append({"inventory": "tcgnt", **note, "reason": reason})
    # Merge blocks covered by one collation entry; this preserves a
    # transposition as one unit. Overlapping entry ranges merge together.
    merged: list[Unit] = []
    for ref, units in byref.items():
        number = 0
        intervals: dict[int, list[int]] = {}
        for i, u in enumerate(units):
            for attachment in u["inventories"]:
                if attachment["inventory"] == "collation":
                    intervals.setdefault(attachment["entry"], []).append(i)
        stop: dict[int, int] = {}
        for positions in intervals.values():
            start, end = min(positions), max(positions)
            stop[start] = max(stop.get(start, start), end)
        i = 0
        while i < len(units):
            end = stop.get(i, i)
            j = i
            while j <= end:
                end = max(end, stop.get(j, j))
                j += 1
            group = units[i : end + 1]
            first, last = group[0], group[-1]
            a = tr[ref][first["tr_range"][0] : last["tr_range"][1]]
            b = rp[first["target_ref"]][first["rp_range"][0] : last["rp_range"][1]]
            sides = {u["hf"] for u in group} - {"unknown"}
            number += 1
            merged.append(
                {
                    **first,
                    "id": f"{ref}#{number}",
                    "tr": a,
                    "rp": b,
                    "tr_range": [first["tr_range"][0], last["tr_range"][1]],
                    "rp_range": [first["rp_range"][0], last["rp_range"][1]],
                    "class": (
                        first["class"]
                        if len(group) == 1 or first["class"] == "structural"
                        else classify(a, b)
                    ),
                    "found_in": sorted({s for u in group for s in u["found_in"]}),
                    "inventories": [s for u in group for s in u["inventories"]],
                    "hf": (
                        next(iter(sides))
                        if len(sides) == 1
                        else "other" if sides else "unknown"
                    ),
                    "rp_alternate": any(u["rp_alternate"] for u in group),
                    "patriarchal": any(u["patriarchal"] for u in group),
                }
            )
            i = end + 1
    merged = [annotated_class(u, tr, rp, tags or {}) for u in merged]
    merged, unmatched = cross_verse_attachments(
        merged, unmatched, tr, rp, forms, structure
    )
    for unit in merged:
        # Appendix A is itself the inventory of the readings it introduced.
        if unit["ref"] in PATCHES and patched(*PATCHES[unit["ref"]]) == (
            unit["tr"],
            unit["rp"],
        ):
            unit["found_in"] = sorted(unit["found_in"] + ["rp2026-appendix-a"])
        reasons: dict[str, str] = {}
        for inventory in ("collation", "tcgnt"):
            if inventory in unit["found_in"]:
                continue
            if unit["class"] in {"movable", "word-division"}:
                reasons[inventory] = (
                    "published inventory excludes movable endings and word division"
                )
            elif unit["ref"] in structure.exchanged:
                reasons[inventory] = (
                    "placed wording constituent; the inventory describes the unplaced verse exchange"
                )
        if reasons:
            unit["inventory_absence"] = reasons
    return merged, unmatched


# Supplementary units: relocations and accents.


def verse_number(ref: str) -> int:
    """The number of a verse "BOOK c:v" in its chapter."""
    return int(ref.rsplit(":", 1)[1])


def verses_described(refs: Sequence[str]) -> str:
    """A run of one chapter's verses as TCGNT describes it: "verses 24–26"."""
    return f"verses {verse_number(refs[0])}–{verse_number(refs[-1])}"


def printed_page(snapshot: Mapping[str, PrintedVerse], ref: str) -> int:
    """The page of the printed RP2026 a verse stands on; an omitted verse has none."""
    page = snapshot[ref]["page"]
    if page is None:
        raise ValueError(f"RP2026 does not print {ref}")
    return page


def supplementary_units(
    tr: Words,
    rp: Words,
    collation: Iterable[CollationRow],
    boyd: Sequence[BoydNote],
    snapshot: Mapping[str, PrintedVerse],
    diacritics: Iterable[Diacritic],
    structure: Structure,
    accents: Mapping[str, Mapping[str, str]],
) -> list[Unit]:
    """Verse relocations and accent-only units, with their inventory evidence.
    accents: the editor's accent units (edition/byzantine.json), by unit id,
    each with the TR's and RP's accented words; one that quotes several
    occurrences of a word, with ellipses, is a TCGNT note's."""
    moves: list[Unit] = []
    for ref, target in structure.moved.items():
        inventories: list[UnitInventory] = []
        for row in collation:
            # The old-address deletion and new-address addition are two
            # published sides of the same move. Require literal contents.
            if row["target_ref"] == ref and row["tr"] and not row["rp"]:
                matches = occurrences(tr[ref], row["tr"])
            elif row["target_ref"] == target and row["rp"] and not row["tr"]:
                matches = occurrences(rp[target], row["rp"])
            elif ref in structure.exchanged and row["target_ref"] in {ref, target}:
                same_ref = row["target_ref"]
                matches = occurrences(tr[same_ref], row["tr"]) if row["tr"] else []
                matches = (
                    matches if len(occurrences(rp[same_ref], row["rp"])) == 1 else []
                )
            else:
                continue
            if len(matches) == 1:
                inventories.append(
                    {
                        "inventory": "collation",
                        "entry": row["entry"],
                        "scope": "relocation",
                    }
                )
        moves.append(
            {
                "id": ref + "#move",
                "ref": ref,
                "target_ref": target,
                "kind": "relocation",
                "class": "structural",
                "tr": tr[ref],
                "rp": rp[target],
                "tr_range": [0, len(tr[ref])],
                "rp_range": [0, len(rp[target])],
                "found_in": (
                    ["placement", "collation"] if inventories else ["placement"]
                ),
                "inventories": inventories,
                "hf": "unknown",
                "rp_alternate": False,
                "patriarchal": False,
            }
        )
    # These are descriptions, not Greek quotations. Interpret only TCGNT's
    # descriptions of the declared moves: a moved passage's verses included
    # where one text prints them and omitted where the other does, and the
    # literal note on two verses that exchange places.
    passages: defaultdict[str, list[str]] = defaultdict(list)
    for ref in structure.moved:
        if ref not in structure.exchanged:
            passages[ref.rsplit(":", 1)[0]].append(ref)
    described: dict[tuple[str, str, str], list[Unit]] = {}
    for chapter, sources in passages.items():
        sources.sort(key=verse_number)
        targets = [structure.moved[ref] for ref in sources]
        held = [u for u in moves if u["ref"] in sources]
        before = f"{chapter}:{verse_number(sources[0]) - 1}"
        at, away = verses_described(targets), verses_described(sources)
        described[(targets[0], f"{{include {at}}}", f"{{omit {at}}}")] = held
        described[(before, f"{{omit {away}}}", f"{{include {away}}}")] = held
    exchanges = sorted(
        {
            tuple(sorted((ref, structure.moved[ref]), key=verse_number))
            for ref in structure.exchanged
        }
    )
    for note in boyd:
        selected: list[Unit] = []
        for first, second in exchanges:
            if note["target_ref"] == first and note["fr"] == (
                f"{first.split()[1]}–{verse_number(second)}"
            ):
                a, b = tr[first] + tr[second], rp[first] + rp[second]
                qa = reading_words(note["tr"][0]["reading"])
                qb = reading_words(note["rp"])
                if (
                    qa
                    and qb
                    and len(occurrences(a, qa)) == len(occurrences(b, qb)) == 1
                ):
                    selected = [u for u in moves if u["ref"] in (first, second)]
        key = (note["target_ref"], note["rp"], note["tr"][0]["reading"])
        if key in described:
            selected = described[key]
        for unit in selected:
            unit["inventories"].append(
                {"inventory": "tcgnt", "entry": note["entry"], "scope": "relocation"}
            )
            if "tcgnt" not in unit["found_in"]:
                unit["found_in"].append("tcgnt")

    declared: dict[str, Mapping[str, str]] = {}
    for unit_id, decision in accents.items():
        if not unit_id.endswith("#accent"):
            raise ValueError(f"Accent decision not keyed by its unit: {unit_id}")
        declared[unit_id.removesuffix("#accent")] = decision
    entries: list[Diacritic] = list(diacritics)
    for ref, decision in declared.items():
        if " … " in decision["rp"]:
            continue
        if any(entry["ref"] == ref for entry in entries):
            raise ValueError(f"Accent decision the printed apparatus makes: {ref}")
        entries.append(
            {"ref": ref, "from": decision["tr"], "to": decision["rp"], "listed": True}
        )
    accent_units: list[Unit] = []
    for entry in entries:
        ref = entry["ref"]
        old, new = entry["from"], entry["to"]
        words = ascii_greek(old).split()
        if words != ascii_greek(new).split():
            raise ValueError(f"Not an accent-only reading: {ref}")
        in_tr, in_rp = occurrences(tr[ref], words), occurrences(rp[ref], words)
        if len(in_tr) != 1 or len(in_rp) != 1:
            raise ValueError(f"Ambiguous accent reading: {ref}")

        # Compare at the precision the entry quotes: one that quotes only a
        # breathing (Heli, Luke 3:23) says nothing of the accent the printed
        # main text also sets, and keeps the breathing.
        marks = "\u0300\u0301\u0342"
        accented = any(mark in unicodedata.normalize("NFD", new) for mark in marks)

        def normalized(s: str) -> str:
            value = unicodedata.normalize("NFD", s.lower())
            if not accented:
                value = "".join(c for c in value if c not in marks)
            return value

        if normalized(snapshot[ref]["accented"][in_rp[0]]) != normalized(new):
            raise ValueError(f"Printed accent disagrees: {ref}")
        inventories = []
        for note in boyd:
            if note["target_ref"] == ref and normalized(note["rp"]) == normalized(new):
                if any(normalized(v["reading"]) == normalized(old) for v in note["tr"]):
                    inventories.append(
                        {"inventory": "tcgnt", "entry": note["entry"], "scope": "unit"}
                    )
        found_in = (
            ["rp2026-printed"] if entry.get("listed") else ["rp2026-apparatus"]
        ) + (["tcgnt"] if inventories else [])
        accent_units.append(
            {
                "id": ref + "#accent",
                "ref": ref,
                "target_ref": ref,
                "kind": "accent",
                "class": "accent",
                "tr": words,
                "rp": words,
                "tr_accented": old,
                "rp_accented": new,
                "tr_range": [in_tr[0], in_tr[0] + 1],
                "rp_range": [in_rp[0], in_rp[0] + 1],
                "found_in": found_in,
                "inventories": inventories,
                "hf": "unknown",
                "rp_alternate": False,
                "patriarchal": False,
                "page": printed_page(snapshot, ref),
            }
        )
    # A decision that quotes several occurrences of one word is TCGNT's note
    # on them: one published unit per note, including the unchanged words
    # between them.
    for ref, decision in declared.items():
        if " … " not in decision["rp"]:
            continue
        candidates = [
            n for n in boyd if n["target_ref"] == ref and n["rp"] == decision["rp"]
        ]
        if len(candidates) != 1:
            raise ValueError(f"Missing breathing inventory: {ref}")
        note = candidates[0]
        if note["tr"][0]["reading"] != decision["tr"]:
            raise ValueError(f"Changed breathing inventory: {ref}")
        marked = decision["rp"].split(" … ")
        forms = {ascii_greek(w) for w in [*marked, *decision["tr"].split(" … ")]}
        if len(forms) != 1:
            raise ValueError(f"Not one word's breathing: {ref}")
        word = forms.pop()
        left, right = occurrences(tr[ref], [word]), occurrences(rp[ref], [word])
        if len(left) != len(marked) or len(right) != len(marked):
            raise ValueError(f"Ambiguous breathing reading: {ref}")
        i, j, k, l = left[0], left[-1] + 1, right[0], right[-1] + 1
        position = note["position"]
        if tr[ref][i:j] != rp[ref][k:l] or position is None or position["offset"] != k:
            raise ValueError(f"Changed breathing scope: {ref}")
        if any(
            unicodedata.normalize("NFD", snapshot[ref]["accented"][at])
            != unicodedata.normalize("NFD", form)
            for at, form in zip(right, marked, strict=True)
        ):
            raise ValueError(f"Printed breathing disagrees: {ref}")
        accent_units.append(
            {
                "id": ref + "#accent",
                "ref": ref,
                "target_ref": ref,
                "kind": "accent",
                "class": "accent",
                "tr": tr[ref][i:j],
                "rp": rp[ref][k:l],
                "tr_accented": note["tr"][0]["reading"],
                "rp_accented": note["rp"],
                "tr_range": [i, j],
                "rp_range": [k, l],
                "found_in": ["rp2026-printed", "tcgnt"],
                "inventories": [
                    {"inventory": "tcgnt", "entry": note["entry"], "scope": "unit"}
                ],
                "hf": note["hf"],
                "rp_alternate": note["rp_alternate"],
                "patriarchal": note["patriarchal"],
                "page": printed_page(snapshot, ref),
            }
        )
    return moves + accent_units
