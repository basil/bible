"""Notes: what each says, the words it is about, and how it prints."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from typing import Any

import pytest
from conftest import book, changed, verse_lines

import bible.annotate
import bible.pipeline
import bible.policy
from bible import annotate, crossrefs, lemmas, notes, scripture, terminology, usj
from bible.checks import CheckFailed
from bible.usj import Content


def test_prose_quotations_span_styles_and_preserve_apostrophes() -> None:
    content: Content = [
        "He quotes “The ",
        usj.char("it", "fathers’"),
        " words: ‘we are his offspring.’” ",
        usj.char("it", "This"),
        " is commentary. See ",
        usj.char("xt", "Acts 17:28"),
        ".",
    ]
    source = deepcopy(content)
    printed = notes.prose(content)
    assert content == source
    assert usj.text_of(printed) == (
        "He quotes The fathers’ words: we are his offspring. "
        "This is commentary. See Acts 17:28."
    )
    italic = [
        usj.text_of(n["content"])
        for n in usj.walk(printed)
        if usj.is_type(n, "char", "it")
    ]
    assert italic == ["The fathers’ words: we are his offspring"]
    assert usj.char("xt", "Acts 17:28") in printed


@pytest.mark.parametrize(
    "key",
    [
        "GEN 15:11",
        "GEN 39:1",
        "JOS 19:51",
        "JDG 2:18",
        "1SA 15:11",
        "2KI 12:14",
        "ISA 2:6",
        "1KI 10:22a",
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
        "ISA 2:6",
        "MAT 17:27 a piece of money",
        "ACT 17:19 Areopagus",
    ):
        assert row["note"].startswith("or,")


def test_editorial_note_styles_and_punctuation(
    edition: bible.pipeline.Edition,
) -> None:
    rows = {r["key"]: r for notes in edition.notes.values() for r in notes}
    assert "_from any cause_" in rows["GEN 30:41"]["note"]
    assert "_then_" in rows["GEN 30:41"]["note"]
    assert rows["1SA 14:29"]["note"].startswith("_E medio sustulit_.")
    assert rows["1SA 14:29"]["lemma"] == "destroyed the land"
    assert rows["PSA 113:24"]["note"] == "Gr. sing."
    assert "_suburbs_ above" in rows["JOS 21:13"]["note"]
    assert "_Lo! a blessing from you_ etc." in rows["1SA 30:26"]["note"]
    assert rows["JHN 18:13 year"]["note"].startswith("_And Annas sent Christ")


@pytest.mark.parametrize(
    "quotation, expected",
    [(True, "_And Annas sent Christ_"), (False, "_and Annas sent Christ_")],
)
def test_declared_quotations_preserve_capitals_but_alternatives_run_on(
    policy: bible.policy.Policy, quotation: bool, expected: str
) -> None:
    source = "And Annas sent Christ"
    body = notes.source_body(
        [("text", source)],
        [],
        "_" + source + "_",
        "key",
        source,
        quotation=quotation,
    )
    assert body.alternative == (None if quotation else source)
    runs, terms, _ = notes.displayed(body)
    result = notes.finished(
        runs, terms, "year", None, terminology.registry(policy), "key"
    )
    assert notes.underscored(result) == expected
    echoed = notes.displayed(body, "before ", " after")[0]
    assert notes.text_of(echoed) == (
        source if quotation else "before " + source + " after"
    )


def test_a_quotation_decision_must_declare_quoted_words() -> None:
    with pytest.raises(CheckFailed, match="declares no quoted words: key"):
        notes.source_body(
            [("text", "And Annas sent Christ")],
            [],
            "And Annas sent Christ",
            "key",
            "And Annas sent Christ",
            quotation=True,
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
            r"\f - \fr 99:5 \ft See \xt Rom. 4:7, 8\f*Blessed are they whose sins are forgiven.",
        ),
        # A caller at the end of a verse glosses the words before it.
        (
            r"\v 7 and he called his name Light.\f + \fr 99:7 \fqa Heb. \ft Brightness.\f*",
            r"and he called his name Light.\f - \fr 99:7 \fq Light: \ft Heb. \fqa Brightness\f*",
        ),
        # Abbreviations print in the edition's forms.
        (
            r"\v 8 the captain of the \f + \fr 99:8 \fqa A. V. \ft guard, i. e. the Sept. reading.\f*cooks stood there.",
            r"the captain of the \f - \fr 99:8 \fq cooks: \ft Authorized Version \fqa guard\ft , i.e., the LXX reading\f*cooks stood there.",
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
        {"note": "Gr. _meeting_ together.", "why": "together is the editor's"}
    )
    assert r"\f - \fr 99:9 \ft Gr. \fqa meeting together\f*" in with_exception(
        {"lemma": None, "why": "the note is on the verse"}
    )
    # An exception that changes nothing, or isn't the note's words, is refused.
    with pytest.raises(CheckFailed, match="Lemma override changes nothing"):
        with_exception({"lemma": "place of rest", "why": "the same"})
    with pytest.raises(CheckFailed, match="Note override changes nothing"):
        with_exception({"note": "Gr. _meeting together_.", "why": "the same"})
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
    doc, report = annotate.george("MAT", doc, listed, ctx)
    assert verse_lines(doc)["2"] == (
        r"and paid an hundred \f - \fr 99:2 \fq pence: \ft The Roman penny is the eighth "
        r"part of an ounce.\f*pence to the \f - \fr 99:2 \fq keeper: \ft or, \fqa porter\f*"
        "keeper of the house."
    )
    assert [row["rule"] for row in report.rows] == ["anchor", "anchor"]


def test_a_note_of_the_margin_must_find_its_words_once(
    ctx: bible.annotate.Context,
) -> None:
    doc = book("MAT", r"\v 2 of the house of the keeper.")
    note = dict(key="MAT 99:2 of", reference="99:2", lemma="of", note="Or, from.")
    with pytest.raises(CheckFailed, match="not found exactly once"):
        annotate.george("MAT", doc, [note], ctx)
    with pytest.raises(CheckFailed, match="verse missing"):
        annotate.george("MAT", doc, [{**note, "reference": "99:3"}], ctx)


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
    with pytest.raises(CheckFailed, match="Ambiguous quotation marks"):
        notes.prose([words])


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
            notes.labelled_pieces(source), [], override, "key", source
        )
        runs, terms, _ = notes.displayed(notes.with_terms(body, registry))
        return notes.underscored(
            notes.finished(runs, terms, "lemma", None, registry, "key")
        )

    # Quoted words that an exception leaves roman stay roman.
    assert (
        printed_note(
            "Or, 'but he that is without fear (sc. of the Lord) shall dwell' etc.",
            "Or, '_but he that is without fear_ (sc. of the Lord) _shall dwell_' etc.",
        )
        == "or, _but he that is without fear_ (sc. of the Lord) _shall dwell_ etc."
    )
    # One that only repeats the italics of the rules, quoted words among
    # them, changes nothing.
    with pytest.raises(CheckFailed, match="Note override changes nothing: key"):
        printed_note(
            "Or, windows, see above, there rendered 'flood-gates.'",
            "Or, _windows_, see above, there rendered '_flood-gates_.'",
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
        ("so in the Sept. and A. V. also", "so in the LXX and Authorized Version also"),
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
    "words",
    [
        "Complut. + and they went.",
        "Complut. — and they went.",
        "Alex. +'and they went.'",
        "Gr. one + one.",
    ],
)
def test_a_sign_after_no_witness_is_refused(
    words: str, policy: bible.policy.Policy
) -> None:
    registry = terminology.registry(policy)
    with pytest.raises(CheckFailed, match="Sign after no witness"):
        terminology.recognize(words, registry)
    # Prose has no signs to read.
    assert terminology.recognize(words, registry, note=False)


def test_every_note_of_the_sources_is_printed_or_replaced_by_a_link(
    edition: bible.pipeline.Edition,
) -> None:
    assert edition.summary["printed_notes"] == 3417
    rows = [row for listed in edition.notes.values() for row in listed]
    assert len({row["key"] for row in rows}) == len(rows)
    # The 1611 margin is printed whole, on the New Testament alone.
    margin = sum(
        len(edition.notes[u["id"]])
        for u in edition.policy.scripture
        if u["source"] == "kjv"
    )
    assert margin == edition.summary["kjv_marginal_notes"] == 775
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
    decided = {"override", "Alexandrine reading", "preserved passage note"}
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
    alternative = notes.interpreted(notes.labelled_pieces(note), "K").alternative
    span, rule = lemmas.inferred_lemma(kind, verse, words, offset, alternative)
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
