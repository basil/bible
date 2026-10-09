"""The edition's revision of the translation's spelling, vocabulary and
punctuation (edition/revisions.json), by explicit editorial decisions.

Four kinds of change are declared, each with its reason:

    words    a word respelt or modernized wherever it is printed as a whole
             word: in the translation, its notes, and front and back matter
    passages punctuation in a keyed note or front/back-matter paragraph
    punctuation systematic English punctuation rules
    verses   changes to the words of single verses, each naming its verse,
             as "EZK 1:3", which must have the words once: its punctuation,
             or a spelling particular to it. They stand in groups, by the
             reason they share

Revision finishes the translations after source-dependent decisions, so
that the sources are read and those decisions are met in the sources' own
words. Authored pages then consume the revised text and receive their own
punctuation finishing pass, retaining the source names they discuss. A
change that nothing meets is refused.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from collections.abc import Set as AbstractSet
from difflib import SequenceMatcher

import bible.policy
from bible import repairs, scripture, usfm, usj
from bible.checks import CheckFailed, require, require_fields
from bible.policy_schema import RevisionChange, WordingChange
from bible.sources import NEW_TESTAMENT
from bible.usj import Content, Document, Node

# What revision has met: a word, verse or punctuation rule by its key, and a
# passage change by its selector and words.
type MetRevisions = set[str | tuple[str, str]]


def punctuation_only(old: str, new: str) -> bool:
    """Keep lexical tokens, allowing initial case at a changed sentence end.
    A word keeps its apostrophes and hyphens, a plural's possessive one too."""
    pattern = r"\w+(?:['’\-]\w+)*['’]?"
    before, after = list(re.finditer(pattern, old)), list(re.finditer(pattern, new))
    if len(before) != len(after):
        return False
    for a, b in zip(before, after):
        if a[0] == b[0]:
            continue
        if a[0][1:] != b[0][1:] or a[0][0].casefold() != b[0][0].casefold():
            return False
        ended = bool(re.search(r"[.!?]\W*$", old[: a.start()]))
        ends = bool(re.search(r"[.!?]\W*$", new[: b.start()]))
        if ended == ends or not (
            (ends and a[0][0].islower() and b[0][0].isupper())
            or (ended and a[0][0].isupper() and b[0][0].islower())
        ):
            return False
    return True


def check(policy: bible.policy.Policy) -> None:
    data = policy.revisions
    require_fields(
        data,
        {"why", "words", "verses", "passages", "punctuation"},
        (),
        "Revisions file",
    )
    for name, rule in data["punctuation"].items():
        require(name == "before-em-dash", f"Unknown punctuation rule: {name}")
        require_fields(rule, {"why"}, (), f"Punctuation rule {name}")
        require(bool(rule["why"]), f"Punctuation rule without a why: {name}")
    for word, entry in data["words"].items():
        require_fields(entry, {"to", "why"}, (), f"Respelling of {word}")
        require(
            re.fullmatch(r"\w(?:[\w’' -]*\w)?", word) is not None,
            f"Respelling of what is not a word: {word}",
        )
        require(
            entry["to"] and entry["to"] != word and entry["why"],
            f"Respelling that changes nothing, or without a why: {word}",
        )
    for name, group in data["verses"].items():
        require_fields(group, {"why", "changes"}, (), f"Revisions {name}")
        require(
            group["why"] and group["changes"],
            f"Revisions without a why, or without a change: {name}",
        )
        for change in group["changes"]:
            # A change may add its own reason to its group's.
            require_fields(
                change, {"verse", "from", "to"}, {"why"}, f"Revisions {name}"
            )
            key = change["verse"]
            require(
                re.fullmatch(r"\w{3} \S+:\S+", key) is not None,
                f"Revision of what is not a verse: {name}: {key}",
            )
            # NT wording belongs to checked Greek-reading or rendering
            # decisions. Verse revisions may change its punctuation only;
            # keep words, numbers and internal apostrophes/hyphens intact.
            require(
                key[:3] not in NEW_TESTAMENT
                or punctuation_only(change["from"], change["to"]),
                f"Revision changes New Testament words: {name}: {key}",
            )
            require(
                change["from"]
                and change["from"] != change["to"]
                and change.get("why", True),
                f"Revision that changes nothing, or with an empty why: {name}: {key}",
            )

    matter = {e["id"] for e in policy.entries if "file" not in e and "section" not in e}
    for name, passage_group in data["passages"].items():
        require_fields(
            passage_group, {"why", "changes"}, (), f"Passage revisions {name}"
        )
        require(
            passage_group["why"] and passage_group["changes"],
            f"Passage revisions without a why or change: {name}",
        )
        for passage_change in passage_group["changes"]:
            require_fields(
                passage_change,
                {"from", "to"},
                {"note", "unit", "why"},
                f"Passage revision {name}",
            )
            require(
                ("note" in passage_change) != ("unit" in passage_change),
                f"Passage revision needs one selector: {name}",
            )
            selector = _selector(passage_change)
            require(bool(selector), f"Empty passage selector: {name}")
            require(
                "unit" not in passage_change or passage_change["unit"] in matter,
                f"Passage revision unit is not front or back matter: {selector}",
            )
            require(
                "note" not in passage_change
                or re.fullmatch(r"\w{3} \S+:\S+(?: .+)?", selector) is not None,
                f"Invalid passage note selector: {selector}",
            )
            require(
                passage_change["from"]
                and passage_change["from"] != passage_change["to"]
                and passage_change.get("why", True),
                f"Passage revision changes nothing or has an empty why: {selector}",
            )
            require(
                re.fullmatch(
                    r"[\w\s.,;:?!—–\-()'’‘\"“”\[\]]*",
                    passage_change["from"] + passage_change["to"],
                )
                is not None,
                f"Passage revision is not plain punctuation: {selector}",
            )
            require(
                _same_words(passage_change["from"], passage_change["to"]),
                f"Passage revision changes wording or noninitial capitalization: {selector}",
            )


def _same_words(old: str, new: str) -> bool:
    pattern = r"\w+(?:[-'’]\w+)*"
    before, after = list(re.finditer(pattern, old)), list(re.finditer(pattern, new))
    return len(before) == len(after) and all(
        a[0] == b[0]
        or (
            a[0][:1].islower()
            and b[0] == a[0][:1].upper() + a[0][1:]
            and (
                not new[: b.start()].strip(' \n\t("‘“')
                or new[: b.start()].rstrip(' \n\t("‘“').endswith((".", "?", "!"))
            )
        )
        for a, b in zip(before, after)
    )


def _selector(change: WordingChange) -> str:
    """The note key or the unit a passage revision names."""
    return change.get("note", change.get("unit", ""))


def passage_changes(policy: bible.policy.Policy) -> list[WordingChange]:
    return [
        change
        for group in policy.revisions["passages"].values()
        for change in group["changes"]
    ]


def passages(
    code: str,
    doc: Document,
    policy: bible.policy.Policy,
    met: MetRevisions,
) -> Document:
    """Revise a keyed note or one paragraph, keeping its words and metadata.

    Find every change in the original document, so overlapping decisions
    cannot consume one another. Matches are recorded by selector and words.
    A note is found by its key wherever it is printed: a note keyed in its
    source's book may stand in another (Nehemias holds Esdras's notes, and
    Daniel those of Susanna and Bel), so its key's book does not say which.
    """
    changes = [
        c for c in passage_changes(policy) if "note" in c or c.get("unit") == code
    ]
    if not changes:
        return doc

    def skip(node: Node) -> bool:
        return usj.is_note(node) or usj.is_label(node)

    targets: list[tuple[str | None, Content]] = []

    def collect(content: Content) -> Content:
        targets.append((None, content))
        targets.extend(
            (note.get("x-key"), note["content"])
            for note in usj.notes_of(content)
            if "x-key" in note
        )
        return content

    usj.with_content(doc, collect)
    edits: dict[int, list[tuple[int, int, str]]] = {}
    ranges: dict[int, list[tuple[int, int]]] = {}
    for change in changes:
        old, new = change["from"], change["to"]
        selector = _selector(change)
        selected = [
            content
            for key, content in targets
            if (key == change["note"] if "note" in change else key is None)
        ]
        if "note" in change and not selected:
            # Printed elsewhere, or nowhere, which check_met refuses.
            continue
        found = [
            (content, match.start())
            for content in selected
            for match in re.finditer(
                "(?=" + re.escape(old) + ")", usj.text_of(content, skip=skip)
            )
        ]
        require(
            len(found) == 1 and ("note" not in change or len(selected) == 1),
            f"Passage revision not met once: {selector}: {old}",
        )
        content, at = found[0]
        words = usj.text_of(content, skip=skip)
        require(
            _same_words(words, words[:at] + new + words[at + len(old) :]),
            f"Passage revision changes wording or noninitial capitalization: {selector}: {old}",
        )
        spans = ranges.setdefault(id(content), [])
        require(
            all(at + len(old) <= start or end <= at for start, end in spans),
            f"Overlapping passage revisions: {selector}: {old}",
        )
        spans.append((at, at + len(old)))
        # Only changed characters give way; unchanged words retain their styles.
        edits.setdefault(id(content), []).extend(
            (at + a, at + b, new[c:d])
            for tag, a, b, c, d in SequenceMatcher(
                None, old, new, autojunk=False
            ).get_opcodes()
            if tag != "equal"
        )
        met.add((selector, old))
    if not edits:
        return doc

    def rewrite(content: Content) -> Content:
        revised = content
        if id(content) in edits:
            revised = usj.substituted(content, edits[id(content)], skip=skip)
            require(
                _same_words(
                    usj.text_of(content, skip=skip), usj.text_of(revised, skip=skip)
                ),
                "Combined passage revisions change wording or noninitial "
                f"capitalization: {code}",
            )
        result: Content = []
        for item in revised:
            if isinstance(item, dict) and "content" in item:
                item = {**item, "content": rewrite(item["content"])}
            result.append(item)
        return result

    result = usj.with_content(doc, rewrite)
    # A note's lemma must still quote its verse.
    _check_lemmas(doc, result)
    return result


def verse_changes(policy: bible.policy.Policy) -> list[RevisionChange]:
    return [
        change
        for group in policy.revisions["verses"].values()
        for change in group["changes"]
    ]


def _edit(at: int, old: str, new: str) -> tuple[int, int, str]:
    """Words at an offset giving way to others, as usj.substituted takes
    them. Only what differs gives way, so that the rest keeps its styles."""
    prefix, gone, came = repairs.change(old, new)
    if not gone and not prefix:
        # What is set before the words stands in their style, not in that of
        # the words before them.
        gone, came = old[:1], came + old[:1]
    start = at + prefix
    return start, start + len(gone), came


def _rewritten(
    content: Content, pattern: re.Pattern[str], new: Callable[[re.Match[str]], str]
) -> Content:
    """Content with every match of a pattern in its words giving way to what
    new makes of it. The words are read as one, whatever styles divide them;
    a note's words are its own, not those of the content it stands in."""
    edits = [
        _edit(match.start(), match[0], new(match))
        for match in pattern.finditer(usj.text_of(content))
    ]
    return usj.substituted(content, edits) if edits else content


def respelt(doc: Document, policy: bible.policy.Policy, met: MetRevisions) -> Document:
    """A document with the words the file respells, each recorded as met."""
    words = policy.revisions["words"]
    if not words:
        return doc
    pattern = re.compile(
        r"(?<!\w)(?:"
        + "|".join(map(re.escape, sorted(words, key=len, reverse=True)))
        + r")(?!\w)"
    )

    def new(match: re.Match[str]) -> str:
        met.add(match[0])
        return words[match[0]]["to"]

    def note(item: Node) -> Node:
        if item["type"] != "note":
            return item
        return {**item, "content": _rewritten(item["content"], pattern, new)}

    def respell(content: Content) -> Content:
        # A verse's number parts its words from those of the verse before.
        numbers = [i for i, item in enumerate(content) if usj.is_type(item, "verse")]
        starts, ends = [0, *(i + 1 for i in numbers)], [*numbers, len(content)]
        result = []
        for start, end in zip(starts, ends):
            result += usj.mapped(_rewritten(content[start:end], pattern, new), note)
            result += content[end : end + 1]
        return result

    return usj.with_content(doc, respell)


# The source quotations have not yet been tagged for their fonts. Recognize
# their letters too, and the stops that close them, so that their punctuation
# is not revised as English.
FOREIGN_END = re.compile(f"[{usfm.GREEK}{usfm.HEBREW}][\u0300-\u036f]*[.?!]*$")
BEFORE_DASH = re.compile(r"[,;:]+(?=—)")
# What a tagged foreign word or a label stands as in the English it interrupts.
FOREIGN, LABEL = "\1", "\0"


def punctuated(
    doc: Document, policy: bible.policy.Policy, met: MetRevisions
) -> Document:
    """Regularize English punctuation across styles, within each text unit.

    Notes have their own words; verses, labels and foreign styles interrupt
    a unit. The dash keeps its style because only the punctuation is deleted.
    Punctuation after a tagged foreign word is refused, as it may be the
    foreign text's own, and so is a change that leaves a lemma its verse no
    longer has.
    """
    if "before-em-dash" not in policy.revisions["punctuation"]:
        return doc
    changed = False

    def english(content: Content) -> str:
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif "content" in item and not usj.is_note(item):
                words = english(item["content"])
                parts.append(
                    FOREIGN * len(words)
                    if item.get("marker") in ("wg", "wh")
                    else LABEL * len(words) if usj.is_label(item) else words
                )
        return "".join(parts)

    def rewrite(content: Content, after: str = "") -> Content:
        nonlocal changed
        text = after + english(content)
        edits = []
        for match in BEFORE_DASH.finditer(text, len(after)):
            if text[match.start() - 1 : match.start()] == FOREIGN:
                raise CheckFailed(
                    "Punctuation before a dash after a tagged foreign word: "
                    f"{usj.book_code(doc)}: {text[match.start() : match.start() + 30]}"
                )
            if not FOREIGN_END.search(text, 0, match.start()):
                edits.append((match.start() - len(after), match.end() - len(after), ""))
        if edits:
            changed = True
            met.add("before-em-dash")
            return usj.substituted(content, edits)
        return content

    def inline(content: Content, *, separate: bool = True) -> Content:
        result: Content = []
        run: Content = []
        after = ""
        for item in content:
            if isinstance(item, dict) and (
                item["type"] == "verse"
                or usj.is_label(item)
                or item.get("marker") in ("wg", "wh")
            ):
                result += rewrite(run, after) if separate else run
                run = []
                result.append(item)
                after = FOREIGN if item.get("marker") in ("wg", "wh") else ""
                continue
            if isinstance(item, dict) and "content" in item:
                # Character styles share their parent's words. Rewrite their
                # children first to find notes and protected spans within them.
                item = {
                    **item,
                    "content": inline(item["content"], separate=item["type"] == "note"),
                }
            run.append(item)
        return result + (rewrite(run, after) if separate else run)

    result = usj.with_content(doc, inline)
    if changed:
        _check_lemmas(doc, result)
    return result


def _check_lemmas(before: Document, after: Document) -> None:
    """Refuse a lemma its verse had before a change and no longer has."""

    def lemmas(note: Node) -> list[str]:
        return [
            scripture.plain(usj.text_of(item["content"])).removesuffix(":")
            for item in usj.walk(note["content"])
            if usj.is_type(item, "char", "fq")
        ]

    old = scripture.verses(before)
    for reference, verse in scripture.verses(after).items():
        was, words = scripture.plain(old[reference].text), scripture.plain(verse.text)
        for (_, then), (_, now) in zip(old[reference].notes, verse.notes):
            for quoted, kept in zip(lemmas(then), lemmas(now)):
                if quoted in was and kept not in words:
                    raise CheckFailed(
                        "Punctuation leaves a lemma its verse no longer has: "
                        f"{usj.book_code(after)} {reference}: {kept}"
                    )


def revised(
    code: str,
    doc: Document,
    policy: bible.policy.Policy,
    met: MetRevisions,
) -> Document:
    """A book with the changes the file declares for its verses. A verse's
    words give way where they stand, in the styles they stand in, and the
    lemma of a note of the verse that quotes them changes with them. A lemma
    that quotes them in part would be left as the verse no longer reads, so
    it is refused."""
    changes = [c for c in verse_changes(policy) if c["verse"].split()[0] == code]
    if not changes:
        return doc
    verses = scripture.verses(doc)
    edits = []
    for change in changes:
        key = change["verse"]
        reference = key.split()[1]
        require(reference in verses, f"Revision of a verse the edition lacks: {key}")
        verse = verses[reference]
        old = change["from"]
        require(
            verse.text.count(old) == 1,
            f"Revision not met once in its verse: {key}: {old}",
        )
        start, end, new = _edit(verse.text.index(old), old, change["to"])
        # New words take the style of the first words they replace, so words
        # set across a style or a note would lose it; words only deleted
        # lose nothing.
        index, local = verse.part_at(start, at_end=start == end)
        block, lo, hi, _ = verse.parts[index]
        strings = usj.leaves(doc["content"][block]["content"][lo:hi])
        require(
            not new
            or sum(a < local + end - start and local < b for a, b in strings) <= 1,
            f"Revision across a style or note: {key}: {old}",
        )
        edits.append((verse, start, end, new, change))
        met.add(key)
    # Two groups may revise one verse, but not the same words of it.
    stretches = sorted((verse.reference, start, end) for verse, start, end, *_ in edits)
    for one, other in zip(stretches, stretches[1:]):
        require(
            one[0] != other[0] or (one[2] <= other[1] and one != other),
            f"Revisions of the same words: {code} {one[0]}",
        )
    doc = scripture.rewritten(
        doc, [(verse, start, end, new) for verse, start, end, new, _ in edits]
    )
    if not any(verse.notes for verse, *_ in edits):
        return doc
    # The notes of a revised verse, by the verse they stand in.
    revised_notes: dict[str, list[RevisionChange]] = {}
    for verse, _, _, _, change in edits:
        revised_notes.setdefault(verse.reference, []).append(change)
    verses = scripture.verses(doc)
    replacements: dict[int, Node] = {}
    for reference, listed in revised_notes.items():
        words = scripture.plain(verses[reference].text)

        def lemma(item: Node) -> Node:
            if not usj.is_type(item, "char", "fq"):
                return item
            content = item["content"]
            for change in listed:
                content = _rewritten(
                    content,
                    re.compile(re.escape(change["from"])),
                    lambda match: change["to"],
                )
            quoted = scripture.plain(usj.text_of(content)).removesuffix(":")
            require(
                quoted in words,
                "Revision leaves a lemma its verse no longer has: "
                f"{code} {reference}: {quoted}",
            )
            return {**item, "content": content}

        for _, note in verses[reference].notes:
            replacements[id(note)] = {
                **note,
                "content": usj.mapped(note["content"], lemma),
            }

    def swap(content: Content) -> Content:
        return [
            (
                replacements.get(id(item), item)
                if isinstance(item, dict) and item["type"] == "note"
                else (
                    {**item, "content": swap(item["content"])}
                    if isinstance(item, dict) and "content" in item
                    else item
                )
            )
            for item in content
        ]

    return usj.with_content(doc, swap)


def check_met(
    policy: bible.policy.Policy, met: AbstractSet[str | tuple[str, str | None]]
) -> None:
    data = policy.revisions
    verses = {change["verse"] for change in verse_changes(policy)}
    passages = {(_selector(c), c["from"]) for c in passage_changes(policy)}
    unused = sorted(
        (set(data["words"]) | verses | set(data["punctuation"]) | passages) - met,
        key=str,
    )
    require(not unused, f"Revisions that nothing prints: {unused}")
