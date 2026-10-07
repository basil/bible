"""Apply the dispositions to the KJV: edits at fixed offsets in the USJ, each
with its Textus Receptus footnote, and the structural moves and omissions.

Only the declared seam rules touch anything beside the edited words: the
capital of a word that begins or stops beginning a sentence, the punctuation
an omission leaves behind, the article a or an before a changed word, and the
supplied-word brackets an instruction writes. An operation the rules cannot
carry out is refused by name, never guessed at.
"""

from __future__ import annotations

import functools
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal

from bible import scripture, usj
from bible.alexandrinus import without_verses
from bible.byzantine.crosswire import (
    bracket_kept,
    curly_apostrophes,
    edit_offsets,
    spans,
    unique_moves,
    words,
)
from bible.byzantine.greek import Structure, occurrences
from bible.byzantine.rows import Disposition, Edit, Seam
from bible.checks import CheckFailed
from bible.scripture import Verse
from bible.usj import Content, Document, Node

# A change to a verse's words: the verse, the offsets of the words, and the
# content that takes their place (scripture.edited).
type Change = tuple[Verse, int, int, Content]

# What a Textus Receptus note says the TR has: other words for its lemma,
# words added or omitted, a verse added after it, the passage it stands on
# elsewhere, or here the verses printed elsewhere. A note carries its kind,
# and the verse or passage it names (`where`), in its x-scope; nothing reads
# its label.
type NoteKind = Literal["replace", "adds", "omits", "adds-verse", "moved", "moved-out"]
# What the TR has where the passage is, or where the verses are, as the
# edition words it.
PASSAGE_NOTES = {
    "moved": "has this passage at {where}.",
    "moved-out": "has here the verses printed at {where}.",
}
# The labels the reconciliation gives its notes, for the review.
NOTE_LABELS: dict[str, str] = {
    "replace": "Textus Receptus: ",
    "adds": "Textus Receptus adds: ",
    "omits": "Textus Receptus omits: ",
    "adds-verse": "Textus Receptus adds verse {where}: ",
    **{kind: "Textus Receptus " + sentence for kind, sentence in PASSAGE_NOTES.items()},
}
# The kind of note each operation on the KJV's words takes: the TR's words
# that an omission takes out, it adds; those an insertion puts in, it omits.
NOTE_KINDS: dict[str, NoteKind] = {
    "replace": "replace",
    "transpose": "replace",
    "delete": "adds",
    "insert": "omits",
}


def raw_bounds(raw: str, normalized: str, start: int, end: int) -> tuple[int, int]:
    """Map the reader's normalized offsets back to original paragraph spaces."""
    tokens = list(re.finditer(r"\S+", raw))
    starts: list[int] = []
    ends: list[int] = []
    text = ""
    for index, token in enumerate(tokens):
        if index:
            text += " "
            starts.append(tokens[index - 1].end())
            ends.append(token.start())
        text += token[0]
        starts.extend(range(token.start(), token.end()))
        ends.extend(range(token.start() + 1, token.end() + 1))
    if text != normalized or not 0 <= start <= end <= len(text):
        raise ValueError("Stale normalized source or invalid offset")
    lo = starts[start] if start < len(starts) else len(raw.rstrip())
    return lo, ends[end - 1] if end > start else lo


# An interjection carries its own comma; omitting it omits the comma too.
INTERJECTIONS = {"lo", "behold"}


def source_content(document: Document, verse: Verse, lo: int, hi: int) -> Content:
    """The source's own content of a stretch of a verse's words, its styles
    kept, which must lie in one paragraph."""
    index, start = verse.part_at(lo, at_end=lo == hi)
    if verse.part_at(hi, at_end=True)[0] != index:
        raise ValueError("Source quotation crosses paragraphs")
    block, a, b, _ = verse.parts[index]
    _, tail = usj.split(
        document["content"][block]["content"][a:b], start, notes_left=False
    )
    quote, _ = usj.split(tail, hi - lo)
    return quote


def tidy_supplied(document: Document) -> Document:
    """Supplied-word italics an edit has cut short: a space at either edge
    stands outside the span, and a span left with no word is roman."""

    def tidy(node: Node) -> Node | Content:
        if not usj.is_type(node, "char", "add"):
            return node
        text = usj.text_of(node["content"])
        if not re.search(r"[^\W\d_]", text):
            return node["content"]
        content = list(node["content"])
        head = tail = ""
        if isinstance(content[0], str) and content[0] != content[0].lstrip():
            head = content[0][: len(content[0]) - len(content[0].lstrip())]
            content[0] = content[0].lstrip()
        if isinstance(content[-1], str) and content[-1] != content[-1].rstrip():
            tail = content[-1][len(content[-1].rstrip()) :]
            content[-1] = content[-1].rstrip()
        if not head and not tail:
            return node
        return [head, {**node, "content": [c for c in content if c != ""]}, tail]

    return usj.with_content(document, lambda content: usj.mapped(content, tidy))


def supplied_content(text: str) -> Content:
    """An instruction's brackets denote supplied words, never USFM in a string."""
    result: Content = []
    at = 0
    for match in re.finditer(r"\[([^\[\]]+)\]", text):
        result.extend([text[at : match.start()], usj.char("add", match[1])])
        at = match.end()
    result.append(text[at:])
    if any("[" in item or "]" in item for item in result if isinstance(item, str)):
        raise ValueError("Malformed supplied-word brackets")
    return usj.joined(result)


def transposed_content(
    document: Document, verse: Verse, lo: int, hi: int, rendered: str
) -> Content:
    """Move each uniquely identified source word with its original styles."""
    content = supplied_content(rendered)
    # Offsets in the content's words, which lack the reading's brackets.
    for start, end, a, b in unique_moves(verse.text[lo:hi], usj.text_of(content)):
        content = usj.replaced(
            content, start, end, source_content(document, verse, lo + a, lo + b)
        )
    return content


def sentence_start(text: str, at: int) -> bool:
    before = text[:at].rstrip()
    return not before or before[-1] in ".!?"


def question_continuation(text: str, lo: int, hi: int) -> bool:
    """The KJV can continue a question with a lower-case clause."""
    first = re.search(r"[A-Za-z]", text[lo:hi])
    return bool(first and first[0].islower() and text[:lo].rstrip().endswith("?"))


def seam(
    text: str,
    lo: int,
    hi: int,
    new: str,
    quoted_old: str = "",
    continues_sentence: bool = False,
) -> tuple[int, int, str, list[Seam]]:
    """Only the declared capital and punctuation rules, at an edit's edges."""
    start, end = lo, hi
    seams: list[Seam] = []
    if new:
        first = re.search(r"[A-Za-z]", new)
        old = re.search(r"[A-Za-z]", text[lo:hi])
        quoted = re.search(r"[A-Za-z]", quoted_old)
        capital = None
        # Transfer an instruction's quotation case to the actual source case.
        # Capitals supplied as part of the reading (God's, I) stay witnessed.
        if old and quoted and old[0].isupper() != quoted[0].isupper():
            capital = old[0].isupper()
        # A verse may continue a sentence (Matthew 7:14); its initial is
        # evidence of that boundary, rather than a new sentence by default.
        # An insertion at the verse's start reads the initial it precedes.
        initial = old or (None if lo else re.search(r"[A-Za-z]", text[hi:]))
        if (
            sentence_start(text, lo)
            and not (lo == 0 and continues_sentence)
            and not question_continuation(text, lo, hi)
        ):
            if lo or not initial or initial[0].isupper():
                capital = True
            elif not old:
                capital = False
        if first and capital is not None:
            letter = first[0].upper() if capital else first[0].lower()
            changed = new[: first.start()] + letter + new[first.end() :]
            if changed != new:
                seams.append({"rule": 1, "range": [lo, lo], "from": new, "to": changed})
                new = changed
        return start, end, new, seams
    # Remove the omitted phrase's comma when it separates it from the next
    # phrase, or belongs to it. A terminal stop is carried, not discarded.
    if start == 0:
        while end < len(text) and text[end] in " ,;:.?!":
            end += 1
    if text[end : end + 1] == "," and (
        sentence_start(text, lo)
        or text[:lo].rstrip().endswith(",")
        or text[lo:hi].casefold() in INTERJECTIONS
    ):
        end += 1
    if text[end : end + 1] == " ":
        end += 1
    elif start and text[start - 1 : start] == " ":
        start -= 1
    if text[end : end + 1] in {".", ",", ":", ";", "?", "!"}:
        while start and text[start - 1] in " ,;:":
            start -= 1
        if start and text[start - 1] == text[end]:
            end += 1
    if (start, end) != (lo, hi):
        seams.append(
            {"rule": 2, "range": [start, end], "from": text[start:end], "to": ""}
        )
    # A following word that becomes the first is changed independently, so
    # its capitalization does not enter the displaced-reading quotation.
    return start, end, new, seams


def edition_note(
    ref: str,
    kind: NoteKind,
    quotation: Content | None = None,
    key: str | None = None,
    where: str | None = None,
) -> Node:
    """A Textus Receptus footnote: reference, label, and the displaced words,
    with its kind and the verse or passage it names."""
    fields = [
        usj.char("fr", ref + " "),
        usj.char("ft", NOTE_LABELS[kind].format(where=where)),
    ]
    if quotation is not None:
        fields.append(usj.char("fq", *quotation))
    scope: usj.Scope = {"kind": kind}
    if where is not None:
        scope["where"] = where
    extra: usj.Extra = {"category": "edition", "x-scope": scope}
    if key:
        extra["x-key"] = key
    return usj.note("f", *fields, caller="+", **extra)


KJV_WORD = r"[A-Za-z]+(?:-[A-Za-z]+)*"


def kjv_usage(
    documents: Mapping[str, Document],
) -> tuple[set[str], defaultdict[str, Counter[str]]]:
    """The pinned KJV's own common words, and the article it sets before each.

    A capital after a lowercase word is a name (of God, the Lord), not
    evidence of a common word; and the article the KJV sets before a word (an
    hour, a house) is read, not guessed.
    """
    lowercase: Counter[str] = Counter()
    named: Counter[str] = Counter()
    articles: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for doc in documents.values():
        for verse in scripture.verses(doc).values():
            for match in re.finditer(KJV_WORD, verse.text):
                before = verse.text[max(0, match.start() - 2) : match.start()]
                if match[0].islower():
                    lowercase[match[0]] += 1
                elif len(before) == 2 and before[0].islower() and before[1] == " ":
                    named[match[0].lower()] += 1
            for match in re.finditer(r"\b([Aa]n?) ([A-Za-z]+)", verse.text):
                articles[match[2].lower()][match[1].lower()] += 1
    common = {word for word, count in lowercase.items() if count > named[word]}
    return common, articles


def refused(row: Disposition, reason: str) -> Disposition:
    """The row, without its edits, refused by name; the unit stays unchanged."""
    result: Disposition = {
        **row,
        "action": "refused",
        "execution": "refused",
        "reasons": [reason],
        "flags": [*row.get("flags", []), f"executor refused: {reason}"],
    }
    result.pop("edits", None)
    return result


def executing_instructions(
    rows: Iterable[Disposition],
) -> dict[str, list[tuple[str, int | str]]]:
    """Each witnessed unit's executing instruction identities, in selection order."""
    return {
        r["unit"]: [(i["source"], i["entry"]) for i in r["selected"].get("joint", [])]
        for r in rows
        if r.get("disposition") == "witnessed" and r.get("selected")
    }


def merged_deletions(
    ops: Sequence[Mapping[str, Any]], source_verses: Mapping[str, Mapping[str, Verse]]
) -> list[dict[str, Any]]:
    """Adjacent deletions of one construction in one verse, as one operation
    with one exact quotation, so a seam cannot swallow its neighbour's note."""

    def start(op: Mapping[str, Any]) -> list[int]:
        if op.get("range"):
            bounds: list[int] = op["range"]
            return bounds
        book, ref = op["ref"].split()
        tokens = spans(scripture.plain(source_verses[book][ref].text))
        a = op["word_range"][0]
        return [tokens[a][1] if a < len(tokens) else 10**9]

    result: list[dict[str, Any]] = []
    for op in sorted(ops, key=lambda o: (o["ref"], start(o))):
        if (
            result
            and op["kind"] == result[-1]["kind"] == "delete"
            and op["ref"] == result[-1]["ref"]
            and not op.get("raw_range")
            and not result[-1].get("raw_range")
        ):
            book, ref = op["ref"].split()
            text = scripture.plain(source_verses[book][ref].text)
            tokens = spans(text)
            previous = result[-1]
            if previous["word_range"][1] == op["word_range"][0]:
                lo, hi = (
                    tokens[previous["word_range"][0]][1],
                    tokens[op["word_range"][1] - 1][2],
                )
                result[-1] = {
                    **previous,
                    "word_range": [previous["word_range"][0], op["word_range"][1]],
                    "old": text[lo:hi],
                    "quoted_old": text[lo:hi],
                }
                continue
        result.append(dict(op))
    return result


def char_range(
    op: Mapping[str, Any], verse_text: str, plain_text: str
) -> tuple[int, int]:
    """The character range of an operation in the verse's raw text."""
    bounds = op.get("range" if op.get("raw_range") else "word_range")
    if (
        not isinstance(bounds, (list, tuple))
        or len(bounds) != 2
        or any(type(offset) is not int for offset in bounds)
    ):
        raise ValueError("invalid source offset")
    if op.get("raw_range"):
        lo, hi = bounds
        if not 0 <= lo <= hi <= len(verse_text):
            raise ValueError("invalid source offset")
        return lo, hi
    tokens = spans(plain_text)
    a, b = bounds
    if not 0 <= a <= b <= len(tokens):
        raise ValueError("invalid source offset")
    lo, hi = edit_offsets(plain_text, op, tokens)
    if op["kind"] == "insert" and op.get("side") == "after":
        lo = hi = tokens[a - 1][2] if a else 0
    return raw_bounds(verse_text, plain_text, lo, hi)


def execute(
    documents: Mapping[str, Document],
    dispositions: Sequence[Disposition],
    books: Sequence[str],
    usage: tuple[set[str], defaultdict[str, Counter[str]]] | None = None,
) -> tuple[dict[str, Document], list[Disposition]]:
    """Apply every `edit` disposition against the immutable source offsets.

    Returns (prepared documents, dispositions) where each applied row carries
    its `edits` (offsets, old and new words, note, seams) and each refused row
    says why. usage: the KJV's own usage (kjv_usage), read once for the
    article and capital seams, if the caller has read it already.
    """
    known = functools.cache(lambda: kjv_usage(documents) if usage is None else usage)
    source_verses = {book: scripture.verses(documents[book]) for book in books}
    following = {
        (book, left): right
        for book, verses in source_verses.items()
        for left, right in zip(verses, list(verses)[1:])
    }
    # A proper name at a verse's start need not begin a sentence (Luke 3:2).
    # Keep the proposed case where the preceding KJV verse joins the clause.
    source_continuations: set[tuple[str, str | None]] = {
        (book, right)
        for (book, left), right in following.items()
        if source_verses[book][left].text.rstrip().endswith((",", ";", ":"))
    }
    # A reviewed construction can join consecutive verses into one sentence.
    continuations: set[tuple[str | None, str, str | None]] = set()
    for row in dispositions:
        if row.get("action") != "edit" or not row.get("override"):
            continue
        for op in row["ops"]:
            book, ref = op["ref"].split()
            bounds = op.get("range")
            terminal = (
                isinstance(bounds, (list, tuple))
                and len(bounds) == 2
                and bounds[1] == len(source_verses[book][ref].text)
            )
            if terminal and op["new"].rstrip().endswith((",", ";", ":")):
                continuations.add((row["override"], book, following.get((book, ref))))
            elif terminal and op["new"].rstrip().endswith((".", "!", "?")):
                source_continuations.discard((book, following.get((book, ref))))
    occupied: defaultdict[str, list[tuple[int, int]]] = defaultdict(list)
    plans: dict[str, list[Change]] = {}
    result: list[Disposition] = []
    for row in dispositions:
        if row.get("action") != "edit":
            result.append({**row, "execution": "none"})
            continue
        book = (
            row["ops"][0]["ref"].split()[0] if row.get("ops") else row["ref"].split()[0]
        )
        if book not in books:
            result.append({**row, "execution": "none"})
            continue
        planned: list[Change] = []
        edits: list[Edit] = []
        refusal: str | None = None
        try:
            # Validate before adjacent deletions index the word ledger too.
            for op in row["ops"]:
                if op["kind"] not in {"replace", "delete", "insert", "transpose"}:
                    raise ValueError("operation not implemented")
                source_book, source_ref = op["ref"].split()
                source_text = source_verses[source_book][source_ref].text
                char_range(op, source_text, scripture.plain(source_text))
            ops = merged_deletions(row["ops"], source_verses)
            for op in ops:
                book, ref = op["ref"].split()
                verse = source_verses[book][ref]
                text = scripture.plain(verse.text)
                lo, hi = char_range(op, verse.text, text)
                if verse.text[lo - 1 : lo] == "[" and "]" in verse.text[lo:hi]:
                    lo -= 1
                if any(lo <= at <= hi for at, _ in verse.notes):
                    refusal = "existing source note on the edited words"
                    break
                if (
                    verse.part_at(lo, at_end=lo == hi)[0]
                    != verse.part_at(hi, at_end=True)[0]
                ):
                    refusal = "edit crosses paragraphs"
                    break
                if any(lo < b and a < hi for a, b in occupied[book + " " + ref]):
                    refusal = "overlapping edits"
                    break
                quote = verse.text[lo:hi]
                # The KJV prints the apostrophe curly; so does every edit.
                new = curly_apostrophes(op["new"])
                if op["kind"] != "insert" and words(quote) != words(op["old"]):
                    raise ValueError("stale edit: the KJV words differ")
                if not op.get("raw_range") and "[" not in new:
                    # Words an instruction keeps keep the KJV's italics (Rev 3:8
                    # "no man"): bracket each supplied word it carries over.
                    kept = [
                        usj.text_of(n.get("content", []))
                        for n in usj.walk(
                            source_content(documents[book], verse, lo, hi)
                        )
                        if n.get("marker") in {"add", "+add"}
                    ]
                    new = bracket_kept(new, kept)
                if quote == new and not op.get("unstyle"):
                    raise ValueError("edit changes nothing")
                start, end, rendered, seams = seam(
                    verse.text,
                    lo,
                    hi,
                    new,
                    op.get("quoted_old", op["old"]),
                    (book, ref) in source_continuations
                    or (row.get("override"), book, ref) in continuations,
                )
                # An addition's note quotes the words as printed, capital seam
                # included (Luke 6:37 "And judge": the TR omits "And").
                quotation = (
                    supplied_content(rendered)
                    if op["kind"] == "insert"
                    else source_content(documents[book], verse, lo, hi)
                )
                note = edition_note(
                    ref,
                    NOTE_KINDS[op["kind"]],
                    quotation,
                    f"{row['unit']} TR#{len(edits) + 1}",
                )
                prefix = suffix = ""
                content = (
                    transposed_content(documents[book], verse, lo, hi, rendered)
                    if op["kind"] == "transpose"
                    else supplied_content(rendered)
                )
                # Words replaced inside one character style (the small capitals
                # of Matt 27:46) keep that style; a supplied word's italics do not
                # pass to the real word that replaces it.
                if (
                    op["kind"] == "replace"
                    and len(quotation) == 1
                    and isinstance(quotation[0], dict)
                    and quotation[0].get("type") == "char"
                    and quotation[0].get("marker") not in {"add", "+add"}
                    and usj.text_of(quotation) == quote
                ):
                    content = [usj.char(quotation[0]["marker"], *content)]
                    seams.append(
                        {
                            "rule": 3,
                            "range": [lo, hi],
                            "from": "",
                            "to": "",
                            "style": quotation[0]["marker"],
                        }
                    )
                if op["kind"] == "insert":
                    prefix = (
                        " " if start and not verse.text[start - 1].isspace() else ""
                    )
                    suffix = (
                        " "
                        if verse.text[end : end + 1] and verse.text[end].isalpha()
                        else ""
                    )
                    content = usj.joined([prefix], content, [note, suffix])
                    seams.append(
                        {
                            "rule": 2,
                            "range": [lo, hi],
                            "from": "",
                            "to": prefix + suffix,
                        }
                    )
                else:
                    content = usj.joined(content, [note])
                planned.append((verse, start, end, content))
                if op.get("stop"):
                    # An instruction that ends the preceding sentence with a stop
                    # before the words it adds (Pierpont's "(Period) + And").
                    at = raw_bounds(
                        verse.text, text, *[spans(text)[op["word_range"][0] - 1][2]] * 2
                    )[0]
                    if verse.text[at : at + 1] != op["stop"]:
                        planned.append((verse, at, at, [op["stop"]]))
                        seams.append(
                            {
                                "rule": 2,
                                "range": [at, at],
                                "from": "",
                                "to": op["stop"],
                                "external": True,
                            }
                        )
                if new:
                    first_new = spans(usj.text_of(supplied_content(new)))
                elif start == lo and verse.text[end : end + 1].isalpha():
                    first_new = spans(verse.text[end:])[:1]
                else:
                    first_new = []
                article = re.search(r"\b([Aa]n?) $", verse.text[:lo])
                if article and first_new:
                    old_article = article[1]
                    _, articles = known()
                    count = articles[first_new[0][0]]
                    wanted = (
                        max(("a", "an"), key=count.__getitem__)
                        if count["a"] != count["an"]
                        else "an" if first_new[0][0][0] in "aeiou" else "a"
                    )
                    if old_article[0].isupper():
                        wanted = wanted.capitalize()
                    if wanted != old_article:
                        planned.append(
                            (verse, article.start(1), article.end(1), [wanted])
                        )
                        seams.append(
                            {
                                "rule": 4,
                                "range": [article.start(1), article.end(1)],
                                "from": old_article,
                                "to": wanted,
                            }
                        )
                if (
                    new
                    and op["kind"] == "insert"
                    and (
                        sentence_start(verse.text, start)
                        or verse.text[:start].rstrip().endswith(",")
                        and first_new
                        and usj.text_of(supplied_content(new))[0].isupper()
                    )
                ):
                    follower = re.match(r"([A-Z][a-z]+)", verse.text[end:])
                    if follower and follower[1].lower() in known()[0]:
                        at = end
                        planned.append((verse, at, at + 1, [follower[1][0].lower()]))
                        seams.append(
                            {
                                "rule": 1,
                                "range": [at, at + 1],
                                "from": follower[1][0],
                                "to": follower[1][0].lower(),
                            }
                        )
                initial = re.search(r"[A-Za-z]", verse.text)
                continues = start == 0 and (
                    (book, ref) in source_continuations
                    or (row.get("override"), book, ref) in continuations
                    or initial is not None
                    and initial[0].islower()
                )
                if (
                    not new
                    and sentence_start(verse.text, start)
                    and not continues
                    and not question_continuation(verse.text, lo, hi)
                ):
                    follower = re.match(r"[^A-Za-z]*([a-z])", verse.text[end:])
                    if follower:
                        at = end + follower.start(1)
                        planned.append((verse, at, at + 1, [follower[1].upper()]))
                        seams.append(
                            {
                                "rule": 1,
                                "range": [at, at + 1],
                                "from": follower[1],
                                "to": follower[1].upper(),
                            }
                        )
                edits.append(
                    {
                        "ref": book + " " + ref,
                        "kind": op["kind"],
                        "range": [lo, hi],
                        "old": quote,
                        "new": usj.text_of(supplied_content(new)),
                        "applied_range": [start, end],
                        "rendered": rendered,
                        "prefix": prefix,
                        "suffix": suffix,
                        "note": note,
                        "seams": seams,
                    }
                )
            if refusal is None:
                taken = {address: list(ranges) for address, ranges in occupied.items()}
                for verse, a, b, _ in planned:
                    ranges = taken.setdefault(book + " " + verse.reference, [])
                    if any(a < y and x < b for x, y in ranges):
                        raise ValueError("overlapping edits")
                    ranges.append((a, b))
        except (ValueError, CheckFailed) as error:
            refusal = str(error)
        if refusal:
            result.append(refused(row, refusal))
        elif not edits:
            result.append({**row, "execution": "none", "action": "nochange"})
        else:
            plans[row["unit"]] = planned
            for verse, a, b, _ in planned:
                occupied[book + " " + verse.reference].append((a, b))
            result.append({**row, "execution": "applied", "edits": edits})
    # A witnessed construction can be executed by several owner rows. One
    # refused row takes down every row sharing an executing instruction.
    joint = executing_instructions(result)
    while True:
        cause: dict[tuple[str, int | str], str] = {}
        for r in result:
            if r.get("execution") == "refused":
                for identity in joint.get(r["unit"], []):
                    cause.setdefault(identity, r["reasons"][0])
        peers = {
            r["unit"]: next(cause[i] for i in joint[r["unit"]] if i in cause)
            for r in result
            if r.get("execution") != "refused"
            and any(i in cause for i in joint.get(r["unit"], []))
        }
        if not peers:
            break
        result = [
            (refused(r, peers[r["unit"]]) if r["unit"] in peers else r) for r in result
        ]
    owners = {
        r["unit"]: r["reasons"][0] for r in result if r.get("execution") == "refused"
    }
    result = [
        refused(r, owners[r["covered_by"]]) if r.get("covered_by") in owners else r
        for r in result
    ]
    failed_overrides = {
        r["override"]
        for r in result
        if r.get("override") and r.get("execution") == "refused"
    }
    if failed_overrides:
        reasons = {
            r["override"]: r["reasons"][0]
            for r in result
            if r.get("override") in failed_overrides and r.get("execution") == "refused"
        }
        result = [
            (
                refused(r, reasons[r["override"]])
                if r.get("override") in failed_overrides
                and r.get("execution") != "refused"
                else r
            )
            for r in result
        ]
    prepared: dict[str, Document] = {}
    for book in books:
        changes = [
            c
            for row in result
            if row.get("execution") == "applied"
            and row["edits"][0]["ref"].split()[0] == book
            for c in plans[row["unit"]]
        ]
        prepared[book] = tidy_supplied(
            scripture.edited(
                documents[book], sorted(changes, key=lambda c: c[1] == c[2])
            )
        )
    return prepared, result


# Structural changes: whole verses RP omits or places elsewhere.


def renumber(content: Content, ref: str) -> Content:
    """A verse's content with the references of its notes made ref."""

    def change(node: Node) -> Node:
        if node.get("marker") in {"fr", "xo"}:
            return {**node, "content": [ref + " "]}
        return node

    return usj.mapped(content, change)


def structural(
    documents: Mapping[str, Document],
    dispositions: Sequence[Disposition],
    structure: Structure,
) -> tuple[dict[str, Document], list[Disposition]]:
    """Omit the verses RP lacks, noting each on the verse before it, and move
    the verses RP places elsewhere, with a note at each end of the move: at
    the new place, where the Received Text has the passage; and, where a
    passage leaves its chapter, on the last verse left behind, where it is
    now printed. Exchanged verses (Matthew 23:13-14) are noted at both."""
    prepared = dict(documents)
    result: list[Disposition] = [
        (
            {**row, "execution": "applied"}
            if row.get("disposition") == "structural"
            else row
        )
        for row in dispositions
    ]

    def refuse(row: Disposition, reason: str) -> None:
        row.update(refused(row, reason))

    for book, document in documents.items():
        rows = [
            r
            for r in result
            if r.get("disposition") == "structural"
            and r.get("execution") != "refused"
            and r["ref"].split()[0] == book
        ]
        if not rows:
            continue
        verses = scripture.verses(document)
        # A book's moves are one published exchange (Matthew 23:13–14, the
        # Romans doxology): moving only some would duplicate or lose a verse.
        passage = [r for r in rows if r["action"] == "move"]
        split_move = any(len(verses[r["ref"].split()[1]].parts) != 1 for r in passage)
        sources = [r["ref"].split()[1] for r in passage]
        targets = [r["target_ref"].split()[1] for r in passage]
        operations: list[Change] = []
        omitted: set[str] = set()
        # The verses moved out of their chapter: where each goes, the block
        # it stood in, and its content.
        moved_out: list[tuple[str, int, Content]] = []
        for row in rows:
            ref = row["ref"].split()[1]
            verse = verses[ref]
            if row["action"] == "omit":
                if verse.notes:
                    refuse(row, "existing source note on the omitted verse")
                    continue
                if len(verse.parts) != 1:
                    refuse(row, "structural omission crosses paragraphs")
                    continue
                chapter, number = map(int, ref.split(":"))
                home = f"{chapter}:{number - 1}"
                receiver = verses[home]
                quote = source_content(document, verse, 0, len(verse.text))
                note = edition_note(
                    home, "adds-verse", quote, f"{book} {home} TR", str(number)
                )
                row["note"] = note
                row["old"] = verse.text
                row["note_ref"] = book + " " + home
                operations.extend(
                    [
                        (verse, 0, len(verse.text), []),
                        (receiver, len(receiver.text), len(receiver.text), [note]),
                    ]
                )
                omitted.add(ref)
                continue
            target = row["target_ref"].split()[1]
            if structure.moved.get(row["ref"]) != row["target_ref"]:
                raise ValueError(f'Unrecognized structural move: {row["unit"]}')
            if split_move:
                refuse(row, "structural move crosses paragraphs")
                continue
            content = renumber(
                source_content(document, verse, 0, len(verse.text)), target
            )
            first = passage[0]["ref"] == row["ref"]
            moved_note = None
            # One location note on a passage's first verse; an exchanged
            # verse is a passage of its own.
            if target in verses or first:
                where = ref if target in verses else span(sources)
                moved_note = edition_note(
                    target, "moved", key=f"{book} {target} TR", where=where
                )
                content = usj.joined(content, [moved_note])
            row["old"] = verse.text
            row["note"] = moved_note
            if target in verses:
                receiver = verses[target]
                operations.append((receiver, 0, len(receiver.text), content))
                continue
            moved_out.append((target, verse.parts[0][0], content))
            operations.append((verse, 0, len(verse.text), []))
            omitted.add(ref)
            if first:
                # The passage's chapter keeps a note where it stood.
                chapter, number = map(int, ref.split(":"))
                home = f"{chapter}:{number - 1}"
                left = verses[home]
                source_note = edition_note(
                    home, "moved-out", key=f"{book} {home} TR", where=span(targets)
                )
                row["source_note"] = source_note
                row["source_note_ref"] = book + " " + home
                operations.append((left, len(left.text), len(left.text), [source_note]))
        changed = without_verses(scripture.edited(document, operations), omitted)
        if moved_out:
            # A passage moved out of its chapter keeps its one paragraph, and
            # leaves none behind: the only such move is the doxology, from
            # the end of Romans 16 to the end of Romans 14.
            held = {block for _, block, _ in moved_out}
            marker = document["content"][moved_out[0][1]]["marker"]
            items: Content = []
            for target, _, content in moved_out:
                label = target.split(":")[1]
                items += [{"type": "verse", "marker": "v", "number": label}, *content]
            following = int(moved_out[0][0].split(":")[0]) + 1
            blocks: list[Node] = []
            for index, block in enumerate(changed["content"]):
                if block["type"] == "chapter" and int(block["number"]) == following:
                    blocks.append(usj.para(marker, *items))
                if index in held and not usj.text_of(block["content"]).strip():
                    continue
                blocks.append(block)
            changed = usj.with_blocks(changed, blocks)
        prepared[book] = changed
    return prepared, result


def span(addresses: Sequence[str]) -> str:
    """ "16:25–27" for consecutive verses of one chapter, or the one address."""
    first, last = addresses[0], addresses[-1]
    if first == last:
        return first
    return f"{first}–{last.split(':')[1]}"
