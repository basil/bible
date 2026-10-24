"""The pipeline whole: its order, what it refuses, and what it sends to be
typeset."""

from __future__ import annotations

import copy
import re
from collections.abc import Callable, Iterable
from typing import Any, cast

import pytest
from conftest import Staged, changed

import bible.export
import bible.pipeline
import bible.policy
import bible.sources
from bible import (
    annotate,
    assembly,
    export,
    lines,
    pipeline,
    places,
    revision,
    scripture,
    usj,
    web,
)
from bible.checks import CheckFailed
from bible.usj import Document


def test_the_edition_prints_every_unit_once_in_the_manifests_order(
    edition: bible.pipeline.Edition,
    policy: bible.policy.Policy,
    exported: dict[str, str],
) -> None:
    order = [entry["id"] for entry in policy.entries]
    assert list(edition.documents) == order
    assert list(exported) == order
    assert edition.scripture == {unit["id"] for unit in policy.scripture}
    assert edition.authored == {"introduction", "XXF", "XXG"}
    for mode in ("pdf", "sample"):
        assert "XXA" not in dict(pipeline.view(edition, mode))
    # The textual variants are prepared for the website, and printed nowhere.
    assert bible.policy.VARIANTS["id"] not in edition.documents
    assert order[-1] == "REV"
    # Each is written under its own id, whatever file it was printed from.
    assert all(text.startswith(f"\\id {code}") for code, text in exported.items())
    assert dict(edition.summary) == {
        "alexandrine_notes": 415,
        "alexandrine_appendix_paragraphs": 26,
        "byzantine_units": 1940,
        "byzantine_edits": 858,
        "kjv_corrections": 83,
        "byzantine_notes": 941,
        "scripture_units": 78,
        "brenton_units": 51,
        "kjv_units": 27,
        "kjv_marginal_notes": 775,
        "printed_notes": 6204,
        # Every verse of the assembled books: Brenton's, with the passages
        # supplied from Codex Alexandrinus and the King James Bible's
        # 1 Kingdoms 23:12 and 3 Kingdoms 14:1-20, less the verses
        # Alexandrinus lacks, and divided as the edition's numbering divides
        # them; and the King James New Testament less the four verses the
        # Byzantine text lacks.
        # Sirach's translator's Prologue is an introduction, not a verse.
        "verses": 36580,
    }


def test_no_stage_changes_what_an_earlier_stage_made(staged: Staged) -> None:
    """Documents are shared between stages, so none may be changed in place."""
    assert (
        dict(staged.read.brenton),
        dict(staged.read.kjv),
        dict(staged.read.updated_brenton),
    ) == staged.read_before
    assert staged.promoted == staged.promoted_before
    assert staged.units == staged.assembled
    assert staged.lined == staged.line_documents


def test_the_policy_is_read_once_and_cannot_be_changed(
    policy: bible.policy.Policy,
) -> None:
    with pytest.raises(TypeError):
        cast(dict[str, Any], policy.manifest)["title"] = "Another"
    with pytest.raises(TypeError):
        cast(dict[str, Any], policy.brenton_notes["notes"]["GEN 1:9#2"])[
            "lemma"
        ] = "other words"
    for entry in policy.entries:
        if "file" in entry:
            with pytest.raises(TypeError):
                cast(dict[str, Any], entry)["id"] = "XYZ"
    # A test declares another policy; the one it started from is as it was.
    other = changed(policy, "sample", lambda data: data.pop("GEN"))
    assert "GEN" in policy.sample and "GEN" not in other.sample


@pytest.mark.parametrize(
    "name, change, refusal",
    [
        (
            "manifest",
            lambda d: d["scripture"][1].update(continues="GEN"),
            "missing or unknown fields",
        ),
        (
            "witnesses",
            lambda d: d.append({"id": "OTH", "phrase": "The Alexandrian Jews"}),
            "Witnesses of units without a contents entry",
        ),
        (
            "brenton_notes",
            lambda d: d["notes"]["GEN 1:9#2"].update(lema="place"),
            "missing or unknown fields",
        ),
        (
            "kjv_notes",
            lambda d: d["notes"]["MAT 6:1 of"].update(why=""),
            "without a why",
        ),
        (
            "sample",
            lambda d: d.update(XYZ=[1]),
            "Sample names units outside the edition",
        ),
        (
            "manifest",
            lambda d: d["scripture"][0].update(section="middle_testament"),
            "outside both testaments",
        ),
        (
            "prose",
            lambda d: d["numbers"]["changes"].append(
                {"unit": "GEN", "from": "In the beginning", "to": "At first"}
            ),
            "no front or back matter",
        ),
        (
            "manifest",
            lambda d: d["scripture"][0].update(short_titel="Genesis"),
            "Manifest scripture.*GEN.*missing or unknown fields",
        ),
        (
            "manifest",
            lambda d: d["scripture"][0].update(labelled_chapters=True),
            "Labelled chapters not true or without a singular name: GEN",
        ),
        (
            "manifest",
            lambda d: d["scripture"][0].update(
                labelled_chapters=False, cited_singly="Genesis"
            ),
            "Labelled chapters not true or without a singular name: GEN",
        ),
        (
            "prose",
            lambda d: d.update(
                probe={
                    "why": "x",
                    "changes": [
                        {
                            "unit": "XXB",
                            "from": "introduction may be necessary",
                            "to": "introduction may be necessary",
                        }
                    ],
                }
            ),
            "Prose change that changes nothing: probe: XXB",
        ),
        (
            "prose",
            lambda d: d["numbers"]["changes"][0].update(to="5."),
            "Prose change that changes nothing: numbers: MAT 18:28 pence",
        ),
        (
            "prose",
            lambda d: d["numbers"]["changes"].append({"from": "5.", "to": "five"}),
            "neither a note nor a unit",
        ),
    ],
)
def test_a_malformed_decision_is_refused_when_the_policy_is_read(
    policy: bible.policy.Policy,
    name: str,
    change: Callable[[dict[str, Any]], object],
    refusal: str,
) -> None:
    with pytest.raises(CheckFailed, match=refusal):
        changed(policy, name, change)


def test_a_decision_that_nothing_meets_is_refused(
    edition: bible.pipeline.Edition, policy: bible.policy.Policy
) -> None:
    reports = [
        annotate.Report(
            keys={row["key"] for rows in edition.notes.values() for row in rows}
            | {
                key
                for key, decision in policy.brenton_notes["notes"].items()
                if decision.get("omitted")
                # Or moved onto the verse of the link that replaces it.
                or ("verse" in decision and decision.get("lemma") is None)
            },
            edited=[
                change["note"]
                for group in policy.prose.values()
                for change in group["changes"]
                if "note" in change
            ],
        )
    ]
    annotate.check_notes(policy, reports)
    pipeline.check_met(policy, edition.met)

    def exception(data: dict[str, Any]) -> None:
        data["notes"]["GEN 1:1"] = {
            "lemma": "beginning",
            "why": "there is no such note",
        }

    with pytest.raises(
        CheckFailed, match=r"Unused Brenton note exceptions: \['GEN 1:1'\]"
    ):
        annotate.check_notes(changed(policy, "brenton_notes", exception), reports)

    def prose(data: dict[str, Any]) -> None:
        data["numbers"]["changes"].append(
            {"note": "GEN 1:4", "from": "5.", "to": "five"}
        )

    with pytest.raises(CheckFailed, match="Prose changes to notes not met once each"):
        annotate.check_notes(changed(policy, "prose", prose), reports)

    def decision(data: dict[str, Any]) -> None:
        data["decisions"]["GEN 1:1"] = {
            "source": "Heb. 1",
            "not_a_citation": True,
            "why": "x",
        }

    with pytest.raises(CheckFailed, match=r"Unused citation decisions: \['GEN 1:1'\]"):
        pipeline.check_met(changed(policy, "citations", decision), edition.met)

    def name(data: dict[str, Any]) -> None:
        data["dialects"]["brenton"]["books"]["Jezek"] = "EZK"

    with pytest.raises(CheckFailed, match="Unused names for books"):
        pipeline.check_met(changed(policy, "citations", name), edition.met)


@pytest.mark.parametrize(
    "excluded,refusal",
    [
        (["NEH", "XXA", "XXC"], r"neither read nor excluded: \['OTH'\]"),
        (["NEH", "OTH", "OTX", "XXA", "XXC"], r"missing or read: \['OTX'\]"),
        (["GEN", "NEH", "OTH", "XXA", "XXC"], r"missing or read: \['GEN'\]"),
    ],
)
def test_every_brenton_source_is_read_or_excluded(
    sources: bible.sources.Sources,
    declared: bible.policy.Policy,
    excluded: list[str],
    refusal: str,
) -> None:
    def exclude(data: dict[str, Any]) -> None:
        data["excluded"]["brenton"] = excluded

    with pytest.raises(CheckFailed, match=refusal):
        pipeline.read(sources, changed(declared, "manifest", exclude))


def test_the_editions_spelling_is_revised_wherever_a_word_is_printed(
    edition: bible.pipeline.Edition, policy: bible.policy.Policy
) -> None:
    words = policy.revisions["words"]
    assert words["Chanaan"]["to"] == "Canaan"
    decisions = policy.revisions["names"]["decisions"]
    assert decisions["Pharaoh, Egyptian royal title"]["to"] == "Pharaoh"
    assert edition.met["revisions"] == (
        set(words)
        | {
            ("name", key, form)
            for decision in decisions.values()
            for form, keys in decision["forms"].items()
            for key in keys
        }
        | {
            ("kept", key, kept["form"])
            for decision in decisions.values()
            for kept in decision.get("keep", ())
            for key in kept["verses"]
        }
        | {
            ("colophon name", code, form)
            for decision in decisions.values()
            for form, books in decision.get("colophons", {}).items()
            for code in books
        }
        | {
            ("matter name", code, form)
            for decision in decisions.values()
            for form, units in decision.get("matter", {}).items()
            for code in units
        }
        | {
            (key, word)
            for word, entry in words.items()
            for key in entry.get("notes", ())
        }
        | {
            (word, phrase)
            for word, entry in words.items()
            for phrase in entry.get("except", ())
        }
        | set(policy.revisions["punctuation"])
        | {
            ("ligature", ligature)
            for ligature in policy.revisions["ligatures"]["letters"]
        }
        | {c["verse"] for c in revision.verse_changes(policy)}
        | {
            (c.get("note", c.get("unit")), c["from"])
            for c in revision.passage_changes(policy)
        }
    )

    def pattern(keys: Iterable[str]) -> re.Pattern[str]:
        return re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, keys)) + r")(?!\w)")

    def printed(phrase: str) -> str:
        doc = usj.parse("\\id GEN\n\\c 1\n\\p\n\\v 1 " + phrase)
        return scripture.verses(revision.respelled(doc, policy, set()))["1:1"].text

    # Scoped grammar can remain in explanatory prose and ambiguous nouns, and
    # a spelling that excepts phrases survives in them alone, as the source
    # has them or as the grammar of scripture revises their other words, or
    # where a style divides it.
    excepting = {
        pattern([word]): pattern([*entry["except"], *map(printed, entry["except"])])
        for word, entry in words.items()
        if "except" in entry and "scope" not in entry
    }
    unscoped = pattern(
        word
        for word, entry in words.items()
        if "scope" not in entry and "except" not in entry
    )
    assert any("scope" in entry for entry in words.values())
    # Authored prose preserves the source forms it discusses: the words
    # quoted from the sources and the explicit before-and-after examples.
    # Enumerate every occurrence, so this does not permit unrevised words
    # elsewhere in the introduction or in the translated books.
    source_forms = {
        "introduction": [
            "publickly",
            "Ghost",
            "ghost",
            "Hallelujah",
            "tare",
            "forgat",
            "trode",
            "tare",
            "trode",
            "forgat",
            "strake sail",
            "forgat",
            "an hundred",
            "Shew",
            "shewed",
            "alway",
            "amongst",
            "throughly",
            "subtil",
            "brasen",
            "spue",
            "apostolick",
            "musick",
            "emerods",
            "enquire",
            "grey",
            "waggon",
            "amongst",
            "connexion",
            "shew",
            "expence",
            "scrole",
            "dulness",
            "shamefacedness",
            "sweetsmelling",
            "fellowservant",
            "stiffnecked",
            "longsuffering",
            "JESUS",
            "KING OF KINGS, AND LORD OF LORDS",
            "THE BEING",
            "I AM",
        ],
    }
    # Names decided by their bearers also survive when the introduction
    # discusses the source form, rather than referring to the bearer.
    assert "he writes Abraam, Noe, Juda" in usj.text_of(
        edition.documents["introduction"]["content"]
    )
    assert {"Abraam", "Amos"} <= {
        form for decision in decisions.values() for form in decision["forms"]
    }
    spelling = pattern(
        sorted(
            [word for word, entry in words.items() if "scope" not in entry]
            + [
                phrase
                for entry in words.values()
                if "scope" not in entry
                for phrase in entry.get("except", ())
            ],
            key=len,
            reverse=True,
        )
    )
    variants = bible.policy.VARIANTS["id"]

    def marks(content: usj.Content) -> tuple[set[int], list[tuple[int, usj.Node]]]:
        """Where a character style opens or closes in the words, and each
        note with its place in them. The supplied words' style among roman
        words divides nothing, so it marks no bound."""
        bounds: set[int] = set()
        notes: list[tuple[int, usj.Node]] = []
        at = 0

        def visit(items: usj.Content, styles: tuple[str, ...] = ()) -> None:
            nonlocal at
            for item in items:
                if isinstance(item, str):
                    at += len(item)
                elif usj.is_note(item):
                    notes.append((at, item))
                elif "content" in item:
                    styled = item["type"] == "char" and (
                        item["marker"] not in revision.INVISIBLE
                        or not revision.ROMAN.issuperset(styles)
                    )
                    bounds.update([at] if styled else [])
                    visit(
                        item["content"],
                        (*styles, item["marker"]) if styled else styles,
                    )
                    bounds.update([at] if styled else [])

        visit(content)
        return bounds, notes

    for code, doc in {
        **edition.documents,
        "XXA": edition.numbering_page,
        variants: edition.variants_page,
    }.items():
        found: list[str] = []
        for paragraph in usj.walk(doc["content"]):
            if paragraph["type"] not in {"para", "table:cell"}:
                continue
            content = paragraph["content"]
            words_of = usj.text_of(content)
            bounds, notes = marks(content)

            def kept(text: str, at: int) -> list[tuple[int, int]]:
                # A compound may stand unrevised where the printed words at
                # its place have it with a style dividing it.
                return [
                    match.span()
                    for match in spelling.finditer(text)
                    if match[0] in words
                    and words_of[at + match.start() : at + match.end()] == match[0]
                    and any(at + match.start() < b < at + match.end() for b in bounds)
                ]

            passages = [(words_of, kept(words_of, 0))]
            for at, note in notes:
                # Note lemmas alone can inherit a kept occurrence; a reading
                # or a comment with the same words cannot.
                protected: list[tuple[int, int]] = []
                offset = 0
                for item in note["content"]:
                    text = usj.text_of([item])
                    quoted = text.rstrip(": ")
                    if usj.is_type(item, "char", "fq") and words_of.startswith(
                        quoted, at
                    ):
                        protected += [
                            (offset + a, offset + b) for a, b in kept(quoted, at)
                        ]
                    offset += len(text)
                passages.append((usj.text_of(note["content"]), protected))
            for text, protected in passages:
                for a, b in sorted(protected, reverse=True):
                    text = text[:a] + " " * (b - a) + text[b:]
                found.extend(unscoped.findall(text))
                for word, phrases in excepting.items():
                    assert not word.search(phrases.sub("", text)), (code, word.pattern)
        assert found == source_forms.get(code, []), (code, found)
    # A scoped word that stands alone is a verb wherever it is printed, so
    # none is left in the verses of the books, outside their headings and
    # the phrases it excepts.
    alone = pattern(
        word
        for word, entry in words.items()
        if "scope" in entry and "notes" not in entry and " " not in word
    )
    scoped_phrases = pattern(
        phrase
        for word, entry in words.items()
        if "scope" in entry
        for phrase in entry.get("except", ())
    )
    for code in edition.scripture:
        blocks = edition.documents[code]["content"]
        for reference, verse in scripture.verses(edition.documents[code]).items():
            for block, lo, hi, _ in verse.parts:
                if not revision.prose(blocks[block]["marker"]):
                    text = usj.text_of(blocks[block]["content"][lo:hi])
                    assert not alone.findall(scoped_phrases.sub("", text)), (
                        code,
                        reference,
                    )
    assert "has been" in usj.serialize(edition.documents["XXB"])
    ezekiel = usj.serialize(edition.documents["EZK"])
    assert "the word of the Lord came to Ezekiel the priest" in ezekiel
    assert "And Ezekiel shall be for a sign to you" in ezekiel


NOE = (
    "\\id GEN\n\\mt1 NOE\n\\c 1\n\\p\n\\v 1 Noe’s sons and Noeman "
    "\\f - \\fr 1:1 \\fq went with Noe: \\ft or, \\fqa Noe\\f*went \\add with\\add* Noe.\n"
    "\\v 2 And Noe went.\n"
)


def revisions(
    policy: bible.policy.Policy, **sections: dict[str, Any]
) -> bible.policy.Policy:
    def change(data: dict[str, Any]) -> None:
        data.update(
            words={},
            verses={},
            passages={},
            punctuation={},
            names={"why": "names", "decisions": {}},
            ligatures={"why": "ligatures", "letters": {}},
        )
        data.update(sections)

    return changed(policy, "revisions", change)


def test_inscription_case_crosses_styles_and_notes_without_changing_them(
    declared: bible.policy.Policy,
) -> None:
    source = usj.parse(
        "\\id REV\n\\c 17\n\\p \\v 5 "
        "MYSTERY, BABYLON THE GREAT, THE MOTHER OF "
        "\\f - \\fq HARLOTS: \\ft or, \\fqa fornications\\f*"
        "\\add HARLOTS\\add* AND ABOMINATIONS OF THE EARTH."
    )
    before = copy.deepcopy(source)
    result = revision.respelled(source, declared, set())
    assert usj.text_of(result["content"][-1]["content"]) == (
        "Mystery, Babylon the great, the mother of harlots and abominations of the earth."
    )
    rendered = usj.serialize(result)
    assert "\\add harlots\\add*" in rendered
    assert "\\fq harlots: " in rendered
    assert "\\fqa fornications" in rendered
    assert source == before


@pytest.mark.parametrize(
    "code,reference,expected",
    [
        ("EXO", "3:14", "I am the Being"),
        ("EXO", "3:14", "The Being hath sent me to you"),
        ("LEV", "24:11", "named the Name"),
        ("ISA", "41:4", "I am"),
        ("MAT", "1:21", "call his name Jesus"),
        ("ACT", "17:23", "To the unknown God"),
        ("REV", "19:16", "King of kings, and Lord of lords"),
    ],
)
def test_emphatic_case_is_normalized(
    edition: bible.pipeline.Edition, code: str, reference: str, expected: str
) -> None:
    assert expected in scripture.verses(edition.documents[code])[reference].text


def test_a_word_is_respelled_whole_in_the_text_and_its_notes(
    policy: bible.policy.Policy,
) -> None:
    words = revisions(policy, words={"Noe": {"to": "Noah", "why": "the English name"}})
    met: revision.MetRevisions = set()
    text = usj.serialize(revision.respelled(usj.parse(NOE), words, met))
    assert (
        "\\v 1 Noah’s sons and Noeman \\f - \\fr 1:1 \\fq went with Noah: \\ft or, "
        "\\fqa Noah\\f*went \\add with\\add* Noah.\n\\v 2 And Noah went.\n"
    ) in text
    assert "\\mt1 NOE" in text and met == {"Noe"}


def test_a_word_excepts_the_phrases_it_stands_in(
    policy: bible.policy.Policy,
) -> None:
    words = revisions(
        policy,
        words={
            "Noe": {"to": "Noah", "why": "the English name", "except": ["with Noe"]}
        },
    )
    met: revision.MetRevisions = set()
    text = usj.serialize(revision.respelled(usj.parse(NOE), words, met))
    # The excepted phrase stands as it is, whatever styles divide it, and
    # the word is respelled everywhere else.
    assert (
        "\\v 1 Noah’s sons and Noeman \\f - \\fr 1:1 \\fq went with Noe: \\ft or, "
        "\\fqa Noah\\f*went \\add with\\add* Noe.\n\\v 2 And Noah went.\n"
    ) in text
    assert met == {"Noe", ("Noe", "with Noe")}


def test_a_scoped_word_excepts_the_phrases_it_stands_in(
    policy: bible.policy.Policy,
) -> None:
    words = revisions(
        policy,
        words={
            "bore": {
                "to": "bare",
                "why": "the King James past tense",
                "scope": "scripture",
                "except": ["bore his ear"],
            }
        },
    )
    met: revision.MetRevisions = set()
    source = usj.parse(
        "\\id GEN\n\\ip She bore a son.\n\\c 1\n\\p \\v 1 She "
        "\\f - \\fq bore: \\ft Gr. \\fqa bore\\f*bore a son, and he shall bore his ear."
    )
    result = revision.respelled(source, words, met)
    verse = scripture.verses(result)["1:1"]
    # The excepted phrase stands in scripture, the word gives way elsewhere
    # in it and in the readings its notes quote, and prose keeps its own.
    assert verse.text == "She bare a son, and he shall bore his ear."
    assert usj.text_of(verse.notes[0][1]["content"]) == "bare: Gr. bare"
    assert "\\ip She bore a son." in usj.serialize(result)
    assert met == {"bore", ("bore", "bore his ear")}


def test_a_scoped_word_excepts_its_phrases_in_a_confined_note_too(
    policy: bible.policy.Policy,
) -> None:
    words = revisions(
        policy,
        words={
            "bore": {
                "to": "bare",
                "why": "x",
                "scope": "scripture",
                "except": ["bore his ear"],
            },
            "does": {
                "to": "doth",
                "why": "x",
                "scope": "scripture",
                "notes": ["GEN 1:1#1"],
            },
        },
    )
    revision.check(words)
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p \\v 1 He "
        "\\f - \\fq bore his ear: \\ft Gr. \\fqa does\\f*bore his ear."
    )
    usj.notes_of(doc["content"])[0]["x-key"] = "GEN 1:1#1"
    met: revision.MetRevisions = set()
    verse = scripture.verses(revision.respelled(doc, words, met))["1:1"]
    # The lemma of a note a word is confined to quotes the excepted phrase
    # as the verse keeps it, while the reading takes the confined word.
    assert verse.text == "He bore his ear."
    assert usj.text_of(verse.notes[0][1]["content"]) == "bore his ear: Gr. doth"
    assert met == {"does", ("GEN 1:1#1", "does"), ("bore", "bore his ear")}


def test_a_word_scoped_to_scripture_spares_front_and_back_matter(
    policy: bible.policy.Policy,
) -> None:
    words = revisions(
        policy,
        words={
            "Noe": {"to": "Noah", "why": "the English name"},
            "went": {"to": "goeth", "why": "the tense", "scope": "scripture"},
        },
    )
    met: revision.MetRevisions = set()
    book = usj.serialize(revision.respelled(usj.parse(NOE), words, met))
    assert "goeth with Noah: \\ft or, \\fqa Noah\\f*goeth" in book
    assert "\\v 2 And Noah goeth.\n" in book and met == {"Noe", "went"}
    met = set()
    matter = usj.serialize(
        revision.respelled(
            usj.parse(
                "\\id XXB\n\\ip Noe went.\\f + \\ft Noe went; \\fqa Noe went\\f*"
            ),
            words,
            met,
            book=False,
        )
    )
    assert "\\ip Noah went." in matter
    assert "\\ft Noah went; \\fqa Noah went" in matter
    assert met == {"Noe"}


def test_a_word_is_respelled_whatever_styles_divide_it(
    policy: bible.policy.Policy,
) -> None:
    words = revisions(
        policy,
        words={
            "Noe": {"to": "Noah", "why": "the English name"},
            "Sem": {"to": "Shem", "why": "the English name"},
            "ham": {"to": "Cham", "why": "the Greek name"},
        },
    )
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 N\\add oe\\add* and \\add Se\\add*m "
        "\\f - \\fr 1:1 \\fq N\\+it oe\\+it*: \\ft or, \\fqa S\\+it em\\+it*\\f*begat "
        "Noe\\add man\\add* and \\it Sem\\it*s and \\it thus \\it*ham and Noe\n"
        "\\v 2 begat Sem.\n"
    )
    met: revision.MetRevisions = set()
    text = usj.serialize(revision.respelled(doc, words, met))
    # Each letter keeps the style it stood in, and what is added takes the
    # style of the word it joins.
    assert "\\v 1 N\\add oah\\add* and \\add She\\add*m " in text
    assert "\\fq N\\+it oah\\+it*: \\ft or, \\fqa Sh\\+it em\\+it*\\f*" in text
    assert "and \\it thus \\it*Cham and " in text
    # A word is whole by the letters about it, in whatever style, and a
    # verse's number ends one.
    assert "begat Noe\\add man\\add* and \\it Sem\\it*s and " in text
    assert text.endswith("and Noah\n\\v 2 begat Shem.\n")
    assert met == {"Noe", "Sem", "ham"}


def group(
    *changes: object, why: str = "the sentence runs on", wording: str | None = None
) -> dict[str, Any]:
    entry: dict[str, Any] = {"why": why, "changes": list(changes)}
    if wording is not None:
        entry["wording"] = wording
    return {"pointing": entry}


def test_a_verse_is_revised_in_its_own_words_and_the_notes_that_quote_them(
    policy: bible.policy.Policy,
) -> None:
    change = {"verse": "GEN 1:1", "from": "went with Noe.", "to": "went with Noe:"}
    verses = revisions(policy, verses=group(change))
    revision.check(verses)
    met: revision.MetRevisions = set()
    text = usj.serialize(revision.revised("GEN", usj.parse(NOE), verses, met))
    # The words change in the styles they stand in; the other verse is as it was.
    assert "\\fqa Noe\\f*went \\add with\\add* Noe:\n\\v 2 And Noe went.\n" in text
    assert met == {"GEN 1:1"}
    quoted = {
        "verse": "GEN 1:1",
        "from": "with Noe",
        "to": "beside Noe",
        "why": "a note quotes these words",
    }
    both = revisions(
        policy,
        verses={
            **group(change),
            "wording": {"why": "x", "wording": "spelling", "changes": [quoted]},
        },
    )
    revision.check(both)
    text = usj.serialize(revision.revised("GEN", usj.parse(NOE), both, set()))
    # Two groups revise the one verse, each its own words.
    assert "\\fq went beside Noe: " in text and "went \\add beside\\add* Noe:" in text


def test_a_note_quotes_a_verse_whatever_styles_divide_its_words(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 He went \\add with\\add* Noe \\f - \\fr 1:1 "
        "\\fq went \\+it with\\+it* Noe: \\ft or, \\fqa beside\\f*then.\n"
    )
    change = {"verse": "GEN 1:1", "from": "went with Noe", "to": "went beside Noe"}
    verses = revisions(policy, verses=group(change))
    text = usj.serialize(revision.revised("GEN", doc, verses, set()))
    assert "\\v 1 He went \\add beside\\add* Noe " in text
    assert "\\fq went \\+it beside\\+it* Noe: \\ft or, \\fqa beside\\f*then." in text


def test_a_revision_meets_its_words_whole(policy: bible.policy.Policy) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 He had besides them, beside Noe \\f - \\fr 1:1 "
        "\\fq beside Noe: \\ft or, \\fqa besides\\f*then.\n"
    )
    # "besides" holds "beside", but not as a whole word.
    change = {"verse": "GEN 1:1", "from": "beside", "to": "besides"}
    text = usj.serialize(
        revision.revised("GEN", doc, revisions(policy, verses=group(change)), set())
    )
    assert "\\v 1 He had besides them, besides Noe " in text
    assert "\\fq besides Noe: \\ft or, \\fqa besides\\f*then." in text


def test_a_revision_across_a_style_or_note_is_refused(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 He went,—\\add with\\add* Noe,—"
        "\\f - \\fr 1:1 \\ft Gr. went\\f* then.\n"
    )
    # The supplied word would be set in the plain words before it.
    styled = {"verse": "GEN 1:1", "from": "went,—with Noe,—", "to": "went with Noe "}
    with pytest.raises(CheckFailed, match="across a style or note: GEN 1:1"):
        revision.revised("GEN", doc, revisions(policy, verses=group(styled)), set())
    # The note would stand after the words that followed it.
    noted = {"verse": "GEN 1:1", "from": "Noe,— then", "to": "Noe; Then"}
    with pytest.raises(CheckFailed, match="across a style or note: GEN 1:1"):
        revision.revised("GEN", doc, revisions(policy, verses=group(noted)), set())
    within = {"verse": "GEN 1:1", "from": "went,—", "to": "went "}
    text = usj.serialize(
        revision.revised("GEN", doc, revisions(policy, verses=group(within)), set())
    )
    assert "\\v 1 He went \\add with\\add* Noe,—" in text


def test_a_revision_changes_a_lemma_whole_or_is_refused(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 He went with Noe \\f - \\fr 1:1 "
        "\\fq with Noe: \\ft Gr. went with Noe\\f*then.\n"
    )
    # The lemma holds only part of the words revised, and would go stale.
    partly = {"verse": "GEN 1:1", "from": "went with", "to": "walked beside"}
    with pytest.raises(CheckFailed, match="lemma its verse no longer has: GEN 1:1"):
        revision.revised("GEN", doc, revisions(policy, verses=group(partly)), set())
    # Only the lemma quotes the verse: the note's own words stay.
    within = {"verse": "GEN 1:1", "from": "with Noe", "to": "beside Noe"}
    text = usj.serialize(
        revision.revised("GEN", doc, revisions(policy, verses=group(within)), set())
    )
    assert "\\fq beside Noe: \\ft Gr. went with Noe\\f*then." in text


@pytest.mark.parametrize(
    "sections, refusal",
    [
        (
            {"words": {"Noe": {"to": "Noe", "why": "x"}}},
            "changes nothing, or without a why",
        ),
        ({"words": {"Noe.": {"to": "Noah", "why": "x"}}}, "not a word"),
        (
            {"words": {"Noe": {"to": "Noah", "why": "x", "scope": "notes"}}},
            "scope that is not scripture",
        ),
        (
            {"words": {"Noe": {"to": "Noah", "why": "x", "except": ["Noeman"]}}},
            "Invalid exception",
        ),
        (
            {
                "words": {
                    "Noe": {"to": "Noah", "why": "x", "except": ["Noe went"]},
                    "went": {"to": "goeth", "why": "x"},
                }
            },
            "Invalid exception",
        ),
        (
            {
                "words": {
                    "went": {
                        "to": "goeth",
                        "why": "x",
                        "scope": "scripture",
                        "except": ["went with"],
                    },
                    "with": {"to": "wyth", "why": "x"},
                }
            },
            "Invalid exception",
        ),
        (
            {
                "words": {
                    "went": {
                        "to": "goeth",
                        "why": "x",
                        "scope": "scripture",
                        "except": ["went with"],
                    },
                    "with": {"to": "wyth", "why": "x", "scope": "scripture"},
                }
            },
            "Invalid exception",
        ),
        (
            {"verses": {"GEN 1:1": [{"from": "Noe", "to": "Noah"}]}},
            "missing or unknown fields",
        ),
        ({"verses": group(why="")}, "without a why, or without a change"),
        ({"verses": group({"from": "Noe", "to": "Noah"})}, "missing or unknown fields"),
        (
            {"verses": group({"verse": "Genesis 1", "from": "Noe", "to": "Noah"})},
            "not a verse",
        ),
        (
            {"verses": group({"verse": "GEN 1:1", "from": "Noe", "to": "Noe"})},
            "changes nothing",
        ),
        (
            {"verses": group({"verse": "MAT 1:1", "from": "Noe", "to": "Noah"})},
            "Revision changes New Testament words",
        ),
        (
            {"verses": group({"verse": "GEN 1:1", "from": "beside", "to": "besides"})},
            "Revision changes words without their kind",
        ),
        (
            {
                "verses": group(
                    {"verse": "GEN 1:1", "from": "the fowls", "to": "all birds"},
                    wording="spelling",
                )
            },
            "or other than one",
        ),
        (
            {
                "verses": group(
                    {"verse": "MAT 1:1", "from": "beside", "to": "besides"},
                    wording="spelling",
                )
            },
            "Revision changes New Testament words",
        ),
        (
            {
                "verses": group(
                    {"verse": "GEN 1:1", "from": "beside", "to": "besides"},
                    wording="wording",
                )
            },
            "unknown kind of wording",
        ),
        (
            {
                "words": {"emerods": {"to": "hæmorrhoids", "why": "x"}},
                "ligatures": {"why": "x", "letters": {"æ": "ae"}},
            },
            r"Respellings that write a ligature: \['hæmorrhoids'\]",
        ),
        (
            {"ligatures": {"why": "x", "letters": {"ae": "æ"}}},
            "not each one letter written as its letters",
        ),
        (
            {"ligatures": {"why": "x", "letters": ["æ", "ae"]}},
            "not each one letter written as its letters",
        ),
        (
            {
                "words": {"Phœnicia": {"to": "Phoenicia", "why": "x"}},
                "ligatures": {"why": "x", "letters": {"œ": "oe"}},
            },
            r"Respellings that only write out a ligature: \['Phœnicia'\]",
        ),
        (
            {
                "verses": group(
                    {"verse": "GEN 1:1", "from": "Judea", "to": "Judæa"},
                    wording="misprint",
                ),
                "ligatures": {"why": "x", "letters": {"æ": "ae"}},
            },
            "Revision that writes a ligature: pointing: GEN 1:1",
        ),
        (
            {
                "verses": group(
                    {"verse": "GEN 1:1", "from": "Phœnicia.", "to": "Phoenicia,"},
                    wording="spelling",
                ),
                "ligatures": {"why": "x", "letters": {"œ": "oe"}},
            },
            "Revision that only writes out a ligature: pointing: GEN 1:1",
        ),
        (
            {"words": {"emerods": {"why": "x"}}},
            "Respelling of emerods has missing or unknown fields",
        ),
    ],
)
def test_a_malformed_revision_is_refused(
    policy: bible.policy.Policy, sections: dict[str, Any], refusal: str
) -> None:
    with pytest.raises(CheckFailed, match=refusal):
        revision.check(revisions(policy, **sections))


def test_ligatures_are_written_out_in_words_notes_and_lemmas(
    policy: bible.policy.Policy,
) -> None:
    source = usj.parse(
        "\\id JOB\n\\c 4\n\\p \\v 1 Then Eliphaz the "
        "\\f - \\fq Thæmanite: \\ft Gr. \\fqa Æthiopic chœnix\\f*"
        "\\add Thæmanite\\add* answered."
    )
    before = copy.deepcopy(source)
    met: revision.MetRevisions = set()
    result = revision.unligatured(source, policy, met)
    assert source == before
    assert usj.serialize(result) == usj.serialize(
        usj.parse(
            "\\id JOB\n\\c 4\n\\p \\v 1 Then Eliphaz the "
            "\\f - \\fq Thaemanite: \\ft Gr. \\fqa Aethiopic choenix\\f*"
            "\\add Thaemanite\\add* answered."
        )
    )
    assert met == {("ligature", "æ"), ("ligature", "Æ"), ("ligature", "œ")}


def test_the_edition_prints_no_ligature(
    edition: bible.pipeline.Edition, policy: bible.policy.Policy
) -> None:
    letters = policy.revisions["ligatures"]["letters"]
    # The website's own pages print too, the textual variants among them.
    documents = {
        **edition.documents,
        bible.policy.NUMBERING["id"]: edition.numbering_page,
        bible.policy.VARIANTS["id"]: edition.variants_page,
    }
    printed = sorted(
        code
        for code, doc in documents.items()
        if any(
            ligature in usj.text_of(doc["content"], skip=lambda _: False)
            for ligature in letters
        )
    )
    assert not printed


def test_a_revision_must_be_met(policy: bible.policy.Policy) -> None:
    doc = usj.parse(NOE)
    twice = {"verse": "GEN 1:1", "from": "Noe", "to": "Noah"}
    with pytest.raises(CheckFailed, match="not met once in its verse: GEN 1:1"):
        revision.revised("GEN", doc, revisions(policy, verses=group(twice)), set())
    absent = {**twice, "verse": "GEN 1:9"}
    with pytest.raises(CheckFailed, match="verse the edition lacks: GEN 1:9"):
        revision.revised("GEN", doc, revisions(policy, verses=group(absent)), set())
    stop = {"verse": "GEN 1:2", "from": "went.", "to": "went;"}
    same = {"verse": "GEN 1:2", "from": "Noe went.", "to": "Noe went:"}
    with pytest.raises(CheckFailed, match="Revisions of the same words: GEN 1:2"):
        revision.revised("GEN", doc, revisions(policy, verses=group(stop, same)), set())
    unprinted = revisions(policy, verses=group({**twice, "verse": "XYZ 1:1"}))
    with pytest.raises(
        CheckFailed, match=r"Revisions that nothing prints: \['XYZ 1:1'\]"
    ):
        revision.check_met(unprinted, set())
    unmet = revisions(
        policy, words={"Jehoshaphat": {"to": "Josaphat", "why": "nowhere"}}
    )
    with pytest.raises(
        CheckFailed, match=r"Revisions that nothing prints: \['Jehoshaphat'\]"
    ):
        revision.check_met(unmet, set())


def names(*decisions: dict[str, Any]) -> dict[str, Any]:
    return {
        "why": "the bearers",
        "decisions": {f"bearer {i}": d for i, d in enumerate(decisions)},
    }


NOAH = {
    "to": "Noah",
    "why": "the spelling of the New Testament",
    "forms": {"Noe": ["GEN 1:1"]},
    "keep": [{"form": "Noe", "who": "another Noe", "verses": ["GEN 1:2"]}],
}


def test_a_verse_naming_two_bearers_alike_lists_each_occurrence(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 Noe and \\add Noe\\add* went.\n\\v 2 Noe.\n"
    )
    numbered = names(
        {"to": "Noah", "why": "x", "forms": {"Noe": ["GEN 1:1#1"]}},
        {
            "to": "Noël",
            "why": "x",
            "forms": {"Noe": ["GEN 1:2"]},
            "keep": [{"form": "Noe", "who": "another", "verses": ["GEN 1:1#2"]}],
        },
    )
    met: revision.MetRevisions = set()
    result = revision.named("GEN", doc, revisions(policy, names=numbered), met)
    verses = scripture.verses(result)
    assert verses["1:1"].text == "Noah and Noe went." and verses["1:2"].text == "Noël."
    assert met == {
        ("name", "GEN 1:1#1", "Noe"),
        ("kept", "GEN 1:1#2", "Noe"),
        ("name", "GEN 1:2", "Noe"),
    }
    # A kept occurrence must survive the later revisions, as a kept verse
    # must.
    respelling = revisions(
        policy,
        names=numbered,
        verses=group({"verse": "GEN 1:1", "from": "and Noe", "to": "and Noah"}),
    )
    with pytest.raises(CheckFailed, match="Kept name respelled: GEN 1:1: Noe"):
        revision.check_kept(
            "GEN",
            result,
            revision.revised("GEN", result, respelling, set()),
            respelling,
        )
    # An occurrence the verse lacks, or one listed beside the whole verse,
    # is refused.
    with pytest.raises(CheckFailed, match="Name not met: GEN 1:1: Noe"):
        absent = names(
            {
                "to": "Noah",
                "why": "x",
                "forms": {"Noe": ["GEN 1:1#1", "GEN 1:1#3", "GEN 1:2"]},
                "keep": [{"form": "Noe", "who": "another", "verses": ["GEN 1:1#2"]}],
            }
        )
        revision.named("GEN", doc, revisions(policy, names=absent), set())
    with pytest.raises(CheckFailed, match="Verse listed twice for a name"):
        both = names(
            {"to": "Noah", "why": "x", "forms": {"Noe": ["GEN 1:1#1"]}},
            {"to": "Noël", "why": "x", "forms": {"Noe": ["GEN 1:1"]}},
        )
        revision.check(revisions(policy, names=both))
    # A verse that names the form once is listed whole.
    with pytest.raises(CheckFailed, match="Name numbered in a verse that has it once"):
        once = names(
            {"to": "Noah", "why": "x", "forms": {"Noe": ["GEN 1:1", "GEN 1:2#1"]}}
        )
        revision.named("GEN", doc, revisions(policy, names=once), set())
    # A lemma cannot say which occurrence it quotes, whether the respelled
    # one or the kept one, so it is refused rather than respelled with both.
    for lemma in ["Noe", "Noe went"]:
        quoted = usj.parse(
            "\\id GEN\n\\c 1\n\\p\n\\v 1 Noe and Noe "
            f"\\f - \\fq {lemma}: \\ft the other\\f*went.\n\\v 2 Noe.\n"
        )
        with pytest.raises(
            CheckFailed, match="Lemma quoting a numbered name: GEN 1:1: Noe"
        ):
            revision.named("GEN", quoted, revisions(policy, names=numbered), set())


def test_a_name_is_respelled_in_its_listed_verses_and_their_lemmas(
    policy: bible.policy.Policy,
) -> None:
    decided = revisions(policy, names=names(NOAH))
    revision.check(decided)
    met: revision.MetRevisions = set()
    text = usj.serialize(revision.named("GEN", usj.parse(NOE), decided, met))
    # Every whole word of the listed verse, and the lemma that quotes it; the
    # kept verse, the reading and the longer word are as they were.
    assert text.endswith(
        "\\v 1 Noah’s sons and Noeman \\f - \\fr 1:1 \\fq went with Noah: \\ft or, "
        "\\fqa Noe\\f*went \\add with\\add* Noah.\n\\v 2 And Noe went.\n"
    )
    assert met == {("name", "GEN 1:1", "Noe"), ("kept", "GEN 1:2", "Noe")}
    revision.check_met(decided, met)
    # A form of two words is met across the line break that sets verse in
    # lines, and in a New Testament book, whose words no verse revision may
    # change.
    sea = {"to": "Red Sea", "why": "x", "forms": {"Red sea": ["MAT 1:1"]}}
    doc = usj.parse("\\id MAT\n\\c 1\n\\q1\n\\v 1 By the Red\n\\q1 sea.\n")
    decided = revisions(policy, names=names(sea))
    revision.check(decided)
    text = usj.serialize(revision.named("MAT", doc, decided, set()))
    assert text.endswith("\\v 1 By the Red\n\\q1 Sea.\n")
    with pytest.raises(CheckFailed, match="changes New Testament words"):
        revision.check(
            revisions(
                policy,
                verses=group({"verse": "MAT 1:1", "from": "sea", "to": "Sea"}),
            )
        )


def test_a_subscription_name_is_scoped_and_must_be_met(
    declared: bible.policy.Policy,
) -> None:
    decision = {
        "to": "Luke",
        "why": "Paul's companion",
        "forms": {"Lucas": ["2CO 1:1"]},
        "colophons": {"Lucas": ["2CO"]},
    }
    own = revisions(declared, names=names(decision))
    revision.check(own)
    source = usj.parse(
        "\\id 2CO\n\\c 1\n\\p \\v 1 Lucas "
        "\\f - \\fq Lucas: \\ft Lucas says \\fqa Lucas\\f*went.\n"
        "\\esb \\cat colophon\\cat*\n"
        "\\p Written by \\add Lucas\\add*.\n\\esbe\n"
    )
    before = copy.deepcopy(source)
    met: revision.MetRevisions = set()
    result = revision.named(
        "2CO", revision.named_colophon("2CO", source, own, met), own, met
    )
    assert source == before
    assert usj.serialize(result) == usj.serialize(
        usj.parse(
            "\\id 2CO\n\\c 1\n\\p \\v 1 Luke "
            "\\f - \\fq Luke: \\ft Lucas says \\fqa Lucas\\f*went.\n"
            "\\esb \\cat colophon\\cat*\n"
            "\\p Written by \\add Luke\\add*.\n\\esbe\n"
        )
    )
    revision.check_met(own, met)
    with pytest.raises(CheckFailed, match="Revisions that nothing prints"):
        revision.check_met(own, {("name", "2CO 1:1", "Lucas")})
    only_colophon = revisions(declared, names=names({**decision, "forms": {}}))
    revision.check(only_colophon)
    # A form decided for a subscription alone is still a name no word respells.
    with pytest.raises(
        CheckFailed, match="Name also respelled as a word: Lucas: Lucas"
    ):
        revision.check(
            revisions(
                declared,
                names=names({**decision, "forms": {}}),
                words={"Lucas": {"to": "Luke", "why": "x"}},
            )
        )
    # Another book's subscription keeps the source's name.
    other = usj.parse(
        "\\id ROM\n\\c 1\n\\p \\v 1 Paul.\n"
        "\\esb \\cat colophon\\cat*\n\\p Written by Lucas.\n\\esbe\n"
    )
    assert revision.named_colophon("ROM", other, only_colophon, set()) is other
    # A form decided for a subscription alone is still decided in the verses.
    with pytest.raises(CheckFailed, match="Name without a decision: 2CO 1:1: Lucas"):
        revision.named("2CO", source, only_colophon, set())
    for text in ["Written by Lucasians.", "Written by Lucas and Lucas."]:
        stale = usj.parse(
            "\\id 2CO\n\\esb \\cat colophon\\cat*\n\\p " + text + "\n\\esbe\n"
        )
        with pytest.raises(CheckFailed, match="Colophon name not met once"):
            revision.named_colophon("2CO", stale, only_colophon, set())
    # A form within a longer one is the longer one's, so no two edits overlap.
    nested = revisions(
        declared,
        names=names(
            {**decision, "forms": {}},
            {
                "to": "Titus and Luke",
                "why": "x",
                "forms": {},
                "colophons": {"Titus and Lucas": ["2CO"]},
            },
        ),
    )
    revision.check(nested)
    pair = usj.parse(
        "\\id 2CO\n\\esb \\cat colophon\\cat*\n\\p By Titus and Lucas.\n\\esbe\n"
    )
    with pytest.raises(CheckFailed, match="Colophon name not met once: 2CO: Lucas"):
        revision.named_colophon("2CO", pair, nested, set())
    with pytest.raises(CheckFailed, match="expected one terminal colophon"):
        revision.named_colophon("2CO", usj.parse(NOE), only_colophon, set())


@pytest.mark.parametrize(
    "colophons,message",
    [
        ({"Lucas": []}, "without a colophon"),
        ({"Lucas": ["2CO", "2CO"]}, "Colophon listed twice"),
        ({"Lucas": ["XYZ"]}, "not a King James book"),
        ({"Luke": ["2CO"]}, "changes nothing: Luke"),
    ],
)
def test_malformed_subscription_name_decisions_are_refused(
    declared: bible.policy.Policy, colophons: dict[str, list[str]], message: str
) -> None:
    decision = {"to": "Luke", "why": "x", "forms": {}, "colophons": colophons}
    with pytest.raises(CheckFailed, match=message):
        revision.check(revisions(declared, names=names(decision)))


def test_a_front_matter_name_is_scoped_and_must_be_met(
    declared: bible.policy.Policy,
) -> None:
    decision = {
        "to": "Luke",
        "why": "Paul's companion",
        "forms": {"Lucas": ["2CO 1:1"]},
        "matter": {"Lucas": ["XXB"]},
    }
    own = revisions(declared, names=names(decision))
    revision.check(own)
    source = usj.parse(
        "\\id XXB\n\\ip Lucas went\\f + \\ft with \\it Lucas\\it*.\\f*, "
        "Lucasians say.\n\\tr \\tc1 Lucas \\tc2 by Lucas\n"
    )
    before = copy.deepcopy(source)
    met: revision.MetRevisions = set()
    result = revision.named_matter("XXB", source, own, met)
    assert source == before
    assert usj.serialize(result) == usj.serialize(
        usj.parse(
            "\\id XXB\n\\ip Luke went\\f + \\ft with \\it Luke\\it*.\\f*, "
            "Lucasians say.\n\\tr \\tc1 Luke \\tc2 by Luke\n"
        )
    )
    assert met == {("matter name", "XXB", "Lucas")}
    revision.check_met(own, met | {("name", "2CO 1:1", "Lucas")})
    with pytest.raises(CheckFailed, match="Revisions that nothing prints"):
        revision.check_met(own, {("name", "2CO 1:1", "Lucas")})
    # A unit that names nobody decided is shared, not copied.
    plain = usj.parse("\\id XXE\n\\ip Paul went.\n")
    assert revision.named_matter("XXE", plain, own, set()) is plain
    # A decided form prints in the matter only where a decision says.
    other = usj.parse("\\id XXE\n\\ip Lucas went.\n")
    with pytest.raises(CheckFailed, match="Name without a decision: XXE: Lucas"):
        revision.named_matter("XXE", other, own, set())
    stale = usj.parse("\\id XXB\n\\ip Lucasians went.\n")
    with pytest.raises(CheckFailed, match="Matter name not met: XXB: Lucas"):
        revision.named_matter("XXB", stale, own, set())
    # A form decided for the matter alone is still a name no word respells,
    # and still decided in the verses.
    only_matter = revisions(declared, names=names({**decision, "forms": {}}))
    revision.check(only_matter)
    with pytest.raises(CheckFailed, match="Name also respelled as a word: Lucas"):
        revision.check(
            revisions(
                declared,
                names=names({**decision, "forms": {}}),
                words={"Lucas": {"to": "Luke", "why": "x"}},
            )
        )
    verses = usj.parse("\\id 2CO\n\\c 1\n\\p \\v 1 Lucas went.\n")
    with pytest.raises(CheckFailed, match="Name without a decision: 2CO 1:1: Lucas"):
        revision.named("2CO", verses, only_matter, set())
    # Two decisions may not respell one form in one unit.
    twice = revisions(declared, names=names(decision, {**decision, "forms": {}}))
    with pytest.raises(CheckFailed, match="Matter name decided twice: .*: Lucas: XXB"):
        revision.check(twice)
    # Brenton's list of abbreviations is respelled as a unit, so it may be
    # listed.
    revision.check(
        revisions(
            declared, names=names({**decision, "matter": {"Lucas": ["XXB", "XXD"]}})
        )
    )
    # A respelling that would join words across styles is refused, not
    # skipped.
    joined = revisions(
        declared,
        names=names(
            {"to": "Luke", "why": "x", "forms": {}, "matter": {"Lucas Paulus": ["XXB"]}}
        ),
    )
    styled = usj.parse("\\id XXB\n\\ip \\it Lucas\\it* Paulus went.\n")
    with pytest.raises(CheckFailed, match="Matter name across a style: XXB"):
        revision.named_matter("XXB", styled, joined, set())


@pytest.mark.parametrize(
    "matter,message",
    [
        ({"Lucas": []}, "without a unit"),
        ({"Lucas": ["XXB", "XXB"]}, "Unit listed twice"),
        ({"Lucas": ["GEN"]}, "not front or back matter"),
        ({"Luke": ["XXB"]}, "changes nothing: Luke"),
    ],
)
def test_malformed_front_matter_name_decisions_are_refused(
    declared: bible.policy.Policy, matter: dict[str, list[str]], message: str
) -> None:
    decision = {"to": "Luke", "why": "x", "forms": {}, "matter": matter}
    with pytest.raises(CheckFailed, match=message):
        revision.check(revisions(declared, names=names(decision)))


@pytest.mark.parametrize("separator", [" ", "\n"])
def test_name_phrases_keep_word_boundaries_and_prefer_the_longest(
    separator: str,
) -> None:
    pattern = revision._names(frozenset({"Noe", "Noel", "Noe son", "Noe son of"}))
    text = (
        f"Noe{separator}son of Noah; Noe{separator}son; "
        f"Noe{separator}son ofa; Noel; Noe; Noes; xNoe."
    )
    assert [m[0] for m in pattern.finditer(text)] == [
        f"Noe{separator}son of",
        f"Noe{separator}son",
        f"Noe{separator}son",
        "Noel",
        "Noe",
    ]


def test_a_name_prints_only_where_a_decision_says(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(NOE)
    unlisted = revisions(policy, names=names({**NOAH, "keep": []}))
    with pytest.raises(CheckFailed, match="Name without a decision: GEN 1:2: Noe"):
        revision.named("GEN", doc, unlisted, set())
    absent = {"to": "Lamek", "why": "x", "forms": {"Lamech": ["GEN 1:1"]}}
    with pytest.raises(CheckFailed, match="Name not met: GEN 1:1: Lamech"):
        revision.named("GEN", doc, revisions(policy, names=names(NOAH, absent)), set())
    # A form within a longer one is the longer one's, and is not respelled there.
    peor = usj.parse("\\id GEN\n\\c 1\n\\p\n\\v 1 Baal Peor and Baal.\n")
    within = names(
        {"to": "Bael", "why": "x", "forms": {"Baal": ["GEN 1:1"]}},
        {"to": "Baal-peor", "why": "x", "forms": {"Baal Peor": ["GEN 1:1"]}},
    )
    with pytest.raises(CheckFailed, match="Name within another name: GEN 1:1: Baal"):
        revision.named("GEN", peor, revisions(policy, names=within), set())
    # Two bearers may share a form, but a verse is listed for it once. A word
    # respelled wherever it is printed would respell a name behind the
    # decision's back, or print one where no decision says: as the word, in a
    # phrase, or in what it respells, all of which the check refuses. A
    # verse's own change to a kept name is refused by the kept verse after
    # the fact.
    with pytest.raises(CheckFailed, match="Verse listed twice for a name"):
        revision.check(revisions(policy, names=names(NOAH, {**NOAH, "keep": []})))
    for word, to in [("Noe", "Noah"), ("Noe went", "Noah went"), ("Noë", "Noe")]:
        shared = revisions(
            policy, names=names(NOAH), words={word: {"to": to, "why": "x"}}
        )
        with pytest.raises(
            CheckFailed, match=f"Name also respelled as a word: {word}: Noe"
        ):
            revision.check(shared)
    own = revisions(
        policy,
        names=names(NOAH),
        verses=group({"verse": "GEN 1:2", "from": "Noe went", "to": "Noah went"}),
    )
    named = revision.named("GEN", doc, own, set())
    with pytest.raises(CheckFailed, match="Kept name respelled: GEN 1:2: Noe"):
        revision.check_kept(
            "GEN", named, revision.revised("GEN", named, own, set()), own
        )
    with pytest.raises(
        CheckFailed,
        match=r"nothing prints: \[\('kept', 'GEN 1:2', 'Noe'\), \('name', 'GEN 1:1', 'Noe'\)\]",
    ):
        revision.check_met(revisions(policy, names=names(NOAH)), set())


@pytest.mark.parametrize(
    "decision,message",
    [
        ({**NOAH, "to": "Noe"}, "changes nothing: Noe"),
        ({**NOAH, "why": ""}, "without a target, a why or a form"),
        ({**NOAH, "forms": {"Noe": ["GEN 1"]}}, "not a verse: bearer 0: Noe: GEN 1"),
        ({**NOAH, "forms": {"Noe": ["GEN 1:1", "GEN 1:1"]}}, "listed twice"),
        ({**NOAH, "forms": {"Noe": ["GEN 1:2"]}}, "listed twice for a name"),
        (
            {**NOAH, "keep": [{"form": "Noah", "who": "x", "verses": ["GEN 1:2"]}]},
            "Kept name without its decision",
        ),
        (
            {**NOAH, "keep": [{"form": "Noe", "verses": ["GEN 1:2"]}]},
            "Kept name bearer 0",
        ),
    ],
)
def test_a_malformed_name_decision_is_refused(
    policy: bible.policy.Policy, decision: dict[str, Any], message: str
) -> None:
    with pytest.raises(CheckFailed, match=message):
        revision.check(revisions(policy, names=names(decision)))


@pytest.mark.parametrize(
    "old,new",
    [
        ("word.", "word?"),
        ("king's word: 1", "king's word; 1"),
        ("believed: blessed", "believed? Blessed"),
        ("believed? Blessed", "believed: blessed"),
    ],
)
def test_nt_verse_revisions_allow_punctuation(
    policy: bible.policy.Policy, old: str, new: str
) -> None:
    decision = {"verse": "MAT 1:1", "from": old, "to": new}
    revision.check(revisions(policy, verses=group(decision)))


@pytest.mark.parametrize(
    "old,new",
    [
        ("1", "2"),
        ("thy", "thine"),
        ("king's", "kings"),
        ("the apostles’ feet", "the apostles feet"),
        ("market-place", "market place"),
        ("God", "god"),
        ("said: god", "said: God"),
        ("said? God", "said? god"),
        ("said: god", "said? GOD"),
    ],
)
def test_nt_punctuation_decisions_cannot_change_words(
    policy: bible.policy.Policy, old: str, new: str
) -> None:
    decision = {"verse": "MAT 1:1", "from": old, "to": new}
    with pytest.raises(CheckFailed, match="Revision changes New Testament words"):
        revision.check(revisions(policy, verses=group(decision)))


def test_a_revision_may_end_a_paragraph_or_leave_a_style_without_words(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 In \\add the\\add* beginning\n"
        "\\v 2 God made\n\\p\n\\v 3 the earth\n"
    )
    changes = group(
        {"verse": "GEN 1:1", "from": "In the beginning", "to": "In beginning"},
        {"verse": "GEN 1:2", "from": "God made", "to": "God made:"},
    )
    revised = revision.revised("GEN", doc, revisions(policy, verses=changes), set())
    # The style that lost its words is gone, and the verse after it in the
    # paragraph is still found; words added at a paragraph's end stand there.
    assert usj.serialize(revised).endswith(
        "\\p\n\\v 1 In beginning\n\\v 2 God made:\n\\p\n\\v 3 the earth\n"
    )


def test_the_sample_prints_selected_chapters_as_the_full_edition_has_them(
    edition: bible.pipeline.Edition, policy: bible.policy.Policy
) -> None:
    full = dict(pipeline.view(edition, "pdf"))
    sample = dict(pipeline.view(edition, "sample"))
    assert set(sample) == set(full) - (edition.scripture - set(policy.sample))

    # Stasis rules and kathisma headings belong to the next chapter; assembly
    # groups them with the preceding one. Their selection is checked in
    # test_psalter.
    def without_divisions(doc: Document) -> Document:
        return usj.with_blocks(
            doc,
            [b for b in doc["content"] if b.get("marker") not in {"sd1", "sd2", "ms1"}],
        )

    for code, chapters in policy.sample.items():
        _, wanted = assembly.chapters_of(without_divisions(sample[code]))
        assert [int(blocks[0]["number"]) for blocks in wanted] == sorted(chapters)
        whole = {
            blocks[0]["number"]: blocks
            for blocks in assembly.chapters_of(without_divisions(full[code]))[1]
        }
        for blocks in wanted:
            number = int(blocks[0]["number"])
            expected = whole[str(number)]
            assert blocks == expected, code
    # A heading set before a chapter is kept with it.
    daniel = usj.serialize(sample["DAG"])
    assert daniel.count("\\c 0\n\\cp ​\n\\cl Susanna\n") == 1
    # A chapter's own closing note stays with it: Psalm 71 ends in the
    # Hebrew note that holds its last verse.
    close = "\\q1\n\\v 20 The hymns of David the son of Jesse are ended.\n"
    psalms = edition.documents["PSA"]
    assert usj.serialize(pipeline.sample_chapters("PSA", psalms, [71])).endswith(close)
    assert close not in usj.serialize(pipeline.sample_chapters("PSA", psalms, [72]))


def test_what_is_typeset_prints_margin_origins_and_bottom_callers(
    exported: dict[str, str], edition: bible.pipeline.Edition
) -> None:
    for code in edition.scripture:
        text = exported[code]
        # A note in the margin has no caller: any, "*" as well as "+", would
        # stand in the text. A note at the foot of the page has its number.
        assert not re.search(r"\\x (?!- )", text), code
        assert not re.search(r"\\f (?![-+] )", text), code
        assert "\\ef " not in text, code
        # The chapter is the page's to supply: an origin is its verse alone.
        assert not re.search(r"\\(?:fr|xo) \d+:", text), code
        for note in re.findall(r"\\f \+ (.*?)\\f\*", text, re.DOTALL):
            assert not re.search(r"\\(?:fr|xo) ", note), (code, note)
    assert (
        r"\f + \cat edition\cat*\fq even fire, that it should come down from heaven upon the earth: "
    ) in exported["REV"]
    # Supplied verses within the Complutensian note keep their own labels.
    passage = next(
        line for line in exported["EXO"].splitlines() if "Complutensian" in line
    )
    exodus = usj.parse("\\id EXO\n\\c 28\n\\p\n" + passage)
    complutensian = next(
        note
        for note in usj.notes_of(exodus["content"])
        if "Complutensian" in usj.text_of(note["content"])
    )
    assert [
        usj.text_of(part["content"])
        for part in usj.walk(complutensian["content"])
        if part.get("marker") == "fv"
    ] == [str(number) for number in range(23, 29)]
    # Front matter's notes are numbered, and print under their callers alone.
    assert "\\f + \\ft See Preface to Lambert Bos’s edition" in exported["XXB"]
    # Greek and Hebrew are tagged for their fonts, single letters too: within
    # a note's words, and among a paragraph's.
    assert "\\+wg εἰς ὁμοιότητα\\+wg*" in exported["GEN"]
    assert "\\+wh רפאים\\+wh*" in exported["2SA"]


def test_greek_and_hebrew_are_set_in_the_styles_of_their_fonts() -> None:
    content = usj.parse("Gr. ἀλλʼ ἐγώ, \\it Heb.\\it* א, \\it or β\\it*", fragment=True)
    assert usj.serialize(export.font_runs(content)) == (
        "Gr. \\wg ἀλλ’ ἐγώ\\wg*, \\it Heb.\\it* \\wh א\\wh*, "
        "\\it or \\+wg β\\+wg*\\it*"
    )
    # Only the form of what prints changes.
    assert usj.text_of(export.font_runs(content)) == "Gr. ἀλλ’ ἐγώ, Heb. א, or β"


def test_authored_pages_select_fonts_in_body_notes_and_bibliography(
    edition: bible.pipeline.Edition,
) -> None:
    doc = usj.parse(
        "\\id INT\n\\mt1 Introduction\n"
        "\\p Greek ἐνέστηκεν and Hebrew א."
        "\\f + \\ft See Παλαιά Διαθήκη.\\f*\n"
        "\\li1 Παλαιά Διαθήκη.\n"
    )
    before = copy.deepcopy(doc)
    printed = export.document("introduction", doc, edition)
    text = usj.serialize(printed)
    assert "\\wg ἐνέστηκεν\\wg*" in text
    assert "\\wh א\\wh*" in text
    assert "\\+wg Παλαιά Διαθήκη\\+wg*" in text
    assert "\\wg Παλαιά Διαθήκη\\wg*" in text
    assert usj.text_of(printed["content"]) == usj.text_of(doc["content"])
    assert doc == before
    documents = {**edition.documents, "introduction": doc}
    [(_, online)] = [
        (unit, page)
        for unit, page in web.matter(edition, documents)
        if unit["id"] == "introduction"
    ]
    online_text = usj.serialize(online)
    assert "\\wg ἐνέστηκεν\\wg*" in online_text
    assert "\\wh א\\wh*" in online_text
    assert "\\+wg Παλαιά Διαθήκη\\+wg*" in online_text


def test_lines_that_go_on_with_a_verse_are_indented() -> None:
    doc = usj.parse(
        "\\id PSA\n\\c 1\n\\p \\v 1 He said:\n\\q1 One,\n\\q1 two.\n"
        "\\q1 \\v 2 Three,\n\\q1 four.\n\\b\n\\q1 five.\n"
    )
    markers = [b.get("marker") for b in pipeline.indented(doc)["content"]]
    assert markers == ["id", "c", "p", "q1", "q2", "q1", "q2", "b", "q1"]


def test_chapters_open_new_paragraphs_without_changing_internal_continuations() -> None:
    # Matthew 5 goes on with the paragraph before it, and Scrivener opens
    # each epistle flush left; a paragraph within a chapter keeps its marker.
    doc = usj.parse(
        "\\id MAT\n\\c 4\n\\p \\v 1 Prose.\n\\m and on.\n"
        "\\c 5\n\\nb \\v 1 Prose.\n\\c 6\n\\m \\v 1 Prose.\n"
    )
    before = copy.deepcopy(doc)
    opened = lines.opened(doc)
    assert doc == before
    assert [b.get("marker") for b in opened["content"]] == [
        "id",
        "c",
        "p",
        "m",
        "c",
        "p",
        "c",
        "p",
    ]
    assert scripture.verses(opened) == scripture.verses(doc)


def test_sample_keeps_the_full_editions_chapter_paragraphs() -> None:
    doc = usj.parse(
        "\\id ACT\n\\c 7\n\\p\\v 1 One.\n\\c 8\n\\nb\\v 1 Two.\n\\c 9\n\\nb\\v 1 Three."
    )
    doc = lines.opened(doc)
    consecutive = pipeline.sample_chapters("ACT", doc, [7, 8, 9])
    assert usj.serialize(consecutive).count("\\p") == 3
    excerpt = pipeline.sample_chapters("ACT", doc, [8, 9])
    assert usj.serialize(excerpt).count("\\p") == 2
    assert "\\c 8\n\\p\n" in usj.serialize(excerpt)


def spaced_markers(usfm: str) -> list[str | None]:
    return [b.get("marker") for b in export.spaced(usj.parse(usfm))["content"]]


def test_a_poem_within_prose_gets_a_blank_line_before_and_after_it() -> None:
    assert spaced_markers(
        "\\id PRO\n\\c 25\n\\p \\v 1 Prose.\n\\q1 \\v 2 Line,\n\\q1 line.\n"
        "\\p \\v 3 Prose again.\n"
    ) == ["id", "c", "p", "b", "q1", "q1", "b", "p"]


def test_a_blank_line_the_source_sets_before_a_poem_is_not_doubled() -> None:
    assert spaced_markers(
        "\\id SIR\n\\c 1\n\\p \\v 1 Prose.\n\\b\n\\q1 \\v 2 Line.\n"
    ) == ["id", "c", "p", "b", "q1"]


def test_a_colophon_follows_a_blank_line_the_page_can_discard() -> None:
    assert spaced_markers(
        "\\id ROM\n\\c 16\n\\p \\v 27 Amen.\n"
        "\\esb \\cat colophon\\cat*\n\\p Written to the Romans.\n\\esbe\n"
    ) == ["id", "c", "p", "b", "esb"]


def test_a_pause_supplies_the_break_before_the_next_poetic_line() -> None:
    assert spaced_markers(
        "\\id PSA\n\\c 33\n\\q1 \\v 11 The rich have become poor and hungry:\n"
        "\\q1 but they that seek the Lord diligently shall not want any good thing.\n"
        "\\qr Pause.\n\\b\n\\q1 \\v 12 Come, ye children, hear me:\n"
        "\\q1 I will teach you the fear of the Lord.\n"
        "\\b\n\\q1 \\v 13 What man is there that desireth life,\n"
        "\\qr Pause.\n\\b\n\\p \\v 14 Prose.\n"
    ) == ["id", "c", "q1", "q1", "qr", "q1", "q1", "b", "q1", "qr", "p"]


def test_a_title_leads_directly_into_its_poem() -> None:
    # Chapters and titles already mark boundaries; no blank paragraph pads
    # them or separates a title from its poem.
    assert spaced_markers(
        "\\id PSA\n\\c 3\n\\q1 \\v 1 Line.\n\\c 4\n\\d \\v 1 A Psalm.\n"
        "\\b\n\\q1 \\v 2 Line.\n\\c 5\n\\d \\v 1 A Psalm.\n\\p \\v 2 Prose.\n"
    ) == ["id", "c", "q1", "c", "d", "q1", "c", "d", "p"]


def test_labelled_chapters_supply_their_own_space() -> None:
    assert spaced_markers(
        "\\id PSA\n\\cl Psalm\n\\c 1\n\\q1 \\v 1 Line.\n"
        "\\c 2\n\\d \\v 1 A Psalm.\n\\q1 \\v 2 Line.\n"
        "\\b\n\\c 3\n\\d \\v 1 A Psalm.\n\\q1 \\v 2 Line.\n\\p \\v 3 Prose.\n\\c 4\n\\q1 \\v 1 Line.\n"
    ) == [
        "id",
        "cl",
        "c",
        "q1",
        "c",
        "d",
        "q1",
        "c",
        "d",
        "q1",
        "b",
        "p",
        "b",
        "c",
        "q1",
    ]


def test_a_title_within_a_chapter_supplies_its_own_space() -> None:
    # Esaias 21:11 opens a passage with a title within its chapter, and
    # Psalm 71 closes with one.
    assert spaced_markers(
        "\\id ISA\n\\c 21\n\\p \\v 10 Prose.\n\\d \\v 11 A Vision.\n\\p Prose.\n"
        "\\c 22\n\\q1 \\v 1 Line.\n\\b\n\\d \\v 2 The hymns are ended.\n"
    ) == ["id", "c", "p", "d", "p", "b", "c", "q1", "d"]


def test_chapter_boundaries_get_blanks_only_at_prose_poetry_transitions() -> None:
    assert spaced_markers(
        "\\id PRO\n\\c 8\n\\q1 \\v 1 Line.\n\\c 9\n\\q1 \\v 1 Line.\n"
        "\\c 10\n\\p \\v 1 Prose.\n\\c 11\n\\p \\v 1 Prose.\n"
    ) == ["id", "c", "q1", "c", "q1", "b", "c", "p", "c", "p"]


@pytest.mark.parametrize("before,after", [("p", "q1"), ("q1", "p")])
@pytest.mark.parametrize(
    "left,right", [("", ""), ("\\b\n", ""), ("", "\\b\n"), ("\\b\n", "\\b\n")]
)
def test_chapter_transition_has_one_blank_before_the_chapter(
    before: str, after: str, left: str, right: str
) -> None:
    assert spaced_markers(
        f"\\id TST\n\\c 1\n\\{before} \\v 1 Before.\n{left}"
        f"\\c 2\n{right}\\{after} \\v 1 After.\n"
    ) == ["id", "c", before, "b", "c", after]


@pytest.mark.parametrize("code,chapter", [("DEU", "32"), ("2SA", "2")])
def test_poetry_transitions_across_real_chapters(
    prepared: list[tuple[str, Document]], code: str, chapter: str
) -> None:
    blocks = dict(prepared)[code]["content"]
    at = next(
        i
        for i, block in enumerate(blocks)
        if usj.is_type(block, "chapter") and block["number"] == chapter
    )
    assert usj.paragraph(blocks[at - 1]) == "b"
    assert usj.paragraph(blocks[at - 2]) in (usj.PROSE if code == "DEU" else usj.POEM)
    assert usj.paragraph(blocks[at + 1]) == ("q1" if code == "DEU" else "p")


def test_headings_and_rules_supply_their_own_space() -> None:
    assert spaced_markers(
        "\\id PSA\n\\ms1 The First Kathisma\n\\c 1\n\\q1 \\v 1 Line.\n"
        "\\sd2\n\\c 4\n\\d \\v 1 A Psalm.\n\\q1 \\v 2 Line.\n"
        "\\b\n\\s2 Second Stasis\n\\q1 \\v 3 Line.\n"
        "\\ms1 The Second Kathisma\n\\c 9\n\\d \\v 1 A Psalm.\n\\q1 \\v 2 Line.\n"
    ) == [
        "id",
        "ms1",
        "c",
        "q1",
        "sd2",
        "c",
        "d",
        "q1",
        "s2",
        "q1",
        "ms1",
        "c",
        "d",
        "q1",
    ]


def test_the_psalter_alone_carries_one_chapter_label(exported: dict[str, str]) -> None:
    psalms = exported["PSA"]
    assert "\\h Psalm\n" in psalms
    assert "\\toc2 Psalms\n" in psalms
    assert psalms.count("\\cl ") == 1
    assert "\\cl Psalm\n\\c 1\n" in psalms
    assert all(
        "\\cl " not in text
        for code, text in exported.items()
        if code not in {"PSA", "DAG", "SIR"}
    )


def test_a_title_keeps_the_marking_of_its_supplied_words(
    exported: dict[str, str],
) -> None:
    # Psalm 4's title supplies "the", and Sirach's prologue heading most of
    # its words; the stylesheet sets them in the title's italic.
    psalms = exported["PSA"]
    assert (
        "\\v 1 For the end, a Song of David among \\add the \\add*Psalms.\n" in psalms
    )
    assert (
        "\\imt1 \\add The Prologue to the Wisdom of\\add* Jesus \\add the son of\\add* Sirach\n"
        in exported["SIR"]
    )
    assert "\\v 3 \\add saying\\add*, Let us break through their bonds," in psalms


@pytest.mark.parametrize(
    "marks", [",", ";", ":", ".", "?", "!", ",;:", ",;:.?!", ".,;:", "?,:", "!,;:"]
)
def test_punctuation_before_a_dash_across_styles(
    policy: bible.policy.Policy, marks: str
) -> None:
    doc = usj.parse(f"\\id GEN\n\\c 1\n\\p\n\\v 1 Word{marks}\\it —more\\it*.")
    before = copy.deepcopy(doc)
    met: revision.MetRevisions = set()
    result = revision.punctuated(doc, policy, met)
    expected = re.sub(r"[,;:]+$", "", marks)
    assert scripture_text(result) == f"Word{expected}—more."
    assert "\\it —more\\it*" in usj.serialize(result)
    assert doc == before
    assert revision.punctuated(result, policy, set()) == result
    assert met == ({"before-em-dash"} if expected != marks else set())


def scripture_text(doc: usj.Document) -> str:
    return usj.text_of(doc["content"][2]["content"])


def test_punctuation_in_notes_and_matter(policy: bible.policy.Policy) -> None:
    doc = usj.parse(
        "\\id GEN\n\\ip Preface:—words.\n\\c 1\n\\p\n\\v 1 Word,\\f - \\fr 1:1 \\fq Word,—more: \\ft Gr. Witness;—reading.\\f*—more."
    )
    note = usj.notes_of(doc["content"])[0]
    note.update({"x-key": "GEN 1:1#1"})
    before = copy.deepcopy(doc)
    result = revision.punctuated(doc, policy, set())
    assert "Preface—words." in usj.serialize(result)
    new_note = usj.notes_of(result["content"])[0]
    assert new_note["x-key"] == note["x-key"]
    assert usj.text_of(new_note["content"]) == "1:1 Word—more: Gr. Witness—reading."
    assert doc == before


def test_dash_rule_respects_boundaries_and_foreign_words(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 End,\n\\v 2 —start, —spaced;–en.—?! after,‘—quote [,—bracket] λόγος\\it ,—\\it* שָׁלוֹם.— λόγος.,— שָׁלוֹם?.:— \\wg λόγος,—\\wg* \\it \\+wh שָׁלוֹם.—\\+wh*\\it*.\n\\p —paragraph.\n\\tr \\tc1 Cell, \\tc2 —next"
    )
    before = copy.deepcopy(doc)
    result = revision.punctuated(doc, policy, set())
    assert "—?! after,‘—quote [—bracket]" in usj.serialize(result)
    assert "λόγος\\it ,—\\it* שָׁלוֹם.—" in usj.serialize(result)
    assert "\\wg λόγος,—\\wg*" in usj.serialize(result)
    assert "\\+wh שָׁלוֹם.—\\+wh*" in usj.serialize(result)
    assert "λόγος.,— שָׁלוֹם?.:—" in usj.serialize(result)
    assert "End," in usj.serialize(result)
    assert "Cell," in usj.serialize(result)
    assert ", —spaced;–en.—" in usj.serialize(result)
    assert doc == before


@pytest.mark.parametrize(
    "verse",
    ["\\wg λόγος\\wg*,—and", "\\it \\+wg λόγος\\+wg*,—and\\it*"],
)
def test_punctuation_after_a_tagged_foreign_word_is_refused(
    policy: bible.policy.Policy, verse: str
) -> None:
    doc = usj.parse(f"\\id GEN\n\\c 1\n\\p\n\\v 1 The word {verse} more.")
    with pytest.raises(CheckFailed, match="tagged foreign word: GEN: ,—and"):
        revision.punctuated(doc, policy, set())


def test_punctuation_that_leaves_a_lemma_is_refused(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 O king,\\f + \\fq O king, \\ft Or, lord.\\f*—the eyes."
    )
    with pytest.raises(CheckFailed, match="lemma .* GEN 1:1: O king,"):
        revision.punctuated(doc, policy, set())


@pytest.mark.parametrize(
    "rule",
    [
        {"unknown": {"why": "x"}},
        {"before-em-dash": {"why": ""}},
        {"before-em-dash": {"why": "x", "from": ","}},
    ],
)
def test_bad_punctuation_rules_are_refused(
    policy: bible.policy.Policy, rule: dict[str, Any]
) -> None:
    with pytest.raises(CheckFailed):
        revision.check(revisions(policy, punctuation=rule))


def test_unused_punctuation_rule_is_refused(policy: bible.policy.Policy) -> None:
    policy = revisions(policy, punctuation={"before-em-dash": {"why": "x"}})
    met: revision.MetRevisions = set()
    revision.punctuated(usj.parse("\\id GEN\n\\ip Nothing, —adjacent."), policy, met)
    with pytest.raises(CheckFailed, match="before-em-dash"):
        revision.check_met(policy, met)


def test_brackets_go_from_the_text_but_not_from_a_note(
    policy: bible.policy.Policy,
) -> None:
    policy = revisions(policy, punctuation={revision.BRACKETS: {"why": "x"}})
    doc = usj.parse(
        "\\id ESG\n\\c 1\n\\p [\\sc In\\sc* the year, Mardochæus\\f + \\fr 1:1 "
        "\\ft 'the morning [spread] upon' (\\fqa Heb.\\ft )\\f* the \\add son\\add*"
        "\n\\v 1a of Jairus\n\\c 2\n\\p\n\\v 1 dreamed]: and [he said], [Lo]."
    )
    met: revision.MetRevisions = set()
    result = revision.unbracketed(doc, policy, met)
    assert met == {revision.BRACKETS}
    text = usj.serialize(result)
    assert "\\p \\sc In\\sc* the year, Mardochæus\\f + " in text
    assert "\\v 1 dreamed: and he said, Lo." in text
    assert "'the morning [spread] upon'" in text
    # The spans close chapters later, so they must pair across the book,
    # one at a time and in order.
    for unpaired in ("[In the year.", "In] the [year.", "[In [the] year.]"):
        with pytest.raises(CheckFailed, match="do not pair"):
            revision.unbracketed(
                usj.parse(f"\\id ESG\n\\c 1\n\\p\n\\v 1 {unpaired}"), policy, met
            )
    # One between letters would join two words, and is refused.
    with pytest.raises(CheckFailed, match="between letters"):
        revision.unbracketed(
            usj.parse("\\id ESG\n\\c 1\n\\p\n\\v 1 [In the]year."), policy, met
        )
    # A book without them is shared, and the rule is not met by it.
    unchanged = usj.parse("\\id GEN\n\\c 1\n\\p\n\\v 1 In the beginning.")
    assert revision.unbracketed(unchanged, policy, set()) is unchanged
    # The rule applies by decision.
    assert revision.unbracketed(doc, revisions(policy, punctuation={}), met) is doc


def test_brackets_in_a_book_the_hebrew_lacks_are_supplied_words(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id SIR\n\\c 6\n\\p\n\\v 2 for [thereby] thou\\f + \\fr 6:2 \\ft [sic]\\f* "
        "\\add shalt\\add* inherit [an ill name]."
    )
    text = usj.serialize(bible.pipeline.bracketed("SIR", doc, policy))
    assert "\\v 2 for \\add thereby\\add* thou\\f + \\fr 6:2 \\ft [sic]\\f*" in text
    assert "inherit \\add an ill name\\add*." in text
    # The rule that drops the others decides these too.
    unruled = revisions(policy, punctuation={})
    assert bible.pipeline.bracketed("SIR", doc, unruled) is doc
    # In a book the Hebrew has, they are left for revision to drop.
    doc = usj.parse("\\id GEN\n\\c 35\n\\p\n\\v 16 [And Jacob removed,] and")
    assert bible.pipeline.bracketed("GEN", doc, policy) is doc
    # A span the read cannot take for a run of words is refused.
    with pytest.raises(CheckFailed, match="more than a run of words"):
        bible.pipeline.bracketed(
            "SIR",
            usj.parse("\\id SIR\n\\c 6\n\\p\n\\v 2 for [thereby\n\\v 3 thou]"),
            policy,
        )


BEFORE, INSIDE = "before-parenthesis", "inside-parenthesis"


@pytest.mark.parametrize(
    ("verse", "expected", "rules"),
    [
        ("Word, (aside) more.", "Word (aside) more.", {BEFORE}),
        ("Word; (aside,) more.", "Word (aside), more.", {BEFORE, INSIDE}),
        ("Word:(aside;) more.", "Word(aside); more.", {BEFORE, INSIDE}),
        ("Word, (aside,:) more.", "Word (aside),: more.", {BEFORE, INSIDE}),
        ("Word, (aside:)—more.", "Word (aside)—more.", {BEFORE, INSIDE}),
        ("Word, (aside.) More.", "Word (aside.) More.", {BEFORE}),
        ("Word, (aside?) more.", "Word (aside?) more.", {BEFORE}),
        ("Word, (aside!) more.", "Word (aside!) more.", {BEFORE}),
        ("Word. (Aside.) More.", "Word. (Aside.) More.", set()),
        ("Word, (λόγος,) more.", "Word (λόγος,) more.", {BEFORE}),
        # A moved mark is read by the rules after the move.
        ("Word (a,) (bee) more.", "Word (a) (bee) more.", {BEFORE, INSIDE}),
        ("Word (bee,) (39) more.", "Word (bee), (39) more.", {INSIDE}),
        ("Word (a,);—more.", "Word (a)—more.", {"before-em-dash", INSIDE}),
        ("Word (a (b,)) more.", "Word (a (b)), more.", {INSIDE}),
    ],
)
def test_punctuation_beside_parentheses(
    policy: bible.policy.Policy, verse: str, expected: str, rules: set[str]
) -> None:
    doc = usj.parse(f"\\id GEN\n\\c 1\n\\p\n\\v 1 {verse}")
    before = copy.deepcopy(doc)
    met: revision.MetRevisions = set()
    result = revision.punctuated(doc, policy, met)
    assert scripture_text(result) == expected
    assert doc == before
    assert revision.punctuated(result, policy, set()) == result
    assert met == rules


@pytest.mark.parametrize(
    "usfm",
    [
        # A mark already stands where the run would move.
        "\\c 1\n\\p\n\\v 1 Word (aside,); more.",
        "\\c 1\n\\p\n\\v 1 Word (aside,). More.",
        # The "Or," of an alternative.
        "\\c 1\n\\p\n\\v 1 Word.\\f + \\fr 1:1 \\ft Or, (as some read) smoke.\\f*",
        # A join across a heading, a chapter's heading, or onto an introduction.
        "\\c 1\n\\p\n\\v 1 He said:\n\\s1 Head\n\\p\n\\v 2 (Aside.)",
        "\\c 1\n\\p\n\\v 1 He said:\n\\c 2\n\\s1 Head\n\\p\n\\v 1 (Aside.)",
        "\\c 1\n\\p\n\\v 1 He said:\n\\ip (An introduction.)",
    ],
)
def test_punctuation_not_understood_is_refused(
    policy: bible.policy.Policy, usfm: str
) -> None:
    doc = usj.parse(f"\\id GEN\n{usfm}")
    with pytest.raises(CheckFailed, match="to be decided"):
        revision.punctuated(doc, policy, set())


@pytest.mark.parametrize("marker", ["39", "1", "a"])
@pytest.mark.parametrize("marks", [",", ";", ":"])
def test_punctuation_before_reference_and_list_markers_stays(
    policy: bible.policy.Policy, marker: str, marks: str
) -> None:
    doc = usj.parse(
        f"\\id GEN\n\\ip These{marks} ({marker}) one, (2) two."
        f"\n\\c 1\n\\p\n\\v 1 Word{marks}\\it ({marker})\\it* more."
        f" \\wg λόγος\\wg*{marks} ({marker}) more."
        "\\f - \\fr 1:1 \\fq Word: \\ft Alex. adds "
        f"\\fqa words{marks} \\ft \\+it ({marker}) and more\\+it*\\f*"
    )
    usj.notes_of(doc["content"])[0]["x-key"] = "GEN 1:1"
    before = copy.deepcopy(doc)
    met: revision.MetRevisions = set()
    result = revision.punctuated(doc, policy, met)
    assert result == before
    assert doc == before
    assert met == set()
    assert revision.punctuated(result, policy, set()) == result


@pytest.mark.parametrize("marker", ["39", "a"])
@pytest.mark.parametrize(
    "boundary",
    [
        "\n\\q1\n",
        "\n\\q1\n\\v 2 ",
        "\n\\c 2\n\\p\n\\v 1 ",
        "\n\\s1 Heading\n\\p\n\\v 2 ",
    ],
)
def test_reference_and_list_markers_do_not_join_lines_or_verses(
    policy: bible.policy.Policy, marker: str, boundary: str
) -> None:
    doc = usj.parse(
        "\\id JOB\n\\c 1\n\\q1\n\\v 1 Words;"
        "\\f + \\fr 1:1 \\ft A note.\\f*"
        f"{boundary}\\it ({marker})\\it* more."
    )
    before = copy.deepcopy(doc)
    met: revision.MetRevisions = set()
    result = revision.punctuated(doc, policy, met)
    assert result == before
    assert doc == before
    assert met == set()
    assert revision.punctuated(result, policy, set()) == result


def test_mark_ending_a_chapter_before_a_parenthesis(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse("\\id GEN\n\\c 1\n\\p\n\\v 1 He said:\n\\c 2\n\\p\n\\v 1 (Aside.)")
    result = revision.punctuated(doc, policy, set())
    assert scripture.plain(scripture.verses(result)["1:1"].text) == "He said"


def test_parenthesis_marks_keep_their_styles_and_notes(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 Word,\\f + \\fr 1:1 \\ft Note, (aside;) more.\\f*"
        " (\\add aside\\add*,) more;\\it (again:)\\it* on."
    )
    before = copy.deepcopy(doc)
    result = revision.punctuated(doc, policy, set())
    assert usj.serialize(result).endswith(
        "\\v 1 Word\\f + \\fr 1:1 \\ft Note (aside); more.\\f*"
        " (\\add aside\\add*), more\\it (again):\\it* on.\n"
    )
    assert doc == before


def test_mark_ending_a_verse_before_a_parenthesis(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id JOB\n\\c 1\n\\q1\n\\v 1 If one:\n\\q1\n\\v 2 (for two:)\n\\p\n"
        "\\v 3 then three,\\f + \\fr 1:3 \\ft Note.\\f*\n\\v 4 (and four.) Five;\n"
        "\\p\n\\v 5 (Six.) Seven: \\v 6 λόγος; \\v 7 (eight,) \\v 8 (nine.)"
    )
    before = copy.deepcopy(doc)
    met: revision.MetRevisions = set()
    result = revision.punctuated(doc, policy, met)
    assert {
        reference: scripture.plain(verse.text)
        for reference, verse in scripture.verses(result).items()
    } == {
        "1:1": "If one",
        "1:2": "(for two):",
        "1:3": "then three",
        "1:4": "(and four.) Five",
        "1:5": "(Six.) Seven:",
        "1:6": "λόγος;",
        "1:7": "(eight)",
        "1:8": "(nine.)",
    }
    assert "then three\\f + \\fr 1:3 \\ft Note.\\f*" in usj.serialize(result)
    assert met == {"before-parenthesis", "inside-parenthesis"}
    assert doc == before
    assert revision.punctuated(result, policy, set()) == result


def test_parenthesis_mark_after_a_tagged_foreign_word_is_refused(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse("\\id GEN\n\\c 1\n\\p\n\\v 1 The word (\\wg λόγος\\wg*,) more.")
    with pytest.raises(CheckFailed, match=r"tagged foreign word: GEN: ,\) more"):
        revision.punctuated(doc, policy, set())


@pytest.mark.parametrize(
    ("ending", "expected"),
    [("heard;", "heard"), ("λόγος;", "λόγος;")],
)
def test_parenthesis_after_a_poetry_line(
    policy: bible.policy.Policy, ending: str, expected: str
) -> None:
    doc = usj.parse(
        f"\\id JOB\n\\c 33\n\\q1\n\\v 8 I {ending}"
        "\\f + \\fr 33:8 \\ft Note.\\f*\n\\q1\n(in mine ears;) more."
    )
    before = copy.deepcopy(doc)
    result = revision.punctuated(doc, policy, set())
    assert (
        scripture.verses(result)["33:8"].text == f"I {expected}\n(in mine ears); more."
    )
    assert "\\fr 33:8 \\ft Note.\\f*" in usj.serialize(result)
    assert [b["marker"] for b in result["content"] if b["type"] == "para"] == [
        "q1",
        "q1",
    ]
    assert doc == before
    assert revision.punctuated(result, policy, set()) == result


@pytest.mark.parametrize("boundary", ["\n\\q1\n", " \\v 9 "])
def test_tagged_foreign_word_before_a_parenthesis_across_boundaries(
    policy: bible.policy.Policy, boundary: str
) -> None:
    doc = usj.parse(
        "\\id JOB\n\\c 33\n\\q1\n\\v 8 \\wg λόγος\\wg*;" + boundary + "(aside) more."
    )
    with pytest.raises(CheckFailed, match="tagged foreign word"):
        revision.punctuated(doc, policy, set())


def test_poetry_line_punctuation_cannot_leave_a_lemma(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id JOB\n\\c 33\n\\q1\n\\v 8 I heard;"
        "\\f + \\fq heard; \\ft Or, listened.\\f*\n\\q1\n(aside) more."
    )
    with pytest.raises(CheckFailed, match="lemma .* JOB 33:8: heard;"):
        revision.punctuated(doc, policy, set())


@pytest.mark.parametrize("mark", [",", ":", ";"])
def test_closing_parenthesis_outside_supplied_words(
    policy: bible.policy.Policy, mark: str
) -> None:
    doc = usj.parse(
        "\\id ROM\n\\c 10\n\\p\n\\v 6 (that is, \\add to bring Christ down"
        + mark
        + "\\add*\\f + \\ft Note.\\f*) more."
    )
    before = copy.deepcopy(doc)
    result = revision.punctuated(doc, policy, set())
    assert usj.serialize(result).endswith(
        "\\v 6 (that is, \\add to bring Christ down\\add*"
        "\\f + \\ft Note.\\f*)" + mark + " more.\n"
    )
    assert doc == before
    assert revision.punctuated(result, policy, set()) == result


def test_acrostic_heading_periods_go_without_changing_other_punctuation(
    policy: bible.policy.Policy,
) -> None:
    policy = revisions(policy, punctuation={revision.ACROSTICS: {"why": "x"}})
    doc = usj.parse(
        "\\id LAM\n\\c 1\n\\qa \\v 1 Aleph.\n"
        "\\q1 Words.\\f + \\ft Aleph. is a name.\\f*\n"
        "\\qa \\v 2 Beth.\n\\q1 More words."
    )
    before = copy.deepcopy(doc)
    met: revision.MetRevisions = set()
    result = revision.punctuated(doc, policy, met)
    assert usj.serialize(result) == usj.serialize(doc).replace(
        "\\v 1 Aleph.", "\\v 1 Aleph"
    ).replace("\\v 2 Beth.", "\\v 2 Beth")
    assert met == {revision.ACROSTICS}
    assert doc == before
    assert revision.punctuated(result, policy, set()) == result


def test_an_acrostic_period_a_lemma_quotes_is_refused(
    policy: bible.policy.Policy,
) -> None:
    policy = revisions(policy, punctuation={revision.ACROSTICS: {"why": "x"}})
    doc = usj.parse(
        "\\id LAM\n\\c 1\n\\qa \\v 1 Aleph.\n"
        "\\q1 Words.\\f + \\fq Aleph. \\ft A letter.\\f*\n"
    )
    with pytest.raises(CheckFailed, match="lemma its verse no longer has: LAM 1:1"):
        revision.punctuated(doc, policy, set())


def test_an_acrostic_heading_that_is_no_name_is_refused(
    policy: bible.policy.Policy,
) -> None:
    policy = revisions(policy, punctuation={revision.ACROSTICS: {"why": "x"}})
    doc = usj.parse("\\id PSA\n\\c 1\n\\qa \\v 1 Aleph.\n\\q1 Words.")
    with pytest.raises(CheckFailed, match="Unexpected acrostic heading: PSA"):
        revision.punctuated(doc, policy, set())


def test_every_punctuation_rule_is_accepted(policy: bible.policy.Policy) -> None:
    rules = {
        name: {"why": "x"}
        for name in (*revision.RULES, revision.BRACKETS, revision.ACROSTICS)
    }
    revision.check(revisions(policy, punctuation=rules))


def test_the_edition_prints_no_brackets_of_brentons(
    edition: bible.pipeline.Edition,
) -> None:
    # The additions to Esther, a verse the Hebrew lacks, and the Authorized
    # Version's supplied words in the Apocrypha, which Brenton brackets.
    assert scripture.verses(edition.documents["ESG"])["1:1a"].text.startswith(
        "In the second year"
    )
    assert "crooked:" in scripture.verses(edition.documents["PRO"])["4:27a"].text
    assert "for thereby thou" in scripture.verses(edition.documents["SIR"])["6:1"].text
    for code in edition.scripture:
        for block in edition.documents[code]["content"]:
            if "content" in block:
                text = usj.text_of(block["content"])
                assert "[" not in text and "]" not in text, code

    # In a book the Hebrew lacks, they are the translators' supplied words.
    doc = edition.documents["SIR"]
    assert [
        usj.text_of(node["content"])
        for index, lo, hi, _ in scripture.verses(doc)["6:1"].parts
        for node in usj.walk(doc["content"][index]["content"][lo:hi])
        if usj.is_type(node, "char", "add")
    ] == ["thereby"]
    # The notes that explained what the Hebrew lacks by the brackets say it of
    # their words instead.
    verse = scripture.verses(edition.documents["GEN"])["35:16"]
    assert usj.text_of(verse.notes[0][1]["content"]).endswith(
        "And Jacob removed from Bethel, and pitched his tent beyond the tower of "
        "Gader: Heb. has these words as verse 21."
    )
    verse = scripture.verses(edition.documents["2SA"])["21:11"]
    assert usj.text_of(verse.notes[0][1]["content"]).endswith(
        "the offspring of the giants overtook them: Heb. omits"
    )
    # Where the passage runs over verses, the note names them and has no lemma.
    for reference, said in (
        ("3:13a", "Heb. omits verses 13a–13g"),
        ("4:17a", "Heb. omits verses 4:17a–5:2b"),
    ):
        verse = scripture.verses(edition.documents["ESG"])[reference]
        (_, note), *_ = verse.notes
        assert usj.text_of(note["content"]).endswith(said)
        assert not [
            n for n in usj.walk(note["content"]) if usj.is_type(n, "char", "fq")
        ]
    # The brackets that marked something else go too: Exodus 5:14's supplied
    # words, which the read marks and the note explains, and Judges 1:10's
    # parenthesis, which the 1844 printing does without.
    doc = edition.documents["EXO"]
    verse = scripture.verses(doc)["5:14"]
    assert "scourged, and questioned, men saying" in verse.text
    assert "and questioned" in [
        usj.text_of(node["content"])
        for index, lo, hi, _ in verse.parts
        for node in usj.walk(doc["content"][index]["content"][lo:hi])
        if usj.is_type(node, "char", "add")
    ]
    assert any(
        "and questioned: supplied from the Hebrew" in usj.text_of(note["content"])
        for _, note in verse.notes
    )
    assert (
        "against him; and the name of Hebron before was Cariatharbocsepher: and they"
        in scripture.verses(edition.documents["JDG"])["1:10"].text
    )
    # A note's own bracket, Brenton quoting the Authorized Version, stays.
    verse = scripture.verses(edition.documents["ISA"])["52:7"]
    assert any("[spread]" in usj.text_of(note["content"]) for _, note in verse.notes)


def passage_group(*changes: dict[str, str]) -> dict[str, Any]:
    return {
        "dashes": {
            "why": "The explanation continues after the dash.",
            "changes": changes,
        }
    }


def test_passage_revisions_keep_styles_metadata_and_inputs(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 Text.\\f - \\fr 1:1 \\ft a \\it note.\\it*—The words.\\f*"
    )
    note = usj.notes_of(doc["content"])[0]
    note.update(
        {"x-key": "GEN 1:1#1", "x-scope": {"lemma": "Text"}, "category": "edition"}
    )
    before = copy.deepcopy(doc)
    change = {"note": "GEN 1:1#1", "from": "note.—The words", "to": "note—The words"}
    initial = {"note": "GEN 1:1#1", "from": "a ", "to": "A "}
    rules = revisions(policy, passages=passage_group(change, initial))
    revision.check(rules)
    met: revision.MetRevisions = set()
    result = revision.passages("GEN", doc, rules, met)
    after = usj.notes_of(result["content"])[0]
    assert {k: v for k, v in after.items() if k != "content"} == {
        k: v for k, v in note.items() if k != "content"
    }
    assert "\\+it note\\+it*—The words" in usj.serialize(result)
    assert doc == before
    assert usj.text_of(after["content"]).startswith("1:1 A note")
    assert met == {("GEN 1:1#1", "note.—The words"), ("GEN 1:1#1", "a ")}
    revision.check_met(rules, met)


def test_passage_revisions_in_matter_and_capitalization(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id XXB\n\\ip Word. \\it more\\it*;—and another.\n\\ip Word.—Elsewhere."
    )
    before = copy.deepcopy(doc)
    change = {"unit": "XXB", "from": "more;—and", "to": "more. And"}
    rules = revisions(policy, passages=passage_group(change))
    revision.check(rules)
    result = revision.passages("XXB", doc, rules, set())
    assert "\\it more\\it*. And another." in usj.serialize(result)
    assert "Word.—Elsewhere." in usj.serialize(result)
    assert doc == before
    invalid = revisions(
        policy,
        passages=passage_group({"unit": "XXB", "from": "another", "to": "Another"}),
    )
    revision.check(invalid)
    with pytest.raises(CheckFailed, match="noninitial capitalization"):
        revision.passages("XXB", doc, invalid, set())


def test_keyed_note_fragments_can_lower_initials_across_semantic_runs(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 Text.\\f - \\fr 1:1 \\fq Text: "
        "\\ft Gr. \\fqa Ancient\\ft . Or, \\fqa everlasting\\ft ; so the Heb.\\f*"
    )
    note = usj.notes_of(doc["content"])[0]
    note["x-key"] = "GEN 1:1"
    before = copy.deepcopy(doc)
    change = {"note": "GEN 1:1", "from": "Ancient. Or,", "to": "ancient, or,"}
    rules = revisions(policy, passages=passage_group(change))
    revision.check(rules)
    met: revision.MetRevisions = set()
    result = revision.passages("GEN", doc, rules, met)
    revised = usj.notes_of(result["content"])[0]
    assert usj.text_of(revised["content"]) == (
        "1:1 Text: Gr. ancient, or, everlasting; so the Heb."
    )
    assert [
        usj.text_of(n["content"])
        for n in usj.walk(revised["content"])
        if usj.is_type(n, "char", "fqa")
    ] == ["ancient", "everlasting"]
    assert doc == before
    revision.check_met(rules, met)


@pytest.mark.parametrize(
    "old,new",
    [
        ("Ancient", "different"),
        ("McDonald", "Mcdonald"),
        ("ancient trees", "ancient Trees"),
        ("1-18", "1–19"),
        ("a1-18b", "a1–18b"),
    ],
)
def test_note_capitalization_cannot_change_words_or_internal_case(
    policy: bible.policy.Policy, old: str, new: str
) -> None:
    doc = usj.parse("\\id GEN\n\\c 1\n\\p\n\\v 1 Text.\\f - \\ft Gr. " + old + "\\f*")
    usj.notes_of(doc["content"])[0]["x-key"] = "GEN 1:1"
    rules = revisions(
        policy, passages=passage_group({"note": "GEN 1:1", "from": old, "to": new})
    )
    with pytest.raises(CheckFailed, match="capitalization"):
        revision.check(rules)
        revision.passages("GEN", doc, rules, set())


def test_note_number_ranges_can_use_an_en_dash(policy: bible.policy.Policy) -> None:
    doc = usj.parse("\\id GEN\n\\c 1\n\\p\n\\v 1 Text.\\f - \\ft Numbered 1-18.\\f*")
    usj.notes_of(doc["content"])[0]["x-key"] = "GEN 1:1"
    before = copy.deepcopy(doc)
    rules = revisions(
        policy,
        passages=passage_group({"note": "GEN 1:1", "from": "1-18", "to": "1–18"}),
    )
    revision.check(rules)
    met: revision.MetRevisions = set()
    result = revision.passages("GEN", doc, rules, met)
    assert usj.text_of(usj.notes_of(result["content"])[0]["content"]) == (
        "Numbered 1–18."
    )
    assert scripture.verses(result)["1:1"].text == scripture.verses(doc)["1:1"].text
    assert doc == before
    revision.check_met(rules, met)


@pytest.mark.parametrize(
    "spelling,old,new",
    [
        ("greek", "ἐπαξοοῦν", "ἐπαξονοῦν"),
        ("greek", "ἠχος", "ἦχος"),
        ("hebrew", "תנפה", "תְּנוּפָה"),
    ],
)
def test_foreign_spelling_is_confined_to_its_key_and_keeps_metadata(
    policy: bible.policy.Policy, spelling: str, old: str, new: str
) -> None:
    doc = usj.parse(
        f"\\id NUM\n\\c 1\n\\p\n\\v 18 Text.\\f - \\fr 1:18 \\ft English \\it {old}\\it*.\\f*"
        f"\n\\v 19 Other.\\f - \\fr 1:19 \\ft English {old}.\\f*"
    )
    notes = usj.notes_of(doc["content"])
    notes[0].update(
        {"x-key": "NUM 1:18", "x-scope": {"lemma": "Text"}, "category": "edition"}
    )
    notes[1]["x-key"] = "NUM 1:19"
    before = copy.deepcopy(doc)
    change = {"note": "NUM 1:18", "spelling": spelling, "from": old, "to": new}
    rules = revisions(policy, passages=passage_group(change))
    revision.check(rules)
    met: revision.MetRevisions = set()
    result = revision.passages("NUM", doc, rules, met)
    after = usj.notes_of(result["content"])
    assert usj.text_of(after[0]["content"]) == f"1:18 English {new}."
    assert f"\\+it {new}\\+it*" in usj.serialize(result)
    assert {k: v for k, v in after[0].items() if k != "content"} == {
        k: v for k, v in notes[0].items() if k != "content"
    }
    assert after[1] == notes[1]
    assert doc == before
    revision.check_met(rules, met)


def test_foreign_spelling_in_matter_can_share_a_paragraph_with_punctuation(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse("\\id XXE\n\\ip English ἐπαξοοῦν.—More.")
    rules = revisions(
        policy,
        passages=passage_group(
            {"unit": "XXE", "spelling": "greek", "from": "ἐπαξοοῦν", "to": "ἐπαξονοῦν"},
            {"unit": "XXE", "from": ".—More", "to": "—More"},
        ),
    )
    revision.check(rules)
    result = revision.passages("XXE", doc, rules, set())
    assert usj.text_of(result["content"]) == "English ἐπαξονοῦν—More."


def test_foreign_spelling_can_share_a_note_with_lowercase_fragments(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id NUM\n\\c 1\n\\p\n\\v 18 Text.\\f - \\fr 1:18 " "\\ft Greek ἐπαξοοῦν.\\f*"
    )
    usj.notes_of(doc["content"])[0]["x-key"] = "NUM 1:18"
    rules = revisions(
        policy,
        passages=passage_group(
            {"note": "NUM 1:18", "from": "Greek", "to": "greek"},
            {
                "note": "NUM 1:18",
                "spelling": "greek",
                "from": "ἐπαξοοῦν",
                "to": "ἐπαξονοῦν",
            },
        ),
    )
    revision.check(rules)
    met: revision.MetRevisions = set()
    result = revision.passages("NUM", doc, rules, met)
    assert usj.text_of(usj.notes_of(result["content"])[0]["content"]) == (
        "1:18 greek ἐπαξονοῦν."
    )
    revision.check_met(rules, met)


def test_foreign_spelling_sets_letters_before_a_word_in_its_style(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id NUM\n\\c 1\n\\p\n\\v 18 Text.\\f - \\fr 1:18 \\fqa Alex. "
        "\\ft ὑρετῆ, or \\it μαρτία\\it* or λέγε.\\f*"
    )
    usj.notes_of(doc["content"])[0]["x-key"] = "NUM 1:18"
    rules = revisions(
        policy,
        passages=passage_group(
            {"note": "NUM 1:18", "spelling": "greek", "from": "ὑρετῆ", "to": "εὑρετῆ"},
            {
                "note": "NUM 1:18",
                "spelling": "greek",
                "from": "μαρτία",
                "to": "ἁμαρτία",
            },
            {"note": "NUM 1:18", "spelling": "greek", "from": "λέγε.", "to": "λέγει."},
        ),
    )
    revision.check(rules)
    result = usj.serialize(revision.passages("NUM", doc, rules, set()))
    assert "\\fqa Alex. \\ft εὑρετῆ, or \\+it ἁμαρτία\\+it* or λέγει.\\f*" in result


def test_foreign_spelling_reaches_the_parts_of_daniel(
    policy: bible.policy.Policy,
) -> None:
    change = {"note": "SUS 1:5", "spelling": "greek", "from": "λέγει", "to": "λέγε"}
    revision.check(revisions(policy, passages=passage_group(change)))


@pytest.mark.parametrize(
    "change,refusal",
    [
        (
            {"note": "MAT 1:1", "spelling": "greek", "from": "λέγει", "to": "λέγε"},
            "not Old Testament",
        ),
        (
            {
                "unit": "translators-preface",
                "spelling": "greek",
                "from": "λέγει",
                "to": "λέγε",
            },
            "not Old Testament",
        ),
        (
            {
                "note": "NUM 1:18",
                "spelling": "greek",
                "from": "English λέγει",
                "to": "Changed λέγε",
            },
            "changes other words",
        ),
        (
            {"note": "NUM 1:18", "spelling": "greek", "from": "λέγει", "to": "ל"},
            "changes other words",
        ),
        (
            {
                "note": "NUM 1:18",
                "spelling": "greek",
                "from": "λέγει",
                "to": "λέγει λέγε",
            },
            "changes other words",
        ),
        (
            {"note": "NUM 1:18", "spelling": "greek", "from": "λέγει.", "to": "λέγε!"},
            "changes other words",
        ),
        (
            {
                "note": "NUM 1:18",
                "spelling": "greek",
                "from": "λέγει",
                "to": "λέγει\u05b0",
            },
            "changes other words",
        ),
        (
            {"note": "NUM 1:18", "spelling": "greek", "from": "λέγει", "to": "_greek_"},
            "changes other words",
        ),
        (
            {
                "note": "NUM 1:18",
                "spelling": "greek",
                "from": "λέγει",
                "to": "\0greek\0",
            },
            "changes other words",
        ),
        (
            {
                "note": "NUM 1:18",
                "spelling": "greek",
                "from": "λέγει",
                "to": "\\it λέγε\\it*",
            },
            "changes other words",
        ),
        (
            {"note": "NUM 1:18", "spelling": "latin", "from": "word", "to": "words"},
            "Unknown passage spelling",
        ),
        (
            {
                "note": "NUM 1:18",
                "spelling": "greek",
                "from": "οἴκον",
                "to": "βασιλεία",
            },
            "more than one letter",
        ),
        (
            {"note": "NUM 1:18", "spelling": "greek", "from": "λέγει", "to": "λέγη"},
            "more than one letter",
        ),
        (
            {
                "note": "NUM 1:18",
                "spelling": "greek",
                "from": "ἠχος",
                "to": "η\u0313\u0342χος",
            },
            "composed form",
        ),
    ],
)
def test_foreign_spelling_refuses_other_changes(
    policy: bible.policy.Policy, change: dict[str, str], refusal: str
) -> None:
    rules = revisions(policy, passages=passage_group(change))
    with pytest.raises(CheckFailed, match=refusal):
        revision.check(rules)


def test_foreign_spelling_refuses_a_note_moved_into_the_new_testament(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse("\\id MAT\n\\c 1\n\\p\n\\v 1 Text.\\f - \\fr 1:1 \\ft λέγει.\\f*")
    usj.notes_of(doc["content"])[0]["x-key"] = "NUM 1:18"
    rules = revisions(
        policy,
        passages=passage_group(
            {"note": "NUM 1:18", "spelling": "greek", "from": "λέγει", "to": "λέγε"},
        ),
    )
    revision.check(rules)
    with pytest.raises(CheckFailed, match="outside Old Testament"):
        revision.passages("MAT", doc, rules, set())


def test_foreign_spelling_refuses_stale_and_overlapping_matches(
    policy: bible.policy.Policy,
) -> None:
    change = {"unit": "XXE", "spelling": "greek", "from": "ἐπαξοοῦν", "to": "ἐπαξονοῦν"}
    rules = revisions(policy, passages=passage_group(change))
    for text in ("Absent.", "ἐπαξοοῦν ἐπαξοοῦν"):
        with pytest.raises(CheckFailed, match="not met once"):
            revision.passages("XXE", usj.parse("\\id XXE\n\\ip " + text), rules, set())
    with pytest.raises(CheckFailed, match="Overlapping"):
        revision.passages(
            "XXE",
            usj.parse("\\id XXE\n\\ip ἐπαξοοῦν"),
            revisions(policy, passages=passage_group(change, change)),
            set(),
        )
    with pytest.raises(CheckFailed, match="nothing prints"):
        revision.check_met(rules, set())


@pytest.mark.parametrize(
    "change",
    [
        {"from": "Word.—", "to": "Word—"},
        {"unit": "GEN", "from": "Word.—", "to": "Word—"},
        {"unit": "XXB", "note": "GEN 1:1", "from": "Word.—", "to": "Word—"},
        {"note": "invalid", "from": "Word.—", "to": "Word—"},
        {"unit": "XXB", "from": "Word.—", "to": "Word.—"},
        {"unit": "XXB", "from": "Word.—", "to": "Other—"},
        {"unit": "XXB", "from": "two words", "to": "twowords"},
        {"unit": "XXB", "from": "door-post", "to": "door post"},
        {"unit": "XXB", "from": "word and", "to": "word And"},
        {"unit": "XXB", "from": "Word.—", "to": "Word—", "why": ""},
        {"unit": "XXB", "from": "Word.—", "to": "\\it Word\\it*—"},
    ],
)
def test_invalid_passage_revisions_are_refused(
    policy: bible.policy.Policy, change: dict[str, str]
) -> None:
    with pytest.raises(CheckFailed):
        revision.check(revisions(policy, passages=passage_group(change)))


@pytest.mark.parametrize("text", ["Absent.", "Word.—Word.—", "Word.—\n\\ip Word.—"])
def test_passage_revisions_must_match_once(
    policy: bible.policy.Policy, text: str
) -> None:
    rules = revisions(
        policy, passages=passage_group({"unit": "XXB", "from": "Word.—", "to": "Word—"})
    )
    with pytest.raises(CheckFailed, match="not met once"):
        revision.passages("XXB", usj.parse("\\id XXB\n\\ip " + text), rules, set())


def test_overlapping_and_unused_passage_revisions_are_refused(
    policy: bible.policy.Policy,
) -> None:
    first = {"unit": "XXB", "from": "Word.—more", "to": "Word—more"}
    second = {"unit": "XXB", "from": ".—more", "to": "—more"}
    rules = revisions(policy, passages=passage_group(first, second))
    doc = usj.parse("\\id XXB\n\\ip Word.—more")
    with pytest.raises(CheckFailed, match="Overlapping"):
        revision.passages("XXB", doc, rules, set())
    with pytest.raises(CheckFailed, match="nothing prints"):
        revision.check_met(rules, {("XXB", first["from"])})
    with pytest.raises(CheckFailed, match="Overlapping"):
        revision.passages(
            "XXB", doc, revisions(policy, passages=passage_group(first, first)), set()
        )


def test_prepared_contextual_dashes_and_derived_quotations(
    edition: bible.pipeline.Edition,
    policy: bible.policy.Policy,
    read: bible.pipeline.Read,
) -> None:
    # A verse's or a passage's change is made in the source's letters, and
    # printed with its ligatures written out.
    letters = str.maketrans(dict(policy.revisions["ligatures"]["letters"]))
    for change in revision.verse_changes(policy):
        code, reference = change["verse"].split()
        words = scripture.verses(edition.documents[code])[reference].text
        # Respelling follows the verse decisions, so a decision's words may
        # be respelled (4MA 12:7 "says"); its space may stand at a line break.
        respelled = revision.respelled(
            usj.parse(f"\\id {code}\n\\c 1\n\\p\n\\v 1 {change['to']}"), policy, set()
        )
        expected = scripture.plain(scripture_text(respelled)).translate(letters)
        assert expected in scripture.plain(words), (change, words)
        # A respelling can retain its source as a substring (beside → besides),
        # so its words are matched whole.
        # An added stop can retain the entire former phrase (God?) → God?);).
        gone = revision._phrase(change["from"].translate(letters))
        if gone.search(expected) is None:
            assert gone.search(words) is None
    for passage_change in revision.passage_changes(policy):
        if "note" in passage_change:
            code = passage_change["note"].split()[0]
            note = next(
                n
                for n in usj.notes_of(edition.documents[code]["content"])
                if n.get("x-key") == passage_change["note"]
            )
            words = usj.text_of(note["content"])
        else:
            words = usj.text_of(edition.documents[passage_change["unit"]]["content"])
        assert passage_change["to"].translate(letters) in words
        assert passage_change["from"].translate(letters) not in words
    assert (
        "expressly were appointed"
        in scripture.verses(edition.documents["2CH"])["31:19"].text
    )
    assert "dead?—" in scripture.verses(edition.documents["2SA"])["12:18"].text
    note = next(
        n
        for n in usj.notes_of(edition.documents["DEU"]["content"])
        if n.get("x-key") == "DEU 17:20"
    )
    assert "Heb.—" in usj.text_of(note["content"])
    quoted = places.report(policy.versification["kjv"], edition.documents, read.kjv)
    assert "Artaxerxes (this Artaxerxes" in quoted
    assert "save Israel.—" not in quoted


def test_passage_note_keys_must_select_once(policy: bible.policy.Policy) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 Text.\\f - \\ft Word.—more\\f*\\f - \\ft Other.\\f*"
    )
    for note in usj.notes_of(doc["content"]):
        note["x-key"] = "GEN 1:1#1"
    rules = revisions(
        policy,
        passages=passage_group(
            {"note": "GEN 1:1#1", "from": "Word.—more", "to": "Word—more"}
        ),
    )
    with pytest.raises(CheckFailed, match="not met once"):
        revision.passages("GEN", doc, rules, set())


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (
            "an holy place; An Historical account",
            "a holy place; A Historical account",
        ),
        (
            "an hundred-fold harvest; an hundredfold harvest",
            "a hundredfold harvest; a hundredfold harvest",
        ),
        (
            "an heir; an honest man; an honestly-made answer; an honourable man; an hour",
            "an heir; an honest man; an honestly-made answer; an honourable man; an hour",
        ),
        (
            "mine honour; thine heir; mine hour; Mine eyes; Thine hand",
            "mine honour; thine heir; mine hour; Mine eyes; Thy hand",
        ),
        (
            "mine own hand; thine own soul; mine own; thine own; mine are thine; thine is the kingdom",
            "mine own hand; thine own soul; mine own; thine own; mine are thine; thine is the kingdom",
        ),
        (
            "mine heart; thine house; thine holy soul",
            "my heart; thy house; thy holy soul",
        ),
        (
            "my eyes; my ears; my enemies; my honour; thine arm; thy inheritance",
            "mine eyes; mine ears; mine enemies; mine honour; thine arm; thine inheritance",
        ),
        (
            "my old age; my own house; thy own soul",
            "mine old age; mine own house; thine own soul",
        ),
        (
            "mine old age; Thine ancient mercies; mine every sin; mine own country; "
            "thine own soul; mine own failings; thine honourable virginity; mine hour of need",
            "mine old age; Thine ancient mercies; mine every sin; mine own country; "
            "thine own soul; mine own failings; thine honourable virginity; mine hour of need",
        ),
        (
            "thy union; thy universal memorial; thy useless servant; thy ewe lamb; "
            "thine unworthy servant; thy one side; thy Urim",
            "thy union; thy universal memorial; thy useless servant; thy ewe-lamb; "
            "thine unworthy servant; thy one side; thy Urim",
        ),
        (
            "an herb; an humble person; an uniform; an uniformity; an eunuch; such an one",
            "a herb; a humble person; a uniform; a uniformity; a eunuch; such a one",
        ),
        (
            "a horse; a house; a holy man; a hundred; a historical account; "
            "a union; a useful thing; a ewe lamb; a once-barren root; Such a one; "
            "an uncle; an unknown thing; an unholy man; a whole hour; an hour",
            "a horse; a house; a holy man; a hundred; a historical account; "
            "a union; a useful thing; a ewe-lamb; a once-barren root; Such a one; "
            "an uncle; an unknown thing; an unholy man; a whole hour; an hour",
        ),
        (
            "no honour; none holy as the Lord; none hath; none of them",
            "no honour; none holy as the Lord; none hath; none of them",
        ),
        (
            "The silver is mine; All that I have is thine; Thine is the kingdom",
            "The silver is mine; All that I have is thine; Thine is the kingdom",
        ),
    ],
)
def test_contextual_articles_and_possessives(
    policy: bible.policy.Policy, before: str, after: str
) -> None:
    doc = usj.parse("\\id GEN\n\\c 1\n\\p\n\\v 1 " + before)
    original = copy.deepcopy(doc)
    result = revision.respelled(doc, policy, set())
    assert scripture.verses(result)["1:1"].text == after
    assert doc == original


def test_contextual_phrases_in_styles_notes_and_paragraphs(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 my \\add honour\\add*"
        "\\f - \\fq my \\+it honour\\+it*: \\ft an \\+it hundred\\+it* and one; thine heir; thine heart.\\f*."
        "\n\\ip mine hour; my eyes; an holy place."
    )
    original = copy.deepcopy(doc)
    result = revision.respelled(doc, policy, set())
    printed = usj.serialize(result)
    assert "mine \\add honour\\add*" in printed
    assert "mine \\+it honour\\+it*:" in printed
    assert "a \\+it hundred\\+it* and one; thine heir; thy heart." in printed
    assert "mine hour; mine eyes; a holy place." in printed
    assert doc == original


def test_phrase_revision_refuses_a_partial_inconsistent_lemma(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 mine heart\\f - \\fq mine: \\ft or, my.\\f*."
    )
    with pytest.raises(CheckFailed, match="lemma .* GEN 1:1: mine"):
        revision.respelled(doc, policy, set())


def test_attributive_none_changes_only_in_a_declared_phrase(
    policy: bible.policy.Policy,
) -> None:
    rules = revisions(
        policy,
        words={
            "none habitation": {
                "to": "no habitation",
                "why": "Attributive none before aspirated h.",
            }
        },
    )
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 none habitation; none holy; none hath; no honour."
    )
    assert scripture.verses(revision.respelled(doc, rules, set()))["1:1"].text == (
        "no habitation; none holy; none hath; no honour."
    )


@pytest.mark.parametrize(
    ("code", "reference", "phrase"),
    [
        ("GEN", "15:2", "mine heir"),
        ("GEN", "15:4", "thine heir"),
        ("MAL", "1:6", "mine honour"),
        ("JHN", "2:4", "mine hour"),
        ("LUK", "2:30", "For mine eyes have seen thy salvation"),
        ("JOB", "34:19", "an honourable"),
        ("ISA", "56:5", "an honourable"),
        ("MRK", "15:43", "an honourable"),
    ],
)
def test_confirmed_article_and_possessive_passages(
    edition: bible.pipeline.Edition, code: str, reference: str, phrase: str
) -> None:
    assert phrase in scripture.verses(edition.documents[code])[reference].text


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("has shewed", "hath shown"),
        ("has showed", "hath shown"),
        ("has the Lord God shewed", "hath the Lord God shown"),
        ("does not; stags and does", "doth not; stags and does"),
        ("meats and drinks; eats and drinks", "meats and drinks; eateth and drinketh"),
        ("and fears shall be; and fears not", "and fears shall be; and feareth not"),
        ("king wishes; good wishes", "king wisheth; good wishes"),
        ("that remains; the remains", "that remaineth; the remains"),
        ("Lord supports; the supports", "Lord supporteth; the supports"),
        (
            "and works in stone; and works mercy",
            "and works in stone; and worketh mercy",
        ),
        ("hast not shewed", "hast not shown"),
        ("hast thou shewed", "hast thou shown"),
        ("have I shewed", "have I shown"),
        ("is not shewed", "is not shown"),
        ("pattern shewed", "pattern shown"),
        ("he shewed", "he showed"),
        ("strake of the gall", "strake of the gall"),
        ("strake sail", "struck sail"),
        ("Oh, oh", "Oh, oh"),
        ("Oh how desirable", "O how desirable"),
        ("that flies; flies", "that flieth; flies"),
        ("he that walks; public walks", "he that walketh; public walks"),
        ("he holds; strong holds", "he holdeth; strongholds"),
        ("any one of you; any one that", "any one of you; anyone that"),
        ("from day to day; to day", "from day to day; today"),
    ],
)
def test_reviewed_grammar_and_exceptions(
    declared: bible.policy.Policy, before: str, after: str
) -> None:
    doc = usj.parse("\\id GEN\n\\c 1\n\\p\n\\v 1 " + before)
    original = copy.deepcopy(doc)
    result = revision.respelled(doc, declared, set())
    assert scripture.verses(result)["1:1"].text == after
    assert doc == original


def test_a_compound_divided_by_a_style_stays_divided(
    declared: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 \\f - \\fr 1 \\fq any thing: \\ft "
        "any thing; Gr. \\fqa any thing\\f*any \\it thing\\it* and "
        "\\f - \\fr 1 \\fq any thing: \\ft Gr. \\fqa any thing\\f*any thing"
    )
    original = copy.deepcopy(doc)
    result = revision.respelled(doc, declared, set())
    verse = scripture.verses(result)["1:1"]
    assert verse.text == "any thing and anything"
    assert usj.serialize(result).count("\\it thing\\it*") == 1
    assert [usj.text_of(note["content"]) for _, note in verse.notes] == [
        "1 any thing: anything; Gr. anything",
        "1 anything: Gr. anything",
    ]
    assert doc == original


def test_the_supplied_word_style_divides_no_compound(
    declared: bible.policy.Policy,
) -> None:
    # The style is printed roman and shown plain, so the reader sees the words
    # alone, and they are joined as they are anywhere else, lemma included;
    # within an italic rendering it prints otherwise, and divides them.
    doc = usj.parse(
        "\\id 1KI\n\\c 1\n\\p\n\\v 1 \\f - \\fr 1 \\fq any thing: \\ft Gr. "
        "\\fqa any one; \\ft or, \\fqa any \\+add thing\\+add*\\f*"
        "any \\add thing\\add* and every \\add thing\\add*."
    )
    original = copy.deepcopy(doc)
    result = revision.respelled(doc, declared, set())
    verse = scripture.verses(result)["1:1"]
    assert verse.text == "anything and everything."
    assert "any\\add thing\\add* and every\\add thing\\add*." in usj.serialize(result)
    assert (
        usj.text_of(verse.notes[0][1]["content"])
        == "1 anything: Gr. anyone; or, any thing"
    )
    assert doc == original


def test_house_style_distinguishes_titles_names_and_common_words(
    declared: bible.policy.Policy,
) -> None:
    source = usj.parse(
        "\\id GEN\n\\c 1\n\\p \\v 1 king David and king Solomon; the king; "
        "David the king; king of Israel. mount Sinai; mount of Olives; "
        "the mount of God; mount my mule. sabbath-day; sabbaths of years; "
        "a scripture; the scriptures. enquiring; enquiry; grey-haired. "
        "firstborn; corner stone; stumblingblock; fulness. "
        "sin-offering; whole-burnt offering; meat offering; freewill-offering. "
        "He begot a son, and she bore a son; he shall bore his ear, and broke it."
    )
    before = copy.deepcopy(source)
    result = revision.respelled(source, declared, set())
    assert scripture.verses(result)["1:1"].text == (
        "King David and King Solomon; the king; David the king; king of Israel. "
        "Mount Sinai; Mount of Olives; the mount of God; mount my mule. "
        "Sabbath day; Sabbaths of years; a Scripture; the Scriptures. "
        "inquiring; inquiry; gray-haired. first-born; corner-stone; "
        "stumbling-block; fulness. sin offering; whole-burnt offering; "
        "meat offering; free-will offering. He begat a son, and she bare a son; "
        "he shall bore his ear, and brake it."
    )
    assert source == before


def test_spake_revises_scripture_and_readings_but_preserves_commentary(
    declared: bible.policy.Policy,
) -> None:
    source = usj.parse(
        "\\id GEN\n\\ip He spoke and had spoken.\n\\c 1\n\\p \\v 1 He "
        "\\f - \\fq spoke: \\ft He spoke; or, \\fqa spoke\\f*spoke and had spoken."
    )
    before = copy.deepcopy(source)
    result = revision.respelled(source, declared, set())
    verse = scripture.verses(result)["1:1"]
    assert verse.text == "He spake and had spoken."
    assert usj.text_of(verse.notes[0][1]["content"]) == ("spake: He spoke; or, spake")
    assert "\\ip He spoke and had spoken." in usj.serialize(result)
    assert source == before


def test_title_case_can_surround_unchanged_names_and_ligatures(
    declared: bible.policy.Policy,
) -> None:
    rules = revisions(
        declared,
        names=names(NOAH),
        words={
            "king Noe": {"to": "King Noe", "why": "Capitalize the title only."},
            "mount Gæbal": {"to": "Mount Gæbal", "why": "Capitalize the title only."},
        },
        ligatures={
            "why": "Write out the source ligature last.",
            "letters": {"æ": "ae"},
        },
    )
    revision.check(rules)
    for target in ["King Noah", "King noe"]:
        wrong = revisions(
            rules,
            names=names(NOAH),
            words={"king Noe": {"to": target, "why": "x"}},
        )
        with pytest.raises(CheckFailed, match="Name also respelled as a word"):
            revision.check(wrong)


def test_words_a_style_divides_are_not_redivided_or_met(
    policy: bible.policy.Policy,
) -> None:
    words = revisions(
        policy,
        words={
            "whole burnt-offering": {"to": "whole-burnt offering", "why": "x"},
            "any thing": {"to": "anything", "why": "x"},
        },
    )
    met: revision.MetRevisions = set()
    # Moving burnt between the words would move it out of the style.
    text = "\\v 1 the whole \\it burnt-offering\\it* and any \\it thing\\it*"
    doc = usj.parse("\\id GEN\n\\c 1\n\\p\n" + text)
    assert usj.serialize(revision.respelled(doc, words, met)).endswith(text + "\n")
    # A word that only a style keeps changes nothing, so is not met.
    assert met == set()
    # The supplied-word style divides nothing, since it is printed plain.
    supplied = "\\v 1 the whole \\add burnt-offering\\add* and any \\add thing\\add*"
    doc = usj.parse("\\id GEN\n\\c 1\n\\p\n" + supplied)
    result = revision.respelled(doc, words, met)
    assert (
        scripture.verses(result)["1:1"].text == "the whole-burnt offering and anything"
    )
    assert met == {"whole burnt-offering", "any thing"}
    # Within a reading's italic it prints roman, and divides the words for
    # the grammar of scripture too, which reads each quoted field alone.
    scoped = revisions(
        policy,
        words={"any thing": {"to": "anything", "scope": "scripture", "why": "x"}},
    )
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 \\f - \\fr 1 \\fq any thing: \\ft or, "
        "\\fqa any \\+add thing\\+add*\\f*any \\add thing\\add*."
    )
    verse = scripture.verses(revision.respelled(doc, scoped, set()))["1:1"]
    assert verse.text == "anything."
    assert usj.text_of(verse.notes[0][1]["content"]) == "1 anything: or, any thing"


def test_hyphenating_unchanged_words_preserves_their_styles_and_lemma(
    declared: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id EPH\n\\c 2\n\\p\\v 20 "
        "\\f - \\fq corner stone: \\ft A comment.\\f*corner \\add stone\\add*; "
        "mother \\add in\\add* law."
    )
    original = copy.deepcopy(doc)
    result = revision.respelled(doc, declared, set())
    verse = scripture.verses(result)["2:20"]
    assert verse.text == "corner-stone; mother-in-law."
    assert usj.text_of(verse.notes[0][1]["content"]) == "corner-stone: A comment."
    assert "\\add stone\\add*" in usj.serialize(result)
    assert "\\add in\\add*" in usj.serialize(result)
    assert doc == original


def test_string_seams_and_notes_do_not_prevent_compound_spelling(
    declared: bible.policy.Policy,
) -> None:
    note = usj.parse("\\id GEN\n\\c 1\n\\p\n\\v 1 \\f - \\fr 1 \\ft A comment.\\f*x")
    annotation = usj.notes_of(note["content"])[0]
    seams: list[usj.Content] = [["any ", "thing"], ["any ", annotation, "thing"]]
    for content in seams:
        doc = usj.parse("\\id GEN\n\\c 1\n\\p\n\\v 1 x")
        doc["content"][-1]["content"][1:] = content
        result = revision.respelled(doc, declared, set())
        assert scripture.verses(result)["1:1"].text == "anything"
        if annotation in content:
            assert usj.notes_of(result["content"]) == [annotation]


def test_a_note_inside_a_compound_requires_a_whole_word_lemma(
    declared: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 any \\f - \\fr 1 \\fq thing: "
        "\\ft A comment.\\f*thing and a thing"
    )
    with pytest.raises(CheckFailed, match="lemma its verse no longer has"):
        revision.respelled(doc, declared, set())


@pytest.mark.parametrize(
    ("code", "reference", "phrase"),
    [
        ("1KI", "1:41", "What meaneth"),
        ("EXO", "30:8", "Aaron lighteth"),
        ("JER", "6:29", "silversmith worketh"),
        ("JOB", "11:12", "man vainly buoyeth"),
        ("JOB", "22:3", "what mattereth it"),
        ("JOB", "33:29", "Mighty One worketh"),
        ("PRO", "16:27", "and treasureth fire"),
        ("PRO", "17:13", "Whoso rewardeth"),
        ("PSA", "135:7", "great lights"),
        ("PSA", "8:7", "works of thy hands"),
        ("PRO", "2:4", "as for treasures"),
        ("1KI", "11:22", "By all means"),
    ],
)
def test_reviewed_verbs_and_preserved_nouns(
    edition: bible.pipeline.Edition, code: str, reference: str, phrase: str
) -> None:
    assert phrase in scripture.verses(edition.documents[code])[reference].text


def test_reviewed_verb_phrases_preserve_nouns_and_commentary(
    declared: bible.policy.Policy,
) -> None:
    words = "means; lights; works; buoys; matters; treasures; rewards"
    commentary = "Aaron lights; silversmith works; what matters it; Whoso rewards"
    doc = usj.parse("\\id GEN\n\\ip " + commentary + "\n\\c 1\n\\p\n\\v 1 " + words)
    original = copy.deepcopy(doc)
    result = revision.respelled(doc, declared, set())
    assert scripture.verses(result)["1:1"].text == words
    assert usj.text_of(result["content"]) == usj.text_of(doc["content"])
    assert doc == original


def test_grammar_pass_spares_commentary_and_keeps_note_metadata(
    declared: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\ip He has shewed it.\n\\c 1\n\\p\n\\v 1 He has \\add shewed\\add* it. As he \\add does\\add*"
        "\\f - \\fr 1:1 \\fq has \\+it shewed\\+it*: \\ft He has shewed it; "
        "\\fqa he has \\+it shewed\\+it* it\\ft ; \\fl has\\xt has\\f*"
    )
    note = usj.notes_of(doc["content"])[0]
    note.update(
        {
            "x-key": "GEN 1:1#1",
            "x-scope": {"lemma": "has shewed"},
            "category": "edition",
        }
    )
    original = copy.deepcopy(doc)
    result = revision.respelled(doc, declared, set())
    text = usj.serialize(result)
    assert "\\ip He has shown it." in text
    assert "He hath \\add shown\\add* it." in text
    assert "As he \\add doth\\add*" in text
    assert "\\fq hath \\+it shown\\+it*:" in text
    assert "\\ft He has shown it;" in text
    assert "\\fqa he hath \\+it shown\\+it* it" in text
    assert "\\fl has\\xt has" in text
    after = usj.notes_of(result["content"])[0]
    assert {k: v for k, v in after.items() if k != "content"} == {
        k: v for k, v in note.items() if k != "content"
    }
    assert doc == original


@pytest.mark.parametrize(
    "marker",
    [
        "h",
        "toc1",
        "toc2",
        "toc3",
        "mt1",
        "mt2",
        "mt3",
        "s1",
        "ms1",
        "ip",
        "im",
        "imi",
        "iex",
        "is1",
        "is2",
    ],
)
@pytest.mark.parametrize("position", ["before", "between", "after"])
def test_scoped_grammar_spares_excluded_paragraphs_wherever_they_stand(
    declared: bible.policy.Policy, marker: str, position: str
) -> None:
    paragraph = (
        f'\\{marker} He has shewed it; says "has shewed".'
        "\\f - \\fq has shewed: \\ft He has shewed it; "
        "\\fqa has shewed\\f*\n"
    )
    first = "\\c 1\n\\p\n\\v 1 He has shewed it.\n"
    second = "\\p\n\\v 2 He has shewed it.\n"
    parts = {
        "before": paragraph + first + second,
        "between": first + paragraph + second,
        "after": first + second + paragraph,
    }
    doc = usj.parse("\\id GEN\n" + parts[position])
    note = usj.notes_of(doc["content"])[0]
    note.update(
        {
            "x-key": "GEN 1:1#1",
            "x-scope": {"lemma": "has shewed"},
            "category": "edition",
        }
    )
    original = copy.deepcopy(doc)
    result = revision.respelled(doc, declared, set())
    block = next(b for b in result["content"] if b.get("marker") == marker)
    assert usj.text_of(block["content"]) == 'He has shown it; says "has shown".'
    printed = usj.serialize(result)
    # The note quotes the paragraph it is set in, and keeps its grammar.
    assert "\\fq has shown:" in printed
    assert "\\ft He has shown it;" in printed
    assert "\\fqa has shown" in printed
    assert "\\v 1 He hath shown it." in printed
    assert "\\v 2 He hath shown it." in printed
    after = usj.notes_of(result["content"])[0]
    assert {k: v for k, v in after.items() if k != "content"} == {
        k: v for k, v in note.items() if k != "content"
    }
    assert doc == original


def test_scoped_grammar_in_numbered_psalm_superscriptions(
    declared: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id PSA\n\\c 1\n\\d He has shewed it.\n"
        "\\d \\v 1 He has shewed it.\n\\q1 \\v 2 He has shewed it."
    )
    original = copy.deepcopy(doc)
    result = revision.respelled(doc, declared, set())
    printed = usj.serialize(result)
    assert "\\d He has shown it." in printed
    assert scripture.verses(result)["1:1"].text == "He hath shown it."
    assert scripture.verses(result)["1:2"].text == "He hath shown it."
    assert doc == original


def test_scoped_pass_is_one_sweep_and_quotations_share_it(
    declared: bible.policy.Policy,
) -> None:
    rules = revisions(
        declared,
        words={
            "shewed": {"to": "showed", "why": "spelling"},
            "has showed": {"to": "hath shown", "why": "grammar", "scope": "scripture"},
            "hath": {"to": "had", "why": "prove one sweep", "scope": "scripture"},
        },
    )
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 has shewed; "
        "\\f + \\ft commentary; \\fqa has \\+it shewed\\+it*\\f*"
    )
    result = revision.respelled(doc, rules, set())
    assert scripture.verses(result)["1:1"].text == "hath shown; "
    assert "\\fqa hath \\+it shown\\+it*" in usj.serialize(result)


def test_isolated_alternative_uses_its_source_note_context(
    declared: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id 1SA\n\\c 22\n\\p\n\\v 9 He answered with answers."
        "\\f - \\ft present, \\fqa answers\\f*"
        "\\f - \\ft commentary answers; \\fqa answers\\f*"
    )
    notes = usj.notes_of(doc["content"])
    notes[0]["x-key"] = "1SA 22:9"
    notes[1]["x-key"] = "1SA 22:9#2"
    before = copy.deepcopy(doc)
    result = revision.respelled(doc, declared, set())
    assert scripture.verses(result)["22:9"].text == "He answered with answers."
    printed = usj.serialize(result)
    assert "\\fqa answereth" in printed
    assert "\\ft commentary answers; \\fqa answers" in printed
    assert doc == before


def test_note_contexts_must_each_be_met(declared: bible.policy.Policy) -> None:
    rules = revisions(
        declared,
        words={
            "answers": {
                "to": "answereth",
                "why": "alternative",
                "scope": "scripture",
                "notes": ("GEN 1:1", "GEN 1:2"),
            }
        },
    )
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 answers\\f - \\ft present, \\fqa answers\\f*"
    )
    usj.notes_of(doc["content"])[0]["x-key"] = "GEN 1:1"
    met: revision.MetRevisions = set()
    result = revision.respelled(doc, rules, met)
    assert scripture.verses(result)["1:1"].text == "answers"
    assert "\\fqa answereth" in usj.serialize(result)
    with pytest.raises(CheckFailed, match="GEN 1:2"):
        revision.check_met(rules, met)


def test_corpus_grammar_exceptions_and_quoted_readings(
    edition: bible.pipeline.Edition,
) -> None:
    for code, label in [("JDG", "19:4"), ("JDG", "19:7"), ("NAM", "2:9")]:
        text = scripture.verses(edition.documents[code])[label].text
        assert "stayed" in text and "staid" not in text
    assert (
        "strake of the gall" in scripture.verses(edition.documents["TOB"])["11:11"].text
    )
    assert "Oh, oh" in scripture.verses(edition.documents["NUM"])["24:23"].text
    assert (
        "hath the Lord God shown me"
        in scripture.verses(edition.documents["AMO"])["7:1"].text
    )
    assert "What hast thou to say" in usj.serialize(edition.documents["JOS"])
    assert "\\fqa mounteth" in usj.serialize(edition.documents["PSA"])
    assert "singeth to thee" in scripture.verses(edition.documents["MAN"])["1:15"].text


def test_the_word_pattern_finds_the_longest_word_at_a_place() -> None:
    """The words are set out as a trie, which must find what a plain
    alternation finds: whole words, and the longest where one begins another,
    falling back to the shorter where the longer runs on into a word."""
    pattern = revision._words(["has", "has born", "hat", "to-day"])
    text = "has born, has borne, has, hath, that hat; to-day, to-days"
    found = [m[0] for m in pattern.finditer(text)]
    assert found == ["has born", "has", "has", "hat", "to-day"]
    assert not revision._words([]).search("anything")


def test_source_instructions_keep_their_export_markers_and_spacing() -> None:
    doc = usj.parse(
        "\\id LAM\n\\c 1\n\\q1 \\v 1 Words.\n\\qr Pause.\n"
        "\\qa \\v 2 Beth.\n\\q1 Words.\n\\q1 More.\n"
        "\\b\n\\qa Gimel.\n\\q1 Words.\n\\p Prose."
    )
    result = export.spaced(pipeline.indented(doc))
    assert [b.get("marker") for b in result["content"]] == [
        "id",
        "c",
        "q1",
        "qr",
        "qa",
        "q1",
        "q2",
        "qa",
        "q1",
        "b",
        "p",
    ]
    assert "\\qr Pause." in usj.serialize(result)
    assert "\\qa" in usj.serialize(result)


def test_an_acrostic_heading_supplies_its_own_space() -> None:
    # Lamentations 1 opens its poem after a paragraph of prose, and its
    # chapters 2 to 4 with their first names, as chapter 5 opens with a line.
    # Neither a chapter nor an acrostic label needs a blank paragraph.
    assert spaced_markers(
        "\\id LAM\n\\c 1\n\\p Prose.\n\\qa \\v 1 Aleph.\n\\q1 Line.\n"
        "\\c 2\n\\qa \\v 1 Aleph.\n\\q1 Line.\n\\c 5\n\\q1 \\v 1 Line.\n"
    ) == ["id", "c", "p", "qa", "q1", "c", "qa", "q1", "c", "q1"]


def test_a_note_is_set_under_the_label_its_verse_prints() -> None:
    labels = {"24:35": "30:15", "0:1": ""}
    assert bible.export.printed_origin("24:35 ", labels) == "30:15 "
    assert bible.export.printed_origin("24:34 ", labels) == "24:34 "
    with pytest.raises(CheckFailed, match="unnumbered verse"):
        bible.export.printed_origin("0:1 ", labels)
    with pytest.raises(CheckFailed, match="verses with printed labels"):
        bible.export.printed_origin("24:35-36 ", labels)


def test_exported_proverbs_sets_the_hebrews_labels(
    edition: bible.pipeline.Edition,
) -> None:
    text = usj.serialize(
        bible.export.document("PRO", edition.documents["PRO"], edition)
    )
    assert "\\v 22f \\vp 30:1\\vp* " in text
    assert "\\v 23 \\vp 24:23\\vp* " in text


def test_a_margin_note_names_another_chapters_label_in_full(
    edition: bible.pipeline.Edition,
) -> None:
    # The margin drops the chapter the running head supplies, but names a
    # verse as it prints: with its chapter where its label names one.
    doc = usj.parse(
        "\\id PRO\n\\c 24\n\\p\n"
        "\\v 22f \\vp 30:1\\vp* Agur\\f - \\fr 24:22f \\ft A\\f*\n"
        "\\v 22g \\vp 2\\vp* said\\f - \\fr 24:22g \\ft B\\f*\n"
        "\\v 23 back\\f - \\fr 24:23 \\ft C\\f*\n"
    )
    text = usj.serialize(bible.export.document("PRO", doc, edition))
    assert [
        line.split("\\fr ")[1].split(" \\ft")[0]
        for line in text.split("\n")
        if "\\fr " in line
    ] == ["30:1", "2", "23"]
