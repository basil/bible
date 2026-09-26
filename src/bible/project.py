"""Writing the PTXprint project: the prepared USFM of every unit, PTXprint's
Settings.xml and BookNames.xml, and its configuration, which overlays config/
on the Berean Standard Bible (BSB) layout that ships with PTXprint."""

import configparser
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile

from bible import edition, paths
from bible.checks import require
from bible.edition import book_names_element, ordered_entries, source_id, source_usfm
from bible.files import read_json, write_json
from bible.prepare import front_matter_text, recorder, sample_chapters, scripture_text
from bible.typography import typographic_text

BSB_DEFAULT = "shared/ptxprint/Default"
# The generated PTXprint project, and where PTXprint writes its processed copies.
PROJECT_DIR = "projects/BIBLE"
PROCESSED_DIR = "local/ptxprint/Bible"


def bsb_baseline():
    """BSB's PTXprint configuration and stylesheet, which config/ overrides."""
    with zipfile.ZipFile(paths.UPSTREAM / "resources/bsb.zip") as z:
        return (
            z.read(f"{BSB_DEFAULT}/ptxprint.cfg").decode(),
            z.read(f"{BSB_DEFAULT}/ptxprint.sty").decode(),
        )


def project_usfm(project, code):
    """A prepared unit's file in the PTXprint project."""
    return project / f"{code}.usfm"


def processed_usfm(project, code):
    """PTXprint's processed copy of a prepared unit."""
    return project / PROCESSED_DIR / f"{code}-Bible.usfm"


def write_project(mode, base, archives):
    """Write the PTXprint project; returns its folder and the order of its units."""
    project = base / PROJECT_DIR
    conf = project / "shared/ptxprint/Bible"
    conf.mkdir(parents=True)
    entries = ordered_entries()
    if mode == "sample":
        sample = read_json(paths.EDITION_DIR / "sample.json")
        unknown = set(sample) - {u["id"] for u in edition.MANIFEST["scripture"]}
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
        "FullName": edition.MANIFEST["title"],
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
    baseline, styles = bsb_baseline()
    (conf / "ptxprint.sty").write_text(styles, encoding="utf-8")
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_string(baseline)
    # read() would silently skip a missing overlay and typeset BSB's layout.
    cfg.read_string(
        (paths.CONFIG_DIR / "layout.ini").read_text(encoding="utf-8"),
        "config/layout.ini",
    )
    cfg.remove_section("import")
    cfg["project"]["booklist"] = " ".join(ids)
    cfg["project"]["book"] = ids[0]
    with (conf / "ptxprint.cfg").open("w", encoding="utf-8") as f:
        cfg.write(f)
    for name in ("ptxprint-mods.sty", "ptxprint-mods.tex", "changes.txt"):
        shutil.copyfile(paths.CONFIG_DIR / name, conf / name)
    front = (paths.CONTENT_DIR / "front.sfm").read_text(encoding="utf-8")
    if mode == "sample":
        require(r"\mt1 THE HOLY BIBLE" in front, "Cannot label the sample title page")
        front = front.replace(
            r"\mt1 THE HOLY BIBLE",
            "\\mt1 THE HOLY BIBLE\n\\mt3 TYPESETTING SAMPLE — selected chapters",
        )
    (conf / "FRTlocal.sfm").write_text(front, encoding="utf-8")
    return project, ids
