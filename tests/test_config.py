"""The PTXprint overrides in config/: each one must change something."""

from collections import defaultdict
import configparser
import io
from pathlib import Path

from ptxprint.modelmap import ModelMap
from ptxprint.usxutils import merge_sty, simple_parse

import pipeline

LAYOUT = Path("config/layout.ini")
STYLE_MODS = Path("config/ptxprint-mods.sty")


def read_cfg(text):
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_string(text)
    return cfg


def overlay_values():
    """Each "section/key" that layout.ini sets, with its value."""
    cfg = read_cfg(LAYOUT.read_text(encoding="utf-8"))
    return {f"{s}/{k}": v for s in cfg.sections() for k, v in cfg[s].items()}


def normalized(key, value):
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


def test_layout_overrides_only_non_default_values():
    baseline = read_cfg(pipeline.bsb_baseline()[0])
    repeated = [
        f"{key} = {value}"
        for key, value in overlay_values().items()
        # A key BSB leaves out has no default headless PTXprint could compare:
        # notes/xrcallers, for one, falls back to the Paratext settings.
        if baseline.has_option(*key.split("/", 1))
        and normalized(key, value) == normalized(key, baseline.get(*key.split("/", 1)))
    ]
    assert repeated == [], "layout.ini repeats BSB's defaults"


def test_layout_sets_every_key_of_a_shared_setting():
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


def style_value(value):
    try:
        return float(value)
    except ValueError:
        return value.strip()


def test_style_mods_override_only_non_default_fields():
    # The order template.tex loads them in; BSB leaves custom.sty off.
    src = pipeline.UPSTREAM / "src"
    with (src / "usfm_sb.sty").open(encoding="utf-8") as f:
        base = simple_parse(f)
    with (src / "ptx2pdf.sty").open(encoding="utf-8") as f:
        merge_sty(base, simple_parse(f))
    merge_sty(base, simple_parse(io.StringIO(pipeline.bsb_baseline()[1])))
    with STYLE_MODS.open(encoding="utf-8") as f:
        mods = simple_parse(f)
    repeated = [
        f"{marker} {field} {value}"
        for marker, fields in mods.items()
        for field, value in fields.items()
        if field != "marker"
        and field in base.get(marker, {})
        and style_value(value) == style_value(base[marker][field])
    ]
    assert repeated == [], "ptxprint-mods.sty repeats the styles beneath it"
