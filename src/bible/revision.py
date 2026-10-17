"""The edition's revision of the translation's spelling, vocabulary and
punctuation (edition/revisions.json), by explicit editorial decisions.

Five kinds of change are declared, each with its reason:

    names    a proper name respelt where its bearer is decided: every
             whole-word occurrence of a form in the verses its decision
             lists, and in the lemmas of their notes. Every other verse of
             the printed books that has the form is listed as keeping it,
             with who keeps it, so that each form prints only where a
             decision says
    words    a word respelt or modernized wherever it is printed as a whole
             word: in the translation, its notes, and front and back matter,
             or, with a scope of "scripture", in a book's verses and the
             lemmas and readings of their notes alone, preserving source
             prose's grammar. A word may except phrases it stands in, which
             spelling leaves as they are, though the grammar of scripture
             still revises their other words. Words that a character style
             divides are not joined, divided or re-divided, and nor are
             they in the lemma that quotes them
    passages punctuation in a keyed note or front/back-matter paragraph,
             and lowercase word initials in a keyed note's fragments,
             or Greek/Hebrew spelling in Old Testament notes and matter
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

import functools
import re
import unicodedata
from collections.abc import Callable, Container, Iterable
from difflib import SequenceMatcher

import bible.policy
from bible import assembly, notes, repairs, scripture, usfm, usj
from bible.checks import CheckFailed, require, require_fields
from bible.policy_schema import RevisionChange, WordingChange
from bible.references import book_of
from bible.usj import Content, Document, Node, Predicate

# What revision has met: a word, verse or punctuation rule by its key, a
# passage change by its selector and words, a word confined to notes by the
# note's key and the word, a phrase a word excepts by the word and the
# phrase, and a name respelt or kept by its verse and form.
type MetRevisions = set[str | tuple[str, ...]]
# The words to revise, letter by letter; an empty key ends a word.
type Trie = dict[str, "Trie"]

# What scoped grammar does not read among the words: notes, labels, the
# fields that quote or cite, and foreign words.
UNREVISED = frozenset("xt fl fq fqa wg wh".split())

# A word or phrase revised, or excepted: whole words, and what joins them.
WORD = re.compile(r"\w(?:[\w’', -]*\w)?")


def _unrevised(item: Node) -> bool:
    return usj.is_note(item) or usj.is_label(item) or item.get("marker") in UNREVISED


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
        {"why", "words", "verses", "passages", "punctuation", "names"},
        (),
        "Revisions file",
    )
    for name, rule in data["punctuation"].items():
        require(name in RULES or name == BRACKETS, f"Unknown punctuation rule: {name}")
        require_fields(rule, {"why"}, (), f"Punctuation rule {name}")
        require(bool(rule["why"]), f"Punctuation rule without a why: {name}")
    words = data["words"]
    everywhere = {word for word, entry in words.items() if "scope" not in entry}
    for word, entry in words.items():
        require_fields(
            entry, {"to", "why"}, {"scope", "notes", "except"}, f"Respelling of {word}"
        )
        require(
            entry.get("scope", "scripture") == "scripture",
            f"Respelling with a scope that is not scripture: {word}",
        )
        # Spelling alone excepts. An excepted phrase holds its word whole and
        # no other word respelt wherever it is printed, which it would leave
        # unrevised, so no other word excepts it.
        require(
            "except" not in entry
            or (
                "scope" not in entry
                and bool(entry["except"])
                and len(set(entry["except"])) == len(entry["except"])
                and all(
                    phrase not in words
                    and WORD.fullmatch(phrase) is not None
                    and _spans(phrase) & everywhere == {word}
                    for phrase in entry["except"]
                )
            ),
            f"Invalid exception to a respelling: {word}",
        )
        require(
            "notes" not in entry
            or (
                entry.get("scope") == "scripture"
                and bool(entry["notes"])
                and len(set(entry["notes"])) == len(entry["notes"])
                and all(
                    re.fullmatch(r"\w{3} \S+:\S+(?: .+)?", key) is not None
                    for key in entry["notes"]
                )
            ),
            f"Invalid note context for grammar revision: {word}",
        )
        require(
            WORD.fullmatch(word) is not None,
            f"Respelling of what is not a word: {word}",
        )
        require(
            entry["to"] and entry["to"] != word and entry["why"],
            f"Respelling that changes nothing, or without a why: {word}",
        )
    names = data["names"]
    require_fields(names, {"why", "decisions"}, (), "Names")
    require(bool(names["why"]), "Names without a why")
    owners: dict[str, str] = {}
    for bearer, decision in names["decisions"].items():
        require_fields(
            decision, {"to", "why", "forms"}, {"keep"}, f"Name decision {bearer}"
        )
        require(
            bool(decision["to"]) and bool(decision["why"]) and bool(decision["forms"]),
            f"Name decision without a target, a why or a form: {bearer}",
        )
        listed: dict[str, set[str]] = {}
        for form, keys in decision["forms"].items():
            require(
                WORD.fullmatch(form) is not None and form != decision["to"],
                f"Name decision of what is not a word, or that changes nothing: {form}",
            )
            # One decision owns a form.
            require(form not in owners, f"Name decided for two bearers: {form}")
            owners[form] = bearer
            _check_name_verses(
                keys, listed.setdefault(form, set()), f"{bearer}: {form}"
            )
        for kept in decision.get("keep", ()):
            require_fields(kept, {"form", "who", "verses"}, (), f"Kept name {bearer}")
            require(
                kept["form"] in decision["forms"] and bool(kept["who"]),
                f"Kept name without its decision, or without who keeps it: {bearer}",
            )
            _check_name_verses(
                kept["verses"], listed[kept["form"]], f"{bearer}: {kept['form']}"
            )
    # No word respells a name behind its decision's back, or prints one where
    # no decision says, alone or in a phrase: a word applies wherever it is
    # printed.
    for word, entry in words.items():
        spanned = sorted((_spans(word) | _spans(entry["to"])) & owners.keys())
        require(
            not spanned, f"Name also respelt as a word: {word}: {', '.join(spanned)}"
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
                key[:3] not in policy.kjv_units
                or punctuation_only(change["from"], change["to"]),
                f"Revision changes New Testament words: {name}: {key}",
            )
            require(
                change["from"]
                and change["from"] != change["to"]
                and change.get("why", True),
                f"Revision that changes nothing, or with an empty why: {name}: {key}",
            )

    # The front and back matter that prints: a unit read only for what it
    # sends to the books, as Brenton's Appendix, is never revised as a unit,
    # and its notes are revised at their verses, by their keys.
    matter = {e["id"] for e in policy.entries if "file" not in e and "section" not in e}
    # Brenton's units, and the files their notes are keyed by: Daniel's
    # include those of Susanna and Bel.
    brenton = [e for e in policy.entries if e.get("source") == "brenton"]
    brenton_units = {e["id"] for e in brenton}
    brenton_files = {code for e in brenton for code in assembly.source_codes(e)}
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
                {"note", "unit", "why", "spelling"},
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
            if "spelling" in passage_change:
                spelling = passage_change["spelling"]
                require(
                    spelling in {"greek", "hebrew"},
                    f"Unknown passage spelling: {selector}: {spelling}",
                )
                require(
                    (
                        selector.split()[0] in brenton_files
                        if "note" in passage_change
                        else selector in brenton_units
                    ),
                    f"Foreign spelling is not Old Testament matter or a note: {selector}",
                )
                old, new = passage_change["from"], passage_change["to"]
                masked = _foreign_mask(old, spelling)
                require(
                    "\0" not in old + new
                    and masked != old
                    and masked == _foreign_mask(new, spelling),
                    f"Foreign spelling changes other words, spacing or punctuation: {selector}",
                )
                require(
                    new == unicodedata.normalize("NFC", new),
                    f"Foreign spelling is not in composed form: {selector}",
                )
                require(
                    all(
                        _one_letter_apart(a, b)
                        for a, b in zip(
                            _foreign_words(old, spelling),
                            _foreign_words(new, spelling),
                            strict=True,
                        )
                    ),
                    f"Foreign spelling changes more than one letter of a word: {selector}",
                )
                continue
            require(
                re.fullmatch(
                    r"[\w\s.,;:?!—–\-()'’‘\"“”\[\]]*",
                    passage_change["from"] + passage_change["to"],
                )
                is not None,
                f"Passage revision is not plain punctuation: {selector}",
            )
            require(
                _same_words(
                    passage_change["from"],
                    passage_change["to"],
                    note="note" in passage_change,
                ),
                f"Passage revision changes wording or noninitial capitalization: {selector}",
            )


def _check_name_verses(keys: Iterable[str], seen: set[str], label: str) -> None:
    """Verses a name decision lists: each once, for its form, across the
    verses that respell it and the verses that keep it."""
    keys = tuple(keys)
    require(bool(keys), f"Name decision without a verse: {label}")
    for key in keys:
        require(
            re.fullmatch(r"\w{3} \S+:\S+", key) is not None,
            f"Name decision for what is not a verse: {label}: {key}",
        )
        require(key not in seen, f"Verse listed twice for a name: {label}: {key}")
        seen.add(key)


def _foreign_mask(text: str, spelling: str) -> str:
    """One token per foreign word, retaining every other character exactly.

    Marks belong to a preceding foreign letter. A bare mark, punctuation,
    spaces and letters of another script cannot be changed as spelling.
    """
    return _foreign_scan(text, spelling)[0]


def _foreign_words(text: str, spelling: str) -> list[str]:
    """The foreign words in order, as _foreign_mask reads them."""
    return _foreign_scan(text, spelling)[1]


def _foreign_scan(text: str, spelling: str) -> tuple[str, list[str]]:
    result: list[str] = []
    words: list[str] = []
    inside = False
    for char in text:
        name = unicodedata.name(char, "")
        foreign = name.startswith(spelling.upper() + " ")
        category = unicodedata.category(char)
        if foreign and category.startswith("L"):
            if not inside:
                result.append("\0" + spelling + "\0")
                words.append("")
            words[-1] += char
            inside = True
        elif (
            inside
            and category.startswith("M")
            and (foreign or name.startswith("COMBINING "))
        ):
            words[-1] += char
        else:
            result.append(char)
            inside = False
    return "".join(result), words


def _one_letter_apart(old: str, new: str) -> bool:
    """Whether two words differ in their marks and at most one letter."""
    a, b = (
        "".join(
            c
            for c in unicodedata.normalize("NFD", word)
            if not unicodedata.category(c).startswith("M")
        )
        for word in (old, new)
    )
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) <= 1
    short, long = sorted((a, b), key=len)
    return len(long) == len(short) + 1 and any(
        long[:i] + long[i + 1 :] == short for i in range(len(long))
    )


def _starts_word(text: str, at: int, spelling: str) -> bool:
    """Whether a foreign word begins at the offset, as _foreign_mask reads it."""
    before = _foreign_mask(text[:at], spelling)
    return _foreign_mask(text[: at + 1], spelling) == before + f"\0{spelling}\0"


def _same_words(old: str, new: str, *, note: bool = False) -> bool:
    """Keep lexical tokens and internal case. Keyed notes may lower a word's
    initial; other capitalization must begin a sentence."""
    # A separator between whole numbers is punctuation, not a word's hyphen.
    old, new = (
        re.sub(r"(?<!\w)(\d+)-(\d+)(?!\w)", r"\1–\2", text) for text in (old, new)
    )
    pattern = r"\w+(?:[-'’]\w+)*"
    before, after = list(re.finditer(pattern, old)), list(re.finditer(pattern, new))
    return len(before) == len(after) and all(
        a[0] == b[0]
        or (note and a[0][:1].isupper() and b[0] == a[0][:1].lower() + a[0][1:])
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
    """Revise a keyed note or one paragraph, keeping its words and metadata,
    but for the Greek or Hebrew words a spelling change respells.

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
    spellings: dict[int, set[str]] = {}
    brenton = any(
        e["id"] == code and e.get("source") == "brenton" for e in policy.entries
    )
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
        after = words[:at] + new + words[at + len(old) :]
        spelling = change.get("spelling")
        if spelling:
            require(
                brenton,
                f"Foreign spelling applied outside Old Testament: {code}: {selector}",
            )
            spellings.setdefault(id(content), set()).add(spelling)
            require(
                _foreign_mask(words, spelling) == _foreign_mask(after, spelling),
                "Foreign spelling changes other words, spacing or punctuation: "
                f"{selector}: {old}",
            )
        else:
            require(
                _same_words(words, after, note="note" in change),
                "Passage revision changes wording or noninitial capitalization: "
                f"{selector}: {old}",
            )
        spans = ranges.setdefault(id(content), [])
        require(
            all(at + len(old) <= start or end <= at for start, end in spans),
            f"Overlapping passage revisions: {selector}: {old}",
        )
        spans.append((at, at + len(old)))
        # Only changed characters give way; unchanged words retain their styles.
        for tag, a, b, c, d in SequenceMatcher(
            None, old, new, autojunk=False
        ).get_opcodes():
            if tag == "equal":
                continue
            edit = (at + a, at + b, new[c:d])
            # An edit of no stretch adds to the string before it: letters set
            # before a word go with the word's first, to stand in its style.
            if spelling and a == b < len(old) and _starts_word(words, at + a, spelling):
                edit = (at + a, at + a + 1, new[c:d] + old[a])
            edits.setdefault(id(content), []).append(edit)
        met.add((selector, old))
    if not edits:
        return doc

    note_contents = {id(content) for key, content in targets if key is not None}

    def rewrite(content: Content) -> Content:
        revised = content
        if id(content) in edits:
            revised = usj.substituted(content, edits[id(content)], skip=skip)
            before_words = usj.text_of(content, skip=skip)
            after_words = usj.text_of(revised, skip=skip)
            for spelling in spellings.get(id(content), ()):
                before_words = _foreign_mask(before_words, spelling)
                after_words = _foreign_mask(after_words, spelling)
            require(
                _same_words(
                    before_words, after_words, note=id(content) in note_contents
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


def _style_runs(
    content: Content, *, skip: Predicate = usj.is_note
) -> list[tuple[int, int]]:
    """Runs with the same character styles, ignoring notes and string seams."""
    runs: list[tuple[int, int]] = []
    previous: tuple[str, ...] | None = None
    at = 0

    def visit(items: Content, styles: tuple[str, ...] = ()) -> None:
        nonlocal at, previous
        for item in items:
            if isinstance(item, str):
                end = at + len(item)
                if item:
                    if styles == previous:
                        runs[-1] = (runs[-1][0], end)
                    else:
                        runs.append((at, end))
                    previous = styles
                at = end
            elif "content" in item and not skip(item):
                inner = (*styles, item["marker"]) if item["type"] == "char" else styles
                visit(item["content"], inner)

    visit(content)
    return runs


def _separators(words: str) -> list[str]:
    """What divides words: spaces and hyphens."""
    return re.findall(r"[\s\-]+", words)


def _keeps_styles(
    match: re.Match[str],
    replacement: str,
    runs: Callable[[], list[tuple[int, int]]],
) -> bool:
    """Whether a replacement keeps the character styles of the words it
    replaces: it respells each word in place, or the words stand in one
    style. Joining, dividing or re-dividing words that a style divides would
    erase the distinction, so such words are left as they are. Notes and
    adjacent strings alone do not divide them."""
    return _separators(match[0]) == _separators(replacement) or any(
        a <= match.start() and match.end() <= b for a, b in runs()
    )


def _rewritten(
    content: Content,
    pattern: re.Pattern[str],
    new: Callable[[re.Match[str]], str],
    *,
    skip: Predicate = usj.is_note,
    done: Callable[[re.Match[str]], object] | None = None,
) -> Content:
    """Content with every match of a pattern in its words giving way to what
    new makes of it, and done told of each match that gives way. The words
    are read as one, whatever styles divide them, unless the replacement
    would not keep the styles; a note's words are its own, not those of the
    content it stands in."""
    edits: list[tuple[int, int, str]] = []
    runs = functools.cache(lambda: _style_runs(content, skip=skip))
    for match in pattern.finditer(usj.text_of(content, skip=skip)):
        replacement = new(match)
        if replacement == match[0] or not _keeps_styles(match, replacement, runs):
            continue
        if _separators(match[0]) == _separators(replacement):
            # Contextual decisions can change several words. Keep each word
            # in its own inline style rather than moving the whole phrase
            # into one.
            before = re.finditer(r"\S+", match[0])
            after = re.finditer(r"\S+", replacement)
            edits.extend(
                _edit(match.start() + old.start(), old[0], changed[0])
                for old, changed in zip(before, after)
                if old[0] != changed[0]
            )
        else:
            edits.append(_edit(match.start(), match[0], replacement))
        if done is not None:
            done(match)
    return usj.substituted(content, edits, skip=skip) if edits else content


def _words(words: Iterable[str]) -> re.Pattern[str]:
    """The whole words given, the longest at a place first, in one pattern."""
    return _pattern(tuple(words))


@functools.cache
def _pattern(words: tuple[str, ...]) -> re.Pattern[str]:
    """The words set out as a trie, so that the text is scanned once however
    many there are: a plain alternation of a thousand words tries each of them
    at every letter, ten times slower on the whole edition. Each document is
    respelt with the same few sets of words, so each trie is built once."""
    trie: Trie = {}
    for word in words:
        node = trie
        for char in word:
            node = node.setdefault(char, {})
        node[""] = {}
    if not trie:
        return re.compile(r"(?!)")
    return re.compile(r"(?<!\w)" + _branches(trie) + r"(?!\w)")


def _branches(trie: Trie) -> str:
    """A trie as a regular expression. A longer word is tried before a
    shorter one it begins with, as the ending is optional and greedy."""
    ends = "" in trie
    alternatives = [
        re.escape(char) + _branches(node) for char, node in trie.items() if char
    ]
    if not alternatives:
        return ""
    group = (
        alternatives[0] if len(alternatives) == 1 else f"(?:{'|'.join(alternatives)})"
    )
    return f"(?:{group})?" if ends else group


@functools.cache
def _phrase(words: str) -> re.Pattern[str]:
    """The words given, not as part of a longer word: an edge that is a
    letter or digit must not run on into another. A space among them is a
    space or the line break that sets verse in lines."""
    return re.compile(
        (r"(?<!\w)" if re.match(r"\w", words) else "")
        + re.escape(words).replace("\\ ", "[ \n]")
        + (r"(?!\w)" if re.search(r"\w$", words) else "")
    )


def _spans(phrase: str) -> set[str]:
    """Every run of whole words in a phrase: what a word revised in it
    would match."""
    starts = [match.start() for match in re.finditer(r"(?<!\w)\w", phrase)]
    ends = [match.end() for match in re.finditer(r"\w(?!\w)", phrase)]
    return {phrase[start:end] for start in starts for end in ends if start < end}


def exceptions(policy: bible.policy.Policy) -> dict[str, str]:
    """The phrases the words except, each with the word it holds."""
    return {
        phrase: word
        for word, entry in policy.revisions["words"].items()
        for phrase in entry.get("except", ())
    }


def respelt(
    doc: Document,
    policy: bible.policy.Policy,
    met: MetRevisions,
    *,
    book: bool = True,
) -> Document:
    """Spell first, then revise grammar in scripture; the names come before
    both (named).

    Each pass is one longest-match sweep. Spelling, vocabulary and participle
    changes apply wherever a word is printed, source prose included. Grammar,
    the words scoped to scripture, applies to a book's verses alone: their
    words, and the lemmas (fq) and readings (fqa) of the notes set in them. A
    verse runs to the next verse number, or to the end of its book. The titles,
    headings and introductions it spans keep their grammar, and so do the
    notes set in them, whose lemmas quote them. Plain quotation marks do not
    establish scope.
    """
    words = policy.revisions["words"]
    excepted = exceptions(policy)
    changed = False

    def to(match: re.Match[str]) -> str:
        return words[match[0]]["to"]

    def done(match: re.Match[str], key: str | None = None) -> None:
        # A word is met where it is changed, not where a style keeps it.
        nonlocal changed
        changed = True
        met.add(match[0])
        if key is not None and "notes" in words[match[0]]:
            met.add((key, match[0]))

    def spelt(match: re.Match[str]) -> str:
        # A phrase a word excepts stands as it is, and is met for the word.
        if match[0] in excepted:
            met.add((excepted[match[0]], match[0]))
            return match[0]
        return to(match)

    spelling = _words(
        [word for word, entry in words.items() if "scope" not in entry] + list(excepted)
    )

    def spelt_note(
        items: Content, text: str, at: int, divided: list[tuple[int, int]]
    ) -> Content:
        """A note's words respelt. Its readings and commentary stand alone;
        its lemma, where it quotes the words at the note's place, keeps the
        compounds a style keeps divided there."""

        def lemmas(items: Content) -> Content:
            output: Content = []
            for item in items:
                if isinstance(item, dict) and "content" in item:
                    if item.get("marker") == "fq":
                        quoted = usj.text_of(item["content"]).rstrip(": ")
                        kept = (
                            [
                                (a - at, b - at)
                                for a, b in divided
                                if at <= a < b <= at + len(quoted)
                            ]
                            if text.startswith(quoted, at)
                            else []
                        )
                        inner = _rewritten(
                            item["content"],
                            spelling,
                            lambda match: (
                                match[0] if match.span() in kept else spelt(match)
                            ),
                            done=done,
                        )
                    else:
                        inner = lemmas(item["content"])
                    item = {**item, "content": inner}
                output.append(item)
            return output

        return _rewritten(
            lemmas(items),
            spelling,
            spelt,
            skip=lambda item: usj.is_note(item) or item.get("marker") == "fq",
            done=done,
        )

    def spelt_notes(segment: Content) -> Content:
        """A verse with its notes respelt, each read at its place."""
        text = usj.text_of(segment)
        runs = functools.cache(lambda: _style_runs(segment))
        divided = [
            match.span()
            for match in spelling.finditer(text)
            if match[0] in words
            and not _keeps_styles(match, words[match[0]]["to"], runs)
        ]
        at = 0

        def visit(items: Content) -> Content:
            nonlocal at
            output: Content = []
            for item in items:
                if isinstance(item, str):
                    at += len(item)
                elif usj.is_note(item):
                    item = {
                        **item,
                        "content": spelt_note(item["content"], text, at, divided),
                    }
                elif "content" in item:
                    item = {**item, "content": visit(item["content"])}
                output.append(item)
            return output

        return visit(segment)

    def spell(content: Content) -> Content:
        # Verse numbers separate neighboring verses. Notes have their own
        # words; inline styles do not interrupt a phrase.
        numbers = [i for i, item in enumerate(content) if usj.is_type(item, "verse")]
        starts, ends = [0, *(i + 1 for i in numbers)], [*numbers, len(content)]
        output: Content = []
        for start, end in zip(starts, ends):
            segment = content[start:end]
            if usj.notes_of(segment):
                segment = spelt_notes(segment)
            part = _rewritten(segment, spelling, spelt, done=done)
            output += part + content[end : end + 1]
        return output

    grammar = {word: entry for word, entry in words.items() if "scope" in entry}
    general = _words(word for word, entry in grammar.items() if "notes" not in entry)
    # A word confined to some notes is revised in their lemmas and readings.
    confined = {
        key: _words(
            word for word, entry in grammar.items() if key in entry.get("notes", (key,))
        )
        for entry in grammar.values()
        for key in entry.get("notes", ())
    }

    def quoted(content: Content, key: str | None = None) -> Content:
        output: Content = []
        for item in content:
            if isinstance(item, dict) and "content" in item:
                if item.get("marker") in {"fq", "fqa"}:
                    inner = _rewritten(
                        item["content"],
                        confined.get(key, general) if key is not None else general,
                        to,
                        skip=_unrevised,
                        done=lambda match: done(match, key),
                    )
                else:
                    inner = quoted(item["content"], item.get("x-key", key))
                item = {**item, "content": inner}
            output.append(item)
        return output

    def scoped(doc: Document) -> list[Node]:
        # Exclude the prose of titles and introductions, wherever they stand,
        # while keeping numbered scripture in d paragraphs (including Psalm
        # superscriptions).
        parts: dict[int, list[tuple[int, int]]] = {}
        for verse in scripture.verses(doc).values():
            for block_index, lo, hi, _ in verse.parts:
                parts.setdefault(block_index, []).append((lo, hi))
        blocks = []
        for index, block in enumerate(doc["content"]):
            if index in parts and not prose(block.get("marker", "")):
                content = block["content"]
                output: Content = []
                at = 0
                for lo, hi in parts[index]:
                    output += content[at:lo]
                    output += quoted(
                        _rewritten(
                            content[lo:hi], general, to, skip=_unrevised, done=done
                        )
                    )
                    at = hi
                output += content[at:]
                block = {**block, "content": output}
            blocks.append(block)
        return blocks

    result = usj.with_content(doc, spell)
    if book and grammar:
        result = usj.with_blocks(result, scoped(result))
    if changed:
        _check_lemmas(doc, result)
    return result


def prose(marker: str) -> bool:
    """Whether a paragraph keeps its source grammar though a verse spans it:
    a book's titles and its introduction. Headings are no part of a verse."""
    return marker in usj.BOOK_PARAGRAPHS or marker.startswith("i")


# The source quotations have not yet been tagged for their fonts. Recognize
# their letters too, and the stops that close them, so that their punctuation
# is not revised as English.
FOREIGN_END = re.compile(f"[{usfm.GREEK}{usfm.HEBREW}][{usfm.COMBINING}]*[.?!]*$")
# The systematic rules, each a pattern over a unit's English, in the order
# they apply: a run of commas, colons and semicolons duplicates the break an
# em dash or a parenthesis marks. Inside closing parentheses the run moves
# after the last, or goes when a dash follows; before a dash or an opening
# parenthesis it goes. The move comes first, so that a run it sets before a
# dash or a parenthesis goes too, and a second pass changes nothing. A
# period, question mark or exclamation mark inside a parenthesis ends the
# parenthesis's own sentence, and stays.
RULES: dict[str, re.Pattern[str]] = {
    "inside-parenthesis": re.compile(r"([,;:]+)\)+(—?)"),
    "before-em-dash": re.compile(r"[,;:]+(?=—)"),
    "before-parenthesis": re.compile(r"[,;:]+(?=\s?\()"),
}
# A run that ends a verse, before a verse that opens a parenthesis.
VERSE_END = re.compile(r"[,;:]+(?=\s*$)")
# The rule that drops Brenton's square brackets from a book's text. Not a
# pattern over a unit's English like RULES: a note's brackets, and the
# appendix of readings' around a former reading, are not scripture text and
# stay, so the rule reads a book's paragraphs alone (unbracketed).
BRACKETS = "brackets"
# A bracket between two letters, which dropping it would join.
INSIDE_WORD = re.compile(r"\w[\[\]]+\w")
# What the rules do not understand, and refuse: a mark already standing where
# a run would move, unless a dash follows to clear it; the comma of the "Or,"
# that opens a note's alternative; and the separator before an item's label,
# as "(1)" or "(a)".
FOLLOWING = re.compile(r"(?![,;:]*—)[,;:.?!]")
ALTERNATIVE = re.compile(r"(?<!\w)Or$")
ITEM = re.compile(r"\s?\((?:\d+|[a-z])\)")
# What a tagged foreign word or a label stands as in the English it interrupts.
FOREIGN, LABEL = "\1", "\0"


def _english(content: Content) -> str:
    parts = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif "content" in item and not usj.is_note(item):
            words = _english(item["content"])
            parts.append(
                FOREIGN * len(words)
                if item.get("marker") in ("wg", "wh")
                else LABEL * len(words) if usj.is_label(item) else words
            )
    return "".join(parts)


def _revisable(text: str, match: re.Match[str], doc: Document) -> bool:
    """Whether marks matched in a unit's English are to be revised. Marks
    after a tagged foreign word are refused, as they may be the foreign
    text's own; those after an untagged Greek or Hebrew quotation are left."""
    if text[match.start() - 1 : match.start()] == FOREIGN:
        raise CheckFailed(
            "Punctuation revised after a tagged foreign word: "
            f"{usj.book_code(doc)}: {text[match.start() : match.start() + 30]}"
        )
    return not FOREIGN_END.search(text, 0, match.start())


def _understood(name: str, text: str, match: re.Match[str], doc: Document) -> None:
    """Refuse marks that a rule would revise without understanding them."""
    if name == "inside-parenthesis":
        refused = not match[2] and bool(FOLLOWING.match(text, match.end()))
    else:
        refused = name == "before-parenthesis" and bool(
            ALTERNATIVE.search(text, 0, match.start()) or ITEM.match(text, match.end())
        )
    if refused:
        raise CheckFailed(
            f"Punctuation {name} not understood, to be decided: "
            f"{usj.book_code(doc)}: {text[max(0, match.start() - 30) : match.end() + 10]}"
        )


def _between(doc: Document, start: int, end: int, verse: str) -> None:
    """Refuse a join of lines across a heading, or onto an introduction."""
    blocks = doc["content"]
    if any(
        blocks[i].get("marker") in usj.HEADINGS for i in range(start + 1, end)
    ) or prose(blocks[end].get("marker", "")):
        raise CheckFailed(
            "Punctuation before-parenthesis across a heading or introduction, "
            f"to be decided: {usj.book_code(doc)} {verse}"
        )


def _joined(doc: Document, met: MetRevisions) -> Document:
    """The document with the run of marks that ends a verse removed where the
    next verse opens a parenthesis, or the parenthesis opens the next line
    of the same verse. Read protected words at verse offsets, and delete only
    the marks, preserving the lines and their notes."""
    verses = list(scripture.verses(doc).values())
    edits = []
    texts = [
        "\n".join(
            _english(doc["content"][block]["content"][lo:hi])
            for block, lo, hi, _ in verse.parts
        )
        for verse in verses
    ]
    for index, (verse, text) in enumerate(zip(verses, texts)):
        matches = []
        for match in re.finditer(r"[,;:]+(?=\n\s*\()", text):
            line = text.count("\n", 0, match.end())
            _between(
                doc, verse.parts[line][0], verse.parts[line + 1][0], verse.reference
            )
            matches.append(match)
        if index + 1 < len(verses) and texts[index + 1].lstrip().startswith("("):
            end = VERSE_END.search(text)
            if end is not None:
                # A chapter may stand between, as a sentence runs across it.
                following = verses[index + 1]
                _between(
                    doc, verse.parts[-1][0], following.parts[0][0], following.reference
                )
                matches.append(end)
        for match in matches:
            if _revisable(text, match, doc):
                _understood("before-parenthesis", text, match, doc)
                edits.append((verse, match.start(), match.end(), ""))
    if not edits:
        return doc
    met.add("before-parenthesis")
    return scripture.rewritten(doc, edits)


def punctuated(
    doc: Document, policy: bible.policy.Policy, met: MetRevisions
) -> Document:
    """Regularize English punctuation across styles, within each text unit.

    Notes have their own words; verses, labels and foreign styles interrupt
    a unit. The dash and the parenthesis keep their style because only the
    punctuation beside them changes. Punctuation after a tagged foreign word
    is refused, as it may be the foreign text's own, and so is a change that
    leaves a lemma its verse no longer has.
    """
    rules = [name for name in RULES if name in policy.revisions["punctuation"]]
    if not rules:
        return doc
    changed = False

    def rewrite(content: Content, after: str = "") -> Content:
        nonlocal changed
        # Each rule reads what the one before it left.
        for name in rules:
            text = after + _english(content)
            edits = []
            for match in RULES[name].finditer(text, len(after)):
                if not _revisable(text, match, doc):
                    continue
                _understood(name, text, match, doc)
                start, end = match.start() - len(after), match.end() - len(after)
                if name == "inside-parenthesis":
                    # Move only the marks: replacing the whole match would
                    # pull the parenthesis into the marks' character style.
                    edits.append((start, start + len(match[1]), ""))
                    if not match[2]:
                        edits.append((end, end, match[1]))
                else:
                    edits.append((start, end, ""))
            if edits:
                changed = True
                met.add(name)
                content = usj.substituted(content, sorted(edits))
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
    # Across verses and lines, after the marks have moved out of parentheses.
    if "before-parenthesis" in rules:
        joined = _joined(result, met)
        changed = changed or joined is not result
        result = joined
    if changed:
        _check_lemmas(doc, result)
    return result


def unbracketed(
    doc: Document, policy: bible.policy.Policy, met: MetRevisions
) -> Document:
    """A book without Brenton's square brackets around the Greek that the
    Hebrew lacks: the marks go from its paragraphs' text, and nothing else
    changes, since a bracket stands beside a space or a stop; one between
    two letters is refused. A note keeps its own. The brackets of a passage may
    close verses or a chapter later, so they must pair across the book, one
    passage at a time. (In a book the Hebrew lacks, the read stage has already
    taken them for supplied words.)"""
    if BRACKETS not in policy.revisions["punctuation"]:
        return doc
    code = usj.book_code(doc)
    opened = depth = 0

    def dropped(content: Content) -> Content:
        nonlocal opened, depth
        result: Content = []
        for item in content:
            if isinstance(item, str):
                for mark in item:
                    if mark in "[]":
                        depth += 1 if mark == "[" else -1
                        opened += mark == "["
                        require(0 <= depth <= 1, f"Brackets of {code} do not pair")
                inside = INSIDE_WORD.search(item)
                require(
                    inside is None,
                    f"Bracket of {code} between letters: {inside and inside[0]}",
                )
                item = item.replace("[", "").replace("]", "")
            elif "content" in item and not usj.is_note(item):
                item = {**item, "content": dropped(item["content"])}
            usj.extended(result, [item])
        return result

    result = usj.with_content(doc, dropped)
    require(depth == 0, f"Brackets of {code} do not pair: one is left open")
    if not opened:
        return doc
    met.add(BRACKETS)
    _check_lemmas(doc, result)
    return result


def _check_lemmas(before: Document, after: Document) -> None:
    """Refuse a lost lemma, preserving its whole-word edges when it had them."""

    def lemmas(note: Node) -> list[str]:
        return [
            scripture.plain(usj.text_of(item["content"])).removesuffix(":")
            for item in usj.walk(note["content"])
            if usj.is_type(item, "char", "fq")
        ]

    old = scripture.verses(before)
    for reference, verse in scripture.verses(after).items():
        # A verse whose words and notes the revision left alone keeps its lemmas.
        if old[reference].text == verse.text and old[reference].notes == verse.notes:
            continue
        was, words = scripture.plain(old[reference].text), scripture.plain(verse.text)
        for (at, then), (now_at, now) in zip(old[reference].notes, verse.notes):
            # Normalize the caller's offset without dropping its trailing space.
            start = len(scripture.plain(old[reference].text[:at] + "\0")) - 1
            now_start = len(scripture.plain(verse.text[:now_at] + "\0")) - 1
            for quoted, kept in zip(lemmas(then), lemmas(now)):
                if quoted not in was:
                    continue
                if _phrase(quoted).match(was, start):
                    lost = _phrase(kept).match(words, now_start) is None
                else:
                    lost = (
                        _phrase(kept).search(words) is None
                        if _phrase(quoted).search(was)
                        else kept not in words
                    )
                if lost:
                    raise CheckFailed(
                        "Revision leaves a lemma its verse no longer has: "
                        f"{usj.book_code(after)} {reference}: {kept}"
                    )


def regularized(doc: Document, policy: bible.policy.Policy) -> Document:
    """A document with the systematic spelling and punctuation alone,
    recording nothing: the appendix of readings quotes both Bibles so, to
    show the readings' differences and not the edition's finishing."""
    return punctuated(respelt(doc, policy, set()), policy, set())


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
    changes = [c for c in verse_changes(policy) if book_of(c["verse"]) == code]
    if not changes:
        return doc
    doc = _reworded(
        code,
        doc,
        [(c["verse"].split()[1], c["from"], c["to"]) for c in changes],
        every=False,
    )
    met.update(c["verse"] for c in changes)
    return doc


def _in_book(keys: Iterable[str], code: str) -> list[str]:
    """The references among the verse keys that are in a book."""
    return [key.split()[1] for key in keys if book_of(key) == code]


@functools.cache
def _names(forms: frozenset[str]) -> re.Pattern[str]:
    """The forms given, each as a phrase, the longest at a place first."""
    return re.compile(
        "|".join(
            _phrase(form).pattern
            for form in sorted(forms, key=lambda form: (-len(form), form))
        )
    )


def named(
    code: str,
    doc: Document,
    policy: bible.policy.Policy,
    met: MetRevisions,
) -> Document:
    """A book with its names respelt where their bearers are decided
    (revisions.json, names): every whole-word occurrence of a form in the
    verses its decision lists, in the styles it stands in, and in the lemmas
    of the notes that quote it. Every other verse that prints the form must
    be listed as keeping it, so that each form prints only where a decision
    says: an occurrence listed neither way is refused, and so is a listed
    verse without its form."""
    decisions = policy.revisions["names"]["decisions"]
    forms = frozenset(form for d in decisions.values() for form in d["forms"])
    if not forms:
        return doc
    changes: dict[tuple[str, str], str] = {}
    kept: set[tuple[str, str]] = set()
    for decision in decisions.values():
        for form, keys in decision["forms"].items():
            for reference in _in_book(keys, code):
                changes[reference, form] = decision["to"]
        for keeping in decision.get("keep", ()):
            for reference in _in_book(keeping["verses"], code):
                kept.add((reference, keeping["form"]))
    verses = scripture.verses(doc)
    pattern = _names(forms)
    # Where each form stands, by verse: a form within a longer one is the
    # longer one's.
    found: dict[tuple[str, str], list[int]] = {}
    for reference, verse in verses.items():
        for match in pattern.finditer(verse.text):
            form = re.sub(r"\s+", " ", match[0])
            require(
                (reference, form) in changes or (reference, form) in kept,
                f"Name without a decision: {code} {reference}: {form}",
            )
            found.setdefault((reference, form), []).append(match.start())
    for kind, listed in (("name", changes.keys()), ("kept", kept)):
        for reference, form in listed:
            require(
                (reference, form) in found, f"Name not met: {code} {reference}: {form}"
            )
            met.add((kind, f"{code} {reference}", form))
    # A form respelt within a longer one would splice the two decisions.
    for reference, form in changes:
        require(
            [m.start() for m in _phrase(form).finditer(verses[reference].text)]
            == found[reference, form],
            f"Name within another name: {code} {reference}: {form}",
        )
    if not changes:
        return doc
    return _reworded(
        code,
        doc,
        [(reference, form, to) for (reference, form), to in changes.items()],
        every=True,
        verses=verses,
    )


def check_kept(
    code: str, before: Document, after: Document, policy: bible.policy.Policy
) -> None:
    """Refuse a kept name that another revision respelt: each kept verse of a
    book as finished prints its form as often as the names left it."""
    kept = [
        (reference, keeping["form"])
        for decision in policy.revisions["names"]["decisions"].values()
        for keeping in decision.get("keep", ())
        for reference in _in_book(keeping["verses"], code)
    ]
    if not kept:
        return
    was, now = scripture.verses(before), scripture.verses(after)
    for reference, form in kept:
        counts = [
            (
                len(_phrase(form).findall(verses[reference].text))
                if reference in verses
                else 0
            )
            for verses in (was, now)
        ]
        require(
            counts[0] == counts[1], f"Kept name respelt: {code} {reference}: {form}"
        )


def _reworded(
    code: str,
    doc: Document,
    changes: list[tuple[str, str, str]],
    *,
    every: bool,
    verses: dict[str, scripture.Verse] | None = None,
) -> Document:
    """A book with words of its verses giving way to others: in each verse
    named, the words once, or every whole-word occurrence of them. They give
    way where they stand, in the styles they stand in, and the lemma of a
    note of the verse that quotes them changes with them. A lemma that quotes
    them in part would be left as the verse no longer reads, so it is
    refused. The verses are the document's, if already read."""
    if verses is None:
        verses = scripture.verses(doc)
    edits = []
    boundaries: dict[str, str] = {}
    for reference, old, to in changes:
        key = f"{code} {reference}"
        require(reference in verses, f"Revision of a verse the edition lacks: {key}")
        verse = verses[reference]
        found = list(_phrase(old).finditer(verse.text))
        require(
            bool(found) if every else len(found) == 1,
            f"Revision not met{'' if every else ' once'} in its verse: {key}: {old}",
        )
        for match in found:
            start, end, new = _edit(match.start(), old, to)
            # A stop inserted just after a replacement lemma belongs to the
            # scope the note declares, not to its printed lemma
            # (notes.boundary_stop). The lemma is plain, as the verse's line
            # breaks are not.
            if start == end and len(new) == 1 and new in notes.BOUNDARY_STOPS:
                for offset, note in verse.notes:
                    if note.get("category") != "edition":
                        continue
                    phrase = notes.lemma_of(note)
                    if phrase and scripture.plain(verse.text[offset:start]) == phrase:
                        boundaries[note["x-key"]] = new
            # New words take the style of the first words they replace, so
            # words set across a style or a note would lose it; words only
            # deleted lose nothing.
            index, local = verse.part_at(start, at_end=start == end)
            block, lo, hi, _ = verse.parts[index]
            strings = usj.leaves(doc["content"][block]["content"][lo:hi])
            require(
                not new
                or sum(a < local + end - start and local < b for a, b in strings) <= 1,
                f"Revision across a style or note: {key}: {old}",
            )
            edits.append((verse, start, end, new, (old, to)))
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
    # The words of a revised verse that changed, by the verse they stand in.
    revised_words: dict[str, list[tuple[str, str]]] = {}
    for verse, _, _, _, change in edits:
        changed = revised_words.setdefault(verse.reference, [])
        if change not in changed:
            changed.append(change)
    verses = scripture.verses(doc)
    replacements: dict[int, Node] = {}
    for reference, listed in revised_words.items():
        words = scripture.plain(verses[reference].text)
        phrases = [(_phrase(old), to) for old, to in listed]

        def lemma(item: Node) -> Node:
            if not usj.is_type(item, "char", "fq"):
                return item
            content = item["content"]
            for pattern, to in phrases:
                content = _rewritten(content, pattern, lambda match: to)
            quoted = scripture.plain(usj.text_of(content)).removesuffix(":")
            require(
                quoted in words,
                "Revision leaves a lemma its verse no longer has: "
                f"{code} {reference}: {quoted}",
            )
            return {**item, "content": content}

        for _, note in verses[reference].notes:
            changed_note: Node = {**note, "content": usj.mapped(note["content"], lemma)}
            if note.get("x-key") in boundaries:
                phrase = notes.lemma_of(changed_note)
                assert phrase is not None
                changed_note["x-scope"] = {
                    **note.get("x-scope", {}),
                    "declared": phrase + boundaries[note["x-key"]],
                }
            replacements[id(note)] = changed_note

    result = usj.replaced_by_identity(doc, replacements)
    check_revised_notes(code, doc, result)
    return result


def check_revised_notes(code: str, before: Document, after: Document) -> None:
    """A verse revision may change a note's lemma, and the scope declared for
    it, and nothing else: its readings, explanations, labels, witness and
    category are the source's or the editor's words, not the verse's."""

    def keyed(doc: Document) -> dict[str, Node]:
        return {n["x-key"]: n for n in usj.notes_of(doc["content"]) if "x-key" in n}

    def body(note: Node) -> Content:
        return [
            part
            for part in note["content"]
            if not usj.is_type(part, "char", "fr")
            and not usj.is_type(part, "char", "fq")
        ]

    was, now = keyed(before), keyed(after)
    require(was.keys() == now.keys(), f"Revision changed the notes of a book: {code}")
    for key, note in now.items():
        old = was[key]
        scope, former = note.get("x-scope", {}), old.get("x-scope", {})
        require(
            body(note) == body(old)
            and note.get("category") == old.get("category")
            and {k: v for k, v in scope.items() if k != "declared"}
            == {k: v for k, v in former.items() if k != "declared"}
            and (
                not former.get("declared")
                or scope.get("declared") == former["declared"]
            ),
            f"Revision changed a note's construction: {code} {key}",
        )


def check_met(policy: bible.policy.Policy, met: Container[object]) -> None:
    data = policy.revisions
    verses = {change["verse"] for change in verse_changes(policy)}
    passages = {(_selector(c), c["from"]) for c in passage_changes(policy)}
    notes = {
        (key, word)
        for word, entry in data["words"].items()
        for key in entry.get("notes", ())
    }
    excepted = {(word, phrase) for phrase, word in exceptions(policy).items()}
    names: set[str | tuple[str, ...]] = set()
    for decision in data["names"]["decisions"].values():
        names.update(
            ("name", key, form)
            for form, keys in decision["forms"].items()
            for key in keys
        )
        names.update(
            ("kept", key, kept["form"])
            for kept in decision.get("keep", ())
            for key in kept["verses"]
        )
    expected = (
        set(data["words"])
        | verses
        | set(data["punctuation"])
        | passages
        | notes
        | excepted
        | names
    )
    unused = sorted((key for key in expected if key not in met), key=str)
    require(not unused, f"Revisions that nothing prints: {unused}")
