"""Writing the PTXprint project: the prepared USFM of every unit, PTXprint's
Settings.xml and BookNames.xml, and its configuration, which overlays config/
on the Berean Standard Bible (BSB) layout that ships with PTXprint."""

import configparser
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile

from bible import edition, numbering, paths
from bible.checks import require
from bible.edition import book_names_element, ordered_entries, source_id, source_usfm
from bible.files import read_json, write_json
from bible.prepare import front_matter_text, recorder, sample_chapters
from bible.typography import typographic_text

BSB_DEFAULT = "shared/ptxprint/Default"
FRONT_TEMPLATE = paths.UPSTREAM / "python/lib/ptxprint/FRTtemplateBasic.txt"
# The generated PTXprint project, and where PTXprint writes its processed copies.
PROJECT_DIR = "projects/BIBLE"
SETTINGS_DIR = "shared/ptxprint/Bible"
PROCESSED_DIR = "local/ptxprint/Bible"
# A note's origin in the prepared text, as "\\fr 3:16 ": the chapter is cut
# from the printed copy. PTXprint's notes/frverseonly and notes/xrverseonly
# would cut it from PTXprint's processed copy instead, which the build
# requires to keep every printable character of this one.
ORIGIN_CHAPTER = re.compile(r"(\\(?:fr|xo) )\d+:")
# Front matter has no verses, and its source gives its notes the origin "1:0",
# which names nothing: these notes print under their callers alone.
EMPTY_ORIGIN = re.compile(r"\\(?:fr|xo) \d+:0 ")


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


def project_settings(project):
    """The PTXprint configuration the project was written with."""
    cfg = configparser.ConfigParser(interpolation=None)
    # read() would silently skip a missing file.
    cfg.read_string((project / SETTINGS_DIR / "ptxprint.cfg").read_text("utf-8"))
    return cfg


def text_font(cfg):
    """The family of the body face, from PTXprint's "family|style|..." value."""
    return cfg["document"]["fontregular"].split("|")[0]


def printed_origins(entry, text, record):
    """A unit's text with its note origins as they are printed."""
    if "section" not in entry:
        text, empty = EMPTY_ORIGIN.subn("", text)
        if empty:
            record("omit note origins that name no verse", origins=empty)
    # Notes sit beside their source verses, so print only the verse in
    # an origin; the nearby chapter figure and running head supply the
    # chapter. The targets of cross references keep their full form.
    text, origins = ORIGIN_CHAPTER.subn(r"\1", text)
    if origins:
        record("print note origins without their chapter", origins=origins)
    return text


def write_project(mode, base, archives, scripture):
    """Write the PTXprint project from validate's prepared scripture; returns its
    folder and the order of its units."""
    project = base / PROJECT_DIR
    conf = project / SETTINGS_DIR
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
            written = source_usfm(entry, archives)
            require(
                written.startswith(f"\\id {code}\n"), f"Wrong id in {entry['file']}"
            )
            text = numbering.page(written, archives)
            if text != written:
                record(
                    "print the passages and tables that the page names",
                    passages=[match[0] for match in numbering.NAMED.finditer(written)],
                    tables=numbering.TABLES.findall(written),
                )
        else:
            if "section" in entry:
                text = scripture[code].text
                transformations.extend(scripture[code].transformations)
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
        text = printed_origins(entry, text, record)
        project_usfm(project, code).write_text(text, encoding="utf-8")
    write_json(base / "order.json", ids)
    transformations.append(
        {
            "operation": "protect literal pipes with U+E000 before XX module parsing; restore U+007C afterwards",
            "configuration": "config/changes.txt",
        }
    )
    write_json(base / "transformations.json", transformations)
    baseline, styles = bsb_baseline()
    (conf / "ptxprint.sty").write_text(styles, encoding="utf-8")
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_string(baseline)
    # read() would silently skip a missing overlay and typeset BSB's layout.
    cfg.read_string(
        (paths.CONFIG_DIR / "layout.ini").read_text(encoding="utf-8"),
        "config/layout.ini",
    )
    root = ET.Element("ScriptureText")
    # Only the settings PTXprint reads; without a Guid it would write its own.
    settings = {
        "FullName": edition.MANIFEST["title"],
        "Guid": "407badbc319745d4b3cc9f242039a5ab",
        "Encoding": "65001",
        "LanguageIsoCode": "en",
        "DefaultFont": text_font(cfg),
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
    # BSB's import selections describe copying from its project; our generated
    # project already contains the edition's inputs and must stand on its own.
    cfg.remove_section("import")
    # Replace BSB's selected book with the edition's manifest order, including
    # its front pages, dividers, and appendices as distinct printable units.
    cfg["project"]["booklist"] = " ".join(ids)
    cfg["project"]["book"] = ids[0]
    if mode == "sample":
        # Mark the title page so a selection of chapters cannot be mistaken
        # for the complete edition.
        cfg["vars"]["subtitle"] += " — TYPESETTING SAMPLE: selected chapters"
    with (conf / "ptxprint.cfg").open("w", encoding="utf-8") as f:
        cfg.write(f)
    # Copy the shared protrusion adapter alongside its production loader;
    # the font regression test loads this same adapter independently.
    for name in (
        "ptxprint-mods.sty",
        "ptxprint-mods.tex",
        "protrusion.tex",
        "changes.txt",
    ):
        shutil.copyfile(paths.CONFIG_DIR / name, conf / name)
    # Replace BSB's front matter with PTXprint's basic template so the title,
    # publication data, and contents come from this edition's settings.
    shutil.copyfile(FRONT_TEMPLATE, conf / "FRTlocal.sfm")
    return project, ids
