"""USJ, the JSON form of USFM, as the model of every document the build handles.

A document is plain data: {"type": "USJ", "version": ..., "content": [...]}, whose
content holds book, chapter, para, and table objects; a para's content holds
strings, verse milestones, char objects, and notes. Nothing here is the build's
own invention but two things: a note may carry "x-key", the address of the
source note it was made from, and "x-scope", the words a manuscript decision
says it is about.

Documents are never changed in place. A stage builds new lists and objects for
what it changes and shares the rest.

Text is held with single spaces. A paragraph's words carry no space at either
end, nor before a verse number; the line breaks of the USFM are the writer's.
"""

import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from typing import Literal, NoReturn, TypedDict, TypeGuard, Unpack, overload

from bible.checks import CheckFailed, present, require


class Scope(TypedDict, total=False):
    declared: str | None
    lemma: str | None
    glossed: str | None
    # The witness an edition note of the New Testament names (the term of
    # byzantine.received.labels), None where it gives another rendering.
    witness: str | None
    # While the promote stage finishes a Textus Receptus note: what the note
    # says the TR has (byzantine.edit.NoteKind), and the verse or passage it
    # names. The note the edition prints declares only its lemma.
    kind: str
    where: str


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
        "loc": str,
        "id": str,
        "alt": str,
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
    "p m mi nb po pm q1 q2 qr qa qc qd lit b li1 imt1 ip im imi ib ili1 ili2 iex s1 s2 s3 ms1 ms2 sd1 sd2 is1 is2 d cl".split()
)
# Headings and divisions: no part of the verses or the introduction they stand among.
HEADINGS = frozenset("s1 s2 s3 ms1 ms2 sd1 sd2 cl lit".split())
CELLS = frozenset(f"{kind}{n}" for kind in ("tc", "th") for n in range(1, 8))
CHARS = frozenset("add bd fv it lik sc vp wg wh qs".split())
NOTES = frozenset("f x".split())
# The paragraphs of the body: prose, and the lines of a poem.
PROSE = frozenset("p m mi nb".split())
POEM = frozenset("q1 q2 qr".split())
BODY = PROSE | POEM
# The parts of a note, each of which runs to the next or to the note's end.
FIELDS = frozenset("fr ft fq fqa fk fl xo xt xta".split())
LABEL = re.compile(r"\d+[a-z]?(?:-\d+[a-z]?)?")
# A verse's printed number, right after the verse's own.
PRINTED = re.compile(r"\\vp ([^\\]*)\\vp\* ?")
# A category, a peripheral division's title and identifier, and the rest of
# a published chapter number's line.
CATEGORY = re.compile(r"([^\\]+)\\cat\*")
PERIPHERAL = re.compile(r'([^\n\\|]+)\|id="([^"\n]+)"')
LINE = re.compile(r"[^\n\\]*")
# What follows a marker that takes one: a note's caller, a book's code, a
# document's USFM version.
TOKEN = re.compile(r"(\S+) ?")
SPACES = re.compile(r"\s+")


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


def cell(marker: str, *content: str | Node) -> Node:
    return {
        "type": "table:cell",
        "marker": marker,
        "align": "start",
        "content": list(content),
    }


def row(*cells: Node) -> Node:
    return {"type": "table:row", "marker": "tr", "content": list(cells)}


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
    containers: list[Node] = []

    def blocks() -> Content:
        return containers[-1]["content"] if containers else root

    def fail(message: str, at: int) -> NoReturn:
        """Refuse the text, showing where."""
        raise CheckFailed(f"{message}: {text[max(0, at - 30) : at + 50]!r}")

    def content() -> Content:
        if inline:
            return inline[-1][1]["content"]
        if block is not None:
            return block["content"]
        return root

    def add_text(value: str, at: int) -> None:
        if not value:
            return
        if "\\" in value:
            fail("Malformed marker", at)
        if block is None and not inline and not fragment:
            if value.strip():
                fail("Text outside a paragraph", at)
            return
        items = content()
        if items and isinstance(items[-1], str):
            items[-1] += value
        else:
            items.append(value)

    def in_note() -> bool:
        return any(kind == "note" for kind, _ in inline)

    cursor = 0
    versioned = False
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
                    if kind != "field":
                        fail(f"Unclosed \\{_marker(node)}", at)
                if not (inline and inline[-1][1]["marker"] == name):
                    fail("Unmatched note end", at)
                inline.pop()
                continue
            if in_note():
                fail("Nested note", at)
            caller = TOKEN.match(text, end)
            if caller is None:
                fail("Missing note caller", at)
            cursor = caller.end()
            node = note(name, caller=caller[1])
            content().append(node)
            inline.append(("note", node))
        elif name == "cat":
            category = CATEGORY.match(text, end)
            if closing or category is None:
                fail("Invalid category", at)
            owner = next((n for kind, n in reversed(inline) if kind == "note"), None)
            if owner is None:
                owner = containers[-1] if containers else None
            if owner is None or owner["type"] not in {"note", "sidebar"}:
                fail("Category outside a note or sidebar", at)
            owner["category"] = category[1].strip()
            cursor = category.end()
        elif name == "ref":
            if closing:
                if not inline or inline[-1][0] != "ref":
                    fail("Unmatched reference end", at)
                _, node = inline.pop()
                # The location is an attribute of the reference, not its words.
                last = node["content"][-1] if node["content"] else ""
                if isinstance(last, str) and "|" in last:
                    words, loc = last.rsplit("|", 1)
                    node["content"][-1] = words
                    node["loc"] = loc.removeprefix("loc=").strip('" ')
                continue
            node = {"type": "ref", "content": []}
            content().append(node)
            inline.append(("ref", node))
        elif name in FIELDS:
            if closing or plus:
                fail("Invalid note field", at)
            if not (in_note() or fragment):
                fail("Note field outside a note", at)
            while inline and inline[-1][0] != "note":
                kind, node = inline.pop()
                if kind != "field":
                    fail(f"Unclosed \\{_marker(node)}", at)
            node = char(name)
            content().append(node)
            inline.append(("field", node))
        elif name in CHARS:
            if closing:
                if not (
                    inline
                    and inline[-1][0] == "char"
                    and inline[-1][1]["marker"] == name
                ):
                    fail("Unmatched character style", at)
                inline.pop()
                continue
            # A style nests in the one it stands in, with its + or without,
            # and within a note in the part of the note it stands in.
            node = char(name)
            content().append(node)
            inline.append(("char", node))
        else:
            if closing or plus:
                fail("Invalid marker", at)
            if fragment:
                fail("Block marker in a fragment", at)
            if inline:
                fail("Unclosed span or note", at)
            if name == "v":
                if not (block is not None and block["type"] == "para"):
                    fail("Verse outside a paragraph", at)
                label = LABEL.match(text, end)
                if label is None:
                    fail("Missing verse number", at)
                cursor = label.end() + (text[label.end() : label.end() + 1] == " ")
                verse: Node = {"type": "verse", "marker": "v", "number": label[0]}
                # The number a verse prints, in place of its own, stands
                # right after it, as usfmtc reads it.
                if printed := PRINTED.match(text, cursor):
                    verse["pubnumber"] = printed[1]
                    cursor = printed.end()
                assert block is not None
                block["content"].append(verse)
                continue
            if name in CELLS:
                if table is None:
                    fail("Table cell outside a row", at)
                block = cell(name)
                assert table is not None
                current = table["content"][-1]
                assert isinstance(current, dict)
                current["content"].append(block)
                continue
            block = None
            if name == "tr":
                if table is None:
                    table = {"type": "table", "content": []}
                    blocks().append(table)
                table["content"].append(row())
                continue
            table = None
            if name == "esb":
                if containers and containers[-1]["type"] == "sidebar":
                    fail("Nested sidebar", at)
                node = {"type": "sidebar", "marker": "esb", "content": []}
                blocks().append(node)
                containers.append(node)
            elif name == "esbe":
                if not containers or containers[-1]["type"] != "sidebar":
                    fail("Sidebar end without its beginning", at)
                containers.pop()
            elif name == "periph":
                if containers and containers[-1]["type"] == "sidebar":
                    fail("Peripheral division inside sidebar", at)
                containers.clear()
                line = PERIPHERAL.match(text, end)
                if line is None:
                    fail("Peripheral division without an identifier", at)
                node = {
                    "type": "periph",
                    "alt": line[1].strip(),
                    "id": line[2],
                    "content": [],
                }
                root.append(node)
                containers.append(node)
                cursor = line.end()
            elif name == "id":
                if any(n["type"] == "sidebar" for n in containers):
                    fail("Unclosed sidebar before a new book", at)
                containers.clear()
                code = TOKEN.match(text, end)
                if code is None:
                    fail("Missing book code", at)
                cursor = code.end()
                block = {"type": "book", "marker": "id", "code": code[1], "content": []}
                root.append(block)
            elif name == "usfm":
                # The version a document declares, once, which is its USJ version.
                if versioned:
                    fail("USFM version declared twice", at)
                if not (len(root) == 1 and is_type(root[0], "book")):
                    fail("USFM version not after the book", at)
                version = TOKEN.match(text, end)
                if version is None:
                    fail("Missing USFM version", at)
                if version[1] != VERSION:
                    fail("Unsupported USFM version", at)
                cursor = version.end()
                versioned = True
            elif name == "c":
                label = LABEL.match(text, end)
                if label is None:
                    fail("Missing chapter number", at)
                cursor = label.end()
                blocks().append({"type": "chapter", "marker": "c", "number": label[0]})
            elif name == "cp":
                # The number a chapter prints, in place of its own. One set
                # further into its chapter would be moved to its head.
                if not (
                    bool(blocks())
                    and is_type(blocks()[-1], "chapter")
                    and "pubnumber" not in blocks()[-1]
                ):
                    fail("Published chapter number not at the head of a chapter", at)
                line = LINE.match(text, end)
                chapter_node = blocks()[-1]
                assert isinstance(chapter_node, dict) and line is not None
                blocks()[-1] = {**chapter_node, "pubnumber": line[0].strip(" ")}
                cursor = line.end()
            else:
                if name not in PARAGRAPHS:
                    fail(f"Unsupported marker \\{name}", at)
                block = para(name)
                blocks().append(block)
    add_text(text[cursor:], cursor)
    require(not any(n["type"] == "sidebar" for n in containers), "Unclosed sidebar")
    for kind, node in inline:
        require(
            kind == "field" and fragment,
            f"Unclosed \\{_marker(node)} at the end of the text",
        )
    if fragment:
        return _tidy(root, edges=False)
    return document([_tidy_block(node) for node in objects(root)])


def _marker(node: Node) -> str:
    """An open span's marker: a reference has none but its type."""
    return node.get("marker", node["type"])


def _spaces(value: str) -> str:
    return SPACES.sub(" ", value)


def _tidy(content: Iterable[str | Node], *, edges: bool) -> Content:
    """Content with single spaces, and none at a paragraph's edges or before a
    verse number."""
    result: Content = []
    for item in content:
        if isinstance(item, str):
            item = _spaces(item)
            if not item:
                continue
            # A space never doubles across a character style's close: the
            # style's words give up a space they end with when one follows.
            if item.startswith(" ") and result and _ends_with_space(result[-1]):
                result[-1] = _without_trailing_space(result[-1])
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
    # Nor does a character style that closes the paragraph.
    if trimmed and _ends_with_space(trimmed[-1]):
        trimmed[-1] = _without_trailing_space(trimmed[-1])
    return trimmed


def trimmed(content: Iterable[str | Node]) -> Content:
    """Content with single spaces, and none at its edges or before a verse
    number: a paragraph's words as the parser leaves them."""
    return _tidy(content, edges=True)


def _ends_with_space(item: str | Node) -> bool:
    """Whether a character style's words, outside a note, end with a space."""
    if not is_type(item, "char") or item["marker"] in FIELDS or not item["content"]:
        return False
    last = item["content"][-1]
    return isinstance(last, str) and last.endswith(" ")


def _without_trailing_space(item: str | Node) -> Node:
    assert isinstance(item, dict)
    content = item["content"]
    last = content[-1]
    assert isinstance(last, str)
    trimmed = last.rstrip(" ")
    return {**item, "content": [*content[:-1], *([trimmed] if trimmed else [])]}


def _tidy_block(node: Node) -> Node:
    if node["type"] in {"sidebar", "periph"}:
        return {**node, "content": [_tidy_block(n) for n in objects(node["content"])]}
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
        return _inline(node, nested=False)
    # The writer nests and closes styles as this version does.
    require(node["version"] == VERSION, f"Unsupported USJ version: {node['version']}")
    return "\n".join(_block_lines(node["content"])) + "\n"


def _block_lines(blocks: Iterable[str | Node]) -> list[str]:
    lines: list[str] = []
    for block in objects(blocks):
        kind = block["type"]
        if kind == "book":
            lines.append(_line(f"\\id {block['code']}", block["content"]))
            # Declared once, after the book that opens the document.
            if len(lines) == 1:
                lines.append(f"\\usfm {VERSION}")
        elif kind == "chapter":
            lines.append(f"\\c {block['number']}")
            if "pubnumber" in block:
                lines.append(f"\\cp {block['pubnumber']}")
        elif kind == "table":
            for row in objects(block["content"]):
                lines.append("\\tr")
                for cell in objects(row["content"]):
                    lines.append(_line(f"\\{cell['marker']}", cell["content"]))
        elif kind == "sidebar":
            category = (
                f" \\cat {block['category']}\\cat*" if block.get("category") else ""
            )
            lines.append(f"\\esb{category}")
            lines.extend(_block_lines(block["content"]))
            lines.append("\\esbe")
        elif kind == "periph":
            lines.append(f'\\periph {block["alt"]}|id="{block["id"]}"')
            lines.extend(_block_lines(block["content"]))
        else:
            require(kind == "para", f"Unsupported block: {kind}")
            # Each verse opens a line of its own.
            head, verses = _split_verses(block["content"])
            lines.append(_line(f"\\{block['marker']}", head))
            lines.extend(_line(_verse_marker(verse), rest) for verse, rest in verses)
    return lines


def _verse_marker(verse: Node) -> str:
    # PTXprint reads a printed number only right after the verse's own.
    if "pubnumber" in verse:
        return f"\\v {verse['number']} \\vp {verse['pubnumber']}\\vp*"
    return f"\\v {verse['number']}"


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
    text = _inline(content, nested=False)
    return f"{marker} {text}" if text else marker


def _inline(content: Iterable[str | Node], *, nested: bool) -> str:
    parts = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif item["type"] == "note":
            # A part of a note runs to the next, so only parts can follow one.
            fields = [
                is_type(part, "char") and part["marker"] in FIELDS
                for part in item["content"]
            ]
            require(
                fields == sorted(fields),
                f"Content after a part of a note {item.get('x-key', 'without a key')}:"
                f" {item['content']!r}",
            )
            body = _inline(item["content"], nested=False)
            marker = item["marker"]
            category = f"\\cat {item['category']}\\cat*" if item.get("category") else ""
            parts.append(f"\\{marker} {item['caller']} {category}{body}\\{marker}*")
        elif item["type"] == "char":
            body = _inline(item["content"], nested=True)
            if item["marker"] in FIELDS:
                parts.append(f"\\{item['marker']} {body}")
            else:
                marker = ("+" if nested else "") + item["marker"]
                parts.append(f"\\{marker} {body}\\{marker}*")
        elif item["type"] == "ref":
            body = _inline(item["content"], nested=nested)
            target = f"|{item['loc']}" if item.get("loc") else ""
            parts.append(f"\\ref {body}{target}\\ref*")
        else:
            require(False, f"Unsupported inline content: {item['type']}")
    return "".join(parts)


# Reading a document.


def is_note(node: Node) -> bool:
    """What stands in a verse without being its words."""
    return node["type"] == "note"


def is_origin(node: object) -> bool:
    """A note's origin: the verse it names as its own."""
    return isinstance(node, dict) and node.get("marker") in ("fr", "xo")


def unlabelled(content: Iterable[str | Node]) -> str:
    """The words of content without its labels (is_label)."""
    return text_of(content, skip=is_label)


def is_label(node: Node) -> bool:
    """What stands in a paragraph without being its prose: a note's origin and
    the number of a verse that a supplied passage prints, in the text or in a
    note."""
    return is_origin(node) or node.get("marker") in ("vp", "fv")


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


def with_code(doc: Document, code: str) -> Document:
    """A document under another book code: a unit printed from a file that
    holds another, or under an id of its own."""
    book, *rest = doc["content"]
    return with_blocks(doc, [{**book, "code": code}, *rest])


def with_content(doc: Document, change: Callable[[Content], Content]) -> Document:
    """A document with the content of each paragraph and table cell given to
    change. Its \\id line is the source's own, and stays."""

    def block(node: Node) -> Node:
        if node["type"] in {"sidebar", "periph"}:
            return {**node, "content": [block(n) for n in objects(node["content"])]}
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


def extended(content: Content, items: Iterable[str | Node]) -> None:
    """Items appended to content in place, adjacent strings run together
    and empty strings left out."""
    for item in items:
        if isinstance(item, str) and content and isinstance(content[-1], str):
            content[-1] += item
        elif item != "":
            content.append(item)


def joined(*parts: Iterable[str | Node]) -> Content:
    """Content lists as one, adjacent strings run together."""
    result: Content = []
    for part in parts:
        extended(result, part)
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
    # A replacement explicitly retaining a style keeps its following words
    # in that span. Its start stays a boundary where a note can be placed.
    at = 0
    for index, item in enumerate(content):
        length = len(text_of([item]))
        if (
            is_type(item, "char")
            and item["marker"] not in FIELDS | {"add"}
            and new
            and is_type(new[0], "char", item["marker"])
            and at <= start < end <= at + length
        ):
            before, rest = split(item["content"], start - at, notes_left=False)
            _, after = split(rest, end - start, notes_left=True)
            head: Content = [{**item, "content": before}] if before else []
            inner = joined(new[0]["content"], new[1:], after)
            return joined(
                content[:index],
                head,
                [{**item, "content": inner}],
                content[index + 1 :],
            )
        at += length
    head, rest = split(content, start, notes_left=False)
    _, tail = split(rest, end - start, notes_left=True)
    return joined(head, new, tail)


def inserted(
    content: Content,
    offset: int,
    items: Content,
    *,
    after_notes: bool = True,
    split_styles: bool = False,
) -> Content:
    """The content with items set at an offset in its words, after the notes
    already there or before them. A destination inside a character style is
    refused unless split_styles divides it, keeping the items outside it."""
    head, tail = split(content, offset, notes_left=after_notes, whole=not split_styles)
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
                extended(result, [item])
            elif "content" in item and not skip(item):
                opened = at
                had_words = bool(text_of(item["content"], skip=skip))
                inner = visit(item["content"])
                if item["type"] == "char" and any(
                    a <= opened and at <= b for a, b in unwrap
                ):
                    extended(result, inner)
                elif inner or not had_words:
                    # Note fields consume their opening separator. A deletion
                    # can expose a word space there; keep it at the end of the
                    # preceding field, as when the note was first constructed.
                    if (
                        item["type"] == "char"
                        and item["marker"] in FIELDS
                        and inner != item["content"]
                        and inner
                        and isinstance(inner[0], str)
                        and result
                        and is_type(result[-1], "char")
                        and result[-1]["marker"] in FIELDS
                    ):
                        first = inner[0]
                        spaces = len(first) - len(first.lstrip(" "))
                        if spaces:
                            previous = result[-1]
                            result[-1] = {
                                **previous,
                                "content": joined(
                                    previous["content"], [first[:spaces]]
                                ),
                            }
                            inner = joined([first[spaces:]], inner[1:])
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
                extended(result, changed)
                continue
            item = changed
        extended(result, [item])
    return result


def without_notes(content: Iterable[str | Node]) -> Content:
    """The content without its notes, wherever they stand."""
    return mapped(content, lambda node: None if is_note(node) else node)


def replaced_by_identity(doc: Document, replacements: Mapping[int, Node]) -> Document:
    """The document with the objects in replacements, by their identity,
    replaced in place: mapped rebuilds every object, so an object found in
    the document is known by its identity alone."""

    def visit(content: Content) -> Content:
        return [
            (
                replacements[id(item)]
                if isinstance(item, dict) and id(item) in replacements
                else (
                    {**item, "content": visit(item["content"])}
                    if isinstance(item, dict) and "content" in item
                    else item
                )
            )
            for item in content
        ]

    return with_content(doc, visit)


def objects(content: Iterable[str | Node]) -> Iterator[Node]:
    """The objects of a block container, which cannot hold bare text."""
    for item in content:
        assert isinstance(item, dict)
        yield item


def paragraph(node: Node | None) -> str | None:
    """A paragraph's marker; None for any other block, or for none."""
    return node["marker"] if is_type(node, "para") else None
