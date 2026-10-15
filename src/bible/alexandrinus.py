"""Declared Alexandrine readings, checked against Brenton and audited to Swete
(edition/alexandrinus.json).

The decision file owns every departure from Brenton’s translation: a
reading printed in place of Brenton’s words, a passage supplied from
Brenton's Appendix, a note kept as it is. Each decision pins the note or
Appendix paragraph it rests on, derives its English from those words by
declared edits, and records Swete's evidence and its reason.

This stage reads Brenton's books as their source numbers them, before any
chapter is selected or relabelled and before any note is set as a footnote.
The notes it writes say which words they are about; a note of Brenton's whose
words a reading changes keeps the words it was about.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

import bible.policy
from bible import (
    annotate,
    lemmas,
    notes,
    references,
    scripture,
    terminology,
    usfm,
    usj,
)
from bible.checks import present, require, require_fields
from bible.policy_schema import AlexandrinusReadingsNoteEdits, Decision
from bible.scripture import plain, word_spans, words_of
from bible.usj import Content, Document, Node

ALEX = re.compile(r"\b(?:Alex\.?|Alexandr\w*|App(?:endix)?\.?)(?!\w)")
# Brenton's appendix, and the heading of the passages it supplies.
APPENDIX = "BAK"
SUPPLIED = "The Following Passages are Supplied From the Alexandrine Text"
# Where a decision's note stands in the words it prints.
CALLER = "\ue000"
NUMBER = dict(
    zip(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety".split(),
        [*range(20), 20, 30, 40, 50, 60, 70, 80, 90],
    )
)
ORDINAL = dict(
    zip(
        "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth thirtieth fortieth fiftieth sixtieth seventieth eightieth ninetieth".split(),
        [*range(1, 20), 20, 30, 40, 50, 60, 70, 80, 90],
    )
)
SCALE = {"hundred": 100, "thousand": 1000, "million": 1000000}
SWETE = {"volume", "page", "evidence", "reading", "agrees"}
COMMON = {"why", "swete", "supplied"}
REPLACEMENT = {"from", "note", "label", "lemma", "target", "english", "note_at"}
# A verse omitted whole, noted on the verse before it.
OMISSION = {"omit_verse", "note_target"}
MOVE = {"verses", "before"}
FIELDS = {
    "readings": COMMON
    | REPLACEMENT
    | {"edits", "note_edits", "source_note", "omit_verse", "note_target"},
    "passages": COMMON
    | {"appendix", "kjv", "edits", "insertions", "moves", "source_notes"},
    "kept": COMMON | {"appendix", "todo", "source_note", "note", "lemma", "moved_to"},
}


def tokens(text: str) -> list[str]:
    """Words and number values, including Brenton's reversed tens and ordinals."""
    words = re.findall(
        rf"\d[\d,]*(?:st|nd|rd|th)?|{scripture.WORD.pattern}",
        usfm.plain_text(text).casefold(),
    )
    result = []
    i = 0
    while i < len(words):
        word = words[i]
        if word[0].isdigit():
            result.append(re.sub(",", "", word))
            i += 1
            continue
        first = i
        if word in ("a", "an") and i + 1 < len(words) and words[i + 1] in SCALE:
            i += 1
        elif word not in NUMBER and word not in ORDINAL and word not in SCALE:
            result.append(word.replace("'", "").replace("’", ""))
            i += 1
            continue
        total = part = 0
        ordinal = False
        while i < len(words):
            w = words[i]
            if w in NUMBER or w in ORDINAL:
                part += NUMBER.get(w, ORDINAL.get(w, 0))
                ordinal |= w in ORDINAL
            elif w == "hundred":
                part = (part or 1) * 100
            elif w in ("thousand", "million"):
                total += (part or 1) * SCALE[w]
                part = 0
            elif (
                w == "and"
                and i + 1 < len(words)
                and words[i + 1] in NUMBER | ORDINAL | SCALE
            ):
                pass
            else:
                break
            i += 1
        require(i > first, "Number reader did not advance")
        result.append(str(total + part) + ("th" if ordinal else ""))
    # Numeric ordinal suffixes compare by value, regardless of English spelling.
    return [re.sub(r"(?<=\d)(st|nd|rd)$", "th", w) for w in result]


def check_swete(
    key: str, entry: Decision, policy: bible.policy.Policy, kept: bool = False
) -> None:
    swete = entry.get("swete")
    require(
        swete is not None
        and hasattr(swete, "keys")
        and set(swete) == SWETE
        and type(swete["volume"]) is int
        and str(swete["volume"]) in policy.alexandrinus["swete"]
        and type(swete["page"]) is int
        and swete["page"] > 0
        and swete["evidence"] in {"apparatus", "text", "silence"}
        and isinstance(swete["reading"], str)
        and bool(swete["reading"].strip())
        and (swete["agrees"] is None or type(swete["agrees"]) is bool),
        f"Malformed Swete record: {key}",
    )
    assert swete is not None
    require(
        kept or swete["agrees"] is True,
        f"Swete does not agree with promoted reading: {key}",
    )
    require(
        isinstance(entry.get("why"), str) and entry["why"].strip(),
        f"Alexandrine decision without a why: {key}",
    )


def derived(
    key: str, operation: Decision, source: str, supplied: Sequence[str] = ()
) -> str:
    """The English a decision prints, derived exactly from a source phrase by
    its declared edits: order, punctuation, spelling and supplied-word markup
    cannot change without one. Its vocabulary must be Brenton's besides."""
    proof = operation.get("english")
    require(
        proof is not None
        and hasattr(proof, "keys")
        and {"source"} <= set(proof) <= {"source", "span", "edits"}
        and proof["source"] in {"brenton", "from"},
        f"Missing or malformed exact English derivation: {key}",
    )
    assert proof is not None
    original = source if proof["source"] == "brenton" else operation.get("from")
    require(isinstance(original, str), f"Invalid English source: {key}")
    assert isinstance(original, str)
    start, stop = proof.get("span", (0, len(original)))
    require(
        0 <= start <= stop <= len(original) and start < stop,
        f"Invalid English source span: {key}",
    )
    base = original[start:stop]
    parts, end = [], 0
    for edit in proof.get("edits", ()):
        require_fields(edit, {"span", "to"}, {"why"}, f"English edit of {key}")
        a, b = edit["span"]
        require(
            end <= a <= b <= len(base) and base[a:b] != edit["to"],
            f"Malformed English editorial edit: {key}",
        )
        parts += [base[end:a], edit["to"]]
        end = b
    english = "".join(parts) + base[end:]
    before = operation.get("from", "")
    allowed = set(tokens(before) + tokens(source) + tokens(" ".join(supplied)))
    added = set(tokens(english)) - allowed
    require(not added, f"English not supplied by Brenton: {key}: {sorted(added)}")
    require(
        set(usfm.inventory(before + english)["markers"]) <= {"add", "add*"},
        f"Unsupported USFM marker in Alexandrine replacement: {key}",
    )
    return english


def note_content(
    entry: Decision, key: str, terms: terminology.Registry
) -> Content | None:
    """The note a decision leaves on the words it displaces: the one it
    declares, or the displaced words quoted under the witness its label
    names, Brenton unless a manuscript is shown to read them; None if it
    declares none."""
    if "note" in entry:
        require("label" not in entry, f"Alexandrine label beside a note: {key}")
        if entry["note"] is None:
            return None
        return usj.parse(entry["note"], fragment=True)
    require(
        entry.get("label") != "brenton", f"Alexandrine label changes nothing: {key}"
    )
    words = plain(usj.text_of(usj.parse(entry["from"], fragment=True)))
    return [
        usj.char("fl", f"{terms.display(entry.get('label', 'brenton'))} "),
        usj.char("fq", words.strip().rstrip(".")),
        usj.char("ft", "."),
    ]


def edition_note(
    key: str, reference: str, content: Content, scope: usj.Scope | None = None
) -> Node:
    extra: usj.Extra = {"x-key": key, "category": "edition"}
    if scope is not None:
        extra["x-scope"] = scope
    return usj.note("f", usj.char("fr", f"{reference} "), *content, caller="+", **extra)


def operations(
    policy: bible.policy.Policy, code: str
) -> Iterator[tuple[str, Decision, str, str, str]]:
    """Each replacement a book's decisions declare, as (decision, operation,
    source words, verse, the key of its note)."""
    data = policy.alexandrinus
    for key, entry in data["readings"].items():
        if key.split()[0] != code:
            continue
        verse = entry.get("target", key).split()[1].split("#")[0]
        yield key, entry, entry["source_note"], verse, key
        for index, item in enumerate(entry.get("edits", ()), 1):
            verse = item["target"].split()[-1]
            yield key, further(entry, item), entry[
                "source_note"
            ], verse, f"{key}@{index}"
    for key, entry in data["passages"].items():
        if key.split()[0] != code:
            continue
        # A King James passage's Appendix paragraph only points to it: the
        # words its edits print are the King James words and those supplied.
        source = "" if "kjv" in entry else entry["appendix"]
        for index, item in enumerate(entry.get("edits", ()), 1):
            verse = item["target"].split()[-1]
            yield key, further(entry, item), source, verse, f"{key}@{index}"


def further(entry: Decision, item: Decision) -> Decision:
    """A decision's further replacement: its own words, derivation and note
    position, and the decision's reason, note and lemma unless it has its
    own. A verse is omitted by the decision itself, or by a passage's
    further replacement, each naming the verse its note stands on."""
    inherited = cast(
        Decision,
        {
            key: value
            for key, value in entry.items()
            if key not in {"english", "note_at", "omit_verse", "note_target"}
        },
    )
    return {**inherited, **item}


def consumed_notes(policy: bible.policy.Policy, code: str) -> set[str]:
    """The keys of the notes a book's decisions replace or take up."""
    data = policy.alexandrinus
    keys = {key for key in data["readings"] if key.split()[0] == code}
    for key, entry in data["passages"].items():
        if key.split()[0] == code:
            keys.update(entry.get("source_notes", ()))
    return keys


def companions(
    policy: bible.policy.Policy, code: str
) -> dict[str, AlexandrinusReadingsNoteEdits]:
    """The notes a book's decisions rewrite without replacing the words they
    stand in: a reading's companion notes, and kept notes given new words."""
    data = policy.alexandrinus
    found: dict[str, AlexandrinusReadingsNoteEdits] = {}
    for owner, entry in data["readings"].items():
        if owner.split()[0] != code:
            continue
        for key, edit in entry.get("note_edits", {}).items():
            require_fields(
                edit, {"from", "to", "why"}, {"lemma"}, f"Companion note edit {owner}"
            )
            require(
                key not in found, f"Conflicting companion note edit: {owner}: {key}"
            )
            found[key] = edit
    for key, entry in data["kept"].items():
        if key.split()[0] == code and "note" in entry:
            require(
                entry["note"] != entry.get("source_note") or "lemma" in entry,
                f"Kept Alexandrine note changes nothing: {key}",
            )
            words: AlexandrinusReadingsNoteEdits = {
                "from": entry["source_note"],
                "to": present(
                    entry["note"], f"Kept Alexandrine note without its words: {key}"
                ),
                "why": entry["why"],
            }
            if "lemma" in entry:
                words = {**words, "lemma": entry["lemma"]}
            found[key] = words
    return found


def check(
    policy: bible.policy.Policy, books: Mapping[str, Document]
) -> tuple[int, int]:
    """Every decision well formed, and the decisions exhaustive: each of
    Brenton's Alexandrine notes and each paragraph of the Appendix's supplied
    passages has exactly one."""
    data = policy.alexandrinus
    require_fields(
        data,
        {"swete", "readings", "passages", "kept"},
        (),
        "Alexandrine file",
    )
    sections = [set(data["readings"]), set(data["passages"]), set(data["kept"])]
    require(
        sum(map(len, sections)) == len(set.union(*sections)),
        "Alexandrine decision appears in several sections",
    )
    sections_to_check: tuple[Literal["readings", "passages", "kept"], ...] = (
        "readings",
        "passages",
        "kept",
    )
    for section in sections_to_check:
        for key, entry in data[section].items():
            require(
                set(entry) <= FIELDS[section],
                f"Unknown Alexandrine decision fields: {key}",
            )
            check_swete(key, entry, policy, section == "kept")
            code = key.removeprefix(f"{APPENDIX} ").split()[0]
            require(
                code in books and code != APPENDIX, f"Alexandrine book missing: {key}"
            )
            if section == "kept":
                require(
                    ("appendix" in entry) == key.startswith(f"{APPENDIX} ")
                    and ("appendix" in entry) != ("source_note" in entry)
                    and not entry.get("supplied"),
                    f"Invalid retained Alexandrine decision: {key}",
                )
                # A lemma places the words a kept note is given, and nothing
                # else: without them it would be accepted and never read.
                require(
                    "lemma" not in entry
                    or ("note" in entry and isinstance(entry["lemma"], str | None)),
                    f"Kept Alexandrine lemma without the note it places: {key}",
                )
            elif section == "passages":
                require(
                    ("appendix" in entry or "kjv" in entry)
                    and bool(
                        entry.get("edits")
                        or entry.get("insertions")
                        or entry.get("moves")
                    ),
                    f"Alexandrine passage needs an English source and an operation: {key}",
                )
                require(
                    entry.get("kjv", True) is True,
                    f"Invalid KJV passage: {key}",
                )
                for move in entry.get("moves", ()):
                    require_fields(move, MOVE, {"label"}, f"Move of {key}")
                    if "label" in move:
                        require(
                            move["label"] != "brenton",
                            f"Alexandrine label changes nothing: {key}",
                        )
                        terminology.registry(policy).display(move["label"])
            allowed = REPLACEMENT | COMMON
            if section == "passages":
                allowed |= OMISSION
            for item in entry.get("edits", ()):
                require(
                    set(item) <= allowed and "target" in item,
                    f"Invalid Alexandrine edit: {key}",
                )
                check_swete(key, {**entry, **item}, policy)
            edits = entry.get("edits", ())
            for item in (entry, *edits):
                # A verse omitted whole is noted on a verse named for it: by
                # its own note, or by the note of the decision's edit of that
                # verse, which then quotes it.
                require(
                    bool(item.get("omit_verse")) == ("note_target" in item),
                    f"Omission without the verse its note stands on: {key}",
                )
                if not item.get("omit_verse") or (
                    {**entry, **item}.get("note") is not None
                ):
                    continue
                # The quotation is the omitted verse's words, so that it
                # cannot drift from them.
                words = plain(usj.text_of(usj.parse(item["from"], fragment=True)))
                quoting = [
                    note
                    for other in edits
                    if other["target"] == item["note_target"]
                    and (note := other.get("note")) is not None
                ]
                require(
                    any(
                        words.strip().rstrip(".")
                        in plain(usj.text_of(usj.parse(note, fragment=True)))
                        for note in quoting
                    ),
                    f"Omission without its note: {key}",
                )
            if section == "passages" and "kjv" in entry:
                # The King James words are conformed to Alexandrinus in the
                # verses the passage supplies, and nowhere else; the words
                # they displace are not the Vatican's, so each edit says
                # whose they are.
                supplied = {str(v) for v in references.parse_passage(key).verses}
                require(
                    all(item["target"] in supplied for item in entry.get("edits", ())),
                    f"KJV passage edits a verse it does not supply: {key}",
                )
                require(
                    all("note" in item for item in entry.get("edits", ())),
                    f"KJV passage edit without its own note: {key}",
                )
    consumed = [
        k for entry in data["passages"].values() for k in entry.get("source_notes", ())
    ]
    require(
        len(consumed) == len(set(consumed)),
        "Alexandrine note consumed by several passages",
    )
    declared = (
        set(data["readings"])
        | {k for k, v in data["kept"].items() if "appendix" not in v}
        | set(consumed)
    )
    require(
        not set(consumed) & (set(data["readings"]) | set(data["kept"])),
        "Alexandrine passage note also has a decision",
    )
    found = {
        note["x-key"]
        for code, doc in books.items()
        if code != APPENDIX
        for note in usj.notes_of(doc["content"])
        if "x-key" in note and ALEX.search(notes.source_text(note))
    }
    require(
        found == declared,
        f"Alexandrine notes not exhaustive; missing: {sorted(found - declared)}; unused: {sorted(declared - found)}",
    )
    # An Appendix paragraph that supplies nothing moves into the note on its
    # verse: that note is then given its words, in the same book. The list it
    # stands in prints nowhere, so a paragraph kept but not moved is lost.
    for key, entry in data["kept"].items():
        if "appendix" in entry:
            require("moved_to" in entry, f"Appendix paragraph moved nowhere: {key}")
        if "moved_to" in entry:
            target = data["kept"].get(entry["moved_to"], {})
            require(
                "appendix" in entry
                and entry["moved_to"].split()[0] == key.split()[1]
                and "note" in target,
                f"Appendix paragraph moved to a note not given its words: {key}",
            )
    spans = [
        usj.parse(entry["appendix"])["content"][0]
        for section in ("passages", "kept")
        for entry in data[section].values()
        if "appendix" in entry
    ]
    paragraphs = supplied_paragraphs(books[APPENDIX])
    require(
        Counter(usj.serialize(p["content"]) for p in spans)
        == Counter(usj.serialize(p["content"]) for p in paragraphs),
        "Alexandrine appendix passages not exhaustive",
    )
    return len(found), len(paragraphs)


def supplied_heading(doc: Document) -> int:
    found = [
        index
        for index, block in enumerate(doc["content"])
        if usj.is_type(block, "para", "is1")
        and usj.text_of(block["content"]).strip() == SUPPLIED
    ]
    require(len(found) == 1, "Alexandrine appendix heading changed")
    return found[0]


def supplied_paragraphs(doc: Document) -> list[Node]:
    return [
        block
        for block in doc["content"][supplied_heading(doc) :]
        if usj.is_type(block, "para", "ip")
    ]


def appendix_notes(doc: Document) -> Document:
    """The Appendix's notes: what stands before the heading of the passages
    it supplies, which the books print."""
    return usj.with_blocks(doc, doc["content"][: supplied_heading(doc)])


def surviving_scope(
    note: Node, verse: scripture.Verse, offset: int, policy: bible.policy.Policy
) -> tuple[str | None, str | None]:
    """The words a note of Brenton's is about, measured against its verse
    before a reading changes it: its lemma and the narrower words it glosses."""
    key = note["x-key"]
    exception = policy.brenton_notes["notes"].get(key, {})
    words = word_spans(verse.text)
    body = notes.interpreted(notes.source_pieces(note), key)
    if exception.get("note") is not None:
        body = notes.declared_readings(
            body, exception["note"], key, quotation=exception.get("quotation", False)
        )
    span, glossed, _ = lemmas.inferred(
        note["marker"],
        verse.text,
        words,
        offset,
        body.alternative,
        exception,
        key,
        addition=body.addition,
    )
    return (
        lemmas.lemma_text(verse.text, words, span) if span else None,
        lemmas.lemma_text(verse.text, words, glossed) if glossed else None,
    )


def anchor(verse: scripture.Verse, phrase: str | None, key: str) -> int:
    """Where a phrase stands in a verse: the start of its one occurrence, as
    whole words, whatever the markup; a note on the whole verse stands at its
    start. An absent or repeated phrase needs a decision, never a guess."""
    if phrase is None:
        return 0
    words = word_spans(verse.text)
    hits = lemmas.occurrences(words, words_of(phrase))
    require(
        words_of(phrase) and len(hits) == 1,
        f"Note lemma not anchored once: {key} ({len(hits)})",
    )
    return words[hits[0]][1]


def check_pins(
    code: str,
    policy: bible.policy.Policy,
    placed: Mapping[str, tuple[scripture.Verse, int, Node]],
    consumed: set[str],
    rewritten: Mapping[str, AlexandrinusReadingsNoteEdits],
) -> None:
    """Each note a decision rests on must be the note as the source has it."""
    data = policy.alexandrinus
    for key in consumed:
        require(
            key in placed and ALEX.search(notes.source_text(placed[key][2])),
            f"Alexandrine keyed note missing: {key}",
        )
    for section in ("readings", "kept"):
        for key, entry in data[section].items():
            if key.split()[0] == code and "source_note" in entry:
                pinned(key, entry["source_note"], placed)
    for key, entry in data["passages"].items():
        if key.split()[0] == code:
            for identity, body in entry.get("source_notes", {}).items():
                pinned(identity, body, placed)
    for key, edit in rewritten.items():
        require(
            key in placed and key not in consumed,
            f"Companion note missing or already decided: {key}",
        )
        pinned(key, edit["from"], placed)


@dataclass(frozen=True)
class Replacement:
    """The words of a verse that a decision replaces, what it prints in their
    place, and the note it leaves: in which verse, and where in its words."""

    decision: str
    verse: str
    start: int
    end: int
    content: tuple[str | Node, ...]
    note: Node | None
    note_verse: str
    note_at: tuple[int, int]
    omits_verse: bool


def replacement(
    key: str,
    entry: Decision,
    source: str,
    verse: scripture.Verse,
    note_key: str,
    verses: Mapping[str, scripture.Verse],
    consumed: set[str],
    terms: terminology.Registry,
) -> Replacement:
    reference = verse.reference
    # The words as the verse has them, however a note among them parts
    # their spaces, and whatever space a style's close carried at the end.
    old = usj.text_of(usj.parse(entry["from"], fragment=True)).strip(" ")
    found = list(
        re.finditer(" +".join(map(re.escape, re.split(" +", old))), verse.text)
    )
    require(len(found) == 1, f"Alexandrine from not found once outside notes: {key}")
    start, old = found[0].start(), found[0][0]
    english = derived(key, entry, source, entry.get("supplied", ()))
    at = entry.get("note_at", 0)
    require(
        type(at) is int and 0 <= at <= len(english), f"Invalid note position: {key}"
    )
    # The note's caller stands in the words printed, at its declared place.
    new = usj.parse(english[:at] + CALLER + english[at:], fragment=True)
    before = usj.text_of(new).index(CALLER)
    new = usj.substituted(new, [(before, before + 1, "")])
    body = note_content(entry, key, terms)
    require(
        body is not None or entry.get("why"),
        f"Dropped Vatican text without a why: {key}",
    )
    home, note_at = reference, (start, before)
    omits = entry.get("omit_verse", False)
    if omits:
        require(
            not usj.text_of(new)
            and plain(verse.text) == plain(old)
            and entry.get("lemma", "") is None,
            f"Whole-verse omission leaves surviving text: {key}",
        )
        require(
            all(note["x-key"] in consumed for _, note in verse.notes),
            f"Whole-verse omission leaves a surviving note: {key}",
        )
        home = entry["note_target"].split()[-1]
        ordered = list(verses)
        require(
            ordered.index(reference) > 0
            and ordered[ordered.index(reference) - 1] == home
            and reference.split(":")[0] == home.split(":")[0],
            f"Omission note must attach to the preceding verse: {key}",
        )
        # At the end of the preceding verse's words.
        note_at = (len(verses[home].text), 0)
    note = None
    if body is not None:
        lemma = entry["lemma"] if "lemma" in entry else derived_lemma(english, at)
        note = edition_note(note_key, home, body, {"declared": lemma})
    return Replacement(
        key, reference, start, start + len(old), tuple(new), note, home, note_at, omits
    )


def shifted(position: int, changes: list[Replacement], strict: bool = False) -> int:
    """An offset in a verse's words, carried through the replacements made
    in the verse; strictly, through only those before it."""
    delta = 0
    for change in changes:
        if position < change.start or (strict and position == change.start):
            break
        length = len(usj.text_of(change.content))
        if position < change.end:
            return change.start + delta + min(position - change.start, length)
        delta += length - (change.end - change.start)
    return position + delta


def promoted(
    code: str, doc: Document, policy: bible.policy.Policy, kjv: Mapping[str, Document]
) -> Document:
    """A book of Brenton's with its Alexandrine decisions carried out: the
    verses its passages supply are set first, so that a King James verse may
    be conformed to Alexandrinus; then the words of verses are replaced and
    verses omitted; and the verses Alexandrinus orders otherwise are moved
    last, by whole paragraphs."""
    doc = with_insertions(code, doc, policy, kjv)
    verses = scripture.verses(doc)
    placed = {
        note["x-key"]: (verse, offset, note)
        for verse in verses.values()
        for offset, note in verse.notes
    }
    order = {key: n for n, key in enumerate(placed)}
    consumed = consumed_notes(policy, code)
    rewritten = companions(policy, code)
    check_pins(code, policy, placed, consumed, rewritten)
    terms = terminology.registry(policy)
    replacements = []
    for key, entry, source, reference, note_key in operations(policy, code):
        require(reference in verses, f"Alexandrine target verse missing: {key}")
        replacements.append(
            replacement(
                key, entry, source, verses[reference], note_key, verses, consumed, terms
            )
        )
    if not replacements and not rewritten:
        return with_moves(code, doc, policy, terms)
    omitted = {r.verse for r in replacements if r.omits_verse}
    # Every note of a verse the decisions touch is taken up, and set again
    # where it belongs once the words have changed.
    touched = (
        {r.verse for r in replacements}
        | {r.note_verse for r in replacements if r.note}
        | {placed[key][0].reference for key in rewritten}
    ) - omitted
    again: dict[str, list[tuple[int, int, Node, usj.Scope | None]]] = {}
    for reference in touched:
        verse = verses[reference]
        changes = sorted(
            (r for r in replacements if r.verse == reference), key=lambda r: r.start
        )
        for previous, current in zip(changes, changes[1:]):
            require(
                previous.end <= current.start,
                f"Overlapping Alexandrine replacements: {previous.decision}, {current.decision}",
            )
        kept: list[tuple[int, int, Node, usj.Scope | None]] = []
        for offset, note in verse.notes:
            key = note["x-key"]
            if key in consumed:
                continue
            companion = rewritten.get(key)
            scope: usj.Scope | None = None
            if companion is not None and "lemma" in companion:
                scope = {"declared": companion["lemma"]}
            elif any(r.start <= offset < r.end for r in changes):
                # A note within replaced words keeps the words it was about.
                require(
                    note.get("category") != "edition",
                    f"Alexandrine replacement covers an edition note: {key}",
                )
                lemma, glossed = surviving_scope(note, verse, offset, policy)
                scope = {"lemma": lemma, "glossed": glossed}
            if companion is not None:
                note = edition_note(
                    key, reference, usj.parse(companion["to"], fragment=True), scope
                )
            elif scope is not None:
                note = {**note, "x-scope": scope}
            kept.append((shifted(offset, changes), order[key], note, scope))
        # A reading's note takes the place, among the verse's notes, of the
        # note it replaces; any other new note follows them.
        fresh: list[tuple[int, int, Node, usj.Scope | None]] = [
            (
                shifted(r.note_at[0], changes, strict=True) + r.note_at[1],
                order.get(r.note["x-key"], len(order)),
                r.note,
                None,
            )
            for r in replacements
            if r.note and r.note_verse == reference
        ]
        again[reference] = kept + fresh
    removed = consumed | {
        note["x-key"] for reference in touched for _, note in verses[reference].notes
    }
    doc = scripture.map_notes(
        doc, lambda note: None if note.get("x-key") in removed else note
    )
    verses = scripture.verses(doc)
    doc = scripture.edited(
        doc, [(verses[r.verse], r.start, r.end, list(r.content)) for r in replacements]
    )
    doc = without_verses(doc, omitted)
    verses = scripture.verses(doc)
    note_changes: list[tuple[scripture.Verse, int, int, Content]] = []
    for reference, listed in again.items():
        verse = verses[reference]
        set_again = []
        for position, rank, note, scope in listed:
            if scope is not None:
                # At the words it is about, as the verse now has them. The
                # narrower gloss must survive as well, for the lemma to keep
                # its relation to it.
                phrase = scope["declared"] if "declared" in scope else scope["lemma"]
                position = anchor(verse, phrase, note["x-key"])
                if "glossed" in scope:
                    anchor(verse, scope["glossed"], note["x-key"])
            set_again.append((position, rank, note))
        for position, _, note in sorted(set_again, key=lambda e: e[:2]):
            note_changes.append((verse, position, position, [note]))
    return with_moves(code, scripture.edited(doc, note_changes), policy, terms)


def pinned(
    key: str, body: str, placed: Mapping[str, tuple[scripture.Verse, int, Node]]
) -> None:
    """A decision's source note must be the note as the corrected source has it."""
    require(
        key in placed and plain(notes.source_text(placed[key][2])) == plain(body),
        f"Alexandrine source note changed: {key}",
    )


def derived_lemma(english: str, at: int) -> str | None:
    """The words a displaced reading's note is about: those printed after its
    caller, without their closing punctuation."""
    words = plain(usj.text_of(usj.parse(english[at:], fragment=True)))
    return words.strip().strip(".,;:!?") or None


def without_verses(doc: Document, omitted: set[str]) -> Document:
    """The document without the numbers of the verses a decision omits whole,
    by their references."""
    if not omitted:
        return doc
    blocks, chapter = [], None
    for block in doc["content"]:
        if block["type"] == "chapter":
            chapter = block["number"]
        elif block["type"] == "para":
            block = {
                **block,
                "content": usj.joined(
                    [
                        item
                        for item in block["content"]
                        if not (
                            usj.is_type(item, "verse")
                            and f"{chapter}:{item['number']}" in omitted
                        )
                    ]
                ),
            }
        blocks.append(block)
    return usj.with_blocks(doc, blocks)


def with_insertions(
    code: str, doc: Document, policy: bible.policy.Policy, kjv: Mapping[str, Document]
) -> Document:
    """The document with the verses its passages supply, each from Brenton's
    Appendix by a declared derivation, or from the King James Bible, without
    its small capitals, to be conformed to Alexandrinus by the passage's
    edits. Verses set before a verse that opens a paragraph are a paragraph
    of their own."""
    for key, entry in policy.alexandrinus["passages"].items():
        if key.split()[0] != code:
            continue
        # The King James verses a passage supplies, before its edits.
        source = scripture.verses(kjv[code]) if "kjv" in entry else {}
        if "kjv" in entry:
            # The verses borrowed are those the decision is keyed by.
            supplied = [v.label for v in references.parse_passage(key).verses]
            require(
                [
                    verse["reference"]
                    for insertion in entry.get("insertions", ())
                    for verse in insertion.get("verses", ())
                ]
                == supplied,
                f"KJV passage must supply the verses it is keyed by: {key}",
            )
        for insertion in entry.get("insertions", ()):
            require_fields(
                insertion, {"verses"}, {"before", "after"}, f"Insertion of {key}"
            )
            require(
                ("before" in insertion) != ("after" in insertion)
                and insertion["verses"],
                f"Invalid Alexandrine insertion: {key}",
            )
            verses = scripture.verses(doc)
            reference = insertion.get("before", insertion.get("after"))
            require(reference in verses, f"Alexandrine insertion anchor missing: {key}")
            assert reference is not None
            parts = verses[reference].parts
            if "before" in insertion:
                block, at = parts[0][0], parts[0][1] - 1
            else:
                # After the verse's words, in the paragraph that holds them.
                block, at = parts[-1][0], parts[-1][2]
            items: Content = []
            for verse in insertion["verses"]:
                require_fields(
                    verse,
                    {"reference"},
                    {"note", "english"},
                    f"Inserted verse of {key}",
                )
                label = verse["reference"]
                require(
                    re.fullmatch(r"[1-9]\d*:[1-9]\d*[a-z]?", label) is not None
                    and label not in verses
                    and label.split(":")[0] == reference.split(":")[0],
                    f"Invalid Alexandrine inserted verse: {key}: {label}",
                )
                if "kjv" in entry:
                    require(
                        "english" not in verse,
                        f"KJV insertion changed its source verse: {key}",
                    )
                    require(label in source, f"KJV source verse missing: {key}")
                    # The King James small capitals go, wherever they stand,
                    # as Brenton's text around them has none.
                    words = usj.mapped(
                        [
                            item
                            for b, lo, hi, _ in source[label].parts
                            for item in kjv[code]["content"][b]["content"][lo:hi]
                        ],
                        lambda node: (
                            node["content"] if usj.is_type(node, "char", "sc") else node
                        ),
                    )
                else:
                    english = derived(
                        key, verse, entry["appendix"], entry.get("supplied", ())
                    )
                    words = usj.parse(english.strip(), fragment=True)
                items.append(
                    {"type": "verse", "marker": "v", "number": label.split(":")[1]}
                )
                if "note" in verse:
                    note = present(
                        verse["note"],
                        f"Alexandrine inserted verse without its note: {key}: {label}",
                    )
                    items.append(
                        edition_note(
                            f"{code} {label}",
                            label,
                            usj.parse(note, fragment=True),
                            {"declared": None},
                        )
                    )
                items += words
            blocks = list(doc["content"])
            content = blocks[block]["content"]
            if "before" in insertion and at == 0:
                # Before a verse that opens its paragraph, the verses are a
                # paragraph of their own, and the verse keeps its break; a
                # line of verse or a continued paragraph would not say which.
                require(
                    blocks[block]["marker"] == "p",
                    f"Alexandrine insertion before a {blocks[block]['marker']}: {key}",
                )
                blocks.insert(block, usj.para("p", *items))
            else:
                blocks[block] = {
                    **blocks[block],
                    "content": usj.joined(content[:at], items, content[at:]),
                }
            doc = usj.with_blocks(doc, blocks)
    return doc


def with_moves(
    code: str, doc: Document, policy: bible.policy.Policy, terms: terminology.Registry
) -> Document:
    """The document with the verses its passages move, each run set before
    the verse Alexandrinus has it before, under its own numbers, by whole
    paragraphs: the run opens a paragraph and closes one, and nothing else
    stands in the paragraphs between. A section heading (usj.HEADINGS) before
    the run or before the verse it goes before is refused, since neither
    place says which way it goes. The run, the verse it goes before and the
    verse it leaves behind must be Brenton's, neither inserted by a passage
    nor with inserted verses beside them, so that the notes name Brenton’s
    order. A note at its head says where the source has the verses,
    and one on the verse it leaves behind says where they are printed, as
    the Hebrew's relocated passages are noted, in words made from the
    move."""
    insertions = [
        insertion
        for key, entry in policy.alexandrinus["passages"].items()
        if key.split()[0] == code
        for insertion in entry.get("insertions", ())
    ]
    # The verses passages insert, and the verses they are set beside.
    inserted = {verse["reference"] for i in insertions for verse in i["verses"]}
    anchors = {i.get("before", i.get("after")) for i in insertions}
    for key, entry in policy.alexandrinus["passages"].items():
        if key.split()[0] != code:
            continue
        for move in entry.get("moves", ()):
            label = terms.display(move.get("label", "brenton"))
            verses = scripture.verses(doc)
            passage = references.parse_passage(f"{code} {move['verses']}")
            labels = [v.label for v in passage.verses]
            target = move["before"]
            require(
                all(label in verses for label in labels)
                and target in verses
                and target not in labels
                and target.split(":")[0] == labels[0].split(":")[0],
                f"Alexandrine move names verses the book lacks: {key}",
            )
            first, last = verses[labels[0]], verses[labels[-1]]
            lo, hi = first.parts[0][0], last.parts[-1][0]
            held = {block for label in labels for block, *_ in verses[label].parts}
            blocks = list(doc["content"])
            at = verses[target].parts[0][0]
            require(
                first.parts[0][1] == 1
                and last.parts[-1][2] == len(blocks[hi]["content"])
                and held == set(range(lo, hi + 1))
                and all(
                    block not in held
                    for label, verse in verses.items()
                    if label not in labels
                    for block, *_ in verse.parts
                )
                and verses[target].parts[0][1] == 1
                and at < lo
                and not any(
                    usj.is_type(blocks[i], "para")
                    and blocks[i]["marker"] in usj.HEADINGS
                    for i in (at - 1, lo - 1)
                    if i >= 0
                ),
                f"Alexandrine move is not of whole paragraphs to an earlier verse: {key}",
            )
            # The verse the run leaves behind: the one before it in order,
            # which must be Brenton's verse before it by number, so that
            # no omission or earlier move has shifted it.
            ordered = list(verses)
            behind = verses[ordered[ordered.index(labels[0]) - 1]]
            chapter, number = labels[0].split(":")
            require(
                number.isdigit() and behind.reference == f"{chapter}:{int(number) - 1}",
                f"Alexandrine move leaves no verse before it by number: {key}",
            )
            require(
                not {*labels, target, behind.reference} & (inserted | anchors),
                f"Alexandrine move beside an inserted verse: {key}",
            )
            which = "this verse" if len(labels) == 1 else "this passage"
            these = "the verse" if len(labels) == 1 else "the verses"
            after = behind.reference.partition(":")[2]
            run = annotate.spanned(passage.verses)
            notes_set: list[tuple[scripture.Verse, int, int, Content]] = [
                (
                    first,
                    0,
                    0,
                    [
                        annotate.relocation_note(
                            code,
                            first.reference,
                            label,
                            f"has {which} after verse {after}.",
                        )
                    ],
                ),
                (
                    behind,
                    len(behind.text),
                    len(behind.text),
                    [
                        annotate.relocation_note(
                            code,
                            behind.reference,
                            label,
                            f"has here {these} printed at {run}.",
                        )
                    ],
                ),
            ]
            blocks = list(scripture.edited(doc, notes_set)["content"])
            doc = usj.with_blocks(
                doc,
                blocks[:at] + blocks[lo : hi + 1] + blocks[at:lo] + blocks[hi + 1 :],
            )
    return doc
