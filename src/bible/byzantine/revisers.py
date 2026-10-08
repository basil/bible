"""The Revised Version of 1881 and Boyd's ASV of 2021 as witnesses.

A revision changes text and wording together and does not say which is
which. Its change is a report only where the CrossWire bridge places it on
the words of one Greek unit, or where it makes the same contrast on the same
words as a placed instruction. The RV is read only where Westcott and Hort,
whose text the revisers mostly adopted, read with RP; Boyd's ASV revision
targets RP2018 and is not read where Appendix A changes unaccented words.
Each Boyd row says whether he changed the 1901 ASV there or kept its words.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Container, Iterable, Iterator, Mapping, Sequence
from difflib import SequenceMatcher
from typing import TypedDict, overload

from bible.byzantine import BOYD_ASV, RV
from bible.byzantine.apparatus import overlaps
from bible.byzantine.crosswire import (
    SPELLINGS,
    Aligned,
    bridged_words,
    fitting_unit,
    spans,
    words,
)
from bible.byzantine.greek import PATCHES, Structure, occurrences
from bible.byzantine.rows import (
    Alarm,
    Attachment,
    BoydNote,
    Instruction,
    RevisionRow,
    Unit,
)
from bible.byzantine.units import NEUTRAL_CLASSES as NEUTRAL


class Change(TypedDict):
    """A change a revision makes: its kind, the KJV words it changes (by
    index), the words on either side, and where the new words stand."""

    side: str
    kind: str
    word_range: list[int]
    old: str
    new: str
    span: list[int]


# What an instruction edit does at a verse: its kind, the KJV words it
# changes (by index) and their words, the new words, and its unit.
type Contrast = tuple[str, list[int], list[str], str, Attachment]

# Boyd's modern spellings, compared as the older form. Only for comparison:
# a row quotes each source's own words.
RESPELLINGS = {
    "straightaway": "straightway",
    "judea": "judaea",
    "worshiped": "worshipped",
    "worshiping": "worshipping",
    "worshiper": "worshipper",
    "worshipers": "worshippers",
    "worshipeth": "worshippeth",
    "marveled": "marvelled",
    "marveling": "marvelling",
    "marvelous": "marvellous",
    "fullness": "fulness",
    "steadfast": "stedfast",
    "steadfastly": "stedfastly",
    "steadfastness": "stedfastness",
    "unsteadfast": "unstedfast",
    "fulfill": "fulfil",
    "fulfillment": "fulfilment",
    "defense": "defence",
    "offense": "offence",
    "pretense": "pretence",
    "elizabeth": "elisabeth",
    "elizabeth's": "elisabeth's",
    "sepulcher": "sepulchre",
    "sepulchers": "sepulchres",
    "galilean": "galilaean",
    "galileans": "galilaeans",
    "arimathea": "arimathaea",
    "idumea": "idumaea",
    "berea": "beroea",
    "entrusted": "intrusted",
    "jailer": "jailor",
    "councilor": "councillor",
    "enroll": "enrol",
    "enrollment": "enrolment",
    "villainy": "villany",
    "sergeants": "serjeants",
    "theater": "theatre",
    "reveling": "revelling",
    "revelings": "revellings",
    "unreprovable": "unreproveable",
    "willfully": "wilfully",
    "cumin": "cummin",
    "carcass": "carcase",
    "brazen": "brasen",
    "plaited": "platted",
    "plaiting": "platting",
    "enclosed": "inclosed",
    "appareled": "apparelled",
    "staunched": "stanched",
    # The tribes of Revelation 7, which the KJV names after the Greek.
    "asher": "aser",
    "naphtali": "nephthalim",
    "manasseh": "manasses",
    "issachar": "isachar",
    "zebulun": "zabulon",
}
# Words written joined in one source and apart in another, compared joined.
COMPOUNDS = frozenset(
    """forever forevermore everyone anyone someone anymore today tomorrow
    longsuffering stumblingblock wayside seaside ofttimes wrongdoing
    midheaven evildoer evildoers cornerstone housetops mountainside
    bridechamber seacoast wineskins fullgrown highminded likeminded
    doubleminded""".split()
)


def comparable(text: str) -> list[tuple[str, int, int, int, int]]:
    """The words of a verse for comparison: (word, first, stop, start, end).

    first and stop are the indices of the source words, as the CrossWire
    bridge counts them; start and end are character offsets.
    """
    items: list[tuple[str, int, int, int, int]] = []
    for n, (word, start, end) in enumerate(spans(text)):
        word = SPELLINGS.get(word, word)
        word = RESPELLINGS.get(word, word)
        if items and items[-1][0] + word in COMPOUNDS:
            joined = items.pop()
            items.append((joined[0] + word, joined[1], n + 1, joined[3], end))
        else:
            items.append((word, n, n + 1, start, end))
    return items


def changes(before: str, after: str) -> Iterator[Change]:
    """Each change from one verse to the other, by the first's word indices."""
    a, b = comparable(before), comparable(after)
    count = a[-1][2] if a else 0
    matcher = SequenceMatcher(
        None, [x[0] for x in a], [x[0] for x in b], autojunk=False
    )
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        first = a[i1][1] if i1 < len(a) else count
        stop = a[i2 - 1][2] if i2 > i1 else first
        at = b[j1][3] if j1 < len(b) else len(after)
        # An insertion stands after the word before it, or before what
        # follows: the revision's text says which side of a stop it is on.
        side = "after" if after[:at].rstrip()[-1:].isalnum() else "before"
        if op == "insert" and i1 and j1:
            # Before the KJV's stop where the revision sets that stop after
            # the words it inserts, whatever it sets before them (REV 20:14
            # "the second death, [even] the lake of fire.").
            stops = set(before[a[i1 - 1][4] : a[i1][3] if i1 < len(a) else None]) & set(
                ".,;:?!"
            )
            following = after[b[j2 - 1][4] : b[j2][3] if j2 < len(b) else None]
            if stops & set(following) and not stops & set(after[b[j1 - 1][4] : at]):
                side = "after"
        yield {
            "side": side,
            "kind": op,
            "word_range": [first, stop],
            "old": before[a[i1][3] : a[i2 - 1][4]] if i2 > i1 else "",
            "new": after[b[j1][3] : b[j2 - 1][4]] if j2 > j1 else "",
            "span": [at, b[j2 - 1][4] if j2 > j1 else at],
        }


def wh_side(unit: Unit, notes: Mapping[int, BoydNote]) -> str | None:
    """Where Westcott and Hort stand at a unit, by Boyd's sigla, or None.

    Boyd writes CT where all the critical editions agree, WH among them.
    A reading his note does not list is RP's.
    """
    sides: set[str] = set()
    for found in unit["inventories"]:
        if found["inventory"] != "tcgnt":
            continue
        variants = [
            v
            for v in notes[found["entry"]]["variants"]
            if {"WH", "CT"} & set(v["sigla"])
        ]
        if not variants:
            sides.add("RP")
        elif any({"TR", "SCR"} & set(v["sigla"]) for v in variants):
            sides.add("TR")
        else:
            sides.add("other")
    return sides.pop() if len(sides) == 1 else None


def readable(units: Sequence[Unit], notes: Iterable[BoydNote]) -> dict[str, set[str]]:
    """The units at which each revision is read: the RV where Westcott and
    Hort stand with RP, and Boyd's ASV where RP is not patched."""
    by_entry = {n["entry"]: n for n in notes}
    return {
        RV: {u["id"] for u in units if wh_side(u, by_entry) == "RP"},
        BOYD_ASV: {u["id"] for u in units if u["ref"] not in PATCHES},
    }


def contrasts(instructions: Iterable[Instruction]) -> dict[str, list[Contrast]]:
    """The attached instruction edits by verse, as (kind, range, old words,
    new, attachment), for placing a revision's change by English contrast."""
    result: defaultdict[str, list[Contrast]] = defaultdict(list)
    for i in instructions:
        if i.get("scope") != "greek":
            continue
        for edit in i["edits"]:
            for uid in edit.get("units", []):
                result[edit["ref"]].append(
                    (
                        edit["kind"],
                        list(edit["word_range"]),
                        words(edit["old"]),
                        edit["new"],
                        {"unit": uid, "scope": edit.get("scope", "unit")},
                    )
                )
    return result


def revision_reports(
    name: str,
    kjv: Mapping[str, str],
    revision: Mapping[str, str],
    aligned: Mapping[str, Aligned],
    units: Sequence[Unit],
    admitted: Container[str],
    base: Mapping[str, str] | None = None,
    instructions: Iterable[Instruction] = (),
) -> list[RevisionRow]:
    """One row for each change of the revision that one Greek unit explains.

    A change that the alignment fits to no single unit, but that makes on
    the same words the same contrast as a placed instruction, takes its unit
    (the `english` method). Only the admitted units,
    as `readable` gives them, are read. With base, the text the
    revision was made from, a row says whether the reviser changed the base
    there ("revised") or kept its words ("kept").
    """
    by_ref: defaultdict[str, list[Unit]] = defaultdict(list)
    by_id = {u["id"]: u for u in units}
    for unit in units:
        by_ref[unit["ref"]].append(unit)
    placed = contrasts(instructions)
    rows: list[RevisionRow] = []
    for ref, candidates in by_ref.items():
        text = revision.get(ref, "")
        if ref not in aligned or not text.strip():
            continue
        made = [c["span"] for c in changes(base.get(ref, ""), text)] if base else None
        for n, change in enumerate(changes(kjv[ref], text), start=1):
            i, j = change["word_range"]
            fit = fitting_unit(candidates, aligned[ref], i, j, change["kind"])
            contrast = change["kind"], [i, j], words(change["old"]), change["new"]
            # Several witnesses may quote the same contrast at the same
            # unit. Their agreement is one attachment, not an ambiguity.
            same = {
                (u["unit"], u["scope"]) for *c, u in placed[ref] if tuple(c) == contrast
            }
            if fit:
                (unit, scope, _), method = fit, "aligned"
            elif len(same) == 1:
                uid, scope = next(iter(same))
                unit = by_id[uid]
                method = "english"
            else:
                continue
            if unit["class"] in NEUTRAL or unit["id"] not in admitted:
                continue
            row: RevisionRow = {
                "witness": name,
                "entry": f"{ref}#{n}",
                "ref": ref,
                "kind": change["kind"],
                "old": change["old"],
                "new": change["new"],
                "word_range": [i, j],
                "units": [{"unit": unit["id"], "scope": scope}],
                "scope": "greek",
                "method": method,
                "hf": unit["hf"],
            }
            if change["kind"] == "insert":
                row["side"] = change["side"]
            if made is not None:
                row["reviser"] = (
                    "revised"
                    if any(overlaps(change["span"], s) for s in made)
                    else "kept"
                )
            rows.append(row)
    return rows


@overload
def at_kjv_addresses(
    boyd: Mapping[str, str], kjv: Iterable[str], structure: Structure
) -> dict[str, str]: ...


@overload
def at_kjv_addresses[T, M](
    boyd: Mapping[str, T], kjv: Iterable[str], structure: Structure, missing: M
) -> dict[str, T | M]: ...


def at_kjv_addresses(
    boyd: Mapping[str, object],
    kjv: Iterable[str],
    structure: Structure,
    missing: object = "",
) -> Mapping[str, object]:
    """Boyd's ASV, which stands at RP's addresses, at the KJV's. The 1901
    ASV and the RV stand at the KJV's already."""
    return {ref: boyd.get(structure.rp_ref(ref), missing) for ref in kjv}


def phrase_count(text: str, phrase: str) -> int:
    """Literal word occurrences, ignoring case and punctuation, not restyling."""
    return len(occurrences(words(text), words(phrase)))


def alarms(
    units: Iterable[Unit],
    aligned: Mapping[str, Aligned],
    kjv: Mapping[str, str],
    texts: Mapping[str, Mapping[str, str]],
) -> dict[str, Alarm]:
    """The revision alarm at each unit: the KJV words CrossWire ties to the
    unit's TR words are missing from both the RV and Boyd's ASV. A unit with
    no TR words, a change of order, or no verified bridge has no alarm to
    check. Literal absence is an attention signal, not semantic omission.
    texts: {witness: verses at the KJV's addresses}; both revision maps
    must be present before a comparison is available."""
    result: dict[str, Alarm] = {}
    for unit in units:
        ref, (a, b) = unit["ref"], unit["tr_range"]
        bridge = aligned.get(ref)
        if unit["class"] == "order" or (not unit.get("kind") and a == b):
            result[unit["id"]] = {"applicable": False, "available": False}
            continue
        if unit.get("kind") or bridge is None:
            result[unit["id"]] = {"applicable": True, "available": False}
            continue
        indices = bridged_words(bridge, a, b)
        runs: list[list[int]] = []
        for index in indices:
            if runs and index == runs[-1][-1] + 1:
                runs[-1].append(index)
            else:
                runs.append([index])
        text = kjv[ref]
        phrases = [
            text[bridge["word_ranges"][run[0]][0] : bridge["word_ranges"][run[-1]][1]]
            for run in runs
        ]
        others = [texts[name].get(ref) for name in texts]
        present = [o for o in others if o is not None and o.strip()]
        available = (
            bool(phrases)
            and {RV, BOYD_ASV} <= texts.keys()
            and len(present) == len(others)
        )
        missing = [
            p
            for p in phrases
            if available and all(phrase_count(o, p) == 0 for o in present)
        ]
        result[unit["id"]] = {
            "applicable": bool(phrases),
            "available": available,
            "phrases": phrases,
            "missing": missing,
            "alarm": bool(missing),
        }
    return result
