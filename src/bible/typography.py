"""Typographic quotation marks, ellipses and dashes, in place of the sources'
straight quotes, triple periods and double hyphens.

SmartyPants curls each quote from the characters about it, so it is given a
document's words as a reader meets them: paragraph after paragraph, each verse
after its number, each note where it stands. Markup never reaches it; what it
changes is carried back to the strings the words came from.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections.abc import Callable, Sequence

from bible import usj
from bible.checks import require
from bible.usj import Content, Document

PLAIN = re.compile(r"['\"`]|\.\.\.|--")
OPENING = {"'": "‘", '"': "“"}


def _walk(
    doc: Document,
    text: Callable[[str], str],
    const: Callable[[str], object],
    note_end: Callable[[], object],
    comment: Callable[[], object],
) -> Document:
    """Visit a document's words in reading order. text(value) is given each
    string and returns what stands in its place; const(value) is given what
    is read between them."""

    def inline(content: Content) -> Content:
        result: Content = []
        previous: str | None = None
        for item in content:
            if isinstance(item, str):
                result.append(text(item))
            elif item["type"] == "verse":
                const(f"\n{item['number']} ")
                result.append(item)
            elif item["type"] == "note":
                const(f"{item['caller']} ")
                result.append({**item, "content": inline(item["content"])})
                note_end()
            elif "content" in item:
                marker = item.get("marker")
                # Commentary that follows a rendering or a citation.
                if marker == "ft" and previous in ("fq", "fqa", "xt"):
                    comment()
                if marker in usj.FIELDS:
                    previous = marker
                result.append({**item, "content": inline(item["content"])})
            else:
                result.append(item)
        return result

    blocks = []
    for block in doc["content"]:
        if block["type"] == "chapter":
            const(f"{block['number']}\n")
        elif block["type"] == "table":
            rows: Content = []
            for row in usj.objects(block["content"]):
                cells: Content = []
                for cell in usj.objects(row["content"]):
                    cells.append({**cell, "content": inline(cell["content"])})
                    const("\n")
                rows.append({**row, "content": cells})
            block = {**block, "content": rows}
        else:
            block = {**block, "content": inline(block["content"])}
            const("\n")
        blocks.append(block)
    return usj.with_blocks(doc, blocks)


def curled(text: str, comments: Sequence[int], note_ends: Sequence[int]) -> str:
    import smartypants

    require("<" not in text, "Text looks like HTML to SmartyPants")
    require("''" not in text and "``" not in text, "Ambiguous doubled quote characters")
    require(not re.search(r"`(?![A-Za-z])", text), "Backtick is not an opening quote")
    # The sources' few `single' quotes open with a backtick.
    text = text.replace("`", "‘")
    # A quotation that opens commentary after a rendering or a citation opens,
    # though no space stands before it.
    for at in comments:
        end = next((end for end in note_ends if end > at), len(text))
        if re.match(r"['\"]\w", text[at:end]):
            text = text[:at] + OPENING[text[at]] + text[at + 1 :]
    return str(
        smartypants.smartypants(
            text,
            smartypants.Attr.q
            | smartypants.Attr.d
            | smartypants.Attr.e
            | smartypants.Attr.u,
        )
    )


def typographic(doc: Document) -> Document:
    """A document with typographic quotes, ellipses and dashes."""
    parts: list[str] = []
    leaves: list[tuple[int, str]] = []
    comments: list[int] = []
    ends: list[int] = []
    length = 0

    def add(value: str, leaf: bool) -> str:
        nonlocal length
        if leaf:
            leaves.append((length, value))
        parts.append(value)
        length += len(value)
        return value

    _walk(
        doc,
        lambda value: add(value, True),
        lambda value: add(value, False),
        lambda: ends.append(length),
        lambda: comments.append(length),
    )
    plain = "".join(parts)
    if not PLAIN.search(plain):
        return doc
    quoted = curled(plain, comments, ends)
    # Carry each change back to the string it falls in.
    starts = [start for start, _ in leaves]
    values = [value for _, value in leaves]
    edits: dict[int, list[tuple[int, str]]] = {}
    i = j = 0
    while i < len(plain):
        if plain[i] == quoted[j]:
            i += 1
            j += 1
            continue
        n = (
            3
            if plain.startswith("...", i) and quoted[j] == "…"
            else 2 if plain.startswith("--", i) and quoted[j] == "—" else 1
        )
        require(
            plain[i : i + n] in ("'", '"', "`", "...", "--"),
            "Typography changed more than quotes, ellipses and dashes",
        )
        for step in range(n):
            leaf = bisect_right(starts, i + step) - 1
            offset = i + step - starts[leaf]
            require(
                leaf >= 0 and offset < len(values[leaf]),
                "Typography changed what is not the document's words",
            )
            edits.setdefault(leaf, []).append((offset, quoted[j] if step == 0 else ""))
        i += n
        j += 1
    require(j == len(quoted), "Typography added words")
    for leaf, changes in edits.items():
        value = values[leaf]
        for offset, new in reversed(changes):
            value = value[:offset] + new + value[offset + 1 :]
        values[leaf] = value
    replaced = iter(values)
    return _walk(
        doc,
        lambda value: next(replaced),
        lambda value: None,
        lambda: None,
        lambda: None,
    )


def count(doc: Document) -> int:
    """How many straight quotes, triple periods and double hyphens a document has."""
    found = 0

    def text(value: str) -> str:
        nonlocal found
        found += len(PLAIN.findall(value))
        return value

    _walk(doc, text, lambda value: None, lambda: None, lambda: None)
    return found
