"""The edition manifest (edition/manifest.json): which books are printed, in
what order, under what names, and how their headings break into lines."""

import re
import xml.etree.ElementTree as ET

from bible import paths
from bible.checks import require
from bible.files import read_json
from bible.usfm import HEADING_MARKERS, source_marker

MANIFEST = read_json(paths.EDITION_DIR / "manifest.json")
# Daniel is printed from three Brenton files, in this order.
DANIEL_PARTS = ("SUS", "DAG", "BEL")
BOOK_NAME_MARKERS = {
    "title": "toc1",
    "short_title": "toc2",
    "abbreviation": "toc3",
}
BOOK_NAME_ATTRIBUTES = {
    "abbreviation": "abbr",
    "short_title": "short",
    "title": "long",
}


def scripture_unit(code):
    return next(u for u in MANIFEST["scripture"] if u["id"] == code)


def source_id(entry):
    """The id of the source file an entry is printed from."""
    return entry.get("source_id", entry["id"])


def source_usfm(entry, archives):
    """The text an entry is prepared from: its source file, or the edition's own."""
    if "file" in entry:
        return (paths.ROOT / entry["file"]).read_text(encoding="utf-8")
    return archives[entry["source"]][source_id(entry)]


def brenton_source_use():
    """Brenton source ids in the order the printed units draw on them."""
    source_use = []
    for unit in MANIFEST["scripture"]:
        if unit["source"] == "brenton":
            source_use.extend(
                DANIEL_PARTS if unit["id"] == "DAG" else [source_id(unit)]
            )
    return source_use


def ordered_entries():
    # Units are placed by section below; one in neither would silently vanish.
    scripture = MANIFEST["scripture"]
    unplaced = [
        u["id"]
        for u in scripture
        if u.get("section") not in ("old_testament", "new_testament")
    ]
    require(not unplaced, f"Scripture units outside both testaments: {unplaced}")
    return [
        # The editor's introduction is a project unit rather than a front-matter
        # periph so that it follows the contents page and is listed in it.
        {"id": "CNC", "file": "content/introduction.sfm"},
        # Each testament opens with its divider and its own translation's front matter.
        {"id": "XXF", "file": "content/old-testament.sfm"},
        *MANIFEST["old_testament_front"],
        *(u for u in scripture if u["section"] == "old_testament"),
        {"id": "XXG", "file": "content/new-testament.sfm"},
        *MANIFEST["new_testament_front"],
        *(u for u in scripture if u["section"] == "new_testament"),
        {"id": "GLO", "file": "content/appendices.sfm"},
        *MANIFEST["appendices"],
    ]


def normalize_printed_title(value, marker):
    saint = "SAINT" if marker.startswith("mt") else "Saint"
    value = re.sub(r"(?<!\w)S\.(?=\s|$)", saint, value)
    return re.sub(r"\.(\s*)$", r"\1", value)


def normalize_title_lines(text, markers):
    for marker in markers:
        text = re.sub(
            r"^(\\" + marker + r"\s+)([^\n]*)$",
            lambda m: m[1] + normalize_printed_title(m[2], marker),
            text,
            count=1,
            flags=re.M,
        )
    return text


def resolved_book_names(entry, source_text):
    """The contents title, running-head title, and abbreviation of an entry.

    The edition's names replace the source's. Front matter that the edition
    does not rename keeps its source names, as preparation prints them.
    """
    if "title" not in entry and "section" not in entry:
        names = {
            field: source_marker(source_text, marker)
            for field, marker in BOOK_NAME_MARKERS.items()
        }
        names["title"] = normalize_printed_title(names["title"], "toc1")
        return names
    require(entry.get("title"), f"Missing title: {entry['id']}")
    return {
        "title": entry["title"],
        "short_title": entry.get("short_title") or source_marker(source_text, "toc2"),
        "abbreviation": entry.get("abbreviation") or source_marker(source_text, "toc3"),
    }


def heading_lines(entry, names):
    """The mt lines printed over a book, as (marker, text) pairs.

    As in the Cambridge KJV, the heading is the contents title itself. The
    manifest's optional "heading" says how to break it into lines and which
    line is the main one; without it the whole title is one mt1 line.
    """
    lines = entry.get("heading", [["mt1", names["title"]]])
    require(
        isinstance(lines, list)
        and all(
            isinstance(line, list)
            and len(line) == 2
            and line[0] in HEADING_MARKERS
            and isinstance(line[1], str)
            and line[1].strip() == line[1] != ""
            for line in lines
        )
        and sum(marker == "mt1" for marker, _ in lines) == 1,
        f"Invalid heading: {entry['id']}",
    )
    require(
        " ".join(text for _, text in lines) == names["title"],
        f"Heading lines do not spell the contents title: {entry['id']}",
    )
    return [(marker, text.upper()) for marker, text in lines]


def book_names_element(entries, archives):
    """PTXprint's BookNames.xml for the project's entries."""
    root = ET.Element("BookNames")
    for entry in entries:
        names = resolved_book_names(entry, source_usfm(entry, archives))
        ET.SubElement(
            root,
            "book",
            code=entry["id"],
            **{attr: names[field] for field, attr in BOOK_NAME_ATTRIBUTES.items()},
        )
    return root
