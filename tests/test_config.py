"""The PTXprint overrides in config/: each one must change something."""

from __future__ import annotations

import configparser
import io
from collections import defaultdict

from ptxprint.modelmap import ModelMap
from ptxprint.usxutils import merge_sty, simple_parse

from bible import paths
from bible.project import FRONT_TEMPLATE, bsb_baseline

LAYOUT = paths.CONFIG_DIR / "layout.ini"
STYLE_MODS = paths.CONFIG_DIR / "ptxprint-mods.sty"


def read_cfg(text: str) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_string(text)
    return cfg


def overlay_values() -> dict[str, str]:
    """Each "section/key" that layout.ini sets, with its value."""
    cfg = read_cfg(LAYOUT.read_text(encoding="utf-8"))
    return {f"{s}/{k}": v for s in cfg.sections() for k, v in cfg[s].items()}


def normalized(
    key: str, value: str
) -> bool | float | str | tuple[str | frozenset[str], ...]:
    """A cfg value as PTXprint reads it, by the kind of widget that holds it."""
    info = ModelMap.get(key)
    widget = info.widget if info and info.widget else ""
    value = value.strip()
    if widget.startswith("c_"):
        return configparser.ConfigParser.BOOLEAN_STATES.get(value.lower(), False)
    if widget.startswith("s_"):
        return float(value or 0)
    if widget.startswith("bl_"):
        # PTXprint writes "Charis| Italic Bold|..." but reads any word order.
        name, style, *rest = value.split("|")
        return (name, frozenset(style.split()), *rest)
    return value


def test_layout_overrides_only_non_default_values() -> None:
    baseline = read_cfg(bsb_baseline()[0])
    repeated = [
        f"{key} = {value}"
        for key, value in overlay_values().items()
        # A key BSB leaves out has no default headless PTXprint could compare:
        # it falls back to the Paratext settings.
        if baseline.has_option(*key.split("/", 1))
        and normalized(key, value) == normalized(key, baseline.get(*key.split("/", 1)))
    ]
    assert repeated == [], "layout.ini repeats BSB's defaults"


def test_layout_sets_every_key_of_a_shared_setting() -> None:
    # PTXprint writes a widget shared by several keys under each of them, and
    # on loading, whichever comes last in the file wins. The merged file keeps
    # BSB's order, so setting one key alone can be undone by BSB's value for
    # another.
    shared = defaultdict(set)
    for key, info in ModelMap.items():
        if "/" in key and not key.endswith("_") and info.widget:
            shared[info.widget].add(key)
    overlay = overlay_values()
    for key in overlay:
        group = shared[ModelMap[key].widget] if key in ModelMap else {key}
        assert group <= overlay.keys(), f"{key} is also stored as {group - {key}}"
        values = {normalized(k, overlay[k]) for k in group}
        assert len(values) == 1, f"{sorted(group)} disagree"


def test_publication_data_uses_project_license_fields() -> None:
    cfg = read_cfg(LAYOUT.read_text(encoding="utf-8"))
    front = FRONT_TEMPLATE.read_text(encoding="utf-8")
    assert cfg["project"]["copyright"] == "Copyright © 2026 Basil Crow"
    assert (
        "Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International"
        in cfg["project"]["license"]
    )
    assert (
        "https://creativecommons.org/licenses/by-nc-nd/4.0/"
        in cfg["project"]["license"]
    )
    assert (
        front.index("\\periph Title Page")
        < front.index("\\periph Publication Data")
        < front.index("\\periph Table of Contents")
    )
    assert "\\zcopyright" in front and "\\zlicense" in front
    assert "\\resetpagenums -1" in front
    assert cfg["project"]["ifcolophon"] == "False"


def style_value(value: str) -> str | float:
    try:
        return float(value)
    except ValueError:
        return value.strip()


def test_style_mods_override_only_non_default_fields() -> None:
    # The order template.tex loads them in; BSB leaves custom.sty off.
    src = paths.UPSTREAM / "src"
    with (src / "usfm_sb.sty").open(encoding="utf-8") as f:
        base = simple_parse(f)
    with (src / "ptx2pdf.sty").open(encoding="utf-8") as f:
        merge_sty(base, simple_parse(f))
    merge_sty(base, simple_parse(io.StringIO(bsb_baseline()[1])))
    with STYLE_MODS.open(encoding="utf-8") as f:
        mods = simple_parse(f)
    repeated = [
        f"{marker} {field} {value}"
        for marker, fields in mods.items()
        for field, value in fields.items()
        if field != "marker" and field in base.get(marker, {})
        # An explicit FontSize clears an inherited FontScale in PTXprint.
        # Note origins need that reset to stay 10 pt inside smaller notes,
        # even when the numeric FontSize equals the underlying declaration.
        and not (field == "fontsize" and "fontscale" in base.get(marker, {}))
        and style_value(value) == style_value(base[marker][field])
    ]
    assert repeated == [], "ptxprint-mods.sty repeats the styles beneath it"
