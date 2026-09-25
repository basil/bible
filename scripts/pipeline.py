#!/usr/bin/env python3
"""Offline preparation, typesetting, and acceptance checks for the combined Bible."""

import argparse
from collections import Counter
import configparser
import difflib
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

from source_inventory import inventory, read_archive, sha256

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
EDITION = json.loads(Path("config/edition.json").read_text(encoding="utf-8"))
SOURCES = json.loads(Path("sources.json").read_text(encoding="utf-8"))
DEPS = json.loads(Path("dependencies.json").read_text(encoding="utf-8"))
UPSTREAM = Path("/opt/ptxprint")
NORMALIZED_TITLE_IDS = {
    "1SA",
    "2SA",
    "1KI",
    "2KI",
    "1CH",
    "2CH",
    "1ES",
    "EZR",
    "NEH",
    "ESG",
    "1MA",
    "2MA",
    "3MA",
    "SNG",
    "WIS",
    "SIR",
    "LAM",
    "DAG",
    "4MA",
}
PERIOD_FREE_TITLE_MARKERS = ("h", "toc1", "mt1", "mt2", "mt3")
BOOK_NAME_MARKERS = {
    "title": "toc1",
    "short_title": "toc2",
    "abbreviation": "toc3",
}


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def normalize_printed_title(value, marker):
    saint = "SAINT" if marker.startswith("mt") else "Saint"
    value = re.sub(r"(?<!\w)S\.(?=\s|$)", saint, value)
    return re.sub(r"\.(\s*)$", r"\1", value)


def source_marker(text, marker):
    match = re.search(r"^\\" + marker + r"\s+([^\n]+)", text, re.M)
    require(match is not None, f"Missing source {marker} marker")
    return match[1].strip()


def resolved_book_names(entry, source_text=None):
    title = entry.get("title")
    if not title and source_text is not None:
        title = source_marker(source_text, "h")
        return {"title": title, "short_title": title, "abbreviation": title}
    require(title, f"Missing title: {entry.get('id', entry.get('project_id'))}")
    if source_text is None:
        return {"title": title, "short_title": title, "abbreviation": title}
    return {
        "title": title,
        "short_title": entry.get("short_title") or source_marker(source_text, "toc2"),
        "abbreviation": entry.get("abbreviation") or source_marker(source_text, "toc3"),
    }


def book_names_element(entries, archives):
    root = ET.Element("BookNames")
    for entry in entries:
        code = entry.get("project_id", entry.get("id"))
        source_text = None
        if entry.get("source"):
            source_text = archives[entry["source"]][
                entry.get("source_id", entry["id"])
            ][2]
        elif "file" in entry:
            source_text = Path(entry["file"]).read_text(encoding="utf-8")
        names = resolved_book_names(entry, source_text)
        ET.SubElement(
            root,
            "book",
            code=code,
            abbr=names["abbreviation"],
            short=names["short_title"],
            long=names["title"],
        )
    return root


def run(args, **kw):
    return subprocess.run([str(a) for a in args], check=True, **kw)


def capture(*args):
    return subprocess.check_output([str(a) for a in args], text=True)


def validate():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    require(
        DEPS["base_image"] in dockerfile
        and f"SOURCE_DATE_EPOCH={DEPS['source_date_epoch']}" in dockerfile,
        "Dockerfile and dependency lock disagree",
    )
    greek_font = DEPS["gfs_porson"]
    greek_font_archive = Path(greek_font["archive"])
    require(
        sha256(greek_font_archive.read_bytes()) == greek_font["sha256"],
        f"Archive checksum mismatch: {greek_font_archive}",
    )
    archives = {}
    for name, source in SOURCES.items():
        path = Path(source["archive"])
        require(
            sha256(path.read_bytes()) == source["sha256"],
            f"Archive checksum mismatch: {path}",
        )
        data = read_archive(path)
        require(set(data) == set(source["files"]), f"Archive inventory changed: {path}")
        for code, (member, raw, text) in data.items():
            expected = source["files"][code]
            require(
                member == expected["member"] and sha256(raw) == expected["sha256"],
                f"Changed source: {name}/{code}",
            )
            require(
                inventory(text) == {k: expected[k] for k in ("chapters", "markers")},
                f"Changed inventory: {name}/{code}",
            )
        archives[name] = data
    units = EDITION["scripture"]
    ids = [u["id"] for u in units]
    require(len(ids) == len(set(ids)) == 78, "Expected 78 printed scripture units")
    require(
        sum(u["source"] == "brenton" for u in units) == 51,
        "Expected 51 printed Brenton units",
    )
    require(sum(u["source"] == "kjv" for u in units) == 27, "Expected 27 KJV units")
    orthodox = "GEN EXO LEV NUM DEU JOS JDG RUT 1SA 2SA 1KI 2KI 1CH 2CH MAN 1ES EZR NEH TOB JDT ESG 1MA 2MA 3MA 4MA PSA JOB PRO ECC SNG WIS SIR HOS AMO MIC JOL OBA JON NAM HAB ZEP HAG ZEC MAL ISA JER BAR LAM LJE EZK DAG".split()
    require(
        ids[: len(orthodox)] == orthodox and ids[len(orthodox)] == "MAT",
        "Orthodox Old Testament order changed",
    )
    require(
        "2ES" not in ids and "SUS" not in ids and "BEL" not in ids,
        "Unexpected separate scripture unit",
    )
    revised_titles = {
        "1SA": "1 Kingdoms",
        "2SA": "2 Kingdoms",
        "1KI": "3 Kingdoms",
        "2KI": "4 Kingdoms",
        "1CH": "1 Chronicles",
        "2CH": "2 Chronicles",
        "1ES": "1 Esdras",
        "EZR": "2 Esdras",
        "NEH": "Nehemiah",
        "ESG": "Esther",
        "DAG": "Daniel",
        "SNG": "Song of Songs",
        "SIR": "Wisdom of the Son of Sirach",
        "LAM": "Lamentations of Jeremias",
        "1MA": "1 Maccabees",
        "2MA": "2 Maccabees",
        "3MA": "3 Maccabees",
        "4MA": "4 Maccabees",
    }
    saint_headings = {
        "MAT": {"mt1": "SAINT MATTHEW"},
        "MRK": {"mt1": "SAINT MARK"},
        "LUK": {"mt1": "SAINT LUKE"},
        "JHN": {"mt1": "SAINT JOHN"},
        "REV": {"mt2": "SAINT JOHN THE DIVINE"},
    }
    for unit in units:
        if unit["source"] != "brenton":
            continue
        expected_title = revised_titles.get(unit["id"])
        if expected_title is None:
            source_text = archives["brenton"][unit["id"]][2]
            expected_title = re.search(r"\\toc1\s+([^\n]+)", source_text)[1].strip()
        require(
            unit["title"] == expected_title, f"Unexpected Brenton title: {unit['id']}"
        )
    for unit in units:
        text = scripture_text(unit, archives)
        markers = {
            marker: re.search(r"^\\" + marker + r"\s+([^\n]+)", text, re.M)[1].strip()
            for marker in ("h", "toc1", "toc2", "toc3", "mt1")
        }
        source_text = archives[unit["source"]][unit.get("source_id", unit["id"])][2]
        names = resolved_book_names(unit, source_text)
        require(
            markers["toc1"] == names["title"]
            and markers["h"] == markers["toc2"] == names["short_title"]
            and markers["toc3"] == names["abbreviation"],
            f"Generated book names disagree: {unit['id']}",
        )
        printed_title_lines = re.findall(
            r"^\\(?:h|toc1|mt[123])\s+([^\n]+)", text, re.M
        )
        require(
            all("." not in value for value in printed_title_lines),
            f"Printed title contains a period: {unit['id']}",
        )
        for marker, expected in saint_headings.get(unit["id"], {}).items():
            match = re.search(r"^\\" + marker + r"\s+([^\n]+)", text, re.M)
            require(
                match is not None and match[1].strip() == expected,
                f"Saint heading differs from edition style: {unit['id']}/{marker}",
            )
        if unit["id"] in NORMALIZED_TITLE_IDS:
            require(
                markers["mt1"] == unit["title"].upper(),
                f"Printed title differs from manifest: {unit['id']}",
            )
    xml_names = {
        book.get("code"): {
            "title": book.get("long"),
            "short_title": book.get("short"),
            "abbreviation": book.get("abbr"),
        }
        for book in book_names_element(ordered_entries(), archives)
    }
    for unit in units:
        source_text = archives[unit["source"]][unit.get("source_id", unit["id"])][2]
        require(
            xml_names[unit["id"]] == resolved_book_names(unit, source_text),
            f"BookNames.xml values disagree: {unit['id']}",
        )
    esdras_names = set(xml_names["EZR"].values())
    nehemiah_names = set(xml_names["NEH"].values())
    require(
        esdras_names.isdisjoint(nehemiah_names)
        and "Ezra and Nehemiah" not in esdras_names | nehemiah_names,
        "2 Esdras and Nehemiah must never share alternative names",
    )
    require(
        all(
            ("chapters" not in u or u["id"] in ("EZR", "NEH"))
            and ("source_parts" not in u or u["id"] == "DAG")
            for u in units
        ),
        "chapters and source_parts are only implemented for EZR/NEH and DAG",
    )
    source_use = []
    for unit in units:
        if unit["source"] == "brenton":
            source_use.extend(
                unit.get("source_parts", [unit.get("source_id", unit["id"])])
            )
    require(
        set(source_use)
        == {
            u
            for u in archives["brenton"]
            if u not in ("NEH", "FRT", "INT", "OTH", "XXA", "XXB", "XXC", "BAK")
        },
        "Brenton source selection changed",
    )
    require(
        all(
            source_use.count(code) == (2 if code == "EZR" else 1)
            for code in set(source_use)
        ),
        "Brenton source reused",
    )

    def selected(key):
        return [(e["source"], e["id"]) for e in EDITION[key]]

    require(
        selected("old_testament_front")
        == [
            ("brenton", "XXB"),
            ("brenton", "INT"),
            ("brenton", "OTH"),
            ("brenton", "FRT"),
        ],
        "Old Testament front matter changed",
    )
    require(
        selected("new_testament_front") == [("kjv", "OTH"), ("kjv", "INT")],
        "New Testament front matter changed",
    )
    require(
        selected("appendices")
        == [("brenton", "XXA"), ("brenton", "BAK"), ("brenton", "XXC")],
        "Appendices changed",
    )
    require(
        "Greatandmanifoldweretheblessings" in canonical_text(archives["kjv"]["OTH"][2]),
        "KJV dedication opening missing",
    )
    inv = SOURCES["brenton"]["files"]
    require(
        list(inv["EZR"]["chapters"]) == [str(i) for i in range(1, 24)],
        "Combined Ezra–Nehemiah must have 23 chapters",
    )
    require("151" in inv["PSA"]["chapters"], "Psalm 151 missing")
    require("1b" in inv["ESG"]["chapters"]["1"], "Esther additions missing")
    require(len(inv["DAG"]["chapters"]["3"]) > 90, "Daniel chapter 3 additions missing")
    for b in ("MAN", "3MA", "4MA"):
        require(bool(inv[b]["chapters"]), f"{b} missing")
    entries = ordered_entries()
    ordered_ids = [e.get("project_id", e.get("id")) for e in entries]

    # Each testament's front matter sits between its divider and its first book.
    def follows(*codes):
        first = ordered_ids.index(codes[0])
        return ordered_ids[first : first + len(codes)] == list(codes)

    require(ordered_ids[0] == "CNC", "Editor's introduction must open the book")
    require(
        follows("CNC", "XXF", "XXB", "XXE", "OTH", "XXD", "GEN"),
        "Old Testament front matter misplaced",
    )
    require(
        follows("DAG", "XXG", "TDX", "NDX", "MAT"),
        "New Testament front matter misplaced",
    )
    require(
        follows("REV", "GLO", "XXA", "BAK", "XXC") and ordered_ids[-1] == "XXC",
        "Appendices misplaced",
    )
    require(
        "THE APOCRYPHA" not in Path("config/front.sfm").read_text(encoding="utf-8"),
        "Obsolete Apocrypha divider/title remains",
    )
    require(
        "\\periph" not in Path("config/introduction.sfm").read_text(encoding="utf-8"),
        "The editor's introduction is a unit, not a front-matter periph",
    )
    # Explain the overlapping witness without modifying either original file.
    ezr = archives["brenton"]["EZR"][2]
    neh = archives["brenton"]["NEH"][2]
    tail = re.split(r"(?=\\c 11\s)", ezr, maxsplit=1)[1]
    tail = re.sub(r"\\c (\d+)", lambda m: "\\c " + str(int(m[1]) - 10), tail)
    neh = neh[neh.index("\\c 1") :]

    def normalized(s):
        return re.sub(r"\s+", " ", s).strip()

    diff = list(
        difflib.unified_diff(
            tail.splitlines(True),
            neh.splitlines(True),
            fromfile="EZR chapters 11–23 (renumbered for comparison)",
            tofile="standalone NEH",
        )
    )
    Path("build").mkdir(exist_ok=True)
    Path("build/nehemiah-differences.diff").write_text("".join(diff), encoding="utf-8")
    report = {
        "scripture_units": len(units),
        "brenton_units": sum(u["source"] == "brenton" for u in units),
        "brenton_source_files": len(set(source_use)),
        "kjv_units": sum(u["source"] == "kjv" for u in units),
        "source_verse_labels": sum(
            sum(len(v) for v in SOURCES["brenton"]["files"][code]["chapters"].values())
            for code in set(source_use)
        )
        + sum(
            sum(len(v) for v in SOURCES["kjv"]["files"][u["id"]]["chapters"].values())
            for u in units
            if u["source"] == "kjv"
        ),
        "nehemiah_equal_after_whitespace_normalization": normalized(tail)
        == normalized(neh),
        "nehemiah_diff_lines": len(diff),
    }
    write_json("build/validation.json", report)
    print("Validated pinned sources:", report, flush=True)
    return archives


def ordered_entries():
    result = []

    def add_div(code, title, subtitle):
        # Subtitle lines mirror the title page in config/front.sfm.
        result.append(
            {
                "project_id": code,
                "title": title,
                "subtitle": subtitle,
                "generated": True,
            }
        )

    # The editor's introduction is a project unit rather than a front-matter periph so
    # that it follows the contents page and is listed in it.
    result.append({"project_id": "CNC", "file": "config/introduction.sfm"})
    # Each testament opens with its divider and its own translation's front matter.
    add_div("XXF", "THE OLD TESTAMENT", ["Brenton’s Septuagint"])
    result.extend(EDITION["old_testament_front"])
    result.extend(u for u in EDITION["scripture"] if u["section"] == "old_testament")
    add_div(
        "XXG",
        "THE NEW TESTAMENT",
        ["Scrivener’s Cambridge Paragraph Bible", "King James Version"],
    )
    result.extend(EDITION["new_testament_front"])
    result.extend(u for u in EDITION["scripture"] if u["section"] == "new_testament")
    add_div(
        "GLO",
        "APPENDICES",
        ["Brenton’s Jeremiah table and notes", "eBible’s corrections to the text"],
    )
    result.extend(EDITION["appendices"])
    return result


def chapter_parts(text):
    parts = re.split(r"(?=\\c \d+\s)", text)
    return parts[0], parts[1:]


def passage_payload(text):
    """A wording witness that ignores only headings and displayed reference labels."""
    text = text[text.index(r"\c ") :]
    text = re.sub(r"\\s\d?\s+[^\n]*", "", text)
    text = re.sub(r"\\cp\s+[^\n]*", "", text)
    text = re.sub(r"\\(?:c|v)\s+\d+[a-z]?\s*", "", text)
    text = re.sub(r"\\(?:fr|xo)\s+\d+:\d+[a-z]?\s*", "", text)
    return canonical_text(text)


def preserved_markers(text):
    result = {}
    for marker, count in Counter(re.findall(r"\\(\+?[\w-]+\*?)", text)).items():
        name = marker.lstrip("+").rstrip("*")
        if name in (
            "f",
            "fr",
            "ft",
            "fqa",
            "x",
            "xo",
            "xt",
            "add",
            "it",
            "tr",
            "tc1",
            "tc2",
            "vp",
        ):
            result[marker] = count
    return result


def scripture_text(entry, archives, log=None):
    code = entry["id"]
    source_id = entry.get("source_id", code)
    original = archives[entry["source"]][source_id][2]
    names = resolved_book_names(entry, original)

    def record(operation, **details):
        if log is not None:
            log.append({"project_id": code, "operation": operation, **details})

    if code in ("EZR", "NEH"):
        # The split below is fixed; the manifest's chapters field must describe it.
        require(
            entry.get("chapters") == ([1, 10] if code == "EZR" else [11, 23]),
            f"Manifest chapters disagree with the Ezra–Nehemiah split: {code}",
        )
        header, chapters = chapter_parts(original)
        require(len(chapters) == 23, "Ezra–Nehemiah source boundary changed")
        selected = chapters[:10] if code == "EZR" else chapters[10:]
        if code == "NEH":
            selected = [
                re.sub(
                    r"^\\c (\d+)", lambda m: r"\c " + str(int(m[1]) - 10), c, count=1
                )
                for c in selected
            ]
            record(
                "select source chapters and relabel them",
                source_ids=[source_id],
                source_chapters="11–23",
                edition_chapters="1–13",
            )
        else:
            record(
                "select source chapters",
                source_ids=[source_id],
                source_chapters="1–10",
            )
        expected = header + "".join(chapters[:10] if code == "EZR" else chapters[10:])
        text = header + "".join(selected)
    elif code == "DAG":
        # The grouping below is fixed; the manifest's source_parts must describe it.
        require(
            entry.get("source_parts") == ["SUS", "DAG", "BEL"],
            "Manifest source_parts disagree with the Daniel grouping",
        )
        daniel_header, daniel_chapters = chapter_parts(original)
        _, susanna = chapter_parts(archives["brenton"]["SUS"][2])
        _, bel = chapter_parts(archives["brenton"]["BEL"][2])
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
        record(
            "group Susanna and Bel and the Dragon with Daniel",
            source_ids=["SUS", source_id, "BEL"],
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
        record(
            "relabel verses",
            source_ids=[source_id],
            source_verses="3:19–24",
            edition_verses="4:1–6",
            relabelled_note_origins={"3:23": "4:5"},
            moved_paragraph_marker="after the new chapter 4 marker",
        )
    for field, marker in BOOK_NAME_MARKERS.items():
        text, count = re.subn(
            r"(\\" + marker + r"\s+)[^\n]*",
            lambda m: m[1] + names[field],
            text,
            count=1,
        )
        require(count == 1, f"Missing {marker} heading: {code}")
    text, count = re.subn(
        r"(\\h\s+)[^\n]*",
        lambda m: m[1] + names["short_title"],
        text,
        count=1,
    )
    require(count == 1, f"Missing h heading: {code}")
    if code in NORMALIZED_TITLE_IDS:
        title = entry["title"]
        text, count = re.subn(
            r"(\\mt1\s+)[^\n]*",
            lambda m: m[1] + title.upper(),
            text,
            count=1,
        )
        require(count == 1, f"Missing mt1 heading: {code}")
        if code == "SIR":
            text = re.sub(r"\\mt2\s+[^\n]*\n", "", text, count=1)
    for marker in PERIOD_FREE_TITLE_MARKERS:
        text = re.sub(
            r"^(\\" + marker + r"\s+)([^\n]*)$",
            lambda m: m[1] + normalize_printed_title(m[2], marker),
            text,
            count=1,
            flags=re.M,
        )
    headings = {}
    for marker in ("h", "toc1", "toc2", "toc3", "mt1", "mt2", "mt3"):
        pattern = r"^\\" + marker + r"\s+([^\n]*)$"
        source_values = [v.strip() for v in re.findall(pattern, original, re.M)]
        edition_values = [v.strip() for v in re.findall(pattern, text, re.M)]
        if source_values != edition_values:
            headings[marker] = {"source": source_values, "edition": edition_values}
    if headings:
        record("edition book headings replace the source headings", headings=headings)
    require(
        passage_payload(expected) == passage_payload(text),
        f"Source wording changed: {code}",
    )
    require(
        preserved_markers(expected) == preserved_markers(text),
        f"Source notes or styling changed: {code}",
    )
    expected_chapters = {
        "EZR": [str(i) for i in range(1, 11)],
        "NEH": [str(i) for i in range(1, 14)],
        "DAG": ["0"] + [str(i) for i in range(1, 14)],
        "MAL": ["1", "2", "3", "4"],
    }
    if code in expected_chapters:
        require(
            list(inventory(text)["chapters"]) == expected_chapters[code],
            f"Wrong chapter grouping: {code}",
        )
    if code == "MAL":
        chapters = inventory(text)["chapters"]
        require(
            chapters["3"] == [str(i) for i in range(1, 19)]
            and chapters["4"] == [str(i) for i in range(1, 7)],
            "Wrong Malachias 3–4 verse labels",
        )
    return text


def prepare(mode, base, archives):
    project = base / "projects/BIBLE"
    conf = project / "shared/ptxprint/Bible"
    conf.mkdir(parents=True)
    entries = ordered_entries()
    if mode == "sample":
        sample = json.loads(Path("config/sample.json").read_text(encoding="utf-8"))
        entries = [e for e in entries if "section" not in e or e["id"] in sample]
    ids = []
    transformations = []
    for entry in entries:
        code = entry.get("project_id", entry.get("id"))
        ids.append(code)
        if entry.get("generated"):
            text = f"\\id {code}\n\\h {entry['title']}\n\\toc1 {entry['title']}\n\\mt1 {entry['title']}\n"
            text += "".join(f"\\mt2 {line}\n" for line in entry["subtitle"])
        elif "file" in entry:
            text = Path(entry["file"]).read_text(encoding="utf-8")
            require(text.startswith(f"\\id {code}\n"), f"Wrong id in {entry['file']}")
        else:
            original = archives[entry["source"]][entry.get("source_id", entry["id"])][2]
            text = (
                scripture_text(entry, archives, transformations)
                if "section" in entry
                else original
            )
            if code != entry.get("source_id", entry["id"]):
                text, remapped = re.subn(r"^(\\id\s+)\S+", lambda m: m[1] + code, text)
                require(remapped == 1, f"Could not remap leading \\id to {code}")
                transformations.append(
                    {
                        "source": entry.get("source_id", entry["id"]),
                        "project_id": code,
                        "operation": "remap project id to retain it as a distinct ordered unit",
                    }
                )
            for marker, heading in entry.get("headings", {}).items():
                text, count = re.subn(
                    r"^(\\" + marker + r"\s+)[^\n]*",
                    lambda m: m[1] + heading,
                    text,
                    count=1,
                    flags=re.M,
                )
                require(count == 1, f"Missing {marker} heading: {code}")
            if entry.get("headings"):
                transformations.append(
                    {
                        "project_id": code,
                        "operation": "edition heading replaces the source heading",
                        "headings": entry["headings"],
                    }
                )
            if "section" not in entry:
                require(
                    inventory(original) == inventory(text),
                    f"Preparation changed source markup: {code}",
                )
            if mode == "sample" and "section" in entry:
                chunks = re.split(r"(?=\\c [0-9]+\s)", text)
                kept = [chunks[0]]
                previous_kept = True
                for c in chunks[1:]:
                    selected = int(re.match(r"\\c (\d+)", c)[1]) in sample[code]
                    if selected:
                        if not previous_kept:
                            # A chapter cannot continue the preceding (omitted) chapter's paragraph.
                            c = re.sub(r"^(\\c \d+\s+)\\nb\b", r"\1\\p", c, count=1)
                        kept.append(c)
                    previous_kept = selected
                text = "".join(kept)
                transformations.append(
                    {
                        "project_id": code,
                        "operation": "sample chapter selection; nb after an omitted chapter becomes p",
                        "chapters": sample[code],
                    }
                )
            # GFS Porson does not encode U+02BC. Normalize Greek elision marks to the
            # typographic apostrophe it does encode before fixing the printable baseline.
            text, greek_apostrophes = re.subn(
                r"(?<=[\u0370-\u03ff\u1f00-\u1fff])\u02bc", "\u2019", text
            )
            if greek_apostrophes:
                transformations.append(
                    {
                        "project_id": code,
                        "operation": "normalize Greek U+02BC elision mark to U+2019 for GFS Porson",
                        "count": greek_apostrophes,
                    }
                )
            # Every later edit must leave printable content unchanged, apart from the spacer.
            expected = canonical_text(text).replace("\u200b", "")
            # Keep the source's reference-only note in 1KI 6:1. Upstream deletes it
            # as empty unless a nonprinting body separates fr from the note end.
            text, empty_notes = re.subn(
                r"(\\f \+ \\fr [^\\]+)(?=\\f\*)", r"\1\\ft " + "\u200b", text
            )
            if empty_notes:
                transformations.append(
                    {
                        "project_id": code,
                        "operation": "retain reference-only note with zero-width ft spacer",
                        "count": empty_notes,
                    }
                )
            # Explicitly tag even single-letter quotations (the upstream heuristic misses
            # these). Keep the Greek apostrophe in the Greek font too.
            for marker, chars, continuation in [
                ("wh", "\u0590-\u05ff", "\u0590-\u05ff"),
                (
                    "wg",
                    "\u0370-\u03ff\u1f00-\u1fff",
                    "\u2019\u0370-\u03ff\u1f00-\u1fff",
                ),
            ]:
                pattern = (
                    "["
                    + chars
                    + "][\u0300-\u036f"
                    + continuation
                    + "]*(?: +["
                    + chars
                    + "][\u0300-\u036f"
                    + continuation
                    + "]*)*"
                )
                text, count = re.subn(
                    pattern,
                    lambda m: "\\+" + marker + " " + m[0] + "\\+" + marker + "*",
                    text,
                )
                if count:
                    transformations.append(
                        {
                            "project_id": code,
                            "operation": "tag quotation runs",
                            "marker": marker,
                            "count": count,
                        }
                    )
            require(
                canonical_text(text).replace("\u200b", "") == expected,
                f"Preparation changed printable content: {code}",
            )
        (project / f"{code}.usfm").write_text(text, encoding="utf-8")
    require(len(ids) == len(set(ids)), "Duplicate generated project id")
    write_json(base / "order.json", ids)
    transformations.append(
        {
            "operation": "protect literal pipes with U+E000 before XX module parsing; restore U+007C afterwards",
            "configuration": "config/changes.txt",
        }
    )
    write_json(base / "transformations.json", transformations)
    root = ET.Element("ScriptureText")
    settings = {
        "Name": "BIBLE",
        "FullName": EDITION["title"],
        "Guid": "407badbc319745d4b3cc9f242039a5ab",
        "Encoding": "65001",
        "Language": "English",
        "LanguageIsoCode": "en",
        "DefaultFont": "Utopia",
        "DefaultFontSize": "9.5",
        "StyleSheet": "usfm.sty",
        "Versification": "4",
        "FileNamePrePart": "",
        "FileNameBookNameForm": "MAT",
        "FileNamePostPart": ".usfm",
        "UsfmVersion": "3.0",
        "MinParatextVersion": "8.0.100.76",
        "ChapterVerseSeparator": ":",
    }
    for key, value in settings.items():
        ET.SubElement(root, key).text = value
    ET.SubElement(root, "Naming", PrePart="", PostPart=".usfm", BookNameForm="MAT")
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
    cfg.read("config/layout.ini", encoding="utf-8")
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
    return project, conf


def render(mode="pdf", name=None):
    archives = validate()
    require(
        UPSTREAM.exists(), "Run this command through Make/Docker (make bootstrap first)"
    )
    for dep in ("ptxprint", "usfmtc", "utopia"):
        require(
            capture(
                "git",
                "-c",
                "safe.directory=/opt/" + dep,
                "-C",
                "/opt/" + dep,
                "rev-parse",
                "HEAD",
            ).strip()
            == DEPS[dep]["commit"],
            f"Wrong {dep} checkout",
        )
    name = name or ("sample" if mode == "sample" else "full")
    base = ROOT / "build" / name
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    project, conf = prepare(mode, base, archives)
    home = base / "home"
    home.mkdir()
    env = os.environ.copy()
    env.update(
        HOME=str(home),
        XDG_CONFIG_HOME=str(home / "config"),
        XDG_CACHE_HOME=str(home / "cache"),
        SOURCE_DATE_EPOCH=str(DEPS["source_date_epoch"]),
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
    check_processed(project, base)
    pdfs = list(project.rglob("*.pdf"))
    require(len(pdfs) == 1, f"Expected one PDF, found {pdfs}; see {base}/console.log")
    target = ROOT / "dist" / ("sample.pdf" if mode == "sample" else "bible.pdf")
    target.parent.mkdir(exist_ok=True)
    report = inspect_pdf(pdfs[0], base, sample=mode == "sample")
    tracked = {
        str(p): sha256(p.read_bytes())
        for folder in ("config", "scripts")
        for p in sorted(Path(folder).rglob("*"))
        if p.is_file() and "__pycache__" not in str(p)
    }
    for input_name in (
        "Dockerfile",
        "Makefile",
        "requirements.txt",
        "dependencies.json",
        "sources.json",
        DEPS["gfs_porson"]["archive"],
    ):
        tracked[input_name] = sha256(Path(input_name).read_bytes())
    fonts = {}
    for folder in (
        "/opt/ptxprint/fonts",
        "/usr/local/share/fonts/gfs",
        "/usr/local/share/fonts/adobe",
        "/usr/local/share/fonts/erewhon",
        "/usr/share/fonts/truetype/ezra",
    ):
        files = sorted(
            p for p in Path(folder).iterdir() if p.suffix in {".otf", ".ttf"}
        )
        require(files, f"No font files to record in provenance: {folder}")
        for p in files:
            require(p.name not in fonts, f"Duplicate font file name: {p.name}")
            fonts[p.name] = sha256(p.read_bytes())
    provenance = {
        "title": EDITION["title"],
        "pdf_sha256": sha256(pdfs[0].read_bytes()),
        "dependencies": DEPS,
        "source_archives": {
            k: {x: v[x] for x in ("url", "sha256", "retrieved")}
            for k, v in SOURCES.items()
        },
        "inputs": tracked,
        "order": json.loads((base / "order.json").read_text(encoding="utf-8")),
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
    staged_pdf = target.with_suffix(".pdf.tmp")
    staged_provenance = target.with_suffix(".provenance.json.tmp")
    shutil.copyfile(pdfs[0], staged_pdf)
    write_json(staged_provenance, provenance)
    target.with_suffix(".provenance.json").unlink(missing_ok=True)
    staged_pdf.replace(target)
    staged_provenance.replace(target.with_suffix(".provenance.json"))
    print("Wrote", target, flush=True)
    return target, base, report


def canonical_text(text):
    # Ignore only markup and whitespace; retain every source word, number and punctuation.
    for macro, char in {
        "asterisk": "*",
        "percent": "%",
        "hash": "#",
        "dollar": "$",
        "ampersand": "&",
        "circumflex": "^",
        "space": " ",
    }.items():
        text = re.sub(r"\\" + macro + r"\b\s?", lambda m: char, text)
    text = re.sub(r"\\\+?[\w-]+\*?\s?", "", text)
    return re.sub(r"\s+", "", text)


def check_processed(project, base):
    records = []
    texfiles = list((project / "local/ptxprint/Bible").glob("*_ptxp.tex"))
    require(len(texfiles) == 1, "Missing typesetting driver")
    tex = texfiles[0].read_text(encoding="utf-8")
    require(
        "%\\OmitCallerInNote{f}" in tex and "%\\OmitCallerInNote{x}" in tex,
        "Note callers unexpectedly suppressed",
    )
    for code in json.loads((base / "order.json").read_text(encoding="utf-8")):
        source = (project / (code + ".usfm")).read_text(encoding="utf-8")
        processed = project / "local/ptxprint/Bible" / (code + "-Bible.usfm")
        require(processed.exists(), f"PTXprint omitted {code}")
        output = processed.read_text(encoding="utf-8")
        require(
            inventory(source)["chapters"] == inventory(output)["chapters"],
            f"PTXprint changed chapter/verse labels: {code}",
        )
        require(
            canonical_text(source) == canonical_text(output),
            f"PTXprint changed printable content: {code}",
        )

        # Nested italic/quotation markers may be flattened by the module parser.
        def counts(s):
            result = {}
            for k, v in inventory(s)["markers"].items():
                k = k.lstrip("+")
                if k.rstrip("*") in ("f", "x", "add", "it", "tr", "tc1", "tc2", "vp"):
                    result[k] = result.get(k, 0) + v
            return result

        require(
            counts(source) == counts(output),
            f"PTXprint changed notes, styles or tables: {code}",
        )
        require("\ue000" not in output, f"Unrestored pipe sentinel: {code}")
        records.append(
            {
                "id": code,
                "content_sha256": sha256(canonical_text(output).encode()),
                "chapters": inventory(output)["chapters"],
                "preserved_markers": counts(output),
            }
        )
    write_json(base / "processed-integrity.json", records)


def check_boundaries(base, text, pages, reading_text, sample=False):
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
    expected = json.loads((base / "order.json").read_text(encoding="utf-8"))
    require(
        [r[0] for r in toc] == expected,
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
        source = (base / "projects/BIBLE" / (code + ".usfm")).read_text(
            encoding="utf-8"
        )
        heading = re.search(r"\\mt1\s+([^\n]+)", source)[1].strip()
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
        if lines:
            header = lines[0].strip()
            if re.fullmatch(
                rf"(?:{page_number}(?:\s+.+)?|.+\s+{page_number}(?:\s+.+)?)",
                header,
            ):
                lines = lines[1:]
        reading_pages_without_headers.append("".join(lines))
    by_code = {b: (i, int(p)) for i, (b, t, p) in enumerate(toc)}
    for witness in json.loads(
        Path("config/render-witnesses.json").read_text(encoding="utf-8")
    ):
        code = witness["id"]
        if code not in by_code or (
            "chapter" in witness
            and witness["chapter"]
            not in inventory(
                (base / "projects/BIBLE" / (code + ".usfm")).read_text(encoding="utf-8")
            )["chapters"]
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


def check_added_words_roman(pdf):
    # Malachias 4:2 reads "healing \\add shall be\\add* in his wings". A font change
    # would put the added words in a different font from their roman neighbours.
    words = ["healing", "shall", "be", "in", "his", "wings"]
    pages = [
        number
        for number, page in enumerate(capture("pdftotext", pdf, "-").split("\f"), 1)
        if " ".join(words) in " ".join(page.split())
    ]
    require(len(pages) == 1, f"Added-word witness not found once: {pages}")
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
    require(False, "Added-word witness not found in PDF text runs")


def inspect_pdf(pdf, base, sample=False):
    with (base / "qpdf.log").open("w", encoding="utf-8") as log:
        run(["qpdf", "--check", pdf], stdout=log, stderr=subprocess.STDOUT)
    info = capture("pdfinfo", "-box", pdf)
    (base / "pdfinfo.txt").write_text(info, encoding="utf-8")
    pages = int(re.search(r"Pages:\s+(\d+)", info)[1])
    # Check every page, not just the first MediaBox.
    boxes = capture("pdfinfo", "-f", "1", "-l", str(pages), "-box", pdf)
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
        all(f in fonts for f in ("Utopia", "Erewhon", "GFSPorson", "Ezra")),
        "Expected text/verse-number/quotation fonts missing",
    )
    text = capture("pdftotext", "-layout", pdf, "-")
    (base / "text.txt").write_text(text, encoding="utf-8")
    check_added_words_roman(pdf)
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
    # PTXprint emits columns in reading order. Protruding edge glyphs can make
    # pdftotext's geometric heuristics merge adjacent columns, so use stream
    # order for wording witnesses; keep the layout extraction above for pages.
    reading_text = capture("pdftotext", "-raw", pdf, "-")
    (base / "reading.txt").write_text(reading_text, encoding="utf-8")
    check_boundaries(base, text, pages, reading_text, sample)
    return {
        "pages": pages,
        "a5_all_pages": True,
        "fonts_embedded": True,
        "text_sha256": sha256(text.encode()),
    }


def check():
    Path("dist/check.json").unlink(missing_ok=True)
    first, base1, report1 = render(name="repeat-1")
    saved = ROOT / "build/repeat-1.pdf"
    shutil.copyfile(first, saved)
    second, base2, report2 = render(name="repeat-2")
    require(report1 == report2, "Repeat builds differ in text/page count")
    # Render pages in batches, hashing then discarding rasters to limit disk use
    # without reopening each PDF once per page.
    pages = report1["pages"]
    rasters = ROOT / "build/check-rasters"

    def page_hashes(pdf, first, last):
        if rasters.exists():
            shutil.rmtree(rasters)
        rasters.mkdir(parents=True)
        run(["pdftoppm", "-f", first, "-l", last, "-r", "72", pdf, rasters / "page"])
        files = sorted(rasters.glob("page-*.ppm"))
        require(
            len(files) == last - first + 1, f"Could not render pages {first}-{last}"
        )
        result = [sha256(f.read_bytes()) for f in files]
        shutil.rmtree(rasters)
        return result

    hashes = []
    for start in range(1, pages + 1, 100):
        end = min(start + 99, pages)
        batch = page_hashes(saved, start, end)
        for page, a, b in zip(
            range(start, end + 1), batch, page_hashes(second, start, end)
        ):
            require(a == b, f"Rendered page {page} differs")
        hashes.extend(batch)
        print("Compared rendered pages:", end, flush=True)
    write_json(
        "dist/check.json",
        {
            "repeatability": "passed",
            "pages": len(hashes),
            "render_dpi": 72,
            "page_sha256": hashes,
            "checks": report2,
        },
    )
    print("All source, PDF and repeatability checks passed.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["validate", "sample", "pdf", "check"])
    args = parser.parse_args()
    try:
        if args.command == "validate":
            validate()
        elif args.command == "check":
            check()
        else:
            render(args.command)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(1)
