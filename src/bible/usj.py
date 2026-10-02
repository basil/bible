"""USJ, the JSON form of USFM, as the model of every document the build handles.

A document is plain data: {"type": "USJ", "version": ..., "content": [...]}, whose
content holds book, chapter, para and table objects; a para's content holds
strings, verse milestones, char objects and notes. Nothing here is the build's
own invention but two things: a note may carry "x-key", the address of the
source note it was made from, and "x-scope", the words a manuscript decision
says it is about.

Documents are never changed in place. A stage builds new lists and objects for
what it changes and shares the rest.

Text is held with single spaces. A paragraph's words carry no space at either
end, nor before a verse number; the line breaks of the USFM are the writer's.
"""

import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from typing import Literal, TypedDict, TypeGuard, Unpack, overload

from bible.checks import present, require


class Scope(TypedDict, total=False):
    declared: str | None
    lemma: str | None
    glossed: str | None


Node = TypedDict(
    "Node",
    {
        "type": str,
        "marker": str,
        "content": list["str | Node"],
        "caller": str,
        "code": str,
        "number": str,
        "pubnumber": str,
        "align": str,
        "category": str,
        "x-key": str,
        "x-scope": Scope,
    },
    total=False,
)

Extra = TypedDict(
    "Extra", {"x-key": str, "x-scope": Scope, "category": str}, total=False
)


class Document(TypedDict):
    type: str
    version: str
    content: list[Node]


type Content = list[str | Node]
type Predicate = Callable[[Node], bool]
type Change = Callable[[Node], Node | Content | None]


VERSION = "3.1"
MARKER = re.compile(r"\\(?P<plus>\+?)(?P<name>[a-z][a-z0-9-]*)(?P<close>\*?)")
BOOK_PARAGRAPHS = frozenset("h toc1 toc2 toc3 mt1 mt2 mt3".split())
PARAGRAPHS = BOOK_PARAGRAPHS | frozenset(
    "p m mi nb q1 qc b ip im imi ib iex s1 ms1 is1 is2 d".split()
)
CELLS = frozenset("tc1 tc2 th1 th2".split())
CHARS = frozenset("add it sc vp wg wh".split())
NOTES = frozenset("f ef x".split())
# The parts of a note, each of which runs to the next or to the note's end.
FIELDS = frozenset("fr ft fq fqa fl xo xt xta".split())
LABEL = re.compile(r"\d+[a-z]?(?:-\d+[a-z]?)?")


def is_type(node: object, kind: str, marker: str | None = None) -> TypeGuard[Node]:
    return (
        isinstance(node, dict)
        and node["type"] == kind
        and (marker is None or node.get("marker") == marker)
    )


def para(marker: str, *content: str | Node) -> Node:
    return {"type": "para", "marker": marker, "content": list(content)}


def char(marker: str, *content: str | Node) -> Node:
    return {"type": "char", "marker": marker, "content": list(content)}


def note(
    marker: str, *content: str | Node, caller: str = "-", **extra: Unpack[Extra]
) -> Node:
    result: Node = {
        "type": "note",
        "marker": marker,
        "caller": caller,
        "content": list(content),
    }
    if "x-key" in extra:
        result["x-key"] = extra["x-key"]
    if "x-scope" in extra:
        result["x-scope"] = extra["x-scope"]
    if "category" in extra:
        result["category"] = extra["category"]
    return result


def document(content: Iterable[Node]) -> Document:
    return {"type": "USJ", "version": VERSION, "content": list(content)}


@overload
def parse(text: str, *, fragment: Literal[False] = False) -> Document: ...


@overload
def parse(text: str, *, fragment: Literal[True]) -> Content: ...


@overload
def parse(text: str, *, fragment: bool) -> Document | Content: ...


def parse(text: str, *, fragment: bool = False) -> Document | Content:
    """Read USFM. A fragment is the inline content of a paragraph or a note,
    and comes back as a content list."""
    root: Content = []
    # The block that takes inline content, and the notes, note parts and
    # character styles open within it, innermost last.
    block: Node | None = None
    inline: list[tuple[str, Node]] = []
    table: Node | None = None

    def where(at: int) -> str:
        return f"{text[max(0, at - 30) : at + 50]!r}"

    def content() -> Content:
        if inline:
            return inline[-1][1]["content"]
        if block is not None:
            return block["content"]
        return root

    def add_text(value: str, at: int) -> None:
        if not value:
            return
        require("\\" not in value, f"Malformed marker: {where(at)}")
        if block is None and not inline and not fragment:
            require(not value.strip(), f"Text outside a paragraph: {where(at)}")
            return
        items = content()
        if items and isinstance(items[-1], str):
            items[-1] += value
        else:
            items.append(value)

    def in_note() -> bool:
        return any(kind == "note" for kind, _ in inline)

    cursor = 0
    for match in MARKER.finditer(text):
        if match.start() < cursor:
            continue
        add_text(text[cursor : match.start()], cursor)
        name, plus, closing = match["name"], bool(match["plus"]), bool(match["close"])
        end = at = match.end()
        if not closing and text[end : end + 1] in (" ", "\n") and end < len(text):
            end += 1
        cursor = end
        if name in NOTES:
            if closing:
                while inline and inline[-1][0] != "note":
                    kind, node = inline.pop()
                    require(
                        kind == "field", f"Unclosed \\{node['marker']}: {where(at)}"
                    )
                require(
                    inline and inline[-1][1]["marker"] == name,
                    f"Unmatched note end: {where(at)}",
                )
                inline.pop()
                continue
            require(not in_note(), f"Nested note: {where(at)}")
            caller = present(
                re.match(r"(\S+) ?", text[end:]), f"Missing note caller: {where(at)}"
            )
            cursor = end + caller.end()
            node = note(name, caller=caller[1])
            content().append(node)
            inline.append(("note", node))
        elif name in FIELDS:
            require(not closing and not plus, f"Invalid note field: {where(at)}")
            require(in_note() or fragment, f"Note field outside a note: {where(at)}")
            while inline and inline[-1][0] != "note":
                kind, node = inline.pop()
                require(kind == "field", f"Unclosed \\{node['marker']}: {where(at)}")
            node = char(name)
            content().append(node)
            inline.append(("field", node))
        elif name in CHARS:
            if closing:
                require(
                    inline
                    and inline[-1][0] == "char"
                    and inline[-1][1]["marker"] == name,
                    f"Unmatched character style: {where(at)}",
                )
                inline.pop()
                continue
            # Within a note, an unnested style ends the part of the note it follows.
            if not plus and inline and inline[-1][0] == "field":
                inline.pop()
            node = char(name)
            content().append(node)
            inline.append(("char", node))
        else:
            require(not closing and not plus, f"Invalid marker: {where(at)}")
            require(not fragment, f"Block marker in a fragment: {where(at)}")
            require(not inline, f"Unclosed span or note: {where(at)}")
            if name == "v":
                require(
                    block is not None and block["type"] == "para",
                    f"Verse outside a paragraph: {where(at)}",
                )
                label = present(
                    LABEL.match(text, end), f"Missing verse number: {where(at)}"
                )
                cursor = label.end() + (text[label.end() : label.end() + 1] == " ")
                assert block is not None
                block["content"].append(
                    {"type": "verse", "marker": "v", "number": label[0]}
                )
                continue
            if name in CELLS:
                require(table is not None, f"Table cell outside a row: {where(at)}")
                block = {
                    "type": "table:cell",
                    "marker": name,
                    "align": "start",
                    "content": [],
                }
                assert table is not None
                row = table["content"][-1]
                assert isinstance(row, dict)
                row["content"].append(block)
                continue
            block = None
            if name == "tr":
                if table is None:
                    table = {"type": "table", "content": []}
                    root.append(table)
                table["content"].append(
                    {"type": "table:row", "marker": "tr", "content": []}
                )
                continue
            table = None
            if name == "id":
                code = present(
                    re.match(r"(\S+) ?", text[end:]), f"Missing book code: {where(at)}"
                )
                cursor = end + code.end()
                block = {"type": "book", "marker": "id", "code": code[1], "content": []}
                root.append(block)
            elif name == "c":
                label = present(
                    LABEL.match(text, end), f"Missing chapter number: {where(at)}"
                )
                cursor = label.end()
                root.append({"type": "chapter", "marker": "c", "number": label[0]})
            elif name == "cp":
                # The number a chapter prints, in place of its own. One set
                # further into its chapter would be moved to its head.
                require(
                    bool(root)
                    and is_type(root[-1], "chapter")
                    and "pubnumber" not in root[-1],
                    f"Published chapter number not at the head of a chapter: {where(at)}",
                )
                line = re.match(r"[^\n\\]*", text[end:])
                chapter_node = root[-1]
                assert isinstance(chapter_node, dict) and line is not None
                root[-1] = {**chapter_node, "pubnumber": line[0].strip(" ")}
                cursor = end + line.end()
            else:
                require(name in PARAGRAPHS, f"Unsupported marker \\{name}: {where(at)}")
                block = para(name)
                root.append(block)
    add_text(text[cursor:], cursor)
    for kind, node in inline:
        require(
            kind == "field" and fragment,
            f"Unclosed \\{node['marker']} at the end of the text",
        )
    if fragment:
        return _tidy(root, edges=False)
    return document([_tidy_block(node) for node in objects(root)])


def _spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value)


def _tidy(content: Iterable[str | Node], *, edges: bool) -> Content:
    """Content with single spaces, and none at a paragraph's edges or before a
    verse number."""
    result: Content = []
    for item in content:
        if isinstance(item, str):
            item = _spaces(item)
            if not item:
                continue
        elif "content" in item:
            item = {**item, "content": _tidy(item["content"], edges=False)}
        result.append(item)
    if not edges:
        return result
    # A paragraph's words carry no space at either end, nor a verse's before
    # its first word, whatever notes stand there.
    trimmed: Content = []
    opening = True
    for index, item in enumerate(result):
        if isinstance(item, str):
            following = result[index + 1] if index + 1 < len(result) else None
            if opening:
                item = item.lstrip(" ")
            if following is None or is_type(following, "verse"):
                item = item.rstrip(" ")
            if not item:
                continue
            opening = False
        elif is_type(item, "verse"):
            opening = True
        elif not is_type(item, "note"):
            opening = False
        trimmed.append(item)
    return trimmed


def _tidy_block(node: Node) -> Node:
    if node["type"] == "table":
        return {
            **node,
            "content": [
                {
                    **row,
                    "content": [_tidy_block(cell) for cell in objects(row["content"])],
                }
                for row in objects(node["content"])
            ],
        }
    if "content" not in node:
        return node
    return {**node, "content": _tidy(node["content"], edges=True)}


def serialize(node: Document | Content) -> str:
    """Write USFM: a document, or a list of inline content."""
    if isinstance(node, list):
        return _inline(node, nested=False, in_note=False)
    lines = []
    for block in node["content"]:
        kind = block["type"]
        if kind == "book":
            lines.append(_line(f"\\id {block['code']}", block["content"]))
        elif kind == "chapter":
            lines.append(f"\\c {block['number']}")
            if "pubnumber" in block:
                lines.append(f"\\cp {block['pubnumber']}")
        elif kind == "table":
            for row in objects(block["content"]):
                lines.append("\\tr")
                for cell in objects(row["content"]):
                    lines.append(_line(f"\\{cell['marker']}", cell["content"]))
        else:
            require(kind == "para", f"Unsupported block: {kind}")
            # Each verse opens a line of its own.
            head, verses = _split_verses(block["content"])
            lines.append(_line(f"\\{block['marker']}", head))
            lines.extend(
                _line(f"\\v {verse['number']}", rest) for verse, rest in verses
            )
    return "\n".join(lines) + "\n"


def _split_verses(content: Content) -> tuple[Content, list[tuple[Node, Content]]]:
    head: Content = []
    parts: list[tuple[Node, Content]] = []
    for item in content:
        if is_type(item, "verse"):
            parts.append((item, []))
        elif not parts:
            head.append(item)
        else:
            parts[-1][1].append(item)
    return head, parts


def _line(marker: str, content: Iterable[str | Node]) -> str:
    text = _inline(content, nested=False, in_note=False)
    return f"{marker} {text}" if text else marker


def _inline(content: Iterable[str | Node], *, nested: bool, in_note: bool) -> str:
    parts = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif item["type"] == "note":
            body = _inline(item["content"], nested=False, in_note=True)
            marker = item["marker"]
            parts.append(f"\\{marker} {item['caller']} {body}\\{marker}*")
        elif item["type"] == "char" and item["marker"] in FIELDS:
            parts.append(
                f"\\{item['marker']} "
                + _inline(item["content"], nested=True, in_note=in_note)
            )
        elif item["type"] == "char":
            plus = "+" if nested else ""
            marker = item["marker"]
            parts.append(
                f"\\{plus}{marker} "
                + _inline(item["content"], nested=True, in_note=in_note)
                + f"\\{plus}{marker}*"
            )
        elif item["type"] == "ref":
            parts.append(_inline(item["content"], nested=nested, in_note=in_note))
        else:
            require(False, f"Unsupported inline content: {item['type']}")
    return "".join(parts)


# Reading a document.


def is_note(node: Node) -> bool:
    """What stands in a verse without being its words."""
    return node["type"] == "note"


def is_label(node: Node) -> bool:
    """What stands in a paragraph without being its prose: a note's origin and
    the number of a verse that a supplied passage prints."""
    return node.get("marker") in ("fr", "xo", "vp")


def text_of(content: Iterable[str | Node], *, skip: Predicate = is_note) -> str:
    """The words of some content, without the objects to skip."""
    parts = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif "content" in item and not skip(item):
            parts.append(text_of(item["content"], skip=skip))
    return "".join(parts)


def walk(content: Iterable[str | Node]) -> Iterator[Node]:
    """Every object in the content, outermost first."""
    for item in content:
        if isinstance(item, dict):
            yield item
            if "content" in item:
                yield from walk(item["content"])


def notes_of(content: Iterable[str | Node]) -> list[Node]:
    return [node for node in walk(content) if node["type"] == "note"]


def book_code(doc: Document) -> str:
    return doc["content"][0]["code"]


def inventory(doc: Document) -> dict[str, list[str]]:
    """The chapters of a document, each with its verses' labels in order."""
    chapters: dict[str, list[str]] = {}
    chapter: str | None = None
    for block in doc["content"]:
        if block["type"] == "chapter":
            chapter = block["number"]
            require(chapter not in chapters, f"Duplicate chapter {chapter}")
            chapters[chapter] = []
        elif block["type"] == "para":
            for item in block["content"]:
                if is_type(item, "verse"):
                    chapter = present(chapter, "Verse before a chapter")
                    require(
                        item["number"] not in chapters[chapter],
                        f"Duplicate verse {chapter}:{item['number']}",
                    )
                    chapters[chapter].append(item["number"])
    return chapters


def with_blocks(doc: Document, blocks: Iterable[Node]) -> Document:
    return {**doc, "content": list(blocks)}


def with_content(doc: Document, change: Callable[[Content], Content]) -> Document:
    """A document with the content of each paragraph and table cell given to
    change. Its \\id line is the source's own, and stays."""

    def block(node: Node) -> Node:
        if node["type"] == "table":
            return {
                **node,
                "content": [
                    {
                        **row,
                        "content": [block(cell) for cell in objects(row["content"])],
                    }
                    for row in objects(node["content"])
                ],
            }
        if "content" not in node or node["type"] == "book":
            return node
        return {**node, "content": change(node["content"])}

    return with_blocks(doc, [block(node) for node in doc["content"]])


# Changing content, by the offsets of its words.


def joined(*parts: Iterable[str | Node]) -> Content:
    """Content lists as one, adjacent strings run together."""
    result: Content = []
    for part in parts:
        for item in part:
            if isinstance(item, str) and result and isinstance(result[-1], str):
                result[-1] += item
            elif item != "":
                result.append(item)
    return result


def split(
    content: Sequence[str | Node],
    offset: int,
    *,
    notes_left: bool = True,
    whole: bool = False,
) -> tuple[Content, Content]:
    """The content before and after an offset in its words.

    A character style the offset falls within is divided, or refused if it
    must stay whole. Notes and verse numbers standing exactly at the offset go
    with the words before it, or after.
    """
    left: Content = []
    right: Content = []
    at = 0
    for index, item in enumerate(content):
        if isinstance(item, str):
            if at + len(item) <= offset and not right:
                left.append(item)
            elif at >= offset:
                right.append(item)
            else:
                left.append(item[: offset - at])
                right.append(item[offset - at :])
            at += len(item)
        elif is_note(item) or "content" not in item:
            (
                left
                if at < offset or (at == offset and notes_left and not right)
                else right
            ).append(item)
        else:
            length = len(text_of(item["content"]))
            if at + length <= offset and length and not right:
                left.append(item)
            elif at >= offset:
                right.append(item)
            else:
                require(not whole, f"Place inside a \\{item['marker']} span")
                before, after = split(
                    item["content"], offset - at, notes_left=notes_left
                )
                if before:
                    left.append({**item, "content": before})
                if after:
                    right.append({**item, "content": after})
            at += length
    return left, right


def replaced(content: Content, start: int, end: int, new: Content) -> Content:
    """The content with the words from start to end, and the notes among
    them, giving way to new content."""
    head, rest = split(content, start, notes_left=False)
    _, tail = split(rest, end - start, notes_left=True)
    return joined(head, new, tail)


def inserted(
    content: Content, offset: int, items: Content, *, after_notes: bool = True
) -> Content:
    """The content with items set at an offset in its words, after the notes
    already there or before them, and never inside a character style."""
    head, tail = split(content, offset, notes_left=after_notes, whole=True)
    return joined(head, items, tail)


def leaves(
    content: Iterable[str | Node], *, skip: Predicate = is_note
) -> list[tuple[int, int]]:
    """Each string of the content with the offsets of its words."""
    found: list[tuple[int, int]] = []
    at = 0

    def visit(items: Iterable[str | Node]) -> None:
        nonlocal at
        for item in items:
            if isinstance(item, str):
                found.append((at, at + len(item)))
                at += len(item)
            elif "content" in item and not skip(item):
                visit(item["content"])

    visit(content)
    return found


def substituted(
    content: Content,
    edits: Iterable[tuple[int, int, str]],
    *,
    skip: Predicate = is_note,
    right: bool = False,
    unwrap: Iterable[tuple[int, int]] = (),
) -> Content:
    """The content with stretches of its words rewritten in place.

    An edit is (start, end, words). The words stand in the first string the
    stretch touches, and what the stretch covers in other strings goes. An
    edit of no stretch adds to the string that ends at its place, or, from
    the right, to the one that starts there. A character style left without
    words goes with them; one whose words lie wholly within an unwrap range
    gives them to what holds it.
    """
    spans = leaves(content, skip=skip)
    changes: list[list[tuple[int, int, str]]] = [[] for _ in spans]
    for start, end, words in edits:
        if start == end:
            if right:
                touched = [i for i, (a, b) in enumerate(spans) if a <= start < b]
                touched = touched or [len(spans) - 1]
            else:
                touched = [i for i, (a, b) in enumerate(spans) if a < start <= b]
                touched = touched or [0]
            touched = touched[:1]
        else:
            touched = [i for i, (a, b) in enumerate(spans) if a < end and start < b]
        require(bool(spans) and touched, "Edit outside the words of its content")
        for n, index in enumerate(touched):
            a, b = spans[index]
            changes[index].append(
                (max(start - a, 0), min(end - a, b - a), words if n == 0 else "")
            )
    index = -1
    at = 0

    def visit(items: Iterable[str | Node]) -> Content:
        nonlocal index, at
        result: Content = []
        for item in items:
            if isinstance(item, str):
                index += 1
                at += len(item)
                for start, end, words in sorted(changes[index], reverse=True):
                    item = item[:start] + words + item[end:]
                result = joined(result, [item])
            elif "content" in item and not skip(item):
                opened = at
                had_words = bool(text_of(item["content"], skip=skip))
                inner = visit(item["content"])
                if item["type"] == "char" and any(
                    a <= opened and at <= b for a, b in unwrap
                ):
                    result = joined(result, inner)
                elif inner or not had_words:
                    result.append({**item, "content": inner})
            else:
                result.append(item)
        return result

    return visit(content)


def mapped(content: Iterable[str | Node], change: Change) -> Content:
    """The content with every object replaced by what change makes of it:
    an object, a list of content to stand in its place, or None to drop it.
    Children are mapped before their parents."""
    result: Content = []
    for item in content:
        if isinstance(item, dict):
            if "content" in item:
                item = {**item, "content": mapped(item["content"], change)}
            changed = change(item)
            if changed is None:
                continue
            if isinstance(changed, list):
                result = joined(result, changed)
                continue
            item = changed
        result = joined(result, [item])
    return result


def objects(content: Iterable[str | Node]) -> Iterator[Node]:
    """The objects of a block container, which cannot hold bare text."""
    for item in content:
        assert isinstance(item, dict)
        yield item
