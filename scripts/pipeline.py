#!/usr/bin/env python3
"""Offline preparation, typesetting, and acceptance checks for the combined Bible."""

import argparse
from collections import Counter
import configparser
import difflib
import functools
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

from source_inventory import MARKER, inventory, marker_counts, read_archive, sha256

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
BUILD = ROOT / "build"
DIST = ROOT / "dist"
# The PDF each command publishes under dist/; it builds in build/<command>.
OUTPUTS = {"sample": "sample.pdf", "pdf": "bible.pdf"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


EDITION = read_json("config/edition.json")
# The pinned source texts. An archive's hash pins every book in it.
SOURCES = {
    "brenton": {
        "archive": "sources/eng-Brenton_usfm.zip",
        "url": "https://ebible.org/Scriptures/eng-Brenton_usfm.zip",
        "retrieved": "2026-09-23",
        "sha256": "93496ef23f7ff2427c32f5d353089dee73e82975ab92c80a00663fb333c57e32",
    },
    "kjv": {
        "archive": "sources/engkjvcpb_usfm.zip",
        "url": "https://ebible.org/Scriptures/engkjvcpb_usfm.zip",
        "retrieved": "2026-09-23",
        "sha256": "7940a2d164513b2bd2dbec2c8570b89ef8673621ed4f30f3099218a7ddd04936",
    },
    "marginal_notes": {
        "file": "sources/exhaustive-listing-marginal-notes-1611-edition-king-james-bible.md",
        "url": "https://en.literaturabautista.com/exhaustive-listing-marginal-notes-1611-edition-king-james-bible",
        "retrieved": "2026-09-25",
    },
}
# The font archives the image was built from, relative to /opt as they are to
# the checkout. The image build checks their hashes; outside it there are none.
FONT_ARCHIVES = tuple(
    str(p.relative_to("/opt")) for p in sorted(Path("/opt/sources").glob("*.zip"))
)
MARGINAL_NOTES = read_json("config/marginal-notes.json")
UPSTREAM = Path("/opt/ptxprint")
# The generated PTXprint project, and where PTXprint writes its processed copies.
PROJECT_DIR = "projects/BIBLE"
PROCESSED_DIR = "local/ptxprint/Bible"
# Daniel is printed from three Brenton files, in this order.
DANIEL_PARTS = ("SUS", "DAG", "BEL")
HEADING_MARKERS = ("mt1", "mt2", "mt3")
EXPECTED_NT_MARGINAL_NOTES = 775
# The Epistle Dedicatory's mt2 lines are its address ("&c.") and salutation.
FRONT_PERIOD_FREE_TITLE_MARKERS = ("h", "toc1", "mt1")
# Every such heading, not just the first: OTH and BAK head book names with them.
FRONT_PERIOD_FREE_HEADING_MARKERS = ("is1", "is2")
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
# Notes, character styles and table cells, which PTXprint must keep...
NOTE_AND_STYLE_MARKERS = {"f", "x", "add", "it", "tr", "tc1", "tc2", "vp"}
# ...and the parts of notes, which preparation must keep as well.
NOTE_PART_MARKERS = {"fr", "ft", "fqa", "xo", "xt"}
# USFM's escapes for characters that would otherwise be markup.
ESCAPED_CHARACTERS = {
    "asterisk": "*",
    "percent": "%",
    "hash": "#",
    "dollar": "$",
    "ampersand": "&",
    "circumflex": "^",
    "space": " ",
}
GREEK = "\u0370-\u03ff\u1f00-\u1fff"
HEBREW = "\u0590-\u05ff"


class CheckFailed(RuntimeError):
    """A source, preparation, or output check refused the build."""


def require(condition, message):
    if not condition:
        raise CheckFailed(message)


def pinned_bytes(path, expected_sha256):
    """A pinned file's contents, refused unless they match the recorded hash."""
    data = Path(path).read_bytes()
    require(sha256(data) == expected_sha256, f"Checksum mismatch: {path}")
    return data


def file_sha256(path):
    return sha256(Path(path).read_bytes())


def recorder(log, code):
    """A function that logs one of a unit's transformations."""
    if log is None:
        log = []

    def record(operation, **details):
        log.append({"project_id": code, "operation": operation, **details})

    return record


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


def scripture_unit(code):
    return next(u for u in EDITION["scripture"] if u["id"] == code)


def source_id(entry):
    """The id of the source file an entry is printed from."""
    return entry.get("source_id", entry["id"])


def source_usfm(entry, archives):
    """The text an entry is prepared from: its source file, or the edition's own."""
    if "file" in entry:
        return Path(entry["file"]).read_text(encoding="utf-8")
    return archives[entry["source"]][source_id(entry)]


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


def source_marker(text, marker):
    match = re.search(r"^\\" + marker + r"\s+([^\n]+)", text, re.M)
    require(match is not None, f"Missing source {marker} marker")
    return match[1].strip()


def replace_marker_line(text, marker, value, code):
    """The text with the value of its first \\marker line replaced."""
    text, count = re.subn(
        r"^(\\" + marker + r"\s+)[^\n]*",
        lambda m: m[1] + value,
        text,
        count=1,
        flags=re.M,
    )
    require(count == 1, f"Missing {marker} heading: {code}")
    return text


def marker_lines(text, markers):
    """The (marker, value) pairs of the lines that open with one of the markers."""
    pattern = r"^\\(" + "|".join(markers) + r")\s+([^\n]*)$"
    return [
        (marker, value.strip()) for marker, value in re.findall(pattern, text, re.M)
    ]


def project_usfm(project, code):
    """A prepared unit's file in the PTXprint project."""
    return project / f"{code}.usfm"


def processed_usfm(project, code):
    """PTXprint's processed copy of a prepared unit."""
    return project / PROCESSED_DIR / f"{code}-Bible.usfm"


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


def book_names_element(entries, archives):
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


def run(*args, **kw):
    return subprocess.run([str(a) for a in args], check=True, **kw)


def capture(*args):
    return subprocess.check_output([str(a) for a in args], text=True)


def validate():
    archives = {
        name: read_archive(
            io.BytesIO(pinned_bytes(source["archive"], source["sha256"]))
        )
        for name, source in SOURCES.items()
        if "archive" in source
    }
    notes = marginal_notes()
    units = EDITION["scripture"]
    require(
        set(notes) <= {u["id"] for u in units if u["source"] == "kjv"},
        "Marginal notes name a book outside the KJV New Testament",
    )
    # A source divided between units must be printed whole, each chapter once.
    divided = {}
    for u in units:
        if "chapters" in u:
            first, last = u["chapters"]
            divided.setdefault((u["source"], source_id(u)), []).extend(
                str(c) for c in range(first, last + 1)
            )
    for (source, code), chapters in divided.items():
        require(
            chapters == list(inventory(archives[source][code])["chapters"]),
            f"Divided source not printed whole: {source}/{code}",
        )
    source_use = brenton_source_use()
    # Explain the overlapping witness without modifying either original file.
    nehemias = scripture_unit("NEH")
    first, last = nehemias["chapters"]
    _, combined_chapters = chapter_parts(archives["brenton"][source_id(nehemias)])
    _, standalone_nehemias_witness = chapter_parts(archives["brenton"]["NEH"])
    renumbered_nehemias_chapters = "".join(
        renumber_chapters(combined_chapters[first - 1 : last], first - 1)
    )
    standalone_nehemias_chapters = "".join(standalone_nehemias_witness)
    nehemias_source_diff = list(
        difflib.unified_diff(
            renumbered_nehemias_chapters.splitlines(True),
            standalone_nehemias_chapters.splitlines(True),
            fromfile=f"{source_id(nehemias)} chapters {first}-{last} (renumbered for comparison)",
            tofile="standalone NEH",
        )
    )
    BUILD.mkdir(exist_ok=True)
    (BUILD / "nehemias-differences.diff").write_text(
        "".join(nehemias_source_diff), encoding="utf-8"
    )
    report = {
        "scripture_units": len(units),
        "brenton_units": sum(u["source"] == "brenton" for u in units),
        "brenton_source_files": len(set(source_use)),
        "kjv_units": sum(u["source"] == "kjv" for u in units),
        "kjv_marginal_notes": sum(len(n) for n in notes.values()),
        "source_verse_labels": sum(
            len(verses)
            for source, code in {("brenton", c) for c in source_use}
            | {("kjv", u["id"]) for u in units if u["source"] == "kjv"}
            for verses in inventory(archives[source][code])["chapters"].values()
        ),
        "nehemias_equal_after_whitespace_normalization": (
            " ".join(renumbered_nehemias_chapters.split())
            == " ".join(standalone_nehemias_chapters.split())
        ),
        "nehemias_diff_lines": len(nehemias_source_diff),
    }
    write_json(BUILD / "validation.json", report)
    print("Validated pinned sources:", report, flush=True)
    return archives


def brenton_source_use():
    """Brenton source ids in the order the printed units draw on them."""
    source_use = []
    for unit in EDITION["scripture"]:
        if unit["source"] == "brenton":
            source_use.extend(
                DANIEL_PARTS if unit["id"] == "DAG" else [source_id(unit)]
            )
    return source_use


def ordered_entries():
    # Units are placed by section below; one in neither would silently vanish.
    scripture = EDITION["scripture"]
    unplaced = [
        u["id"]
        for u in scripture
        if u.get("section") not in ("old_testament", "new_testament")
    ]
    require(not unplaced, f"Scripture units outside both testaments: {unplaced}")
    return [
        # The editor's introduction is a project unit rather than a front-matter
        # periph so that it follows the contents page and is listed in it.
        {"id": "CNC", "file": "config/introduction.sfm"},
        # Each testament opens with its divider and its own translation's front matter.
        {"id": "XXF", "file": "config/old-testament.sfm"},
        *EDITION["old_testament_front"],
        *(u for u in scripture if u["section"] == "old_testament"),
        {"id": "XXG", "file": "config/new-testament.sfm"},
        *EDITION["new_testament_front"],
        *(u for u in scripture if u["section"] == "new_testament"),
        {"id": "GLO", "file": "config/appendices.sfm"},
        *EDITION["appendices"],
    ]


def chapter_parts(text):
    parts = re.split(r"(?=\\c \d+\s)", text)
    return parts[0], parts[1:]


def renumber_chapters(chapters, offset):
    """Chapters whose opening chapter marker is lowered by offset."""
    return [
        re.sub(r"^\\c (\d+)", lambda m: f"\\c {int(m[1]) - offset}", c, count=1)
        for c in chapters
    ]


def sample_chapters(code, text, wanted):
    """The header and the wanted chapters of a book, for the typesetting sample.

    A heading set just before a chapter marker (Susanna, Bel and the Dragon)
    opens that chapter, so it is kept or dropped with it. A chapter cannot
    continue the paragraph of an omitted chapter, so its nb becomes p.
    """
    header, chapters = chapter_parts(text)
    parts = [header, *chapters]
    for i in range(len(chapters)):
        lead_in = re.search(r"(?:\\s\d?\s[^\n]*\n)+\Z", parts[i])
        if lead_in:
            parts[i] = parts[i][: lead_in.start()]
            parts[i + 1] = lead_in[0] + parts[i + 1]
    kept = [parts[0]]
    previous_kept = True
    for part in parts[1:]:
        selected = int(re.search(r"\\c (\d+)", part)[1]) in wanted
        if selected:
            if not previous_kept:
                part = re.sub(r"(\\c \d+\s+)\\nb\b", r"\1\\p", part, count=1)
            kept.append(part)
        previous_kept = selected
    require(
        len(kept) - 1 == len(set(wanted)),
        f"Sample chapters missing from {code}: {wanted}",
    )
    return "".join(kept)


def passage_payload(text):
    """A wording witness that ignores only headings and displayed reference labels."""
    text = text[text.index(r"\c ") :]
    text = re.sub(r"\\s\d?\s+[^\n]*", "", text)
    text = re.sub(r"\\cp\s+[^\n]*", "", text)
    text = re.sub(r"\\(?:c|v)\s+\d+[a-z]?\s*", "", text)
    text = re.sub(r"\\(?:fr|xo)\s+\d+:\d+[a-z]?\s*", "", text)
    return canonical_text(text)


def preserved_markers(text):
    """Counts of the note and character-style markers, which preparation must keep."""
    kept = NOTE_AND_STYLE_MARKERS | NOTE_PART_MARKERS
    return {
        marker: count
        for marker, count in marker_counts(text).items()
        if marker.lstrip("+").rstrip("*") in kept
    }


@functools.cache
def marginal_notes():
    """The 1611 translators' New Testament marginal notes, by book, in source order.

    George's listing gives a reference, the words the note glosses (the lemma), and
    the note. The Old Testament entries belong to the Hebrew Old Testament, which
    this edition does not print, so they are never read.
    """
    text = Path(SOURCES["marginal_notes"]["file"]).read_text(encoding="utf-8")
    require(
        text.count("\nMatthew 1:11 ") == 1,
        "Marginal notes New Testament boundary changed",
    )
    books = MARGINAL_NOTES["books"]
    entry_pattern = re.compile(
        "(" + "|".join(map(re.escape, books)) + r") (\d+):(\d+) (.+?): (.+)"
    )
    corrections = dict(MARGINAL_NOTES["corrections"])
    anchors = MARGINAL_NOTES["anchors"]
    result = {}
    seen = Counter()
    for paragraph in re.split(r"\n\s*\n", text[text.index("\nMatthew 1:11 ") :]):
        # The Markdown wraps long entries; a continuation line joins its entry.
        entry = " ".join(paragraph.split())
        if not entry:
            continue
        match = entry_pattern.fullmatch(entry)
        require(match is not None, f"Unparsed marginal note: {entry}")
        book, chapter, verse, lemma, note = match.groups()
        code = books[book]
        key = f"{code} {chapter}:{verse} {lemma}"
        seen[key] += 1
        if seen[key] > 1:
            key += f"#{seen[key]}"
        if key in corrections:
            correction = corrections.pop(key)
            require(
                note.count(correction["from"]) == 1,
                f"Marginal note correction does not apply: {key}",
            )
            note = note.replace(correction["from"], correction["to"])
        require(
            "[" not in note and "]" not in note,
            f"Transcriber's remark left in marginal note: {key}",
        )
        result.setdefault(code, []).append(
            {
                "key": key,
                "chapter": chapter,
                "verse": verse,
                "lemma": lemma,
                "note": note,
            }
        )
    require(not corrections, f"Unused marginal note corrections: {sorted(corrections)}")
    keys = {n["key"] for notes in result.values() for n in notes}
    require(
        set(anchors) <= keys,
        f"Unused marginal note anchors: {sorted(set(anchors) - keys)}",
    )
    require(
        len(keys) == EXPECTED_NT_MARGINAL_NOTES,
        f"Expected {EXPECTED_NT_MARGINAL_NOTES} New Testament marginal notes, found {len(keys)}",
    )
    return result


def word_tokens(text):
    """Words with their offsets, ignoring markup, case, and punctuation.

    Markers are blanked rather than removed so that offsets index the USFM itself.
    Apostrophes join a word (king’s is kings); hyphens separate one (market-place).
    """
    masked = re.sub(MARKER, lambda m: " " * len(m[0]), text)
    return [
        (re.sub(r"[’']", "", m[0]).casefold(), m.start())
        for m in re.finditer(r"[A-Za-z]+(?:[’'][A-Za-z]+)*", masked)
    ]


def marginal_note_usfm(reference, note):
    # Brenton's own style: the label in fqa, the note in ft, a closing full stop.
    label = re.match(r"(Or,|Gr\.) ", note)
    body = f"\\fqa {label[1]} \\ft {note[label.end():]}" if label else f"\\ft {note}"
    if not body.endswith((".", "?", "!")):
        body += "."
    return f"\\f + \\fr {reference} {body}\\f*"


def verse_spans(text):
    """Each verse's reference with the offsets of its text, up to the next verse."""
    spans = []
    chapter = None
    markers = list(re.finditer(r"\\(c|v) (\S+)\s*", text))
    for index, m in enumerate(markers):
        if m[1] == "c":
            chapter = m[2]
            continue
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        spans.append((f"{chapter}:{m[2]}", m.end(), end))
    return spans


def insert_marginal_notes(code, text, record):
    """Set each marginal note as a footnote whose caller precedes the words it glosses.

    Brenton's callers, like the 1611 marks, stand before the glossed words, and so do
    these. A note is anchored at George's lemma, or at the Cambridge words recorded
    for it in config/marginal-notes.json where the spelling differs, the lemma occurs
    more than once, or the reference is wrong.
    """
    notes = marginal_notes().get(code, [])
    if not notes:
        return text
    require("\\f " not in text, f"Cambridge text already has footnotes: {code}")
    spans = {reference: (start, end) for reference, start, end in verse_spans(text)}
    inserts = {}
    for note in notes:
        override = MARGINAL_NOTES["anchors"].get(note["key"], {})
        reference = override.get("verse", f"{note['chapter']}:{note['verse']}")
        require(reference in spans, f"Marginal note verse missing: {note['key']}")
        start, end = spans[reference]
        anchor = [w for w, _ in word_tokens(override.get("anchor", note["lemma"]))]
        words = word_tokens(text[start:end])
        hits = [
            offset
            for i, (_, offset) in enumerate(words)
            if [w for w, _ in words[i : i + len(anchor)]] == anchor
        ]
        occurrence = override.get("occurrence")
        require(
            len(hits) == 1 if occurrence is None else 0 < occurrence <= len(hits),
            f"Marginal note anchor not found exactly once: {note['key']} ({len(hits)})",
        )
        position = start + hits[(occurrence or 1) - 1]
        # Keep the note outside a character style that opens on the glossed word.
        while opener := re.search(r"\\\+?(?:add|sc) $", text[start:position]):
            position = start + opener.start()
        preceding = text[start:position]
        require(
            len(re.findall(r"\\\+?(?:add|sc) ", preceding))
            == len(re.findall(r"\\\+?(?:add|sc)\*", preceding)),
            f"Marginal note caller inside a character span: {note['key']}",
        )
        inserts.setdefault(position, []).append(
            marginal_note_usfm(reference, note["note"])
        )
    original = text
    for position in sorted(inserts, reverse=True):
        text = text[:position] + "".join(inserts[position]) + text[position:]
    note_pattern = r"\\f \+ .*?\\f\*"
    require(
        len(re.findall(note_pattern, text)) == len(notes)
        and re.sub(note_pattern, "", text) == original,
        f"Marginal note insertion changed the text: {code}",
    )
    record(
        "insert 1611 translators' marginal notes (Calvin George's transcription)",
        source=SOURCES["marginal_notes"]["file"],
        count=len(notes),
        anchor_overrides=[
            n["key"] for n in notes if n["key"] in MARGINAL_NOTES["anchors"]
        ],
        corrected_notes=[
            n["key"] for n in notes if n["key"] in MARGINAL_NOTES["corrections"]
        ],
    )
    return text


def rename_book(entry, original, text, record):
    """The text with the edition's names and heading in place of the source's."""
    code = entry["id"]
    names = resolved_book_names(entry, original)
    text = replace_marker_line(text, "h", names["short_title"], code)
    for field, marker in BOOK_NAME_MARKERS.items():
        text = replace_marker_line(text, marker, names[field], code)
    # The whole heading is replaced, so the source's own subtitle lines go.
    # Only the header block before the first chapter is touched.
    head, chapters = chapter_parts(text)
    head = re.sub(r"^\\mt[23][^\n]*\n", "", head, flags=re.M)
    heading = "".join(
        f"\\{marker} {value}\n" for marker, value in heading_lines(entry, names)
    )
    head, count = re.subn(
        r"^\\mt1[^\n]*\n", lambda m: heading, head, count=1, flags=re.M
    )
    require(count == 1, f"Missing mt1 heading: {code}")
    text = head + "".join(chapters)
    markers = ("h", *BOOK_NAME_MARKERS.values(), *HEADING_MARKERS)
    source_lines = marker_lines(original, markers)
    edition_lines = marker_lines(text, markers)
    headings = {}
    for marker in markers:
        source_values = [v for m, v in source_lines if m == marker]
        edition_values = [v for m, v in edition_lines if m == marker]
        if source_values != edition_values:
            headings[marker] = {"source": source_values, "edition": edition_values}
    if headings:
        record("edition book headings replace the source headings", headings=headings)
    return text


def scripture_text(entry, archives, log=None):
    code = entry["id"]
    original = source_usfm(entry, archives)
    record = recorder(log, code)
    if "chapters" in entry:
        # Part of a source file that holds more than one book, numbered from 1.
        first, last = entry["chapters"]
        header, chapters = chapter_parts(original)
        require(
            0 < first <= last <= len(chapters),
            f"Manifest chapters outside the source: {code}",
        )
        selected = chapters[first - 1 : last]
        expected = header + "".join(selected)
        text = header + "".join(renumber_chapters(selected, first - 1))
        require(
            list(inventory(text)["chapters"])
            == [str(c) for c in range(1, last - first + 2)],
            f"Wrong chapter selection: {code}",
        )
        record(
            (
                "select source chapters"
                if first == 1
                else "select source chapters and relabel them"
            ),
            source_ids=[source_id(entry)],
            source_chapters=f"{first}-{last}",
            edition_chapters=f"1-{last - first + 1}",
        )
    elif code == "DAG":
        daniel_header, daniel_chapters = chapter_parts(original)
        _, susanna = chapter_parts(archives["brenton"]["SUS"])
        _, bel = chapter_parts(archives["brenton"]["BEL"])
        require(
            len(susanna) == len(bel) == 1 and len(daniel_chapters) == 12,
            "Daniel source boundaries changed",
        )
        expected = "".join(susanna + daniel_chapters + bel)
        susanna[0] = re.sub(
            r"^\\c 1",
            lambda m: "\\s1 SUSANNA\n\\c 0\n\\cp \u200b",
            susanna[0],
            count=1,
        )
        bel[0] = re.sub(
            r"^\\c 1",
            lambda m: "\\s1 BEL AND THE DRAGON\n\\c 13\n\\cp \u200b",
            bel[0],
            count=1,
        )
        daniel_chapters[2], song_heading = re.subn(
            r"(?=\\v 25 Then Azarias stood up, and prayed on this manner)",
            lambda m: "\\s1 THE SONG OF THE THREE CHILDREN\n\\p\n",
            daniel_chapters[2],
            count=1,
        )
        require(
            song_heading == 1, "Daniel 3 Song of the Three Children boundary changed"
        )
        text = daniel_header + "".join(susanna + daniel_chapters + bel)
        require(
            list(inventory(text)["chapters"]) == [str(i) for i in range(0, 14)],
            "Wrong chapter grouping: DAG",
        )
        record(
            "group Susanna and Bel and the Dragon with Daniel",
            source_ids=list(DANIEL_PARTS),
            chapter_labels={"SUS 1": "0", "BEL 1": "13"},
            added_section_headings=[
                "SUSANNA",
                "THE SONG OF THE THREE CHILDREN (before Daniel 3:25)",
                "BEL AND THE DRAGON",
            ],
        )
    else:
        expected = original
        text = original
    if code == "MAL":
        require(
            text.count(r"\v 19 For, behold") == 1, "Malachias chapter boundary changed"
        )
        prefix, tail = text.split(r"\v 19 For, behold", 1)
        # Open chapter 4 before the source's paragraph marker, not inside it.
        require(prefix.endswith("\\p\n"), "Malachias chapter 4 paragraph changed")
        prefix = prefix[: -len("\\p\n")]
        tail = "\\c 4\n\\p\n\\v 1 For, behold" + tail
        for old, new in zip(range(20, 25), range(2, 7)):
            tail = re.sub(
                r"\\v " + str(old) + r"(?=\s)",
                lambda m: r"\v " + str(new),
                tail,
                count=1,
            )
        text, xo = re.subn(r"\\xo 3:23\b", lambda m: r"\xo 4:5", prefix + tail)
        require(xo == 1, "Malachias 3:23 cross-reference origin changed")
        labels = inventory(text)["chapters"]
        require(list(labels) == ["1", "2", "3", "4"], "Wrong chapter grouping: MAL")
        require(
            labels["3"] == [str(i) for i in range(1, 19)]
            and labels["4"] == [str(i) for i in range(1, 7)],
            "Wrong Malachias 3-4 verse labels",
        )
        record(
            "relabel verses",
            source_ids=[source_id(entry)],
            source_verses="3:19-24",
            edition_verses="4:1-6",
            relabelled_note_origins={"3:23": "4:5"},
            moved_paragraph_marker="after the new chapter 4 marker",
        )
    text = rename_book(entry, original, text, record)
    require(
        passage_payload(expected) == passage_payload(text),
        f"Source wording changed: {code}",
    )
    require(
        preserved_markers(expected) == preserved_markers(text),
        f"Source notes or styling changed: {code}",
    )
    if entry["source"] == "kjv":
        # After the source comparisons above, which the added notes would fail.
        text = insert_marginal_notes(code, text, record)
    # Relabelling rewrites chapter and verse markers only, so every note must
    # still name the verse that holds it.
    require(
        all(
            ref == reference
            for reference, start, end in verse_spans(text)
            for ref in re.findall(r"\\(?:fr|xo) (\S+)", text[start:end])
        ),
        f"Note reference disagrees with its verse: {code}",
    )
    return text


def front_matter_text(entry, archives, log=None):
    """A translation's front matter or appendix, under the edition's names if any."""
    code = entry["id"]
    original = source_usfm(entry, archives)
    record = recorder(log, code)
    text = (
        rename_book(entry, original, original, record) if "title" in entry else original
    )
    titled = normalize_title_lines(text, FRONT_PERIOD_FREE_TITLE_MARKERS)
    titled, stripped_headings = re.subn(
        r"^(\\(?:"
        + "|".join(FRONT_PERIOD_FREE_HEADING_MARKERS)
        + r")\s+[^\n]*?)\.(\s*)$",
        r"\1\2",
        titled,
        flags=re.M,
    )
    if titled != text:
        record(
            "drop closing full stops from titles and headings",
            markers=list(
                FRONT_PERIOD_FREE_TITLE_MARKERS + FRONT_PERIOD_FREE_HEADING_MARKERS
            ),
            headings=stripped_headings,
        )
    require(
        inventory(original) == inventory(titled),
        f"Preparation changed source markup: {code}",
    )
    return titled


def typographic_text(code, text, record):
    """The text with the characters and markup the fonts and PTXprint need.

    Only the printable content's form changes, never its substance.
    """
    # GFS Didot does not encode U+02BC. Normalize Greek elision marks to the
    # typographic apostrophe it does encode before fixing the printable baseline.
    text, greek_apostrophes = re.subn(f"(?<=[{GREEK}])\u02bc", "\u2019", text)
    if greek_apostrophes:
        record(
            "normalize Greek U+02BC elision mark to U+2019 for GFS Didot",
            count=greek_apostrophes,
        )
    text, smartened = typographic_quotes(text)
    if smartened:
        record("typographic quotes, ellipses and dashes (SmartyPants)", count=smartened)
    # Every later edit must leave printable content unchanged, apart from the spacer.
    expected = canonical_text(text).replace("\u200b", "")
    # Keep the source's reference-only note in 1KI 6:1. Upstream deletes it
    # as empty unless a nonprinting body separates fr from the note end.
    text, empty_notes = re.subn(
        r"(\\f \+ \\fr [^\\]+)(?=\\f\*)", r"\1\\ft " + "\u200b", text
    )
    if empty_notes:
        record(
            "retain reference-only note with zero-width ft spacer", count=empty_notes
        )
    # Explicitly tag even single-letter quotations (the upstream heuristic misses
    # these). Keep the Greek apostrophe in the Greek font too.
    for marker, letters, continuation in (
        ("wh", HEBREW, HEBREW),
        ("wg", GREEK, "\u2019" + GREEK),
    ):
        word = f"[{letters}][\u0300-\u036f{continuation}]*"
        text, count = re.subn(
            f"{word}(?: +{word})*",
            lambda m: f"\\+{marker} {m[0]}\\+{marker}*",
            text,
        )
        if count:
            record("tag quotation runs", marker=marker, count=count)
    require(
        canonical_text(text).replace("\u200b", "") == expected,
        f"Preparation changed printable content: {code}",
    )
    return text


def prepare(mode, base, archives):
    """Write the PTXprint project; returns its folder and the order of its units."""
    project = base / PROJECT_DIR
    conf = project / "shared/ptxprint/Bible"
    conf.mkdir(parents=True)
    entries = ordered_entries()
    if mode == "sample":
        sample = read_json("config/sample.json")
        unknown = set(sample) - {u["id"] for u in EDITION["scripture"]}
        require(
            not unknown, f"Sample names units outside the edition: {sorted(unknown)}"
        )
        entries = [e for e in entries if "section" not in e or e["id"] in sample]
    ids = [e["id"] for e in entries]
    require(len(ids) == len(set(ids)), "Duplicate project id")
    transformations = []
    for entry in entries:
        code = entry["id"]
        record = recorder(transformations, code)
        if "file" in entry:
            text = source_usfm(entry, archives)
            require(text.startswith(f"\\id {code}\n"), f"Wrong id in {entry['file']}")
        else:
            if "section" in entry:
                text = scripture_text(entry, archives, transformations)
            else:
                text = front_matter_text(entry, archives, transformations)
            if code != source_id(entry):
                text, remapped = re.subn(r"^(\\id\s+)\S+", lambda m: m[1] + code, text)
                require(remapped == 1, f"Could not remap leading \\id to {code}")
                record(
                    "remap project id to retain it as a distinct ordered unit",
                    source=source_id(entry),
                )
            if mode == "sample" and "section" in entry:
                text = sample_chapters(code, text, sample[code])
                record(
                    "sample chapter selection; nb after an omitted chapter becomes p",
                    chapters=sample[code],
                )
            text = typographic_text(code, text, record)
        project_usfm(project, code).write_text(text, encoding="utf-8")
    write_json(base / "order.json", ids)
    transformations.append(
        {
            "operation": "protect literal pipes with U+E000 before XX module parsing; restore U+007C afterwards",
            "configuration": "config/changes.txt",
        }
    )
    write_json(base / "transformations.json", transformations)
    root = ET.Element("ScriptureText")
    # Only the settings PTXprint reads; without a Guid it would write its own.
    settings = {
        "FullName": EDITION["title"],
        "Guid": "407badbc319745d4b3cc9f242039a5ab",
        "Encoding": "65001",
        "LanguageIsoCode": "en",
        "DefaultFont": "Utopia",
        "Versification": "4",
        "FileNamePrePart": "",
        "FileNameBookNameForm": "MAT",
        "FileNamePostPart": ".usfm",
        "ChapterVerseSeparator": ":",
    }
    for key, value in settings.items():
        ET.SubElement(root, key).text = value
    ET.ElementTree(root).write(
        project / "Settings.xml", encoding="utf-8", xml_declaration=True
    )
    ET.ElementTree(book_names_element(entries, archives)).write(
        project / "BookNames.xml", encoding="utf-8", xml_declaration=True
    )
    with zipfile.ZipFile(UPSTREAM / "resources/bsb.zip") as z:
        baseline = z.read("shared/ptxprint/Default/ptxprint.cfg").decode()
        (conf / "ptxprint.sty").write_bytes(
            z.read("shared/ptxprint/Default/ptxprint.sty")
        )
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_string(baseline)
    # read() would silently skip a missing overlay and typeset BSB's layout.
    cfg.read_string(
        Path("config/layout.ini").read_text(encoding="utf-8"), "config/layout.ini"
    )
    cfg.remove_section("import")
    cfg["project"]["booklist"] = " ".join(ids)
    cfg["project"]["book"] = ids[0]
    with (conf / "ptxprint.cfg").open("w", encoding="utf-8") as f:
        cfg.write(f)
    for name in ("ptxprint-mods.sty", "ptxprint-mods.tex", "changes.txt"):
        shutil.copyfile(Path("config") / name, conf / name)
    front = Path("config/front.sfm").read_text(encoding="utf-8")
    if mode == "sample":
        require(r"\mt1 THE HOLY BIBLE" in front, "Cannot label the sample title page")
        front = front.replace(
            r"\mt1 THE HOLY BIBLE",
            "\\mt1 THE HOLY BIBLE\n\\mt3 TYPESETTING SAMPLE — selected chapters",
        )
    (conf / "FRTlocal.sfm").write_text(front, encoding="utf-8")
    return project, ids


def check_image():
    require(UPSTREAM.exists(), "Run this command through Make (make bootstrap first)")
    # The image keeps the pins it was built from; a stale image would typeset
    # with other tools or fonts than the ones pinned here.
    for name in ("Dockerfile", "requirements.txt", *FONT_ARCHIVES):
        require(
            Path("/opt", name).read_bytes() == Path(name).read_bytes(),
            f"The image was built from another {name}; run make bootstrap",
        )


def build(mode, archives):
    """Typeset one edition and check the PDF.

    Returns the PDF, the order of its units, and the report of its checks.
    """
    base = BUILD / mode
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    project, ids = prepare(mode, base, archives)
    home = base / "home"
    home.mkdir()
    env = os.environ.copy()
    env.update(
        HOME=str(home),
        XDG_CONFIG_HOME=str(home / "config"),
        XDG_CACHE_HOME=str(home / "cache"),
    )
    command = [
        "ptxprint",
        "-m",
        str(UPSTREAM / "src"),
        "-p",
        str(project.parent),
        "-c",
        "Bible",
        "-N",
        "-q",
        "-l",
        "INFO",
        "--logfile",
        str(base / "ptxprint.log"),
        "-R",
        "5",
        "-to",
        "1200",
        "BIBLE",
        "print",
    ]
    print("Typesetting", mode, "in", base, flush=True)
    with (base / "console.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=env)
    if result.returncode:
        print((base / "console.log").read_text(encoding="utf-8")[-6000:])
        raise RuntimeError(
            f"PTXprint failed ({result.returncode}); see {base}/console.log"
        )
    check_processed(project, base, ids)
    pdfs = list(project.rglob("*.pdf"))
    require(len(pdfs) == 1, f"Expected one PDF, found {pdfs}; see {base}/console.log")
    report = inspect_pdf(pdfs[0], base, project, ids, mode == "sample")
    return pdfs[0], ids, report


def publish(mode, pdf, ids, report):
    """Copy a checked PDF to dist/ with a record of what produced it."""
    target = DIST / OUTPUTS[mode]
    DIST.mkdir(exist_ok=True)
    tracked = {
        str(p): file_sha256(p)
        for folder in ("config", "scripts")
        for p in sorted(Path(folder).rglob("*"))
        if p.is_file() and "__pycache__" not in str(p)
    }
    for input_name in (
        "Dockerfile",
        "compose.yaml",
        "Makefile",
        "requirements.txt",
        # Not pinned by a hash like the archives, so record the copy that was read.
        SOURCES["marginal_notes"]["file"],
        *FONT_ARCHIVES,
    ):
        tracked[input_name] = file_sha256(input_name)
    fonts = {}
    for folder in (
        UPSTREAM / "fonts",
        *sorted(p for p in Path("/usr/local/share/fonts").iterdir() if p.is_dir()),
        Path("/usr/share/fonts/truetype/ezra"),
    ):
        files = sorted(p for p in folder.iterdir() if p.suffix in {".otf", ".ttf"})
        require(files, f"No font files to record in provenance: {folder}")
        for p in files:
            require(p.name not in fonts, f"Duplicate font file name: {p.name}")
            fonts[p.name] = file_sha256(p)
    provenance = {
        "title": EDITION["title"],
        "pdf_sha256": file_sha256(pdf),
        # The checkouts belong to root, which git refuses unless told otherwise.
        "upstream_commits": {
            name: capture(
                "git",
                "-c",
                "safe.directory=*",
                "-C",
                f"/opt/{name}",
                "rev-parse",
                "HEAD",
            ).strip()
            for name in ("ptxprint", "usfmtc", "utopia")
        },
        "source_archives": {
            k: {x: v[x] for x in ("url", "sha256", "retrieved") if x in v}
            for k, v in SOURCES.items()
        },
        "inputs": tracked,
        "order": ids,
        "checks": report,
        "fonts": fonts,
        "os_release": Path("/etc/os-release").read_text(encoding="utf-8").splitlines(),
        "python_version": sys.version,
        "os_packages": Path("/opt/os-packages.tsv")
        .read_text(encoding="utf-8")
        .splitlines(),
    }
    # Stage both outputs, then swap them in together so a failure never pairs a new
    # PDF with an old provenance record.
    provenance_target = target.with_suffix(".provenance.json")
    staged_pdf = target.with_suffix(".pdf.tmp")
    staged_provenance = target.with_suffix(".provenance.json.tmp")
    shutil.copyfile(pdf, staged_pdf)
    write_json(staged_provenance, provenance)
    provenance_target.unlink(missing_ok=True)
    staged_pdf.replace(target)
    staged_provenance.replace(provenance_target)
    print("Wrote", target, flush=True)


def render(mode):
    archives = validate()
    check_image()
    pdf, ids, report = build(mode, archives)
    publish(mode, pdf, ids, report)


def canonical_text(text):
    # Ignore only markup and whitespace; retain every source word, number and punctuation.
    text = re.sub(
        r"\\(" + "|".join(ESCAPED_CHARACTERS) + r")\b\s?",
        lambda m: ESCAPED_CHARACTERS[m[1]],
        text,
    )
    text = re.sub(MARKER + r"\s?", "", text)
    return re.sub(r"\s+", "", text)


def typographic_quotes(text):
    """Straight quotes, ellipses and double hyphens as typographic characters.

    SmartyPants curls each quote from its context. It reads USFM as plain text:
    it would take <...> for an HTML tag and a backslash before a quote, period,
    hyphen or backtick for an escape, so neither may occur. Its backtick option
    also turns every other ' into a closing quote, so the source's few `single'
    quotes are opened here instead.
    """
    import smartypants

    require("<" not in text, "Text looks like HTML to SmartyPants")
    require(not re.search(r"\\[\\\"'.`-]", text), "Text contains a SmartyPants escape")
    require("''" not in text and "``" not in text, "Ambiguous doubled quote characters")
    require(not re.search(r"`(?![A-Za-z])", text), "Backtick is not an opening quote")
    result = smartypants.smartypants(
        text.replace("`", "‘"),
        smartypants.Attr.q
        | smartypants.Attr.d
        | smartypants.Attr.e
        | smartypants.Attr.u,
    )

    def fold(s):
        for typographic, plain in {
            "‘": "'",
            "’": "'",
            "`": "'",
            "“": '"',
            "”": '"',
            "…": "...",
            "—": "--",
        }.items():
            s = s.replace(typographic, plain)
        return s

    require(
        inventory(result) == inventory(text) and fold(result) == fold(text),
        "SmartyPants changed more than quotes, ellipses and dashes",
    )
    plain = r"['\"`]|\.\.\.|--"
    require(
        not re.search(plain, result) and result.count("&#") == text.count("&#"),
        "SmartyPants left a straight quote or a character reference",
    )
    return result, len(re.findall(plain, text))


def processed_markers(markers):
    # Nested italic/quotation markers may be flattened by the module parser.
    result = {}
    for k, v in markers.items():
        k = k.lstrip("+")
        if k.rstrip("*") in NOTE_AND_STYLE_MARKERS:
            result[k] = result.get(k, 0) + v
    return result


def check_processed(project, base, ids):
    records = []
    texfiles = list((project / PROCESSED_DIR).glob("*_ptxp.tex"))
    require(len(texfiles) == 1, "Missing typesetting driver")
    tex = texfiles[0].read_text(encoding="utf-8")
    require(
        "%\\OmitCallerInNote{f}" in tex and "%\\OmitCallerInNote{x}" in tex,
        "Note callers unexpectedly suppressed",
    )
    for code in ids:
        source = project_usfm(project, code).read_text(encoding="utf-8")
        processed = processed_usfm(project, code)
        require(processed.exists(), f"PTXprint omitted {code}")
        output = processed.read_text(encoding="utf-8")
        before, after = inventory(source), inventory(output)
        require(
            before["chapters"] == after["chapters"],
            f"PTXprint changed chapter/verse labels: {code}",
        )
        content = canonical_text(output)
        require(
            canonical_text(source) == content,
            f"PTXprint changed printable content: {code}",
        )
        markers = processed_markers(after["markers"])
        require(
            processed_markers(before["markers"]) == markers,
            f"PTXprint changed notes, styles or tables: {code}",
        )
        require("\ue000" not in output, f"Unrestored pipe sentinel: {code}")
        records.append(
            {
                "id": code,
                "content_sha256": sha256(content.encode()),
                "chapters": after["chapters"],
                "preserved_markers": markers,
            }
        )
    write_json(base / "processed-integrity.json", records)


def check_boundaries(base, project, ids, text, pages, reading_text, sample):
    tocfiles = list(base.rglob("*_ptxp.toc"))
    require(len(tocfiles) == 1, "Missing/ambiguous contents file")

    def readtoc(path):
        main = (
            path.read_text(encoding="utf-8")
            .split("\\defTOC{main}{", 1)[1]
            .split("\n}", 1)[0]
        )
        return re.findall(
            r"\\doTOCline\{([^}]+)\}\{([^}]+)\}\{[^}]*\}\{[^}]*\}\{(\d+)\}", main
        )

    toc = readtoc(tocfiles[0])
    require(
        [r[0] for r in toc] == ids,
        "PDF contents omitted, duplicated or reordered units",
    )
    # Both files come from the final TeX run: PTXprint copies the raw TOC to _org.toc and
    # regenerates .toc from it. Convergence between runs is checked below, where the
    # printed contents page numbers must match these final pages.
    require(
        toc == readtoc(tocfiles[0].with_name(tocfiles[0].stem + "_org.toc")),
        "PTXprint's regenerated contents differ from the final TeX run",
    )
    page_text = text.split("\f")

    def key(s):
        return "".join(
            c for c in unicodedata.normalize("NFKC", s).casefold() if c.isalnum()
        )

    usfm = {
        code: project_usfm(project, code).read_text(encoding="utf-8") for code in ids
    }
    # The contents follows the title page and precedes the first unit.
    contents = key("".join(page_text[1 : int(toc[0][2]) - 1]))
    previous = 0
    for code, title, page in toc:
        page = int(page)
        require(previous < page <= pages, f"Invalid boundary page: {code} {page}")
        previous = page
        require(
            key(title) + str(page) in contents,
            f"Contents entry missing/wrong page in PDF: {code}",
        )
        heading = " ".join(
            value for _, value in marker_lines(usfm[code], HEADING_MARKERS)
        )
        require(heading, f"Missing heading: {code}")
        require(
            key(canonical_text(heading)) in key(page_text[page - 1]),
            f"Book heading not on advertised PDF page: {code} {page}",
        )
    write_json(
        base / "book-boundaries.json",
        [{"id": b, "title": t, "page": int(p)} for b, t, p in toc],
    )
    reading_pages = reading_text.split("\f")
    reading_pages_without_headers = []
    for page_number, page in enumerate(reading_pages, 1):
        lines = page.splitlines(keepends=True)
        # A running head carries the page number as one of its words.
        if lines and str(page_number) in lines[0].split():
            lines = lines[1:]
        reading_pages_without_headers.append("".join(lines))
    by_code = {b: (i, int(p)) for i, (b, t, p) in enumerate(toc)}
    for witness in read_json("config/render-witnesses.json"):
        code = witness["id"]
        if code not in by_code or (
            "chapter" in witness
            and witness["chapter"] not in inventory(usfm[code])["chapters"]
        ):
            # The sample deliberately selects only representative units and chapters.
            require(sample, f"Special-content witness not checked: {witness}")
            continue
        index, start = by_code[code]
        end = int(toc[index + 1][2]) - 1 if index + 1 < len(toc) else pages
        rendered = key("".join(reading_pages[start - 1 : end]))
        rendered_without_headers = key(
            "".join(reading_pages_without_headers[start - 1 : end])
        )
        require(
            key(witness["phrase"]) in rendered
            or key(witness["phrase"]) in rendered_without_headers,
            f"Special-content witness absent from rendered {code}: {witness['phrase']}",
        )


def check_note_callers(text):
    # Footnote and cross-reference callers restart on each page, so a caller that
    # introduces two different references on one page points readers at two notes.
    note = re.compile(r"(?:^|\s{2,})([a-z]|[*†‡§¶#]+) (\d+:\d+[a-z]?)\b", re.M)
    for number, page in enumerate(text.split("\f"), 1):
        refs = {}
        for caller, ref in note.findall(page):
            refs.setdefault(caller, set()).add(ref)
        clashes = sorted(c for c, r in refs.items() if len(r) > 1)
        require(not clashes, f"Note callers reused on PDF page {number}: {clashes}")


def check_added_words_roman(pdf, reading_text, project, ids, sample):
    # Malachias 4:2 has "\\add shall be\\add* in his wings". Check the added
    # words against their roman neighbours; "healing" may break as "heal- / ing".
    # Like the render witnesses, only the sample may leave the verse out.
    malachias = project_usfm(project, "MAL")
    if (
        "MAL" not in ids
        or "4" not in inventory(malachias.read_text(encoding="utf-8"))["chapters"]
    ):
        require(sample, "Added-word witness Malachias 4:2 is not in the build")
        return
    words = ["shall", "be", "in", "his", "wings"]
    pages = [
        number
        for number, page in enumerate(reading_text.split("\f"), 1)
        if " ".join(words) in " ".join(page.split())
    ]
    require(
        len(pages) == 1, f"Added-word witness Malachias 4:2 not found once: {pages}"
    )
    root = ET.fromstring(
        capture(
            "pdftohtml", "-xml", "-i", "-stdout", "-f", pages[0], "-l", pages[0], pdf
        )
    )
    families = {f.get("id"): f.get("family") for f in root.iter("fontspec")}
    runs = [
        (word, families[t.get("font")])
        for t in root.iter("text")
        for word in "".join(t.itertext()).split()
    ]
    for i in range(len(runs) - len(words) + 1):
        if [w.strip(":,") for w, _ in runs[i : i + len(words)]] == words:
            require(
                len({f for _, f in runs[i : i + len(words)]}) == 1,
                "Added words are not set in the surrounding roman font",
            )
            return
    raise CheckFailed("Added-word witness not found in PDF text runs")


def inspect_pdf(pdf, base, project, ids, sample):
    with (base / "qpdf.log").open("w", encoding="utf-8") as log:
        run("qpdf", "--check", pdf, stdout=log, stderr=subprocess.STDOUT)
    info = capture("pdfinfo", "-box", pdf)
    (base / "pdfinfo.txt").write_text(info, encoding="utf-8")
    pages = int(re.search(r"Pages:\s+(\d+)", info)[1])
    # Check every page, not just the first MediaBox.
    boxes = capture("pdfinfo", "-f", 1, "-l", pages, "-box", pdf)
    sizes = re.findall(r"(?:Page\s+\d+ size:|Page size:)\s+([\d.]+) x ([\d.]+)", boxes)
    require(len(sizes) == pages, "Could not inspect every PDF page")
    require(
        all(
            abs(float(w) - 419.528) < 0.1 and abs(float(h) - 595.276) < 0.1
            for w, h in sizes
        ),
        "Non-A5 page found",
    )
    fonts = capture("pdffonts", pdf)
    (base / "fonts.txt").write_text(fonts, encoding="utf-8")
    rows = fonts.splitlines()[2:]
    require(
        rows
        and all(
            re.search(r"\s+yes\s+(?:yes|no)\s+(?:yes|no)\s+\d+\s+\d+\s*$", r)
            for r in rows
        ),
        "Unembedded PDF font",
    )
    require(
        all(f in fonts for f in ("Utopia", "Erewhon", "GFSDidot", "Ezra")),
        "Expected text/verse-number/quotation fonts missing",
    )
    text = capture("pdftotext", "-layout", pdf, "-")
    (base / "text.txt").write_text(text, encoding="utf-8")
    require(not re.search(r"['\"`]", text), "Straight quote in the rendered PDF text")
    check_note_callers(text)
    # PTXprint emits columns in reading order. Protruding edge glyphs can make
    # pdftotext's geometric heuristics merge adjacent columns, so use stream
    # order for wording witnesses; keep the layout extraction above for pages.
    reading_text = capture("pdftotext", "-raw", pdf, "-")
    (base / "reading.txt").write_text(reading_text, encoding="utf-8")
    check_added_words_roman(pdf, reading_text, project, ids, sample)
    require(
        "Berean Standard Bible" not in text and "CC BY-NC-ND" not in text,
        "Inherited BSB publication text remains",
    )
    logs = "\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in base.rglob("*.log")
    )
    require(
        not re.search(
            r"Missing character:|There is no .* in font|! (?:Emergency stop|Fatal error|TeX capacity|Undefined control)",
            logs,
        ),
        "Missing glyph or TeX error; inspect logs",
    )
    check_boundaries(base, project, ids, text, pages, reading_text, sample)
    return {
        "pages": pages,
        "text_sha256": sha256(text.encode()),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["validate", "sample", "pdf"])
    args = parser.parse_args()
    try:
        if args.command == "validate":
            validate()
        else:
            render(args.command)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(1)
