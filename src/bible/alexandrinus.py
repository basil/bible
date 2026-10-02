"""Declared Alexandrine readings, checked against Brenton and audited to Swete
(edition/alexandrinus.json).

The decision file owns every departure from the Vatican translation: a
reading printed in place of the Vatican's words, a passage supplied from
Brenton's Appendix, a note kept as it is. Each decision pins the note or
Appendix paragraph it rests on, derives its English from those words by
declared edits, and records Swete's evidence and its reason.

This stage reads Brenton's books as their source numbers them, before any
chapter is selected or relabelled and before any note is set as a footnote.
The notes it writes say which words they are about; a note of Brenton's whose
words a reading changes keeps the words it was about.
"""

import re
from collections import Counter
from dataclasses import dataclass

from bible import lemmas, notes, scripture, usj
from bible.checks import require, require_fields
from bible.scripture import plain, word_spans, words_of

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
REPLACEMENT = {"from", "note", "witnesses", "lemma", "target", "english", "note_at"}
FIELDS = {
    "readings": COMMON
    | REPLACEMENT
    | {"edits", "note_edits", "source_note", "omit_verse", "note_target"},
    "passages": COMMON | {"appendix", "kjv", "edits", "insertions", "source_notes"},
    "kept": COMMON | {"appendix", "todo", "source_note", "note", "witnesses"},
}


def tokens(text):
    """Words and number values, including Brenton's reversed tens and ordinals."""
    words = re.findall(
        r"\d[\d,]*(?:st|nd|rd|th)?|[^\W\d_]+(?:[’'][^\W\d_]+)*",
        plain(re.sub(r"\\\+?[\w-]+(?:\*| ?)", "", text)).casefold(),
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


def check_swete(key, entry, policy, kept=False):
    swete = entry.get("swete")
    require(
        hasattr(swete, "keys")
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
    require(
        kept or swete["agrees"] is True,
        f"Swete does not agree with promoted reading: {key}",
    )
    require(
        isinstance(entry.get("why"), str) and entry["why"].strip(),
        f"Alexandrine decision without a why: {key}",
    )


def derived(key, operation, source, supplied=()):
    """The English a decision prints, derived exactly from a source phrase by
    its declared edits: order, punctuation, spelling and supplied-word markup
    cannot change without one. Its vocabulary must be Brenton's besides."""
    proof = operation.get("english")
    require(
        hasattr(proof, "keys")
        and {"source"} <= set(proof) <= {"source", "span", "edits"}
        and proof["source"] in {"brenton", "from"},
        f"Missing or malformed exact English derivation: {key}",
    )
    original = source if proof["source"] == "brenton" else operation.get("from")
    require(isinstance(original, str), f"Invalid English source: {key}")
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
        set(re.findall(r"\\(\+?[A-Za-z]\w*\*?)", before + english)) <= {"add", "add*"},
        f"Unsupported USFM marker in Alexandrine replacement: {key}",
    )
    return english


def note_content(entry, key):
    """The note a decision leaves on the words it displaces: the one it
    declares, or the Vatican's words quoted; None if it declares none."""
    if "note" in entry:
        if entry["note"] is None:
            return None
        return usj.parse(entry["note"], fragment=True)
    words = plain(usj.text_of(usj.parse(entry["from"], fragment=True)))
    return [
        usj.char("fl", "Vat. "),
        usj.char("fq", words.strip().rstrip(".")),
        usj.char("ft", "."),
    ]


def edition_note(key, reference, content, scope=None):
    extra = {"x-key": key, "category": "edition"}
    if scope is not None:
        extra["x-scope"] = scope
    return usj.note("f", usj.char("fr", f"{reference} "), *content, caller="+", **extra)


def operations(policy, code):
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
        for index, item in enumerate(entry.get("edits", ()), 1):
            verse = item["target"].split()[-1]
            yield key, further(entry, item), entry["appendix"], verse, f"{key}@{index}"


def further(entry, item):
    """A decision's further replacement: its own words, derivation and note
    position, and the decision's reason, note and lemma unless it has its
    own. Only the decision itself may omit a verse."""
    inherited = {
        k: v for k, v in entry.items() if k not in ("english", "note_at", "omit_verse")
    }
    return {**inherited, **item}


def consumed_notes(policy, code):
    """The keys of the notes a book's decisions replace or take up."""
    data = policy.alexandrinus
    keys = {key for key in data["readings"] if key.split()[0] == code}
    for key, entry in data["passages"].items():
        if key.split()[0] == code:
            keys.update(entry.get("source_notes", ()))
    return keys


def companions(policy, code):
    """The notes a book's decisions rewrite without replacing the words they
    stand in: a reading's companion notes, and kept notes given new words."""
    data = policy.alexandrinus
    found = {}
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
            found[key] = {
                "from": entry["source_note"],
                "to": entry["note"],
                "why": entry["why"],
            }
    return found


def check(policy, books):
    """Every decision well formed, and the decisions exhaustive: each of
    Brenton's Alexandrine notes and each paragraph of the Appendix's supplied
    passages has exactly one."""
    data = policy.alexandrinus
    require_fields(
        data,
        {"swete", "witness_evidence", "readings", "passages", "kept"},
        (),
        "Alexandrine file",
    )
    sections = [set(data[s]) for s in ("readings", "passages", "kept")]
    require(
        sum(map(len, sections)) == len(set.union(*sections)),
        "Alexandrine decision appears in several sections",
    )
    for section in ("readings", "passages", "kept"):
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
            elif section == "passages":
                require(
                    ("appendix" in entry) != ("kjv" in entry)
                    and bool(entry.get("edits") or entry.get("insertions")),
                    f"Alexandrine passage needs one English source and an operation: {key}",
                )
                require(
                    entry.get("kjv", True) is True
                    and not (
                        "kjv" in entry and (entry.get("edits") or entry.get("supplied"))
                    ),
                    f"KJV passage must preserve its source verse: {key}",
                )
            for item in entry.get("edits", ()):
                require(
                    set(item) <= REPLACEMENT | COMMON and "target" in item,
                    f"Invalid Alexandrine edit: {key}",
                )
                check_swete(key, {**entry, **item}, policy)
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
        for block in doc["content"]
        if block["type"] == "para"
        for note in usj.notes_of(block["content"])
        if "x-key" in note and ALEX.search(notes.source_text(note))
    }
    require(
        found == declared,
        f"Alexandrine notes not exhaustive; missing: {sorted(found - declared)}; unused: {sorted(declared - found)}",
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


def supplied_heading(doc):
    found = [
        index
        for index, block in enumerate(doc["content"])
        if usj.is_type(block, "para", "is1")
        and usj.text_of(block["content"]).strip() == SUPPLIED
    ]
    require(len(found) == 1, "Alexandrine appendix heading changed")
    return found[0]


def supplied_paragraphs(doc):
    return [
        block
        for block in doc["content"][supplied_heading(doc) :]
        if usj.is_type(block, "para", "ip")
    ]


def pruned_appendix(doc, policy):
    """The Appendix without the passages the edition prints in their books,
    the sections left empty by their going, and the blank lines left doubled."""
    promoted = [
        usj.parse(entry["appendix"])["content"][0]
        for entry in policy.alexandrinus["passages"].values()
        if "appendix" in entry
    ]
    start = supplied_heading(doc)
    blocks = doc["content"][: start + 1]
    rest = list(doc["content"][start + 1 :])
    for paragraph in promoted:
        matches = [i for i, block in enumerate(rest) if block == paragraph]
        require(len(matches) == 1, "Alexandrine appendix span not found once")
        del rest[matches[0]]
    # A section holds what follows its heading, up to the next heading.
    kept, index = [], 0
    while index < len(rest):
        end = next(
            (
                i
                for i in range(index + 1, len(rest))
                if usj.is_type(rest[i], "para") and rest[i]["marker"] in ("is1", "is2")
            ),
            len(rest),
        )
        section = rest[index:end]
        empty = all(usj.is_type(b, "para", "ib") for b in section[1:])
        if not (usj.is_type(section[0], "para", "is2") and empty):
            kept += section
        index = end
    for block in kept:
        if usj.is_type(block, "para", "ib") and usj.is_type(blocks[-1], "para", "ib"):
            continue
        blocks.append(block)
    return usj.with_blocks(doc, blocks)


def surviving_scope(note, verse, offset, policy):
    """The words a note of Brenton's is about, measured against its verse
    before a reading changes it: its lemma and the narrower words it glosses."""
    key = note["x-key"]
    exception = policy.brenton_notes["notes"].get(key, {})
    words = word_spans(verse.text)
    span, glossed, _ = lemmas.inferred(
        note["marker"],
        verse.text,
        words,
        offset,
        notes.reading_of(note, exception.get("note"), key),
        exception,
        key,
    )
    return (
        lemmas.lemma_text(verse.text, words, span) if span else None,
        lemmas.lemma_text(verse.text, words, glossed) if glossed else None,
    )


def anchor(verse, phrase, key):
    """Where a phrase stands in a verse: the start of its one occurrence, as
    whole words, whatever the markup; a note on the whole verse stands at its
    start. An absent or repeated phrase needs a decision, never a guess."""
    if phrase is None:
        return 0
    words = word_spans(verse.text)
    hits = lemmas.occurrences(words, words_of(phrase))
    require(
        words_of(phrase) and len(hits) == 1,
        f"Surviving note lemma not anchored once: {key} ({len(hits)})",
    )
    return words[hits[0]][1]


def check_pins(code, policy, placed, consumed, rewritten):
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
    content: tuple
    note: dict | None = None
    note_verse: str | None = None
    note_at: tuple = (0, 0)
    omits_verse: bool = False


def replacement(key, entry, source, verse, note_key, verses, consumed):
    reference = verse.reference
    # The words as the verse has them, however a note among them parts
    # their spaces.
    old = usj.text_of(usj.parse(entry["from"], fragment=True))
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
    body = note_content(entry, key)
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
            and entry.get("lemma", "") is None
            and body is not None,
            f"Whole-verse omission leaves surviving text, or no note: {key}",
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


def shifted(position, changes, strict=False):
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


def promoted(code, doc, policy, kjv):
    """A book of Brenton's with its Alexandrine decisions carried out."""
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
    replacements = []
    for key, entry, source, reference, note_key in operations(policy, code):
        require(reference in verses, f"Alexandrine target verse missing: {key}")
        replacements.append(
            replacement(
                key, entry, source, verses[reference], note_key, verses, consumed
            )
        )
    if not replacements and not rewritten:
        return with_insertions(code, doc, policy, kjv)
    omitted = {r.verse for r in replacements if r.omits_verse}
    # Every note of a verse the decisions touch is taken up, and set again
    # where it belongs once the words have changed.
    touched = (
        {r.verse for r in replacements}
        | {r.note_verse for r in replacements if r.note}
        | {placed[key][0].reference for key in rewritten}
    ) - omitted
    again = {}
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
        kept = []
        for offset, note in verse.notes:
            key = note["x-key"]
            if key in consumed:
                continue
            companion = rewritten.get(key)
            scope = None
            if companion is not None and "lemma" in companion:
                scope = {"declared": companion["lemma"]}
            elif any(r.start <= offset < r.end for r in changes):
                # A note within replaced words keeps the words it was about.
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
        fresh = [
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
    doc = with_insertions(code, doc, policy, kjv)
    verses = scripture.verses(doc)
    changes = []
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
            changes.append((verse, position, position, [note]))
    return scripture.edited(doc, changes)


def pinned(key, body, placed):
    """A decision's source note must be the note as the corrected source has it."""
    require(
        key in placed and plain(notes.source_text(placed[key][2])) == plain(body),
        f"Alexandrine source note changed: {key}",
    )


def derived_lemma(english, at):
    """The words a displaced reading's note is about: those printed after its
    caller, without their closing punctuation."""
    words = plain(usj.text_of(usj.parse(english[at:], fragment=True)))
    return words.strip().strip(".,;:!?") or None


def without_verses(doc, omitted):
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


def with_insertions(code, doc, policy, kjv):
    """The document with the verses its passages supply, each from Brenton's
    Appendix by a declared derivation, or verbatim from the King James Bible."""
    for key, entry in policy.alexandrinus["passages"].items():
        if key.split()[0] != code:
            continue
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
            parts = verses[reference].parts
            if "before" in insertion:
                block, at = parts[0][0], parts[0][1] - 1
            else:
                # After the verse's words, in the paragraph that holds them.
                block, at = parts[-1][0], parts[-1][2]
            items = []
            for verse in insertion["verses"]:
                require_fields(
                    verse,
                    {"reference"},
                    {"note", "witnesses", "english"},
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
                        f"{code} {label}" == key and "english" not in verse,
                        f"KJV insertion changed its source verse: {key}",
                    )
                    source = scripture.verses(kjv[code])
                    require(label in source, f"KJV source verse missing: {key}")
                    words = [
                        item
                        for b, lo, hi, _ in source[label].parts
                        for item in kjv[code]["content"][b]["content"][lo:hi]
                    ]
                else:
                    english = derived(
                        key, verse, entry["appendix"], entry.get("supplied", ())
                    )
                    words = usj.parse(english.strip(), fragment=True)
                items.append(
                    {"type": "verse", "marker": "v", "number": label.split(":")[1]}
                )
                if "note" in verse:
                    items.append(
                        edition_note(
                            f"{code} {label}",
                            label,
                            usj.parse(verse["note"], fragment=True),
                            {"declared": None},
                        )
                    )
                items += words
            blocks = list(doc["content"])
            content = blocks[block]["content"]
            blocks[block] = {
                **blocks[block],
                "content": usj.joined(content[:at], items, content[at:]),
            }
            doc = usj.with_blocks(doc, blocks)
    return doc
