"""Notes: what each says, the words it is about, and how it prints."""

from __future__ import annotations

import re
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import replace
from typing import Any

import pytest
from conftest import book, changed, verse_lines

import bible.annotate
import bible.export
import bible.pipeline
import bible.policy
from bible import (
    annotate,
    crossrefs,
    lemmas,
    notes,
    revision,
    scripture,
    terminology,
    usj,
)
from bible.checks import CheckFailed
from bible.policy_schema import NoteOverride
from bible.usj import Document, Node


@pytest.mark.parametrize(
    "key",
    [
        "GEN 15:11",
        "GEN 39:1",
        "JOS 19:51",
        "JDG 2:18",
        "1SA 15:11",
        "2KI 12:14",
        "1KI 10:22a",
        "1KI 14:1-20@6",
        "1KI 14:1-20@12",
        "MAT 17:27 a piece of money",
        "ACT 17:19 Areopagus",
    ],
)
def test_complete_explanations_keep_their_final_stop(
    edition: bible.pipeline.Edition, key: str
) -> None:
    row = next(r for rows in edition.notes.values() for r in rows if r["key"] == key)
    assert row["note"].endswith(".")
    if key == "1KI 10:22a":
        assert row["note"].startswith("This word")
    if key in (
        "GEN 15:11",
        "MAT 17:27 a piece of money",
        "ACT 17:19 Areopagus",
    ):
        assert row["note"].startswith("or,")


def test_psalm_explanation_keeps_commentary_grammar_and_note_identity(
    edition: bible.pipeline.Edition,
) -> None:
    key = "PSA 24:14"
    rows = [row for row in edition.notes["PSA"] if row["key"] == key]
    assert len(rows) == 1
    assert rows[0]["lemma"] == "truth"
    assert rows[0]["note"] == "or, _it_, sc. what has just been stated"
    verse = scripture.verses(edition.documents["PSA"])["24:14"]
    matching = [note for _, note in verse.notes if note.get("x-key") == key]
    assert len(matching) == 1
    note = matching[0]
    assert usj.text_of(note["content"]).endswith(
        "truth: or, it, sc. what has just been stated"
    )
    alternatives = [
        usj.text_of(node["content"])
        for node in usj.walk(note["content"])
        if node.get("marker") == "fqa"
    ]
    assert alternatives == ["it"]


def test_editorial_note_styles_and_punctuation(
    edition: bible.pipeline.Edition,
) -> None:
    rows = {r["key"]: r for notes in edition.notes.values() for r in notes}

    # Adjacent italic spans have the same meaning whether the review joins them.
    def reviewed(key: str) -> str:
        return rows[key]["note"].replace("_ _", " ")

    assert "_from any cause_" in reviewed("GEN 30:41")
    assert "_then_" in reviewed("GEN 30:41")
    assert reviewed("1SA 14:29").startswith("_E medio sustulit_.")
    assert rows["1SA 14:29"]["lemma"] == "destroyed the land"
    assert "What kind of pause was intended by the LXX" in reviewed("PSA 3:3")
    assert "which is evidently not the meaning here" in reviewed("1KI 10:22a")
    assert "omitting ἐν as a Hebraism" in reviewed("JDG 5:14")
    assert "Iliad, book 10, line 456" in reviewed("DEU 21:4")
    assert reviewed("PSA 113:24") == "Gr. singular"
    assert "_suburbs_ above" in reviewed("JOS 21:13")
    assert reviewed("JOS 20:7#2") == "or, _of Nephthali_"
    assert reviewed("1SA 30:26") == "Heb. agrees. Vat. _behold some_"
    assert rows["JHN 18:13 year"]["lemma"] is None
    assert reviewed("JHN 18:13 year") == (
        "_And Annas sent Christ bound unto Caiaphas the high priest_, verse 24"
    )
    assert reviewed("2CO 4:8 in despair") == ("or, _altogether without help, or means_")


@pytest.mark.parametrize(
    "marker, expected",
    [
        ("_", "_And Annas sent Christ_"),
        ("{", "_and Annas sent Christ_"),
    ],
)
def test_declared_quotations_preserve_capitals_but_alternatives_run_on(
    policy: bible.policy.Policy, marker: str, expected: str
) -> None:
    source = "And Annas sent Christ"
    body = notes.source_body(
        [("text", source)],
        [],
        marker + source + ("}" if marker == "{" else "_"),
        "key",
        source,
    )
    assert body.alternative == (source if marker == "{" else None)
    runs, terms, _ = notes.displayed(body)
    result = notes.finished(
        runs, terms, "year", None, terminology.registry(policy), "key"
    )
    assert notes.underscored(result) == expected
    echoed = notes.displayed(body, "before ", " after")[0]
    assert notes.text_of(echoed) == (
        "before " + source + " after" if marker == "{" else source
    )


@pytest.mark.parametrize(
    "override",
    [
        "{word",
        "_word",
        "word}",
        "{_word_}",
        "_{word}_",
        "{word_",
        "{}word",
        "__word",
        "word{ }word",
        "{.}word",
    ],
)
def test_malformed_note_markers_are_refused(override: str) -> None:
    # The words match the note, so only the markers can be refused.
    source = re.sub("[_{}]", "", override)
    with pytest.raises(CheckFailed, match="note override: key"):
        notes.source_body([("text", source)], [], override, "key", source)


def test_commentary_quotations_preserve_the_separate_alternative() -> None:
    text = (
        "lit. torment, Βάσανος in Old Testament seems to signify punishment, "
        "as κόλασις in New Testament does torment."
    )
    override = (
        text.replace("torment", "_torment_")
        .replace("punishment", "_punishment_")
        .replace("_torment_", "{torment}", 1)
    )
    body = notes.source_body(
        notes.labelled_pieces(text),
        [],
        override,
        "key",
        text,
    )
    assert body.alternative == "torment"
    assert body.reading == (5, 12)
    runs, _, _ = notes.displayed(body, "before ", " after")
    assert ("reading", "before torment after") in runs
    assert [(role, value) for role, value in runs if role == "quotation"] == [
        ("quotation", "punishment"),
        ("quotation", "torment"),
    ]


def test_repeated_alternatives_each_echo_the_context() -> None:
    text = "lit. torment; the other torment."
    body = notes.source_body(
        notes.labelled_pieces(text),
        [],
        "lit. {torment}; the other {torment}.",
        "key",
        text,
    )
    assert body.alternative == "torment"
    runs, _, _ = notes.displayed(body, "before ", " after")
    assert [value for role, value in runs if role == "reading"] == [
        "before torment after",
        "before torment after",
    ]


def test_the_first_declared_alternative_measures_the_lemma() -> None:
    text = "first; second; third."
    body = notes.declared_readings(
        notes.interpreted([("text", text)], "key"),
        "_first_; {second}; {third}.",
        "key",
    )
    assert body.alternative == "second"


def test_changing_commentary_italics_keeps_the_inferred_scope(
    policy: bible.policy.Policy,
) -> None:
    # The quotation stands before the alternative, so a lemma measured by
    # the first italic run would change with it.
    override = policy.brenton_notes["notes"]["GEN 30:33"]["note"]
    assert override is not None
    exception: NoteOverride = {"note": override}
    source = override.translate(str.maketrans("", "", "_{}"))
    text = "And my righteousness shall answer for me on the morrow."
    words = scripture.word_spans(text)
    bodies = [
        notes.source_body(
            notes.labelled_pieces(source),
            [],
            value,
            "key",
            source,
        )
        for value in (override, override.replace("_Hearken to_", "Hearken to"))
    ]
    assert [body.alternative for body in bodies] == ["obey me", "obey me"]
    assert bodies[0].reading == bodies[1].reading
    inferred = [
        lemmas.inferred(
            "f", text, words, text.index("answer"), body.alternative, exception, "key"
        )
        for body in bodies
    ]
    assert inferred[0] == inferred[1]
    assert (
        notes.displayed(bodies[0], "before ", " after")[0]
        != notes.displayed(bodies[1], "before ", " after")[0]
    )


def printed(
    body: str,
    ctx: bible.annotate.Context,
    *,
    code: str = "GEN",
    links: Sequence[crossrefs.Link] = (),
) -> dict[str, str]:
    """A small book's verses with their notes as the edition prints them."""
    doc, _ = annotate.brenton(code, book(code, body), links, frozenset(), ctx)
    return verse_lines(doc)


@pytest.mark.parametrize(
    "verse, expected",
    [
        # A rendering is italic and its label roman; the note runs on from
        # the word it glosses, without its closing stop.
        (
            r"\v 9 Let the water be collected into one \f + \fr 99:9 \fqa Gr. \ft meeting.\f*place, and let the dry land appear.",
            r"Let the water be collected into one \f - \fr 99:9 \fq place: \ft Gr. \fqa meeting\f*place, and let the dry land appear.",
        ),
        # A label that comments stays roman with what follows it.
        (
            r"\v 4 God divided between the light \f + \fr 99:4 \fqa Gr. \ft and between the darkness. \fqa Hebraism.\f*and the darkness.",
            r"God divided between the light \f - \fr 99:4 \fq and the darkness: \ft Gr. \fqa and between the darkness\ft . Hebraism\f*and the darkness.",
        ),
        # "X, or Y" are two renderings; an abbreviation keeps its stop.
        (
            r"\v 6 I am \f + \fr 99:6 \fqa Gr. \ft I have thought, or reasoned, so the Heb.\f*grieved that I made them.",
            r"I am \f - \fr 99:6 \fq grieved: \ft Gr. \fqa I have thought\ft , or \fqa reasoned\ft , so the Heb.\f*grieved that I made them.",
        ),
        # A cross-reference is "See" and what it cites, as the edition cites.
        (
            r"\v 5 \x + \xo 99:5 \xt Rom. 4. 7,8.\x* Blessed are they whose sins are forgiven.",
            r"\f - \fr 99:5 \ft See \ref Rom. 4:7|ROM 4:7\ref*, \ref 8|ROM 4:8\ref*\f*Blessed are they whose sins are forgiven.",
        ),
        # A caller at the end of a verse glosses the words before it.
        (
            r"\v 7 and he called his name Light.\f + \fr 99:7 \fqa Heb. \ft Brightness.\f*",
            r"and he called his name Light.\f - \fr 99:7 \fq Light: \ft Heb. \fqa Brightness\f*",
        ),
        # Abbreviations print in the edition's forms.
        (
            r"\v 8 the captain of the \f + \fr 99:8 \fqa A. V. \ft guard, i. e. the Sept. reading.\f*cooks stood there.",
            r"the captain of the \f - \fr 99:8 \fq cooks: \ft KJV \fqa guard\ft , i.e., the LXX reading\f*cooks stood there.",
        ),
        # A version's name keeps its capital where the note runs on from its lemma.
        (
            r"\v 8 the captain of the \f + \fr 99:8 \ft Eng. Ver. guard.\f*cooks stood there.",
            r"the captain of the \f - \fr 99:8 \fq cooks stood there: \ft KJV guard\f*cooks stood there.",
        ),
        # A caller just inside supplied words stands before them.
        (
            r"\v 3 they came \add \f + \fr 99:3 \fqa Gr. \ft a place.\f*to\add* the city.",
            r"they came \f - \fr 99:3 \fq to the city: \ft Gr. \fqa a place\f*\add to\add* the city.",
        ),
    ],
)
def test_a_note_of_brentons_is_set_as_a_footnote_on_its_words(
    verse: str, expected: str, ctx: bible.annotate.Context
) -> None:
    assert list(printed(verse, ctx).values()) == [expected]


def test_a_lemma_is_widened_until_it_occurs_once_and_its_rendering_with_it() -> None:
    verse = "that ye have no reward of your Father, and praise of men"
    words = scripture.word_spans(verse)
    of = [i for i, (word, _, _) in enumerate(words) if word == "of"]
    span, glossed, rule, first = lemmas.anchored(verse, words, ["of"], 1, {}, "key")
    assert span is not None
    assert (lemmas.lemma_text(verse, words, span), rule, first) == (
        "of your Father",
        "widened",
        of[0],
    )
    assert lemmas.echoes(verse, words, span, glossed) == ("", " your Father")


def test_the_exception_files_correct_the_rules(
    ctx: bible.annotate.Context, policy: bible.policy.Policy
) -> None:
    verse = r"\v 9 Let the water be collected into one \f + \fr 99:9 \fqa Gr. \ft meeting together.\f*place of rest."

    def with_exception(entry: dict[str, Any]) -> str:
        excepted = changed(
            policy,
            "brenton_notes",
            lambda data: data["notes"].update({"GEN 99:9": entry}),
        )
        return printed(
            verse, annotate.Context(excepted, *list(vars(ctx).values())[1:])
        )["9"]

    assert (
        r"\fq place of rest: \ft Gr. \fqa meeting together\f*"
        in printed(verse, ctx)["9"]
    )
    assert r"\fq into one place: \ft Gr. \fqa meeting together\f*" in with_exception(
        {"lemma": "into one place", "why": "the rendering is of the whole phrase"}
    )
    assert r"\fq place: \ft Gr. \fqa meeting \ft together\f*" in with_exception(
        {
            "note": "Gr. {meeting} together.",
            "why": "together is the editor's",
        }
    )
    assert r"\f - \fr 99:9 \ft Gr. \fqa meeting together\f*" in with_exception(
        {"lemma": None, "why": "the note is on the verse"}
    )
    # An exception that changes nothing, or isn't the note's words, is refused.
    with pytest.raises(CheckFailed, match="Lemma override changes nothing"):
        with_exception({"lemma": "place of rest", "why": "the same"})
    with pytest.raises(CheckFailed, match="Note override changes nothing"):
        with_exception(
            {
                "note": "Gr. {meeting together}.",
                "why": "the same",
            }
        )
    with pytest.raises(CheckFailed, match="does not match the note"):
        with_exception({"note": "Gr. _meeting_ apart.", "why": "other words"})


def test_a_repeated_verb_can_keep_its_gloss_clear_of_its_object(
    ctx: bible.annotate.Context, policy: bible.policy.Policy
) -> None:
    verse = (
        r"\v 9 And she "
        r"\f + \fr 99:9 \fqa Gr. \ft caused to sleep.\f*"
        "laid him in her bosom, and laid her dead son in my bosom."
    )
    excepted = changed(
        policy,
        "brenton_notes",
        lambda data: data["notes"].update(
            {
                "GEN 99:9": {
                    "lemma": "laid",
                    "occurrence": 2,
                    "widen": False,
                    "why": "The note glosses the verb, not its object.",
                }
            }
        ),
    )
    result = printed(verse, annotate.Context(excepted, *list(vars(ctx).values())[1:]))[
        "9"
    ]
    assert result == (
        r"And she laid him in her bosom, and \f - \fr 99:9 \fq laid: "
        r"\ft Gr. \fqa caused to sleep\f*laid her dead son in my bosom."
    )


def test_a_declared_lemma_moves_its_caller_before_widening(
    ctx: bible.annotate.Context,
) -> None:
    source = book(
        "GEN",
        r"\v 9 He was very advanced in years; thou art advanced in "
        r"\f + \fr 99:9 \fqa Gr. \ft days.\f*years.",
    )
    before = deepcopy(source)
    policy = changed(
        ctx.policy,
        "brenton_notes",
        lambda data: data["notes"].update(
            {
                "GEN 99:9": {
                    "lemma": "years",
                    "occurrence": 1,
                    "why": "The note belongs to the first years.",
                }
            }
        ),
    )
    doc, _ = annotate.brenton(
        "GEN", source, (), frozenset(), replace(ctx, policy=policy)
    )
    verse = scripture.verses(doc)["99:9"]
    [(offset, note)] = verse.notes
    assert offset == verse.text.index("years")
    assert notes.lemma_of(note) == "very advanced in years"
    assert source == before
    assert verse.text == scripture.verses(source)["99:9"].text


@pytest.mark.parametrize("override", [{}, {"lemma": None}])
def test_inferred_and_null_lemmas_keep_their_callers(
    ctx: bible.annotate.Context, override: dict[str, Any]
) -> None:
    source = book(
        "GEN", r"\v 9 There was light.\f + \fr 99:9 \fqa Gr. \ft brightness.\f*"
    )
    policy = changed(
        ctx.policy,
        "brenton_notes",
        lambda data: data["notes"].update(
            {"GEN 99:9": {**override, "why": "Keep the source position."}}
        ),
    )
    doc, _ = annotate.brenton(
        "GEN", source, (), frozenset(), replace(ctx, policy=policy)
    )
    verse = scripture.verses(doc)["99:9"]
    [(offset, _)] = verse.notes
    assert offset == len(verse.text)


def test_a_declared_lemma_needs_its_caller_before_its_first_word() -> None:
    verse = "He said, ‘Behold the man’, and the man said nothing."
    words = scripture.word_spans(verse)
    # Before the first word, past an opening quotation mark.
    span, glossed, _ = lemmas.declared(
        verse, words, verse.index("‘"), "Behold the man", "key"
    )
    assert span == glossed == (2, 4)
    # A repeated phrase is anchored by the word after the caller, and widened.
    span, glossed, _ = lemmas.declared(
        verse, words, verse.index("the man said"), "the man", "key"
    )
    assert (glossed, span) == ((6, 7), (6, 8))
    # Not after the word before, parted by its space or its comma.
    elsewhere = (verse.index(" ‘"), verse.index(", ‘"))
    for offset in (0, verse.index("the man’"), len(verse), *elsewhere):
        with pytest.raises(CheckFailed, match="does not stand before its lemma: key"):
            lemmas.declared(verse, words, offset, "Behold the man", "key")
    with pytest.raises(CheckFailed, match="not anchored once: key"):
        lemmas.declared(verse, words, 0, "the man", "key")


def test_a_preserved_scope_needs_its_caller_before_its_glossed_words() -> None:
    verse = "Behold Adam the man as Adam was."
    words = scripture.word_spans(verse)
    at = verse.index("Adam")
    span, glossed, rule = lemmas.preserved(
        verse, words, at, "Behold Adam", "Adam", "key"
    )
    assert (span, glossed, rule) == ((0, 1), (1, 1), "preserved passage note")
    assert lemmas.preserved(verse, words, 0, "Behold Adam", None, "key")[0] == (0, 1)
    assert lemmas.preserved(verse, words, len(verse), None, None, "key") == (
        None,
        None,
        "preserved passage note",
    )
    for offset in (0, at - 1, len(verse)):
        with pytest.raises(CheckFailed, match="does not stand before its lemma: key"):
            lemmas.preserved(verse, words, offset, "Behold Adam", "Adam", "key")


def test_a_1611_lemma_override_places_the_note_before_its_words() -> None:
    verse = "For verily he took not on him the nature of angels."
    words = scripture.word_spans(verse)
    override: NoteOverride = {"lemma": "he took not on him", "why": "The clause."}
    span, glossed, rule, first = lemmas.anchored(
        verse, words, ["took"], None, override, "key"
    )
    assert (span, glossed, rule) == ((2, 6), (2, 6), "override")
    assert first == 2
    # A null lemma, for a note on the whole verse, stays at the anchor.
    whole: NoteOverride = {"lemma": None, "why": "Whole."}
    *_, first = lemmas.anchored(verse, words, ["took"], None, whole, "key")
    assert first == 3


def placed(
    edition: bible.pipeline.Edition, key: str
) -> tuple[scripture.Verse, int, Node]:
    """A printed note by its key, with its verse and its place in it."""
    code = key.split()[0]
    row = next(row for row in edition.notes[code] if row["key"] == key)
    verse = scripture.verses(edition.documents[code])[row["reference"]]
    [(offset, note)] = [(at, n) for at, n in verse.notes if n.get("x-key") == key]
    return verse, offset, note


@pytest.mark.parametrize(
    "key, words",
    [
        ("GEN 2:23#3", "her husband"),
        ("DEU 21:5", "in his name"),
        ("ISA 19:3", "them that have in them a divining spirit"),
        ("JOS 13:1", "years"),
        ("JER 30:23 CCEL", "the Queen of the Palace"),
        ("PSA 93:1", "God of vengeance"),
        ("PRO 24:31", "weeds"),
        ("EXO 12:3", "lamb"),
        ("ISA 61:3", "the garment of glory"),
        ("ISA 61:3#2", "oil"),
        ("LEV 4:12 CCEL", "the ashes poured out"),
        ("JOB 33:26 CCEL", "he shall pray"),
        ("EXO 25:36 CCEL", "of one piece"),
        ("1CH 22:9 CCEL", "shall be born"),
        ("1CH 28:4 CCEL#2", "out of the whole"),
        ("EZK 36:31 CCEL", "your abominations"),
    ],
)
def test_brentons_caller_follows_its_declared_words(
    edition: bible.pipeline.Edition, key: str, words: str
) -> None:
    verse, offset, _ = placed(edition, key)
    assert offset == verse.text.index(words)
    if key.startswith("ISA 61:3"):
        assert [n["x-key"] for _, n in verse.notes] == ["ISA 61:3#2", "ISA 61:3"]


@pytest.mark.parametrize(
    "key, words, occurrence",
    [
        ("GEN 30:36", "and", 2),
        ("DEU 4:9", "keep thy heart", 1),
        ("JOS 21:13", "suburbs", 1),
        ("1KI 21:39", "thy life", 1),
        ("2KI 8:28#2", "king of the Syrians", 1),
        ("2KI 17:14", "their neck", 1),
        ("PSA 19:8", "glory", 2),
        ("JOB 11:12 CCEL", "buoyeth", 1),
        ("MIC 7:4 CCEL", "acteth by a rigid rule", 1),
        ("OBA 1:19 CCEL#2", "in the plain", 1),
        ("ISA 6:13", "shall be", 1),
        ("JER 45:2 CCEL", "remaineth", 1),
        ("EZK 17:15 CCEL", "acteth as an adversary", 1),
    ],
)
def test_context_does_not_move_a_callers_scope(
    edition: bible.pipeline.Edition, key: str, words: str, occurrence: int
) -> None:
    verse, offset, note = placed(edition, key)
    matches = list(re.finditer(r"\b" + re.escape(words) + r"\b", verse.text, re.I))
    assert offset == matches[occurrence - 1].start()
    # The printed lemma may add context, but must still identify one passage.
    lemma = notes.lemma_of(note)
    assert lemma is not None
    assert verse.text.count(lemma) == 1


@pytest.mark.parametrize(
    "key, lemma",
    [
        ("OBA 1:19 CCEL#2", "in the plain"),
        ("EXO 12:3", "lamb"),
        ("2KI 8:28#2", "king of the Syrians"),
    ],
)
def test_commentary_lemmas_have_no_whole_lemma_alternatives(
    edition: bible.pipeline.Edition, key: str, lemma: str
) -> None:
    _, _, note = placed(edition, key)
    assert notes.lemma_of(note) == lemma
    assert not any(n.get("marker") == "fqa" for n in usj.walk(note["content"]))


@pytest.mark.parametrize(
    "key, quoted",
    [
        ("JOS 21:13", ["suburbs", "glebe"]),
        ("MIC 7:4 CCEL", ["goeth upon"]),
        ("JOB 33:26 CCEL", ["having prayed"]),
    ],
)
def test_lexical_commentary_does_not_echo_a_widened_lemma(
    edition: bible.pipeline.Edition, key: str, quoted: list[str]
) -> None:
    _, _, note = placed(edition, key)
    assert not any(n.get("marker") == "fqa" for n in usj.walk(note["content"]))
    assert [
        usj.text_of(n["content"])
        for n in usj.walk(note["content"])
        if usj.is_type(n, "char", "it")
    ] == quoted


@pytest.mark.parametrize(
    "key, replacements",
    [
        ("GEN 30:36", ["between them and between Jacob"]),
        ("PSA 19:8", ["we will be magnified in the name"]),
        ("JOB 11:12 CCEL", ["man vainly floats himself", "man vainly swims himself"]),
        ("ISA 6:13", ["there is a tenth"]),
        ("JER 45:2 CCEL", ["He that dwelleth in this city"]),
        ("EZK 17:15 CCEL", ["he that acteth perversely be preserved"]),
        ("LEV 4:12 CCEL", ["burnt on the outpouring of the ashes."]),
        ("EZK 44:13 CCEL", ["approach the sanctuary of the children"]),
        ("EZK 47:9 CCEL", ["this water cometh thither", "this water is come thither"]),
        ("EZK 21:20 CCEL", ["slaughter, it hath happened well for glittering."]),
        ("EXO 25:36 CCEL", ["the branches be of it, altogether"]),
        ("1CH 22:9 CCEL", ["Behold, a son is born to thee"]),
        ("1CH 28:4 CCEL#2", ["chose me from the whole house"]),
        ("1CH 28:4 CCEL#3", ["he preferred in me, that"]),
    ],
)
def test_alternatives_preserve_their_sentences_subjects_and_context(
    edition: bible.pipeline.Edition, key: str, replacements: list[str]
) -> None:
    verse, _, note = placed(edition, key)
    lemma = notes.lemma_of(note)
    assert lemma is not None
    alternatives = [
        usj.text_of(n["content"]).strip()
        for n in usj.walk(note["content"])
        if n.get("marker") == "fqa"
    ]
    assert len(alternatives) == len(replacements)
    for alternative, expected in zip(alternatives, replacements):
        assert expected in verse.text.replace(lemma, alternative, 1)


@pytest.mark.parametrize(
    "key, context, lemma, revised, alternative, revised_alternative",
    [
        ("JOB 11:12 CCEL", "man vainly buoys", "buoys", "buoyeth", "floats", "floats"),
        (
            "JER 45:2 CCEL",
            "that remains",
            "remains",
            "remaineth",
            "dwelleth",
            "dwelleth",
        ),
        (
            "EZK 17:15 CCEL",
            "that acts as an adversary",
            "acts as an adversary",
            "acteth as an adversary",
            "acts perversely",
            "acteth perversely",
        ),
    ],
)
def test_narrow_lemmas_follow_grammar_without_revising_nouns_or_commentary(
    declared: bible.policy.Policy,
    key: str,
    context: str,
    lemma: str,
    revised: str,
    alternative: str,
    revised_alternative: str,
) -> None:
    source = book(
        "GEN",
        f"\\v 9 {context}; buoys; remains; acts."
        f"\\f - \\fr 99:9 \\fq {lemma}: \\ft or, \\fqa {alternative}"
        r"\ft ; man vainly buoys; that remains; that acts.\f*",
    )
    [note] = usj.notes_of(source["content"])
    note["x-key"] = key
    before = deepcopy(source)
    doc = revision.respelled(source, declared, set())
    verse = scripture.verses(doc)["99:9"]
    assert verse.text == context.replace(lemma, revised) + "; buoys; remains; acts."
    [(_, note)] = verse.notes
    assert notes.lemma_of(note) == revised
    assert [
        usj.text_of(n["content"])
        for n in usj.walk(note["content"])
        if n.get("marker") == "fqa"
    ] == [revised_alternative]
    assert usj.text_of(note["content"]).endswith(
        "; man vainly buoys; that remains; that acts."
    )
    assert source == before


def test_a_note_in_the_wrong_verse_is_set_on_its_words_in_the_right_one(
    ctx: bible.annotate.Context, policy: bible.policy.Policy
) -> None:
    verses = (
        "\\v 7 And there shall be two parties among you.\n"
        r"\v 9 both those that went in, \f + \fr 99:9 \fqa Gr. \ft hands.\f*and those that went out."
    )

    def with_exception(entry: dict[str, Any]) -> dict[str, str]:
        moved = changed(
            policy,
            "brenton_notes",
            lambda data: data["notes"].update({"GEN 99:9": entry}),
        )
        return printed(verses, annotate.Context(moved, *list(vars(ctx).values())[1:]))

    why = {"why": "hands renders parties"}
    assert with_exception({"verse": "99:7", "lemma": "parties", **why}) == {
        "7": r"And there shall be two \f - \fr 99:7 \fq parties: \ft Gr. \fqa hands\f*parties among you.",
        "9": "both those that went in, and those that went out.",
    }
    # It moves to another verse of its book, where its words are.
    for verse in ("99:9", "99:8"):
        with pytest.raises(CheckFailed, match="moved to no other verse"):
            with_exception({"verse": verse, "lemma": "parties", **why})
    with pytest.raises(CheckFailed, match="not found"):
        with_exception({"verse": "99:7", "lemma": "sides", **why})


def test_a_note_that_is_a_sentence_takes_a_capital_and_a_full_stop(
    ctx: bible.annotate.Context, policy: bible.policy.Policy
) -> None:
    doc = book("MAT", r"\v 2 and paid an hundred pence to the keeper of the house.")
    listed = [
        dict(
            key="MAT 99:2 pence",
            reference="99:2",
            lemma="pence",
            note="the Roman penny is the eighth part of an ounce",
        ),
        dict(
            key="MAT 99:2 keeper", reference="99:2", lemma="keeper", note="Or, porter."
        ),
    ]
    before, listed_before = deepcopy(doc), deepcopy(listed)
    result, report = annotate.george("MAT", doc, listed, ctx, original=doc)
    assert doc == before and listed == listed_before
    assert verse_lines(result)["2"] == (
        r"and paid an hundred \f - \fr 99:2 \fq pence: \ft The Roman penny is the eighth "
        r"part of an ounce.\f*pence to the \f - \fr 99:2 \fq keeper: \ft or, \fqa porter\f*"
        "keeper of the house."
    )
    assert [row["rule"] for row in report.rows] == ["anchor", "anchor"]


def rendering_note(
    verse: str, lemma: str, former: str, witness: str | None = None
) -> Node:
    return usj.note(
        "f",
        usj.char("fr", verse + " "),
        usj.char("fl", "Vulgate ") if witness else usj.char("ft", "Or, "),
        usj.char("fqa", former),
        caller="+",
        **usj.Extra(
            {
                "x-key": f"MAT {verse} rendering",
                "category": "edition",
                "x-scope": {"declared": lemma, "witness": witness},
            }
        ),
    )


def test_a_reversed_margin_stands_for_the_rendering_note_it_repeats(
    ctx: bible.annotate.Context,
) -> None:
    """Matthew 25:8 adopts the margin's "going out"; the margin, turned round,
    says what the edition's own note on the correction says, and stands for
    it. A former-reading decision that covers no such note is stale."""
    text = r"\v 8 Give us of your oil; for our lamps are going out."
    original = book("MAT", text.replace("going", "gone"), chapter=25)
    margin = dict(
        key="MAT 25:8 gone out",
        reference="25:8",
        lemma="gone out",
        note="Or, going out.",
    )

    def corrected(note: Node) -> Document:
        doc = book("MAT", text, chapter=25)
        verse = scripture.verses(doc)["25:8"]
        at = verse.text.index("going")
        return scripture.edited(doc, [(verse, at, at, [note])])

    doc = corrected(rendering_note("25:8", "going out", "gone out"))
    printed, report = annotate.george("MAT", doc, [margin], ctx, original=original)
    assert report.covered == ["MAT 25:8 rendering"]
    assert [n["x-key"] for _, n in scripture.verses(printed)["25:8"].notes] == [
        "MAT 25:8 gone out"
    ]
    assert "or, \\fqa gone out" in verse_lines(printed)["8"]
    # A lemma widened past the anchor says the same.
    doc = corrected(rendering_note("25:8", "lamps are going out", "lamps are gone out"))
    _, report = annotate.george("MAT", doc, [margin], ctx, original=original)
    assert report.covered == ["MAT 25:8 rendering"]
    # A note saying something else is not covered, and the decision is stale.
    doc = corrected(rendering_note("25:8", "going out", "burning"))
    with pytest.raises(CheckFailed, match="covers no rendering note"):
        annotate.george("MAT", doc, [margin], ctx, original=original)
    # A note that names a witness cannot be left out for the margin.
    doc = corrected(rendering_note("25:8", "going out", "gone out", "vulgate"))
    with pytest.raises(CheckFailed, match="names a witness"):
        annotate.george("MAT", doc, [margin], ctx, original=original)


def test_a_note_of_the_margin_must_find_its_words_once(
    ctx: bible.annotate.Context,
) -> None:
    doc = book("MAT", r"\v 2 of the house of the keeper.")
    note = dict(key="MAT 99:2 of", reference="99:2", lemma="of", note="Or, from.")
    with pytest.raises(CheckFailed, match="not found exactly once"):
        annotate.george("MAT", doc, [note], ctx, original=doc)
    with pytest.raises(CheckFailed, match="verse missing"):
        annotate.george("MAT", doc, [{**note, "reference": "99:3"}], ctx, original=doc)


def test_a_declared_change_of_wording_is_carried_through_a_notes_parts() -> None:
    pieces = notes.labelled_pieces("Or, after 5. shillings the ounce.")
    body = notes.source_body(
        pieces, [], None, "key", "Or, after 5. shillings the ounce."
    )
    edited = notes.edited(body, "5.", "five", "key")
    assert edited.plain == "Or, after five shillings the ounce."
    # The rendering ended at the number's stop, and still ends at the number.
    assert (body.alternative, edited.alternative) == ("after 5", "after five")
    with pytest.raises(CheckFailed, match="does not apply once"):
        notes.edited(body, "6.", "six", "key")


def test_a_change_that_rewrites_a_term_drops_it(
    ctx: bible.annotate.Context,
) -> None:
    source = "Alex. ours, but Heb. and Vat. 'your.'"
    body = notes.with_terms(
        notes.source_body(notes.labelled_pieces(source), [], None, "key", source),
        ctx.terms,
    )
    edited = notes.edited(body, "Heb. and Vat.", "Heb. and Valpy", "key")
    assert [edited.plain[t.start : t.end] for t in edited.terms] == ["Alex.", "Heb."]
    runs, terms, _ = notes.displayed(edited)
    printed = notes.text_of(notes.finished(runs, terms, None, None, ctx.terms, "key"))
    assert "Valpy" in printed and "Vat." not in printed


@pytest.mark.parametrize(
    "before,after", [("Heb.", "Heb. lit."), ("but Heb.", "but the Heb.")]
)
def test_words_added_beside_a_term_are_not_its_own(
    ctx: bible.annotate.Context, before: str, after: str
) -> None:
    source = "Alex. ours, but Heb. and Vat. 'your.'"
    body = notes.with_terms(
        notes.source_body(notes.labelled_pieces(source), [], None, "key", source),
        ctx.terms,
    )
    edited = notes.edited(body, before, after, "key")
    assert [edited.plain[t.start : t.end] for t in edited.terms] == [
        "Alex.",
        "Heb.",
        "Vat.",
    ]
    runs, terms, _ = notes.displayed(edited)
    printed = notes.text_of(notes.finished(runs, terms, None, None, ctx.terms, "key"))
    assert after in printed


@pytest.mark.parametrize(
    "source, before, after, expected",
    [
        ("Or, forbid; lit. take away.", "forbid;", "forbid.", "forbid. Lit. take"),
        ("Heb. Marah. lit. Bitternesses.", "Marah.", "Marah;", "Marah; lit. Bit"),
    ],
)
def test_a_change_of_words_decides_where_lit_stands_again(
    ctx: bible.annotate.Context, source: str, before: str, after: str, expected: str
) -> None:
    body = notes.with_terms(
        notes.source_body(notes.labelled_pieces(source), [], None, "key", source),
        ctx.terms,
    )
    edited = notes.edited(body, before, after, "key")
    runs, terms, _ = notes.displayed(edited)
    printed = notes.text_of(notes.finished(runs, terms, None, None, ctx.terms, "key"))
    assert expected in printed


@pytest.mark.parametrize(
    "words", ["Gr. sing.", "Gr. fut.", "Conf. Luke 15:20", "Heb. Grammar, p. 92"]
)
def test_an_abbreviation_written_out_by_a_decision_is_refused_where_it_stays(
    words: str,
) -> None:
    with pytest.raises(CheckFailed, match="Abbreviations not in Chicago's forms"):
        terminology.check_forms("GEN", words, note=True)


def test_witness_names_keep_their_capital_after_a_lemma(
    ctx: bible.annotate.Context,
) -> None:
    for source in ("Cotton Genesis his.", "Sinaiticus correcting hand c.a thine."):
        body = notes.with_terms(
            notes.source_body(notes.labelled_pieces(source), [], None, "key", source),
            ctx.terms,
        )
        runs, terms, _ = notes.displayed(body)
        printed = notes.text_of(
            notes.finished(runs, terms, "their", None, ctx.terms, "key")
        )
        assert printed.startswith(source.split()[0])


@pytest.mark.parametrize(
    "source,before,after,expected",
    [
        (
            "Or, signify that man.",
            "signify that man",
            "our word, signify that man",
            "our word, signify that man",
        ),
        ("Or, Abodes.", "Abodes", "Abodes of wisdom are", "Abodes of wisdom are"),
    ],
)
def test_inserted_note_context_keeps_the_renderings_style(
    source: str, before: str, after: str, expected: str
) -> None:
    body = notes.source_body(notes.labelled_pieces(source), [], None, "key", source)
    edited = notes.edited(body, before, after, "key")
    assert edited.alternative == expected
    runs, _, _ = notes.displayed(edited)
    assert [value for role, value in runs if role == "reading"] == [expected]
    assert body.plain == source


@pytest.mark.parametrize(
    "words, expected",
    [
        ("Alex. omits 'not.'", "Alex. omits _not_"),
        (
            "The Greek word is different from that translated ‘suburbs.’ above.",
            "The Greek word is different from that translated _suburbs_. above.",
        ),
        ("Heb. שופרות ‘ram's horns.’", "Heb. שופרות _ram's horns_"),
        ("The rendering is 'he destroyed.'", "The rendering is _he destroyed_."),
        (
            "The author quotes 'et tota terra non prandebat.'",
            "The author quotes _et tota terra non prandebat_.",
        ),
        ("Brenton's note has no quotation.", "Brenton's note has no quotation."),
        ("Gr. of their fathers' families.", "Gr. _of their fathers' families_"),
        ("Gr. the fathers'.", "Gr. _the fathers'_"),
        # "Gr. sing." keeps its stop as an abbreviation; the verb does not.
        ("Or, they shall sing.", "or, _they shall sing_"),
    ],
)
def test_quoted_words_use_italic_without_quotation_marks(
    words: str, expected: str, policy: bible.policy.Policy
) -> None:
    body = notes.interpreted(notes.labelled_pieces(words), "key")
    body = notes.with_terms(body, terminology.registry(policy))
    runs, terms, _ = notes.displayed(body)
    result = notes.finished(
        runs, terms, "lemma", None, terminology.registry(policy), "key"
    )
    assert notes.underscored(result) == expected


@pytest.mark.parametrize(
    "words",
    [
        # A plural possessive within single marks, or after them.
        "Gr. 'the fathers' houses.'",
        "Gr. ‘the fathers’ houses.’",
        "Gr. 'the sons' and their fathers' houses.",
        "Gr. 'the fathers' houses' and 'the sons.'",
    ],
)
def test_quotation_marks_that_pair_in_two_ways_are_refused(words: str) -> None:
    body = notes.interpreted(notes.labelled_pieces(words), "key")
    with pytest.raises(CheckFailed, match="Ambiguous quotation marks"):
        notes.displayed(body)


def test_a_label_opens_a_note_only_as_a_whole_word() -> None:
    assert notes.LABEL_START.match("See the note above.")
    assert notes.LABEL_START.match("Gr. meeting.")
    assert not notes.LABEL_START.match("Seeing that it is so.")
    assert not notes.LABEL_START.match("Hebrews are meant.")


def test_an_exception_declares_its_italics_and_must_differ_from_the_rules(
    policy: bible.policy.Policy,
) -> None:
    registry = terminology.registry(policy)

    def printed_note(source: str, override: str) -> str:
        body = notes.source_body(
            notes.labelled_pieces(source),
            [],
            override,
            "key",
            source,
        )
        runs, terms, _ = notes.displayed(notes.with_terms(body, registry))
        return notes.underscored(
            notes.finished(runs, terms, "lemma", None, registry, "key")
        )

    # Quoted words that an exception leaves roman stay roman.
    assert (
        printed_note(
            "Or, 'but he that is without fear (sc. of the Lord) shall dwell' etc.",
            "Or, '{but he that is without fear} (sc. of the Lord) {shall dwell}' etc.",
        )
        == "or, _but he that is without fear_ (sc. of the Lord) _shall dwell_ etc."
    )
    assert printed_note("Or, windows.", "Or, _windows_.") == "or, _windows_"
    # One that only repeats the italics of the rules, quoted words among
    # them, changes nothing.
    with pytest.raises(CheckFailed, match="Note override changes nothing: key"):
        printed_note(
            "Or, windows, see above, there rendered 'flood-gates.'",
            "Or, {windows}, see above, there rendered '_flood-gates_.'",
        )


@pytest.mark.parametrize(
    "english, italic",
    [
        ("valley of trouble", True),
        ("the back of the neck", True),
        ("rose or stood", True),
        ("ambiguous", False),
        ("a particle of entreaty, here rendered literally", False),
        ("name of a town", False),
        ("is retained in the Greek", False),
        ("as if העבדים", False),
    ],
)
def test_a_hebrew_gloss_is_italic_without_measuring_the_lemma(
    english: str, italic: bool
) -> None:
    body = notes.interpreted(
        [("label", "Heb. "), ("text", "ערף " + english + ".")], "key"
    )
    assert body.alternative is None
    assert any(role == "quotation" for _, _, role in body.roles) == italic


def test_the_notes_the_edition_writes_say_what_each_part_is() -> None:
    note = usj.note(
        "f",
        *usj.parse(
            r"\fl Vat. \fqa forty cubits\ft . \fl Gr. \fq its length\ft , etc.",
            fragment=True,
        ),
    )
    body = notes.authored_body(note, None, "key")
    assert [(role, body.plain[a:b]) for a, b, role in body.roles] == [
        ("label", "Vat. "),
        ("alternative", "forty cubits"),
        ("text", ". "),
        ("label", "Gr. "),
        ("quotation", "its length"),
        ("text", ", etc."),
    ]
    assert (body.alternative, body.rule) == ("forty cubits", "rendering")
    with pytest.raises(CheckFailed, match="Unknown part"):
        notes.authored_body(usj.note("f", usj.char("fk", "x")), None, "key")


@pytest.mark.parametrize(
    "words, expected",
    [
        ("so in the Sept. and A. V. also", "so in the LXX and KJV also"),
        ("AV margin", "KJV margin"),
        ("Eng. Ver. margin", "KJV margin"),
        ("Authorized Version margin", "KJV margin"),
        ("English Version margin", "KJV margin"),
        ("English Bible margin", "KJV margin"),
        # The period of a form the label replaces still ends its sentence.
        ("so the Eng. Ver. The Heb. reads", "so the KJV. The Heb. reads"),
        ("Ald. reads", "Aldine text reads"),
        ("Complut. reads", "Complutensian text reads"),
        ("see the MS. Then the Vulg. reads", "see the MS. Then the Vulgate reads"),
        ("in the year a.d. 126, or b.c. 217", "in the year AD 126, or 217 BC"),
        ("scil. the people, &c.", "sc. the people, etc."),
        ("Alex. + the Lord.", "Alex. adds the Lord."),
        ("Heb. and Alex. + and she fell.", "Heb. and Alex. add and she fell."),
        ("Alex. and Vat. — these words.", "Alex. and Vat. omit these words."),
        ("Alex. Vat. — the clause.", "Alex. Vat. omits the clause."),
        ("Heb. — Isaac being troubled.", "Heb. omits Isaac being troubled."),
        ("Alex. — 'not.'", "Alex. omits 'not.'"),
        ("Gr. from. Heb.—מ.", "Gr. from. Heb.—מ."),
        # CCEL closes up the sign of omission; its decision writes the note.
        ("Alex.—'humbly.'", "Alex.—'humbly.'"),
        # "lit." is capitalized where it begins a sentence, and nowhere else.
        ("Gr. Lit. them.", "Gr. lit. them."),
        ("Heb. Marah. lit. Bitternesses.", "Heb. Marah. Lit. Bitternesses."),
        ("Or, forbid; lit. take away.", "Or, forbid; lit. take away."),
        ("etc. Lit. Why have.", "etc. Lit. Why have."),
        ("Lit. beams.", "Lit. beams."),
        ("lit. beams.", "lit. beams."),
        # A label's stop that "lit." continues ends no sentence, whatever
        # capital the source gives "lit.", and takes no stop of its own.
        ("Sept. Lit. them.", "LXX lit. them."),
        ("Vulg. lit. them.", "Vulgate lit. them."),
        ("A. V. Lit. them.", "KJV lit. them."),
        ("(Heb.) lit. them.", "(Heb.) lit. them."),
        ("Gr. finishing — cutting.", "Gr. finishing — cutting."),
        ("Note. - This rendering.", "Note. - This rendering."),
    ],
)
def test_terms_print_in_the_editions_forms(
    words: str, expected: str, policy: bible.policy.Policy
) -> None:
    registry = terminology.registry(policy)
    assert (
        usj.serialize(
            terminology.printed(
                [words], terminology.found([words], registry, note=True), registry
            )
        )
        == expected
    )


@pytest.mark.parametrize(
    "words, message",
    [
        ("Complut. + and they went.", "Sign after no witness"),
        ("Complut. — and they went.", "Sign after no witness"),
        ("Alex. +'and they went.'", "Sign closed up to its words"),
        ("Gr. one + one.", "Sign after no witness"),
        ("Alex.+ 'and they went.'", "Sign closed up to its witness"),
    ],
)
def test_a_sign_after_no_witness_is_refused(
    words: str, message: str, policy: bible.policy.Policy
) -> None:
    registry = terminology.registry(policy)
    with pytest.raises(CheckFailed, match=message):
        terminology.recognize(words, registry)
    # Prose has no signs to read.
    assert terminology.recognize(words, registry, note=False)


def test_every_note_is_printed_replaced_by_a_link_or_explicitly_omitted(
    edition: bible.pipeline.Edition,
) -> None:
    # Unreported Alexandrine readings add notes without consuming sources.
    assert edition.summary["printed_notes"] == 6273
    rows = [row for listed in edition.notes.values() for row in listed]
    assert len({row["key"] for row in rows}) == len(rows)
    # The 1611 margin is printed on the New Testament alone, and whole but
    # for the notes whose reading the Byzantine text prints, or which gloss
    # words of the Received Text the edition no longer has; the Textus
    # Receptus notes stand among them.
    margin = sum(
        len(
            [
                row
                for row in edition.notes[u["id"]]
                if not re.search(r" (TR|rendering)(#\d+)?$", row["key"])
            ]
        )
        for u in edition.policy.scripture
        if u["source"] == "kjv"
    )
    omitted = sum(
        1 for o in edition.policy.kjv_notes["notes"].values() if o.get("omitted")
    )
    assert edition.summary["kjv_marginal_notes"] == 775
    assert margin == 775 - omitted == 758
    assert edition.summary["byzantine_notes"] == 961
    # A widened lemma's rendering takes in the same words (Matthew 6:1).
    row = next(row for row in edition.notes["MAT"] if row["key"] == "MAT 6:1 of")
    assert (row["lemma"], row["note"]) == ("of your Father", "or, _with your Father_")


def test_an_inferred_lemma_has_the_shape_of_its_rendering(
    edition: bible.pipeline.Edition, policy: bible.policy.Policy
) -> None:
    """A lemma that a rule found, and nobody has read, should be about as
    long as the rendering that measured it. One much longer is read once, and
    listed with what was found (edition/brenton-notes.json, "shapes")."""
    read = policy.brenton_notes["shapes"]
    assert all(read.values()), "Unexplained lemma shape"
    decided = {"override", "edition reading", "preserved passage note"}
    brenton = [u["id"] for u in policy.scripture if u["source"] == "brenton"]
    flagged = {
        row["key"]
        for code in brenton
        for row in edition.notes[code]
        if row["rule"] not in decided
        and lemmas.misshapen(row["glossed"], row["reading"])
    }
    assert flagged == set(read)
    # The check tells a rendering from words it can't be of.
    assert lemmas.misshapen("those that went out on the sabbath-day", "hands")
    assert not lemmas.misshapen("captain of the guard", "chief cook")
    assert not lemmas.misshapen("friend", "he that gives away in marriage")
    assert not lemmas.misshapen("five hundred and eighty", "450")


def inferred(verse: str, note: str, kind: str = "f") -> tuple[str | None, str]:
    """The lemma inferred for a note whose caller stands at ‸ in the verse."""
    offset = verse.index("‸")
    verse = verse.replace("‸", "")
    words = scripture.word_spans(verse)
    body = notes.interpreted(notes.labelled_pieces(note), "K")
    span, _, rule = lemmas.inferred_lemma(
        kind, verse, words, offset, body.alternative, addition=body.addition
    )
    return (lemmas.lemma_text(verse, words, span) if span else None), rule


@pytest.mark.parametrize(
    "verse, note, expected",
    [
        (
            "And Abel ‸also brought of the firstborn.",
            "Gr. he also",
            ("also", "last-word"),
        ),
        (
            "O my people, your exactors ‸strip you, and extortioners",
            "Gr. glean you",
            ("strip you", "last-word"),
        ),
        (
            "the ‸captain of the guard, an Egyptian",
            "Gr. chief cook",
            ("captain of the guard", "length"),
        ),
        (
            "thou shalt eat flesh according to ‸all the desire of thy soul.",
            "Gr. in all",
            ("all the desire", "last-word"),
        ),
        ("had sheep, and oxen, ‸and tents.", "Alex. cattle", ("tents", "length")),
        (
            "And God made great ‸whales, and every living reptile",
            "Or, probably any large fish",
            ("whales", "explanatory"),
        ),
        ("with sorrow to the grave. ‸", "Gr. Hades", ("grave", "length before")),
        # Before the caller, the words run from the rendering's first word.
        (
            "and I remembered the covenant with you.‸",
            "Lit. your covenant",
            ("the covenant with you", "last-word before"),
        ),
        (
            "and he approached the Philistine. ‸",
            "Verse 41 is wanting.",
            (None, "verse-level"),
        ),
        # A possessive rendering another glosses it alone.
        (
            "male and female he made them, and called ‸his name Adam",
            "Alex. their",
            ("his", "length"),
        ),
        # So does a preposition or conjunction rendering another, if it occurs
        # once in the verse.
        (
            "and he took him up to him ‸into the chariot.",
            "Gr. upon",
            ("into", "length"),
        ),
        (
            "he went into the house, and ‸into the chariot.",
            "Gr. upon",
            ("into the chariot", "length"),
        ),
        # A comment is about more than a lone conjunction.
        (
            "‸For, behold, thine enemies shall perish",
            "Alex. + for behold thine enemies",
            ("For, behold", "explanatory"),
        ),
        # The caller can follow the first word the rendering replaces.
        (
            "And Sychem the son of Emmor the ‸Evite, the ruler of the land",
            "Alex. the Chorrhæan",
            ("the Evite", "length"),
        ),
        # A lemma occurring twice in its verse is widened until it occurs once.
        (
            "In his dream to Joseph, and said, In my ‸dream a vine",
            "Gr. sleep",
            ("my dream", "length"),
        ),
    ],
)
def test_the_rules_find_the_words_a_note_is_about(
    verse: str, note: str, expected: tuple[str | None, str]
) -> None:
    assert inferred(verse, note) == expected


@pytest.mark.parametrize(
    "note",
    [
        "Alex. + 'new words'.",
        "Alex. adds 'new words'.",
        'Alex. add "new words".',
        "Alex. insert ‘new words’.",
        "Alex. inserts, “new words”.",
        "Gr. Alex. + εἰς ὁμοιότητα.",
    ],
)
def test_addition_syntax_survives_italic_overrides(note: str) -> None:
    body = notes.interpreted(notes.labelled_pieces(note), "key")
    assert body.addition
    assert notes.declared_readings(body, body.plain, "key").addition
    assert inferred("He said, Tell us ‸what happened.", note) == (
        "Tell us",
        "addition before",
    )


def test_joined_witness_labels_introduce_an_addition() -> None:
    note = usj.note(
        "f",
        *usj.parse(
            r"\fqa Heb. \ft and \fqa Alex. \ft insert ‘new words’.", fragment=True
        ),
    )
    body = notes.interpreted(notes.source_pieces(note), "key")
    assert body.addition
    assert body.alternative == "new words"


@pytest.mark.parametrize(
    "verse, expected",
    [
        ("He said, Tell us.‸", "Tell us"),
        ("He said, Tell us ‸\nwhat happened.", "Tell us"),
        (
            "One two three four five six seven eight nine ‸then.",
            "One two three four five six seven eight nine",
        ),
        (
            "One two three four five six seven eight nine ten ‸then.",
            "seven eight nine ten",
        ),
        ("Tell us, Tell us ‸what happened.", "Tell us what"),
        (
            "One two three four five six seven flood-gates opened ‸then.",
            "seven flood-gates opened",
        ),
        (
            "One two three four five flood-gates six seven eight ‸then.",
            "flood-gates six seven eight",
        ),
    ],
)
def test_additions_select_the_preceding_clause(verse: str, expected: str) -> None:
    assert inferred(verse, "Alex. adds 'new words'.") == (expected, "addition before")


@pytest.mark.parametrize("note", ["Alex. + for David.", "Alex. adds 'for David'."])
def test_additions_at_verse_start_keep_existing_inference(note: str) -> None:
    assert inferred("‸A Song of Degrees. O Lord.", note) == (
        "A Song of Degrees" if "+" in note else "A Song",
        "explanatory" if "+" in note else "length",
    )


@pytest.mark.parametrize("note", ["Gr. add these things.", "Gr. add words."])
def test_literal_add_is_a_rendering(note: str) -> None:
    body = notes.interpreted(notes.labelled_pieces(note), "key")
    assert not body.addition
    assert body.alternative == note[4:-1]


@pytest.mark.parametrize(
    "note", ['Alex. adds "new words" at the end.', "Alex. adds `new words' at the end."]
)
def test_an_added_reading_ends_with_its_quotation_marks(note: str) -> None:
    assert notes.interpreted(notes.labelled_pieces(note), "key").alternative == (
        "new words"
    )


def test_an_addition_beside_the_measuring_rendering_does_not_place_the_lemma() -> None:
    body = notes.interpreted(notes.labelled_pieces("Heb. the Lord; Alex. + God."), "K")
    assert body.alternative == "the Lord"
    assert not body.addition


def test_additions_do_not_echo_words_from_a_widened_lemma(
    ctx: bible.annotate.Context,
) -> None:
    result = printed(
        r"\v 1 Tell us, Tell us \f + \fr 99:1 \fqa Alex. \ft adds 'new words'.\f*what happened.",
        ctx,
    )["1"]
    assert result == (
        r"Tell us, Tell us \f - \fr 99:1 \fq Tell us what: \ft Alex. adds \fqa new words\f*what happened."
    )


def test_a_widened_rendering_that_repeats_its_lemma_is_refused(
    ctx: bible.annotate.Context,
) -> None:
    # Widened to "your sins", a rendering "your" of the second your would
    # print the lemma again; "their" still takes in the widened word.
    verse = r"\v 1 for your deeds and for \f + \fr 99:1 \fqa Alex. \ft {}.\f*your sins."
    assert (
        r"\fq your sins: \ft Alex. \fqa their sins\f*"
        in printed(verse.replace("{}", "their"), ctx)["1"]
    )
    with pytest.raises(CheckFailed, match="Widened rendering repeats its lemma"):
        printed(verse.replace("{}", "your"), ctx)
    # Nor does the verse's capital make it differ.
    opening = r"\v 1 \f + \fr 99:1 \fqa Alex. \ft your.\f*Your sins, and your deeds."
    with pytest.raises(CheckFailed, match="Widened rendering repeats its lemma"):
        printed(opening, ctx)


def test_surviving_additions_keep_their_printed_words(
    edition: bible.pipeline.Edition,
    policy: bible.policy.Policy,
) -> None:
    rows = {r["key"]: r for listed in edition.notes.values() for r in listed}
    expected = {
        "GEN 1:11#2": (
            "according to its kind on the earth",
            "Alex. adds εἰς ὁμοιότητα",
            "override",
        ),
        "JON 1:8": (
            "for whose cause this evil is upon us",
            "Vat. omits",
            "edition reading",
        ),
        "PSA 132:1": ("A Song of Degrees", "Alex. adds _for David_", "explanatory"),
    }
    for key, values in expected.items():
        assert tuple(rows[key][field] for field in ("lemma", "note", "rule")) == values
    assert "JON 1:8" not in policy.brenton_notes["notes"]
    assert (
        policy.brenton_notes["notes"]["GEN 1:11#2"]["lemma"]
        == "according to its kind on the earth"
    )


@pytest.mark.parametrize(
    "verse, expected",
    [
        ("And ‸ Moses took the blood and sprinkled it.", (None, "xref-verse")),
        # A clause of up to eight words is shown whole.
        (
            "And having measured the homer full, ‸ he that had gathered much had nothing over",
            ("he that had gathered much had nothing over", "xref-opening"),
        ),
        (
            "Therefore behold I will remove them: and ‸ I will destroy the wisdom of the wise and the prudent men",
            ("I will destroy the wisdom", "xref-opening"),
        ),
    ],
)
def test_a_cross_reference_shows_where_its_quotation_begins(
    verse: str, expected: tuple[None | str, ...]
) -> None:
    assert inferred(verse, "See Rom. 1. 1.", kind="x") == expected


def test_passages_set_in_another_order_are_noted_alike_in_both_testaments(
    edition: bible.pipeline.Edition,
) -> None:
    # Where the Greek sets a passage in another order than the text the King
    # James Bible follows, the Hebrew's in the Old Testament and the Received
    # Text's in the New, a note at its first verse says where that text has
    # it, and a note where it left says where it is printed: labelled with
    # the text, and running on without a full stop, as labelled notes do.
    rows = {
        row["key"]: (row["reference"], row["note"])
        for code in ("PRO", "ROM", "MAT")
        for row in edition.notes[code]
    }
    # In the Old Testament the passages print the Hebrew's labels where they
    # stand, so only the note where they left is set.
    assert "PRO 24:22f Heb." not in rows
    assert rows["PRO 29:27 Heb."] == (
        "29:27",
        "Heb. has here 30:1–14, 30:15–33, and 31:1–9, printed in chapter 24",
    )
    assert rows["ROM 14:24 TR"] == ("14:24", "TR has this passage at 16:25–27")
    assert rows["ROM 16:24 TR"] == (
        "16:24",
        "TR has here the verses printed at 14:24–26",
    )
    # Scrivener alone has the two woes in this order, as Beza does
    # (received.py).
    assert rows["MAT 23:13 TR"] == ("23:13", "Beza has this passage at 23:14")


def test_an_omission_quotes_only_the_part_of_its_lemma_that_is_omitted(
    edition: bible.pipeline.Edition,
) -> None:
    # Both witnesses leave the words out of the note where the lemma is what
    # is omitted, since it stands before the label ("Vat. omits", "TR omits"),
    # and quote the omitted words where they are a part of the lemma.
    rows = {
        row["key"]: (row["lemma"], row["note"])
        for code in ("GEN", "MAT", "JAS")
        for row in edition.notes[code]
    }
    assert rows["GEN 8:7#2"] == ("to see if the water had ceased", "Valpy omits")
    assert rows["GEN 3:22"] == ("the Lord God said", "Valpy omits _the Lord_")
    assert rows["MAT 18:19#1 TR"] == ("verily", "TR omits")
    assert rows["JAS 4:12#1 TR"] == ("but who", "TR omits _but_")
    for code in edition.scripture:
        for row in edition.notes[code]:
            if row["note"].startswith("TR omits _"):
                assert row["note"] != f"TR omits _{row['lemma']}_", row["key"]


@pytest.mark.parametrize(
    "key, anchor, former, cited",
    [
        ("MAT 25:8 gone out", "going out", "gone out", ""),
        ("MRK 7:4 pots", "beds", "tables", ""),
        (
            "ROM 6:17 which was delivered you",
            "whereto ye were delivered",
            "which was delivered you",
            "",
        ),
        ("1CO 8:6 in him", "for him", "in him", ""),
        (
            "1TH 1:4 beloved, your election of God",
            "beloved of God, your election",
            "beloved, your election of God",
            "",
        ),
        ("1TH 4:6 in any matter", "in the matter", "in any matter", ""),
        ("HEB 6:7 by", "for whose sake", "by whom", ""),
        ("2PE 1:3 to", "by glory and virtue", "to glory and virtue", ""),
    ],
)
def test_former_readings_restore_the_eight_marginal_notes(
    edition: bible.pipeline.Edition,
    read: bible.pipeline.Read,
    ctx: bible.annotate.Context,
    key: str,
    anchor: str,
    former: str,
    cited: str,
) -> None:
    code, reference, _ = key.split(" ", 2)
    source_note = next(n for n in read.marginal[code] if n["key"] == key)
    row = next(r for r in edition.notes[code] if r["key"] == key)
    assert row["lemma"] == anchor
    # Retained citations stand after the words the margin gives.
    assert row["note"] == f"or, _{former}_{cited}"
    assert row["style"] == "editorial reversal"
    assert row["source"] == source_note["note"]
    verse = scripture.verses(edition.documents[code])[reference]
    printed_note = next(n for _, n in verse.notes if n.get("x-key") == key)
    assert [
        usj.text_of(n["content"])
        for n in usj.walk(printed_note["content"])
        if usj.is_type(n, "char", "fqa")
    ] == [former]
    prepared = book(
        code,
        r"\v " + reference.split(":")[1] + " " + verse.text,
        chapter=int(reference.split(":")[0]),
    )
    comparison, report = annotate.george(
        code, prepared, [source_note], ctx, original=read.kjv[code]
    )
    assert scripture.verses(comparison)[reference].text == verse.text
    finished = annotate.finished_rows(comparison, report.rows)
    assert finished[0]["lemma"] == anchor
    assert finished[0]["note"] == row["note"]


@pytest.mark.parametrize(
    "prepared, original, override, error",
    [
        (
            "going out",
            "gone out",
            {"former": "went out"},
            "former not found exactly once",
        ),
        ("going out", "gone out gone out", {}, "former not found exactly once"),
        ("going out", "gone out", {"former": ""}, "former not found exactly once"),
        (
            "going out",
            "gone out",
            {"anchor": "missing"},
            "anchor not found exactly once",
        ),
        ("going out going out", "gone out", {}, "anchor not found exactly once"),
        ("gone out", "gone out", {"anchor": "gone out"}, "former changes nothing"),
        ("going out", "gone out", {"omitted": True}, "omitted with other exceptions"),
        ("going out going out", "gone out", {"occurrence": 1}, "former conflicts"),
        ("going out", "gone out", {"lemma": "going"}, "former conflicts"),
        (
            "going out",
            "gone out",
            {"note": "Or, _gone out_."},
            "former is not an alternative",
        ),
        # The text prints other words than the margin's alternative.
        (
            "falling out",
            "gone out",
            {"anchor": "falling out"},
            "does not print the margin's alternative",
        ),
    ],
)
def test_former_reading_decisions_refuse_stale_or_conflicting_words(
    ctx: bible.annotate.Context,
    prepared: str,
    original: str,
    override: dict[str, Any],
    error: str,
) -> None:
    key = "MAT 99:2 gone out"
    with pytest.raises(CheckFailed, match=error):
        policy = changed(
            ctx.policy,
            "kjv_notes",
            lambda d: d["notes"].update(
                {
                    key: {
                        "anchor": "going out",
                        "former": "gone out",
                        "why": "Test reversal.",
                        **override,
                    }
                }
            ),
        )
        annotate.george(
            "MAT",
            book("MAT", r"\v 2 " + prepared),
            [dict(key=key, reference="99:2", lemma="gone out", note="Or, going out.")],
            replace(ctx, policy=policy),
            original=book("MAT", r"\v 2 " + original),
        )


def test_reversing_a_marginal_note_leaves_its_inputs_unchanged(
    ctx: bible.annotate.Context,
) -> None:
    key = "MAT 99:2 gone out"
    policy = changed(
        ctx.policy,
        "kjv_notes",
        lambda d: d["notes"].update(
            {
                key: {
                    "anchor": "going out",
                    "former": "gone out",
                    "why": "Test reversal.",
                }
            }
        ),
    )
    prepared = book("MAT", r"\v 2 Our lamps are going out.")
    original = book("MAT", r"\v 2 Our lamps are gone out.")
    listed = [dict(key=key, reference="99:2", lemma="gone out", note="Or, going out.")]
    before = deepcopy((prepared, original, listed))
    before_policy = bible.policy.thaw(policy.kjv_notes)
    result, report = annotate.george(
        "MAT", prepared, listed, replace(ctx, policy=policy), original=original
    )
    assert (prepared, original, listed) == before
    assert bible.policy.thaw(policy.kjv_notes) == before_policy
    assert (
        scripture.verses(result)["99:2"].text == scripture.verses(prepared)["99:2"].text
    )
    assert annotate.finished_rows(result, report.rows)[0]["note"] == "or, _gone out_"


def test_mark_fist_correction_preserves_the_marginal_note(
    edition: bible.pipeline.Edition, read: bible.pipeline.Read
) -> None:
    key = "MRK 7:3 oft"
    row = next(r for r in edition.notes["MRK"] if r["key"] == key)
    original = next(n for n in read.marginal["MRK"] if n["key"] == key)
    assert row["lemma"] == "with the fist"
    assert row["source"] == original["note"]
    assert row["style"] == "editorial reversal"
    verse = scripture.verses(edition.documents["MRK"])["7:3"]
    note = next(n for _, n in verse.notes if n.get("x-key") == key)
    alternatives = [
        usj.text_of(n["content"])
        for n in usj.walk(note["content"])
        if usj.is_type(n, "char", "fqa")
    ]
    # The former King James words are given first, then the margin's own.
    assert alternatives == ["oft", "diligently", "up to the elbow"]
    assert note["x-key"] == original["key"]
    offset = next(offset for offset, n in verse.notes if n is note)
    assert verse.text[offset:].startswith("with the fist")
    assert usj.text_of(note["content"]).endswith(
        "with the fist: or, oft, or, diligently; Theophylact, up to the elbow"
    )


@pytest.mark.parametrize(
    "key,expected",
    [
        ("ISA 54:4", "Gr. _ancient_, or, _everlasting_"),
        ("ZEC 10:3", "or, _will oversee_, or, _will look upon_"),
        ("ZEC 10:3#2", "or, _shall oversee_, or, _shall look upon_"),
        ("NUM 8:4", "or, _appointment_, or _arrangement_"),
        ("1CO 10:11 ensamples", "or, _types_"),
        ("1CO 14:9 easy", "Gr. _significant_"),
        ("PSA 79:11", "Gr. _cedars of God_, see Gen. 30:8; Jonas 3:3; Acts 7:20"),
        (
            "JDG 13:19",
            "according to the Heb. _a wonderful work_. The LXX seem to have confounded "
            "פלא with פלח or פלה and thus rendered it διεχώρισε ποιῆσαι, but Alex. reads "
            "τῷ θαυμαστὰ ποιοῦντι κυρίῳ.",
        ),
        ("GEN 1:11#2", "Alex. adds εἰς ὁμοιότητα"),
        ("GEN 8:7#2", "Valpy omits"),
        ("GEN 6:7", "Valpy _I am grieved_. Gr. _I have thought_ or _reasoned_"),
        (
            "LUK 17:35 TR",
            "Beza adds verse 36 _Two men shall be in the field; the one shall be taken, and the other left._",
        ),
        (
            "JOB 25:2",
            "Compare chapter 27:1. προοίμιον, _exordium_, is in Job used in the sense of παροιμία, _parable_.",
        ),
    ],
)
def test_margin_fragments_keep_glosses_witnesses_and_sentence_punctuation(
    edition: bible.pipeline.Edition, key: str, expected: str
) -> None:
    row = next(r for rows in edition.notes.values() for r in rows if r["key"] == key)
    assert row["note"] == expected


@pytest.mark.parametrize(
    "key,lemma,alternative",
    [
        (
            "GAL 4:20 stand in doubt of you",
            "I stand in doubt of you",
            "I am perplexed for you",
        ),
        (
            "GAL 4:24 answereth...which now is",
            "answereth to",
            "is in the same rank with",
        ),
        ("HEB 11:22 made mention", "made mention of", "remembered"),
        ("LUK 2:21#1 TR", "circumcising him", "the circumcising of the child"),
        ("REV 21:16#1 TR", "equal, each twelve thousand furlongs", "equal"),
        ("LUK 20:31#1 TR", "likewise", "omits"),
    ],
)
def test_repaired_footnotes_replace_their_whole_construction(
    edition: bible.pipeline.Edition, key: str, lemma: str, alternative: str
) -> None:
    row = next(r for rows in edition.notes.values() for r in rows if r["key"] == key)
    assert row["lemma"] == lemma
    assert alternative in row["note"]


def test_unrelated_and_stale_source_notes_are_omitted(
    edition: bible.pipeline.Edition,
) -> None:
    keys = {r["key"] for rows in edition.notes.values() for r in rows}
    assert not keys & {
        "LUK 10:22 All these",
        "LUK 2:21#1 TR#2",
    }
    # Notes eBible garbled, restored as Brenton printed them.
    assert keys >= {"EXO 32:14", "2SA 22:27", "1KI 11:27"}
    # eBible swapped the texts of Judges 20's two notes; corrected, each stays
    # at its own verse, as Brenton printed them.
    judges = {r["key"]: r for r in edition.notes["JDG"]}
    assert judges["JDG 20:10"]["reference"] == "20:10"
    assert judges["JDG 20:10"]["note"] == "Gr. _it_, sc. _Gabaa_"
    assert judges["JDG 20:13"]["reference"] == "20:13"
    assert judges["JDG 20:13"]["note"] == "Heb. _sons of Belial_"
    places = [
        r["note"] for r in edition.notes["DEU"] if r["key"].startswith("DEU 9:22")
    ]
    assert places == ["Heb. _Taberah_", "Heb. _Massah_", "Heb. _Kibroth Hattaavah_"]


@pytest.mark.parametrize(
    "key,lemma,expected",
    [
        ("JOS 21:13", "Hebron, and the suburbs", "q.d. Anglicè _glebe_."),
        ("ISA 14:2#2", "they shall be multiplied", "i.e., _the Gentiles_"),
        (
            "1KI 11:33#2",
            "the abomination of the children of Ammon",
            "or, _provocation_",
        ),
        ("1KI 7:43", "porch of the pillars", "or, _portico_"),
        ("2KI 19:23#2", "height of his cedar", "Gr. _bulk_ or _size_"),
        ("GEN 4:14", "and I shall be hidden", "or, _then shall I be_"),
        ("1SA 14:40", "will be under subjection", "Gr. _become slaves_"),
        ("1SA 23:11", "shut up", "i.e., _besieged_"),
        ("JOS 21:4", "out of the tribe of Judah", "Gr. _from_"),
        ("1SA 26:24#2", "be precious", "Gr. _magnified_"),
    ],
)
def test_identifying_lemmas_do_not_add_words_to_explanations(
    edition: bible.pipeline.Edition, key: str, lemma: str, expected: str
) -> None:
    # A lemma may be widened to identify its place, but the explanation
    # prints Brenton's own words, neither echoed with the lemma's context nor
    # completed into a substitution.
    row = next(r for rows in edition.notes.values() for r in rows if r["key"] == key)
    assert row["lemma"] == lemma
    assert expected in row["note"]


@pytest.mark.parametrize(
    "key",
    [
        "1KI 22:41",
        "2KI 15:13",
        "JOL 2:3",
        "JOL 2:3#2",
        "GEN 21:22",
        "GEN 37:2",
        "NUM 1:18",
        "1SA 16:4",
        "1KI 10:22a",
        "ISA 52:7",
        "LUK 15:8 pieces of silver",
        "LUK 16:7 measures",
        "LUK 19:13 pounds",
        "ACT 13:18 suffered",
    ],
)
def test_historical_glosses_are_explanations(
    edition: bible.pipeline.Edition,
    key: str,
) -> None:
    row = next(r for rows in edition.notes.values() for r in rows if r["key"] == key)
    assert row["reading"] is None
    assert row["note"]


@pytest.mark.parametrize("mutation", ["alternative", "ambiguous", "boundary"])
def test_finished_checks_refuse_damaged_notes(
    edition: bible.pipeline.Edition,
    mutation: str,
) -> None:
    original = edition.documents["ROM"]
    document = deepcopy(original)
    rows = edition.notes["ROM"]
    note = next(
        n
        for n in usj.notes_of(document["content"])
        if n.get("x-key") == "ROM 12:2#1 TR"
    )
    # The punctuation edit in 12:1 shares the unit's key with its next note.
    if mutation == "alternative":
        field = next(n for n in note["content"] if usj.is_type(n, "char", "fqa"))
        field["content"] = ["damaged alternative"]
        with pytest.raises(CheckFailed, match="changed a note's construction"):
            revision.check_revised_notes("ROM", original, document)
    elif mutation == "ambiguous":
        field = next(n for n in note["content"] if usj.is_type(n, "char", "fq"))
        field["content"] = ["God: "]
        with pytest.raises(CheckFailed, match="not unique"):
            annotate.finished_rows(document, rows)
    else:
        verse = scripture.verses(document)["12:1"]
        document = scripture.edited(
            document,
            [(verse, len(verse.text.rstrip()) - 1, len(verse.text.rstrip()), [])],
        )
        with pytest.raises(CheckFailed, match="boundary stop"):
            annotate.finished_rows(document, rows)


@pytest.mark.parametrize(
    "key,boundary,stop",
    [
        ("ROM 12:2#1 TR", ":", "."),
        ("COL 1:24#1 TR", ".", ";"),
        ("ACT 24:6#1 TR", ":", "."),
        ("2CO 1:6#1 TR", ";", "."),
        ("1JN 5:7#1 TR", ",", "."),
    ],
)
def test_finished_readings_preserve_boundary_punctuation(
    edition: bible.pipeline.Edition,
    key: str,
    boundary: str,
    stop: str,
) -> None:
    code = key.split()[0]
    note = next(
        n
        for n in usj.notes_of(edition.documents[code]["content"])
        if n.get("x-key") == key
    )
    fields = {
        n["marker"]: usj.text_of(n["content"])
        for n in note["content"]
        if isinstance(n, dict)
    }
    declared = note["x-scope"]["declared"]
    assert declared is not None and declared.endswith(boundary)
    assert fields["fqa"].endswith(stop)
    assert not fields["fq"].endswith(boundary + ": ")


@pytest.mark.parametrize(
    "key,lemma,alternative,former",
    [
        ("2CO 12:2 rendering#2", "Christ", "Christ above", "in Christ above fourteen"),
        ("ZEC 3:4", "long", "full length", "with a full length robe"),
        (
            "JHN 17:11#2 TR",
            "them through thine own name which",
            "through thine own name those whom",
            "keep through thine own name those whom thou hast given me",
        ),
        (
            "REV 4:4#1 TR",
            "upon the seats",
            "upon the seats I saw",
            "upon the seats I saw four and twenty elders",
        ),
        ("GEN 11:25", "twenty-nine", "twenty-five", "a hundred and twenty-five years"),
        (
            "2TI 2:6 The husbandman that laboureth, must be first partaker of the fruits",
            "that laboureth must be first",
            "labouring first must be",
            "The husbandman labouring first must be partaker of the fruits",
        ),
        (
            "HEB 6:17 confirmed it by an oath",
            "confirmed it",
            "interposed himself",
            "interposed himself by an oath",
        ),
        ("1PE 2:9 peculiar people", "peculiar", "purchased", "a purchased people"),
        (
            "MAT 17:27 a piece of money",
            "a piece of money",
            "a stater",
            "thou shalt find a stater: that take",
        ),
        (
            "LUK 1:45 that believed, for there",
            "that believed, for there",
            "which believed that there",
            "she which believed that there shall be a performance",
        ),
        (
            "LUK 4:41 to speak, for they knew that he was Christ",
            "to speak: for they knew that he was Christ",
            "to say that they knew him to be Christ",
            "suffered them not to say that they knew him to be Christ.",
        ),
        (
            "2CO 4:8 in despair",
            "in despair",
            "altogether without help, or means",
            "we are perplexed, but not altogether without help, or means;",
        ),
        (
            "TIT 2:9 answering again",
            "answering again",
            "gainsaying",
            "not gainsaying;",
        ),
        (
            "2PE 2:11 against them",
            "against them",
            "against themselves",
            "bring not railing accusation against themselves before the Lord.",
        ),
        (
            "REV 14:13 from henceforth, yea, saith the Spirit",
            "from henceforth: Yea, saith the Spirit",
            "from henceforth saith the Spirit, Yea",
            "die in the Lord from henceforth saith the Spirit, Yea, that they may rest",
        ),
    ],
)
def test_final_replacement_scopes_restore_the_former_construction(
    edition: bible.pipeline.Edition,
    key: str,
    lemma: str,
    alternative: str,
    former: str,
) -> None:
    code = key.split()[0]
    row = next(r for r in edition.notes[code] if r["key"] == key)
    verse = scripture.verses(edition.documents[code])[row["reference"]]
    offset, note = next((at, n) for at, n in verse.notes if n.get("x-key") == key)
    words = scripture.word_spans(verse.text)
    fields = {
        n["marker"]: usj.text_of(n["content"]).rstrip()
        for n in note["content"]
        if isinstance(n, dict)
    }
    assert fields["fq"] == lemma + ":"
    assert fields["fqa"] == alternative

    def restored(note: Node) -> str:
        # The alternative in place of the words the note's scope takes in,
        # with enough unchanged context to show a repeated or missing word
        # or a stop left outside a replacement's scope.
        start, end = annotate.scope_span(verse.text, words, offset, note)
        return verse.text[:start] + alternative + verse.text[end:]

    assert former in restored(note)
    if key == "2CO 12:2 rendering#2":
        assert note["x-scope"]["declared"] == "Christ,"
        damaged: Node = {**note, "x-scope": {"declared": "Christ"}}
        assert former not in restored(damaged)
    if key == "JHN 17:11#2 TR":
        assert not any(n.get("x-key") == key + "#2" for _, n in verse.notes)


def test_the_1611_margins_alternatives_keep_their_label(
    edition: bible.pipeline.Edition,
) -> None:
    expected = {
        "ACT 5:3 to lie": ("to lie to", "or, _to deceive_"),
        "ROM 9:20 repliest against God?": (
            "repliest against God",
            "or, _answerest again_, or _disputest with God_?",
        ),
        "HEB 7:19 but the bringing in": (
            "but the bringing in",
            "or, _but it was the bringing in_",
        ),
        "HEB 7:24 unchangeable": (
            "unchangeable",
            "or, _which passeth not from one to another_",
        ),
        "JAS 5:9 Grudge not": ("Grudge not", "or, _groan_, or _grieve not_"),
    }
    for key, (lemma, text) in expected.items():
        row = next(
            r for rows in edition.notes.values() for r in rows if r["key"] == key
        )
        assert (row["lemma"], row["note"]) == (lemma, text)


def test_corrected_transcriptions_print_without_their_slips(
    edition: bible.pipeline.Edition,
) -> None:
    for key in ["1SA 29:3#2", "1SA 29:4", "1SA 29:5", "1SA 29:8"]:
        row = next(r for r in edition.notes["1SA"] if r["key"] == key)
        assert "_to_ or" not in row["note"]
    # The corrected reference agrees with the quotation link and is merged.
    assert not any(r["key"] == "ISA 29:13" for r in edition.notes["ISA"])
    verse = scripture.verses(edition.documents["ISA"])["29:13"]
    assert any("Matt. 15:8–9" in usj.text_of(n["content"]) for _, n in verse.notes)
    # A reference eBible sets at the end of the verse before Brenton's caller is
    # moved to the caller's verse, where its link replaces it.
    assert not any(r["key"] == "PSA 9:27" for r in edition.notes["PSA"])
    verses = scripture.verses(edition.documents["PSA"])
    romans = [
        usj.text_of(n["content"])
        for reference in ("9:27", "9:28")
        for _, n in verses[reference].notes
        if "Rom. 3:14" in usj.text_of(n["content"])
    ]
    assert len(romans) == 1 and romans[0].startswith("9:28 ")


def test_the_household_reference_stands_at_proverbs_11_29(
    edition: bible.pipeline.Edition,
) -> None:
    verses = scripture.verses(edition.documents["PRO"])
    placed = [
        (reference, offset, note)
        for reference, verse in verses.items()
        for offset, note in verse.notes
        if note.get("x-key") == "PRO 11:28"
    ]
    assert len(placed) == 1
    reference, offset, note = placed[0]
    assert (reference, offset) == ("11:29", 0)
    assert notes.lemma_of(note) == "He that dealeth not graciously with his own house"
    assert "1TI 5:8" in usj.serialize([note])
    assert scripture.plain(verses["11:28"].text) == (
        "He that trusteth in wealth shall fall; "
        "but he that helpeth righteous men shall rise."
    )
    assert scripture.plain(verses["11:29"].text) == (
        "He that dealeth not graciously with his own house shall inherit the wind; "
        "and the fool shall be servant to the wise man."
    )


def test_the_parent_cursing_link_replaces_brentons_kidnapping_reference(
    edition: bible.pipeline.Edition,
) -> None:
    assert not any(r["key"] == "EXO 21:17" for r in edition.notes["EXO"])
    verses = scripture.verses(edition.documents["EXO"])
    assert not verses["21:17"].notes
    [link] = [note for _, note in verses["21:16"].notes]
    assert link["marker"] == "x"
    text = usj.serialize([link])
    assert text.count("|MAT 15:4") == 1
    assert text.count("|MRK 7:10") == 1
    assert "(Heb.\u00a0+ LXX)" in text
    assert scripture.plain(verses["21:16"].text) == (
        "He that revileth his father or his mother shall surely die."
    )
    assert scripture.plain(verses["21:17"].text) == (
        "Whosoever shall steal one of the children of Israel, and prevail over him "
        "and sell him, and he be found with him, let him certainly die."
    )


def test_notes_stay_in_the_margin_whatever_their_length_or_form(
    edition: bible.pipeline.Edition,
) -> None:
    def note(key: str) -> Node:
        return next(
            n
            for n in usj.notes_of(edition.documents[key.split(" ")[0]]["content"])
            if n.get("x-key") == key
        )

    # A sentence of Brenton's, and a gloss.
    for key in ["GEN 15:11", "GEN 1:9"]:
        assert (note(key)["marker"], note(key)["caller"]) == ("f", "-")
    assert any(
        n["marker"] == "f" and len(usj.text_of(n["content"])) > 200
        for n in usj.notes_of(edition.documents["REV"]["content"])
    )
    # A decision sets a note below the text at export, for the page whose
    # margin it relieves: in the prepared books, the only keyed notes below
    # the text are Brenton's Appendix's.
    assert note("REV 6:6 A measure")["marker"] == "f"
    assert all(
        n["x-key"].endswith(" Appendix")
        for code in edition.scripture
        for n in usj.notes_of(edition.documents[code]["content"])
        if n["caller"] == "+" and "x-key" in n
    )
    placed = bible.export.notes_below(edition)
    assert set[str]().union(*placed.values()) == set(edition.policy.margin["below"])
    assert "REV 6:6 A measure" in placed["REV"]


@pytest.mark.parametrize(
    "body, sentence, expected",
    [
        ("This is light.", False, r"\f - \fr 99:1 \fq light: \ft this is light\f*"),
        ("Or, light.", True, r"\f - \fr 99:1 \fq light: \ft or, \fqa light\ft .\f*"),
    ],
)
def test_a_sentence_override_sets_the_capital_and_full_stop(
    ctx: bible.annotate.Context, body: str, sentence: bool, expected: str
) -> None:
    def overridden(sentence: bool) -> bible.annotate.Context:
        policy = changed(
            ctx.policy,
            "brenton_notes",
            lambda data: data["notes"].update(
                {
                    "GEN 99:1": {
                        "sentence": sentence,
                        "why": "test the declared classification",
                    }
                }
            ),
        )
        return replace(ctx, policy=policy)

    verse = r"\v 1 Let there be \f + \fr 99:1 \ft " + body + r"\f*light."
    # The note stays in the margin either way.
    assert expected in printed(verse, overridden(sentence))["1"]
    with pytest.raises(CheckFailed, match="sentence override changes nothing"):
        printed(verse, overridden(not sentence))


def test_a_note_placement_needs_its_reason(declared: bible.policy.Policy) -> None:
    with pytest.raises(CheckFailed, match="Note placement without a why: REV 1:1"):
        changed(declared, "margin", lambda data: data["below"].update({"REV 1:1": ""}))


def test_a_note_set_below_keeps_its_words_and_stale_placements_stop_the_build() -> None:
    key = "REV 13:1#1 TR"
    note = notes.footnote(
        "13:1",
        "ten horns and seven heads",
        [("commentary", "TR "), ("reading", "seven heads and ten horns")],
        **usj.Extra(
            {
                "x-key": key,
                "category": "edition",
                "x-scope": {"declared": "ten horns and seven heads"},
            }
        ),
    )
    doc = usj.document([usj.para("p", "before", note, "after")])
    before = deepcopy(doc)
    placed = notes.set_below(doc, [key])
    assert doc == before
    assert usj.notes_of(placed["content"]) == [{**note, "caller": "+"}]
    assert usj.text_of(placed["content"]) == usj.text_of(doc["content"])
    assert notes.set_below(doc, []) == doc
    with pytest.raises(CheckFailed, match="changes nothing.*REV 13:1#1 TR"):
        notes.set_below(placed, [key])
    with pytest.raises(CheckFailed, match="Unused note placements.*REV 13:1#2 TR"):
        notes.set_below(doc, ["REV 13:1#2 TR"])
    with pytest.raises(CheckFailed, match="Duplicate note placement.*REV 13:1#1 TR"):
        notes.set_below(usj.document([usj.para("p", note, note)]), [key])


def test_a_long_note_of_the_front_matter_is_set_below_the_text() -> None:
    def footnote(words: str) -> Node:
        return usj.note("f", usj.char("ft", words), caller="+")

    limit = bible.export.LONG_NOTE
    short, long = footnote("x" * (limit - 1)), footnote("x" * limit)
    doc = usj.document([usj.para("ip", "One", short, " two", long, ".")])
    before = deepcopy(doc)
    marked = bible.export.long_notes_below(doc)
    assert doc == before
    # Only the milestone before the long note is added, which PTXprint reads
    # to set the numbered note below the text rather than in the margin.
    assert marked["content"][0]["content"] == [
        "One",
        short,
        " two",
        bible.export.BELOW,
        long,
        ".",
    ]
    assert usj.serialize([bible.export.BELOW, long]).startswith("\\zbelow\\*\\f + ")


@pytest.mark.parametrize(
    "reference, index, restored",
    [
        (
            "14:4",
            3,
            "But Ahijah could not see; for his eyes were set by reason of his age",
        ),
        (
            "14:5",
            4,
            "thus and thus shalt thou say to her: for it shall be, when she cometh in, that she shall feign herself to be another woman",
        ),
        (
            "14:10",
            12,
            "and will take away the remnant of the house of Jeroboam, as a man taketh away dung, till it be all gone",
        ),
        ("14:11", 13, "Him that dieth of Jeroboam in the city shall the dogs eat"),
        ("14:12", 15, "when thy feet enter into the city, the child shall die"),
        ("14:15", 19, "as a reed is shaken in the water"),
        ("14:15", 20, "and he shall root up Israel"),
        ("14:16", 22, "And he shall give Israel up because of the sins of Jeroboam"),
        ("14:17", 23, "And Jeroboam’s wife arose, and departed, and came to Tirzah"),
        ("14:17", 24, "and when she came to the threshold of the door, the child died"),
    ],
)
def test_supplied_kingdoms_notes_restore_their_quoted_constructions(
    edition: bible.pipeline.Edition, reference: str, index: int, restored: str
) -> None:
    verse = scripture.verses(edition.documents["1KI"])[reference]
    key = f"1KI 14:1-20@{index}"
    note = next(note for _, note in verse.notes if note.get("x-key") == key)
    lemma = next(
        usj.text_of(node["content"]).removesuffix(": ")
        for node in usj.walk(note["content"])
        if node.get("marker") == "fq"
    )
    alternate = next(
        usj.text_of(node["content"])
        for node in usj.walk(note["content"])
        if node.get("marker") in {"fqa", "it"}
    ).strip()
    assert verse.text.count(lemma) == 1
    assert restored in verse.text.replace(lemma, alternate)
