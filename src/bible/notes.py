"""What a note says: its labels, its renderings and what it cites, and how
the edition prints them.

Brenton's notes and the 1611 margin are read once, as their sources write
them. A label such as "Gr." or "Or," is roman, another rendering of the
glossed words is italic, and a citation is a reference of its own. The rules
here tell them apart; edition/brenton-notes.json and edition/kjv-notes.json
say what to print where the rules go wrong, and why. The notes that
edition/alexandrinus.json writes say what each of their parts is themselves.

A note is printed as a footnote without a caller: its verse, the words it is
about, and its text, which runs on from them unless it is a sentence of its
own. Besides corrections, the "See" that opens a cross-reference, the words a
widened lemma adds to its renderings, and the decisions of edition/prose.json,
the edition changes nothing of a note's words but its citations and
abbreviations, which print in the edition's forms.
"""

import re
from dataclasses import dataclass, replace
from difflib import SequenceMatcher

from bible import citations, lemmas, terminology, usfm, usj
from bible.checks import require
from bible.repairs import change
from bible.scripture import plain, word_spans
from bible.usfm import GREEK, HEBREW

# Labels that introduce another rendering of the glossed words, which is italic.
RENDERING_LABELS = {
    *("Or,", "or,", "or", "Or simply,", "Possibly,", "Perhaps"),
    *("Gr.", "Gr. sing.", "Heb.", "Hebrew"),
    *("Lit.", "lit.", "more lit.", "i. e.", "viz.", "sc.", "scil.", "Scil."),
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
    *("Appendix.", "Appendix", "App.", "Comp.", "Note.", "Vide supra,", "vide"),
    *("See", "Of course"),
    *("nom.", "voc.", "pl.", "singular.", "ver.", "bis."),
    *("Lambert Bos", "Patrick Junius", "Tertullian"),
}
LABELS = RENDERING_LABELS | OTHER_LABELS
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
# comment ("his vow, compare", "lascivious ways, as some copies read", "horn,
# so Heb.", "cold, probably the right reading", "breach, as in", "it, sc. the
# people"). A citation is a reference of its own, which ends it as well.
RENDERING_END = re.compile(
    r"(?<!\betc)(?<!&c)\.['’”]?(?=\s|$)|\.(?=\s+[^\sa-z]|$)|[;:?!(—]"
    r"|,\s+(?=(?:but|which|compare|see|probably|perhaps|so|if|as in)\b"
    r"|(?:sc|scil|viz)\.|i\.\s?e\.|q\.\s?d\.)"
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
    r"\s*(?:(?:also\s+)?(?:probably|perhaps|possibly|see|compare|comp|cf"
    r"|ha(?:s|ve)(?=\s+(?:the|a|an|this|these|those|no|nothing|only|here|it|them)\b)"
    r"|plural|singular|sing|participle|infin"
    r"|adds|add(?=\s*[,:])|omits?|reads?|inserts?|wants?|translates?"
    r"|ends(?=\s+the\s+verse\b)|includes(?=\s+the\s+clause\b))\b|[—(-])",
    re.I,
)
# Punctuation and quotation marks stay roman at either end of an italic run.
TRIM = " \n.,;:?!+'‘’“”\""
# Names, which keep their capital where a note runs on from its lemma: of
# languages, texts, versions and people, and the pronoun "I".
NAMES = re.compile(
    r"(?:Gr|Heb|Hebrew|Hebraism|Syr|Sept|Alex|Vat|Complut|Ald|Vulg|A\. V|App|Appendix"
    r"|Lambert Bos|Patrick Junius|Tertullian|Professor Samuel Lee|Brenton|Swete|Vatican|I)(?!\w)"
)
# Abbreviations, whose full stop stays at the end of a note ("so the Heb.").
# Not those the edition prints without one, or in full.
ABBREVIATION = re.compile(
    r"(?<![\w'’])(?:etc|&c|Gr|Heb|Syr|Alex|lit|Lit|i\. e|q\. d|sc|scil)\.$"
)
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
# What each part of a note the edition writes is, by its marker.
AUTHORED = {
    "fl": "label",
    "ft": "text",
    "fqa": "alternative",
    "fq": "quotation",
    "xt": "citation",
}
# How a part of a printed note is marked.
PRINTED = {"commentary": "ft", "reading": "fqa", "citation": "xt"}


@dataclass(frozen=True)
class Body:
    """A note's words and what each stretch of them is: text, a label, an
    alternative rendering, a quotation, or a citation.

    The reading is the rendering that measures how far the glossed words
    reach. A citation is bound to the words that write it, whatever they are.
    """

    plain: str
    roles: tuple
    reading: tuple | None
    rule: str
    citations: tuple = ()
    terms: tuple = ()

    @property
    def alternative(self):
        return self.plain[slice(*self.reading)] if self.reading else None

    @property
    def leaves(self):
        """The stretches of one role, each citation a stretch of its own, as
        (start, end, role, citation)."""
        intervals = list(self.roles)
        bound = {}
        for first, last, citation in self.citations:
            role = next(r for a, b, r in self.roles if a <= first < b)
            intervals = [
                (a, b, r)
                for x, y, r in intervals
                for a, b in ((x, min(y, first)), (max(x, last), y))
                if a < b
            ]
            intervals.append((first, last, role))
            bound[first] = citation
        return [(a, b, r, bound.get(a)) for a, b, r in sorted(intervals)]


class Roles:
    """A note's roles while they are being read."""

    def __init__(self, text, intervals=None):
        self.plain = text
        self.intervals = (
            list(intervals)
            if intervals is not None
            else [(0, len(text), "text")] if text else []
        )

    def kind_at(self, offset):
        return next(
            kind for start, end, kind in self.intervals if start <= offset < end
        )

    def mark(self, start, end, kind):
        if start == end:
            return
        require(
            0 <= start < end <= len(self.plain), "Note interpretation outside content"
        )
        result = []
        for first, last, prior in self.intervals:
            if last <= start or first >= end:
                result.append((first, last, prior))
                continue
            if first < start:
                result.append((first, start, prior))
            result.append((max(first, start), min(last, end), kind))
            if last > end:
                result.append((end, last, prior))
        self.intervals = []
        for first, last, role in result:
            if self.intervals and self.intervals[-1][2] == role:
                self.intervals[-1] = (self.intervals[-1][0], last, role)
            else:
                self.intervals.append((first, last, role))

    def reading(self, start, end, kind="alternative"):
        """Mark a rendering, without the punctuation at either end of it."""
        while start < end and self.plain[start] in TRIM:
            start += 1
        while end > start and self.plain[end - 1] in TRIM:
            end -= 1
        for first, last, role in tuple(self.intervals):
            if role != "citation" and first < end and start < last:
                self.mark(max(first, start), min(last, end), kind)
        return start, end

    def body(self, reading, rule, *, trim=False):
        start = len(self.plain) - len(self.plain.lstrip()) if trim else 0
        end = len(self.plain.rstrip()) if trim else len(self.plain)
        roles = tuple(
            (max(a, start) - start, min(b, end) - start, role)
            for a, b, role in self.intervals
            if max(a, start) < min(b, end)
        )
        if reading is not None:
            reading = (reading[0] - start, reading[1] - start)
            require(
                0 <= reading[0] < reading[1] <= end - start,
                "Note reading outside content",
            )
        return Body(self.plain[start:end], roles, reading, rule)


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


def source_text(note):
    """A source note's words after its origin, as its source marks them up:
    what the decision files pin and the review shows."""
    return usj.serialize(
        [
            item
            for item in note["content"]
            if not usj.is_type(item, "char", "fr")
            and not usj.is_type(item, "char", "xo")
        ]
    )


def source_pieces(note):
    """One of Brenton's notes as (kind, text) pieces.

    Brenton printed his labels in italic, and the eBible text marks them fqa,
    but it marks the same way the words he cites: those stay italic. A
    cross-reference is "See" and what it cites.
    """
    pieces = [("text", "See ")] if note["marker"] == "x" else []

    def visit(items, kind):
        for item in items:
            if isinstance(item, str):
                pieces.append((kind, item))
                continue
            marker = item.get("marker")
            if marker in ("fr", "xo"):
                continue
            if marker == "ft":
                visit(item["content"], "text")
            elif marker in ("fqa", "fl"):
                visit(item["content"], "emphasis")
            elif marker == "xt":
                visit(item["content"], "xt")
            elif marker == "it" and kind is not None:
                visit(item["content"], "emphasis")
            else:
                require(False, f"Unexpected marker in a Brenton note: \\{marker}")

    for item in note["content"]:
        if isinstance(item, str):
            pieces.append(("text", item))
        elif item["marker"] == "it":
            require(False, "Unexpected marker in a Brenton note: \\it")
        else:
            visit([item], None)
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
            and merged[-1][0] == "emphasis"
            and merged[-1][1].strip() + "." in RENDERING_LABELS
        ):
            merged[-1] = ("emphasis", merged[-1][1].strip() + ". ")
            merged.append((kind, text[1:].lstrip()))
        else:
            merged.append((kind, text))
    result = []
    for kind, text in merged:
        if kind == "emphasis":
            result.append(("label" if text.strip() in LABELS else "cited", text))
        elif kind == "text":
            # A few labels are left in the note text ("Some read, out of").
            result += labelled_pieces(text)
        else:
            result.append((kind, text))
    return result


def interpreted(pieces, key):
    """Read a source note's roles, and the first rendering, which measures
    the words the note is about."""
    text = "".join(value for _, value in pieces)
    meaning = Roles(text)
    starts = []
    offset = 0
    for kind, value in pieces:
        require(
            kind in {"text", "label", "xt", "cited"},
            f"Unsupported source note role: {key}: {kind}",
        )
        starts.append(offset)
        meaning.mark(
            offset,
            offset + len(value),
            {"xt": "citation", "label": "label"}.get(kind, "text"),
        )
        if kind == "cited":
            meaning.reading(offset, offset + len(value), "quotation")
        offset += len(value)
    alternative = None
    for i, (kind, value) in enumerate(pieces[:-1]):
        if kind != "label" or value.strip() not in RENDERING_LABELS:
            continue
        if pieces[i + 1][0] != "text":
            continue
        # A label inside a sentence ("The Gr. word ...") introduces no rendering,
        # but one after a comma does ("rightness, or straightness"), as does "or"
        # after a rendering ("do good or make good"), and a label joined to
        # another ("Heb. and Alex. Samuel").
        sentence = re.split(r"[.;](?:\s|$)", text[: starts[i]])[-1]
        before = text[: starts[i]].rstrip(TRIM)
        continues = (
            value.strip() in ("or", "or,")
            and before != ""
            and meaning.kind_at(len(before) - 1) in {"alternative", "quotation"}
        )
        if (
            re.search(r"\w\s*$", sentence)
            and not continues
            and not (
                i > 1
                and pieces[i - 2][0] == "label"
                and pieces[i - 1][1].strip() in lemmas.CONJUNCTIONS
            )
        ):
            continue
        # A word Brenton set in italic inside the rendering ("a head of hair
        # even hair") does not end it, but a comma from that word on does
        # ("made ellulim, a Hebrew word").
        ends = [start for (kind, _), start in zip(pieces, starts) if kind != "text"]
        stop = next((end for end in ends if end > starts[i + 1]), len(text))
        if stop < len(text) and pieces[i + 2][0] == "cited":
            resume = next((end for end in ends if end > stop), len(text))
            comma = text.find(",", stop, resume)
            stop = resume if comma < 0 else comma
        after = text[starts[i + 1] : stop]
        extent = RENDERING_END.split(after, maxsplit=1)[0]
        start = starts[i + 1]
        # Greek before its English renders by the English ("Alex. ἐντολαί,
        # commands"), and words quoted as added are the reading ("insert
        # 'priest'").
        if gloss := GREEK_GLOSS.match(extent) or ADDED.match(extent):
            start += gloss.end()
            extent = extent[gloss.end() :]
        # A rendering in quotation marks ends with them ("'turned away,' but").
        if closing := re.match(
            r"\s*['‘“].*?[^\W\d_][,.;:?!]?(['’”])(?![^\W\d_])", extent
        ):
            extent = extent[: closing.start(1)]
        # Quoted Greek or Hebrew ends a rendering after a comma ("furnace,
        # κάμινον"). Inside a sentence it makes the sentence a comment ("the
        # word עדנה"), unless an earlier comma ends the rendering ("the hams,
        # from γόνν").
        if quoted := QUOTED.search(extent):
            extent = extent[: quoted.start()]
            if not re.search(r",\s*$", extent):
                extent = extent[: extent.rfind(",")] if "," in extent else ""
        # Words that run into another label and end on one like "the" or "as"
        # introduce it ("Gr. from the Heb.", "O Lord, as in Heb."): they comment.
        tail = word_spans(extent)
        if (
            tail
            and tail[-1][0] in lemmas.LINKING_WORDS
            and stop < len(text)
            and pieces[i + 2][0] == "label"
            and pieces[i + 2][1].strip().rstrip(",").lower() != "or"
            and after.rstrip().endswith(extent.rstrip())
        ):
            extent = extent[: extent.rfind(",")] if "," in extent else ""
        # "Heb. and Alex. Samuel": the conjunction joins two labels.
        joins_labels = (
            extent.strip() in lemmas.CONJUNCTIONS
            and i + 2 < len(pieces)
            and pieces[i + 2][0] == "label"
        )
        if not extent.strip() or COMMENTARY.match(extent) or joins_labels:
            continue
        last = 0
        for separator in [*RENDERING_SEPARATOR.finditer(extent), None]:
            end = separator.start() if separator else len(extent)
            bounds = meaning.reading(start + last, start + end)
            # "Alex. + the Lord" adds to the text rather than rendering it.
            if (
                alternative is None
                and text[slice(*bounds)]
                and not extent.lstrip().startswith("+")
            ):
                alternative = bounds
            last = separator.end() if separator else len(extent)
    # Two renderings or quotations a space apart are one ("innocent things").
    for match in re.finditer(r"(?<=\S) +(?=\S)", text):
        if all(
            meaning.kind_at(at) in {"alternative", "quotation"}
            for at in (match.start() - 1, match.end())
        ):
            meaning.mark(match.start(), match.end(), "alternative")
    return meaning.body(alternative, "rendering" if alternative else "roman", trim=True)


def declared_readings(body, override, key):
    """A note with the renderings an exception declares, between underscores,
    in place of those the rules found."""
    words = override.replace("_", "")
    require(words == body.plain, f"Note override does not match the note: {key}")
    require(override.count("_") % 2 == 0, f"Unclosed italic in note override: {key}")
    roles = Roles(body.plain, body.roles)
    for first, last, role in tuple(roles.intervals):
        if role != "citation":
            roles.mark(first, last, "text")
    at, opened = 0, None
    for part in re.split("(_)", override):
        if part != "_":
            at += len(part)
        elif opened is None:
            opened = at
        else:
            for first, last, role in tuple(roles.intervals):
                if role != "citation" and first < at and opened < last:
                    roles.mark(max(first, opened), min(last, at), "alternative")
            opened = None
    # The lemma is measured by the first rendering the override declares.
    reading = None
    for first, last, role in roles.intervals:
        if role == "alternative":
            value = body.plain[first:last]
            if value.strip(TRIM):
                reading = (
                    first + len(value) - len(value.lstrip(TRIM)),
                    last - len(value) + len(value.rstrip(TRIM)),
                )
                break
    return roles.body(reading, "override")


def reading_of(note, override, key):
    """The rendering by which a source note measures the words it is about."""
    body = interpreted(source_pieces(note), key)
    if override is not None:
        body = declared_readings(body, override, key)
    return body.alternative


def visual(body):
    """A body's roles as they print: readings, citations and the rest."""
    result = []
    for start, end, role in body.roles:
        kind = (
            "reading"
            if role in {"alternative", "quotation"}
            else "citation" if role == "citation" else "text"
        )
        if result and result[-1][0] == kind:
            result[-1] = (kind, result[-1][1] + body.plain[start:end])
        else:
            result.append((kind, body.plain[start:end]))
    return result


def source_body(pieces, found, override, key, source):
    """A source note's body: its roles read, an exception's renderings in
    place of the rules', and its citations bound to their words."""
    text = "".join(value for _, value in pieces)
    leading = len(text) - len(text.lstrip())
    body = interpreted(citations.source_pieces(pieces, found), key)
    require(body.plain and body.plain != ".", f"Empty note: {key}")
    require("_" not in body.plain, f"Underscore in note: {key}")
    if override is not None:
        changed = declared_readings(body, override, key)
        require(
            visual(changed) != visual(body), f"Note override changes nothing: {key}"
        )
        body = changed
    require(
        plain(body.plain) == usfm.plain_text(source),
        f"Note restyling changed its text: {key}",
    )
    return bound(body, found, key, leading)


def bound(body, found, key, leading=0):
    """A body with its citations bound to the words that write them."""
    spans, previous = [], 0
    for citation in found:
        first, last = citation.start - leading, citation.end - leading
        require(
            previous <= first < last <= len(body.plain)
            and body.plain[first:last] == citation.source,
            f"Citation source changed during interpretation: {key}",
        )
        previous = last
        spans.append((first, last, citation))
    return replace(body, citations=tuple(spans))


def authored_body(note, override, key):
    """The body of a note the edition writes, whose markers say what each
    part is: \\fl a label, \\fqa an alternative rendering, \\fq quoted words,
    \\xt a citation, \\ft the rest. A rendering or quotation carries no space
    at either end; the space is the text's beside it."""
    runs = []
    for item in note["content"]:
        if isinstance(item, str) or item.get("marker") in ("fr", "xo"):
            require(
                not isinstance(item, str), f"Unmarked words in an edition note: {key}"
            )
            continue
        require(
            item["marker"] in AUTHORED
            and all(isinstance(c, str) for c in item["content"]),
            f"Unknown part of an edition note: {key}",
        )
        runs.append([AUTHORED[item["marker"]], "".join(item["content"])])
    for index, (role, value) in enumerate(runs):
        if role in ("alternative", "quotation"):
            kept = value.rstrip(" ")
            if kept != value and index + 1 < len(runs):
                runs[index + 1][1] = value[len(kept) :] + runs[index + 1][1]
            runs[index][1] = kept
    text = "".join(value for _, value in runs)
    roles = Roles(text)
    offset, reading = 0, None
    for role, value in runs:
        roles.mark(offset, offset + len(value), role)
        if role == "alternative" and reading is None and value.strip(TRIM):
            reading = (
                offset + len(value) - len(value.lstrip(TRIM)),
                offset + len(value.rstrip(TRIM)),
            )
        offset += len(value)
    body = roles.body(reading, "rendering" if reading else "roman")
    if override is not None:
        body = declared_readings(body, override, key)
    return body


def with_terms(body, terms):
    return replace(body, terms=terminology.recognize(body.plain, terms))


def edited(body, before, after, key):
    """A body with a declared change to its words, its roles, reading,
    citations and terms carried through the change."""
    text = body.plain
    require(text.count(before) == 1, f"Prose edit does not apply once: {key}: {before}")
    prefix, removed, added = change(before, after)
    start = text.index(before) + prefix
    end = start + len(removed)
    leaves = body.leaves
    # What is added belongs to the first stretch the change touches, or to
    # the one that ends where words are only added.
    touched = [
        n
        for n, (a, b, _, _) in enumerate(leaves)
        if a < end and start < b or start == end and a < start <= b
    ]
    owner = touched[0] if touched else 0
    require(touched or start == 0, f"Prose edit has no words to change: {key}")
    roles, bound_citations, at = [], [], 0
    for n, (a, b, role, citation) in enumerate(leaves):
        gone = max(min(b, end) - max(a, start), 0)
        length = (b - a) - gone + (len(added) if n == owner else 0)
        if not length:
            continue
        if citation is not None:
            bound_citations.append((at, at + length, citation))
        if roles and roles[-1][2] == role:
            roles[-1] = (roles[-1][0], at + length, role)
        else:
            roles.append((at, at + length, role))
        at += length

    def moved(at, closing=False):
        if at < start or at == start and not closing:
            return at
        if at >= end:
            return at + len(added) - (end - start)
        return start + (len(added) if closing else 0)

    return replace(
        body,
        plain=text[:start] + added + text[end:],
        roles=tuple(roles),
        reading=(
            None
            if body.reading is None
            else (moved(body.reading[0]), moved(body.reading[1], True))
        ),
        citations=tuple(bound_citations),
        terms=tuple(
            replace(t, start=moved(t.start), end=moved(t.end, True)) for t in body.terms
        ),
    )


# How a note prints.


def text_of(runs):
    return "".join(value for _, value in runs)


def merged_runs(runs):
    result = []
    for role, value in runs:
        if not value:
            continue
        if result and result[-1][0] == role:
            result[-1] = (role, result[-1][1] + value)
        else:
            result.append((role, value))
    return result


def displayed(body, before="", after="", *, books=None):
    """A body as runs of commentary, readings and citations: each rendering
    widened as its lemma was, each citation as the edition prints it. Returns
    the runs, the terms where they now stand, and the runs before widening."""
    runs, original = [], []
    for start, end, role, citation in body.leaves:
        value = body.plain[start:end]
        if citation is not None:
            value = citations.printed(citation, books)
            if citation.items:
                role = "citation"
            elif role not in {"alternative", "quotation"}:
                role = "text"
        shown = value
        # Only an alternative rendering stands in for the whole lemma; words
        # the note merely quotes are left as they are.
        if role == "alternative" and body.rule != "roman" and (before or after):
            shown = before + value + after
        kind = (
            "reading"
            if role in {"alternative", "quotation"}
            else "citation" if role == "citation" else "commentary"
        )
        original.append((kind, value))
        runs.append((kind, shown))
    runs, original = merged_runs(runs), merged_runs(original)
    terms = body.terms
    text = text_of(runs)
    if text != body.plain:
        blocks = SequenceMatcher(
            None, body.plain, text, autojunk=False
        ).get_matching_blocks()
        terms = tuple(
            replace(t, start=block.b + t.start - block.a, end=block.b + t.end - block.a)
            for t in terms
            for block in blocks
            if block.a <= t.start < t.end <= block.a + block.size
        )
    return runs, terms, original


def is_sentence(runs):
    """Whether the note is a sentence of its own: it opens with neither a label,
    a rendering nor a reference, and has a finite verb outside its renderings."""
    roman = "".join(
        value if role == "commentary" else " " * len(value) for role, value in runs
    )
    return (
        runs[0][0] == "commentary"
        and not LABEL_START.match(text_of(runs))
        and FINITE_VERB.search(roman) is not None
    )


def sliced(runs, start=0, end=None):
    end = len(text_of(runs)) if end is None else end
    result, offset = [], 0
    for role, value in runs:
        first, last = max(start - offset, 0), min(end - offset, len(value))
        if first < last:
            result.append((role, value[first:last]))
        offset += len(value)
    return result


def finished(runs, terms, lemma, sentence, registry, key):
    """The note as it prints: its terms in the edition's forms; a sentence
    with its capital and a closing full stop; any other note without one, and
    after a lemma, running on from the colon ("elder: or, greater") unless it
    opens with a name, a reference, capitals or a quotation mark."""
    found = is_sentence(runs)
    require(
        sentence is None or sentence != found,
        f"Note sentence override changes nothing: {key}",
    )
    complete = found if sentence is None else sentence
    text = text_of(runs)
    # The closing full stop, before any closing quotation mark, unless it is
    # the last of an ellipsis; it stays if it ends an abbreviation ("so the Heb.").
    stop = re.search(r"(?<!\.)\.(?=['’”\"]?$)", text)
    terminal = stop.start() if stop else None
    lexical = bool(stop and ABBREVIATION.search(text[: stop.end()]))
    initial = None
    if complete and re.match("[a-z]", text):
        initial = str.upper
    elif (
        not complete
        and lemma is not None
        and runs[0][0] != "citation"
        and not NAMES.match(text)
        and re.match(r"[A-Z](?![A-Z])", text)
    ):
        initial = str.lower
    bounds, offset = [], 0
    for role, value in runs:
        bounds.append((offset, offset + len(value), role))
        offset += len(value)
    edits = []
    for term in terms:
        # A capital in a separate reading or citation is no evidence that a
        # sentence ends at the term.
        capital = re.search(r"\s+([A-Z])", text[term.end :])
        if term.closure and capital and capital.start() == 0:
            at = term.end + capital.start(1)
            if not any(a <= term.start < at < b for a, b, _ in bounds):
                term = replace(term, closure=False)
        if terminal == term.end - 1 and not complete and not lexical:
            term = replace(term, closure=False)
        edits.append((term.start, term.end, terminology.render(term, registry, text)))
    if terminal is not None and not complete and not lexical:
        # A term's own period is the term's; any other closing stop goes.
        own = any(
            t.start <= terminal < t.end
            and t.end == terminal + 1
            and registry.display(t.identity).endswith(".")
            for t in terms
        )
        covered = any(a <= terminal < b for a, b, _ in edits)
        if not own and not covered:
            edits.append((terminal, terminal + 1, ""))
    for start, end, value in sorted(edits, reverse=True):
        role = next(role for a, b, role in bounds if a <= start < b)
        runs = [*sliced(runs, 0, start), (role, value), *sliced(runs, end)]
    runs = merged_runs(runs)
    if complete and not re.search(r"[.?!]['’”\"]?$", text_of(runs)):
        runs = merged_runs([*runs, ("commentary", ".")])
    if initial:
        role, value = runs[0]
        runs[0] = (role, initial(value[0]) + value[1:])
    return runs


def underscored(runs):
    """The note with its italic between underscores, as the exception files write it."""
    result, reading = [], False
    for role, value in runs:
        if (role == "reading") != reading:
            result.append("_")
            reading = not reading
        result.append(value)
    return "".join(result) + ("_" if reading else "")


def footnote(reference, lemma, runs, **extra):
    """A printed note: its verse, the words it is about, and its text. A
    marker takes the space after it, so a run's leading space is written at
    the end of the run before."""
    parts = []
    for role, value in runs:
        marker = PRINTED[role]
        spaces = len(value) - len(value.lstrip())
        if parts and spaces:
            parts[-1][1] += value[:spaces]
            value = value[spaces:]
        if value:
            if parts and parts[-1][0] == marker:
                parts[-1][1] += value
            else:
                parts.append([marker, value])
    content = [usj.char("fr", f"{reference} ")]
    if lemma is not None:
        content.append(usj.char("fq", f"{lemma}: "))
    content += [usj.char(marker, value) for marker, value in parts]
    return usj.note("f", *content, **extra)
