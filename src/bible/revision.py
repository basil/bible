"""The edition's revision of the translation's spelling, vocabulary, and
punctuation (edition/revisions.json), by explicit editorial decisions.

Six kinds of change are declared, each with its reason:

    names    a proper name respelled where its bearer is decided: every
             whole-word occurrence of a form in the verses its decision
             lists, and in the lemmas of their notes. Every other verse of
             the printed books that has the form is listed as keeping it,
             with who keeps it, so that each form prints only where a
             decision says; where a verse names two bearers alike, each
             lists its occurrence by number (LUK 6:16#1); a decision may
             also name the books whose terminal subscriptions respell it,
             and the units of front and back matter that respell it in
             every paragraph and footnote, where a decided form may print
             only where a decision says
    words    a word respelled or modernized wherever it is printed as a whole
             word: in the translation, its notes, and front and back matter,
             or, with a scope of "scripture", in a book's verses and the
             lemmas and readings of their notes alone, preserving source
             prose's grammar. A word may except phrases it stands in, which
             its pass leaves as they are, though the grammar of scripture
             still revises the other words of a phrase spelling excepts.
             Words that a character style divides are not joined, divided,
             or re-divided, and nor are they in the lemma that quotes them,
             except that hyphens may replace spaces between unchanged words
             without moving their styles; the supplied words' style, which
             the reader does not see among roman words, divides nothing
             there
    passages punctuation in a keyed note or front/back-matter paragraph,
             and lowercase word initials in a keyed note's fragments,
             or Greek/Hebrew spelling in Old Testament notes and matter
    punctuation systematic English punctuation rules
    verses   changes to the words of single verses, each naming its verse,
             as "EZK 1:3", which must have the words once: its punctuation,
             or a spelling particular to it. They stand in groups, by the
             reason they share
    ligatures each ligature written out as its letters wherever it is
             printed, last of all, so that every other decision is written
             and met in the sources' letters

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
from collections import Counter
from collections.abc import Callable, Container, Iterable, Mapping
from difflib import SequenceMatcher

import bible.policy
from bible import assembly, matter, notes, repairs, scripture, usfm, usj
from bible.checks import CheckFailed, require, require_fields
from bible.policy_schema import NameDecision, RevisionChange, WordingChange
from bible.references import book_of
from bible.usj import Content, Document, Node, Predicate

# What revision has met: a word, verse, or punctuation rule by its key, a
# passage change by its selector and words, a word confined to notes by the
# note's key and the word, a phrase a word excepts by the word and the
# phrase, a name respelled or kept by its verse and form, and a name
# respelled in a subscription or a unit of matter by its book or unit and
# form.
type MetRevisions = set[str | tuple[str, ...]]
# The words to revise, letter by letter; an empty key ends a word.
type Trie = dict[str, "Trie"]

# What scoped grammar does not read among the words: notes, labels, the
# fields that quote or cite, and foreign words.
UNREVISED = frozenset("xt fl fq fqa wg wh".split())

# A word or phrase revised, or excepted: whole words, and what joins them.
WORD = re.compile(r"\w(?:[\w’', -]*\w)?")

# The character style that does not divide words where the words around it
# are roman: the translators' supplied words are printed in roman and shown
# plain on the website, so joining or dividing words across the style erases
# nothing the reader sees in a verse, a note's own text, or its lemma. Within
# another style, such as an italic rendering (fqa), it divides them.
INVISIBLE = frozenset({"add"})
ROMAN = frozenset({"ft", "fq"})


def _unrevised(item: Node) -> bool:
    return usj.is_note(item) or usj.is_label(item) or item.get("marker") in UNREVISED


# A word, with the apostrophes and hyphens within it, and a plural's
# possessive one.
LEXEME = re.compile(r"\w+(?:['’\-]\w+)*['’]?")


def punctuation_only(old: str, new: str) -> bool:
    """Keep lexical tokens, allowing initial case at a changed sentence end.
    A word keeps its apostrophes and hyphens, a plural's possessive one too."""
    before, after = list(LEXEME.finditer(old)), list(LEXEME.finditer(new))
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


def _lexemes(text: str) -> list[str]:
    """The words, apostrophes and hyphens within them and a plural's
    possessive one kept, with their case and the shape of their apostrophes
    put aside."""
    return [w.casefold().replace("’", "'") for w in LEXEME.findall(text)]


def words_kept(old: str, new: str) -> bool:
    """The words stand, in the same order: punctuation and capitals alone
    change, the most a verse revision may do without declaring its kind."""
    return _lexemes(old) == _lexemes(new)


def one_word_differs(old: str, new: str) -> bool:
    """One word changes, and nothing else among the words: the kind of
    change a verse revision may declare, a spelling or inflection chosen
    by sense, or a misprint corrected."""
    before, after = _lexemes(old), _lexemes(new)
    return len(before) == len(after) and sum(a != b for a, b in zip(before, after)) == 1


# What a verse revision may change among the words, declared by its group:
# the spelling or inflection of a word, chosen by sense verse by verse, or a
# word the source's printing got wrong, which another printing shows.
WORDING = frozenset({"spelling", "misprint"})


def check(policy: bible.policy.Policy) -> None:
    data = policy.revisions
    require_fields(
        data,
        {"why", "words", "verses", "passages", "punctuation", "names", "ligatures"},
        (),
        "Revisions file",
    )
    ligatures = data["ligatures"]
    require_fields(ligatures, {"why", "letters"}, (), "Ligatures")
    letters = ligatures["letters"]
    require(
        bool(ligatures["why"])
        and isinstance(letters, Mapping)
        and all(
            isinstance(ligature, str)
            and isinstance(written, str)
            and len(ligature) == 1
            and len(written) > 1
            for ligature, written in letters.items()
        )
        and not _ligature(letters, "".join(letters.values())),
        "Ligatures without a why, or not each one letter written as its letters",
    )
    for name, rule in data["punctuation"].items():
        require(
            name in RULES or name in {BRACKETS, ACROSTICS},
            f"Unknown punctuation rule: {name}",
        )
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
        # An excepted phrase holds its word whole and no other word of its
        # pass, which it would leave unrevised, so no other word excepts it;
        # a scoped word's phrase holds no spelling either, which would be
        # revised before the phrase is met. A word confined to notes does
        # not except.
        require(
            "except" not in entry
            or (
                "notes" not in entry
                and bool(entry["except"])
                and len(set(entry["except"])) == len(entry["except"])
                and all(
                    phrase not in words
                    and WORD.fullmatch(phrase) is not None
                    and _spans(phrase)
                    & (words.keys() if "scope" in entry else everywhere)
                    == {word}
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
    # The front and back matter that prints: a unit read only for what it
    # sends to the books, as Brenton's Appendix, is never revised as a unit,
    # and its notes are revised at their verses, by their keys.
    matter_units = {
        e["id"] for e in policy.entries if "file" not in e and "section" not in e
    }
    # Brenton's list of abbreviations is respelled as a unit too, for the
    # table the introduction makes of it, so a name decision may list it.
    named_units = policy.matter - {policy.appendix["source"]}
    names = data["names"]
    require_fields(names, {"why", "decisions"}, (), "Names")
    require(bool(names["why"]), "Names without a why")
    # The verses listed for each form, respelled or kept, across every
    # decision: two bearers may share a form, each in its own verses. A
    # subscription or a unit of matter is listed for a form once.
    listed: dict[str, set[str]] = {}
    colophons_listed: dict[str, set[str]] = {}
    matter_listed: dict[str, set[str]] = {}
    for bearer, decision in names["decisions"].items():
        require_fields(
            decision,
            {"to", "why", "forms"},
            {"keep", "colophons", "matter"},
            f"Name decision {bearer}",
        )
        require(
            bool(decision["to"])
            and bool(decision["why"])
            and bool(
                decision["forms"] or decision.get("colophons") or decision.get("matter")
            ),
            f"Name decision without a target, a why or a form: {bearer}",
        )
        for form in _decided_forms(decision):
            require(
                WORD.fullmatch(form) is not None and form != decision["to"],
                f"Name decision of what is not a word, or that changes nothing: {form}",
            )
        for form, keys in decision["forms"].items():
            _check_name_verses(
                keys, listed.setdefault(form, set()), f"{bearer}: {form}"
            )
        for form, books in decision.get("colophons", {}).items():
            require(bool(books), f"Name decision without a colophon: {bearer}: {form}")
            require(
                len(set(books)) == len(books),
                f"Colophon listed twice for a name: {bearer}: {form}",
            )
            for book in books:
                require(
                    book in policy.kjv_units,
                    f"Name decision for what is not a King James book: {bearer}: {book}",
                )
                require(
                    book not in colophons_listed.setdefault(form, set()),
                    f"Colophon name decided twice: {bearer}: {form}: {book}",
                )
                colophons_listed[form].add(book)
        for form, units in decision.get("matter", {}).items():
            require(bool(units), f"Name decision without a unit: {bearer}: {form}")
            require(
                len(set(units)) == len(units),
                f"Unit listed twice for a name: {bearer}: {form}",
            )
            for unit in units:
                require(
                    unit in named_units,
                    f"Name decision for what is not front or back matter: {bearer}: {unit}",
                )
                require(
                    unit not in matter_listed.setdefault(form, set()),
                    f"Matter name decided twice: {bearer}: {form}: {unit}",
                )
                matter_listed[form].add(unit)
        for kept in decision.get("keep", ()):
            require_fields(kept, {"form", "who", "verses"}, (), f"Kept name {bearer}")
            require(
                kept["form"] in _decided_forms(decision) and bool(kept["who"]),
                f"Kept name without its decision, or without who keeps it: {bearer}",
            )
            _check_name_verses(
                kept["verses"],
                listed.setdefault(kept["form"], set()),
                f"{bearer}: {kept['form']}",
            )
    # No word respells a name behind its decision's back, or prints one where
    # no decision says, alone or in a phrase: a word applies wherever it is
    # printed. A form decided for a subscription alone is a name too.
    decided = listed.keys() | colophons_listed.keys() | matter_listed.keys()
    for word, entry in words.items():
        spanned = sorted((_spans(word) | _spans(entry["to"])) & decided)
        if word.casefold() == entry["to"].casefold():
            # A title may change case beside a name without respelling it.
            spanned = [
                name
                for name in spanned
                if _phrase(name).findall(word) != _phrase(name).findall(entry["to"])
            ]
        require(
            not spanned, f"Name also respelled as a word: {word}: {', '.join(spanned)}"
        )
    # A word written anew is written with the letters, not a ligature that
    # the edition would then write out; and a respelling is more than the
    # ligature written out, which the edition does without it.
    table = str.maketrans(dict(letters))
    respellings = [
        *((word, entry["to"]) for word, entry in words.items()),
        *(
            (form, decision["to"])
            for decision in names["decisions"].values()
            for form in _decided_forms(decision)
        ),
    ]
    written = sorted(
        {
            to
            for old, to in respellings
            if _ligature(letters, to)
            and not (
                old.casefold() == to.casefold()
                and [c for c in old if c in letters] == [c for c in to if c in letters]
            )
        }
    )
    require(not written, f"Respellings that write a ligature: {written}")
    unneeded = sorted(old for old, to in respellings if old.translate(table) == to)
    require(not unneeded, f"Respellings that only write out a ligature: {unneeded}")
    for name, group in data["verses"].items():
        require_fields(group, {"why", "changes"}, {"wording"}, f"Revisions {name}")
        require(
            group["why"] and group["changes"],
            f"Revisions without a why, or without a change: {name}",
        )
        wording = group.get("wording")
        require(
            wording is None or (isinstance(wording, str) and wording in WORDING),
            f"Revisions with an unknown kind of wording: {name}: {wording}",
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
            # A verse revision changes punctuation and capitals only,
            # keeping words, numbers, and internal apostrophes and hyphens
            # intact, unless its group declares the kind of wording it
            # changes, and then one word. NT wording belongs to checked
            # Greek-reading or rendering decisions: no kind reaches it, and
            # its capitals change only at a changed sentence end.
            require(
                key[:3] not in policy.kjv_units
                or punctuation_only(change["from"], change["to"]),
                f"Revision changes New Testament words: {name}: {key}",
            )
            # Nor does it only write out a ligature, as a respelling may not:
            # the edition does that without it.
            require(
                words_kept(change["from"], change["to"])
                or not words_kept(change["from"].translate(table), change["to"]),
                f"Revision that only writes out a ligature: {name}: {key}",
            )
            require(
                (
                    words_kept(change["from"], change["to"])
                    if wording is None
                    else one_word_differs(change["from"], change["to"])
                ),
                f"Revision changes words without their kind, or other than one: {name}: {key}",
            )
            # A word it writes anew is written with the letters.
            require(
                all(
                    change["to"].count(ligature) <= change["from"].count(ligature)
                    for ligature in letters
                ),
                f"Revision that writes a ligature: {name}: {key}",
            )

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
                "unit" not in passage_change or passage_change["unit"] in matter_units,
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


def _decided_forms(decision: NameDecision) -> list[str]:
    """The forms a name decision respells, in its verses, its subscriptions,
    or the matter, each once and in the order the file gives them."""
    return list(
        dict.fromkeys(
            [
                *decision["forms"],
                *decision.get("colophons", {}),
                *decision.get("matter", {}),
            ]
        )
    )


def _check_name_verses(keys: Iterable[str], seen: set[str], label: str) -> None:
    """Verses a name decision lists: each once, for its form, across the
    verses that respell it and the verses that keep it."""
    keys = tuple(keys)
    require(bool(keys), f"Name decision without a verse: {label}")
    for key in keys:
        require(
            re.fullmatch(r"\w{3} [^\s#]+:[^\s#]+(?:#[1-9]\d*)?", key) is not None,
            f"Name decision for what is not a verse: {label}: {key}",
        )
        # A verse is listed whole, or by the occurrences of the form in it,
        # not both.
        verse = _occurrence(key)[0]
        require(
            key not in seen
            and verse not in seen
            and (key != verse or not any(o.startswith(verse + "#") for o in seen)),
            f"Verse listed twice for a name: {label}: {key}",
        )
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
    content: Content,
    *,
    skip: Predicate = usj.is_note,
    styles: tuple[str, ...] = (),
) -> list[tuple[int, int]]:
    """Runs with the same character styles, ignoring notes, string seams,
    and the invisible style of supplied words among roman ones. The content
    stands in the styles given: a note's field, read alone, in its own."""
    runs: list[tuple[int, int]] = []
    previous: tuple[str, ...] | None = None
    at = 0

    def visit(items: Content, styles: tuple[str, ...]) -> None:
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
                inner = (
                    (*styles, item["marker"])
                    if item["type"] == "char"
                    and (
                        item["marker"] not in INVISIBLE or not ROMAN.issuperset(styles)
                    )
                    else styles
                )
                visit(item["content"], inner)

    visit(content, styles)
    return runs


def _separators(words: str) -> list[str]:
    """What divides words: spaces and hyphens."""
    return re.findall(r"[\s\-]+", words)


def _hyphenated(words: str, replacement: str) -> bool:
    """Whether a replacement is the words with hyphens for the spaces
    between them."""
    return re.sub(r"\s+", "-", words) == replacement


def _keeps_styles(
    match: re.Match[str],
    replacement: str,
    runs: Callable[[], list[tuple[int, int]]],
) -> bool:
    """Whether a replacement keeps the character styles of the words it
    replaces: it respells each word in place, hyphenates between unchanged
    words, or the words stand in one style. Other joining, dividing or
    re-dividing across styles would erase their distinction. Notes and
    adjacent strings alone do not divide them."""
    return (
        _separators(match[0]) == _separators(replacement)
        or _hyphenated(match[0], replacement)
        or any(a <= match.start() and match.end() <= b for a, b in runs())
    )


def _rewritten(
    content: Content,
    pattern: re.Pattern[str],
    new: Callable[[re.Match[str]], str],
    *,
    skip: Predicate = usj.is_note,
    done: Callable[[re.Match[str]], object] | None = None,
    styles: tuple[str, ...] = (),
) -> Content:
    """Content with every match of a pattern in its words giving way to what
    new makes of it, and done told of each match that gives way. The words
    are read as one, whatever styles divide them, unless the replacement
    would not keep the styles; a note's words are its own, not those of the
    content it stands in. The content stands in the styles given."""
    edits: list[tuple[int, int, str]] = []
    runs = functools.cache(lambda: _style_runs(content, skip=skip, styles=styles))
    for match in pattern.finditer(usj.text_of(content, skip=skip)):
        replacement = new(match)
        if replacement == match[0] or not _keeps_styles(match, replacement, runs):
            continue
        if _hyphenated(match[0], replacement):
            # Keep the words in their original styles, replacing only the
            # separators (for example corner + supplied stone).
            edits.extend(
                (match.start() + gap.start(), match.start() + gap.end(), "-")
                for gap in re.finditer(r"\s+", match[0])
            )
        elif _separators(match[0]) == _separators(replacement):
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
    respelled with the same few sets of words, so each trie is built once."""
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


def respelled(
    doc: Document,
    policy: bible.policy.Policy,
    met: MetRevisions,
    *,
    book: bool = True,
) -> Document:
    """Spell first, then revise grammar in scripture; the names come before
    both (named).

    Each pass is one longest-match sweep. Spelling, vocabulary, and participle
    changes apply wherever a word is printed, source prose included. Grammar,
    the words scoped to scripture, applies to a book's verses alone: their
    words, and the lemmas (fq) and readings (fqa) of the notes set in them. A
    verse runs to the next verse number, or to the end of its book. The titles,
    headings, and introductions it spans keep their grammar, and so do the
    notes set in them, whose lemmas quote them. Plain quotation marks do not
    establish scope.
    """
    words = policy.revisions["words"]
    excepted = exceptions(policy)
    changed = False

    def to(match: re.Match[str]) -> str:
        # A phrase a word excepts stands as it is, and is met for the word.
        if match[0] in excepted:
            met.add((excepted[match[0]], match[0]))
            return match[0]
        return words[match[0]]["to"]

    def done(match: re.Match[str], key: str | None = None) -> None:
        # A word is met where it is changed, not where a style keeps it.
        nonlocal changed
        changed = True
        met.add(match[0])
        if key is not None and "notes" in words[match[0]]:
            met.add((key, match[0]))

    def excepting(scoped: bool) -> list[str]:
        """The phrases the words of a pass except, revised in that pass."""
        return [
            phrase
            for phrase, word in excepted.items()
            if ("scope" in words[word]) == scoped
        ]

    spelling = _words(
        [word for word, entry in words.items() if "scope" not in entry]
        + excepting(scoped=False)
    )

    def spelled_note(
        items: Content, text: str, at: int, divided: list[tuple[int, int]]
    ) -> Content:
        """A note's words respelled. Its readings and commentary stand alone;
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
                                match[0] if match.span() in kept else to(match)
                            ),
                            done=done,
                            styles=("fq",),
                        )
                    else:
                        inner = lemmas(item["content"])
                    item = {**item, "content": inner}
                output.append(item)
            return output

        return _rewritten(
            lemmas(items),
            spelling,
            to,
            skip=lambda item: usj.is_note(item) or item.get("marker") == "fq",
            done=done,
        )

    def spelled_notes(segment: Content) -> Content:
        """A verse with its notes respelled, each read at its place."""
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
                        "content": spelled_note(item["content"], text, at, divided),
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
                segment = spelled_notes(segment)
            part = _rewritten(segment, spelling, to, done=done)
            output += part + content[end : end + 1]
        return output

    grammar = {word: entry for word, entry in words.items() if "scope" in entry}
    general = _words(
        [word for word, entry in grammar.items() if "notes" not in entry]
        + excepting(scoped=True)
    )
    # A word confined to some notes is revised in their lemmas and readings,
    # which keep the phrases the scoped words except as the verse does.
    confined = {
        key: _words(
            [
                word
                for word, entry in grammar.items()
                if key in entry.get("notes", (key,))
            ]
            + excepting(scoped=True)
        )
        for entry in grammar.values()
        for key in entry.get("notes", ())
    }

    def quoted(content: Content, key: str | None = None) -> Content:
        output: Content = []
        for item in content:
            if isinstance(item, dict) and "content" in item:
                if item.get("marker") in {"fq", "fqa"} or (
                    key is not None and item.get("marker") == "it"
                ):
                    inner = _rewritten(
                        item["content"],
                        confined.get(key, general) if key is not None else general,
                        to,
                        skip=_unrevised,
                        done=lambda match: done(match, key),
                        styles=(item["marker"],),
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
# The opening parenthesis of an aside. A reference or list marker, as (39)
# or (a), supplies no sentence break, so the punctuation before it stays,
# across lines and verses too.
ASIDE = r"\((?!(?:\d+|[a-z])\))"
# The systematic rules, each a pattern over a unit's English, in the order
# they apply: a run of commas, colons, and semicolons duplicates the break an
# em dash or an aside's parenthesis marks. Inside closing parentheses the run
# moves after the last, or goes when a dash follows; before a dash or an
# aside it goes. The move comes first, so that a run it sets before a dash or
# an aside goes too, and a second pass changes nothing. A period, question
# mark, or exclamation mark inside a parenthesis ends the parenthesis's own
# sentence, and stays.
RULES: dict[str, re.Pattern[str]] = {
    "inside-parenthesis": re.compile(r"([,;:]+)\)+(—?)"),
    "before-em-dash": re.compile(r"[,;:]+(?=—)"),
    "before-parenthesis": re.compile(rf"[,;:]+(?=\s?{ASIDE})"),
}
# A run that ends a line, before a line of the same verse that opens an aside.
LINE_END = re.compile(rf"[,;:]+(?=\n\s*{ASIDE})")
# A verse that opens an aside, and a run that ends the verse before it.
OPENS_ASIDE = re.compile(rf"\s*{ASIDE}")
VERSE_END = re.compile(r"[,;:]+(?=\s*$)")
# The rule that drops Brenton's square brackets from a book's text. Not a
# pattern over a unit's English like RULES: a note's brackets, and the
# textual variants' around a former reading, are not scripture text and
# stay, so the rule reads a book's paragraphs alone (unbracketed).
BRACKETS = "brackets"
# The rule that drops the periods of Lamentations' acrostic names, which
# stand as headings, not sentences; it too reads a book's paragraphs alone.
ACROSTICS = "acrostic-headings"
# An acrostic name as Brenton prints it, with or without its period.
ACROSTIC = re.compile(r"[A-Za-z]+\.?")
# A bracket between two letters, which dropping it would join.
INSIDE_WORD = re.compile(r"\w[\[\]]+\w")
# What the rules do not understand, and refuse: a mark already standing where
# a run would move, unless a dash follows to clear it; the comma of the "Or,"
# that opens a note's alternative.
FOLLOWING = re.compile(r"(?![,;:]*—)[,;:.?!]")
ALTERNATIVE = re.compile(r"(?<!\w)Or$")
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
            ALTERNATIVE.search(text, 0, match.start())
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
    next verse opens an aside, or the aside opens the next line of the same
    verse. Read protected words at verse offsets, and delete only the marks,
    preserving the lines and their notes."""
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
        for match in LINE_END.finditer(text):
            line = text.count("\n", 0, match.end())
            _between(
                doc, verse.parts[line][0], verse.parts[line + 1][0], verse.reference
            )
            matches.append(match)
        if index + 1 < len(verses) and OPENS_ASIDE.match(texts[index + 1]):
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


def unpointed_acrostics(doc: Document, met: MetRevisions) -> Document:
    """The document with the period of each acrostic heading removed, in
    the style it stands in; a heading that is not a name of Lamentations
    is refused. A document with no period to remove is returned as given."""
    blocks: list[Node] = []
    changed = False
    for block in doc["content"]:
        if usj.paragraph(block) == "qa":
            text = usj.text_of(block["content"])
            require(
                usj.book_code(doc) == "LAM" and ACROSTIC.fullmatch(text) is not None,
                f"Unexpected acrostic heading: {usj.book_code(doc)}: {text!r}",
            )
            if text.endswith("."):
                content = usj.substituted(
                    block["content"], [(len(text) - 1, len(text), "")]
                )
                block = {**block, "content": content}
                changed = True
                met.add(ACROSTICS)
        blocks.append(block)
    return usj.with_blocks(doc, blocks) if changed else doc


def punctuated(
    doc: Document, policy: bible.policy.Policy, met: MetRevisions
) -> Document:
    """Regularize English punctuation across styles, within each text unit.

    Notes have their own words; verses, labels, and foreign styles interrupt
    a unit. The dash and the parenthesis keep their style because only the
    punctuation beside them changes. Punctuation after a tagged foreign word
    is refused, as it may be the foreign text's own, and so is a change that
    leaves a lemma its verse no longer has. The acrostic headings lose
    their periods first, under the same lemma check.
    """
    original = doc
    if ACROSTICS in policy.revisions["punctuation"]:
        doc = unpointed_acrostics(doc, met)
    changed = doc is not original
    rules = [name for name in RULES if name in policy.revisions["punctuation"]]
    if not rules:
        if changed:
            _check_lemmas(original, doc)
        return doc

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
        _check_lemmas(original, result)
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


def _ligature(letters: Mapping[str, str], text: str) -> bool:
    return any(ligature in text for ligature in letters)


def unligatured(
    doc: Document, policy: bible.policy.Policy, met: MetRevisions
) -> Document:
    """A document with its ligatures written out as their letters, wherever
    they stand: in its words, its notes, and the lemmas that quote them
    alike, so that a lemma still quotes its verse. Each ligature written
    out is met."""
    letters = policy.revisions["ligatures"]["letters"]
    table = str.maketrans(dict(letters))

    def written(content: Content) -> Content:
        output: Content = []
        for item in content:
            if isinstance(item, str):
                plain = item.translate(table)
                if plain != item:
                    met.update(
                        ("ligature", ligature)
                        for ligature in letters
                        if ligature in item
                    )
                item = plain
            elif "content" in item:
                item = {**item, "content": written(item["content"])}
            output.append(item)
        return output

    return usj.with_content(doc, written)


def regularized(doc: Document, policy: bible.policy.Policy) -> Document:
    """A document with the systematic spelling and punctuation alone, and
    its ligatures written out, recording nothing: the textual variants quote
    both Bibles so, to show the readings' differences and not the edition's
    finishing."""
    return unligatured(
        punctuated(respelled(doc, policy, set()), policy, set()), policy, set()
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
    """A book with its names respelled where their bearers are decided
    (revisions.json, names): every whole-word occurrence of a form in the
    verses its decision lists, in the styles it stands in, and in the lemmas
    of the notes that quote it. Every other verse that prints the form must
    be listed as keeping it, so that each form prints only where a decision
    says: an occurrence listed neither way is refused, and so is a listed
    verse without its form. Where a verse names two bearers alike, each
    lists its occurrence by number, as LUK 6:16#1; a verse that names the
    form once is listed whole, and a lemma quoting a numbered form, which
    does not say which occurrence it quotes, is refused. A subscription's
    names are named_colophon's."""
    decisions = policy.revisions["names"]["decisions"]
    # A form decided for a subscription alone is still decided: a verse
    # that prints it must be listed too.
    forms = frozenset(form for d in decisions.values() for form in _decided_forms(d))
    if not forms:
        return doc
    # Each listing: the verse, the occurrence it names or None for all, the
    # form, and what it gives way to, or None where it is kept.
    listings: dict[tuple[str, int | None, str], str | None] = {}
    for decision in decisions.values():
        for form, keys in decision["forms"].items():
            for key in _in_book(keys, code):
                listings[_occurrence(key) + (form,)] = decision["to"]
        for keeping in decision.get("keep", ()):
            for key in _in_book(keeping["verses"], code):
                listings[_occurrence(key) + (keeping["form"],)] = None
    verses = scripture.verses(doc)
    pattern = _names(forms)
    # Where each form stands, by verse: a form within a longer one is the
    # longer one's.
    found: dict[tuple[str, str], list[int]] = {}
    for reference, verse in verses.items():
        for match in pattern.finditer(verse.text):
            form = re.sub(r"\s+", " ", match[0])
            places = found.setdefault((reference, form), [])
            places.append(match.start())
            require(
                (reference, None, form) in listings
                or (reference, len(places), form) in listings,
                f"Name without a decision: {code} {reference}: {form}",
            )
    for (reference, occurrence, form), to in listings.items():
        count = len(found.get((reference, form), ()))
        require(count >= (occurrence or 1), f"Name not met: {code} {reference}: {form}")
        require(
            occurrence is None or count > 1,
            f"Name numbered in a verse that has it once: {code} {reference}: {form}",
        )
        key = reference if occurrence is None else f"{reference}#{occurrence}"
        met.add(("name" if to else "kept", f"{code} {key}", form))
    changes = {k: to for k, to in listings.items() if to}
    # A form respelled within a longer one would splice the two decisions.
    for reference, _, form in changes:
        require(
            [m.start() for m in _phrase(form).finditer(verses[reference].text)]
            == found[reference, form],
            f"Name within another name: {code} {reference}: {form}",
        )
    if not changes:
        return doc
    occurrences: dict[tuple[str, str, str], set[int]] = {}
    for (reference, occurrence, form), to in changes.items():
        if occurrence is not None:
            occurrences.setdefault((reference, form, to), set()).add(occurrence)
    # The lemmas change with every occurrence of the words they quote, and
    # cannot tell a respelled occurrence from a kept one.
    for reference, form, _ in occurrences:
        require(
            not any(
                _phrase(form).search(usj.text_of(item["content"]))
                for _, note in verses[reference].notes
                for item in usj.walk(note["content"])
                if usj.is_type(item, "char", "fq")
            ),
            f"Lemma quoting a numbered name: {code} {reference}: {form}",
        )
    return _reworded(
        code,
        doc,
        sorted({(reference, form, to) for (reference, _, form), to in changes.items()}),
        every=True,
        verses=verses,
        occurrences=occurrences,
    )


def _occurrence(key: str) -> tuple[str, int | None]:
    """A verse key as its reference and the occurrence it names, if any."""
    reference, _, occurrence = key.partition("#")
    return reference, int(occurrence) if occurrence else None


def named_colophon(
    code: str, doc: Document, policy: bible.policy.Policy, met: MetRevisions
) -> Document:
    """Respell only the names explicitly assigned to this subscription."""
    changes = {
        form: decision["to"]
        for decision in policy.revisions["names"]["decisions"].values()
        for form, books in decision.get("colophons", {}).items()
        if code in books
    }
    if not changes:
        return doc
    paragraph = matter.colophon_paragraph(doc, f"Name decision for {code}")
    text = usj.text_of(paragraph["content"])
    # A form within a longer one is the longer one's, as in a verse, so that
    # no two edits overlap.
    found: dict[str, list[re.Match[str]]] = {}
    for match in _names(frozenset(changes)).finditer(text):
        found.setdefault(re.sub(r"\s+", " ", match[0]), []).append(match)
    edits = []
    for form, to in changes.items():
        matches = found.get(form, [])
        require(len(matches) == 1, f"Colophon name not met once: {code}: {form}")
        match = matches[0]
        start, end, new = _edit(match.start(), match[0], to)
        require(
            not new
            or sum(a < end and start < b for a, b in usj.leaves(paragraph["content"]))
            <= 1,
            f"Colophon name across a style or note: {code}: {form}",
        )
        edits.append((start, end, new))
        met.add(("colophon name", code, form))
    return matter.with_colophon(doc, usj.substituted(paragraph["content"], edits))


def named_matter(
    code: str, doc: Document, policy: bible.policy.Policy, met: MetRevisions
) -> Document:
    """A unit of front or back matter with its names respelled where a
    decision lists the unit (revisions.json, names, matter): every
    whole-word occurrence of the form in its paragraphs, table cells, and
    footnotes, in the styles it stands in. A form decided anywhere prints in
    the matter only where a decision says: an occurrence the unit is not
    listed for is refused, and so is a listing the unit does not meet."""
    decisions = policy.revisions["names"]["decisions"]
    forms = frozenset(form for d in decisions.values() for form in _decided_forms(d))
    if not forms:
        return doc
    changes = {
        form: decision["to"]
        for decision in decisions.values()
        for form, units in decision.get("matter", {}).items()
        if code in units
    }
    pattern = _names(forms)
    # Each occurrence found, and each respelled: a respelling that would
    # join or divide words across styles is not made, and is refused.
    found: Counter[str] = Counter()
    made: Counter[str] = Counter()

    def form_of(match: re.Match[str]) -> str:
        return re.sub(r"\s+", " ", match[0])

    def to(match: re.Match[str]) -> str:
        form = form_of(match)
        require(form in changes, f"Name without a decision: {code}: {form}")
        found[form] += 1
        return changes[form]

    def done(match: re.Match[str]) -> None:
        made[form_of(match)] += 1

    def footnote(item: Node) -> Node:
        # A footnote's words are its author's too, and are respelled with
        # the paragraph's.
        if not usj.is_note(item):
            return item
        return {**item, "content": _rewritten(item["content"], pattern, to, done=done)}

    def respelled(content: Content) -> Content:
        return usj.mapped(_rewritten(content, pattern, to, done=done), footnote)

    result = usj.with_content(doc, respelled)
    across = sorted(found - made)
    require(not across, f"Matter name across a style: {code}: {', '.join(across)}")
    for form in changes:
        require(form in found, f"Matter name not met: {code}: {form}")
        met.add(("matter name", code, form))
    return result if changes else doc


def check_kept(
    code: str, before: Document, after: Document, policy: bible.policy.Policy
) -> None:
    """Refuse a kept name that another revision respelled: each kept verse of a
    book as finished prints its form as often as the names left it, whether
    it keeps the verse whole or an occurrence of it."""
    kept = [
        (_occurrence(key)[0], keeping["form"])
        for decision in policy.revisions["names"]["decisions"].values()
        for keeping in decision.get("keep", ())
        for key in _in_book(keeping["verses"], code)
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
            counts[0] == counts[1], f"Kept name respelled: {code} {reference}: {form}"
        )


def _reworded(
    code: str,
    doc: Document,
    changes: list[tuple[str, str, str]],
    *,
    every: bool,
    verses: dict[str, scripture.Verse] | None = None,
    occurrences: Mapping[tuple[str, str, str], Container[int]] | None = None,
) -> Document:
    """A book with words of its verses giving way to others: in each verse
    named, the words once, or every whole-word occurrence of them, or the
    occurrences numbered for the change. They give way where they stand, in
    the styles they stand in, and the lemma of a note of the verse that
    quotes them changes with them. A lemma that quotes them in part would be
    left as the verse no longer reads, so it is refused. The verses are the
    document's, if already read."""
    if verses is None:
        verses = scripture.verses(doc)
    edits = []
    boundaries: dict[str, str] = {}
    for reference, old, to in changes:
        key = f"{code} {reference}"
        require(reference in verses, f"Revision of a verse the edition lacks: {key}")
        verse = verses[reference]
        found = list(_phrase(old).finditer(verse.text))
        if occurrences and (reference, old, to) in occurrences:
            numbered = occurrences[reference, old, to]
            found = [m for n, m in enumerate(found, 1) if n in numbered]
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
                content = _rewritten(content, pattern, lambda match: to, styles=("fq",))
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
            ("colophon name", code, form)
            for form, books in decision.get("colophons", {}).items()
            for code in books
        )
        names.update(
            ("matter name", code, form)
            for form, units in decision.get("matter", {}).items()
            for code in units
        )
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
        | {("ligature", ligature) for ligature in data["ligatures"]["letters"]}
        | verses
        | set(data["punctuation"])
        | passages
        | notes
        | excepted
        | names
    )
    unused = sorted((key for key in expected if key not in met), key=str)
    require(not unused, f"Revisions that nothing prints: {unused}")
