"""Lossless comparison spans and punctuation-delimited presentation context."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from difflib import SequenceMatcher

# All case/number forms, including vocatives and duals. Diacritics are
# ignored only when identifying these families, never when matching readings.
TR_CASE_FORMS = frozenset(
    "θεος θεου θεω θεον θεε θεοι θεων θεοις θεους θεοιν "
    "κυριος κυριου κυριω κυριον κυριε κυριοι κυριων κυριοις κυριους κυριοιν "
    "χριστος χριστου χριστω χριστον χριστε χριστοι χριστων χριστοις χριστους χριστοιν".split()
)


def greek_display(text: str) -> str:
    """Display equivalent raised dots and elision marks alike, keeping offsets."""
    return text.replace("·", "·").replace("∙", "·").replace("᾽", "’")


def shared_greek(old: str, new: str) -> str:
    """RP case by default; TR case for θεός, κύριος and χριστός."""
    letters = "".join(
        c
        for c in unicodedata.normalize("NFD", old.lower())
        if not unicodedata.combining(c)
    )
    return old if letters in TR_CASE_FORMS else new


def diff_spans(
    before: str, after: str, *, greek: bool = False
) -> list[tuple[str, str]]:
    """Whole-word/punctuation diff; lossless unless Greek display is requested.

    Disable difflib's popularity heuristic so repeated biblical phrases remain
    eligible anchors. Spaces cannot anchor arbitrary word pairs in a phrase
    replacement. These marks describe the finished text, not edit intent.
    """
    if greek:
        before, after = greek_display(before), greek_display(after)
    token = r"\w+(?:[’']\w+)*|\s+|[^\w\s]"
    left, right = re.findall(token, before), re.findall(token, after)
    # lower(), not casefold(): casefold erases Greek iota subscripts.
    keys_left = [word.lower() for word in left] if greek else left
    keys_right = [word.lower() for word in right] if greek else right
    spans: list[tuple[str, str]] = []

    def append(kind: str, old: str, new: str) -> None:
        if kind == "equal":
            spans.append(("equal", old))
        else:
            # A new closing mark belongs beside the preceding shared word,
            # before the omitted passage, rather than after its bracket.
            if (
                old[:1].isspace()
                and new
                and all(c in ",;:.?!··∙—\"'”’»)]}" for c in new)
            ):
                spans.append(("insert", new))
                new = ""
            if old:
                spans.append(("delete", old))
            if new:
                spans.append(("insert", new))

    opcodes = []
    for opcode in SequenceMatcher(
        str.isspace, keys_left, keys_right, autojunk=False
    ).get_opcodes():
        opcodes.append(opcode)
        if len(opcodes) < 3:
            continue
        prior, shared, following = opcodes[-3:]
        # A mark inside an omitted passage is not the new closing mark of
        # the preceding word: keep the omission whole on both sides of it.
        if (
            (prior[0], shared[0], following[0]) == ("delete", "equal", "delete")
            and "".join(left[shared[1] : shared[2]]).strip()
            and all(
                char.isspace() or char in ",;:.?!··∙—\"'”’»)]}"
                for char in "".join(left[shared[1] : shared[2]])
            )
            and any(char.isalnum() for char in "".join(left[prior[1] : prior[2]]))
            and any(
                char.isalnum() for char in "".join(left[following[1] : following[2]])
            )
        ):
            opcodes[-3:] = [("replace", prior[1], following[2], shared[3], shared[4])]
    for kind, a, b, c, d in opcodes:
        old, new = "".join(left[a:b]), "".join(right[c:d])
        if greek and kind == "equal":
            old = "".join(shared_greek(x, y) for x, y in zip(left[a:b], right[c:d]))
        # Junk spaces do not anchor the matcher, but a shared trailing space
        # still belongs to the context rather than either changed reading.
        suffix = 0
        if kind == "replace":
            while (
                suffix < min(len(old), len(new))
                and old[-suffix - 1].isspace()
                and old[-suffix - 1] == new[-suffix - 1]
            ):
                suffix += 1
        if suffix:
            append(kind, old[:-suffix], new[:-suffix])
            append("equal", old[-suffix:], new[-suffix:])
        else:
            append(kind, old, new)
    return spans


def phrases(text: str) -> list[tuple[int, int]]:
    """Complete phrases, including their closing punctuation and quotations."""
    ends = [m.end() for m in re.finditer(r"[,;:.?!··∙—]+[\"'”’»)\]}]*\s*", text)]
    bounds = [0, *ends]
    if bounds[-1] != len(text):
        bounds.append(len(text))
    return [(a, b) for a, b in zip(bounds, bounds[1:]) if a < b]


def clipped(spans: Sequence[tuple[str, str]]) -> list[tuple[str, str]]:
    """Keep complete phrases touched on either side, and every changed span.

    Select in each original text, then project to the shared span stream.
    Thus punctuation changes and insertions at a boundary retain their own
    phrases even when the two texts divide into phrases differently.
    """
    size = sum(len(value) for _, value in spans)
    selected = bytearray(size)
    for absent in ("insert", "delete"):
        text = "".join(value for kind, value in spans if kind != absent)
        ranges = phrases(text)
        touched: list[tuple[int, int]] = []
        at = 0
        for kind, value in spans:
            if kind == absent:
                continue
            end = at + len(value)
            if kind != "equal":
                touched.extend((a, b) for a, b in ranges if a < end and at < b)
            at = end
        at = stream = 0
        for kind, value in spans:
            end = at + (len(value) if kind != absent else 0)
            if kind != absent:
                for a, b in touched:
                    lo, hi = max(a, at), min(b, end)
                    if lo < hi:
                        selected[stream + lo - at : stream + hi - at] = b"\1" * (
                            hi - lo
                        )
            if kind != "equal":
                selected[stream : stream + len(value)] = b"\1" * len(value)
            at = end
            stream += len(value)
    if not any(kind != "equal" for kind, _ in spans):
        return list(spans)
    result: list[tuple[str, str]] = []
    stream = 0
    gap = False
    for kind, value in spans:
        for i, char in enumerate(value):
            if not selected[stream + i]:
                gap = True
                continue
            if gap:
                if result and result[-1][0] == "equal":
                    result[-1] = ("equal", result[-1][1].rstrip())
                result.append(("equal", " … " if result else "… "))
                gap = False
            if result and result[-1][0] == kind:
                result[-1] = (kind, result[-1][1] + char)
            else:
                result.append((kind, char))
        stream += len(value)
    if gap:
        if result and result[-1][0] == "equal":
            result[-1] = ("equal", result[-1][1].rstrip())
        result.append(("equal", " …"))
    return result


def marked(spans: Sequence[tuple[str, str]]) -> str:
    """ASCII change marks for the Markdown review's code spans."""
    marks = {"delete": "-", "insert": "+"}
    return "".join(
        value if kind == "equal" else f"[{marks[kind]}{value}]" for kind, value in spans
    )


def anchored(
    left: str,
    right: str,
    ranges: Sequence[tuple[int, int, int, int]],
    *,
    greek: bool = False,
) -> list[tuple[str, str]]:
    """Compare each ledger unit and intervening passage independently."""
    spans: list[tuple[str, str]] = []
    lo = ro = 0
    merged: list[tuple[int, int, int, int]] = []
    for a, b, c, d in ranges:
        # Keep a shared closing mark with its word rather than letting the
        # following passage match it to punctuation in a displaced reading.
        while (
            0 <= b < len(left)
            and 0 <= d < len(right)
            and left[b] == right[d]
            and left[b] in ",;:.?!··∙—\"'”’»)]}"
        ):
            b += 1
            d += 1
        if merged and (a < merged[-1][1] or c < merged[-1][3]):
            x, y, z, w = merged[-1]
            merged[-1] = (min(x, a), max(y, b), min(z, c), max(w, d))
        else:
            merged.append((a, b, c, d))
    for a, b, c, d in merged:
        if a < lo or c < ro or not a <= b <= len(left) or not c <= d <= len(right):
            raise ValueError("Invalid projected Greek comparison ranges")
        spans.extend(diff_spans(left[lo:a], right[ro:c], greek=greek))
        spans.extend(diff_spans(left[a:b], right[c:d], greek=greek))
        lo, ro = b, d
    spans.extend(diff_spans(left[lo:], right[ro:], greek=greek))
    return spans


def corresponding(
    texts: Sequence[str],
    links: Sequence[tuple[int, int, int, int, int, int]],
    seeds: Sequence[Sequence[tuple[int, int]]],
) -> list[tuple[tuple[int, int], ...]]:
    """Close passage selections over phrases and verified correspondence links.

    Each link relates indivisible wording in two texts. A gap is allowed only
    when all selected texts have a nonempty, consistently ordered omitted interval.
    Missing correspondence conservatively selects the complete verse.
    """
    whole = tuple((0, len(text)) for text in texts)
    selected: list[tuple[tuple[int, int], ...]] = []
    for seed in seeds:
        ranges = list(seed)
        while True:
            previous = list(ranges)
            for side, text in enumerate(texts):
                lo, hi = ranges[side]
                if lo < 0:
                    continue
                touched = [
                    (a, b)
                    for a, b in phrases(text)
                    if a < hi and lo < b or lo == hi and a <= lo <= b
                ]
                if touched:
                    ranges[side] = (min(lo, touched[0][0]), max(hi, touched[-1][1]))
            for s, a, b, t, c, d in links:
                for x, lo, hi, y, start, end in (
                    (s, a, b, t, c, d),
                    (t, c, d, s, a, b),
                ):
                    u, v = ranges[x]
                    if u >= 0 and (lo < v and u < hi or lo == hi and u <= lo <= v):
                        p, q = ranges[y]
                        ranges[y] = (
                            (start, end) if p < 0 else (min(p, start), max(q, end))
                        )
            if ranges == previous:
                break
        if any(a < 0 for a, _ in ranges):
            return [whole]
        selected.append(tuple(ranges))
    selected.sort()
    merged: list[tuple[tuple[int, int], ...]] = []
    for passage in selected:
        while merged and any(a <= d for (a, _), (_, d) in zip(passage, merged[-1])):
            prior = merged.pop()
            passage = tuple(
                (min(a, c), max(b, d)) for (a, b), (c, d) in zip(passage, prior)
            )
        merged.append(passage)
    if len(merged) < len(selected):
        # Merging fills intervals whose links may require further context.
        return corresponding(texts, links, merged)
    # A leading or trailing ellipsis must describe omitted wording on every side.
    if merged and (
        len({a == 0 for a, _ in merged[0]}) > 1
        or len({b == len(t) for (_, b), t in zip(merged[-1], texts)}) > 1
    ):
        return [whole]
    return merged or [whole]


def passage_spans(
    texts: Sequence[str],
    passage: Sequence[tuple[int, int]],
    side: int,
    anchors: Sequence[tuple[int, int, int, int]],
    *,
    greek: bool = False,
) -> list[tuple[str, str]]:
    """Compare one corresponding passage with common omission markers."""
    a, b = passage[side]
    c, d = passage[side + 1]
    local = [
        (x - a, y - a, z - c, w - c)
        for x, y, z, w in anchors
        if a <= x <= y <= b and c <= z <= w <= d
    ]
    result = anchored(texts[side][a:b], texts[side + 1][c:d], local, greek=greek)
    if a:
        result.insert(0, ("equal", "… "))
    if b < len(texts[side]):
        if result and result[-1][0] == "equal":
            result[-1] = ("equal", result[-1][1].rstrip())
        result.append(("equal", " …"))
    return result
