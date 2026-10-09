"""Published KJV-worded instructions, from any source, laid on the Greek units.

An instruction source parses its own syntax and binds each edit to words of
the pinned KJV. Pierpont's booklet is the one read; `ADDITIONAL` names a
second source, for which nothing is read. From there on every source is
treated alike: `attach` says which Greek unit each edit is about,
`compatibility` says whether the edit may execute as the unit's RP2026
reading, `select` chooses among the instructions at a unit by source
precedence, and `corroborating` names the witnesses that agree with it.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from bible.byzantine import INSTRUCTION_SOURCES
from bible.byzantine.crosswire import (
    FUNCTION_WORDS,
    Aligned,
    contrast,
    edit_offsets,
    fitting_unit,
    reported_operation,
    spans,
    words,
)
from bible.byzantine.greek import occurrences
from bible.byzantine.rendering import Checker
from bible.byzantine.rows import (
    Attachment,
    Instruction,
    InstructionEdit,
    Override,
    Report,
    Unit,
)

# Classes that a KJV-worded change cannot be about: orthography the English
# cannot show. A proper name's spelling can show (Bethphage, Bethsphage).
ORTHOGRAPHIC = {"movable", "word-division", "spelling"}

# What one edit does, for comparing edits: its verse, kind, words, contrast
# and side.
EditKey = tuple[str, str, tuple[int, ...], tuple[tuple[str, ...], tuple[str, ...]], str]


def bind_plain(edit: Mapping[str, Any], text: str) -> dict[str, Any]:
    """Bind an explicit edit: `old` occurs once (or `occurrence` says which);
    an insertion stands after or before its `anchor`, likewise."""
    tokens = words(text)
    kind = edit["kind"]
    occurrence = edit.get("occurrence")
    if "occurrence" in edit and (type(occurrence) is not int or occurrence < 1):
        raise ValueError("instruction occurrence must be a positive integer")
    if kind == "insert":
        if edit.get("side", "after") not in {"before", "after"}:
            raise ValueError("instruction insertion side must be before or after")
        anchor = words(edit.get("anchor", ""))
        hits = occurrences(tokens, anchor) if anchor else []
        if occurrence is not None:
            hits = hits[occurrence - 1 : occurrence]
        if len(hits) != 1:
            return {**edit, "bind": "ambiguous" if hits else "absent"}
        at = hits[0] + (len(anchor) if edit.get("side", "after") == "after" else 0)
        return {
            **edit,
            "bind": "unique",
            "word_range": [at, at],
            "side": edit.get("side", "after"),
        }
    old = words(edit["old"])
    hits = occurrences(tokens, old)
    if occurrence is not None:
        hits = hits[occurrence - 1 : occurrence]
    if len(hits) != 1:
        return {**edit, "bind": "ambiguous" if hits else "absent"}
    return {**edit, "bind": "unique", "word_range": [hits[0], hits[0] + len(old)]}


def attach(
    instructions: Iterable[Instruction],
    units: Iterable[Unit],
    aligned: Mapping[str, Aligned],
    reports: Iterable[Report] = (),
) -> list[Instruction]:
    """Say which Greek unit each bound edit is about, and how it was found.

    Methods, tried in order: `aligned` (the changed KJV words bridge to the
    unit's Scrivener tokens), `construction` (a transposition spanning several
    adjacent units whose Greek is one reordering), `contrast` (an apparatus
    report attached by its Greek makes the same English contrast), `shape`
    (an addition or omission, and the verse has one unit that only adds or
    only omits words), `sole`
    (the verse has one unit and the edit's shape does not contradict it).
    Contrast evidence includes objective apparatus placements. These three
    fallbacks require changed English words; punctuation alone supplies no
    lexical contrast or addition/omission shape.
    An edit no method places stays unattached and is listed in the review.
    """
    by_ref: defaultdict[str, list[Unit]] = defaultdict(list)
    for u in units:
        by_ref[u["ref"]].append(u)
    by_ref_reports: defaultdict[str, list[Report]] = defaultdict(list)
    for r in reports:
        by_ref_reports[r["ref"]].append(r)
    result: list[Instruction] = []
    for instruction in instructions:
        row: Instruction = {
            **instruction,
            "edits": [e.copy() for e in instruction["edits"]],
        }
        attached: dict[str, Attachment] = {}
        unattached: list[list[int]] = []
        for edit in row["edits"]:
            if edit.get("bind") != "unique" or "ref" not in edit:
                continue
            ref = edit["ref"]
            candidates = [
                u
                for u in by_ref[ref]
                if u.get("kind") != "relocation" and u["class"] != "accent"
            ]
            if not by_ref[ref]:
                edit["method"] = None
                continue
            i, j = edit["word_range"]
            kind = edit["kind"]
            # The units, the scope, the aligned TR positions and the method.
            fit: tuple[list[Unit], str, set[int], str] | None = None
            if ref in aligned:
                found = fitting_unit(
                    candidates, aligned[ref], i, j, kind, transpose=kind == "transpose"
                )
                if found:
                    unit, scope, positions = found
                    fit = [unit], scope, positions, "aligned"
                elif kind == "transpose":
                    positions = {p for ps in aligned[ref]["positions"][i:j] for p in ps}
                    construction = sorted(
                        (
                            u
                            for u in candidates
                            if positions & set(range(*u["tr_range"]))
                        ),
                        key=lambda u: u["tr_range"],
                    )
                    before = [w for u in construction for w in u["tr"]]
                    after = [w for u in construction for w in u["rp"]]
                    if (
                        len(construction) > 1
                        and before != after
                        and sorted(before) == sorted(after)
                    ):
                        fit = construction, "unit", positions, "construction"
            if not fit:
                own = contrast(edit["old"], edit["new"])
                # Tokenless equality does not locate punctuation: a colon
                # cannot inherit a closing-quote report's Greek unit. The
                # shape and sole fallbacks below likewise need changed words.
                ids = {
                    a["unit"]
                    for r in by_ref_reports[ref]
                    if any(own)
                    and (old := r.get("old")) is not None
                    and (new := r.get("new")) is not None
                    and r.get("method") in {"greek", "aligned", "hand"}
                    and contrast(old, new) == own
                    for a in r["units"]
                }
                chosen = [u for u in candidates if u["id"] in ids]
                if len(chosen) == 1:
                    fit = chosen, "constituent", set(), "contrast"
            if not fit and any(own) and kind in {"insert", "delete"}:
                # An addition or omission whose words the bridge cannot place
                # (beside a supplied italic word, say) fits the verse's one unit
                # that adds, or omits, words outright.
                shaped = [
                    u
                    for u in candidates
                    if (
                        kind == "insert"
                        and u["tr_range"][0] == u["tr_range"][1]
                        and u["rp_range"][0] < u["rp_range"][1]
                    )
                    or (
                        kind == "delete"
                        and u["rp_range"][0] == u["rp_range"][1]
                        and u["tr_range"][0] < u["tr_range"][1]
                    )
                ]
                if len(shaped) == 1:
                    fit = [shaped[0]], "constituent", set(), "shape"
            if not fit and any(own) and len(candidates) == 1:
                unit = candidates[0]
                omission, addition, transposition = reported_operation(edit)
                a, b = unit["tr_range"]
                c, d = unit["rp_range"]
                contradicts = (
                    omission
                    and d - c >= b - a
                    or addition
                    and b - a >= d - c
                    or transposition
                    and unit["class"] != "order"
                )
                if not contradicts:
                    fit = [unit], "constituent", set(), "sole"
            if fit:
                found_units, scope, positions, method = fit
                edit["units"] = [u["id"] for u in found_units]
                edit["scope"] = scope
                edit["method"] = method
                edit["positions"] = sorted(positions)
                for u in found_units:
                    attached.setdefault(
                        u["id"], {"unit": u["id"], "scope": scope, "method": method}
                    )
            else:
                edit["method"] = None
                unattached.append(edit["word_range"])
        row["units"] = list(attached.values())
        if not any(by_ref[r] for r in row.get("refs", []) if r):
            row["scope"] = "out-of-scope"
            row["reason"] = row.get("reason") or "no Greek unit in the verse"
        elif attached and not unattached:
            row["scope"] = "greek"
        elif attached:
            row["scope"] = "greek"
            row["reason"] = "some occurrences attach to no unit"
        else:
            row["scope"] = "verse"
            row["reason"] = row.get("reason") or (
                "edit attaches to no unit"
                if row["bind"] == "unique"
                else f"binding {row['bind']}"
            )
        result.append(row)
    return result


def same_content(old: str, new: str) -> bool:
    """Whether a reordering preserves the KJV's content-word forms.

    Case, punctuation and grammatical function words may change; shared
    Greek does not license a new inflection or rendering of a content word.
    Supplied-word brackets change typography, not the words compared here.
    """

    def forms(text: str) -> list[str]:
        return sorted(
            w
            for w in words(text.replace("[", "").replace("]", ""))
            if w not in FUNCTION_WORDS and not w.isdigit()
        )

    return forms(old) == forms(new)


def supplied_only(
    text: str, edit: InstructionEdit, supplied: Sequence[tuple[int, int, str]]
) -> bool:
    """Whether every changed KJV word of the edit is a supplied (italic) word."""
    if edit["kind"] == "insert":
        return False
    tokens = [
        (s, e) for _, s, e in spans(text)[edit["word_range"][0] : edit["word_range"][1]]
    ]
    return bool(tokens) and all(
        any(a <= s and e <= b for a, b, _ in supplied) for s, e in tokens
    )


def compatibility(
    instruction: Instruction,
    units_by_id: Mapping[str, Unit],
    kjv: Mapping[str, str],
    supplied: Mapping[str, Sequence[tuple[int, int, str]]],
    checker: Checker | None = None,
) -> tuple[str, str | None]:
    """Whether the instruction may execute as the unit's RP2026 reading.

    Returns (status, reason). `compatible` needs every edit bound uniquely,
    attached, and of a shape the unit's Greek allows: an omission where RP
    has fewer words (or, when the words were aligned, any change of wording),
    an addition where RP has more, a transposition at a reordering, a
    replacement at any unit but pure orthography.
    `agrees` means the KJV already reads so; nothing executes. With a
    `checker` (rendering.Checker), an edit whose words render Greek RP2026
    keeps, or add a rendering of Greek both texts share, is incompatible, and
    the instruction records whether its rendering is verified or unverified.
    """
    instruction.pop("refused_by", None)
    instruction.pop("rendering", None)
    if instruction.get("scope") == "out-of-scope":
        return "out-of-scope", instruction.get("reason")
    if instruction.get("role") == "agrees":
        return "agrees", "the KJV already reads with the Majority here"
    edits = instruction.get("edits", [])
    if not edits or instruction.get("bind") not in {"unique", "already"}:
        return "unbound", f"binding {instruction.get('bind')}"
    if any(e.get("bind") not in {"unique", "already"} for e in edits):
        return "unbound", "an occurrence does not bind uniquely"
    # An insertion whose words the KJV has there already changes nothing.
    if all(
        e.get("bind") == "already"
        or e.get("no_effect")
        or (not e["old"] and not e["new"])
        for e in edits
    ):
        return "agrees", "the instruction changes nothing in the pinned KJV"
    if any(e.get("bind") != "unique" for e in edits):
        return "unbound", "an insertion the KJV already has stands with a change"
    if any(not e.get("units") for e in edits):
        return "unattached", instruction.get("reason") or "an edit attaches to no unit"

    # Italic words supplied by the translators render no Greek, so an
    # instruction that only touches them is not about the text. An omission
    # of a whole Greek reading is the exception: the Cambridge text sets some
    # doubtful passages in italics (1 John 5:7-8) though the TR has them.
    def textual_omission(e: InstructionEdit) -> bool:
        return e["kind"] == "delete" and all(
            not units_by_id[u]["rp"] for u in e["units"]
        )

    if all(
        supplied_only(kjv[e["ref"]], e, supplied.get(e["ref"], []))
        and not textual_omission(e)
        for e in edits
    ):
        return (
            "incompatible",
            "changes only supplied (italic) words, which render no Greek",
        )
    verdicts: list[str] = []
    for e in edits:
        for uid in e["units"]:
            u = units_by_id[uid]
            if u["class"] in ORTHOGRAPHIC:
                return "incompatible", f"{uid} is {u['class']} only"
            a, b = u["tr_range"]
            c, d = u["rp_range"]
            tr_count, rp_count = b - a, d - c
            kind, method = e["kind"], e.get("method")
            if kind == "delete" and rp_count >= tr_count and method != "aligned":
                return "incompatible", f"omission at {uid}, where RP is not shorter"
            if kind == "delete" and rp_count >= tr_count and u["class"] in {"addition"}:
                return "incompatible", f"omission at {uid}, which RP adds to"
            if kind == "insert" and tr_count >= rp_count and method != "aligned":
                return "incompatible", f"addition at {uid}, where RP is not longer"
            if kind == "insert" and tr_count >= rp_count and u["class"] in {"omission"}:
                return "incompatible", f"addition at {uid}, which RP omits"
            if (
                kind == "transpose"
                and u["class"] != "order"
                and method != "construction"
            ):
                return (
                    "incompatible",
                    f"transposition at {uid}, which is not a reordering",
                )
            if (
                kind == "transpose"
                or all(units_by_id[x]["class"] == "order" for x in e["units"])
            ) and not same_content(e["old"], e["new"]):
                return (
                    "incompatible",
                    f"{uid} only reorders the same words; a {kind} that changes the content words cannot render it",
                )
    # The words themselves, once every edit has the shape its unit needs: do
    # they render what RP2026 changed?
    for e in edits:
        if checker is not None:
            verdict, reason = checker.check(e, e["units"])
            if verdict == "contradicted":
                # Provisional: `constructions` checks the whole group again,
                # where a word another edit restores is a move.
                instruction["refused_by"] = "rendering"
                return "incompatible", reason
            verdicts.append(verdict)
    if checker is not None:
        instruction["rendering"] = (
            "unverified"
            if "unverified" in verdicts
            else "verified" if verdicts else None
        )
    return "compatible", None


def edit_key(e: InstructionEdit) -> EditKey:
    """What one edit does, for comparing edits."""
    return (
        e["ref"],
        e["kind"],
        tuple(e["word_range"]),
        contrast(e["old"], e["new"]),
        e.get("side", "before"),
    )


def signature(instruction: Instruction, unit: str) -> tuple[EditKey, ...]:
    """What the instruction does at the unit, for comparing instructions."""
    return tuple(
        edit_key(e) for e in instruction["edits"] if unit in e.get("units", [])
    )


def overlapping(edits: Sequence[InstructionEdit]) -> bool:
    """Whether two edits touch the same KJV words of one verse."""
    for n, x in enumerate(edits):
        for y in edits[n + 1 :]:
            if x["ref"] != y["ref"]:
                continue
            a, b = x["word_range"]
            c, d = y["word_range"]
            if a < d and c < b or a == b == c == d:
                return True
    return False


def effect(
    edits: Iterable[InstructionEdit], kjv: Mapping[str, str]
) -> dict[str, tuple[str, ...]]:
    """The words of each touched verse after the edits, for comparing what two
    instructions do rather than how they cut their changes."""
    by_ref: defaultdict[str, list[InstructionEdit]] = defaultdict(list)
    for e in edits:
        by_ref[e["ref"]].append(e)
    result: dict[str, tuple[str, ...]] = {}
    for ref, own in by_ref.items():
        tokens = words(kjv[ref])
        for e in sorted(own, key=lambda e: e["word_range"], reverse=True):
            i, j = e["word_range"]
            tokens = tokens[:i] + words(e["new"]) + tokens[j:]
        result[ref] = tuple(tokens)
    return result


def select(
    instructions: Sequence[Instruction],
    unit: str,
    kjv: Mapping[str, str] | None = None,
) -> tuple[Instruction | None, list[Instruction], str | None]:
    """Choose what executes at a unit from the compatible instructions.

    The highest-precedence source with a compatible instruction decides.
    Within it, one signature (or several non-overlapping ones) is selected,
    and each lower source whose edits leave the verse reading the same
    corroborates; one whose edits leave it reading differently disagrees.
    Different overlapping signatures within the deciding source are a
    conflict and nothing is selected. Returns (selected, disagreeing,
    conflict_reason); `selected` carries the combined `edits` and the `joint`
    instruction identities.
    """
    at_unit = [
        i for i in instructions if any(a["unit"] == unit for a in i.get("units", []))
    ]
    compatible = [i for i in at_unit if i.get("compatibility") == "compatible"]
    agreeing = [i for i in at_unit if i.get("compatibility") == "agrees"]
    for source in INSTRUCTION_SOURCES:
        own = [i for i in compatible if i["source"] == source]
        if not own:
            continue
        signatures = {signature(i, unit) for i in own}
        combined: list[InstructionEdit] = []
        for i in own:
            for e in i["edits"]:
                if unit in e.get("units", []) and e not in combined:
                    combined.append(e)
        if len(signatures) > 1 and overlapping(combined):
            return None, [], f"conflicting {source} instructions at the unit"
        # A conflict elsewhere in the same source's group takes the whole
        # construction down, including units whose own edits do not overlap.
        # Checking only `combined` can otherwise execute one half before the
        # executor refuses the other half's overlapping words.
        # The same edit from two of the source's rows agrees with itself, and
        # one row overlapping its own edits is the executor's to refuse.
        groups = {i["group"] for i in own if i.get("group")}
        grouped: defaultdict[int, list[InstructionEdit]] = defaultdict(list)
        seen: set[EditKey] = set()
        for i in instructions:
            if (
                i["source"] == source
                and i.get("group") in groups
                and i.get("compatibility") == "compatible"
            ):
                for e in i["edits"]:
                    if e.get("word_range") is None:
                        continue
                    key = edit_key(e)
                    if key not in seen:
                        seen.add(key)
                        grouped[i["entry"]].append(e)
        rows = list(grouped.values())
        if any(
            overlapping([e, f])
            for n, x in enumerate(rows)
            for y in rows[n + 1 :]
            for e in x
            for f in y
        ):
            return None, [], f"conflicting {source} instructions in the construction"
        chosen: Instruction = {
            **own[0],
            "edits": combined,
            "joint": [{"source": i["source"], "entry": i["entry"]} for i in own],
        }
        others = [
            i
            for i in at_unit
            if i["source"] != source
            and i.get("compatibility") in {"compatible", "superseded"}
        ]
        if kjv is not None:
            wanted = effect(combined, kjv)
            disagreeing = [
                i
                for i in others
                if effect([e for e in i["edits"] if unit in e.get("units", [])], kjv)
                != wanted
            ]
        else:
            chosen_signature = tuple(sorted(s for sig in signatures for s in sig))
            disagreeing = [
                i
                for i in others
                if tuple(sorted(signature(i, unit))) != chosen_signature
            ]
        return chosen, disagreeing, None
    if agreeing:
        first = agreeing[0]
        return (
            {
                **first,
                "edits": [],
                "joint": [
                    {"source": i["source"], "entry": i["entry"]} for i in agreeing
                ],
                "nochange": True,
            },
            [],
            None,
        )
    return None, [], None


def corroborating(
    selected: Instruction,
    unit: str,
    instructions: Iterable[Instruction],
    reports: Iterable[Report],
    kjv: Mapping[str, str] | None = None,
) -> list[str]:
    """The witnesses that give the selected instruction's change: instruction
    sources whose edits leave the verse reading the same, and apparatus
    reports attached to the unit whose English contrast equals every one of
    its edits'."""
    found: set[str] = set()
    own = tuple(sorted(signature(selected, unit)))
    wanted = effect(selected["edits"], kjv) if kjv is not None else None
    for i in instructions:
        if i["source"] == selected["source"] or i.get("compatibility") not in {
            "compatible",
            "agrees",
            "superseded",
        }:
            continue
        if not any(a["unit"] == unit for a in i.get("units", [])):
            continue
        mine = [e for e in i["edits"] if unit in e.get("units", [])]
        if (kjv is not None and mine and effect(mine, kjv) == wanted) or tuple(
            sorted(signature(i, unit))
        ) == own:
            found.add(i["source"])
    edits = [e for e in selected["edits"] if unit in e.get("units", [])]
    if edits:
        by_witness: defaultdict[str, list[tuple[tuple[str, ...], tuple[str, ...]]]] = (
            defaultdict(list)
        )
        for r in reports:
            if (
                any(a["unit"] == unit for a in r.get("units", []))
                and (old := r.get("old")) is not None
                and (new := r.get("new")) is not None
            ):
                by_witness[r["witness"]].append(contrast(old, new))
        for witness, contrasts in by_witness.items():
            if all(contrast(e["old"], e["new"]) in contrasts for e in edits):
                found.add(witness)
    return sorted(found)


# Constructions: instructions are judged and executed together, never in parts.

EXECUTABLE = {"compatible", "agrees"}


def touching(x: InstructionEdit, y: InstructionEdit) -> bool:
    """Whether two edits share a unit, or their words overlap or touch. An
    unbound row's stand-in edit has units and no words."""
    if x["ref"] != y["ref"]:
        return False
    if set(x.get("units", [])) & set(y.get("units", [])):
        return True
    if x.get("word_range") is None or y.get("word_range") is None:
        return False
    a, b = x["word_range"]
    c, d = y["word_range"]
    return a <= d and c <= b


def components[T](
    nodes: Sequence[T], linked: Callable[[T, T], bool]
) -> list[list[int]]:
    """Connected components of nodes under a symmetric `linked`."""
    seen: set[int] = set()
    result: list[list[int]] = []
    for n, node in enumerate(nodes):
        if n in seen:
            continue
        stack, part = [n], []
        seen.add(n)
        while stack:
            k = stack.pop()
            part.append(k)
            for m in range(len(nodes)):
                if m not in seen and linked(nodes[k], nodes[m]):
                    seen.add(m)
                    stack.append(m)
        result.append(sorted(part))
    return result


def constructions(
    instructions: list[Instruction],
    kjv: Mapping[str, str],
    checker: Checker | None = None,
    overrides: Iterable[Override] = (),
) -> list[Instruction]:
    """Group, check and choose instructions by construction, book by book.

    1. A source's instructions whose edits share a unit, or whose words overlap
       or touch in a verse, form one group (an instruction spanning verses is
       one node in all of them). A row that did not bind but is attached to a
       unit is a member too. A group executes whole or not at all: a member
       that is not compatible blocks the rest (Rev 2:3, Rev 6:11).
    2. A refusal by the rendering check is provisional: the check runs again
       on the group's combined edits, where a word one instruction removes and
       another restores is a move. Shape refusals remain blocked.
    3. Groups of different sources that touch form one construction. The
       highest-precedence source with an unblocked group executes it. Where
       that source, or a higher one, tried a unit of the construction and
       failed there, the first lower source whose unblocked groups cover every
       unit it or a higher source attempted executes it instead; a unit the
       higher source leaves alone is its decision (Rev 13:16). The others are
       `superseded`: evidence, never a fragment of the text.
    4. An override, of either kind, that touches a construction takes it whole:
       its members are `blocked`, with `displaced_by` (the overrides taking
       it, which should be one) and the status they had (`displaced`), and
       the members that would have executed are marked `displaced_choice`, so
       the override can be compared with them.
    Mutates and returns the instruction rows; adds `group` and `construction`.
    """

    def bound(row: Instruction) -> list[InstructionEdit]:
        return [
            e
            for e in row.get("edits", [])
            if e.get("bind") in {"unique", "already"}
            and "word_range" in e
            and e.get("ref")
        ]

    def attached(row: Instruction) -> list[InstructionEdit]:
        # A failed row still owns every unit it attempted, including those
        # in later verses and those whose edits did not bind. A stand-in has
        # units and no words.
        by_ref: defaultdict[str, list[str]] = defaultdict(list)
        for uid in sorted({u["unit"] for u in row.get("units", [])}):
            by_ref[uid.rsplit("#", 1)[0]].append(uid)
        return [{"ref": ref, "units": units} for ref, units in by_ref.items()]

    # The edits each row takes part in its constructions with, by the row's
    # identity: its bound edits, and an unbound row's stand-ins.
    edits_of: dict[int, list[InstructionEdit]] = {}
    by_book: defaultdict[str, list[Instruction]] = defaultdict(list)
    for row in instructions:
        # A row placed out of scope is about other Greek; it is not part of a
        # construction (a review placed it so, or it has no unit at all).
        if row.get("compatibility") == "out-of-scope":
            continue
        own = edits_of[id(row)] = bound(row)
        if row.get("compatibility") == "unbound":
            own += attached(row)
        if own:
            by_book[own[0]["ref"].split()[0]].append(row)
    rank = {s: n for n, s in enumerate(INSTRUCTION_SOURCES)}
    override_marks: defaultdict[
        str, list[tuple[str, set[str], list[tuple[str, int, int]]]]
    ] = defaultdict(list)
    for o in overrides:
        if not o["unit_ids"]:
            continue  # shared Greek: no instruction to take
        book = o["unit_ids"][0].split()[0]
        override_marks[book].append(
            (
                o["id"],
                set(o["unit_ids"]),
                [(e["ref"], e["start"], e["end"]) for e in o["bound"]],
            )
        )

    def linked(x: Sequence[InstructionEdit], y: Sequence[InstructionEdit]) -> bool:
        return any(touching(a, b) for a in x for b in y)

    def units_of(members: Iterable[Instruction]) -> set[str]:
        return {u for m in members for e in edits_of[id(m)] for u in e.get("units", [])}

    def taken_by(members: Iterable[Instruction]) -> list[str]:
        units = units_of(members)
        marks = [
            (e["ref"], *edit_offsets(kjv[e["ref"]], e))
            for m in members
            for e in edits_of[id(m)]
            if e.get("word_range") is not None
        ]
        return [
            oid
            for oid, ounits, marked in override_marks[book]
            if ounits & units
            or any(
                ref == r and (lo < b and a < hi or lo == hi == a)
                for r, lo, hi in marks
                for ref, a, b in marked
            )
        ]

    def choose(parts: list[list[Instruction]]) -> str | None:
        """The source that executes a construction, or None."""
        usable = [
            members
            for members in parts
            if all(m.get("compatibility") in EXECUTABLE for m in members)
        ]
        if not usable:
            return None
        covered: defaultdict[str, set[str]] = defaultdict(set)
        failed: defaultdict[str, set[str]] = defaultdict(set)
        for members in parts:
            (covered if members in usable else failed)[
                members[0]["source"]
            ] |= units_of(members)
        ranked = sorted(covered, key=lambda s: rank.get(s, 9))
        best = ranked[0]

        def owed(source: str) -> set[str]:
            # A source answers for every unit it or a higher source attempted;
            # a lower source's failure is not its concern.
            return set[str]().union(
                *(
                    units_of(m)
                    for m in parts
                    if rank.get(m[0]["source"], 9) <= rank.get(source, 9)
                )
            )

        higher_failed = any(rank.get(s, 9) < rank.get(best, 9) for s in failed)
        if higher_failed or failed[best]:
            whole = [s for s in ranked if covered[s] >= owed(s)]
            if whole:
                return whole[0]
            # A failed higher source still owns every unit it attempted.
            if higher_failed:
                return None
        return best

    for book, rows in by_book.items():
        groups: list[list[Instruction]] = []
        for source in sorted({r["source"] for r in rows}, key=lambda s: rank.get(s, 9)):
            members = [r for r in rows if r["source"] == source]
            groups += [
                [members[k] for k in part]
                for part in components([edits_of[id(r)] for r in members], linked)
            ]
        for n, members in enumerate(groups):
            name = f"{book}#g{n + 1}"
            for m in members:
                m["group"] = name
            candidates = [
                m
                for m in members
                if m.get("compatibility") == "compatible"
                or m.get("refused_by") == "rendering"
            ]
            if (
                checker is not None
                and candidates
                and (
                    len(candidates) > 1 or any(m.get("refused_by") for m in candidates)
                )
            ):
                combined = [
                    e
                    for m in candidates
                    for e in edits_of[id(m)]
                    if e.get("units") and e.get("word_range") is not None
                ]
                verdicts = [
                    checker.check(e, e["units"], combined)
                    for m in candidates
                    for e in edits_of[id(m)]
                    if e.get("units") and e.get("bind") == "unique"
                ]
                bad = [r for v, r in verdicts if v == "contradicted"]
                for m in candidates:
                    if bad:
                        m["compatibility"], m["compatibility_reason"] = (
                            "incompatible",
                            bad[0],
                        )
                    else:
                        m["compatibility"], m["compatibility_reason"] = (
                            "compatible",
                            None,
                        )
                        m.pop("refused_by", None)
                        m["rendering"] = (
                            "unverified"
                            if any(v == "unverified" for v, _ in verdicts)
                            else "verified"
                        )
            weak = [m for m in members if m.get("compatibility") not in EXECUTABLE]
            if weak and len(members) > 1:
                for m in members:
                    if m.get("compatibility") in EXECUTABLE:
                        m["compatibility"] = "blocked"
                        m["compatibility_reason"] = (
                            f"its construction includes {weak[0]['source']} {weak[0]['entry']}, which is "
                            f"{weak[0].get('compatibility')}; a construction executes whole or not at all"
                        )
        nodes = [[e for m in g for e in edits_of[id(m)]] for g in groups]
        for n, part in enumerate(components(nodes, linked)):
            name = f"{book}#c{n + 1}"
            parts = [groups[k] for k in part]
            everyone = [m for members in parts for m in members]
            for m in everyone:
                m["construction"] = name
            best = choose(parts)
            oids = taken_by(everyone)
            if oids:
                for m in everyone:
                    m["displaced_by"] = oids
                    if m.get("compatibility") in EXECUTABLE:
                        m["displaced"] = m["compatibility"]
                        m["displaced_choice"] = m["source"] == best
                        m["compatibility"] = "blocked"
                        m["compatibility_reason"] = (
                            f"override {' and '.join(oids)} takes this construction"
                        )
                continue
            if best is None:
                for m in everyone:
                    if m.get("compatibility") in EXECUTABLE:
                        m["compatibility"] = "blocked"
                        m["compatibility_reason"] = (
                            "no lower source covers the whole construction after the higher source failed"
                        )
                continue
            for members in parts:
                if members[0]["source"] != best:
                    for m in members:
                        if m.get("compatibility") == "compatible":
                            m["compatibility"] = "superseded"
                            m["compatibility_reason"] = (
                                f"{best}'s wording executes this construction ({name})"
                            )
    return instructions
