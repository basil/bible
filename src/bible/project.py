"""Writing the PTXprint project: the prepared USFM of every unit, PTXprint's
Settings.xml and BookNames.xml, and its configuration, which overlays config/
on the Berean Standard Bible (BSB) layout that ships with PTXprint."""

from __future__ import annotations

import configparser
import shutil
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path

import bible.pipeline
import bible.policy
from bible import assembly, paths, peripherals, scripture, typeface, usj
from bible.checks import require
from bible.files import write_json

BSB_DEFAULT = "shared/ptxprint/Default"
FRONT_TEMPLATE = paths.ROOT / "config/front.sfm"
# The generated PTXprint project, and where PTXprint writes its processed copies.
PROJECT_DIR = "projects/BIBLE"
SETTINGS_DIR = "shared/ptxprint/Bible"
PROCESSED_DIR = "local/ptxprint/Bible"
# The paragraph adjustments the page filler writes, which the typesetter reads.
ADJUSTMENTS_DIR = f"{SETTINGS_DIR}/AdjLists"
# The testaments' dividers, the parts of the contents, by their peripheral ids.
PARTS = tuple(
    peripherals.UNITS[entry["id"]]
    for entry in (bible.policy.OLD_TESTAMENT, bible.policy.NEW_TESTAMENT)
)


def bsb_baseline() -> tuple[str, ...]:
    """BSB's PTXprint configuration and stylesheet, which config/ overrides."""
    with zipfile.ZipFile(paths.UPSTREAM / "resources/bsb.zip") as z:
        return (
            z.read(f"{BSB_DEFAULT}/ptxprint.cfg").decode(),
            z.read(f"{BSB_DEFAULT}/ptxprint.sty").decode(),
        )


def project_usfm(project: Path, code: str) -> Path:
    """A prepared unit's file in the PTXprint project."""
    return project / f"{code}.usfm"


def processed_usfm(project: Path, code: str) -> Path:
    """PTXprint's processed copy of a prepared unit."""
    return project / PROCESSED_DIR / f"{code}-Bible.usfm"


def project_settings(project: Path) -> configparser.ConfigParser:
    """The PTXprint configuration the project was written with."""
    cfg = configparser.ConfigParser(interpolation=None)
    # read() would silently skip a missing file.
    cfg.read_string((project / SETTINGS_DIR / "ptxprint.cfg").read_text("utf-8"))
    return cfg


def text_font(cfg: configparser.ConfigParser) -> str:
    """The family of the body face, from PTXprint's "family|style|..." value."""
    return cfg["document"]["fontregular"].split("|")[0]


def style_mods() -> str:
    """The style overrides, naming the installed Greek and chapter faces."""
    return (paths.CONFIG_DIR / "ptxprint-mods.sty").read_text(encoding="utf-8") + (
        f"\n\\Marker c\n\\FontName [{typeface.chapter_face()}]\n"
        f"\n\\Marker wg\n\\FontName {typeface.greek_family()}\n"
    )


def book_names(
    edition: bible.pipeline.Edition,
    ids: Sequence[str],
    aliases: Mapping[str, str],
) -> ET.Element:
    """PTXprint's BookNames.xml for the units a project prints, each under
    its physical id."""
    root = ET.Element("BookNames")
    for code in ids:
        names = edition.names[code]
        ET.SubElement(
            root,
            "book",
            {
                "code": aliases.get(code, code),
                **{
                    attr: names[field]
                    for field, attr in assembly.NAME_ATTRIBUTES.items()
                },
            },
        )
    return root


def running_heads(documents: Sequence[tuple[str, usj.Document]]) -> str:
    """Hidden chapters' titles for PTXprint's running heads and bookmarks."""
    result = []
    for code, doc in documents:
        chapters = [n for n in doc["content"] if n["type"] == "chapter"]
        if not any(n.get("pubnumber") == scripture.HIDDEN for n in chapters):
            continue
        book = assembly.header(doc, "h")
        require(book, f"Missing running-head book name: {code}")
        for chapter, *body in assembly.chapters_of(doc)[1]:
            if chapter.get("pubnumber") != scripture.HIDDEN:
                continue
            # The heading the website labels the chapter by.
            title = scripture.chapter_label(chapter, body)
            number = chapter["number"]
            # These are plain words passed to TeX, never executable markup.
            require(
                not any(c in book + number + title for c in "\\{}%#$&^_~"),
                f"Unsupported TeX character in running head: {code} {number}",
            )
            result.append(f"\\BibleRunningHead{{{book}}}{{{number}}}{{{title}}}\n")
    return "".join(result)


def pagination() -> str:
    """Register the testaments' dividers as the parts of the contents; the
    first starts the main matter's folios."""
    return "".join(f"\\BiblePart{{{part}}}\n" for part in PARTS)


def write_project(
    mode: str,
    base: Path,
    documents: Sequence[tuple[str, usj.Document]],
    edition: bible.pipeline.Edition,
) -> tuple[Path, list[str]]:
    """Write the prepared USJ documents and PTXprint's
    configuration; the project's directory, and the ids it prints."""
    project = base / PROJECT_DIR
    conf = project / SETTINGS_DIR
    conf.mkdir(parents=True)
    peripheral_ids = [code for code, _ in documents if code not in edition.scripture]
    require(
        len(peripheral_ids) <= 7, "Too many peripheral runs for PTXprint's extra books"
    )
    aliases = {code: f"XX{chr(ord('A') + n)}" for n, code in enumerate(peripheral_ids)}
    ids = [aliases.get(code, code) for code, _ in documents]
    require(ids and len(ids) == len(set(ids)), "Empty or duplicate project id")
    for code, document in documents:
        # PTXprint needs unique physical books in reading order. Standard
        # FRT/INT identities remain in the review and web exports. PTXprint
        # reserves FRT, INT, and some source keys for its own special handling.
        physical = aliases.get(code, code)
        doc = usj.with_code(document, physical)
        project_usfm(project, physical).write_text(usj.serialize(doc), encoding="utf-8")
    write_json(base / "order.json", ids)
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
        "FullName": edition.policy.title,
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
    ET.ElementTree(book_names(edition, [code for code, _ in documents], aliases)).write(
        project / "BookNames.xml", encoding="utf-8", xml_declaration=True
    )
    # BSB's import selections describe copying from its project; our generated
    # project already contains the edition's inputs and must stand on its own.
    cfg.remove_section("import")
    # Replace BSB's selected book with the edition's manifest order, including
    # its front pages and dividers as distinct printable units.
    cfg["project"]["booklist"] = " ".join(ids)
    cfg["project"]["book"] = ids[0]
    if mode == "sample":
        # Mark the title page so a selection of chapters cannot be mistaken
        # for the complete edition.
        cfg["vars"]["subtitle"] += r"\hfil\break{}TYPESETTING SAMPLE: selected chapters"
    with (conf / "ptxprint.cfg").open("w", encoding="utf-8") as f:
        cfg.write(f)
    (conf / "ptxprint-mods.sty").write_text(style_mods(), encoding="utf-8")
    # Copy the TeX helpers alongside their production loader. Regression
    # tests also load these helpers independently.
    for name in (
        "ptxprint-mods.tex",
        "protrusion.tex",
        "running-heads.tex",
        "changes.txt",
    ):
        shutil.copyfile(paths.CONFIG_DIR / name, conf / name)
    with (conf / "ptxprint-mods.tex").open("a", encoding="utf-8") as f:
        f.write(
            "\n"
            + pagination()
            + running_heads([(c, d) for c, d in documents if c in edition.scripture])
        )
    # Replace BSB's front matter with the edition's template, so the opening
    # pages and the contents are this edition's own.
    shutil.copyfile(FRONT_TEMPLATE, conf / "FRTlocal.sfm")
    return project, ids
