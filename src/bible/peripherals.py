"""Peripheral identity and packaging, independent of a source's file codes."""

from bible.usj import Document, Node

# Logical units have descriptive names or existing source keys. Publications
# use peripheral identifiers, USFM's own where it has one.
UNITS = {
    "acknowledgments": "x-acknowledgments",
    "introduction": "intbible",
    "XXA": "x-numbering",
    "XXB": "preface",
    "XXE": "intot",
    "dedication": "x-dedication",
    "translators-preface": "x-translators-preface",
    "abbreviations": "abbreviations",
    "XXF": "x-old-testament",
    "XXG": "x-new-testament",
    "odes": "x-odes",
    "psalter": "x-psalter",
    "colophon": "x-colophon",
}
# The standard peripheral book each publication is packaged in, where it is
# not the front matter's: the introductions' and the back matter's.
BACK = "BAK"
BOOKS = {
    "intbible": "INT",
    "intot": "INT",
    "x-odes": BACK,
    "x-psalter": BACK,
    "x-colophon": BACK,
}
# The website names a unit by its descriptive name, given here where the unit
# is known by a source key.
SLUGS = {"XXA": "numbering", "XXB": "brenton-preface", "XXE": "brenton-introduction"}


def slug(code: str) -> str:
    """The website's name for a logical unit."""
    return SLUGS.get(code, code)


def book(code: str) -> str:
    """The standard peripheral book for a logical unit, whatever its source key."""
    return BOOKS.get(UNITS[code], "FRT")


def division(code: str, doc: Document, title: str) -> Node:
    """A standalone logical unit within a standard peripheral container."""
    return {
        "type": "periph",
        "id": UNITS[code],
        "alt": title,
        "content": [b for b in doc["content"] if b["type"] != "book"],
    }
