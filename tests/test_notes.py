"""Notes: what each says, the words it is about, and how it prints."""

import pytest
from conftest import book, changed, verse_lines

from bible import annotate, lemmas, notes, scripture, terminology, usj
from bible.checks import CheckFailed


def printed(body, ctx, *, code="GEN", links=()):
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
            r"\f - \fr 99:5 \ft See \xt Romans 4:7, 8\f*Blessed are they whose sins are forgiven.",
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
def test_a_note_of_brentons_is_set_as_a_footnote_on_its_words(verse, expected, ctx):
    assert list(printed(verse, ctx).values()) == [expected]


def test_a_lemma_is_widened_until_it_occurs_once_and_its_rendering_with_it():
    verse = "that ye have no reward of your Father, and praise of men"
    words = scripture.word_spans(verse)
    of = [i for i, (word, _, _) in enumerate(words) if word == "of"]
    span, glossed, rule, first = lemmas.anchored(verse, words, ["of"], 1, {}, "key")
    assert (lemmas.lemma_text(verse, words, span), rule, first) == (
        "of your Father",
        "widened",
        of[0],
    )
    assert lemmas.echoes(verse, words, span, glossed) == ("", " your Father")


def test_the_exception_files_correct_the_rules(ctx, policy):
    verse = r"\v 9 Let the water be collected into one \f + \fr 99:9 \fqa Gr. \ft meeting together.\f*place of rest."

    def with_exception(entry):
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


def test_a_note_in_the_wrong_verse_is_set_on_its_words_in_the_right_one(ctx, policy):
    verses = (
        "\\v 7 And there shall be two parties among you.\n"
        r"\v 9 both those that went in, \f + \fr 99:9 \fqa Gr. \ft hands.\f*and those that went out."
    )

    def with_exception(entry):
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


def test_a_note_that_is_a_sentence_takes_a_capital_and_a_full_stop(ctx, policy):
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


def test_a_note_of_the_margin_must_find_its_words_once(ctx):
    doc = book("MAT", r"\v 2 of the house of the keeper.")
    note = dict(key="MAT 99:2 of", reference="99:2", lemma="of", note="Or, from.")
    with pytest.raises(CheckFailed, match="not found exactly once"):
        annotate.george("MAT", doc, [note], ctx)
    with pytest.raises(CheckFailed, match="verse missing"):
        annotate.george("MAT", doc, [{**note, "reference": "99:3"}], ctx)


def test_a_declared_change_of_wording_is_carried_through_a_notes_parts():
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


def test_the_notes_the_edition_writes_say_what_each_part_is():
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
    ],
)
def test_terms_print_in_the_editions_forms(words, expected, policy):
    registry = terminology.registry(policy)
    assert (
        usj.serialize(
            terminology.printed(
                [words], terminology.found([words], registry, note=True), registry
            )
        )
        == expected
    )


def test_every_note_of_the_sources_is_printed_or_replaced_by_a_link(edition):
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


def test_an_inferred_lemma_has_the_shape_of_its_rendering(edition, policy):
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


def inferred(verse, note, kind="f"):
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
def test_the_rules_find_the_words_a_note_is_about(verse, note, expected):
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
def test_a_cross_reference_shows_where_its_quotation_begins(verse, expected):
    assert inferred(verse, "See Rom. 1. 1.", kind="x") == expected
