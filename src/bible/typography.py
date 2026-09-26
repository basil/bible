"""The characters and markup the fonts and PTXprint need: typographic quotes,
Greek elision marks, tagged Greek and Hebrew quotations, and a spacer that
keeps a reference-only note. Only the printable content's form changes."""

import re

from bible.checks import require
from bible.usfm import canonical_text, inventory

GREEK = "\u0370-\u03ff\u1f00-\u1fff"
HEBREW = "\u0590-\u05ff"


def typographic_text(code, text, record):
    """The text with the characters and markup the fonts and PTXprint need.

    Only the printable content's form changes, never its substance.
    """
    # GFS Didot does not encode U+02BC. Normalize Greek elision marks to the
    # typographic apostrophe it does encode before fixing the printable baseline.
    text, greek_apostrophes = re.subn(f"(?<=[{GREEK}])\u02bc", "\u2019", text)
    if greek_apostrophes:
        record(
            "normalize Greek U+02BC elision mark to U+2019 for GFS Didot",
            count=greek_apostrophes,
        )
    text, smartened = typographic_quotes(text)
    if smartened:
        record("typographic quotes, ellipses and dashes (SmartyPants)", count=smartened)
    # Every later edit must leave printable content unchanged, apart from the spacer.
    expected = canonical_text(text).replace("\u200b", "")
    # Keep the source's reference-only note in 1KI 6:1. Upstream deletes it
    # as empty unless a nonprinting body separates fr from the note end.
    text, empty_notes = re.subn(
        r"(\\f \+ \\fr [^\\]+)(?=\\f\*)", r"\1\\ft " + "\u200b", text
    )
    if empty_notes:
        record(
            "retain reference-only note with zero-width ft spacer", count=empty_notes
        )
    # Explicitly tag even single-letter quotations (the upstream heuristic misses
    # these). Keep the Greek apostrophe in the Greek font too.
    for marker, letters, continuation in (
        ("wh", HEBREW, HEBREW),
        ("wg", GREEK, "\u2019" + GREEK),
    ):
        word = f"[{letters}][\u0300-\u036f{continuation}]*"
        text, count = re.subn(
            f"{word}(?: +{word})*",
            lambda m: f"\\+{marker} {m[0]}\\+{marker}*",
            text,
        )
        if count:
            record("tag quotation runs", marker=marker, count=count)
    require(
        canonical_text(text).replace("\u200b", "") == expected,
        f"Preparation changed printable content: {code}",
    )
    return text


def typographic_quotes(text):
    """Straight quotes, ellipses and double hyphens as typographic characters.

    SmartyPants curls each quote from its context. It reads USFM as plain text:
    it would take <...> for an HTML tag and a backslash before a quote, period,
    hyphen or backtick for an escape, so neither may occur. Its backtick option
    also turns every other ' into a closing quote, so the source's few `single'
    quotes are opened here instead.
    """
    # Imported here, so that the build's other stages, such as validate and the
    # image check, run without it.
    import smartypants

    require("<" not in text, "Text looks like HTML to SmartyPants")
    require(not re.search(r"\\[\\\"'.`-]", text), "Text contains a SmartyPants escape")
    require("''" not in text and "``" not in text, "Ambiguous doubled quote characters")
    require(not re.search(r"`(?![A-Za-z])", text), "Backtick is not an opening quote")
    result = smartypants.smartypants(
        text.replace("`", "‘"),
        smartypants.Attr.q
        | smartypants.Attr.d
        | smartypants.Attr.e
        | smartypants.Attr.u,
    )

    def fold(s):
        for typographic, plain in {
            "‘": "'",
            "’": "'",
            "`": "'",
            "“": '"',
            "”": '"',
            "…": "...",
            "—": "--",
        }.items():
            s = s.replace(typographic, plain)
        return s

    require(
        inventory(result) == inventory(text) and fold(result) == fold(text),
        "SmartyPants changed more than quotes, ellipses and dashes",
    )
    plain = r"['\"`]|\.\.\.|--"
    require(
        not re.search(plain, result) and result.count("&#") == text.count("&#"),
        "SmartyPants left a straight quote or a character reference",
    )
    return result, len(re.findall(plain, text))
