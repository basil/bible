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


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


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
    orthodox = "GEN EXO LEV NUM DEU JOS JDG RUT 1SA 2SA 1KI 2KI 1CH 2CH MAN 1ES EZR NEH TOB JDT ESG 1MA 2MA 3MA PSA JOB PRO ECC SNG WIS SIR HOS AMO MIC JOL OBA JON NAM HAB ZEP HAG ZEC MAL ISA JER BAR LAM LJE EZK DAG 4MA".split()
    require(
        ids[: len(orthodox)] == orthodox and ids[len(orthodox)] == "MAT",
        "Orthodox Old Testament order changed",
    )
    require(
        "2ES" not in ids and "SUS" not in ids and "BEL" not in ids,
        "Unexpected separate scripture unit",
    )
    revised_titles = {
        "EZR": "Esdras II",
        "NEH": "Nehemiah",
        "ESG": "Esther",
        "DAG": "Daniel",
        "PRO": "Proverbs of Solomon",
        "SNG": "Song of Songs",
        "SIR": "Wisdom of Sirach",
        "LAM": "Lamentations of Jeremy",
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
    front = [(e["source"], e["id"]) for e in EDITION["front_apparatus"]]
    require(
        front
        == [
            ("brenton", "FRT"),
            ("brenton", "INT"),
            ("kjv", "OTH"),
            ("kjv", "INT"),
        ],
        "Selected Cambridge peripherals must follow Brenton’s introduction, dedication first",
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
    for unit in units:
        if unit["source"] == "brenton":
            scripture_text(unit, archives)
    entries = ordered_entries()
    ordered_ids = [e.get("project_id", e.get("id")) for e in entries]
    require(
        ordered_ids.index("4MA") + 1 == ordered_ids.index("XXG"),
        "Old Testament appendix misplaced",
    )
    require(
        ordered_ids.index("REV") + 1 == ordered_ids.index("GLO")
        and ordered_ids.index("GLO") + 1 == ordered_ids.index("OTH"),
        "Apocrypha introduction misplaced",
    )
    require(
        "THE APOCRYPHA" not in Path("config/front.sfm").read_text(encoding="utf-8"),
        "Obsolete Apocrypha divider/title remains",
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
        "scripture_units": 78,
        "brenton_units": 52,
        "kjv_units": 27,
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
        result.append(
            {
                "project_id": code,
                "title": title,
                "subtitle": subtitle,
                "generated": True,
            }
        )

    result.extend(EDITION["front_apparatus"])
    add_div("XXF", "THE OLD TESTAMENT", "Brenton’s Septuagint")
    for section in ("old_testament", "old_testament_appendix", "new_testament"):
        if section == "old_testament_appendix":
            add_div("CNC", "OLD TESTAMENT APPENDIX", "Maccabees IV")
        if section == "new_testament":
            add_div(
                "XXG",
                "THE NEW TESTAMENT",
                "The Cambridge Paragraph Bible • King James Version",
            )
        result.extend(u for u in EDITION["scripture"] if u["section"] == section)
    add_div(
        "GLO",
        "HISTORICAL APPARATUS",
        "Brenton’s introductions, tables, preface, errata, and appendix",
    )
    result.extend(EDITION["back_apparatus"])
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


def scripture_text(entry, archives):
    code = entry["id"]
    original = archives[entry["source"]][entry.get("source_id", code)][2]
    if code in ("EZR", "NEH"):
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
        expected = header + "".join(chapters[:10] if code == "EZR" else chapters[10:])
        text = header + "".join(selected)
    elif code == "DAG":
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
            lambda m: "\\s1 SONG OF AZARIAS AND HYMN OF THE THREE YOUTHS\n\\p\n",
            daniel_chapters[2],
            count=1,
        )
        require(song_heading == 1, "Daniel 3 Song of Azarias boundary changed")
        text = daniel_header + "".join(susanna + daniel_chapters + bel)
    else:
        expected = original
        text = original
    if code == "MAL":
        require(
            text.count(r"\v 19 For, behold") == 1, "Malachias chapter boundary changed"
        )
        prefix, tail = text.split(r"\v 19 For, behold", 1)
        tail = "\\c 4\n\\v 1 For, behold" + tail
        for old, new in zip(range(20, 25), range(2, 7)):
            tail = re.sub(
                r"\\v " + str(old) + r"(?=\s)",
                lambda m: r"\v " + str(new),
                tail,
                count=1,
            )
        text = prefix + tail.replace(r"\xo 3:23", r"\xo 4:5")
    if code in {"EZR", "NEH", "ESG", "DAG", "PRO", "SNG", "SIR", "LAM"}:
        title = entry["title"]
        for marker in ("h", "toc1", "toc2", "toc3", "mt1"):
            text, count = re.subn(
                r"(\\" + marker + r"\s+)[^\n]*",
                lambda m: m[1] + (title.upper() if marker == "mt1" else title),
                text,
                count=1,
            )
            require(count == 1, f"Missing {marker} heading: {code}")
        if code == "SIR":
            text = re.sub(r"\\mt2\s+[^\n]*\n", "", text, count=1)
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
            text = f"\\id {code}\n\\h {entry['title']}\n\\toc1 {entry['title']}\n\\mt1 {entry['title']}\n\\mt2 {entry['subtitle']}\n"
        else:
            original = archives[entry["source"]][entry.get("source_id", entry["id"])][2]
            text = scripture_text(entry, archives) if "section" in entry else original
            if (
                "section" in entry
                and entry["source"] == "brenton"
                and (
                    entry["id"]
                    in {"EZR", "NEH", "DAG", "MAL", "ESG", "PRO", "SNG", "SIR", "LAM"}
                )
            ):
                transformations.append(
                    {
                        "project_id": code,
                        "source_ids": entry.get(
                            "source_parts", [entry.get("source_id", entry["id"])]
                        ),
                        "operation": "Orthodox book heading, passage grouping, or chapter labels; wording and source markers verified",
                    }
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
            # Explicitly tag even single-letter quotations (the upstream heuristic misses these).
            for marker, chars in [
                ("wh", "\u0590-\u05ff"),
                ("wg", "\u0370-\u03ff\u1f00-\u1fff"),
            ]:
                pattern = (
                    "["
                    + chars
                    + "][\u0300-\u036f"
                    + chars
                    + "]*(?: +["
                    + chars
                    + "][\u0300-\u036f"
                    + chars
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
        "DefaultFont": "Charis",
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
    names = ET.Element("BookNames")
    for entry, code in zip(entries, ids):
        title = entry.get("title")
        if not title:
            title = re.search(
                r"\\h\s+([^\n]+)", archives[entry["source"]][entry["id"]][2]
            )[1].strip()
        ET.SubElement(names, "book", code=code, abbr=title, short=title, long=title)
    ET.ElementTree(names).write(
        project / "BookNames.xml", encoding="utf-8", xml_declaration=True
    )
    with zipfile.ZipFile(UPSTREAM / "resources/bsb.zip") as z:
        baseline = z.read("shared/ptxprint/Default/ptxprint.cfg").decode()
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
    for dep in ("ptxprint", "usfmtc"):
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
    shutil.copyfile(pdfs[0], target.with_suffix(".pdf.tmp"))
    target.with_suffix(".pdf.tmp").replace(target)
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
    ):
        tracked[input_name] = sha256(Path(input_name).read_bytes())
    fonts = {}
    for folder in (
        "/opt/ptxprint/fonts",
        "/usr/share/fonts/truetype/gentiumplus",
        "/usr/share/fonts/truetype/ezra",
    ):
        files = sorted(Path(folder).glob("*.ttf"))
        require(files, f"No font files to record in provenance: {folder}")
        for p in files:
            require(p.name not in fonts, f"Duplicate font file name: {p.name}")
            fonts[p.name] = sha256(p.read_bytes())
    provenance = {
        "title": EDITION["title"],
        "pdf_sha256": sha256(target.read_bytes()),
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
    write_json(target.with_suffix(".provenance.json"), provenance)
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

    contents = key("".join(page_text[2 : int(toc[0][2]) - 1]))
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
    by_code = {b: (i, int(p)) for i, (b, t, p) in enumerate(toc)}
    if "DAG" in by_code:
        index, start = by_code["DAG"]
        end = int(toc[index + 1][2]) - 1 if index + 1 < len(toc) else pages
        daniel_headers = [
            p.splitlines()[0] if p.splitlines() else ""
            for p in page_text[start - 1 : end]
        ]
        require(
            not any(re.search(r"\bDaniel\b.*\b(?:13|14)\b", h) for h in daniel_headers),
            "Internal Daniel 13/14 labels leaked into running headers",
        )
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
        require(
            key(witness["phrase"]) in key("".join(reading_pages[start - 1 : end])),
            f"Special-content witness absent from rendered {code}: {witness['phrase']}",
        )


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
    require("Charis-Italic" in fonts, "Added-word italic font missing")
    require(
        "Charis" in fonts and "Gentium" in fonts and "Ezra" in fonts,
        "Expected text/quotation fonts missing",
    )
    text = capture("pdftotext", "-layout", pdf, "-")
    (base / "text.txt").write_text(text, encoding="utf-8")
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
    reading_text = capture("pdftotext", pdf, "-")
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
