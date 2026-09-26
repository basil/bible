"""The edition's notes: the 1611 translators' New Testament marginal notes, from
Calvin George's transcription, and Brenton's own notes and cross-references.

No note leaves a caller in the text. Each note is set as a footnote that opens
with its verse's reference and names the words it glosses (its lemma): "25:20 I
doubted of such manner of questions: or, I was doubtful how to enquire hereof".
Labels such as "Or," and "Gr." are roman, and only another rendering of the
glossed words is italic.

The rules below find each lemma and each note's italics. Where they go wrong,
edition/kjv-notes.json and edition/brenton-notes.json say what to print
instead, and why.
"""

import bisect
from collections import Counter
from dataclasses import dataclass
import functools
import itertools
import re
import unicodedata

from bible import paths, sources
from bible.checks import require
from bible.files import read_json
from bible.typography import GREEK, HEBREW
from bible.usfm import canonical_text, plain_text, verse_spans, word_spans, words_of

KJV_NOTES = read_json(paths.EDITION_DIR / "kjv-notes.json")
BRENTON_NOTES = read_json(paths.EDITION_DIR / "brenton-notes.json")
EXPECTED_NT_MARGINAL_NOTES = 775

# Labels that introduce another rendering of the glossed words, which is italic.
RENDERING_LABELS = {
    *("Or,", "or,", "or", "Or simply,", "Possibly,", "Perhaps"),
    *("Gr.", "Gr. sing.", "Heb.", "Hebrew"),
    *("Lit.", "lit.", "more lit.", "i. e.", "ie.", "viz.", "sc.", "scil.", "Scil."),
    *("q. d.", "Gr. q. d.", "adj. q. d."),
    *("Alex.", "Vat.", "Vat.,", "Vat. i.e.", "Complut.", "Ald.", "Vulg."),
    *("A. V.", "Margin,"),
    *("Some read,", "Some read", "some read,", "some read", "Some copies read,"),
    *("Many Greek copies have,", "Many ancient copies add these words,"),
    *("That is,", "that is,", "that is to say,"),
}
# Labels after which the note comments rather than renders, and stays roman.
OTHER_LABELS = {
    *("Hebraism.", "Hebrew.", "Heb. עֹבֹר."),
    *(
        "Appendix.",
        "Appendix",
        "App.",
        "Comp.",
        "Note.",
        "Vide supra,",
        "vide",
        "See",
        "Of course",
    ),
    *("nom.", "voc.", "pl.", "singular.", "ver.", "bis."),
    *("Bos", "P. Junius", "Tertullian"),
}
LABELS = RENDERING_LABELS | OTHER_LABELS
# Names, which keep their capital where a note runs on from its lemma: of
# languages, texts, versions and people, and the pronoun "I".
NAMES = re.compile(
    r"(?:Gr|Heb|Hebrew|Hebraism|Syr|Alex|Vat|Complut|Ald|Vulg|A\. V|App|Appendix"
    r"|Bos|P\. Junius|Tertullian|Prof\. Lee|I)(?!\w)"
)
# Abbreviations, whose full stop stays at the end of a note ("so the Heb.").
ABBREVIATION = re.compile(
    r"(?<![\w'’])(?:etc|&c|Gr|Heb|Syr|Alex|Vat|Complut|Ald|Vulg|Chrysost|LXX|A\. V"
    r"|O\. ?T|N\. ?T|App|Comp|lit|Lit|i\. e|q\. d|sc|scil|viz|ver|ch|chap|pl"
    r"|absol|infin|imper|ult|Pet|N|s|ob)\.$"
)
# George's notes are plain text; a label opens a note or a sentence in it.
KJV_LABEL = re.compile(
    r"(?:^|(?<=[.;] ))("
    + "|".join(
        re.escape(label) for label in sorted(RENDERING_LABELS, key=len, reverse=True)
    )
    + r") "
)
# A rendering stops at the end of its sentence or clause, at "etc." unless the
# sentence goes on ("Gr. none etc. shall be seen by thine eyes"), and before a
# comment or citation ("his vow, compare Acts 18. 18", "for him, Rom. 11. 36",
# "lascivious ways, as some copies read", "horn, so Heb.", "cold, probably the
# right reading", "breach, as in ch. xii.", "it, sc. the people").
RENDERING_END = re.compile(
    r"(?<!\betc)(?<!&c)\.['’”]?(?=\s|$)|\.(?=\s+[^\sa-z]|$)|[;:?!(—]"
    r"|,\s+(?=(?:but|which|compare|see|chap|ver|probably|perhaps|so|if|as in)\b"
    r"|(?:sc|scil|viz)\.|i\.\s?e\.|q\.\s?d\.|\d|[A-Z][a-z]*\.\s*\d)"
    r"|,?\s+(?=as some\b)"
)
# Greek or Hebrew quoted in a note.
QUOTED = re.compile(f"[{GREEK}{HEBREW}]")
# Greek that opens a rendering and is followed by its English, which is the
# rendering: "Alex. ἐντολαί, commands", "some read λαοῦ 'people'".
GREEK_GLOSS = re.compile(rf"\s*[{GREEK}][{GREEK}’'\s]*,?\s+(?=['‘“]?[A-Za-z])")
# The words a note quotes as added are the reading, as after "+": "Heb. and
# Alex. insert 'priest'", "Alex. adds, 'and I the shepherd have done wickedly'".
ADDED = re.compile(r"\s*(?:adds?|inserts?),?\s+(?=['‘“])")
# "X, or Y" and "X, etc." (or "&c.") set only X and Y in italic.
RENDERING_SEPARATOR = re.compile(r",?\s+or,?\s+|,?\s*(?:\betc\b|&c\b)")
# What follows a label but comments on the reading instead of giving one:
# "Alex. has the following", "Gr. plural", "Alex. adds to", "Heb. omits".
COMMENTARY = re.compile(
    r"\s*(?:(?:probably|perhaps|possibly|see|compare|comp|cf"
    r"|ha(?:s|ve)(?=\s+(?:the|a|an|this|these|those|no|nothing|only|here|it|them)\b)"
    r"|plural|singular|sing|participle|infin"
    r"|adds|add(?=\s*[,:])|omits?|reads?|inserts?|wants?|translates?)\b|[—(-])",
    re.I,
)
# A citation ("ver. 12", "3. 14"), not a rendering; figures alone ("187 years") are one.
NOT_A_RENDERING = re.compile(r"\d+\s*[.:]\s*\d|\b(?:ver|vv?|ch|chap)\.?\s*\d")
# Words that never end a lemma alone: they want the word after them.
LINKING_WORDS = {
    *("a", "an", "the", "of", "to", "and", "in", "on", "at", "by", "for", "from"),
    *("with", "as", "or", "unto", "upon", "into", "nor", "but"),
}
OPEN_WORDS = LINKING_WORDS | {
    *("thy", "his", "her", "my", "their", "your", "our", "its"),
    *("this", "these", "those", "every", "all", "some", "any", "own"),
    *("thou", "he", "she", "we", "ye", "they", "i"),
}
# Words that open a clause, where a lemma stops unless the rendering has them.
CLAUSE_WORDS = {
    *("that", "which", "who", "whom", "whose", "when", "where", "because"),
    *("if", "lest", "whereas", "while", "until"),
}
# Pronouns whose relative clause belongs to them: "those who ...", "he that ...".
ANTECEDENTS = {"those", "these", "he", "she", "they", "them", "him", "all", "one"}
CONJUNCTIONS = {"and", "but", "or", "nor"}
ARTICLES = {"a", "an", "the"}
POSSESSIVES = {
    *("thy", "thine", "his", "her", "my", "mine", "their", "your", "our", "its"),
}
PREPOSITIONS = {
    *("of", "to", "in", "on", "at", "by", "for", "from", "with", "unto", "upon"),
    *("into", "among", "amongst", "above", "under", "over", "before", "after"),
    *("against", "toward", "towards", "through", "within", "without", "about"),
}
# Labels at the start of a note, which it runs on from.
LABEL_START = re.compile(
    "|".join(re.escape(label) for label in sorted(LABELS, key=len, reverse=True))
    + r"(?!\w)"
)
# Finite verbs, which make a note that opens with neither a label nor a
# rendering a sentence: "the word Batus in the original containeth nine gallons".
FINITE_VERB = re.compile(
    r"\b(?:is|are|was|were|has|hath|have|had|can|could|may|might|must|shall|should"
    r"|will|would|seems?|appears?|reads?|read|renders?|retains?|copies|quotes?"
    r"|takes?|begins?|continues?|ends|belongs?|comes?|form|maintain|signifi(?:es|eth)"
    r"|contain(?:s|eth)|cometh|importeth)\b"
)
# A note that measures nothing glosses its clause, or the clause's first words.
CLAUSE_LEMMA_WORDS = 6
# A cross-reference shows where the quotation begins, so it takes a longer clause.
XREF_CLAUSE_LEMMA_WORDS = 8
# How far "those who ..." reaches into its clause.
RELATIVE_LEMMA_WORDS = 8
DEFAULT_LEMMA_WORDS = 4
# Punctuation that ends the words a note can gloss.
CLAUSE_END = re.compile(r"[,;:.?!()—]")
# Markers that start a new line of text inside a verse.
LINE_START = re.compile(r"\s*\\(?:p|m|b|nb|pi\d?|q\d?|qm\d?|li\d?|mi|d|s\d?)\b")
# Punctuation and quotation marks stay roman at either end of an italic run.
# A backtick stays with its word: SmartyPants reads it as an opening quote
# only before a letter.
TRIM = " \n.,;:?!+'‘’“”\""


@dataclass
class Entry:
    """One note, ready to be set as a footnote."""

    key: str
    reference: str
    position: int  # in the text without notes
    lemma: str | None  # None for a note on the whole verse
    plain: str  # the note's text
    styles: list[str]  # each character's style
    rule: str
    style: str  # the rule that set its italics
    sentence: bool | None = None  # an exception's say, over is_sentence's

    @property
    def printed(self):
        """The note's text and styles as printed: a sentence with its capital
        and a closing full stop; any other note without one, and after a lemma,
        running on from the colon.

        Besides their corrections, the "See" that opens a cross-reference and
        the words a widened lemma adds to its renderings (echoed), these are
        the only changes the edition makes to the words of the notes.
        """
        if (
            self.sentence
            if self.sentence is not None
            else is_sentence(self.plain, self.styles)
        ):
            return closed(self.plain, self.styles)
        plain, styles = unclosed(self.plain, self.styles)
        if self.lemma is not None:
            plain = run_on(plain, styles)
        return plain, styles

    @property
    def body(self):
        """The USFM after the reference and lemma."""
        return usfm_body(*self.printed)

    @property
    def styled(self):
        """The note as printed, with its italic between underscores."""
        return underscored(*self.printed)


# A bracketed remark of the transcriber's or eBible's, with a space beside it.
REMARK = re.compile(r" ?\[[^\]]*\] ?")
EMPTY_BRENTON_NOTE = re.compile(r"\\f \+ \\fr \S+ \\f\*")


def change(before, after):
    """Where after departs from before: the offset, the stretch of before it
    replaces, and what replaces it."""
    start = 0
    while start < min(len(before), len(after)) and before[start] == after[start]:
        start += 1
    end = 0
    while (
        end < min(len(before), len(after)) - start
        and before[-1 - end] == after[-1 - end]
    ):
        end += 1
    return start, before[start : len(before) - end], after[start : len(after) - end]


def punctuation(text):
    return len(text) == 1 and unicodedata.category(text).startswith("P")


def letter_slip(old, new):
    """The kind of slip that replaces old with new, if it is one letter's."""
    if not old and len(new) == 1 and new.isalpha():
        return "missing letter"
    if not new and len(old) == 1 and old.isalpha():
        return "stray letter"
    if len(old) == len(new) == 1 and old.isalpha() and new.isalpha():
        return "wrong letter"
    return None


def correction_category(before, after):
    """The kind of slip a correction mends, or None if it is none of them."""
    at, old, new = change(before, after)
    if not old and new == " ":
        return "missing word space"
    if not old and punctuation(new):
        return "missing punctuation"
    if not new and punctuation(old):
        return "stray punctuation"
    if punctuation(old) and punctuation(new):
        return "wrong punctuation"
    if kind := letter_slip(old, new):
        return kind
    if old and not new:
        beside = (
            before[max(0, at - len(old)) : at],
            before[at + len(old) :][: len(old)],
        )
        if old in beside:
            return "doubled text"
        if REMARK.fullmatch(old):
            return "remark"
        if EMPTY_BRENTON_NOTE.fullmatch(old):
            return "empty note"
    if old == "[Greek characters]" and re.fullmatch(rf"[{GREEK}\s,.;]+", new):
        return "omitted Greek"
    return None


def check_category(category, entry, kind, key, what="slip"):
    """An entry must fit a category, unless it is marked uncategorized, and
    only then."""
    uncategorized = entry.get("uncategorized", False)
    require(
        category is not None or uncategorized,
        f"{kind} fits no category of {what}: {key}",
    )
    require(
        category is None or not uncategorized,
        f"{kind} listed as uncategorized is a {category}: {key}",
    )


def corrected(text, correction, kind, key):
    """The text with a correction's one occurrence of its "from" replaced.

    The correction must mend a slip of a known kind, unless it is marked
    uncategorized.
    """
    require(text.count(correction["from"]) == 1, f"{kind} does not apply: {key}")
    category = correction_category(correction["from"], correction["to"])
    check_category(category, correction, kind, key)
    return text.replace(correction["from"], correction["to"])


@functools.cache
def marginal_notes():
    """The 1611 translators' New Testament marginal notes, by book, in source order.

    George's listing gives a reference, the words the note glosses (the lemma), and
    the note. The Old Testament entries belong to the Hebrew Old Testament, which
    this edition does not print, so they are never read.
    """
    text = (paths.ROOT / sources.SOURCES["marginal_notes"]["file"]).read_text(
        encoding="utf-8"
    )
    require(
        text.count("\nMatthew 1:11 ") == 1,
        "Marginal notes New Testament boundary changed",
    )
    books = KJV_NOTES["books"]
    entry_pattern = re.compile(
        "(" + "|".join(map(re.escape, books)) + r") (\d+):(\d+) (.+?): (.+)"
    )
    corrections = dict(KJV_NOTES["corrections"])
    exceptions = KJV_NOTES["notes"]
    result = {}
    seen = Counter()
    for paragraph in re.split(r"\n\s*\n", text[text.index("\nMatthew 1:11 ") :]):
        # The Markdown wraps long entries; a continuation line joins its entry.
        entry = " ".join(paragraph.split())
        if not entry:
            continue
        match = entry_pattern.fullmatch(entry)
        require(match is not None, f"Unparsed marginal note: {entry}")
        book, chapter, verse, lemma, note = match.groups()
        code = books[book]
        key = f"{code} {chapter}:{verse} {lemma}"
        seen[key] += 1
        if seen[key] > 1:
            key += f"#{seen[key]}"
        if key in corrections:
            note = corrected(
                note, corrections.pop(key), "Marginal note correction", key
            )
        require(
            "[" not in note and "]" not in note,
            f"Transcriber's remark left in marginal note: {key}",
        )
        result.setdefault(code, []).append(
            {
                "key": key,
                "chapter": chapter,
                "verse": verse,
                "lemma": lemma,
                "note": note,
            }
        )
    require(not corrections, f"Unused marginal note corrections: {sorted(corrections)}")
    keys = {n["key"] for notes in result.values() for n in notes}
    require(
        set(exceptions) <= keys,
        f"Unused marginal note exceptions: {sorted(set(exceptions) - keys)}",
    )
    require(
        len(keys) == EXPECTED_NT_MARGINAL_NOTES,
        f"Expected {EXPECTED_NT_MARGINAL_NOTES} New Testament marginal notes, found {len(keys)}",
    )
    return result


# Note bodies: labels roman, renderings italic.


def labelled_pieces(text):
    """Plain note text as (kind, text) pieces, its labels found by KJV_LABEL."""
    pieces = []
    last = 0
    for match in KJV_LABEL.finditer(text):
        if match.start() > last:
            pieces.append(("text", text[last : match.start()]))
        pieces.append(("label", match[0]))
        last = match.end()
    if last < len(text):
        pieces.append(("text", text[last:]))
    return pieces


def unclosed(plain, styles):
    """The note's text and styles without its closing full stop, before any
    closing quotation mark ("A. V. 'my people'"), unless the stop ends an
    abbreviation ("etc.", "so the Heb.") or is the last of an ellipsis."""
    stop = re.search(r"(?<!\.)\.(?=['’”\"]?$)", plain)
    if not stop or ABBREVIATION.search(plain[: stop.end()]):
        return plain, styles
    at = stop.start()
    return plain[:at] + plain[at + 1 :], styles[:at] + styles[at + 1 :]


def is_sentence(plain, styles):
    """Whether the note is a sentence of its own: it opens with neither a label,
    a rendering nor a reference, and has a finite verb outside its renderings."""
    roman = "".join(c if style == "ft" else " " for c, style in zip(plain, styles))
    return (
        styles[0] == "ft"
        and not LABEL_START.match(plain)
        and FINITE_VERB.search(roman) is not None
    )


def closed(plain, styles):
    """The sentence with its first letter a capital, and a closing full stop
    where it has none: George's notes have neither. Quoted Greek or Hebrew
    keeps its letter."""
    if not re.search(r"[.?!]['’”\"]?$", plain):
        plain, styles = plain + ".", [*styles, "ft"]
    if re.match("[a-z]", plain):
        plain = plain[0].upper() + plain[1:]
    return plain, styles


def overridden_sentence(exception, plain, styles, key):
    """An exception's say on whether the note is a sentence."""
    sentence = exception.get("sentence")
    require(
        sentence is None or sentence != is_sentence(plain, styles),
        f"Note sentence override changes nothing: {key}",
    )
    return sentence


def run_on(plain, styles):
    """The note's text as it runs on from its lemma's colon: its first word
    lowercased ("elder: or, greater"), unless the word is a name ("his: Alex.
    their"), a reference, in capitals, or in quotation marks."""
    if (
        styles[0] == "xt"
        or NAMES.match(plain)
        or not re.match(r"[A-Z](?![A-Z])", plain)
    ):
        return plain
    return plain[0].lower() + plain[1:]


def brenton_pieces(body):
    """A Brenton note body as (kind, text) pieces.

    Brenton printed his labels in italic, and the eBible text marks them fqa, but
    it marks the same way the words he cites: those stay italic.
    """
    pieces = []
    kind = "text"
    outer = []
    # An opening marker takes the space after it; a closing one does not.
    for match in re.finditer(r"\\(\+?[\w-]+\*)|\\(\+?[\w-]+) ?|[^\\]+", body):
        marker = match[1] or match[2]
        if marker is None:
            pieces.append((kind, match[0]))
        elif marker == "ft":
            kind = "text"
        elif marker in ("fqa", "fl"):
            kind = "fqa"
        elif marker == "xt":
            kind = "xt"
        elif marker == "+it":
            outer.append(kind)
            kind = "fqa"
        elif marker == "+it*" and outer:
            kind = outer.pop()
        else:
            require(False, f"Unexpected marker in a Brenton note: \\{marker}")
    # Merge runs that one marker split ("\\ft + \\ft 'and ...'"), and take the
    # full stop that follows "Gr" or "Lit" into the label.
    merged = []
    for kind, text in pieces:
        # "\\+it Gr. \\+it* name": one space where two runs meet.
        if merged and merged[-1][1].endswith(" "):
            text = text.lstrip(" ")
            if not text:
                continue
        if merged and kind == "text" and merged[-1][0] == kind:
            merged[-1] = (kind, merged[-1][1] + text)
        elif (
            merged
            and kind == "text"
            and text.startswith(".")
            and merged[-1][0] == "fqa"
            and merged[-1][1].strip() + "." in RENDERING_LABELS
        ):
            merged[-1] = ("fqa", merged[-1][1].strip() + ". ")
            merged.append((kind, text[1:].lstrip()))
        else:
            merged.append((kind, text))
    result = []
    for kind, text in merged:
        if kind == "fqa":
            labelled = text.strip() in LABELS
            result.append(("label" if labelled else "cited", text))
        elif kind == "text":
            # A few labels are left in the note text ("Some read, out of").
            result += labelled_pieces(text)
        else:
            result.append((kind, text))
    return result


def italicize(styles, plain, start, end):
    while start < end and plain[start] in TRIM:
        start += 1
    while end > start and plain[end - 1] in TRIM:
        end -= 1
    for i in range(start, end):
        if styles[i] != "xt":
            styles[i] = "fqa"
    return plain[start:end]


def styled(pieces):
    """The note's text, each character's style, and its first rendering.

    Styles are ft (roman), fqa (italic) and xt (a reference).
    """
    plain = "".join(text for _, text in pieces)
    styles = []
    starts = []
    for kind, text in pieces:
        starts.append(len(styles))
        styles += ["xt" if kind == "xt" else "ft"] * len(text)
    for (kind, text), start in zip(pieces, starts):
        if kind == "cited":
            italicize(styles, plain, start, start + len(text))
    alternative = None
    for i, (kind, text) in enumerate(pieces[:-1]):
        if kind != "label" or text.strip() not in RENDERING_LABELS:
            continue
        if pieces[i + 1][0] != "text":
            continue
        # A label inside a sentence ("The Gr. word ...") introduces no rendering,
        # but one after a comma does ("rightness, or straightness"), as does "or"
        # after a rendering ("do good or make good"), and a label joined to
        # another ("Heb. and Alex. Samuel").
        sentence = re.split(r"[.;](?:\s|$)", plain[: starts[i]])[-1]
        before = plain[: starts[i]].rstrip(TRIM)
        continues = (
            text.strip() in ("or", "or,")
            and before != ""
            and styles[len(before) - 1] == "fqa"
        )
        if (
            re.search(r"\w\s*$", sentence)
            and not continues
            and not (
                i > 1
                and pieces[i - 2][0] == "label"
                and pieces[i - 1][1].strip() in CONJUNCTIONS
            )
        ):
            continue
        # A word Brenton set in italic inside the rendering ("a head of hair
        # even hair") does not end it, but a comma from that word on does
        # ("made ellulim, a Hebrew word").
        ends = [start for (kind, _), start in zip(pieces, starts) if kind != "text"]
        stop = next((end for end in ends if end > starts[i + 1]), len(plain))
        if stop < len(plain) and pieces[i + 2][0] == "cited":
            resume = next((end for end in ends if end > stop), len(plain))
            comma = plain.find(",", stop, resume)
            stop = resume if comma < 0 else comma
        after = plain[starts[i + 1] : stop]
        extent = RENDERING_END.split(after, maxsplit=1)[0]
        start = starts[i + 1]
        # Greek before its English renders by the English ("Alex. ἐντολαί,
        # commands"), and words quoted as added are the reading ("insert
        # 'priest'").
        if gloss := GREEK_GLOSS.match(extent) or ADDED.match(extent):
            start += gloss.end()
            extent = extent[gloss.end() :]
        # Quoted Greek or Hebrew ends a rendering after a comma ("furnace,
        # κάμινον"). Inside a sentence it makes the sentence a comment ("the
        # word עדנה"), unless an earlier comma ends the rendering ("the hams,
        # from γόνν").
        # A rendering in quotation marks ends with them ("'turned away,' but").
        if closing := re.match(
            r"\s*['‘“].*?[^\W\d_][,.;:?!]?(['’”])(?![^\W\d_])", extent
        ):
            extent = extent[: closing.start(1)]
        if quoted := QUOTED.search(extent):
            extent = extent[: quoted.start()]
            if not re.search(r",\s*$", extent):
                extent = extent[: extent.rfind(",")] if "," in extent else ""
        # Words that run into another label and end on one like "the" or "as"
        # introduce it ("Gr. from the Heb.", "O Lord, as in Heb."): they comment.
        tail = word_spans(extent)
        if (
            tail
            and tail[-1][0] in LINKING_WORDS
            and stop < len(plain)
            and pieces[i + 2][0] == "label"
            and pieces[i + 2][1].strip().rstrip(",").lower() != "or"
            and after.rstrip().endswith(extent.rstrip())
        ):
            extent = extent[: extent.rfind(",")] if "," in extent else ""
        # "Heb. and Alex. Samuel": the conjunction joins two labels.
        joins_labels = (
            extent.strip() in CONJUNCTIONS
            and i + 2 < len(pieces)
            and pieces[i + 2][0] == "label"
        )
        if not extent.strip() or COMMENTARY.match(extent) or joins_labels:
            continue
        if NOT_A_RENDERING.search(extent):
            continue
        last = 0
        for separator in [*RENDERING_SEPARATOR.finditer(extent), None]:
            end = separator.start() if separator else len(extent)
            words = italicize(styles, plain, start + last, start + end)
            # "Alex. + the Lord" adds to the text rather than rendering it.
            if alternative is None and words and not extent.lstrip().startswith("+"):
                alternative = words
            last = separator.end() if separator else len(extent)
    # Two italic runs a space apart are one ("innocent things").
    for match in re.finditer(r"(?<=\S) +(?=\S)", plain):
        if styles[match.start() - 1] == styles[match.end()] == "fqa":
            styles[match.start() : match.end()] = ["fqa"] * len(match[0])
    return plain, styles, alternative


def underscored(plain, styles):
    """The note with its italic between underscores, as the exception files write it."""
    result = []
    italic = False
    for char, style in zip(plain, styles):
        if (style == "fqa") != italic:
            result.append("_")
            italic = not italic
        result.append(char)
    return "".join(result) + ("_" if italic else "")


def overridden_styles(note, plain, styles, key):
    """Styles from an exception's note, whose underscores mark its italic."""
    require(
        note.replace("_", "") == plain,
        f"Note override does not match the note: {key}",
    )
    result = []
    italic = False
    for char in note:
        if char == "_":
            italic = not italic
            continue
        result.append("fqa" if italic else "ft")
    require(not italic, f"Unclosed italic in note override: {key}")
    return [
        "xt" if original == "xt" else style for original, style in zip(styles, result)
    ]


def usfm_body(plain, styles):
    """The note text as ft, fqa and xt runs."""
    runs = []
    for char, style in zip(plain, styles):
        # A marker takes the space after it, so a space ends the run before,
        # whatever its style.
        if runs and (runs[-1][0] == style or char.isspace()):
            runs[-1][1] += char
        else:
            runs.append([style, char])
    return "".join(f"\\{style} {text}" for style, text in runs)


def first_italic(plain, styles):
    """The first italic run of a note, without its surrounding punctuation."""
    for italic, run in itertools.groupby(
        zip(plain, styles), key=lambda pair: pair[1] == "fqa"
    ):
        if italic and (text := "".join(char for char, _ in run).strip(TRIM)):
            return text
    return None


def note_body(pieces, override, key, source):
    """The note's text, each character's style, its first rendering, and its
    styling rule.

    The text's USFM must print the source's text, word spaces included.
    """
    plain, styles, alternative = styled(pieces)
    # Space at either end of a note would print, and hide its closing full stop
    # ("Gr. name. ", 1 Kingdoms 17:13).
    start, end = len(plain) - len(plain.lstrip()), len(plain.rstrip())
    plain, styles = plain[start:end], styles[start:end]
    # An empty note would print only its reference and lemma.
    require(unclosed(plain, styles)[0], f"Empty note: {key}")
    require("_" not in plain, f"Underscore in note: {key}")
    rule = "rendering" if alternative else "roman"
    if override is not None:
        changed = overridden_styles(override, plain, styles, key)
        require(changed != styles, f"Note override changes nothing: {key}")
        styles = changed
        rule = "override"
        # The lemma is measured by the rendering the override italicizes.
        alternative = first_italic(plain, styles)
    require(
        plain_text(usfm_body(plain, styles)) == plain_text(source),
        f"Note restyling changed its text: {key}",
    )
    return plain, styles, alternative, rule


# Lemmas.


def occurrences(words, phrase):
    return [
        i
        for i in range(len(words) - len(phrase) + 1)
        if [w for w, _, _ in words[i : i + len(phrase)]] == phrase
    ]


def ends_clause(verse, words, i):
    """Whether punctuation between words[i] and the next word ends a clause."""
    return bool(CLAUSE_END.search(plain_text(verse[words[i][2] : words[i + 1][1]])))


def crosses_clause(verse, words, first, last):
    return any(ends_clause(verse, words, i) for i in range(first, last))


def whole_compounds(verse, words, first, last):
    """The span widened to whole hyphenated words (flood-gates, seven-fold)."""
    while first > 0 and verse[words[first - 1][2] : words[first][1]] == "-":
        first -= 1
    while last + 1 < len(words) and verse[words[last][2] : words[last + 1][1]] == "-":
        last += 1
    return first, last


def unique_span(verse, words, first, last, lone=False):
    """The shortest widening of words[first..last] that occurs once in the verse.

    A widening that stays within its clause and does not end on a word like
    "the" or "his" is preferred, even at up to two words longer; of equally
    good ones, the shortest, then the one to the right. Words that already
    occur once are left as they are, unless they end on "the" or "of"; a lone
    word the note is about (lone) stands even then ("for: Or, unto").
    """

    def unique(span):
        return (
            len(occurrences(words, [w for w, _, _ in words[span[0] : span[1] + 1]]))
            == 1
        )

    def awkwardness(span):
        return 2 * crosses_clause(verse, words, *span) + (
            words[span[1]][0] in OPEN_WORDS
        )

    span = whole_compounds(verse, words, first, last)
    if unique(span) and (
        words[span[1]][0] not in LINKING_WORDS or (lone and span[0] == span[1])
    ):
        return span
    best = None
    for extra in range(1, len(words)):
        if best and (awkwardness(best[1]) == 0 or extra > best[0] + 2):
            break
        for left in range(extra + 1):
            if first - left < 0 or last + extra - left >= len(words):
                continue
            span = whole_compounds(verse, words, first - left, last + extra - left)
            if unique(span) and (
                best is None or awkwardness(span) < awkwardness(best[1])
            ):
                best = extra, span
    return best[1] if best else (first, last)


def phrase_span(words, phrase, key, occurrence=None):
    """The place in the verse where an exception's lemma occurs: its one
    occurrence, or the one the exception names if it occurs more than once."""
    tokens = words_of(phrase)
    hits = occurrences(words, tokens)
    require(
        (
            tokens and len(hits) == 1
            if occurrence is None
            else len(hits) > 1 and 0 < occurrence <= len(hits)
        ),
        (
            f"Lemma override not found exactly once: {key} ({len(hits)})"
            if occurrence is None
            else f"Lemma override occurrence not found, or not needed: {key} ({len(hits)})"
        ),
    )
    first = hits[(occurrence or 1) - 1]
    return first, first + len(tokens) - 1


def overridden_lemma(
    verse, words, exception, span, glossed, rule, key, occurrence=None
):
    """The lemma's span, the span of the words it glosses, and the rule, or
    those of the exception's lemma if it has one.

    An exception's lemma is the words the note glosses. One that occurs more
    than once in the verse comes with its occurrence, and is widened like any
    other lemma.
    """
    if "lemma" not in exception:
        return span, glossed, rule
    if exception["lemma"] is None:
        chosen = widened = None
    elif occurrence is None:
        chosen = widened = phrase_span(words, exception["lemma"], key)
    else:
        chosen = phrase_span(words, exception["lemma"], key, occurrence)
        widened = unique_span(verse, words, *chosen)
    # A lemma the same as the widened one still changes what the rendering echoes.
    require(
        (widened, chosen) != (span, glossed), f"Lemma override changes nothing: {key}"
    )
    return widened, chosen, "override"


def same_word(a, b):
    # Every way of stripping a suffix, so "executes" (execute-s) meets "execute".
    def stems(word):
        return {word} | {
            word[: -len(suffix)]
            for suffix in ("ings", "ing", "eth", "est", "ed", "es", "s", "d", "ly")
            if word.endswith(suffix) and len(word) - len(suffix) >= 3
        }

    return a == b or bool(stems(a) & stems(b))


def clause_after(verse, words, first, other):
    """The words from first to the end of their clause, as a note can gloss them."""
    clause = [first]
    for i in range(first + 1, len(words)):
        if ends_clause(verse, words, i - 1):
            break
        # "those who had in them divining spirits" is one phrase.
        if (
            words[i][0] in CLAUSE_WORDS
            and words[i][0] not in other
            and words[i - 1][0] not in OPEN_WORDS
        ):
            break
        clause.append(i)
    return clause


def clause_before(verse, words, last):
    """The words from the start of their clause to last."""
    first = last
    while first > 0 and not ends_clause(verse, words, first - 1):
        first -= 1
    return list(range(first, last + 1))


def measured(words, clause, other, backward=False):
    """How many words of the clause a rendering stands for, and the rule that said so.

    Forward, the words run from the caller to the rendering's last word. Backward
    they end at the caller, so they run from the rendering's first word, counted
    back from its last, to the caller.
    """
    if other[-1] not in LINKING_WORDS:
        near = clause[::-1] if backward else clause
        for j, i in enumerate(near[: len(other) + 3]):
            if same_word(words[i][0], other[-1]):
                return (j + len(other) if backward else j + 1), "last-word"
    size = len(other)
    # The word the lemma would start with, which the rendering's article stands for.
    edge = clause[-min(size, len(clause))] if backward else clause[0]
    if size > 1 and other[0] in ARTICLES and words[edge][0] not in ARTICLES:
        size -= 1
    return size, "length"


def inferred_lemma(kind, verse, words, offset, alternative, widen=True):
    """The words a Brenton note or cross-reference glosses, and the rule that found them.

    Brenton's caller stands before the glossed words, or after the first of them
    if the rendering begins with it. A rendering measures how far they reach, by
    its last word or its length; otherwise the clause, or its first few words,
    stands for the place. A caller at the end of a verse or a line glosses the
    words before it if the note renders them, and otherwise the whole verse
    (None). Unless widen is false, the words are widened until they occur once.
    """

    def unique(verse, words, first, last, lone=False):
        if widen:
            return unique_span(verse, words, first, last, lone)
        return first, last

    after = [i for i, (_, start, _) in enumerate(words) if start >= offset]
    # A rendering with figures ("Alex. 187 years") cannot be measured by its words.
    if alternative and re.search(r"\d", alternative):
        alternative = None
    other = words_of(alternative or "")
    if kind == "x" and after and after[0] <= 3:
        return None, "xref-verse"
    if not after or LINE_START.match(verse[offset:]):
        before = [i for i, (_, _, end) in enumerate(words) if end <= offset]
        if not other or kind == "x" or not before:
            return None, "verse-level"
        clause = clause_before(verse, words, before[-1])
        size, rule = measured(words, clause, other, backward=True)
        span = clause[-min(size, len(clause))], clause[-1]
        return unique(verse, words, *span), rule + " before"
    clause = clause_after(verse, words, after[0], other)
    # "and tents" for Alex. "cattle": the conjunction is not what the note renders.
    if (
        len(clause) > 1
        and words[clause[0]][0] in CONJUNCTIONS
        and (not other or other[0] not in CONJUNCTIONS)
    ):
        clause = clause[1:]
    if other and kind != "x":
        size, rule = measured(words, clause, other)
    else:
        rule = "xref-opening" if kind == "x" else "explanatory"
        whole = XREF_CLAUSE_LEMMA_WORDS if kind == "x" else CLAUSE_LEMMA_WORDS
        size = len(clause) if len(clause) <= whole else DEFAULT_LEMMA_WORDS
    # "his: Alex. their", "into: Gr. upon": a possessive, preposition or
    # conjunction rendered by one of its kind glosses it alone.
    alone = len(other) == 1 and any(
        other[0] in group and words[clause[0]][0] in group
        for group in (POSSESSIVES, PREPOSITIONS | CONJUNCTIONS)
    )

    def rounded(size):
        # Never end on a word like "the" or "his" while the clause goes on.
        size = min(size, len(clause))
        while (
            not alone
            and size < len(clause)
            and words[clause[size - 1]][0] in OPEN_WORDS
        ):
            size += 1
        return size

    size = rounded(size)
    # "those who" wants the rest of its clause.
    if (
        size > 1
        and words[clause[size - 1]][0] in CLAUSE_WORDS
        and words[clause[size - 2]][0] in ANTECEDENTS
    ):
        size = rounded(max(size + 2, RELATIVE_LEMMA_WORDS))
    if CLAUSE_END.search(plain_text(verse[offset : words[after[0]][1]])):
        rule += " after punctuation"
    span = whole_compounds(verse, words, clause[0], clause[size - 1])
    first, last = unique(verse, words, *span, lone=alone)
    # "the Evite: Alex. the Chorrhæan", "a consecration: Gr. an accomplishment":
    # the caller follows the word the rendering begins with.
    if (
        other
        and first == clause[0]
        and first > 0
        and indefinite(words[first - 1][0]) == indefinite(other[0])
        and indefinite(other[0]) != indefinite(words[first][0])
        and not ends_clause(verse, words, first - 1)
    ):
        first -= 1
    return (first, last), rule


def indefinite(word):
    """The word, with "an" as "a"."""
    return "a" if word == "an" else word


def lemma_text(verse, words, span):
    first, last = span
    return plain_text(verse[words[first][1] : words[last][2]])


def echo(verse, words, span, glossed):
    """The lemma's words before and after the words the note glosses: those it
    took in to occur once in the verse."""
    if span is None or span == glossed:
        return "", ""
    require(
        span[0] <= glossed[0] and glossed[1] <= span[1],
        "Lemma does not contain the words it glosses: "
        + lemma_text(verse, words, span),
    )
    words_glossed = lemma_text(verse, words, glossed)
    head = lemma_text(verse, words, (span[0], glossed[1]))
    tail = lemma_text(verse, words, (glossed[0], span[1]))
    return head[: len(head) - len(words_glossed)], tail[len(words_glossed) :]


def echoed(plain, styles, style, before, after):
    """The note with each rendering widened as its lemma was ("of your Father:
    or, with your Father"), so that it still stands in for the whole lemma.

    A note without a rendering is left as it is, whatever Brenton set in italic.
    """
    if style == "roman" or not (before or after):
        return plain, styles
    result, result_styles = "", []
    for italic, run in itertools.groupby(
        zip(plain, styles), key=lambda pair: pair[1] == "fqa"
    ):
        chars, run_styles = zip(*run)
        if italic:
            chars = before + "".join(chars) + after
            run_styles = ["fqa"] * len(chars)
        result += "".join(chars)
        result_styles += run_styles
    return result, result_styles


# Placing the notes.


def outside_styles(text, start, position, key):
    """The position moved out of any character style opening on the glossed word."""
    while opener := re.search(r"\\\+?(?:add|sc) $", text[start:position]):
        position = start + opener.start()
    preceding = text[start:position]
    require(
        len(re.findall(r"\\\+?(?:add|sc) ", preceding))
        == len(re.findall(r"\\\+?(?:add|sc)\*", preceding)),
        f"Note inside a character span: {key}",
    )
    return position


def set_footnotes(text, entries):
    """The text with each note as a caller-free footnote of its own.

    A footnote opens with its verse's reference and stands where the note's
    caller did, so PTXprint sets it on the page with the words it glosses.
    """
    parts = []
    last = 0
    # A stable sort keeps the notes at one place in order.
    for entry in sorted(entries, key=lambda e: e.position):
        lemma = f"\\fq {entry.lemma}: " if entry.lemma is not None else ""
        parts += [
            text[last : entry.position],
            f"\\f - \\fr {entry.reference} {lemma}{entry.body}\\f*",
        ]
        last = entry.position
    result = "".join(parts) + text[last:]
    require(
        re.sub(r"\\f - .*?\\f\*", "", result) == text
        and len(re.findall(r"\\f - ", result)) == len(entries),
        "Setting the notes changed the text",
    )
    return result


def review_entry(entry, verse, offset, words, span, source):
    """One line of the notes review: the verse with its lemma, and the note."""
    marks = {offset: "‸"}
    if span:
        marks[words[span[0]][1]] = marks.get(words[span[0]][1], "") + "**"
        marks[words[span[1]][2]] = "**" + marks.get(words[span[1]][2], "")
    shown = verse
    for at in sorted(marks, reverse=True):
        shown = shown[:at] + marks[at] + shown[at:]
    return {
        "key": entry.key,
        "rule": entry.rule,
        "verse": plain_text(shown),
        "lemma": entry.lemma,
        "note": entry.styled,
        "source": plain_text(source),
        "style": entry.style,
    }


# The 1611 marginal notes.


def anchor_category(lemma, anchor):
    """How the anchor's words differ from the lemma's, or None if by more than
    one category allows: words joined or parted, or one word's letter slip."""
    if "".join(lemma) == "".join(anchor):
        return "word division"
    differing = [(x, y) for x, y in zip(lemma, anchor) if x != y]
    if len(lemma) == len(anchor) and len(differing) == 1:
        _, old, new = change(*differing[0])
        return letter_slip(old, new)
    return None


def insert_marginal_notes(code, text, record, review=None):
    """Set the 1611 marginal notes on the Cambridge text as caller-free footnotes.

    Each note is anchored at George's lemma, or at the Cambridge words recorded
    for it in edition/kjv-notes.json where the spelling differs, the lemma
    occurs more than once, or the reference is wrong. The note names the words
    it is anchored at, widened until they occur only once in the verse, and
    its renderings take in the same words.
    """
    notes = marginal_notes().get(code, [])
    if not notes:
        return text
    require("\\f " not in text, f"Cambridge text already has footnotes: {code}")
    spans = {reference: (start, end) for reference, start, end in verse_spans(text)}
    entries = []
    for note in notes:
        key = note["key"]
        override = KJV_NOTES["notes"].get(key, {})
        reference = override.get("verse", f"{note['chapter']}:{note['verse']}")
        require(reference in spans, f"Marginal note verse missing: {key}")
        start, end = spans[reference]
        verse = text[start:end]
        words = word_spans(verse)
        anchor = words_of(override.get("anchor", note["lemma"]))
        if "anchor" in override:
            lemma = words_of(note["lemma"])
            require(anchor != lemma, f"Marginal note anchor changes nothing: {key}")
            check_category(
                anchor_category(lemma, anchor),
                override,
                "Marginal note anchor",
                key,
                what="difference",
            )
        hits = occurrences(words, anchor)
        occurrence = override.get("occurrence")
        require(
            len(hits) == 1 if occurrence is None else 0 < occurrence <= len(hits),
            f"Marginal note anchor not found exactly once: {key} ({len(hits)})",
        )
        first = hits[(occurrence or 1) - 1]
        glossed = whole_compounds(verse, words, first, first + len(anchor) - 1)
        # George's lemma of one word stands if it occurs once, even "for".
        span = unique_span(verse, words, *glossed, lone=anchor[0] not in ARTICLES)
        rule = "anchor" if span == (first, first + len(anchor) - 1) else "widened"
        # A 1611 note's occurrence is its anchor's, not its lemma override's.
        span, glossed, rule = overridden_lemma(
            verse, words, override, span, glossed, rule, key
        )
        # A lemma clear of George's anchor says where the note belongs ("George
        # swaps the two notes"), so the footnote follows it. A null lemma, for a
        # note on the whole verse, leaves the note at the anchor.
        if span and (span[1] < first or first + len(anchor) - 1 < span[0]):
            first = span[0]
        position = outside_styles(text, start, start + words[first][1], key)
        source = note["note"]
        plain, styles, _, style = note_body(
            labelled_pieces(source), override.get("note"), key, source
        )
        plain, styles = echoed(plain, styles, style, *echo(verse, words, span, glossed))
        entry = Entry(
            key,
            reference,
            position,
            lemma_text(verse, words, span) if span else None,
            plain,
            styles,
            rule,
            style,
            overridden_sentence(override, plain, styles, key),
        )
        entries.append(entry)
        if review is not None:
            review.append(
                review_entry(entry, verse, words[first][1], words, span, note["note"])
            )
    text = set_footnotes(text, entries)
    record(
        "insert 1611 translators' marginal notes (Calvin George's transcription)",
        source=sources.SOURCES["marginal_notes"]["file"],
        count=len(notes),
        lemma_rules=dict(Counter(e.rule for e in entries)),
        exceptions=[n["key"] for n in notes if n["key"] in KJV_NOTES["notes"]],
        corrected_notes=[
            n["key"] for n in notes if n["key"] in KJV_NOTES["corrections"]
        ],
    )
    return text


# Brenton's notes and cross-references.


# Any caller: the preface's notes use "*" as well as "+".
BRENTON_NOTE = re.compile(r"\\(f|x) \S \\(?:fr|xo) (\S+) ?(.*?)\\\1\*")


def in_its_place(text, key, snippet):
    """Whether the snippet's one occurrence lies where its key says: in the verse
    it names, or in a file without verses, in a note standing among the words it
    names.
    """
    start = text.index(snippet)
    end = start + len(snippet)
    place = key.partition(" ")[2]
    if verse := re.fullmatch(r"(\d+:\d+[a-z]?)(?:#([2-9]|[1-9]\d+))?", place):
        reference, number = verse.groups()
        if number is not None:
            matching = [m for m in BRENTON_NOTE.finditer(text) if m[2] == reference]
            index = int(number) - 1
            return (
                index < len(matching)
                and matching[index].start() <= start
                and end <= matching[index].end()
            )
        matching = [m for m in BRENTON_NOTE.finditer(text) if m[2] == reference]
        if in_a_note(text, snippet):
            return (
                bool(matching)
                and matching[0].start() <= start
                and end <= matching[0].end()
            )
        return any(
            verse_ref == reference and first <= start and end <= last
            for verse_ref, first, last in verse_spans(text)
        )
    if "#" in place:
        return False
    touched = [
        m for m in BRENTON_NOTE.finditer(text) if m.start() < end and start < m.end()
    ]
    if len(touched) != 1:
        return False
    note = touched[0]
    before, after = (
        words_of(BRENTON_NOTE.sub("", side))
        for side in (text[: note.start()], text[note.end() :])
    )
    words = words_of(place)
    return any(
        before[len(before) - k :] + after[: len(words) - k] == words
        for k in range(1, len(words))
    )


def in_a_note(text, snippet):
    """Whether the snippet's one occurrence lies within a note."""
    start = text.index(snippet)
    end = start + len(snippet)
    return any(
        m.start() <= start and end <= m.end() for m in BRENTON_NOTE.finditer(text)
    )


def corrected_brenton(source, text, record):
    """A Brenton source file with the corrections in edition/brenton-notes.json.

    Each correction is keyed by the source file's id and the verse or note it
    mends; #n names the nth note in a verse. Several corrections in one note
    form a list under one key. In a file without verses, the key names the words
    the note stands among. Outside notes a correction may mend only word spaces,
    so the translation stays eBible's: wording checks compare with corrected text.
    """
    corrections = {
        key: c
        for key, c in BRENTON_NOTES["corrections"].items()
        if key.split(" ")[0] == source
    }
    for key, group in corrections.items():
        for correction in group if isinstance(group, list) else [group]:
            mended = corrected(text, correction, "Brenton correction", key)
            require(
                in_its_place(text, key, correction["from"]),
                f"Brenton correction is not where its key says: {key}",
            )
            require(
                in_a_note(text, correction["from"])
                or canonical_text(correction["from"])
                == canonical_text(correction["to"]),
                f"Brenton correction changes the wording outside a note: {key}",
            )
            text = mended
    if corrections:
        record("correct eBible's Brenton text", corrections=sorted(corrections))
    return text


def restyle_brenton_notes(code, text, record, review=None):
    """Set Brenton's notes and cross-references as caller-free footnotes, each naming its lemma.

    A cross-reference becomes a footnote of "See" and its reference.
    """
    exceptions = {
        k: v for k, v in BRENTON_NOTES["notes"].items() if k.split(" ")[0] == code
    }
    # Each note with its position in the text without notes.
    found = []
    removed = 0
    for match in BRENTON_NOTE.finditer(text):
        found.append((match.start() - removed, match[1], match[2], match[3]))
        removed += len(match[0])
    clean = BRENTON_NOTE.sub("", text)
    require(
        "\\f " not in clean and "\\x " not in clean, f"Unparsed Brenton note: {code}"
    )
    if not found:
        require(
            not exceptions, f"Brenton note exceptions for a book without notes: {code}"
        )
        return text
    spans = verse_spans(clean)
    span_starts = [start for _, start, _ in spans]
    seen = Counter()
    entries = []
    for position, kind, source_reference, body in found:
        # A note just after a verse number stands before the space its span skips.
        ahead = re.compile(r"\s*").match(clean, position).end()
        index = bisect.bisect_right(span_starts, ahead) - 1
        require(index >= 0, f"Note before the first verse: {code} {source_reference}")
        reference, start, end = spans[index]
        position = max(position, start)
        require(
            reference == source_reference,
            f"Note reference disagrees with its verse: {code} {source_reference}",
        )
        seen[reference] += 1
        key = f"{code} {reference}" + (
            f"#{seen[reference]}" if seen[reference] > 1 else ""
        )
        exception = exceptions.get(key, {})
        source = body if kind == "f" else "See " + body
        plain, styles, alternative, style = note_body(
            brenton_pieces(source), exception.get("note"), key, source
        )
        verse = clean[start:end]
        words = word_spans(verse)
        offset = position - start
        span, rule = inferred_lemma(kind, verse, words, offset, alternative)
        glossed, _ = inferred_lemma(
            kind, verse, words, offset, alternative, widen=False
        )
        span, glossed, rule = overridden_lemma(
            verse,
            words,
            exception,
            span,
            glossed,
            rule,
            key,
            exception.get("occurrence"),
        )
        plain, styles = echoed(plain, styles, style, *echo(verse, words, span, glossed))
        entry = Entry(
            key,
            reference,
            outside_styles(clean, start, position, key),
            lemma_text(verse, words, span) if span else None,
            plain,
            styles,
            rule,
            style,
            overridden_sentence(exception, plain, styles, key),
        )
        entries.append(entry)
        if review is not None:
            review.append(review_entry(entry, verse, offset, words, span, source))
    keys = {e.key for e in entries}
    require(
        set(exceptions) <= keys,
        f"Unused Brenton note exceptions: {sorted(set(exceptions) - keys)}",
    )
    text = set_footnotes(clean, entries)
    record(
        "set Brenton's notes and cross-references as footnotes without callers",
        notes=sum(kind == "f" for _, kind, _, _ in found),
        cross_references=sum(kind == "x" for _, kind, _, _ in found),
        lemma_rules=dict(Counter(e.rule for e in entries)),
        exceptions=sorted(exceptions),
    )
    return text
