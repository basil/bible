"""Declared Alexandrine readings, checked against Brenton and audited to Swete.

The decision file owns every departure from the Vatican translation. This
stage runs before selection, relabelling and footnote presentation.
"""

from collections import Counter
import re

from bible import notes, paths, sources
from bible.alexandrinus_data import expand_decisions
from bible.checks import require
from bible.files import read_json
from bible.usfm import canonical_text, plain_text, verse_spans, word_spans, words_of

DATA = expand_decisions(read_json(paths.EDITION_DIR / "alexandrinus.json"))
ALEX = re.compile(r"\b(?:Alex\.?|Alexandr\w*|App(?:endix)?\.?)(?!\w)")
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


def tokens(text):
    """Words and number values, including Brenton's reversed tens and ordinals."""
    words = re.findall(
        r"\d[\d,]*(?:st|nd|rd|th)?|[^\W\d_]+(?:[’'][^\W\d_]+)*",
        plain_text(text).casefold(),
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


def check_swete(key, entry, kept=False):
    require(isinstance(entry, dict), f"Invalid Alexandrine decision: {key}")
    swete = entry.get("swete")
    require(
        isinstance(swete, dict)
        and set(swete) == {"volume", "page", "evidence", "reading", "agrees"},
        f"Malformed Swete record: {key}",
    )
    require(
        type(swete["volume"]) is int
        and str(swete["volume"]) in DATA["swete"]
        and type(swete["page"]) is int
        and swete["page"] > 0
        and isinstance(swete["evidence"], str)
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
    supplied = entry.get("supplied", [])
    require(
        isinstance(supplied, list)
        and all(isinstance(w, str) and w.strip() for w in supplied),
        f"Invalid supplied words: {key}",
    )


def check_vocabulary(key, entry, source, before, after):
    for text in (before, after):
        markers = re.findall(r"\\(\+?[A-Za-z][A-Za-z0-9]*\*?)", text)
        require(
            all(marker in {"add", "add*"} for marker in markers),
            f"Unsupported USFM marker in Alexandrine replacement: {key}",
        )
    allowed = set(
        tokens(before) + tokens(source) + tokens(" ".join(entry.get("supplied", [])))
    )
    added = set(tokens(after.replace("{note}", ""))) - allowed
    require(not added, f"English not supplied by Brenton: {key}: {sorted(added)}")
    require(
        "{note}" not in before and after.count("{note}") <= 1,
        f"Invalid Alexandrine note position: {key}",
    )


def check_english(key, entry, source, before, after):
    """Derive exact English from a source phrase and explicit editorial edits.

    Vocabulary membership is only a secondary check. The derivation retains
    order, multiplicity, punctuation, spelling, whitespace and supplied markup.
    {note} is a caller position, not part of the English.
    """
    check_vocabulary(key, entry, source, before, after)
    proof = entry.get("english")
    require(
        isinstance(proof, dict)
        and set(proof) == {"source", "text", "edits"}
        and isinstance(proof["source"], str)
        and proof["source"] in {"brenton", "from"}
        and isinstance(proof["text"], str)
        and bool(proof["text"])
        and isinstance(proof["edits"], list),
        f"Missing or malformed exact English derivation: {key}",
    )
    original = source if proof["source"] == "brenton" else before
    base = proof["text"]
    require(
        base in original,
        f"English source phrase changed: {key}",
    )
    parts = []
    end = 0
    for edit in proof["edits"]:
        require(
            isinstance(edit, dict)
            and set(edit) == {"start", "from", "to", "why"}
            and type(edit["start"]) is int
            and all(isinstance(edit[k], str) for k in ("from", "to", "why"))
            and bool(edit["why"].strip())
            and edit["from"] != edit["to"],
            f"Malformed English editorial edit: {key}",
        )
        start = edit["start"]
        stop = start + len(edit["from"])
        require(
            end <= start <= stop <= len(base) and base[start:stop] == edit["from"],
            f"English editorial edit source changed: {key}",
        )
        parts.extend((base[end:start], edit["to"]))
        end = stop
    parts.append(base[end:])
    require(
        "".join(parts) == after.replace("{note}", ""),
        f"English differs from exact derivation: {key}",
    )


def check_source_notes(key, entry, by_key):
    """Pin complete corrected note bodies, including non-Alexandrine glosses."""
    expected = (
        [key]
        if key in DATA["readings"] or key in DATA["kept"] and "appendix" not in entry
        else []
    ) + entry.get("consumes", [])
    snapshots = entry.get("source_notes", {})
    require(
        isinstance(snapshots, dict) and set(snapshots) == set(expected),
        f"Missing or unused Alexandrine source note snapshots: {key}",
    )
    for identity, body in snapshots.items():
        require(
            identity in by_key and by_key[identity]["body"] == body,
            f"Alexandrine source note changed: {key}: {identity}",
        )


def keyed_notes(code, text):
    seen = Counter()
    result = []
    removed = 0
    for match in notes.BRENTON_NOTE.finditer(text):
        seen[match[2]] += 1
        result.append(
            {
                "key": notes.note_key(code, match[2], seen[match[2]]),
                "reference": match[2],
                "body": match[3],
                "kind": match[1],
                "position": match.start() - removed,
            }
        )
        removed += len(match[0])
    return notes.BRENTON_NOTE.sub("", text), result


def kjv_verse(reference, archives=None):
    """Read the borrowed English verbatim from the pinned KJV archive."""
    archives = sources.load_archives() if archives is None else archives
    parts = reference.split() if isinstance(reference, str) else []
    require(len(parts) == 2, "Invalid KJV source reference")
    code, wanted = parts
    text = archives.get("kjv", {}).get(code, "")
    found = [text[a:b].strip() for ref, a, b in verse_spans(text) if ref == wanted]
    require(len(found) == 1, f"KJV source verse missing: {reference}")
    return found[0]


def inserted_text(entry, verse, archives=None):
    if "kjv" in entry:
        require(
            "text" not in verse and "english" not in verse,
            f"Redundant KJV insertion text: {entry['kjv']}",
        )
        return kjv_verse(entry["kjv"], archives)
    return verse["text"]


def appendix_paragraphs(text):
    heading = "\\is1 The Following Passages are Supplied From the Alexandrine Text"
    require(text.count(heading) == 1, "Alexandrine appendix heading changed")
    return re.findall(r"^\\ip [^\n]*", text[text.index(heading) :], re.M)


def check_decisions(archives):
    require(isinstance(DATA, dict), "Alexandrine file must be an object")
    require(
        set(DATA) == {"swete", "readings", "passages", "kept"},
        "Alexandrine file has missing or unknown sections",
    )
    require(
        all(isinstance(DATA[s], dict) for s in DATA),
        "Alexandrine sections must be objects",
    )
    require(
        bool(DATA["swete"])
        and all(
            k in {"1", "2", "3"} and isinstance(v, str) and v.strip()
            for k, v in DATA["swete"].items()
        ),
        "Invalid Swete bibliography",
    )
    corrected = {
        code: notes.corrected_brenton(code, text, lambda *a, **k: None)
        for code, text in archives["brenton"].items()
    }
    references = {
        code: {ref for ref, _, _ in verse_spans(keyed_notes(code, text)[0])}
        for code, text in corrected.items()
    }
    common = {"why", "swete", "supplied"}
    replacement = {"from", "to", "note", "lemma", "target", "english"}

    def target_code(key):
        require(
            isinstance(key, str) and len(key.split()) == 2,
            f"Invalid Alexandrine key: {key}",
        )
        code = key.split()[0]
        require(code in corrected and code != "BAK", f"Alexandrine book missing: {key}")
        return code

    def check_target(key, target, code):
        require(
            isinstance(target, str)
            and len(target.split()) == 2
            and target.split()[0] == code,
            f"Alexandrine target must name its source book: {key}",
        )
        require(
            target.split()[1] in references[code],
            f"Alexandrine target verse missing: {key}: {target}",
        )

    def check_replacement(key, entry, code, default_target=None):
        require(
            isinstance(entry.get("from"), str)
            and bool(entry["from"])
            and isinstance(entry.get("to"), str),
            f"Invalid Alexandrine replacement: {key}",
        )
        require(
            "{note}" not in entry["from"] and entry["to"].count("{note}") <= 1,
            f"Invalid Alexandrine note position: {key}",
        )
        require(
            "note" not in entry
            or entry["note"] is None
            or isinstance(entry["note"], str)
            and bool(entry["note"].strip()),
            f"Invalid Alexandrine footnote: {key}",
        )
        require(
            "lemma" not in entry
            or entry["lemma"] is None
            or isinstance(entry["lemma"], str)
            and bool(entry["lemma"].strip()),
            f"Invalid Alexandrine lemma: {key}",
        )
        check_target(key, entry.get("target", default_target), code)

    inserted = set()
    for section in ("readings", "passages", "kept"):
        allowed = common | (
            replacement
            | {"edits", "note_edits", "source_notes", "omit_verse", "note_target"}
            if section == "readings"
            else (
                {
                    "appendix",
                    "kjv",
                    "book",
                    "consumes",
                    "edits",
                    "insertions",
                    "source_notes",
                }
                if section == "passages"
                else {"appendix", "todo", "source_notes", "note"}
            )
        )
        for key, entry in DATA[section].items():
            require(
                isinstance(entry, dict) and set(entry) <= allowed,
                f"Unknown Alexandrine decision fields: {key}",
            )
            check_swete(key, entry, section == "kept")
            if "appendix" in entry:
                require(
                    isinstance(entry["appendix"], str)
                    and entry["appendix"].startswith("\\ip ")
                    and corrected["BAK"].count(entry["appendix"]) == 1,
                    f"Alexandrine appendix span not found once: {key}",
                )
            if section == "kept":
                require(
                    "note" not in entry
                    or "appendix" not in entry
                    and isinstance(entry["note"], str)
                    and entry["note"].strip(),
                    f"Invalid retained Alexandrine footnote: {key}",
                )
                require(
                    "todo" not in entry or type(entry["todo"]) is bool,
                    f"Invalid Alexandrine todo: {key}",
                )
                require(
                    not entry.get("supplied"),
                    f"Kept Alexandrine decision has supplied words: {key}",
                )
                if "appendix" not in entry:
                    target_code(key)
                else:
                    require(
                        isinstance(key, str) and key.startswith("BAK "),
                        f"Invalid Alexandrine appendix key: {key}",
                    )
                    target_code(key.removeprefix("BAK "))
                continue
            code = target_code(key)
            if section == "readings":
                check_replacement(key, entry, code, key.split("#")[0])
                if "omit_verse" in entry or "note_target" in entry:
                    require(
                        entry.get("omit_verse") is True
                        and not entry["to"].replace("{note}", "")
                        and entry.get("lemma") is None
                        and isinstance(entry.get("note"), str),
                        f"Invalid whole-verse omission: {key}",
                    )
                    check_target(key, entry.get("note_target"), code)
                    reference = entry.get("target", key).split()[-1].split("#")[0]
                    target = entry["note_target"].split()[-1]
                    ordered = [r for r, _, _ in verse_spans(corrected[code])]
                    require(
                        ordered.index(reference) > 0
                        and ordered[ordered.index(reference) - 1] == target
                        and reference.split(":")[0] == target.split(":")[0],
                        f"Omission note must attach to the preceding verse: {key}",
                    )
                require(
                    isinstance(entry.get("edits", []), list),
                    f"Invalid Alexandrine edits: {key}",
                )
                for item in entry.get("edits", []):
                    require(
                        isinstance(item, dict)
                        and set(item) <= replacement | common
                        and "target" in item,
                        f"Invalid Alexandrine reading edit: {key}",
                    )
                    operation = {**entry, **item}
                    check_replacement(key, operation, code)
                    check_swete(key, operation)
                continue
            require(
                ("appendix" in entry) != ("kjv" in entry),
                f"Alexandrine passage needs one English source: {key}",
            )
            if "kjv" in entry:
                require(
                    entry["kjv"] == key
                    and not entry.get("edits")
                    and not entry.get("supplied"),
                    f"KJV passage must preserve its source verse: {key}",
                )
            require(
                "book" not in entry or entry["book"] == code,
                f"Alexandrine passage book disagrees with key: {key}",
            )
            consumes = entry.get("consumes", [])
            require(
                isinstance(consumes, list)
                and all(
                    isinstance(k, str) and len(k.split()) == 2 and k.split()[0] == code
                    for k in consumes
                ),
                f"Invalid Alexandrine consumed notes: {key}",
            )
            require(
                all(
                    isinstance(entry.get(field, []), list)
                    for field in ("edits", "insertions")
                )
                and bool(entry.get("edits") or entry.get("insertions")),
                f"Alexandrine passage without operations: {key}",
            )
            for item in entry.get("edits", []):
                require(
                    isinstance(item, dict)
                    and set(item) <= replacement | common
                    and "target" in item,
                    f"Invalid Alexandrine passage edit: {key}",
                )
                operation = {**entry, **item}
                check_replacement(key, operation, code)
                check_swete(key, operation)
            for insertion in entry.get("insertions", []):
                require(
                    isinstance(insertion, dict)
                    and set(insertion) <= {"before", "after", "verses"}
                    and ("before" in insertion) != ("after" in insertion),
                    f"Invalid Alexandrine insertion: {key}",
                )
                anchor = insertion.get("before", insertion.get("after"))
                require(
                    isinstance(anchor, str),
                    f"Invalid Alexandrine insertion anchor: {key}",
                )
                check_target(key, f"{code} {anchor}", code)
                verses = insertion.get("verses")
                require(
                    isinstance(verses, list) and bool(verses),
                    f"Alexandrine insertion without verses: {key}",
                )
                for verse in verses:
                    require(
                        isinstance(verse, dict)
                        and {"reference"} <= set(verse)
                        and set(verse) <= {"reference", "text", "note", "english"}
                        and isinstance(verse["reference"], str)
                        and re.fullmatch(r"[1-9]\d*:[1-9]\d*[a-z]?", verse["reference"])
                        is not None
                        and ("kjv" in entry or "text" in verse),
                        f"Invalid Alexandrine inserted verse: {key}",
                    )
                    text = inserted_text(entry, verse, archives)
                    require(
                        isinstance(text, str) and bool(text.strip()),
                        f"Invalid Alexandrine inserted verse: {key}",
                    )
                    ref = verse["reference"]
                    require(
                        "note" not in verse
                        or isinstance(verse["note"], str)
                        and bool(verse["note"].strip()),
                        f"Invalid Alexandrine inserted verse note: {key}",
                    )
                    if "kjv" in entry:
                        require(
                            f"{code} {ref}" == entry["kjv"],
                            f"KJV insertion changed its source verse: {key}",
                        )
                    require(
                        ref.split(":")[0] == anchor.split(":")[0],
                        f"Alexandrine insertion crosses chapter: {key}",
                    )
                    require(
                        ref not in references[code] and (code, ref) not in inserted,
                        f"Alexandrine verse already exists: {key}: {ref}",
                    )
                    inserted.add((code, ref))
    sets = [set(DATA[s]) for s in ("readings", "passages", "kept")]
    require(
        sum(map(len, sets)) == len(set.union(*sets)),
        "Alexandrine decision appears in several sections",
    )
    found = set()
    for code, text in corrected.items():
        _, entries = keyed_notes(code, text)
        found.update(n["key"] for n in entries if ALEX.search(n["body"]))
    consumed = [k for v in DATA["passages"].values() for k in v.get("consumes", [])]
    require(
        len(consumed) == len(set(consumed)),
        "Alexandrine note consumed by several passages",
    )
    declared = (
        set(DATA["readings"])
        | {k for k, v in DATA["kept"].items() if "appendix" not in v}
        | set(consumed)
    )
    require(
        not set(consumed) & (set(DATA["readings"]) | set(DATA["kept"])),
        "Alexandrine passage note also has a decision",
    )
    for code, text in corrected.items():
        if code != "BAK":
            _, found_notes = keyed_notes(code, text)
            companion_edits(code, {n["key"]: n for n in found_notes}, set(consumed))
    require(
        found == declared,
        f"Alexandrine notes not exhaustive; missing: {sorted(found - declared)}; unused: {sorted(declared - found)}",
    )
    appendix = notes.corrected_brenton(
        "BAK", archives["brenton"]["BAK"], lambda *a, **k: None
    )
    spans = [
        v["appendix"].rstrip("\n")
        for section in ("passages", "kept")
        for v in DATA[section].values()
        if "appendix" in v
    ]
    paragraphs = appendix_paragraphs(appendix)
    require(
        Counter(spans) == Counter(paragraphs),
        "Alexandrine appendix passages not exhaustive",
    )
    for section in ("readings", "passages", "kept"):
        for key, entry in DATA[section].items():
            check_swete(key, entry, section == "kept")
    for section in ("readings", "passages", "kept"):
        for key, entry in DATA[section].items():
            code = key.split()[0]
            _, found_notes = keyed_notes(code, corrected[code])
            by_key = {n["key"]: n for n in found_notes}
            check_source_notes(key, entry, by_key)
            if section == "kept":
                continue
            source = entry.get("appendix", by_key.get(key, {}).get("body", ""))
            operations = ([entry] if section == "readings" else []) + entry.get(
                "edits", []
            )
            for item in operations:
                # Every additional operation owns its derivation; it cannot
                # inherit its parent's proof for a different English span.
                operation = {**entry, **item, "english": item.get("english")}
                check_english(key, operation, source, item["from"], item["to"])
            if "kjv" not in entry:
                for insertion in entry.get("insertions", []):
                    for verse in insertion["verses"]:
                        check_english(
                            key,
                            {**entry, "english": verse.get("english")},
                            source,
                            "",
                            verse["text"],
                        )
    return len(found), len(paragraphs)


def replacement_note(entry):
    if "note" in entry:
        return entry["note"]
    return (
        "\\fqa Vat. \\ft \\+it "
        + plain_text(entry["from"]).strip().rstrip(".")
        + "\\+it*."
    )


def lemma_of(entry):
    if "lemma" in entry:
        return entry["lemma"]
    after = (
        entry["to"].partition("{note}")[2] if "{note}" in entry["to"] else entry["to"]
    )
    return plain_text(after).strip().strip(".,;:!?") or None


def place_edits(text, edits):
    """Apply disjoint declared spans, retaining the untouched stretches verbatim."""
    parts = []
    end = 0
    for start, stop, replacement, _ in edits:
        parts.extend((text[end:start], replacement))
        end = stop
    parts.append(text[end:])
    return "".join(parts)


def companion_edits(code, by_key, consumed):
    """Validate declared rewrites of notes that survive a promoted reading."""
    result = {}
    unavailable = consumed | set(DATA["readings"]) | set(DATA["kept"])
    for owner, entry in DATA["readings"].items():
        if owner.split()[0] != code:
            continue
        edits = entry.get("note_edits", [])
        require(isinstance(edits, list), f"Invalid companion note edits: {owner}")
        for edit in edits:
            require(
                isinstance(edit, dict)
                and {"key", "from", "to", "why"} <= set(edit)
                and set(edit) <= {"key", "from", "to", "lemma", "why"}
                and all(
                    isinstance(edit[k], str) and edit[k].strip()
                    for k in ("key", "from", "to", "why")
                )
                and (
                    "lemma" not in edit
                    or edit["lemma"] is None
                    or isinstance(edit["lemma"], str)
                    and edit["lemma"].strip()
                ),
                f"Invalid companion note edit: {owner}",
            )
            key = edit["key"]
            require(key in by_key, f"Companion note missing: {owner}: {key}")
            require(
                key not in unavailable and key not in result,
                f"Conflicting companion note edit: {owner}: {key}",
            )
            require(
                by_key[key]["body"] == edit["from"],
                f"Companion note source changed: {owner}: {key}",
            )
            require(
                not re.search(r"\\(?:f|x|fr|xo)\b", edit["to"]),
                f"Companion note edit contains an envelope: {owner}: {key}",
            )
            result[key] = {**edit, "owner": owner}
    return result


def surviving_lemma(note, clean, span):
    """Measure a surviving note against its original words, before editing them."""
    key = note["key"]
    exception = notes.BRENTON_NOTES["notes"].get(key, {})
    source = note["body"] if note["kind"] == "f" else "See " + note["body"]
    _, _, alternative, _ = notes.note_body(
        notes.brenton_pieces(source), exception.get("note"), key, source
    )
    start, end = span
    verse = clean[start:end]
    words = word_spans(verse)
    offset = max(note["position"] - start, 0)
    chosen, rule = notes.inferred_lemma(note["kind"], verse, words, offset, alternative)
    glossed, _ = notes.inferred_lemma(
        note["kind"], verse, words, offset, alternative, widen=False
    )
    chosen, glossed, _ = notes.overridden_lemma(
        verse, words, exception, chosen, glossed, rule, key, exception.get("occurrence")
    )
    return (
        notes.lemma_text(verse, words, chosen) if chosen else None,
        notes.lemma_text(verse, words, glossed) if glossed else None,
    )


def surviving_anchor(note, result, span, lemma):
    """Find the original phrase once, ignoring markup, spaces and typography.

    word_spans casefolds ligatures and retains offsets into the actual USFM.
    An absent or repeated phrase needs an editorial decision, never an offset
    guess that could silently put a caller inside another word.
    """
    start, end = span
    words = word_spans(result[start:end])
    if lemma is None:
        return start
    phrase = words_of(lemma)
    hits = notes.occurrences(words, phrase)
    require(
        phrase and len(hits) == 1,
        f"Surviving note lemma not anchored once: {note['key']} ({len(hits)})",
    )
    return start + words[hits[0]][1]


def promoted(code, text, record, context=None):
    for key, entry in DATA["kept"].items():
        if ("appendix" in entry and code == "BAK") or (
            "appendix" not in entry and key.split()[0] == code
        ):
            if "appendix" not in entry:
                _, source_notes = keyed_notes(code, text)
                check_source_notes(key, entry, {n["key"]: n for n in source_notes})
            record(
                "retain Brenton's Alexandrine note",
                key=key,
                why=entry["why"],
                swete=entry["swete"],
            )
    if code == "BAK":
        for key, entry in DATA["passages"].items():
            if "appendix" not in entry:
                continue
            span = entry["appendix"]
            require(
                text.count(span) == 1,
                f"Alexandrine appendix span not found once: {key}",
            )
            text = text.replace(span, "", 1)
            record(
                "remove promoted Alexandrine passage from appendix",
                key=key,
                swete=entry["swete"],
            )
        heading = "\\is1 The Following Passages are Supplied From the Alexandrine Text"
        prefix, separator, text = text.partition(heading)
        require(bool(separator), "Alexandrine appendix heading changed")
        removed_headings = []

        def without_empty_section(match):
            heading, _, body = match.group().partition("\n")
            if re.sub(r"(?m)^\\ib\s*$", "", body).strip():
                return match.group()
            removed_headings.append(heading)
            return ""

        text = re.sub(
            r"^\\is2 [^\n]*(?:\n|$).*?(?=^\\is[12] |\Z)",
            without_empty_section,
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        before_spacing = text
        text = re.sub(r"(?m)(^\\ib[^\S\n]*\n)(?:\\ib[^\S\n]*\n)+", r"\1", text)
        if removed_headings or text != before_spacing:
            record(
                "remove empty appendix sections and repeated blank paragraphs",
                headings=removed_headings,
                repeated_blank_paragraphs=before_spacing.count("\\ib")
                - text.count("\\ib"),
            )
        return prefix + separator + text
    clean, found = keyed_notes(code, text)
    by_key = {n["key"]: n for n in found}
    consumed = set()
    edits = []
    new_notes = []
    lemmas = {}
    spans = {r: (a, b) for r, a, b in verse_spans(clean)}

    def edit(key, entry, source, reference, note_key=None, omit_verse=False):
        require(reference in spans, f"Alexandrine target verse missing: {key}")
        a, b = spans[reference]
        old, new = entry["from"], entry["to"]
        require(
            isinstance(old, str) and old and isinstance(new, str),
            f"Invalid Alexandrine replacement: {key}",
        )
        require(
            clean[a:b].count(old) == 1,
            f"Alexandrine from not found once outside notes: {key}",
        )
        check_english(key, entry, source, old, new)
        at = a + clean[a:b].index(old)
        body = replacement_note(entry)
        require(
            body is None or isinstance(body, str) and body.strip(),
            f"Invalid Alexandrine footnote: {key}",
        )
        require(
            body is not None or entry.get("why"),
            f"Dropped Vatican text without a why: {key}",
        )
        marker = new.index("{note}") if "{note}" in new else 0
        new = new.replace("{note}", "")
        edits.append((at, at + len(old), new, key))
        note_reference, note_at = reference, at
        if omit_verse:
            require(
                not new and plain_text(clean[a:b]) == plain_text(old),
                f"Whole-verse omission leaves surviving text: {key}",
            )
            require(
                not any(
                    n["reference"] == reference and n["key"] not in consumed
                    for n in found
                ),
                f"Whole-verse omission leaves a surviving note: {key}",
            )
            verse_marker = clean.rfind("\\v ", 0, a)
            edits.append((verse_marker, a, "", key))
            note_reference = entry["note_target"].split()[-1]
            start, end = spans[note_reference]
            # Attach at the end of the previous verse, before its layout markers.
            tail = re.search(r"(?:\\(?:p|m|b|nb|q\d?)\s*)+$", clean[start:end])
            end = start + tail.start() if tail else end
            note_at = start + len(clean[start:end].rstrip())
            record(
                "omit verse label and attach its note to the preceding verse",
                key=key,
                target=entry["note_target"],
                omitted=f"{code} {reference}",
            )
        if body is not None:
            identity = note_key or key
            new_notes.append(
                {
                    "key": identity,
                    "reference": note_reference,
                    "kind": "f",
                    "body": body,
                    "edit_at": note_at,
                    "offset": marker,
                }
            )
            lemmas[identity] = lemma_of(entry)
        record(
            "print the Alexandrine reading",
            key=key,
            target=f"{code} {reference}",
            **{
                "from": old,
                "to": new,
                "note": body,
                "swete": entry.get("swete"),
                "english": entry["english"],
            },
        )

    for key, entry in DATA["readings"].items():
        if key.split()[0] != code:
            continue
        require(
            key in by_key and ALEX.search(by_key[key]["body"]),
            f"Alexandrine keyed note missing: {key}",
        )
        check_source_notes(key, entry, by_key)
        consumed.add(key)
        target = entry.get("target", key).split()[1].split("#")[0]
        edit(
            key,
            entry,
            by_key[key]["body"],
            target,
            key,
            entry.get("omit_verse", False),
        )
        for index, item in enumerate(entry.get("edits", [])):
            operation = {**entry, **item, "english": item.get("english")}
            edit(
                key,
                operation,
                by_key[key]["body"],
                item["target"].split()[-1],
                f"{key}@{index + 1}",
            )
    for key, entry in DATA["passages"].items():
        if key.split()[0] != code:
            continue
        check_source_notes(key, entry, by_key)
        for identity in entry.get("consumes", []):
            require(
                identity in by_key and ALEX.search(by_key[identity]["body"]),
                f"Alexandrine passage note missing: {identity}",
            )
            consumed.add(identity)
        for index, item in enumerate(entry.get("edits", [])):
            operation = {**entry, **item}
            target = item["target"].split()[-1]
            edit(key, operation, entry["appendix"], target, f"{key}@{index + 1}")
        for insertion in entry.get("insertions", []):
            if "before" in insertion:
                anchor = insertion["before"]
                require(anchor in spans, f"Alexandrine insertion anchor missing: {key}")
                a, _ = spans[anchor]
                marker = clean.rfind("\\v ", 0, a)
                at = marker
            else:
                anchor = insertion["after"]
                require(anchor in spans, f"Alexandrine insertion anchor missing: {key}")
                _, end = spans[anchor]
                before = clean[:end]
                layout = re.search(r"(?:\\(?:p|m|b|nb|q\d?)\s*)+$", before)
                at = layout.start() if layout else end
            addition = ""
            for verse in insertion["verses"]:
                require(
                    verse["reference"] not in spans,
                    f"Alexandrine verse already exists: {key}: {verse['reference']}",
                )
                require(
                    verse["reference"].split(":")[0] == anchor.split(":")[0],
                    f"Alexandrine insertion crosses chapter: {key}",
                )
                if "kjv" in entry:
                    require(
                        f"{code} {verse['reference']}" == entry["kjv"],
                        f"KJV insertion changed its source verse: {key}",
                    )
                else:
                    check_english(
                        key,
                        {**entry, "english": verse.get("english")},
                        entry["appendix"],
                        "",
                        verse["text"],
                    )
                if "note" in verse:
                    identity = f"{code} {verse['reference']}"
                    new_notes.append(
                        {
                            "key": identity,
                            "reference": verse["reference"],
                            "kind": "f",
                            "body": verse["note"],
                            "edit_at": at,
                            "offset": len(addition)
                            + len(f"\\v {verse['reference'].split(':')[1]} "),
                        }
                    )
                    lemmas[identity] = None
                addition += f"\\v {verse['reference'].split(':')[1]} {inserted_text(entry, verse).strip()}\n"
            edits.append((at, at, addition, key))
            record(
                "print the Alexandrine reading",
                key=key,
                anchor=anchor,
                **{
                    "from": "",
                    "to": addition,
                    "note": [v["note"] for v in insertion["verses"] if "note" in v]
                    or None,
                    "swete": entry["swete"],
                    **(
                        {"english": [v["english"] for v in insertion["verses"]]}
                        if "kjv" not in entry
                        else {}
                    ),
                    "source_notes": entry.get("source_notes", {}),
                },
                **({"kjv": entry["kjv"]} if "kjv" in entry else {}),
            )
    companions = companion_edits(code, by_key, consumed)
    for key, entry in DATA["kept"].items():
        if key.split()[0] == code and "note" in entry:
            companions[key] = {
                "from": by_key[key]["body"],
                "to": entry["note"],
                "why": entry["why"],
                "owner": key,
            }
    if not edits and not companions:
        return text
    edits.sort(key=lambda e: (e[0], e[1]))
    for previous, current in zip(edits, edits[1:]):
        require(
            previous[1] <= current[0] and previous[0] != current[0],
            f"Overlapping Alexandrine replacements: {previous[3]}, {current[3]}",
        )
    result = place_edits(clean, edits)
    # Independently undo the declared spans to guard the transformation itself.
    offset = 0
    restored = result
    for start, end, new, key in reversed(edits):
        delta = sum(len(n) - (b - a) for a, b, n, _ in edits if a < start)
        at = start + delta
        require(
            result[at : at + len(new)] == new,
            f"Alexandrine replacement changed unexpectedly: {key}",
        )
        restored = restored[:at] + clean[start:end] + restored[at + len(new) :]
    require(
        canonical_text(restored) == canonical_text(clean),
        f"Alexandrine stage changed text outside declared spans: {code}",
    )

    def shifted(position):
        delta = 0
        for start, end, new, _ in edits:
            if position < start:
                break
            if position < end:
                return start + delta + min(position - start, len(new))
            delta += len(new) - (end - start)
        return position + delta

    result_spans = {r: (a, b) for r, a, b in verse_spans(result)}
    remaining = []
    for original in found:
        key = original["key"]
        if key in consumed:
            continue
        note = dict(original, position=shifted(original["position"]))
        companion = companions.get(key)
        if companion is not None:
            note["body"] = companion["to"]
            if "lemma" in companion:
                lemmas[key] = companion["lemma"]
                note["position"] = surviving_anchor(
                    original,
                    result,
                    result_spans[original["reference"]],
                    companion["lemma"],
                )
            record(
                "rewrite companion note for Alexandrine reading",
                key=key,
                reading=companion["owner"],
                **{field: companion[field] for field in ("from", "to", "why")},
                **({"lemma": companion["lemma"]} if "lemma" in companion else {}),
            )
        affected = any(
            start <= original["position"] < end for start, end, _, _ in edits
        )
        if affected and not (companion is not None and "lemma" in companion):
            lemma, glossed = surviving_lemma(
                original, clean, spans[original["reference"]]
            )
            target_span = result_spans[original["reference"]]
            note["position"] = surviving_anchor(original, result, target_span, lemma)
            # Validate the smaller glossed phrase independently as well. The
            # styling stage must retain its relationship to a widened lemma.
            surviving_anchor(original, result, target_span, glossed)
            lemmas[key] = {"lemma": lemma, "glossed": glossed}
            record(
                "preserve Brenton note anchor across Alexandrine replacement",
                key=key,
                lemma=lemma,
                glossed=glossed,
            )
        remaining.append(note)
    for n in new_notes:
        n["position"] = (
            n["edit_at"]
            + sum(
                len(new) - (end - start)
                for start, end, new, _ in edits
                if start < n["edit_at"]
            )
            + n["offset"]
        )
    ordered = sorted(
        remaining + new_notes,
        key=lambda n: (
            n["position"],
            list(by_key).index(n["key"]) if n["key"] in by_key else len(by_key),
        ),
    )
    for n in reversed(ordered):
        at = n["position"]
        marker = "fr" if n["kind"] == "f" else "xo"
        usfm = f"\\{n['kind']} + \\{marker} {n['reference']} {n['body']}\\{n['kind']}*"
        result = result[:at] + usfm + result[at:]
    if context is not None:
        context.update(keys=[n["key"] for n in ordered], lemmas=lemmas)
    return result
