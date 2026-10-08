"""The CrossWire bridge from the KJV's words to Scrivener's tokens, and the
word-level helpers every English witness uses.

`bridge` maps each KJV word to the TR positions CrossWire tags it with, so a
witness's changed English words can be laid on a Greek unit (`fitting_unit`).
Nothing here edits English or decides anything.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from difflib import SequenceMatcher
from typing import Any, TypedDict

from bible import scripture
from bible.byzantine import BOOKS
from bible.byzantine.greek import ascii_greek
from bible.byzantine.rows import Report, Unit
from bible.sources import Content


class Link(TypedDict):
    """A CrossWire word: its characters in the verse, the TR positions
    (1-based) and forms it renders, and their Strong's numbers."""

    range: list[int]
    src: list[str]
    forms: list[str]
    strongs: list[int]


class Tagged(TypedDict):
    """A CrossWire verse: its words, and the Greek each is tagged with."""

    text: str
    links: list[Link]


class Aligned(TypedDict):
    """The bridge at a verse: for each KJV word, the TR positions it renders."""

    positions: list[list[int]]
    direct: list[list[int]]
    greek_length: int
    word_ranges: list[list[int]]


type Spans = list[tuple[str, int, int]]

# English grammar words shared by the instruction and rendering checks.
FUNCTION_WORDS = frozenset(
    """a an the and or nor but for yet so also even then therefore wherefore because if that which who whom whose
    what when where whither whence while as than of to in into unto upon on at by with from out over under through
    about against among before after behind up down off i me my mine we us our ours thou thee thy thine ye you your
    yours he him his she her hers it its they them their theirs himself herself itself themselves myself ourselves
    yourselves thyself this these those there here be is are was were been being am art wast wert have hast hath has
    had having do doth dost did shall shalt will wilt would wouldest should shouldest may mayest might mightest must can
    canst could couldest let not no""".split()
)

OSIS = "Matt Mark Luke John Acts Rom 1Cor 2Cor Gal Eph Phil Col 1Thess 2Thess 1Tim 2Tim Titus Phlm Heb Jas 1Pet 2Pet 1John 2John 3John Jude Rev".split()
SPELLINGS = {
    "burnt": "burned",
    "judaea": "judea",
    "shew": "show",
    "shewed": "showed",
    "shewing": "showing",
    "honour": "honor",
    "honoured": "honored",
    "honoureth": "honoreth",
    "labour": "labor",
    "labours": "labors",
    "laboured": "labored",
    "labouring": "laboring",
    "favour": "favor",
    "saviour": "savior",
    "neighbour": "neighbor",
    "neighbours": "neighbors",
    "amongst": "among",
}


SPAN = re.compile(r"[A-Za-zÆæ]+(?:[’'][A-Za-zÆæ]+)?")


def spans(text: str) -> Spans:
    # CrossWire uses the Latin ae ligature in names. Normalize the comparison
    # word only; offsets still address the original string, including the glyph.
    return [
        (m[0].lower().replace("æ", "ae").replace("’", "'"), m.start(), m.end())
        for m in SPAN.finditer(text)
    ]


def edit_offsets(
    text: str, edit: Mapping[str, Any], tokens: Spans | None = None
) -> tuple[int, int]:
    """The character span of a bound edit's KJV words."""
    tokens = spans(text) if tokens is None else tokens
    i, j = edit["word_range"]
    lo = tokens[i][1] if i < len(tokens) else len(text)
    hi = tokens[j - 1][2] if j > i else lo
    return lo, hi


def curly_apostrophes(text: str) -> str:
    """The text with the apostrophe curly, as the KJV prints it."""
    return re.sub(r"(?<=[A-Za-z])'(?=[A-Za-z])|(?<=s)'(?![A-Za-z])", "’", text)


def bracket_kept(new: str, kept: Iterable[str]) -> str:
    """New words with each supplied word an edit carries over in brackets, so
    words an instruction keeps keep the KJV's italics (Rev 3:8 "no man")."""
    for word in dict.fromkeys(w for k in kept for w in k.split()):
        new = re.sub(
            r"(?<![A-Za-z\[])" + re.escape(word) + r"(?![A-Za-z\]])",
            "[" + word + "]",
            new,
            count=1,
        )
    return new.replace("] [", " ")


def unique_moves(old: str, new: str) -> list[tuple[int, int, int, int]]:
    """For each word occurring once in both old and new, last first: its span
    in new and its span in old."""
    old_words = list(scripture.WORD.finditer(old))
    new_words = list(scripture.WORD.finditer(new))
    old_counts = Counter(word[0] for word in old_words)
    new_counts = Counter(word[0] for word in new_words)
    offsets = {word[0]: word.span() for word in old_words}
    return [
        (word.start(), word.end(), *offsets[word[0]])
        for word in reversed(new_words)
        if old_counts[word[0]] == new_counts[word[0]] == 1
    ]


def words(text: str) -> list[str]:
    return [w for w, _, _ in spans(text)]


def contrast(old: str, new: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The words that change from old to new, without the words they share
    at either end."""
    a, b = words(old), words(new)
    while a and b and a[0] == b[0]:
        a, b = a[1:], b[1:]
    while a and b and a[-1] == b[-1]:
        a, b = a[:-1], b[:-1]
    return tuple(a), tuple(b)


def reports_by_unit[R: Mapping[str, Any]](reports: Iterable[R]) -> dict[str, list[R]]:
    """Each unit's reports, once for every attachment a report makes to it."""
    attached: defaultdict[str, list[R]] = defaultdict(list)
    for report in reports:
        for a in report.get("units", []):
            attached[a["unit"]].append(report)
    return attached


def reported_operation(row: Mapping[str, Any]) -> tuple[bool, bool, bool]:
    """Whether a row reports an omission, an addition, a transposition."""
    old, new = row.get("old"), row.get("new")
    kind, op = row.get("kind"), row.get("op")
    return (
        op == "omit" or kind == "delete" or bool(old) and new == "",
        op == "add" or kind == "insert" or old == "" and bool(new),
        op == "transpose"
        or (
            old is not None
            and new is not None
            and words(old) != words(new)
            and sorted(words(old)) == sorted(words(new))
        ),
    )


def crosswire(path: Content) -> dict[str, Tagged]:
    result: dict[str, Tagged] = {}
    ref: str | None = None
    chunks: list[str] = []
    links: list[Link] = []
    length = 0
    namespace = "{http://www.bibletechnologies.net/2003/OSIS/namespace}"
    books = dict(zip(OSIS, BOOKS, strict=True))

    def append(text: str | None) -> None:
        nonlocal length
        if ref and text:
            chunks.append(text)
            length += len(text)

    def walk(node: ET.Element) -> None:
        nonlocal ref, chunks, links, length
        tag = node.tag.removeprefix(namespace)
        if tag == "verse":
            start_id = node.get("sID")
            if start_id:
                book, chapter, verse = start_id.split(".")
                ref = f"{books[book]} {chapter}:{verse}" if book in books else None
                chunks, links, length = [], [], 0
            elif ref and node.get("eID"):
                if ref in result:
                    raise ValueError(f"Duplicate CrossWire verse: {ref}")
                result[ref] = {"text": "".join(chunks), "links": links}
                ref = None
            return
        if tag in {"note", "title", "header"}:
            return
        start, owner = length, ref
        append(node.text)
        for child in node:
            walk(child)
            append(child.tail)
        if ref and ref == owner and tag == "w":
            links.append(
                {
                    "range": [start, length],
                    "src": node.get("src", "").split(),
                    "forms": re.findall(r"lemma\.TR:([^ ]+)", node.get("lemma", "")),
                    "strongs": [
                        int(n)
                        for n in re.findall(r"strong:G0*(\d+)", node.get("lemma", ""))
                    ],
                }
            )

    # Only the New Testament's books are walked; each holds its own verses.
    for div in ET.fromstring(path.read_bytes()).iter(f"{namespace}div"):
        if div.get("type") == "book" and div.get("osisID") in books:
            walk(div)
    if len(result) != 7957:
        raise ValueError(f"CrossWire NT inventory: {len(result)}, expected 7957")
    return result


def equal_positions(before: Sequence[str], after: Sequence[str]) -> dict[int, int]:
    return {
        i + offset: j + offset
        for i, j, count in SequenceMatcher(
            None, before, after, autojunk=False
        ).get_matching_blocks()
        for offset in range(count)
    }


def attach_sole(reports: Sequence[Report], units: Iterable[Unit]) -> list[Report]:
    """Place a witness's only row in a verse on the verse's only unit.

    This report fallback refuses a contrast whose operation contradicts the
    unit's length or order; reports at equal-length substitutions can still
    describe an English addition or omission. Instruction attachment checks
    the executable edits separately in instructions.attach.
    """
    by_ref: defaultdict[str, list[Unit]] = defaultdict(list)
    rows: defaultdict[str, list[Report]] = defaultdict(list)
    for unit in units:
        by_ref[unit["ref"]].append(unit)
    for row in reports:
        rows[row["ref"]].append(row)
    result: list[Report] = []
    for row in reports:
        if row["units"]:
            result.append({"method": "greek", **row})
            continue
        candidates = by_ref[row["ref"]]
        if (
            row["scope"] != "verse"
            or len(candidates) != 1
            or len(rows[row["ref"]]) != 1
        ):
            result.append(row)
            continue
        unit = candidates[0]
        omission, addition, transpose = reported_operation(row)
        tr_count = unit["tr_range"][1] - unit["tr_range"][0]
        rp_count = unit["rp_range"][1] - unit["rp_range"][0]
        contradicts = (
            omission
            and rp_count > tr_count
            or addition
            and tr_count > rp_count
            or transpose
            and unit["class"] != "order"
        )
        if contradicts:
            result.append(row)
            continue
        placed: Report = {
            **row,
            "scope": "greek",
            "method": "sole",
            "units": [{"unit": unit["id"], "scope": "unit"}],
        }
        placed.pop("reason", None)
        result.append(placed)
    return result


def bridge(
    rows: Mapping[str, Tagged],
    tr: Mapping[str, Sequence[str]],
    kjv: Mapping[str, str],
) -> tuple[dict[str, Aligned], dict[str, str]]:
    """Map the agreeing words of the Greek and English streams.

    No inferred correspondence across a Greek mismatch. Untagged English
    closes over both neighbouring tagged groups; it never gets an invented
    Greek word of its own.
    """
    result: dict[str, Aligned] = {}
    failures: dict[str, str] = {}
    for ref, row in rows.items():
        positions: dict[int, str] = {}
        valid = True
        for link in row["links"]:
            if len(link["src"]) != len(link["forms"]):
                valid = False
                break
            for p, form in zip(link["src"], link["forms"]):
                if not p.isdigit() or int(p) < 1:
                    valid = False
                    break
                index, greek = int(p) - 1, ascii_greek(form)
                if index in positions and positions[index] != greek:
                    valid = False
                positions[index] = greek
        if not valid or set(positions) != set(range(len(positions))):
            failures[ref] = "incomplete or conflicting CrossWire Greek positions"
            continue
        greek_map = equal_positions(
            [positions[i] for i in range(len(positions))], tr[ref]
        )
        old, new = spans(row["text"]), spans(kjv[ref])

        def normalize(s: Spans) -> list[str]:
            return [SPELLINGS.get(w, w) for w, _, _ in s]

        english_map = equal_positions(normalize(old), normalize(new))
        mapped: list[list[int]] = []
        for _, start, end in old:
            linked = [
                l for l in row["links"] if l["range"][0] <= start < end <= l["range"][1]
            ]
            mapped.append(sorted({int(p) - 1 for l in linked for p in l["src"]}))
        original = [list(p) for p in mapped]
        for i, ps in enumerate(original):
            if ps:
                continue
            left = next((original[j] for j in range(i - 1, -1, -1) if original[j]), [])
            right = next(
                (original[j] for j in range(i + 1, len(original)) if original[j]), []
            )
            mapped[i] = sorted(set(left + right))
        target: list[list[int]] = [[] for _ in new]
        direct: list[list[int]] = [[] for _ in new]
        for i, j in english_map.items():
            target[j] = sorted({greek_map[p] for p in mapped[i] if p in greek_map})
            direct[j] = sorted({greek_map[p] for p in original[i] if p in greek_map})
        result[ref] = {
            "positions": target,
            # Only the TR words CrossWire tags the English word itself with;
            # an untagged (supplied or grammatical) word has none here.
            "direct": direct,
            "greek_length": len(tr[ref]),
            "word_ranges": [[s, e] for _, s, e in new],
        }
    return result, failures


def presentation_bridge(row: Tagged, tr: Sequence[str], kjv: str) -> Aligned:
    """Partial, position-checked correspondence for display only.

    A missing or conflicting tag remains unresolved; it cannot shift later
    positions or borrow its neighbours' evidence. Scripture editing uses bridge.
    """
    forms: dict[int, set[str]] = defaultdict(set)
    for link in row["links"]:
        for p, form in zip(link["src"], link["forms"]):
            if p.isdigit() and int(p) > 0:
                forms[int(p) - 1].add(ascii_greek(form))
    valid = {p for p, fs in forms.items() if p < len(tr) and fs == {tr[p]}}
    old, new = spans(row["text"]), spans(kjv)
    english_map = equal_positions(
        [SPELLINGS.get(w, w) for w, _, _ in old],
        [SPELLINGS.get(w, w) for w, _, _ in new],
    )
    direct: list[list[int]] = []
    untagged = []
    for _, start, end in old:
        links = [
            l for l in row["links"] if l["range"][0] <= start < end <= l["range"][1]
        ]
        ps = [p for l in links for p in l["src"]]
        checked = (
            bool(ps)
            and all(len(l["src"]) == len(l["forms"]) for l in links)
            and all(p.isdigit() and int(p) - 1 in valid for p in ps)
        )
        direct.append(sorted({int(p) - 1 for p in ps}) if checked else [])
        untagged.append(not links)
    mapped = [list(ps) for ps in direct]
    for i, empty in enumerate(untagged):
        if empty:
            left = next(
                (direct[j] for j in range(i - 1, -1, -1) if not untagged[j]), []
            )
            right = next(
                (direct[j] for j in range(i + 1, len(old)) if not untagged[j]), []
            )
            mapped[i] = sorted(set(left + right)) if left and right else left or right
    target: list[list[int]] = [[] for _ in new]
    target_direct: list[list[int]] = [[] for _ in new]
    for i, j in english_map.items():
        target[j], target_direct[j] = mapped[i], direct[i]
    return {
        "positions": target,
        "direct": target_direct,
        "greek_length": len(tr),
        "word_ranges": [[s, e] for _, s, e in new],
    }


def bridged_words(bridge: Aligned, start: int, end: int) -> list[int]:
    """The English words the bridge maps to the Greek positions start to end."""
    return [
        i
        for i, ps in enumerate(bridge["positions"])
        if any(start <= p < end for p in ps)
    ]


def fitting_unit(
    candidates: Iterable[Unit],
    aligned: Aligned,
    i: int,
    j: int,
    kind: str,
    transpose: bool = False,
) -> tuple[Unit, str, set[int]] | None:
    """The one unit whose TR words the KJV words i to j render.

    An insertion fits the unit beside it. Several fitting units narrow to
    those whose Greek does what the English does. Returns the unit, the
    attachment scope and the aligned TR positions, or None.
    """
    positions = aligned["positions"]
    ps = {p for group in positions[i:j] for p in group}
    fitting: list[Unit] = []
    compatible: list[Unit] = []
    for u in candidates:
        if u.get("kind") == "relocation" or u["class"] == "accent":
            continue
        a, b = u["tr_range"]
        c, d = u["rp_range"]
        if kind == "insert":
            left: list[int] = positions[i - 1] if i else []
            right: list[int] = positions[i] if i < len(positions) else []
            fits = (
                bool(set(range(a, b)) & set(left + right))
                if a < b
                else (
                    a == 0
                    and i == 0
                    or a == aligned["greek_length"]
                    and i == len(positions)
                    or a - 1 in left
                    and a in right
                )
            )
        else:
            # A published directive may change only the noun of a
            # noun/adjective concord unit (MAT 3:8). Retain that narrower
            # scope rather than pretending it covers every Greek constituent.
            fits = a < b and bool(set(range(a, b)) & ps)
        operation_fits = (
            a == b and c < d
            if kind == "insert"
            else (
                c == d
                if kind == "delete"
                else c < d and (u["class"] == "order" if transpose else True)
            )
        )
        if fits:
            fitting.append(u)
            if operation_fits:
                compatible.append(u)
    if len(fitting) > 1:
        fitting = compatible
    if len(fitting) != 1:
        return None
    chosen = fitting[0]
    a, b = chosen["tr_range"]
    scope = (
        "unit"
        if kind == "insert" and a == b or set(range(a, b)) <= ps
        else "constituent"
    )
    return chosen, scope, ps
