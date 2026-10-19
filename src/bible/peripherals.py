"""Peripheral identity and packaging, independent of a source's file codes."""

from typing import NamedTuple

from bible.usj import Document, Node


class Identity(NamedTuple):
    """A unit's peripheral identifier, and the website's slug for it."""

    periph: str
    slug: str


# Source decision keys stay in their source namespace. Publications use
# peripheral identifiers, and the website uses these descriptive slugs.
UNITS = {
    "XXD": Identity("abbreviations", "abbreviations"),
    "CNC": Identity("intbible", "editor-introduction"),
    "XXA": Identity("x-numbering", "numbering"),
    "XXF": Identity("x-old-testament", "old-testament"),
    "XXB": Identity("preface", "brenton-preface"),
    "XXE": Identity("intot", "brenton-introduction"),
    "XXG": Identity("x-new-testament", "new-testament"),
    "TDX": Identity("x-dedication", "dedication"),
    "NDX": Identity("x-translators-preface", "translators-to-reader"),
}


def book(code: str) -> str:
    """The standard peripheral book for a logical unit, whatever its source key."""
    return "INT" if UNITS[code].periph in {"intbible", "intot"} else "FRT"


def division(code: str, doc: Document, title: str) -> Node:
    """A standalone logical unit within a standard peripheral container."""
    return {
        "type": "periph",
        "id": UNITS[code].periph,
        "alt": title,
        "content": [b for b in doc["content"] if b["type"] != "book"],
    }
