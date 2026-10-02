"""Writing the PTXprint project: the prepared USFM of every unit, PTXprint's
Settings.xml and BookNames.xml, and its configuration, which overlays config/
on the Berean Standard Bible (BSB) layout that ships with PTXprint."""

from __future__ import annotations

import configparser
import shutil
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

import bible.policy
import bible.sources
from bible import assembly, paths
from bible.checks import require
from bible.files import write_json

BSB_DEFAULT = "shared/ptxprint/Default"
FRONT_TEMPLATE = paths.UPSTREAM / "python/lib/ptxprint/FRTtemplateBasic.txt"
# The generated PTXprint project, and where PTXprint writes its processed copies.
PROJECT_DIR = "projects/BIBLE"
SETTINGS_DIR = "shared/ptxprint/Bible"
PROCESSED_DIR = "local/ptxprint/Bible"


class ProjectOutput(NamedTuple):
    project: Path
    ids: list[str]


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


def book_names(
    policy: bible.policy.Policy, sources: bible.sources.Sources, ids: Sequence[str]
) -> ET.Element:
    """PTXprint's BookNames.xml for the units a project prints."""
    root = ET.Element("BookNames")
    entries = {entry["id"]: entry for entry in policy.entries}
    for code in ids:
        entry = entries[code]
        names = assembly.names(entry, assembly.source_text(entry, sources))
        ET.SubElement(
            root,
            "book",
            {
                "code": code,
                **{
                    attr: names[field]
                    for field, attr in assembly.NAME_ATTRIBUTES.items()
                },
            },
        )
    return root


def write_project(
    mode: str,
    base: Path,
    documents: Sequence[tuple[str, str]],
    policy: bible.policy.Policy,
    sources: bible.sources.Sources,
) -> ProjectOutput:
    """Write the exported documents, as (id, USFM), and PTXprint's configuration."""
    project = base / PROJECT_DIR
    conf = project / SETTINGS_DIR
    conf.mkdir(parents=True)
    ids = [code for code, _ in documents]
    require(ids and len(ids) == len(set(ids)), "Empty or duplicate project id")
    for code, text in documents:
        project_usfm(project, code).write_text(text, encoding="utf-8")
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
        "FullName": policy.title,
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
    ET.ElementTree(book_names(policy, sources, ids)).write(
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
        "word-spacing.tex",
        "changes.txt",
    ):
        shutil.copyfile(paths.CONFIG_DIR / name, conf / name)
    # Replace BSB's front matter with PTXprint's basic template so the title,
    # publication data, and contents come from this edition's settings.
    shutil.copyfile(FRONT_TEMPLATE, conf / "FRTlocal.sfm")
    return ProjectOutput(project, ids)
