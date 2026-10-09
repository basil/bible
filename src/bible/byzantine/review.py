"""The scholarly review packet for the Orthodox Liturgical English Bible (OLEB):
every unit with all its evidence, in markdown.

Nothing here decides anything. For each unit the packet shows the Greek of
both texts, the KJV before and after with its note, every witness in its own
words, the disposition with its tags, a sentence saying how it follows, and
the override if there is one; each book ends with the rows attached to no
unit in its verses that have no unit section.
"""

from __future__ import annotations

import html
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import TypedDict

from bible import scripture, usj
from bible.byzantine import (
    ADDITIONAL,
    BOOKS,
    BOYD_ASV,
    FAA,
    MSB,
    PIERPONT,
    REVISIONS,
    RV,
    TCENT,
    WEB,
    edit,
)
from bible.byzantine import revisers as revisions
from bible.byzantine.appendix import (
    PreparedGreek,
    passage_ranges,
    prepare_greek,
    projected,
    selections,
)
from bible.byzantine.crosswire import edit_offsets, reports_by_unit
from bible.byzantine.crosswire import spans as word_spans
from bible.byzantine.decisions import ref_key
from bible.byzantine.english import verses_of
from bible.byzantine.presentation import (
    anchored,
    clipped,
    diff_spans,
    marked,
    passage_spans,
)
from bible.byzantine.rows import (
    BoydNote,
    Disposition,
    Instruction,
    InstructionEdit,
    Override,
    Report,
    RevisionRow,
    Unit,
)
from bible.byzantine.stages import Context
from bible.byzantine.tags import Tag, score
from bible.scripture import Verse
from bible.usj import Node

NAMES = {
    PIERPONT: "Pierpont",
    ADDITIONAL: "additional file",
    TCENT: "TCENT",
    FAA: "FAA",
    MSB: "MSB",
    WEB: "WEB",
    RV: "RV 1881",
    "asv": "ASV 1901",
    BOYD_ASV: "Boyd ASV 2021",
}
LOOSE_HEADING = "## Attached to no unit"
GREEK_CHANGES = {
    "substitution": "word replacement",
    "inflection": "word-form change",
    "order": "word order",
    "omission": "words omitted",
    "addition": "words added",
    "article": "article change",
    "particle": "particle change",
    "pronoun": "pronoun change",
    "prefix": "prefix change",
    "movable": "optional word ending",
    "word-division": "word division",
    "accent": "accent change",
    "spelling": "spelling change",
    "name-spelling": "name spelling",
    "structural": "verse relocation or omission",
}
GREEK_INVENTORIES = {
    "collation": "Robinson’s collation",
    "diff": "direct TR–RP comparison",
    "tcgnt": "Boyd’s Greek apparatus",
    "placement": "RP2026 verse placement",
    "rp2026-appendix-a": "RP2026 Appendix A",
    "rp2026-printed": "RP2026 printed text",
    "rp2026-apparatus": "RP2026 apparatus",
}
DIFF_LEGEND = (
    "Bold in the OLEB verses marks the full Textus Receptus note lemmas. Contextual diffs use [-removed] "
    "and [+added] inside code spans. Unit comparisons use corresponding Greek and English passages, keeping shared constructions intact. "
    "Greek-only excerpts retain complete phrases without English alignment. Paired Greek and English ellipses mark corresponding omitted intervals; verified moved passages may be excerpted; uncertain correspondence quotes complete verses. "
    "Greek diffs mark wording, punctuation and accents as prepared for the appendix, suppressing case-only differences. Shared words use RP capitalization except every inflection of θεός, κύριος and χριστός (including human uses), which keeps TR capitalization even at verse openings; whole-verse Greek diffs appear once per verse. "
    "Witness diffs show complete touched phrases where their "
    "wording can be located uniquely; … marks clipped context. KJV context shows "
    "an instruction’s proposal; source context shows the reported alternative "
    "in the witness’s own verse wording. Otherwise only the quoted contrast appears. "
    "Unit comparisons start from the corrections-only KJV baseline where needed; correction sections compare original KJV with that baseline. Explicit whole-verse comparisons show all changes and remain complete. The printed appendix gives every entry a TR → RP comparison and adds KJV → OLEB only where the complete English wording changes, including shared-Greek corrections and moved verses, before verse-specific punctuation revisions and with systematic spelling and punctuation applied to both sides, with shared wording once, former readings in upright square brackets, new Greek readings in bold and new English readings in italics. Deleted English and Greek stay upright. Separately labelled apparatus evidence uses the same Greek comparison format. Printed boundary spaces follow ordinary prose spacing outside brackets and bold type in both languages; Markdown marks retain the exact source spaces. "
    "Verse context includes every unit. Witness quotations include excluded "
    "readings; eligibility and attachment labels state their evidential scope."
    " Greek change describes what differs, not whether English must change. "
    "Other Greek editions and RP’s margin help check a witness’s textual basis; "
    "RP2026’s main text remains the target. Recorded in identifies where the "
    "Greek difference is documented, not evidence for English wording."
)

# A witness's row that attaches to units.
type Attached = Instruction | Report | RevisionRow


class Index(TypedDict):
    """Lookups the packet renders from: each unit's instructions, reports and
    revision rows, the rows attached to no unit by verse, the readings by id,
    the prepared verses, the dispositions by unit, and Boyd's Greek notes."""

    instructions_at: dict[str, list[Instruction]]
    reports_at: dict[str, list[Report]]
    revisions_at: dict[str, list[RevisionRow]]
    loose_in_verse: defaultdict[str, list[str]]
    overrides: dict[str, Override]
    prepared: dict[str, Verse]
    corrected: dict[str, Verse]
    rows: dict[str, Disposition]
    tcgnt: dict[int, BoydNote]


def esc(text: object) -> str:
    """Markdown-safe inline text: pipes and leading # neutralized, newlines joined."""
    return " ".join(str(text).replace("|", "\\|").split())


def marked_readings(before: str, after: str, *, verse: bool = False) -> tuple[str, str]:
    """Two readable texts: removed text marked only before, added only after."""
    left: list[str] = []
    right: list[str] = []
    for kind, value in diff_spans(before, after):
        # Leave spaces outside emphasis so Markdown renders every mark.
        marked = value
        if kind != "equal" and value.strip():
            lo = len(value) - len(value.lstrip())
            hi = len(value.rstrip())
            if verse:
                words = list(re.finditer(r"\w", value))
                if words:
                    lo, hi = words[0].start(), words[-1].end()
                else:
                    lo = hi
            if lo < hi:
                marked = value[:lo] + "**" + esc(value[lo:hi]) + "**" + value[hi:]
        elif kind == "equal":
            marked = value.replace("|", "\\|")
        if kind != "insert":
            left.append(marked)
        if kind != "delete":
            right.append(marked)
    return "".join(left) or "∅", "".join(right) or "∅"


def inline_change(before: str, after: str) -> str:
    """One contextual diff for a witness phrase, with shared wording once."""
    before, after = scripture.plain(before), scripture.plain(after)
    return esc(before) if before == after else inline_diff(before, after)


def witness_excerpt(
    before: str | None,
    after: str | None,
    text: str | None = None,
    *,
    reading: str = "old",
    bounds: tuple[int, int] | None = None,
    label: str = "source context",
) -> str:
    """Clip genuine verse context around a located witness contrast.

    Substitute only the reported reading, not other differences in the verse.
    Ambiguous/absent phrases stay quotations; modern witnesses never borrow
    surrounding KJV wording. Explicit bounds preserve repeated bound edits.
    """
    old, new = scripture.plain(before or ""), scripture.plain(after or "")
    anchor = old if reading == "old" else new
    # A bound insertion has no words to find, but its point is located.
    located = bounds is not None and bounds[0] == bounds[1]
    if text is None or not anchor and not located:
        return "quoted contrast: " + inline_change(old, new)
    if bounds is None:
        hits = (
            list(re.finditer(r"(?<!\w)" + re.escape(anchor) + r"(?!\w)", text))
            if anchor
            else []
        )
        if len(hits) != 1:
            return "quoted contrast: " + inline_change(old, new)
        lo, hi = hits[0].span()
    else:
        lo, hi = bounds
        if scripture.plain(text[lo:hi]) != anchor:
            return "quoted contrast: " + inline_change(old, new)
    return label + ": " + context_excerpt(old, new, text, (lo, hi))


def context_excerpt(
    old: str, new: str, text: str, bounds: Sequence[int], *, greek: bool = False
) -> str:
    """Show complete touched phrases; diff only the declared local readings."""
    lo, hi = bounds
    prefix, suffix = text[:lo], text[hi:]
    old, new = scripture.plain(old), scripture.plain(new)
    if not old and new:
        if prefix and not prefix[-1].isspace():
            new = " " + new
        if suffix and re.match(r"\w", suffix):
            new += " "
    elif old and not new and prefix[-1:].isspace() and suffix[:1].isspace():
        old += suffix[0]
        suffix = suffix[1:]
    return diff_markup(
        clipped(
            [("equal", prefix), *diff_spans(old, new, greek=greek), ("equal", suffix)]
        )
    )


def inline_diff(before: str, after: str) -> str:
    """The contextual difflib comparison, with explicit removal/addition marks."""
    before, after = scripture.plain(before), scripture.plain(after)
    if before == after:
        return "unchanged"
    return diff_markup(diff_spans(before, after))


def diff_markup(spans: Iterable[tuple[str, str]]) -> str:
    """Render difflib spans with one shared notation for every comparison."""
    value = marked(list(spans))
    delimiter = "`" * (
        1 + max((len(m[0]) for m in re.finditer(r"`+", value)), default=0)
    )
    return f"{delimiter} {value} {delimiter}"


def verse_comparison(
    before: str,
    after: str,
    before_label: str,
    after_label: str,
    *,
    after_verse: Verse | None = None,
    anchors: Sequence[tuple[int, int, int, int]] = (),
) -> list[str]:
    """Contextual source-to-target diff and readable finished verse, in two rows."""
    before, after = scripture.plain(before), scripture.plain(after)
    if after_verse is not None:
        right = lemma_reading(after_verse)
    else:
        right = marked_readings(before, after, verse=True)[1]
    if before == after:
        return [
            f"English whole verse · {before_label} = {after_label} · unchanged: {right}",
            "",
        ]
    return [
        f"English whole verse · {before_label} → {after_label}: "
        + diff_markup(anchored(before, after, anchors)),
        "",
        f"{after_label} (whole verse): {right}  ",
        "",
    ]


def unit_greek_excerpt(
    unit: Unit,
    context: Context,
    passages: Passages,
) -> str:
    """Quote the shared passage containing this unit."""
    texts, selected, _ = passages
    ranges = passage_ranges(
        context, unit["ref"], unit["target_ref"], texts[0], texts[1]
    )
    return " / ".join(
        diff_markup(passage_spans(texts, p, 0, ranges, greek=True)) for p in selected
    )


Passages = tuple[
    tuple[str, ...],
    tuple[tuple[tuple[int, int], ...], ...],
    tuple[tuple[int, int, int, int], ...],
]


def unit_passages(
    unit: Unit,
    context: Context,
    prepared: PreparedGreek,
    prepared_verses: Mapping[str, Verse],
    corrected: Mapping[str, Verse] | None = None,
) -> Passages:
    tr, rp, _ = prepared
    ref, target = unit["ref"], unit["target_ref"]
    verse = prepared_verses.get(target)
    texts, selected, english = selections(
        context,
        ref,
        target,
        " ".join(tr.get(ref, [])),
        " ".join(rp.get(target, [])),
        scripture.plain(
            corrected[ref].text if corrected is not None else context["kjv"][ref]
        ),
        scripture.plain(verse.text if verse else ""),
        prepared_verses,
    )
    offsets = [m.start() for m in re.finditer(r"\S+", texts[0])] + [len(texts[0])]
    a, b = projected(context, "tr", ref, unit["tr_range"])
    lo, hi = offsets[a], offsets[b]
    local = tuple(p for p in selected if p[0][0] <= lo <= hi <= p[0][1])
    return texts, local or selected, english


def greek_verses(
    context: Context,
    ref: str,
    prepared: PreparedGreek,
    target: str | None = None,
) -> list[str]:
    """One prepared verse diff, anchored to the ledger's Greek units.

    Diff each unit and its intervening context separately so repeated words
    cannot pull an alignment across an unrelated part of the verse. Structural
    units describe relocation; the ordinary units carry its wording differences.
    """
    target = target or ref
    tr, rp, _ = prepared
    left = " ".join(tr.get(ref, []))
    right = " ".join(rp.get(target, []))
    ranges = passage_ranges(context, ref, target, left, right)
    spans = anchored(left, right, ranges, greek=True)
    return [
        f"Greek whole verse · TR {ref} → RP2026 {target}: " + diff_markup(spans) + "  ",
        "",
    ]


def note_text(note: Node | None) -> str:
    return (
        " ".join(
            usj.text_of(n["content"]) if isinstance(n, dict) else n
            for n in note["content"]
        ).strip()
        if note
        else ""
    )


def edition_notes(verse: Verse) -> list[str]:
    return list(
        dict.fromkeys(
            note_text(n) for _, n in verse.notes if n.get("category") == "edition"
        )
    )


def lemma_reading(verse: Verse) -> str:
    """Highlight the printed note lemmas in the readable finished verse."""
    text = scripture.plain(verse.text)
    ranges: list[tuple[int, int]] = []
    for offset, note in verse.notes:
        if note.get("category") != "edition":
            continue
        field = next(
            (
                n
                for n in note["content"]
                if isinstance(n, dict) and n.get("marker") == "fq"
            ),
            None,
        )
        if field is None:
            continue
        lemma = scripture.plain(usj.text_of(field["content"])).removesuffix(":")
        matches = (
            list(re.finditer(r"(?<!\w)" + re.escape(lemma) + r"(?!\w)", text))
            if lemma
            else []
        )
        if matches:
            at = len(scripture.plain(verse.text[:offset]))
            match = min(matches, key=lambda m: abs(m.end() - at))
            ranges.append(match.span())
    merged: list[tuple[int, int]] = []
    for lo, hi in sorted(set(ranges)):
        if merged and lo < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    for lo, hi in reversed(merged):
        text = text[:lo] + "**" + text[lo:hi] + "**" + text[hi:]
    return esc(text) or "∅"


def attachment_scope(row: Attached, uid: str) -> str:
    scopes = {a.get("scope", "unit") for a in row.get("units", []) if a["unit"] == uid}
    if "constituent" in scopes:
        return "part of this unit"
    if "relocation" in scopes:
        return "relocation"
    return "at unit"


def revision_status(
    name: str,
    unit: Unit,
    context: Context,
    index: Index,
    rows: Sequence[RevisionRow],
) -> str:
    """Keep eligibility, an attached contrast and corroboration distinct."""
    if unit["id"] in context["revision_admitted"][name]:
        return "eligible reading; " + (
            "English contrast attached" if rows else "no English contrast attached"
        )
    if name == RV:
        side = revisions.wh_side(unit, index["tcgnt"])
        reason = {
            "TR": "Westcott–Hort reads with TR",
            "other": "Westcott–Hort reads with neither TR nor RP",
        }.get(side or "", "Westcott–Hort agreement with RP is not established")
    else:
        reason = "RP2026 Appendix A changes this verse from Boyd’s RP2018 target"
    return "not admitted at this unit: " + reason


def patriarchal_status(unit: Unit, index: Index) -> str:
    """Describe ANT's agreement with the target from the attached apparatus.

    Boyd lists departures from RP; an unlisted ANT reading agrees with RP.
    A constituent note establishes agreement only for its recorded part.
    """
    sides: set[str] = set()
    complete = False
    for found in unit["inventories"]:
        if found["inventory"] != "tcgnt":
            continue
        note = index["tcgnt"][found["entry"]]
        variants = [v for v in note["variants"] if "ANT" in v["sigla"]]
        sides.add(
            "RP"
            if not variants
            else (
                "TR"
                if any({"TR", "SCR"} & set(v["sigla"]) for v in variants)
                else "other"
            )
        )
        complete |= found["scope"] == "unit"
    if "TR" in sides or unit.get("patriarchal"):
        return "differs from RP2026 (TR reading)"
    if "other" in sides:
        return "differs from RP2026 (other reading)"
    if sides:
        return "agrees with RP2026" + (" in recorded part" if not complete else "")
    return "RP2026 agreement unknown"


def kjv_bounds(kjv: str, row: InstructionEdit | RevisionRow) -> tuple[int, int]:
    """A bound contrast's KJV span by word offsets, including its insertion side."""
    lo, hi = edit_offsets(kjv, row)
    at = row["word_range"][0]
    if not row["old"] and row.get("side") == "after" and at:
        lo = hi = word_spans(kjv)[at - 1][2]
    return lo, hi


def revision_excerpt(row: RevisionRow, kjv: str) -> str:
    """Locate the contrast by word offsets, including its insertion side."""
    return context_excerpt(row["old"], row["new"], kjv, kjv_bounds(kjv, row))


def source_plain(markup: str | None) -> str | None:
    """A witness's source passage markup as its plain verse wording."""
    return html.unescape(re.sub(r"<[^>]*>", "", markup)) if markup else markup


def witness_lines(unit: Unit, context: Context, index: Index) -> list[str]:
    """One line per witness that speaks to the unit, in its own words."""
    uid = unit["id"]
    lines: list[str] = []
    for i in index["instructions_at"][uid]:
        name = NAMES.get(i["source"], i["source"])
        bits = [f"{name} {i['entry']}"]
        if i["source"] == PIERPONT:
            w = i.get("weight") or {}
            bits.append(
                f"weight {w.get('raw', '?')}"
                + (f" ({i['strength']})" if i.get("strength") else "")
            )
            berry = i.get("berry") or {}
            if berry.get("raw"):
                bits.append(f"Berry {berry['raw']}")
        bits.append(f"bound {i.get('bind')}")
        bits.append("attachment: " + attachment_scope(i, uid))
        bits.append(
            i.get("compatibility", "?")
            + (
                f" ({i['compatibility_reason']})"
                if i.get("compatibility_reason")
                and i.get("compatibility") not in {"compatible"}
                else ""
            )
        )
        if i.get("rendering"):
            bits.append(
                "lexical support found"
                if i["rendering"] == "verified"
                else f"lexical support: {i['rendering']}"
            )
        if i.get("method") == "hand":
            bits.append("placed by hand")
        proposals: list[str] = []
        for e in i.get("edits", []):
            at = e.get("ref")
            text = context["kjv"].get(at) if at is not None else None
            bounds = (
                kjv_bounds(text, e)
                if text is not None and e.get("word_range") is not None
                else None
            )
            proposals.append(
                witness_excerpt(
                    e["old"],
                    e["new"],
                    text,
                    bounds=bounds,
                    label="KJV context (proposal)",
                )
            )
        contrasts = "; ".join(proposals)
        lines.append(
            f"- {esc(bits[0])}: "
            + (contrasts + " · " if contrasts else "")
            + esc(" · ".join(bits[1:]))
            + f"  \n  `{esc(i['raw'])}`"
        )
    for r in index["reports_at"][uid]:
        name = NAMES.get(r["witness"], r["witness"])
        # Boyd's passages are escaped USX markup; compare their plain wording.
        source_text = source_plain(
            r.get("source_main_passages", {}).get(r.get("target_ref", r["ref"]))
        ) or r.get("source_main_text")
        reading = "new"
        if r["witness"] == FAA:
            faa = context["faa_rows"].get(r["ref"], {})
            reading = "new" if r.get("new") else "old"
            source_text = (
                faa.get("RP_English") if reading == "new" else faa.get("TR_English")
            )
        contrast = (
            witness_excerpt(r["old"], r["new"], source_text, reading=reading)
            if r.get("old") is not None
            and r.get("new") is not None
            and (r["old"] or r["new"])
            else "contrast not extracted"
        )
        extra = ""
        if r["witness"] == FAA and r.get("greek_group"):
            faa = context["faa_rows"].get(r["ref"], {})
            g = r["greek_group"] - 1
            try:
                label = (
                    "ordered Greek pairing" if r.get("method") == "hand" else "Greek"
                )
                extra = f" — {label} {esc(faa['TR_Greek_groups'][g]['reading'])} / {esc(faa['RP_Greek_groups'][g]['reading'])}"
                if r.get("method") == "hand" and r.get("placement"):
                    extra += f" · English placement: {esc(r['placement'])}"
            except (KeyError, IndexError):
                extra = ""
        method = (
            f" ({r.get('method')})"
            if r.get("method") and r.get("method") != "greek"
            else ""
        )
        raw = f"  \n  `{esc(r['raw'])}`" if r.get("raw") else ""
        lines.append(
            f"- {name} {esc(r['entry'])}{method}: {contrast}{extra} · attachment: {attachment_scope(r, uid)}{raw}"
        )
    for name in REVISIONS:
        verse = context["texts"][name].get(unit["ref"])
        rows = [row for row in index["revisions_at"][uid] if row["witness"] == name]
        if not verse:
            continue
        revised: list[str] = []
        for row in rows:
            scope = attachment_scope(row, uid)
            origin = {"kept": "ASV inherited", "revised": "includes Boyd revision"}.get(
                row.get("reviser") or "", ""
            )
            kjv = context["kjv"][row["ref"]]
            excerpt = revision_excerpt(row, kjv)
            revised.append(
                "KJV contrast "
                + scope
                + ": "
                + excerpt
                + (f" ({origin})" if origin else "")
            )
        details = "; ".join(revised)
        if name == BOYD_ASV and unit["ref"] in context["texts"]["asv"]:
            base = context["texts"]["asv"][unit["ref"]]
            reading = "ASV 1901 → Boyd ASV 2021 (whole verse): " + diff_markup(
                diff_spans(scripture.plain(base), scripture.plain(verse))
            )
        else:
            reading = esc(verse)
        lines.append(
            f"- {NAMES[name]} ({revision_status(name, unit, context, index, rows)}): {reading}"
            + (f"  \n  {details}" if details else "")
        )
    return lines


def calculus(row: Disposition, unit: Unit, index: Index) -> str:
    """One or two sentences saying how the disposition follows."""
    d = row["disposition"]
    tags = set(row["tags"])
    if d == "override":
        base = f"An override ({row['override']}, {row['kind']}) settles the unit"
        if Tag.EV_INSTRUCTION_REFUSED in tags:
            s = row.get("refused_instruction", {})
            source = s.get("source")
            name = NAMES.get(source, source) if source is not None else None
            base += f", departing from {name} {s.get('entry')}"
        if row.get("redundant"):
            base += (
                "; no apparatus report, instruction, revision row or revision alarm attaches to its units, so without it they stay unchanged and it could be removed"
                if row["kind"] == "nochange"
                else "; it has the same effect as the selected instruction and could be removed"
            )
        return base + "."
    if d == "structural":
        return (
            "A whole-verse difference, carried out from the Greek texts with one note."
        )
    if d == "conflict":
        return f"Instructions from the deciding source disagree ({row.get('reason')}); their edits do not execute and the English stands."
    if d == "witnessed":
        source, entry, *_ = row["basis"].split(":")
        if row["action"] == "nochange":
            parts = [
                f"{NAMES.get(source)} {entry} says the KJV already reads with the Majority here"
            ]
        else:
            parts = [
                f"{NAMES.get(source)} {entry} binds uniquely to the pinned KJV and fits the unit's Greek"
            ]
        support = row.get("corroborated_by", [])
        if support:
            parts.append("agreeing: " + ", ".join(NAMES.get(w, w) for w in support))
        if row.get("disagreeing"):
            parts.append(
                "differing: "
                + ", ".join(
                    f"{NAMES.get(x['source'])} {x['entry']}" for x in row["disagreeing"]
                )
            )
        if Tag.EV_SINGLE_WITNESS in tags:
            parts.append("no other witness gives this change")
        if Tag.EV_RENDERING_UNVERIFIED in tags:
            parts.append(
                "no Greek in the verse is tagged as rendering the changed words, so check the English against RP2026 by hand"
            )
        return "; ".join(parts) + "."
    if d == "neutral":
        return f"The difference is {unit['class']} only, and no witness reports it: the English cannot show it."
    bits = []
    if Tag.EV_TCENT_REPORTS in tags:
        bits.append(
            "Boyd's apparatus reports a translatable difference, but no KJV-worded instruction binds here: an override is wanted"
        )
    elif Tag.EV_HYPER_LITERAL_ONLY in tags:
        bits.append(
            "the apparatus reports come only from hyper-literal lists; no applicable KJV-worded change has been established"
        )
    elif row["witnesses"] or index["instructions_at"][unit["id"]]:
        bits.append(
            "the instructions here do not bind, attach or fit the unit (see above)"
        )
    elif index["revisions_at"][unit["id"]]:
        bits.append("no applicable KJV-worded instruction executes")
    else:
        bits.append("no attached witness reports an English difference")
    if index["revisions_at"][unit["id"]]:
        bits.append("attached revision contrasts remain for review")
    if Tag.EV_REVISION_ALARM in tags:
        bits.append("yet both revisions lack the KJV's words for it")
    text = "; ".join(bits)
    return text[:1].upper() + text[1:] + "."


def unit_english_lines(
    unit: Unit,
    row: Disposition,
    context: Context,
    index: Index,
    passages: Passages,
) -> list[str]:
    """The executed English for this unit, preserving shared constructions."""
    baseline = (
        "Corrected KJV"
        if index["corrected"][unit["ref"]].text != context["kjv"][unit["ref"]]
        else "KJV"
    )
    covered = row.get("covered_by")
    owner = index["rows"].get(covered, row) if covered is not None else row
    shared = bool(row.get("covered_by") or Tag.EV_MULTI_UNIT in owner["tags"])
    label = "English for shared construction" if shared else "English at this unit"
    if row.get("covered_by"):
        label += f" (executed with {row['covered_by']})"
    if not owner.get("edits") and row["action"] not in {"move", "omit"}:
        contrast = "unchanged" + (
            " (executor refused)" if row["action"] == "refused" else ""
        )
        return [
            f"{label} · {baseline} {unit['ref']} → OLEB {unit['target_ref']}: {contrast}"
        ]
    texts, selected, anchors = passages
    comparisons = [passage_spans(texts, p, 2, anchors) for p in selected]
    changed = [
        diff_markup(spans)
        for spans in comparisons
        if any(k != "equal" for k, _ in spans)
    ]
    contrast = (
        " / ".join(changed)
        if changed
        else "unchanged" + (" (executor refused)" if row["action"] == "refused" else "")
    )
    return [
        f"{label} · {baseline} {unit['ref']} → OLEB {unit['target_ref']}: {contrast}"
    ]


def section(
    unit: Unit,
    row: Disposition,
    context: Context,
    index: Index,
    *,
    greek_context: Mapping[str, str] | None = None,
    prepared: PreparedGreek,
) -> list[str]:
    uid = unit["id"]
    kjv = context["kjv"]
    ref, target = unit["ref"], unit["target_ref"]
    lines = [
        f"## {uid} · {row['disposition']}"
        + (f" · {row['action']}" if row["action"] not in {"edit", "nochange"} else "")
        + f" · score {score(row)}",
        "",
    ]
    hf = {
        "RP": "agrees with RP2026",
        "TR": "agrees with TR",
        "other": "other or mixed reading",
        "unknown": "agreement unknown",
    }.get(unit.get("hf") or "", "agreement unknown")
    flags = [
        f"Hodges–Farstad: {hf}",
        "RP margin: "
        + (
            "includes TR reading"
            if unit.get("rp_alternate")
            else "TR reading not recorded"
        ),
        "Patriarchal: " + patriarchal_status(unit, index),
    ]
    recorded = ", ".join(
        GREEK_INVENTORIES.get(name, name) for name in unit.get("found_in", [])
    )
    lines.append(
        f"Greek change: {GREEK_CHANGES.get(unit['class'], unit['class'])} · "
        + " · ".join(flags)
        + (f" · Recorded in: {recorded}" if recorded else "")
    )
    lines.append("")
    passages = unit_passages(
        unit, context, prepared, index["prepared"], index["corrected"]
    )
    greek = "Greek at this unit · TR → RP2026: " + unit_greek_excerpt(
        unit, context, passages=passages
    )
    if unit["id"] in prepared[2]:
        old, new = unit["tr_accented"], unit["rp_accented"]
        greek += f" · apparatus accent evidence: {esc(old)} → {esc(new)}"
    addresses = context["tr_alignment"].addresses[ref]
    source_refs = list(
        dict.fromkeys(
            addresses[slice(*projected(context, "tr", ref, unit["tr_range"]))]
        )
    )
    if source_refs and source_refs != [ref]:
        greek += " · Scrivener source: " + ", ".join(source_refs)
    lines.append(greek)
    lines.extend(unit_english_lines(unit, row, context, index, passages))
    lines.append("")
    if greek_context:
        lines.append(
            f"Greek whole verse · TR {ref} → RP2026 {target}: see {greek_context['unit']}"
        )
    else:
        lines.extend(
            line for line in greek_verses(context, ref, prepared, target) if line
        )
    after = index["prepared"].get(target)
    lines.extend(
        verse_comparison(
            kjv[ref],
            after.text if after else "",
            f"KJV {ref}",
            (
                f"OLEB {target} (all changes)"
                if index["corrected"][ref].text != context["kjv"][ref]
                else f"OLEB {target}"
            ),
            after_verse=after,
            anchors=passages[2] if index["corrected"][ref].text == kjv[ref] else (),
        )[:-1]
    )
    notes = (
        edition_notes(after)
        if after
        else ([note_text(row["note"])] if row.get("note") else [])
    )
    if notes:
        lines.append("⁺ " + "; ".join(esc(n) for n in notes))
    if row["action"] == "refused":
        lines.append(f"Executor refused: {esc(row['reasons'][0])}")
    # Hard breaks keep comparison rows readable without blank paragraphs.
    lines[2:] = [line.rstrip() + "  " if line else "" for line in lines[2:]]
    lines.append("")
    lines.append("Witness quotations · attachment and eligibility")
    witnesses = witness_lines(unit, context, index)
    lines.extend(witnesses or ["- none attached to this unit"])
    loose = index["loose_in_verse"][ref]
    if loose:
        lines.append("")
        lines.append("Also in this verse, attached to no unit")
        lines.extend(loose)
    lines.append("")
    basis = row.get("basis") or row.get("override") or ""
    lines.append(
        f"Disposition {row['disposition']} · {row['action']}"
        + (f" · basis {basis}" if basis else "")
    )
    lines.append("Tags " + " ".join(f"`{t}`" for t in row["tags"]))
    lines.append("Calculus " + esc(calculus(row, unit, index)))
    for flag in row.get("flags", []):
        lines.append(f"Flag {esc(flag)}")
    if row.get("alarm_phrases"):
        lines.append(
            "Revision alarm (literal word absence, independent of admission): KJV words missing from both revisions: "
            + "; ".join(esc(p) for p in row["alarm_phrases"])
        )
    if row["disposition"] == "override":
        lines += ["", *override_lines(index["overrides"][row["override"]], ref)]
    elif row["disposition"] in {"silent", "conflict"} and index["revisions_at"][uid]:
        contrasts = {
            f"{NAMES[r['witness']]} · {attachment_scope(r, uid)}: {inline_change(r['old'], r['new'])}"
            for r in index["revisions_at"][uid]
        }
        lines.append(
            "Attached revision contrasts (not executed): "
            + "; ".join(sorted(contrasts))
        )
    lines.append("")
    for pos, line in enumerate(lines):
        if line.startswith(
            (
                "Disposition ",
                "Tags ",
                "Calculus ",
                "Override ",
                "Flag ",
                "Revision alarm",
            )
        ):
            lines[pos] = line + "  "
    return lines


def override_lines(o: Override, ref: str) -> list[str]:
    """An override as the editor wrote it, its evidence ticked as checked."""
    lines = [
        " · ".join(
            [f"Override {o['id']}", o["kind"]]
            + [" ".join(f"`{t}`" for t in o["tags"])] * bool(o["tags"])
        )
    ]
    for e in o.get("edits", []):
        lines.append(
            f"- {esc(e['from']) or '∅'} → {esc(e['to']) or '∅'}"
            + (f" ({e['ref']})" if e["ref"] != ref else "")
            + (f" · shared Greek {esc(e['greek'])}" if "greek" in e else "")
        )
    lines.append(f"- why: {esc(o['why'])}")
    for w, item in o.get("evidence", {}).items():
        where = item.get("entry", item.get("ref"))
        if w == FAA and item.get("field") == "source_notes":
            where = f"{where} verse note"
        lines.append(f"- {NAMES.get(w, w)} {esc(where)}: “{esc(item['quote'])}” ✓")
    return lines


def rendering_section(
    row: Disposition, context: Context, index: Index, prepared: PreparedGreek
) -> list[str]:
    """An override of the English where the TR and RP2026 share the Greek."""
    ref = row["ref"]
    target = context["structure"].rp_ref(ref)
    o = index["overrides"][row["override"]]
    corrected = index["corrected"][ref]
    after = index["prepared"].get(target)
    override = override_lines(o, ref)
    return [
        f"### {ref}",
        "",
        *greek_verses(context, ref, prepared, target),
        *verse_comparison(
            context["kjv"][ref],
            corrected.text,
            f"KJV {ref}",
            f"Corrected KJV {ref}",
        ),
        *verse_comparison(
            context["kjv"][ref],
            after.text if after else "",
            f"KJV {ref}",
            f"OLEB {target} (all changes)",
            after_verse=after,
        ),
        override[0] + "  ",
        *override[1:],
        "",
    ]


def build_index(context: Context) -> Index:
    """Lookups the packet renders from."""
    corrected, rows = edit.execute(
        context["documents"],
        [r for r in context["dispositions"] if r["disposition"] == "shared"],
        list(context["documents"]),
    )
    if any(r.get("execution") != "applied" for r in rows):
        raise ValueError("Review corrections-only baseline could not be executed")
    index: Index = {
        "instructions_at": reports_by_unit(context["instructions"]),
        "reports_at": reports_by_unit(context["reports"]),
        "revisions_at": reports_by_unit(context["revision_rows"]),
        "loose_in_verse": defaultdict(list),
        "overrides": {o["id"]: o for o in context["overrides"]},
        "prepared": verses_of(context["prepared"]),
        "corrected": verses_of(corrected),
        "rows": {r["unit"]: r for r in context["dispositions"]},
        "tcgnt": {n["entry"]: n for n in context["tcgnt"]},
    }
    for i in context["instructions"]:
        if i.get("scope") == "verse":
            for ref in i.get("refs", []):
                index["loose_in_verse"][ref].append(
                    f"- {NAMES.get(i['source'], i['source'])} {i['entry']} · bound {i.get('bind')} · {i.get('compatibility')}: `{esc(i['raw'])}`"
                )
    for r in context["reports"]:
        if r.get("scope") == "verse":
            extracted = (
                r.get("old") is not None
                and r.get("new") is not None
                and (r["old"] or r["new"])
            )
            contrast = (
                f"{esc(r['old']) or '∅'} → {esc(r['new']) or '∅'}"
                if extracted
                else "contrast not extracted"
            )
            index["loose_in_verse"][r["ref"]].append(
                f"- {NAMES.get(r['witness'])} {esc(r['entry'])}: {contrast}"
                + (f" ({esc(r.get('reason'))})" if r.get("reason") else "")
            )
    return index


def packets(context: Context) -> dict[str, str]:
    """One review file per book, by its name: every Scrivener-RP2026 unit
    of the book with all its evidence."""
    index = build_index(context)
    prepared = prepare_greek(context)
    tr, rp, _ = prepared
    rows = index["rows"]
    by_book: defaultdict[str, list[Unit]] = defaultdict(list)
    for u in context["units"]:
        by_book[u["ref"].split()[0]].append(u)
    loose_by_book: defaultdict[str, list[str]] = defaultdict(list)
    for ref in sorted(
        (ref for ref, loose in index["loose_in_verse"].items() if loose), key=ref_key
    ):
        loose_by_book[ref.split()[0]].append(ref)
    files: dict[str, str] = {}
    for book in BOOKS:
        lines = [
            f"# {book}",
            "",
            "Every Scrivener-RP2026 unit in the book. Neutral units are tabled first; other units keep the Greek, verse comparisons, witnesses and disposition together. The corrections of shared Greek follow them. The tag legend is in src/bible/byzantine/tags.py.",
            "",
        ]
        lines += [
            DIFF_LEGEND,
            "",
            "Citation brackets in a reading's evidence record the source's supplied-word markup; a tick verifies quotation accuracy.",
            "",
        ]
        neutral = [
            u for u in by_book[book] if rows[u["id"]]["disposition"] == "neutral"
        ]
        if neutral:
            lines += [
                "## Neutral units",
                "",
                "| Unit | Class | TR → RP | Score | Evidence |",
                "| --- | --- | --- | --- | --- |",
            ]
            lines += [
                f"| {u['id']} | {u['class']} | {esc(' '.join(tr[u['ref']][slice(*projected(context, "tr", u["ref"], u["tr_range"]))]) or '∅')} → {esc(' '.join(rp[u['target_ref']][slice(*projected(context, "rp", u["target_ref"], u["rp_range"]))]) or '∅')} | {score(rows[u['id']])} | {' '.join('`' + t + '`' for t in rows[u['id']]['tags'] if t.startswith('ev:'))} |"
                for u in neutral
            ]
            lines.append("")
        greek_contexts: dict[tuple[str, str], dict[str, str]] = {}
        for u in by_book[book]:
            row = rows[u["id"]]
            if row["disposition"] == "neutral":
                continue
            pair = (u["ref"], u["target_ref"])
            lines += section(
                u,
                row,
                context,
                index,
                greek_context=greek_contexts.get(pair),
                prepared=prepared,
            )
            greek_contexts.setdefault(pair, {"unit": u["id"]})
        corrections = [
            r
            for r in context["dispositions"]
            if r["disposition"] == "shared" and r["ref"].split()[0] == book
        ]
        if corrections:
            lines += [
                "## Corrections of shared Greek",
                "",
                "The editor's corrections of the English where the TR and RP2026 have the same Greek, without TR notes.",
                "",
            ]
            for row in corrections:
                lines += rendering_section(row, context, index, prepared)
        # A section shows its verse's loose rows; list the rest after them.
        sectioned = {
            u["ref"] for u in by_book[book] if rows[u["id"]]["disposition"] != "neutral"
        }
        unsectioned = [ref for ref in loose_by_book[book] if ref not in sectioned]
        if unsectioned:
            lines += [
                LOOSE_HEADING,
                "",
                "Instructions and reports in verses with no unit section above, attached to no unit.",
                "",
            ]
            for ref in unsectioned:
                lines += [f"### {ref}", "", *index["loose_in_verse"][ref], ""]
        files[f"{book}.md"] = "\n".join(lines) + "\n"
    return files


def reading(value: object) -> str:
    """An inventory row's Greek, however the inventory gives it: a list of
    words, a list of readings with their sigla, or a string."""
    if isinstance(value, list):
        return (
            " ".join(v["reading"] if isinstance(v, dict) else str(v) for v in value)
            or "∅"
        )
    return str(value) if value else "∅"


def summary(context: Context) -> str:
    """The reconciliation in figures, for the review: how many units (and
    corrections of shared Greek) of each disposition, how each witness's rows
    were read, the inventory rows that match no unit, and the verses the
    CrossWire bridge could not align."""
    c = Counter
    lines = ["# The Byzantine New Testament", ""]
    rows = context["dispositions"]
    lines += ["## Dispositions", "", "| Disposition | Rows |", "| --- | --- |"]
    lines += [
        f"| {d} | {n} |" for d, n in sorted(c(r["disposition"] for r in rows).items())
    ]
    lines += ["", "| Action | Rows |", "| --- | --- |"]
    lines += [f"| {a} | {n} |" for a, n in sorted(c(r["action"] for r in rows).items())]
    lines += [
        "",
        f"Rows executed: {sum(1 for r in rows if r.get('execution') == 'applied')}; refused: {sum(1 for r in rows if r.get('execution') == 'refused')}.",
        "",
    ]
    lines += ["## Witnesses", "", "| Witness | Rows | Scope |", "| --- | --- | --- |"]
    witnesses: defaultdict[str, list[str | None]] = defaultdict(list)
    for r in context["reports"]:
        witnesses[r["witness"]].append(r.get("scope"))
    for i in context["instructions"]:
        witnesses[i["source"]].append(i.get("scope"))
    for name, scopes in sorted(witnesses.items()):
        lines.append(
            f"| {NAMES.get(name, name)} | {len(scopes)} | {', '.join(f'{k}: {n}' for k, n in sorted(c(scopes).items(), key=lambda kv: str(kv[0])))} |"
        )
    lines += [
        "",
        "## Invariants",
        "",
        *(f"- {k}: {v}" for k, v in context["invariants"].items()),
        "",
    ]
    lines += [
        "## Finished verses to read",
        "",
        *(
            f"- {ref}: {'; '.join(problems)}"
            for ref, problems in sorted(
                context["finished"].items(), key=lambda kv: ref_key(kv[0])
            )
        ),
        "",
    ]
    lines += ["## Inventory rows matching no unit", ""]
    lines += [
        f"- {r['inventory']} {r.get('entry')} at {r.get('target_ref')}: {esc(reading(r.get('tr')))} → {esc(reading(r.get('rp')))}"
        for r in context["unmatched"]
    ] or ["- none"]
    lines += ["", "## Verses the CrossWire bridge could not align", ""]
    lines += [f"- {ref}" for ref in context["bridge_failures"]] or ["- none"]
    lines += ["", "## Pierpont's rows", "", "| Role | Rows |", "| --- | --- |"]
    lines += [
        f"| {role} | {n} |"
        for role, n in sorted(
            c(r["role"] for r in context["pierpont_inventory"]["rows"]).items()
        )
    ]
    return "\n".join(lines) + "\n"
