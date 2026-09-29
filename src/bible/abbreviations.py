"""Brenton's list of abbreviations, completed with those the printed notes use,
and the printed abbreviations in the form The Chicago Manual of Style gives it.

His list gives twelve, and the notes use more: his own, the introductions to
the Apocrypha, the footnotes to his preface, the margin of 1611, and the
quotation links. edition/abbreviations.json gives the rows that complete it,
set as his are, after them. An abbreviation used only once or twice is
printed in full where it stands instead, the file deciding each, unless it is
one Chicago prints, as "AD", "MS" and "p." are, and his rows for those are
dropped. Text names are also printed in full, but for the Alexandrine Text,
which stays "Alex." and keeps his row, and Brenton's "Comp." for "Compare" is
printed in full. "Sept." is printed as "LXX", which is listed, and "A. V.",
like the English Version, a note's "English Bible" and eBible's "AV", as
"Authorized Version", whose row is dropped. The notes and the front and back
matter of both translations then print each abbreviation as Chicago does:
"i.e." and "q.d." closed up, "i.e." with a comma after it; "LXX", "MS" and
"MSS" without a period; "AD" and "BC" in full capitals, "AD" before its year
and "BC" after; "etc." for "&c."; "sc." and "Sc." for "scil." and "Scil.";
and "St." for the saint's "S.". The numbers that the sources write with a
period within a sentence are Chicago's too, each as the file decides.
"""

import re

from bible import paths
from bible.checks import require
from bible.files import read_json
from bible.usfm import NOTE

ABBREVIATIONS = read_json(paths.EDITION_DIR / "abbreviations.json")
SOURCE = "FRT"
# Latin in a meaning, italic as Brenton's "quasi dicat" is.
LATIN = re.compile(r"_([^_]+)_")

# Source forms closed up or replaced in the printed edition.
REPLACED = [
    (re.compile(r"\bi\. e\."), "i.e."),
    # ...with a comma after it, roman after an italic one: "(\it i.e.\it*, in".
    (re.compile(r"\bi\.e\.(?= )"), "i.e.,"),
    (re.compile(r"\bi\.e\.\\it\*(?= )"), r"i.e.\\it*,"),
    (re.compile(r"\bq\. d\."), "q.d."),
    (re.compile(r"\bscil\."), "sc."),
    (re.compile(r"\bScil\."), "Sc."),
    # Brenton's "Comp." for "Compare", printed in full.
    (re.compile(r"\bComp\."), "Compare"),
    (re.compile(r"\bcomp\."), "compare"),
    # eBible's corrections: "1870. captives | AV: burned".
    (re.compile(r"\bAV\b"), "Authorized Version"),
    # The Translators to the Reader's saints: "S. \it Augustine\it*".
    (re.compile(r"\bS\. (?=\\\+?it [A-Z])"), "St. "),
    # ...and one inside an italic quotation: "\it The doctrine of S\it*. John".
    (re.compile(r"\bS(?=\\\+?it\*\. [A-Z])"), "St"),
    # The Epistle Dedicatory's address is in capitals: "DEFENDER OF THE FAITH, &c."
    # A line in capitals, not "LXX, &c." in a note, which ends in "\f*".
    (re.compile(r"(?<=[A-Z]{2}, )&c\.(?=[^a-z\n]*$)", re.M), "ETC."),
    (re.compile(r"&c\."), "etc."),
    # The Translators to the Reader's italic "\it &c\it*.", whose period is roman.
    (re.compile(r"&c\b"), "etc"),
]
TEXT_NAMES = {
    "Vat.": "Vatican Text",
    "Ald.": "Aldine Text",
    "Complut.": "Complutensian Text",
    "Vulg.": "Vulgate",
}
# The forms printed without a period of their own, as the sources print them:
# those that Chicago prints so, "Sept." as "LXX", and the Authorized Version
# and the text names in full.
UNSTOPPED = {
    "LXX": "LXX",
    "Sept": "LXX",
    "MS": "MS",
    "MSS": "MSS",
    "A. V": "Authorized Version",
    **{name.removesuffix("."): full for name, full in TEXT_NAMES.items()},
}
# The notes have already lost the period that closed them: "guard, A. V".
PERIOD = re.compile(r"(?<![\w.])(LXX|Sept|MSS?|A\. V|Vat|Ald|Complut|Vulg)(\.?)(?!\w)")
# Brenton's dates, mostly in small capitals: "a.d. 126", "(b.c. 217–209)".
# Only a.d. and b.c.: any other pair is left for UNCHICAGO to refuse.
ERA = re.compile(
    r"(?:\\(\+?)sc )?\b(?=a\.d|b\.c)([ab])\.([dc])\.(?(1)\\\1sc\*|)"
    r"(?: (\d+(?:[–-]\d+)?)\b)?"
)
# A period that also ends a sentence stays: one before the end of its note or
# its paragraph, or before a capital in the same run of text, after any
# closing quotation mark or bracket. A capital after a marker opens a
# rendering, a name as often as not ("Authorized Version \fqa Mattaniah").
SENTENCE_END = re.compile(r"(?:\\\+?\w+\*|['’”)])*(?:\\[fx]\*|\s+[A-Z]|[ \t]*(?:\n|$))")
# What must not be left once the forms are Chicago's: the forms the rules above
# replace, and those the file prints in full, which are never words.
UNCHICAGO = re.compile(
    r"\bi\. e\.|\bi\.e\.(?:\\it\*)? |\bq\. d\.|\b[Ss]cil\.|\bSept\b"
    # "Comp." at a note's end has lost its period, and compares nothing.
    r"|\b[Cc]omp(?:\.|\\f\*)"
    # "AD" before its year, never after it: "AD 126".
    r"|\d AD\b"
    r"|\bS(?:\. \\\+?it|\\\+?it\*\.) [A-Z]|&c\b|\b[ab]\.[dc]\."
    r"|(?<![\w.])(?:LXX|MSS?|A\. V)\.(?!" + SENTENCE_END.pattern + ")"
    r"|(?<![\w.])(?:[ON]\. ?T|A\. V|Vat|Ald|Complut|Vulg)(?!\w)|\bAV\b"
    # At a note's end, the period is already gone: "and so Chrysost\f*".
    r"|\b(?:App|Chrysost|Gram|Qu|Rom|om|nom|voc|absol|infin|imper|pl|qy|viz|niph"
    r"|fem|ob)(?:\.|\\f\*)|\bCateches\b|\bult\b|\b4to\b|\bEng\. Ver\b"
    r"|\d\.(?:li|[sd])\b"
)
# A number with a period within a note's sentence, which the file must decide:
# "after 5. shillings", "Mark 14:72\ft . and margin". Outside the notes, the
# corrections' "1870. it" and the supplied passages' "3. \it verse" are labels.
NUMBER_STOP = re.compile(r"\d(?:\\\+?\w+(?:\*|\s))*\. +(?:\\\+?\w+(?:\*|\s))*[a-z]")


def row(entry):
    """An added row, set as Brenton's are: the abbreviation in italic, and "for"
    its meaning."""
    meaning = LATIN.sub(r"\\it \1\\it*", entry["meaning"])
    return f"\\tr\n\\tc1 \\it {entry['abbreviation']}\\it*\n\\tc2 for {meaning}."


def completed(source_text, record):
    """The list without the removed rows, his meanings capitalized as
    Chicago does, and with added rows after his."""
    require(
        source_text.rstrip().split("\n")[-1].startswith("\\tc2 "),
        "Brenton's list of abbreviations doesn't end with its table",
    )
    removed = ABBREVIATIONS["expanded"]["removed"]
    for abbreviation in removed:
        source_text, found = re.subn(
            rf"\\tr\n\\tc1 \\it {re.escape(abbreviation)}[ \t]*\\it\*[ \t]*\n\\tc2 [^\n]*\n",
            "",
            source_text,
        )
        require(found == 1, f"Brenton's row met {found} times: {abbreviation}")
    record(
        "drop the rows for abbreviations printed in full",
        why=ABBREVIATIONS["expanded"]["why"],
        removed=removed,
    )
    meanings = ABBREVIATIONS["meanings"]["changes"]
    source_text = replaced_once(source_text, meanings, "Brenton's meaning")
    record(
        "lowercase the meanings that aren't proper nouns",
        why=ABBREVIATIONS["meanings"]["why"],
        changes={c["from"]: c["to"] for c in meanings},
    )
    added = [row(entry) for entry in ABBREVIATIONS["added"]]
    record(
        "complete the list of abbreviations",
        why=ABBREVIATIONS["why"],
        added=[entry["abbreviation"] for entry in ABBREVIATIONS["added"]],
    )
    return source_text.rstrip("\n") + "\n" + "\n".join(added) + "\n"


def chicago_forms(text, changes):
    """A stretch of text with its abbreviations in Chicago's forms, counting in
    changes each form it replaces."""

    def count(old, new):
        key = f"{old} → {new}"
        changes[key] = changes.get(key, 0) + 1

    for pattern, new in REPLACED:

        def replaced(m, new=new):
            printed = m.expand(new)
            count(m[0], printed)
            return printed

        text = pattern.sub(replaced, text)

    def unstopped(m):
        stop = "." if m[2] and SENTENCE_END.match(m.string, m.end()) else ""
        printed = UNSTOPPED[m[1]] + stop
        if printed != m[0]:
            count(m[0], printed)
        return printed

    text = PERIOD.sub(unstopped, text)

    def era(m):
        name = {"a": "AD", "b": "BC"}[m[2]]
        year = m[4]
        if year and name == "BC":
            printed = f"{year} BC"
        elif year:
            printed = f"AD {year}"
        else:
            printed = name + ("." if SENTENCE_END.match(m.string, m.end()) else "")
        count(re.sub(r"\d", "N", m[0]), re.sub(r"\d", "N", printed))
        return printed

    return ERA.sub(era, text)


def replaced_once(text, changes, name, where=""):
    """The text with each change's words, which it must hold once, replaced."""
    for change in changes:
        found = text.count(change["from"])
        require(found == 1, f"{name} met {found} times: {where}{change['from']}")
        text = text.replace(change["from"], change["to"])
    return text


def decided(code, text, record, section, name, operation):
    """The unit's text with the changes a section of the file decides for it,
    each met once."""
    changes = [c for c in ABBREVIATIONS[section]["changes"] if c["unit"] == code]
    text = replaced_once(text, changes, name, f"{code} ")
    if changes:
        record(
            operation,
            why=ABBREVIATIONS[section]["why"],
            changes={c["from"]: c["to"] for c in changes},
        )
    return text


def chicago(code, text, record, *, notes_only):
    """The unit's text with the abbreviations its list gives, and the numbers
    the file decides, in Chicago's forms, and those it doesn't give in full:
    in its notes only, or throughout."""
    original = text
    text = decided(
        code, text, record, "numbers", "Number change", "numbers in Chicago's forms"
    )
    # After the numbers, which a sum in pence is read by: "after five shillings".
    text = decided(
        code, text, record, "expanded", "Expansion", "abbreviations printed in full"
    )
    changes = {}
    if notes_only:
        # The translation stays as it is: a decision too must fall in a note.
        require(
            NOTE.sub("", text) == NOTE.sub("", original),
            f"Abbreviation decision changes the text outside the notes: {code}",
        )
        text = NOTE.sub(lambda m: chicago_forms(m[0], changes), text)
        left = [m for note in NOTE.finditer(text) for m in UNCHICAGO.finditer(note[0])]
    else:
        text = chicago_forms(text, changes)
        left = list(UNCHICAGO.finditer(text))
    require(not left, f"Abbreviations not in Chicago's forms: {[m[0] for m in left]}")
    stops = [
        m[0] for note in NOTE.finditer(text) for m in NUMBER_STOP.finditer(note[0])
    ]
    require(not stops, f"Number with a period within a note's sentence: {code} {stops}")
    if changes:
        record("abbreviations in Chicago's forms", forms=changes)
    return text
