"""The edition's notes: the 1611 marginal notes' parsing, corrections and
anchoring, Brenton's notes, the lemmas and italics of both, and the footnotes
they are set as."""

import re

import pytest

from bible import notes
from bible.checks import CheckFailed
from bible.edition import MANIFEST, scripture_unit as unit
from bible.prepare import front_matter_text, recorder, scripture_text
from bible.usfm import word_spans


def test_marginal_notes_parse():
    parsed = notes.marginal_notes()
    assert sum(len(n) for n in parsed.values()) == notes.EXPECTED_NT_MARGINAL_NOTES


def test_unused_correction(patched):
    patched(notes, "KJV_NOTES")["corrections"]["MAT 1:1 nothing"] = {
        "from": "a",
        "to": "b",
    }
    with pytest.raises(
        CheckFailed, match=r"Unused marginal note corrections: \['MAT 1:1 nothing'\]"
    ):
        notes.marginal_notes()


def test_correction_that_does_not_apply(patched):
    patched(notes, "KJV_NOTES")["corrections"]["MAT 23:18 guilty"][
        "from"
    ] = "no such text"
    with pytest.raises(
        CheckFailed, match="correction does not apply: MAT 23:18 guilty"
    ):
        notes.marginal_notes()


def test_transcribers_remark_left_in_note(patched):
    # This correction removes "[symbol in wrong place in 1611]".
    del patched(notes, "KJV_NOTES")["corrections"]["MAT 5:15 a bushel"]
    with pytest.raises(
        CheckFailed, match="Transcriber's remark left in marginal note: MAT 5:15"
    ):
        notes.marginal_notes()


def test_unused_exception(patched):
    patched(notes, "KJV_NOTES")["notes"]["MAT 1:1 nothing"] = {"anchor": "nothing"}
    with pytest.raises(CheckFailed, match="Unused marginal note exceptions"):
        notes.marginal_notes()


def test_missing_anchor_verse(archives, patched):
    exceptions = patched(notes, "KJV_NOTES")["notes"]
    exceptions["MAT 12:14 held a counsel"]["verse"] = "12:99"
    with pytest.raises(CheckFailed, match="verse missing: MAT 12:14 held a counsel"):
        scripture_text(unit("MAT"), archives)


def test_wrong_anchor(archives, patched):
    # George's lemma reads "counsel" where the Cambridge text has "council".
    del patched(notes, "KJV_NOTES")["notes"]["MAT 12:14 held a counsel"]
    with pytest.raises(
        CheckFailed, match=r"not found exactly once: MAT 12:14 held a counsel \(0\)"
    ):
        scripture_text(unit("MAT"), archives)


def test_ambiguous_anchor(archives, patched):
    # "of" occurs more than once in Matthew 6:1; the override picks the second.
    del patched(notes, "KJV_NOTES")["notes"]["MAT 6:1 of"]
    with pytest.raises(
        CheckFailed, match=r"not found exactly once: MAT 6:1 of \([2-9]\)"
    ):
        scripture_text(unit("MAT"), archives)


def test_anchor_inside_added_words(archives, patched):
    # "it" is the second of Mark 3:21's added words "of it".
    patched(notes, "KJV_NOTES")["notes"]["MRK 3:21 friends"] = {
        "anchor": "it",
        "why": "x",
        "uncategorized": True,
    }
    with pytest.raises(
        CheckFailed, match="Note inside a character span: MRK 3:21 friends"
    ):
        scripture_text(unit("MRK"), archives)


def test_cambridge_text_must_not_already_have_notes(with_source):
    damaged = with_source(
        "kjv",
        "MAT",
        lambda t: t.replace("\\v 2 ", "\\v 2 \\f + \\ft x\\f* ", 1),
    )
    with pytest.raises(CheckFailed, match="already has footnotes: MAT"):
        scripture_text(unit("MAT"), damaged)


def unit_front(code):
    return next(e for e in MANIFEST["old_testament_front"] if e["id"] == code)


def footnotes(text, reference):
    """The footnotes set for a verse in prepared USFM, in order."""
    return re.findall(r"\\f - \\fr " + re.escape(reference) + r" .*?\\f\*", text)


@pytest.mark.parametrize(
    "code, reference, usfm",
    [
        (
            "ACT",
            "25:20",
            "\\f - \\fr 25:20 \\fq I doubted of such manner of questions: "
            "\\ft or, \\fqa I was doubtful how to enquire hereof\\f*",
        ),
        (
            "1CO",
            "15:31",
            "\\f - \\fr 15:31 \\fq your: \\ft some read, \\fqa our\\f*",
        ),
        (
            "1CO",
            "16:3",
            "\\f - \\fr 16:3 \\fq liberality: \\ft Gr. \\fqa gift\\f*",
        ),
        # George's lone preposition stands where it occurs once...
        ("MRK", "1:4", "\\f - \\fr 1:4 \\fq for: \\ft or, \\fqa unto\\f*"),
        # ...and is widened where it doesn't, and its rendering with it.
        (
            "MAT",
            "6:1",
            "\\f - \\fr 6:1 \\fq of your Father: \\ft or, \\fqa with your Father\\f*",
        ),
        (
            "MRK",
            "2:21",
            "\\f - \\fr 2:21 \\fq new cloth: \\ft or, \\fqa raw cloth\\ft , or "
            "\\fqa unwrought cloth\\f*",
        ),
    ],
)
def test_marginal_footnotes(scripture, code, reference, usfm):
    assert footnotes(scripture[code], reference) == [usfm]


def test_each_note_is_its_own_footnote(scripture):
    assert footnotes(scripture["ROM"], "9:12") == [
        "\\f - \\fr 9:12 \\fq elder: \\ft or, \\fqa greater\\f*",
        "\\f - \\fr 9:12 \\fq younger: \\ft or, \\fqa lesser\\f*",
    ]


def test_marginal_note_on_the_whole_verse(archives, patched):
    patched(notes, "KJV_NOTES")["notes"][
        "LUK 17:36 Two men shall be in the field, the one shall be taken, and the other left"
    ] = {
        "lemma": None,
        "why": "x",
    }
    assert footnotes(scripture_text(unit("LUK"), archives), "17:36") == [
        "\\f - \\fr 17:36 \\ft This 36. verse is wanting in most of the Greek copies.\\f*"
    ]


def test_footnote_follows_a_lemma_clear_of_its_anchor(scripture):
    # George swaps Mark 7:4's notes; their lemmas say where each belongs.
    assert footnotes(scripture["MRK"], "7:4") == [
        "\\f - \\fr 7:4 \\fq pots: \\ft Sextarius, is about a pint and an half.\\f*",
        "\\f - \\fr 7:4 \\fq tables: \\ft or, \\fqa beds\\f*",
    ]
    assert "\\fqa beds\\f*tables." in scripture["MRK"]


@pytest.mark.parametrize(
    "code, reference, usfm",
    [
        # Its italic renderings, each after its label.
        (
            "GEN",
            "24:11",
            "\\f - \\fr 24:11 \\fq rested: \\ft Heb. \\fqa caused to kneel "
            "down\\ft . Gr. \\fqa caused to sleep\\f*",
        ),
        # A cross-reference at the start of its verse needs no lemma.
        ("DEU", "32:21", "\\f - \\fr 32:21 \\ft See \\xt Rom. 10. 9\\f*"),
        # A note after the last word of its verse glosses the words before it.
        (
            "PRO",
            "21:27",
            "\\f - \\fr 21:27 \\fq wickedly: \\ft or, \\fqa unlawfully\\f*",
        ),
        # A widened lemma widens its rendering...
        (
            "GEN",
            "40:9",
            "\\f - \\fr 40:9 \\fq my dream: \\ft Gr. \\fqa my sleep\\f*",
        ),
        # ...unless an exception's lemma says what the rendering renders.
        (
            "JDG",
            "2:18",
            "\\f - \\fr 2:18 \\fq was moved: \\ft Gr. \\fqa repented\\ft . This "
            "word seems generally to stand for כהס\\f*",
        ),
        # A note on the whole verse.
        (
            "1SA",
            "17:49",
            "\\f - \\fr 17:49 \\ft Verse 50 is not in the Vatican codex. "
            "Alex. has the following.\\f*",
        ),
    ],
)
def test_brenton_footnotes(scripture, code, reference, usfm):
    assert footnotes(scripture[code], reference) == [usfm]


def test_brenton_text_keeps_no_caller(scripture):
    text = scripture["GEN"]
    assert "\\f +" not in text and "\\x " not in text
    # The empty note in 3 Kingdoms 6:1 is corrected away; its verse keeps the other.
    assert len(footnotes(scripture["1KI"], "6:1")) == 1


@pytest.mark.parametrize(
    "note, styled",
    [
        ("Or, a thing", "Or, _a thing_"),
        ("Gr. logos.", "Gr. _logos_."),
        ("Who is he?", "Who is he?"),
        ("Some read, our", "Some read, _our_"),
        # Greek before its English renders by the English.
        ("Some read τίς, who", "Some read τίς, _who_"),
        ("Gr. is revealed", "Gr. _is revealed_"),
        (
            "Or, gods that you worship, 2 Thess. 2.4",
            "Or, _gods that you worship_, 2 Thess. 2.4",
        ),
        (
            "Or, lascivious ways, as some copies read",
            "Or, _lascivious ways_, as some copies read",
        ),
        ("Gr. rightness, or straightness", "Gr. _rightness_, or _straightness_"),
        (
            "Or, be diminished, or fail of, etc.",
            "Or, _be diminished_, or _fail of_, etc.",
        ),
        ("the word signifieth a measure", "the word signifieth a measure"),
    ],
)
def test_marginal_note_styling(note, styled):
    plain, styles, _ = notes.styled(notes.labelled_pieces(note))
    assert notes.underscored(plain, styles) == styled


@pytest.mark.parametrize(
    "body, styled",
    [
        (
            "\\fqa Gr. \\ft and between the darkness. \\fqa Hebraism.",
            "Gr. _and between the darkness_. Hebraism.",
        ),
        # A comment after a label stays roman.
        (
            "\\fqa Or, \\ft probably any large fish, or marine animals.",
            "Or, probably any large fish, or marine animals.",
        ),
        ("\\fqa Alex. \\ft has the following.", "Alex. has the following."),
        ("\\fqa Gr. \\ft plural.", "Gr. plural."),
        # A label inside a sentence introduces no rendering.
        (
            "\\ft The \\fqa Gr. \\ft word ἀλλοφύλοι is applied elsewhere.",
            "The Gr. word ἀλλοφύλοι is applied elsewhere.",
        ),
        (
            "\\fqa Gr. \\ft do good \\fqa or \\ft make good.",
            "Gr. _do good_ or _make good_.",
        ),
        ("\\fqa Heb. \\ft and \\fqa Alex. \\ft Samuel.", "Heb. and Alex. _Samuel_."),
        # Quoted Greek ends a rendering after a comma...
        ("\\fqa Gr. \\ft furnace, κάμινον.", "Gr. _furnace_, κάμινον."),
        # ...and before its English, the English is the rendering.
        ("\\fqa Alex. \\ft ἐντολαί, commands.", "Alex. ἐντολαί, _commands_."),
        # A comment after a comma ends a rendering.
        ("\\fqa Gr. \\ft horn, so \\fqa Heb.", "Gr. _horn_, so Heb."),
        ("\\fqa Gr. \\ft it, sc. the people.", "Gr. _it_, sc. the people."),
        # Words ending on "the" or "as" before a label introduce it.
        ("\\fqa Gr. \\ft from the \\fqa Heb.", "Gr. from the Heb."),
        # Quoted words a note adds are the reading, as after "+".
        (
            "\\fqa Heb. \\ft and \\fqa Alex. \\ft insert 'priest.'",
            "Heb. and Alex. insert '_priest_.'",
        ),
        ("\\fqa Alex. \\ft + the Lord.", "Alex. + _the Lord_."),
        (
            "\\fqa Gr. \\ft 'turned away,' but not from them.",
            "Gr. '_turned away_,' but not from them.",
        ),
        # Brenton's italic for a cited word stays italic.
        (
            "\\ft rendered by \\fqa meadow, \\ft in Job.",
            "rendered by _meadow_, in Job.",
        ),
        # A word Brenton set in italic inside a rendering does not end it...
        (
            "\\fqa Gr. \\ft a head of hair \\fqa even \\ft hair, etc.",
            "Gr. _a head of hair even hair_, etc.",
        ),
        # ...but a comma after it does.
        (
            "\\fqa Gr. \\ft made \\fqa ellulim, \\ft a Hebrew word.",
            "Gr. _made ellulim_, a Hebrew word.",
        ),
        # Figures are a rendering.
        ("\\fqa Alex. \\ft 187 years.", "Alex. _187 years_."),
        (
            "\\fqa Alex. \\ft translates the words \\fqa “the way of the seers.”",
            "Alex. translates the words “_the way of the seers_.”",
        ),
    ],
)
def test_brenton_note_styling(body, styled):
    plain, styles, _ = notes.styled(notes.brenton_pieces(body))
    assert notes.underscored(plain, styles) == styled


@pytest.mark.parametrize(
    "styled, style, expected",
    [
        ("Gr. _thy_", "rendering", "Gr. _thy soul_"),
        ("Gr. _in_, or, _among_", "rendering", "Gr. _in soul_, or, _among soul_"),
        # Brenton's own italic in a note without a rendering stays as it is.
        ("see _Underskiddaw_", "roman", "see _Underskiddaw_"),
    ],
)
def test_echoed(styled, style, expected):
    plain = styled.replace("_", "")
    styles = notes.overridden_styles(styled, plain, ["ft"] * len(plain), "K")
    assert (
        notes.underscored(*notes.echoed(plain, styles, style, "", " soul")) == expected
    )


def test_echo():
    verse = "with all your heart, and with all your soul"
    words = word_spans(verse)
    # The second your (7), widened to your soul or all your.
    assert notes.echo(verse, words, (7, 8), (7, 7)) == ("", " soul")
    assert notes.echo(verse, words, (6, 7), (7, 7)) == ("all ", "")
    assert notes.echo(verse, words, (7, 7), (7, 7)) == ("", "")
    assert notes.echo(verse, words, None, None) == ("", "")


def test_usfm_body_runs():
    plain, styles, alternative = notes.styled(notes.labelled_pieces("Gr. gift."))
    assert alternative == "gift"
    assert notes.usfm_body(plain, styles) == "\\ft Gr. \\fqa gift\\ft ."


def test_usfm_body_joins_a_run_of_spaces_to_the_run_before():
    styles = ["fqa", "fqa", "ft", "xt", "xt", "xt"]
    assert notes.usfm_body("ab  cd", styles) == "\\fqa ab  \\xt cd"


def test_measured_backward_keeps_the_article_the_lemma_starts_with():
    verse = "and he saw the great city."
    words = word_spans(verse)
    clause = notes.clause_before(verse, words, len(words) - 1)
    assert notes.measured(words, clause, ["the", "big", "town"], backward=True) == (
        3,
        "length",
    )


def test_note_override_must_match_the_note():
    plain, styles, _ = notes.styled(notes.labelled_pieces("Gr. gift."))
    with pytest.raises(CheckFailed, match="does not match the note: KEY"):
        notes.overridden_styles("Gr. _gifts_.", plain, styles, "KEY")


def test_note_override_sets_the_rendering():
    source = "\\fqa Lit. \\ft deserting in a military sense."
    pieces = notes.brenton_pieces(source)
    _, _, alternative, rule = notes.note_body(
        pieces, "Lit. _deserting_ in a military sense.", "K", source
    )
    assert (alternative, rule) == ("deserting", "override")
    _, _, alternative, _ = notes.note_body(
        pieces, "Lit. deserting in a military sense.", "K", source
    )
    assert alternative is None


def lemma(verse, note, kind="f"):
    """The lemma inferred for a note whose caller stands at ‸ in the verse."""
    offset = verse.index("‸")
    verse = verse.replace("‸", "")
    words = word_spans(verse)
    _, _, alternative = notes.styled(notes.labelled_pieces(note))
    span, rule = notes.inferred_lemma(kind, verse, words, offset, alternative)
    return (notes.lemma_text(verse, words, span) if span else None), rule


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
def test_inferred_lemma(verse, note, expected):
    assert lemma(verse, note) == expected


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
def test_cross_reference_lemma(verse, expected):
    assert lemma(verse, "See Rom. 1. 1.", kind="x") == expected


def test_footnotes_stand_where_their_notes_were():
    text = "\\v 1 One two three four.\n"
    start = text.index("One")
    entries = [
        notes.Entry(
            "K#2", "1:1", start + 8, "three", "b.", ["ft"] * 2, "length", "roman"
        ),
        notes.Entry("K", "1:1", start + 4, "two", "a.", ["ft"] * 2, "length", "roman"),
    ]
    assert notes.set_footnotes(text, entries) == (
        "\\v 1 One \\f - \\fr 1:1 \\fq two: \\ft a\\f*two "
        "\\f - \\fr 1:1 \\fq three: \\ft b\\f*three four.\n"
    )


@pytest.mark.parametrize(
    "lemma, note, styled",
    [
        ("two", "Or, first", "or, _first_"),
        ("two", "Some read, first", "some read, _first_"),
        ("two", "The Gr. word first", "the Gr. word first"),
        # Names keep their capital...
        ("two", "Gr. first", "Gr. _first_"),
        ("two", "Alex. first", "Alex. _first_"),
        ("two", "A. V. first", "A. V. _first_"),
        # ...as do the pronoun "I", capitals, quotations and references.
        ("two", "I first", "I first"),
        ("two", "LXX. first", "LXX. first"),
        ("two", "'First,' etc.", "'First,' etc."),
        # A note on the whole verse opens its sentence.
        (None, "Or, first", "Or, _first_"),
    ],
)
def test_note_runs_on_from_its_lemma(lemma, note, styled):
    plain, styles, _ = notes.styled(notes.labelled_pieces(note))
    entry = notes.Entry("K", "1:1", 0, lemma, plain, styles, "anchor", "rendering")
    assert entry.styled == styled


@pytest.mark.parametrize(
    "note, styled",
    [
        ("Gr. gift.", "Gr. _gift_"),
        ("Who is he?", "Who is he?"),
        ("A. V. 'my people.'", "A. V. '_my people_'"),
        # An abbreviation keeps its full stop.
        ("Gr. gift, etc.", "Gr. _gift_, etc."),
        ("Gr. gift, so the Heb.", "Gr. _gift_, so the Heb."),
        ("Gr. gift, as in LXX.", "Gr. _gift_, as in LXX."),
        ("Gr. or.", "Gr. _or_"),
        ("i. e. Abimelech's.", "i. e. _Abimelech's_"),
        ("Gr. infin. for imper.", "Gr. infin. for imper."),
        # So does an ellipsis.
        ("Or, probably so...", "Or, probably so..."),
    ],
)
def test_note_drops_its_closing_full_stop(note, styled):
    plain, styles, _ = notes.styled(notes.labelled_pieces(note))
    entry = notes.Entry("K", "1:1", 0, None, plain, styles, "verse-level", "rendering")
    assert entry.styled == styled


@pytest.mark.parametrize(
    "note, styled",
    [
        # George's notes have neither the capital nor the full stop.
        (
            "the word Batus in the original containeth nine gallons 3. quarts",
            "The word Batus in the original containeth nine gallons 3. quarts.",
        ),
        ("The Gr. is from the Heb. word.", "The Gr. is from the Heb. word."),
        ("Who is he?", "Who is he?"),
        # Quoted Greek keeps its letter.
        ("ὥστε seems to be given", "ὥστε seems to be given."),
        # A label, a rendering, or a verb only in a rendering makes no sentence.
        ("Or, as being righteous", "or, _as being righteous_"),
        ("Gr. it is so.", "Gr. _it is so_"),
        ("Men, understood.", "men, understood"),
    ],
)
def test_sentence_keeps_its_capital_and_full_stop(note, styled):
    plain, styles, _ = notes.styled(notes.labelled_pieces(note))
    entry = notes.Entry("K", "1:1", 0, "two", plain, styles, "anchor", "roman")
    assert entry.styled == styled


def test_sentence_override():
    plain, styles, _ = notes.styled(
        notes.labelled_pieces("a word easily read for another")
    )
    entry = notes.Entry("K", "1:1", 0, "two", plain, styles, "anchor", "roman", False)
    assert entry.styled == "a word easily read for another"
    with pytest.raises(CheckFailed, match="Note sentence override changes nothing: K"):
        notes.overridden_sentence({"sentence": True}, plain, styles, "K")


def test_note_drops_its_closing_full_stop_before_a_trailing_space():
    # eBible ends the notes on 1 Kingdoms 17:13-31 with a space.
    source = "\\ft \\+it Gr. \\+it* name. "
    plain, styles, _, _ = notes.note_body(
        notes.brenton_pieces(source), None, "K", source
    )
    entry = notes.Entry("K", "1:1", 0, "names", plain, styles, "length", "rendering")
    assert entry.body == "\\ft Gr. \\fqa name"


def test_reference_after_lemma_keeps_its_capital():
    source = "\\xt Rom. 10. 15."
    plain, styles, _, _ = notes.note_body(
        notes.brenton_pieces(source), None, "K", source
    )
    entry = notes.Entry("K", "1:1", 0, "two", plain, styles, "anchor", "roman")
    assert entry.body == "\\xt Rom. 10. 15"


def test_unused_brenton_exception(archives, patched):
    patched(notes, "BRENTON_NOTES")["notes"]["GEN 1:1"] = {
        "lemma": "heaven",
        "why": "x",
    }
    with pytest.raises(
        CheckFailed, match=r"Unused Brenton note exceptions: \['GEN 1:1'\]"
    ):
        scripture_text(unit("GEN"), archives)


def test_brenton_lemma_override_that_changes_nothing(archives, patched):
    patched(notes, "BRENTON_NOTES")["notes"]["GEN 1:10"] = {
        "lemma": "gatherings",
        "why": "x",
    }
    with pytest.raises(CheckFailed, match="Lemma override changes nothing: GEN 1:10"):
        scripture_text(unit("GEN"), archives)


def test_brenton_lemma_override_of_the_widened_lemma_stops_the_echo(archives, patched):
    patched(notes, "BRENTON_NOTES")["notes"]["DEU 4:29"] = {
        "lemma": "your heart",
        "why": "x",
    }
    text = scripture_text(unit("DEU"), archives)
    assert footnotes(text, "4:29")[0] == (
        "\\f - \\fr 4:29 \\fq your heart: \\ft Gr. \\fqa thy\\f*"
    )


def test_brenton_lemma_override_names_its_occurrence(archives):
    # "Thus" occurs twice; widened to be unique, the rendering takes in "saying".
    assert footnotes(scripture_text(unit("1KI"), archives), "20:19") == [
        "\\f - \\fr 20:19 \\fq saying, Thus: \\ft Gr. \\fqa saying, these things\\f*"
    ]


def test_brenton_lemma_override_occurrence_must_be_needed(archives, patched):
    patched(notes, "BRENTON_NOTES")["notes"]["GEN 1:10"] = {
        "lemma": "gatherings",
        "occurrence": 1,
        "why": "x",
    }
    with pytest.raises(
        CheckFailed, match=r"occurrence not found, or not needed: GEN 1:10 \(1\)"
    ):
        scripture_text(unit("GEN"), archives)


def test_brenton_lemma_override_must_occur_once(archives, patched):
    patched(notes, "BRENTON_NOTES")["notes"]["GEN 1:10"] = {"lemma": "the", "why": "x"}
    with pytest.raises(
        CheckFailed, match=r"not found exactly once: GEN 1:10 \([2-9]\)"
    ):
        scripture_text(unit("GEN"), archives)


def test_brenton_note_override_that_changes_nothing(archives, patched):
    patched(notes, "BRENTON_NOTES")["notes"]["GEN 1:10"] = {
        "note": "Gr. _systems_.",
        "why": "x",
    }
    with pytest.raises(CheckFailed, match="Note override changes nothing: GEN 1:10"):
        scripture_text(unit("GEN"), archives)


def test_brenton_corrections(archives, scripture):
    assert footnotes(scripture["GEN"], "21:11") == [
        "\\f - \\fr 21:11 \\fq word: \\ft Gr. \\fqa saying\\ft , or \\fqa matter\\f*"
    ]
    preface = front_matter_text(unit_front("XXB"), archives)
    assert "LXX.\\f* is little doubt" in preface


def test_brenton_correction_that_does_not_apply(archives, patched):
    patched(notes, "BRENTON_NOTES")["corrections"]["GEN 1:1"] = {
        "from": "no such text",
        "to": "x",
        "why": "x",
    }
    with pytest.raises(CheckFailed, match="Brenton correction does not apply: GEN 1:1"):
        scripture_text(unit("GEN"), archives)


@pytest.mark.parametrize(
    "source, key, snippet",
    [
        # Another verse's note.
        ("GEN", "GEN 21:12", "\\fr 21:11 \\fqa Gr. \\fqa Gr. "),
        # Another verse's text.
        ("GEN", "GEN 1:2", "the beginning God made"),
        # Words the preface's note does not stand among.
        ("XXB", "XXB is little", "\\f*is little doubt"),
    ],
)
def test_brenton_correction_must_be_where_its_key_says(
    archives, patched, source, key, snippet
):
    patched(notes, "BRENTON_NOTES")["corrections"] = {
        key: {"from": snippet, "to": snippet + ".", "why": "x"}
    }
    message = f"Brenton correction is not where its key says: {key}"
    with pytest.raises(CheckFailed, match=message):
        notes.corrected_brenton(
            source, archives["brenton"][source], recorder(None, source)
        )


def test_brenton_correction_must_keep_the_wording_outside_notes(archives, patched):
    # A correction to the verse's own words, not a note's, even a slip's size.
    patched(notes, "BRENTON_NOTES")["corrections"] = {
        "GEN 1:1": {
            "from": "beginning God made the heaven and",
            "to": "beginning God made the heavens and",
            "why": "x",
        }
    }
    with pytest.raises(
        CheckFailed, match="changes the wording outside a note: GEN 1:1"
    ):
        notes.corrected_brenton(
            "GEN", archives["brenton"]["GEN"], recorder(None, "GEN")
        )


@pytest.mark.parametrize(
    "before, after, category",
    [
        ("\\ft he\\fl or", "\\ft he \\fl or", "missing word space"),
        ("Hebraism \\ft See", "Hebraism. \\ft See", "missing punctuation"),
        ("12.; \\ft", "12; \\ft", "stray punctuation"),
        ("him. And", "him, And", "wrong punctuation"),
        ("Th LXX", "The LXX", "missing letter"),
        ("appeaars", "appears", "stray letter"),
        ("debtOr,", "debtor,", "wrong letter"),
        ("\\fqa Gr. \\fqa Gr. \\ft x", "\\fqa Gr. \\ft x", "doubled text"),
        ("hell [obviously a typo]", "hell", "remark"),
        ("Israel,\\f + \\fr 6:1 \\f*", "Israel,", "empty note"),
        ("[Greek characters]", "τὰ ὅσια,", "omitted Greek"),
        # Two letters wrong, a letter for a space, and Greek with English.
        ("my nanda.", "my hands.", None),
        ("good a les.", "good axles.", None),
        ("[Greek characters]", "ἐτροποφόρησεν, perhaps for", None),
        ("same", "same", None),
    ],
)
def test_correction_category(before, after, category):
    assert notes.correction_category(before, after) == category


def test_correction_that_fits_no_category(archives, patched):
    patched(notes, "BRENTON_NOTES")["corrections"] = {
        "GEN 21:11": {"from": "\\fqa Gr. \\fqa Gr. ", "to": "\\fqa Heb. ", "why": "x"}
    }
    with pytest.raises(
        CheckFailed, match="Brenton correction fits no category of slip: GEN 21:11"
    ):
        notes.corrected_brenton(
            "GEN", archives["brenton"]["GEN"], recorder(None, "GEN")
        )


def test_uncategorized_correction_that_fits_a_category(archives, patched):
    patched(notes, "BRENTON_NOTES")["corrections"]["GEN 21:11"]["uncategorized"] = True
    with pytest.raises(
        CheckFailed,
        match="Brenton correction listed as uncategorized is a doubled text: GEN 21:11",
    ):
        notes.corrected_brenton(
            "GEN", archives["brenton"]["GEN"], recorder(None, "GEN")
        )


@pytest.mark.parametrize(
    "lemma, anchor, category",
    [
        ("day spring", "dayspring", "word division"),
        ("marketplace", "market-place", "word division"),
        ("boisterous", "boysterous", "wrong letter"),
        ("highly favored", "highly favoured", "missing letter"),
        ("into an house", "into a house", "stray letter"),
        ("held a counsel", "held a council", None),
        ("stop me in this", "stop me of this", None),
        ("to use of the edifying", "to the use of edifying", None),
        ("the kings chaberlaine", "the king’s chamberlain", None),
    ],
)
def test_anchor_category(lemma, anchor, category):
    words = [[w for w, _, _ in word_spans(p)] for p in (lemma, anchor)]
    assert notes.anchor_category(*words) == category


def test_anchor_that_fits_no_category(archives, patched):
    del patched(notes, "KJV_NOTES")["notes"]["MAT 12:14 held a counsel"][
        "uncategorized"
    ]
    with pytest.raises(
        CheckFailed,
        match="anchor fits no category of difference: MAT 12:14 held a counsel",
    ):
        scripture_text(unit("MAT"), archives)


def test_uncategorized_anchor_that_fits_a_category(archives, patched):
    patched(notes, "KJV_NOTES")["notes"]["MAT 14:30 boisterous"]["uncategorized"] = True
    with pytest.raises(
        CheckFailed,
        match="anchor listed as uncategorized is a wrong letter: MAT 14:30 boisterous",
    ):
        scripture_text(unit("MAT"), archives)


def test_anchor_that_changes_nothing(archives, patched):
    patched(notes, "KJV_NOTES")["notes"]["MAT 14:30 boisterous"] = {
        "anchor": "Boisterous,"
    }
    with pytest.raises(
        CheckFailed, match="anchor changes nothing: MAT 14:30 boisterous"
    ):
        scripture_text(unit("MAT"), archives)


def test_note_must_keep_its_word_spaces():
    # Ignoring whitespace, "heor" and "he or" would be the same text.
    with pytest.raises(CheckFailed, match="Note restyling changed its text: K"):
        notes.note_body(notes.brenton_pieces("\\ft heor."), None, "K", "\\ft he or.")
