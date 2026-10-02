"""The edition's revision of the translation's spelling and punctuation
(edition/revisions.json), along the lines of the New Cambridge Paragraph Bible.

Two kinds of change are declared, each with its reason:

    words    a word respelt wherever it is printed as a whole word: in the
             translation, its notes, and the front and back matter
    verses   changes to the words of single verses, each naming its verse,
             as "EZK 1:3", which must have the words once: its punctuation,
             or a spelling particular to it. They stand in groups, by the
             reason they share

The revision is made last, to the edition as prepared, so that the sources
are read, and every other decision is met, in the sources' own words. A
change that nothing meets is refused.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from collections.abc import Set as AbstractSet

import bible.policy
from bible import repairs, scripture, usj
from bible.checks import require, require_fields
from bible.policy_schema import RevisionChange
from bible.usj import Content, Document, Node


def check(policy: bible.policy.Policy) -> None:
    data = policy.revisions
    require_fields(data, {"why", "words", "verses"}, (), "Revisions file")
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
            require(
                change["from"]
                and change["from"] != change["to"]
                and change.get("why", True),
                f"Revision that changes nothing, or with an empty why: {name}: {key}",
            )


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


def respelt(doc: Document, policy: bible.policy.Policy, met: set[str]) -> Document:
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


def revised(
    code: str, doc: Document, policy: bible.policy.Policy, met: set[str]
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
    unused = sorted((set(data["words"]) | verses) - met)
    require(not unused, f"Revisions that nothing prints: {unused}")
