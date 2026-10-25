"""The Alexandrine readings: declared, derived from Brenton's words, and
carried out on his books before anything else reads them."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any, cast

import pytest
from conftest import book, changed, verse_lines

import bible.annotate
import bible.pipeline
import bible.policy
from bible import alexandrinus, annotate, notes, scripture, terminology, usj
from bible.checks import CheckFailed
from bible.policy_schema import Decision, Swete
from bible.usj import Document

SWETE: Swete = {
    "volume": 1,
    "page": 5,
    "evidence": "text",
    "reading": "Κύριος",
    "agrees": True,
}
NOTE = r"\fqa Alex. \ft + the Lord."
READING: Decision = {
    "why": "Print Brenton's Alexandrine reading.",
    "swete": SWETE,
    "from": "God said",
    "note": r"\fl Vat. \ft omits “the Lord”.",
    "english": {
        "source": "brenton",
        "span": (17, 25),
        "edits": ({"span": (8, 8), "to": " God said"},),
    },
    "source_note": NOTE,
}
VERSES = (
    r"\v 21 And they were clothed."
    "\n"
    r"\v 22 And \f + \fr 99:22 \fqa Alex. \ft + the Lord.\f*God said, Behold, \f + \fr 99:22 \fqa Gr. \ft look.\f*Adam is become as one of us."
    "\n"
    r"\v 23 So he sent him forth."
)


def decided(
    policy: bible.policy.Policy,
    readings: dict[str, Any] | None = None,
    passages: object = None,
    kept: object = None,
) -> bible.policy.Policy:
    def change(data: dict[str, Any]) -> None:
        data.update(readings=readings or {}, passages=passages or {}, kept=kept or {})

    return changed(policy, "alexandrinus", change)


def promoted(
    policy: bible.policy.Policy,
    body: str = VERSES,
    kjv: Mapping[str, Document] | None = None,
) -> Document:
    doc = book("GEN", body)
    return alexandrinus.promoted("GEN", doc, policy, kjv or {}, {"GEN": doc})


def test_a_reading_replaces_the_vatican_words_and_notes_them(
    policy: bible.policy.Policy, ctx: bible.annotate.Context
) -> None:
    doc = promoted(decided(policy, {"GEN 99:22": READING}))
    assert verse_lines(doc)["22"] == (
        r"And \f + \cat edition\cat*\fr 99:22 \fl Vat. \ft omits “the Lord”.\f*the Lord God said, Behold, "
        r"\f + \fr 99:22 \fqa Gr. \ft look.\f*Adam is become as one of us."
    )
    note = scripture.verses(doc)["99:22"].notes[0][1]
    assert (note["x-key"], note["category"], note["x-scope"]) == (
        "GEN 99:22",
        "edition",
        {"declared": "the Lord God said"},
    )
    # The edition's note names the words that were printed in the Vatican's place.
    printed, _ = annotate.brenton("GEN", doc, (), frozenset(), ctx)
    assert verse_lines(printed)["22"].startswith(
        r"And \f - \cat edition\cat*\fr 99:22 \fq the Lord God said: \ft Vat. omits \+it the Lord\+it*\f*the Lord God said,"
    )


def test_a_reading_without_a_note_of_its_own_gives_brentons_alternative(
    policy: bible.policy.Policy,
) -> None:
    reading = {k: v for k, v in READING.items() if k != "note"}
    doc = promoted(decided(policy, {"GEN 99:22": reading}))
    assert r"\fl Brenton \fqa God said\ft ." in verse_lines(doc)["22"]


def test_a_reading_without_a_note_names_the_witness_its_label_declares(
    policy: bible.policy.Policy,
) -> None:
    reading = {k: v for k, v in READING.items() if k != "note"} | {"label": "vatican"}
    doc = promoted(decided(policy, {"GEN 99:22": reading}))
    assert r"\fl Vat. \fqa God said\ft ." in verse_lines(doc)["22"]


@pytest.mark.parametrize(
    "label,message",
    [("brenton", "label changes nothing"), ("vatican", "fields beside a note")],
)
def test_a_reading_label_must_change_something_and_stand_alone(
    policy: bible.policy.Policy, label: str, message: str
) -> None:
    reading = dict(READING) | {"label": label}
    if label == "brenton":
        del reading["note"]
    with pytest.raises(CheckFailed, match=message):
        promoted(decided(policy, {"GEN 99:22": reading}))


@pytest.mark.parametrize("omits", [False, True])
@pytest.mark.parametrize("hebrew", [False, True])
@pytest.mark.parametrize("label", [None, "vatican"])
def test_structured_witness_notes_match_explicit_notes_through_annotation(
    policy: bible.policy.Policy,
    ctx: bible.annotate.Context,
    omits: bool,
    hebrew: bool,
    label: str | None,
) -> None:
    reading = {k: v for k, v in READING.items() if k != "note"}
    if label:
        reading["label"] = label
    witness = "Vat." if label else "Brenton"
    explicit = (
        rf"\fl {witness} \ft omits." if omits else rf"\fl {witness} \fqa God said\ft ."
    )
    if omits:
        reading["omits"] = True
    if hebrew:
        reading["hebrew_agrees"] = True
        explicit = r"\fl Heb. \ft agrees. " + explicit
    generated = promoted(decided(policy, {"GEN 99:22": reading}))
    handwritten = promoted(
        decided(policy, {"GEN 99:22": {**READING, "note": explicit}})
    )
    assert generated == handwritten
    printed, report = annotate.brenton("GEN", generated, (), frozenset(), ctx)
    expected, _ = annotate.brenton("GEN", handwritten, (), frozenset(), ctx)
    assert printed == expected
    row = next(row for row in report.rows if row["key"] == "GEN 99:22")
    assert row["reading"] == (None if omits else "God said")


@pytest.mark.parametrize("label", [None, "vatican"])
def test_generated_alternative_widens_with_its_lemma(
    policy: bible.policy.Policy, ctx: bible.annotate.Context, label: str | None
) -> None:
    reading = {k: v for k, v in READING.items() if k != "note"}
    reading["english"] = {"source": "brenton", "span": (17, 25)}
    if label:
        reading["label"] = label
    body = VERSES.replace("God said, Behold,", "God said to the Lord, Behold,")
    generated = promoted(decided(policy, {"GEN 99:22": reading}), body)
    printed, report = annotate.brenton("GEN", generated, (), frozenset(), ctx)
    note = scripture.verses(printed)["99:22"].notes[0][1]
    fields = {
        n["marker"]: usj.text_of(n["content"])
        for n in note["content"]
        if isinstance(n, dict)
    }
    assert fields["fq"] != "the Lord: "  # The repeated lemma had to widen.
    assert "God said" in fields["fqa"]
    assert fields["fqa"] != "God said"  # Its alternative widened with it.
    assert (
        next(row for row in report.rows if row["key"] == "GEN 99:22")["reading"]
        == "God said"
    )
    # Commentary quotations keep their exact words even when the lemma widens.
    explicit = {**reading, "note": r"\fl Vat. \fq God said\ft ."}
    explicit.pop("label", None)
    quoted = promoted(decided(policy, {"GEN 99:22": explicit}), body)
    printed, _ = annotate.brenton("GEN", quoted, (), frozenset(), ctx)
    assert r"\+it God said\+it*" in verse_lines(printed)["22"]


@pytest.mark.parametrize(
    "change, message",
    [
        ({"omits": False}, "Invalid Alexandrine omits"),
        ({"hebrew_agrees": False}, "Invalid Alexandrine hebrew_agrees"),
        ({"omits": "yes"}, "Invalid Alexandrine omits"),
        ({"label": "unknown"}, "Unknown Alexandrine label"),
        ({"label": []}, "Unknown Alexandrine label"),
        (
            {"label": "hebrew", "hebrew_agrees": True},
            "Contradictory Alexandrine Hebrew agreement",
        ),
        (
            {"label": "vatican", "omits": True, "omit_verse": True},
            "Unsupported Alexandrine omission",
        ),
        ({"omits": True, "lemma": None}, "Unsupported Alexandrine omission"),
        ({"omit_verse": True}, "Unsupported Alexandrine omission"),
        (
            {"label": "vatican", "hebrew_agrees": True, "omit_verse": True},
            "Unsupported Alexandrine omission",
        ),
        ({"note": None, "hebrew_agrees": True}, "fields beside a note"),
        ({"note": r"\ft Commentary.", "omits": True}, "fields beside a note"),
        ({"from": " . "}, "Empty Alexandrine alternative"),
    ],
)
def test_invalid_structured_notes_name_the_decision(
    declared: bible.policy.Policy, change: dict[str, Any], message: str
) -> None:
    with pytest.raises(CheckFailed, match=message + ".*GEN 99:22"):
        alexandrinus.note_content(
            cast(Decision, {"from": "God said", **change}),
            "GEN 99:22",
            terminology.registry(declared),
        )


@pytest.mark.parametrize(
    "change",
    [
        {"lemma": "the Lord God"},
        {"note_at": 8},
        {"omits": True, "note_at": 17},
    ],
)
def test_a_composed_note_must_fit_its_lemma(
    policy: bible.policy.Policy, change: dict[str, Any]
) -> None:
    """An alternative stands for every word printed in its place, and an
    omission names some of them; anything else needs an explicit note."""
    reading = {k: v for k, v in READING.items() if k != "note"} | change
    with pytest.raises(CheckFailed, match="does not fit its lemma.*GEN 99:22"):
        promoted(decided(policy, {"GEN 99:22": reading}))


def test_further_replacements_inherit_or_replace_the_whole_note_description() -> None:
    parent: Decision = {
        "from": "old",
        "label": "vatican",
        "omits": True,
        "hebrew_agrees": True,
    }
    assert dict(alexandrinus.further(parent, {"from": "other"})) == {
        **parent,
        "from": "other",
    }
    assert dict(alexandrinus.further(parent, {"from": "other", "note": None})) == {
        "from": "other",
        "note": None,
    }
    assert dict(alexandrinus.further(parent, {"label": "hebrew"})) == {
        "from": "old",
        "label": "hebrew",
    }
    assert dict(
        alexandrinus.further({"note": r"\ft Commentary."}, {"label": "vatican"})
    ) == {"label": "vatican"}


@pytest.mark.parametrize(
    "text",
    [
        r"\fl Heb. \ft nearly agrees. \fl Vat. \fq quoted words\ft .",
        r"\fl Sinaiticus \fqa other words\ft .",
        r"\fl Vat. \ft adds \fq a clause\ft . \fl Heb. \ft omits it.",
    ],
)
def test_exceptional_notes_keep_their_explicit_roles(
    declared: bible.policy.Policy, text: str
) -> None:
    body = alexandrinus.note_content(
        {"note": text}, "GEN 99:22", terminology.registry(declared)
    )
    assert body == usj.parse(text, fragment=True)
    assert body is not None
    interpreted = notes.authored_body(
        alexandrinus.edition_note("GEN 99:22", "99:22", body), None, "GEN 99:22"
    )
    assert interpreted.alternative == ("other words" if "fqa" in text else None)


@pytest.mark.parametrize("override", [False, True])
def test_an_addition_keeps_its_scope_before_promotion(
    policy: bible.policy.Policy, override: bool
) -> None:
    doc = book(
        "GEN",
        r"\v 22 He said, Tell us \f + \fr 99:22 \fqa Alex. \ft adds 'new words'.\f*what happened.",
    )
    verse = scripture.verses(doc)["99:22"]
    offset, note = verse.notes[0]
    if override:
        policy = changed(
            policy,
            "brenton_notes",
            lambda data: data["notes"].update(
                {
                    "GEN 99:22": {
                        "note": "Alex. adds '_new words_'.",
                        "why": "Test italics.",
                    }
                }
            ),
        )
    assert alexandrinus.surviving_scope(note, verse, offset, policy) == (
        "Tell us",
        "Tell us",
    )


def test_english_is_derived_exactly_and_only_from_brentons_words() -> None:
    assert alexandrinus.derived("key", READING, NOTE) == "the Lord God said"
    # A span's edit may write supplied words; its vocabulary must be Brenton's,
    # or declared as the editor's.
    supplied: Decision = {
        **READING,
        "english": {
            "source": "from",
            "edits": ({"span": (0, 0), "to": r"\add Almighty\add* "},),
        },
    }
    with pytest.raises(CheckFailed, match="English not supplied by its sources"):
        alexandrinus.derived("key", supplied, NOTE)
    assert (
        alexandrinus.derived("key", supplied, NOTE, ["Almighty"])
        == r"\add Almighty\add* God said"
    )
    # Brenton's numbers may be spelled out, whichever way he wrote them.
    aged: Decision = {
        "from": "an hundred and sixty and seven years",
        "english": {
            "source": "brenton",
            "span": (15, 24),
            "edits": ({"span": (0, 3), "to": "an hundred and eighty and seven"},),
        },
    }
    assert (
        alexandrinus.derived("key", aged, r"\fqa Alex. \ft 187 years.")
        == "an hundred and eighty and seven years"
    )
    with pytest.raises(CheckFailed, match="Malformed English editorial edit"):
        alexandrinus.derived(
            "key",
            {
                **READING,
                "english": {
                    "source": "brenton",
                    "edits": ({"span": (0, 3), "to": NOTE[:3]},),
                },
            },
            NOTE,
        )


@pytest.mark.parametrize(
    "words, expected",
    [
        ("an hundred and eighty and seven", ["187"]),
        ("five and twenty cubits", ["25", "cubits"]),
        ("sixty-two thousand and five hundred", ["62500"]),
        ("In the twenty-sixth year", ["in", "the", "26th", "year"]),
        ("21st 22nd 23rd 24th", ["21th", "22th", "23th", "24th"]),
    ],
)
def test_numbers_are_brentons_by_their_value_however_written(
    words: str, expected: list[str]
) -> None:
    assert alexandrinus.tokens(words) == expected


@pytest.mark.parametrize(
    "change, refusal",
    [
        ({"from": "God spake"}, "from not found once"),
        ({"source_note": r"\fqa Alex. \ft + the Lord God."}, "source note changed"),
    ],
)
def test_a_decision_that_no_longer_fits_its_source_is_refused(
    change: Decision,
    refusal: str,
    policy: bible.policy.Policy,
) -> None:
    with pytest.raises(CheckFailed, match=refusal):
        promoted(decided(policy, {"GEN 99:22": {**READING, **change}}))


def test_a_kept_note_declared_without_its_words_is_refused(
    policy: bible.policy.Policy,
) -> None:
    kept = {"GEN 99:22#1": {"source_note": NOTE, "note": None, "why": "Keep it."}}
    with pytest.raises(CheckFailed, match="without its words: GEN 99:22#1"):
        alexandrinus.companions(decided(policy, kept=kept), "GEN")


def test_a_kept_note_about_no_words_keeps_its_place(
    policy: bible.policy.Policy,
) -> None:
    kept = {
        "GEN 99:22#2": {
            "why": "Keep it.",
            "swete": SWETE,
            "source_note": r"\fqa Gr. \ft look.",
            "note": r"\fl Alex. \ft See the Appendix.",
            "lemma": None,
        }
    }
    doc = promoted(decided(policy, {"GEN 99:22": READING}, kept=kept))
    assert verse_lines(doc)["22"].endswith(
        r"Behold, \f + \cat edition\cat*\fr 99:22 \fl Alex. \ft See the Appendix.\f*Adam is become as one of us."
    )


def test_a_note_about_no_words_within_replaced_words_is_refused(
    policy: bible.policy.Policy,
) -> None:
    reading = {
        **READING,
        "from": "Behold, Adam is",
        "english": {"source": "from", "edits": [{"span": [0, 8], "to": ""}]},
        "lemma": None,
    }

    def whole(data: dict[str, Any]) -> None:
        data["notes"]["GEN 99:22#2"] = {"lemma": None, "why": "The verse."}

    # Its place lay among the words the reading replaces.
    with pytest.raises(CheckFailed, match="within replaced words: GEN 99:22#2"):
        promoted(
            changed(decided(policy, {"GEN 99:22": reading}), "brenton_notes", whole)
        )


def test_the_appendix_is_read_for_its_notes_alone(policy: bible.policy.Policy) -> None:
    doc = usj.parse(
        "\\id BAK\n\\ip Job 25. 2.—A note.\n\\is1 ———————\n"
        "\\is1 The Following Passages are Supplied From the Alexandrine Text\n"
        "\\is2 GENESIS\n\\ip 99. Considerable variation here.\n\\ib\n"
    )
    notes_only = usj.serialize(alexandrinus.appendix_notes(doc))
    assert (
        notes_only == "\\id BAK\n\\usfm 3.1\n\\ip Job 25. 2.—A note.\n\\is1 ———————\n"
    )


def test_an_appendix_paragraph_moved_to_a_note_without_words_is_refused(
    policy: bible.policy.Policy, read: bible.pipeline.Read
) -> None:
    wordless = changed(
        policy, "alexandrinus", lambda d: d["kept"]["PRO 21:16"].pop("note")
    )
    with pytest.raises(CheckFailed, match="not given its words: BAK PRO 21:16-17"):
        alexandrinus.check(wordless, read.brenton)
    # The list it stands in prints nowhere: kept but not moved, it would be lost.
    unmoved = changed(
        policy, "alexandrinus", lambda d: d["kept"]["BAK PRO 21:16-17"].pop("moved_to")
    )
    with pytest.raises(CheckFailed, match="moved nowhere: BAK PRO 21:16-17"):
        alexandrinus.check(unmoved, read.brenton)


def test_a_kept_lemma_without_the_note_it_places_is_refused(
    policy: bible.policy.Policy, read: bible.pipeline.Read
) -> None:
    stale = changed(
        policy, "alexandrinus", lambda d: d["kept"]["GEN 33:18"].update(lemma=None)
    )
    with pytest.raises(CheckFailed, match="without the note it places: GEN 33:18"):
        alexandrinus.check(stale, read.brenton)


def test_a_note_within_replaced_words_keeps_the_words_it_was_about(
    policy: bible.policy.Policy,
) -> None:
    reading = {
        **READING,
        "from": "God said, Behold, Adam",
        "english": {
            "source": "from",
            "edits": [{"span": [0, 3], "to": "the Lord God"}],
        },
    }
    doc = promoted(decided(policy, {"GEN 99:22": reading}))
    kept = scripture.verses(doc)["99:22"].notes[1][1]
    assert kept["x-key"] == "GEN 99:22#2"
    assert kept["x-scope"] == {"lemma": "Adam", "glossed": "Adam"}
    # Its caller stands at those words again, in the verse as it now reads.
    assert verse_lines(doc)["22"].endswith(
        r"the Lord God said, Behold, \f + \fr 99:22 \fqa Gr. \ft look.\f*Adam is become as one of us."
    )


def test_a_kept_note_is_set_before_the_words_it_glosses_not_its_wider_lemma(
    policy: bible.policy.Policy, ctx: bible.annotate.Context
) -> None:
    body = (
        r"\v 22 And \f + \fr 99:22 \fqa Alex. \ft + the Lord.\f*God said, Behold "
        r"\f + \fr 99:22 \fqa Gr. \ft look.\f*Adam the man as Adam was."
    )
    reading = {
        **READING,
        "from": "God said, Behold Adam",
        "english": {
            "source": "from",
            "edits": [{"span": [0, 3], "to": "the Lord God"}],
        },
    }
    doc = promoted(decided(policy, {"GEN 99:22": reading}), body)
    kept = scripture.verses(doc)["99:22"].notes[1][1]
    # Its lemma takes in a word before the one it glosses, to occur once.
    assert kept["x-scope"] == {"lemma": "Behold Adam", "glossed": "Adam"}
    assert verse_lines(doc)["22"].endswith(
        r"the Lord God said, Behold \f + \fr 99:22 \fqa Gr. \ft look.\f*Adam the man as Adam was."
    )
    printed, _ = annotate.brenton("GEN", doc, (), frozenset(), ctx)
    assert (
        r"Behold \f - \fr 99:22 \fq Behold Adam: \ft Gr. \fqa Behold look\f*Adam"
        in (verse_lines(printed)["22"])
    )


def test_a_readings_note_stands_before_its_declared_lemma(
    policy: bible.policy.Policy, ctx: bible.annotate.Context
) -> None:
    reading = {**READING, "lemma": "God said"}
    printed, _ = annotate.brenton(
        "GEN", promoted(decided(policy, {"GEN 99:22": reading})), (), frozenset(), ctx
    )
    assert verse_lines(printed)["22"].startswith(
        r"And the Lord \f - \cat edition\cat*\fr 99:22 \fq God said: \ft Vat. omits \+it the Lord\+it*\f*God said,"
    )
    # Even where the lemma lies outside the words the reading prints.
    reading = {**READING, "lemma": "And"}
    printed, _ = annotate.brenton(
        "GEN", promoted(decided(policy, {"GEN 99:22": reading})), (), frozenset(), ctx
    )
    assert verse_lines(printed)["22"].startswith(r"\f - \cat edition")
    with pytest.raises(CheckFailed, match="remove note_at: GEN 99:22"):
        promoted(decided(policy, {"GEN 99:22": {**reading, "note_at": 0}}))


def test_a_repeated_declared_lemma_is_the_one_the_reading_prints(
    policy: bible.policy.Policy, ctx: bible.annotate.Context
) -> None:
    body = (
        r"\v 22 And \f + \fr 99:22 \fqa Alex. \ft + the Lord.\f*God said, Behold "
        r"Adam the man as Adam was."
    )
    reading = {
        **READING,
        "from": "as Adam was",
        "english": {"source": "from", "edits": [{"span": [7, 11], "to": ""}]},
        "note": r"\fl Vat. \ft adds \fq was\ft .",
        "lemma": "Adam",
    }
    doc = promoted(decided(policy, {"GEN 99:22": reading}), body)
    assert verse_lines(doc)["22"].endswith(
        r"Behold Adam the man as \f + \cat edition\cat*\fr 99:22 \fl Vat. \ft adds \fq was\ft .\f*Adam."
    )
    printed, _ = annotate.brenton("GEN", doc, (), frozenset(), ctx)
    assert r"as \f - \cat edition\cat*\fr 99:22 \fq as Adam: " in (
        verse_lines(printed)["22"]
    )


def test_a_verse_omitted_whole_leaves_its_note_on_the_verse_before(
    policy: bible.policy.Policy,
) -> None:
    body = (
        r"\v 16 And Elisama, and Eliphalath,"
        "\n"
        r"\v 17 Samae, Nathan.\f + \fr 99:17 \fqa Alex. \ft omits these names.\f*"
        "\n"
        r"\v 18 And the Philistines heard."
    )
    reading = {
        **READING,
        "from": "Samae, Nathan.",
        "english": {"source": "from", "edits": [{"span": [0, 14], "to": ""}]},
        "note": r"\fl Vat. \ft adds \fq Samae, Nathan\ft .",
        "lemma": None,
        "source_note": r"\fqa Alex. \ft omits these names.",
        "omit_verse": True,
        "note_target": "GEN 99:16",
        "edits": [
            {
                "target": "GEN 99:16",
                "from": "Eliphalath,",
                "note": None,
                "why": "End the list.",
                "english": {"source": "from", "edits": [{"span": [10, 11], "to": "."}]},
            }
        ],
    }
    lines = verse_lines(promoted(decided(policy, {"GEN 99:17": reading}), body))
    assert list(lines) == ["16", "18"]
    assert (
        lines["16"]
        == r"And Elisama, and Eliphalath.\f + \cat edition\cat*\fr 99:16 \fl Vat. \ft adds \fq Samae, Nathan\ft .\f*"
    )


def test_a_reading_omits_consecutive_verses_as_one_run(
    policy: bible.policy.Policy, read: bible.pipeline.Read
) -> None:
    before = scripture.verses(read.brenton["1KI"])
    doc = alexandrinus.promoted(
        "1KI", read.brenton["1KI"], policy, read.kjv, read.brenton
    )
    verses = scripture.verses(doc)
    assert "5:14a" not in verses and "5:14b" not in verses
    assert verses["5:14"].text == before["5:14"].text
    assert verses["5:15"].text == before["5:15"].text
    # The paragraph they filled goes with them.
    assert verses["5:15"].parts[0][0] == verses["5:14"].parts[-1][0] + 1
    ((offset, note),) = verses["5:14"].notes
    assert offset == len(verses["5:14"].text)
    assert note["x-scope"] == {"declared": None}
    assert usj.text_of(note["content"]) == (
        "5:14 Heb. also omits the following verses, which Vat. adds: 14a"
        + before["5:14a"].text.strip()
        + " 14b"
        + before["5:14b"].text.strip()
    )
    omission = policy.alexandrinus["passages"]["1KI 14:1-20"]["omissions"][0]
    ((_, long_note),) = verses["12:24"].notes
    assert usj.text_of(long_note["content"]).endswith(
        " 24z" + before["12:24z"].text.strip()
    )
    assert long_note["x-key"] in policy.margin["below"]
    assert all(label not in verses for label in omission["verses"])


@pytest.mark.parametrize(
    "code, reference, key, former, account",
    [
        (
            "1SA",
            "25:24",
            "1SA 25:24",
            "even",
            "Heb. agrees. Vat. even.",
        ),
        (
            "1KI",
            "16:8",
            "1KI 16:8",
            "And Ela",
            "Heb. agrees. Vat. And Ela.",
        ),
        (
            "JER",
            "23:32",
            "JER 23:32 CCEL",
            "have not told them truly",
            "Heb. agrees. Vat. have not told them truly.",
        ),
    ],
)
def test_notes_preserve_displaced_conjunctions_and_english_supplements(
    policy: bible.policy.Policy,
    read: bible.pipeline.Read,
    code: str,
    reference: str,
    key: str,
    former: str,
    account: str,
) -> None:
    doc = alexandrinus.promoted(
        code, read.brenton[code], policy, read.kjv, read.brenton
    )
    verse = scripture.verses(doc)[reference]
    note = next(note for _, note in verse.notes if note["x-key"] == key)
    assert usj.text_of(note["content"]) == f"{reference} {account}"
    assert any(
        isinstance(item, dict)
        and item.get("marker") in {"fq", "fqa"}
        and usj.text_of(item["content"]) == former
        for item in note["content"]
    )


RUN = (
    r"\v 16 Before."
    "\n\\p\n"
    r"\v 16a \f + \fr 99:16a \fqa Alex. \ft omits these.\f*First addition."
    "\n"
    r"\v 16b Second addition."
    "\n\\p\n"
    r"\v 17 After."
)


def run_reading(**omission: Any) -> dict[str, Any]:
    return {
        "why": "Alexandrinus lacks both verses.",
        "swete": SWETE,
        "source_note": r"\fqa Alex. \ft omits these.",
        "omissions": [
            {
                "verses": ["99:16a", "99:16b"],
                "note_target": "99:16",
                "note": r"\fl Vat. \ft adds:",
                "source_notes": {},
                **omission,
            }
        ],
    }


def test_a_reading_run_takes_its_paragraph_and_its_note_gives_it_whole(
    policy: bible.policy.Policy, read: bible.pipeline.Read
) -> None:
    doc = promoted(decided(policy, {"GEN 99:16a": run_reading()}), RUN)
    assert list(verse_lines(doc)) == ["16", "17"]
    verses = scripture.verses(doc)
    assert verses["99:17"].parts[0][0] == verses["99:16"].parts[-1][0] + 1
    assert verse_lines(doc)["16"] == (
        r"Before.\f + \cat edition\cat*\fr 99:16 \fl Vat. \ft adds: \+fv 16a\+fv*First"
        r" addition. \+fv 16b\+fv*Second addition.\f*"
    )
    # The build gives the run; a note's own quotation of it would drift unseen.
    misquoting = run_reading(note=r"\fl Vat. \ft adds \fq First addition\ft :")
    with pytest.raises(CheckFailed, match="introduce its verses: GEN 99:16a"):
        promoted(decided(policy, {"GEN 99:16a": misquoting}), RUN)
    with pytest.raises(CheckFailed, match="one run: GEN 99:16a"):
        promoted(decided(policy, {"GEN 99:16a": run_reading(verses=["99:16b"])}), RUN)
    # The note it takes up goes, wherever it stands, though nothing else
    # in the book is decided.
    before = {
        **run_reading(),
        "source_note": r"\fqa Alex. \ft omits the next verses.",
    }
    noted = RUN.replace(r"\f + \fr 99:16a \fqa Alex. \ft omits these.\f*", "").replace(
        r"\v 16 Before.",
        r"\v 16 Before.\f + \fr 99:16 \fqa Alex. \ft omits the next verses.\f*",
    )
    assert (
        verse_lines(promoted(decided(policy, {"GEN 99:16": before}), noted))["16"]
        == verse_lines(doc)["16"]
    )
    # A verse omitted on its own is not noted on a verse the run omits,
    # where the run would take its note.
    lone = {
        **run_reading(),
        "from": "After.",
        "omit_verse": True,
        "note_target": "GEN 99:16b",
        "lemma": None,
        "note": r"\fl Vat. \ft adds \fq After\ft .",
        "english": {"source": "from", "edits": [{"span": [0, 6], "to": ""}]},
        "source_note": r"\fqa Alex. \ft omits.",
    }
    tail = RUN.replace(r"\f + \fr 99:16a \fqa Alex. \ft omits these.\f*", "").replace(
        r"\v 17 After.",
        r"\v 17 After.\f + \fr 99:17 \fqa Alex. \ft omits.\f*" "\n" r"\v 18 Last.",
    )
    with pytest.raises(CheckFailed, match="omit them as a run"):
        promoted(decided(policy, {"GEN 99:17": lone}), tail)
    # The run rests on the reading's evidence and reason, and a reading
    # replaces words or omits verses, and pins its note.
    for reading, message in (
        (run_reading(swete=SWETE), "Omission of GEN 99:16a"),
        (
            {key: value for key, value in run_reading().items() if key != "omissions"},
            "needs words or verses to omit: GEN 99:16a",
        ),
        ({**run_reading(), "omissions": []}, "needs words or verses to omit"),
        ({**run_reading(), "lemma": None}, "needs words or verses to omit"),
        (
            {k: v for k, v in run_reading().items() if k != "source_note"},
            "without its source note: GEN 99:16a",
        ),
    ):
        with pytest.raises(CheckFailed, match=message):
            alexandrinus.check(decided(policy, {"GEN 99:16a": reading}), read.brenton)


def test_single_verse_omissions_are_quoted_and_leave_their_paragraph(
    policy: bible.policy.Policy, read: bible.pipeline.Read
) -> None:
    def omission(target: str, home: str, words: str) -> dict[str, Any]:
        return {
            "target": f"GEN 99:{target}",
            "omit_verse": True,
            "note_target": f"GEN 99:{home}",
            "lemma": None,
            "from": words,
            "note": rf"\fl Vat. \ft adds \fq {words.rstrip('.')}\ft .",
            "why": "Alexandrinus lacks the verse.",
            "english": {
                "source": "from",
                "edits": [{"span": [0, len(words)], "to": ""}],
            },
        }

    def passage(*edits: dict[str, Any]) -> dict[str, Any]:
        return {
            "appendix": r"\ip \it Verse\it* 16a. Omitted.",
            "why": "Alexandrinus lacks the verses.",
            "swete": SWETE,
            "edits": list(edits),
        }

    # A verse's own note that does not quote it.
    unquoted = {
        **omission("16b", "16a", "Second addition."),
        "note": r"\fl Vat. \ft adds \fq Second\ft .",
    }
    with pytest.raises(CheckFailed, match="Omission without its note: GEN 99:16b"):
        alexandrinus.check(
            decided(policy, passages={"GEN 99:16b": passage(unquoted)}), read.brenton
        )
    body = RUN.replace(r"\f + \fr 99:16a \fqa Alex. \ft omits these.\f*", "")
    # Consecutive verses, each noted on the one before.
    chain = passage(
        omission("16a", "16", "First addition."),
        omission("16b", "16a", "Second addition."),
    )
    with pytest.raises(CheckFailed, match="omit them as a run"):
        promoted(decided(policy, passages={"GEN 99:16b": chain}), body)
    # A verse that is its paragraph.
    alone = passage(omission("17", "16b", "After."))
    with pytest.raises(CheckFailed, match="empties its paragraph"):
        promoted(decided(policy, passages={"GEN 99:17": alone}), body)


def test_a_passage_supplies_verses_from_the_appendix_or_the_king_james_bible(
    policy: bible.policy.Policy,
) -> None:
    appendix = r"\ip \it Verse\it* 22. And the Philistine \add drew\add* nigh."
    passage = {
        "appendix": appendix,
        "why": "Print the passage.",
        "swete": SWETE,
        "insertions": [
            {
                "after": "99:21",
                "verses": [
                    {
                        "reference": "99:22a",
                        "note": r"\fl Vat. \ft omits this verse.",
                        "english": {"source": "brenton", "span": [22, 61]},
                    }
                ],
            }
        ],
    }
    lines = verse_lines(promoted(decided(policy, passages={"GEN 99:22a": passage})))
    assert list(lines) == ["21", "22a", "22", "23"]
    assert lines["22a"] == (
        r"\f + \cat edition\cat*\fr 99:22a \fl Vat. \ft omits this verse.\f*And the Philistine \add drew\add* nigh."
    )
    borrowed = {
        "kjv": True,
        "why": "The verse is missing.",
        "swete": SWETE,
        "insertions": [{"before": "99:23", "verses": [{"reference": "99:22b"}]}],
    }
    kjv = {"GEN": book("GEN", r"\v 22b Then said \sc David\sc*, Will they?")}
    lines = verse_lines(
        promoted(decided(policy, passages={"GEN 99:22b": borrowed}), kjv=kjv)
    )
    assert list(lines) == ["21", "22", "22b", "23"]
    # Without the King James small capitals, as Brenton has none.
    assert lines["22b"] == "Then said David, Will they?"
    # A note declared without its words is refused by name.
    english = {"source": "brenton", "span": [22, 61]}
    verse = {"reference": "99:22a", "note": None, "english": english}
    unnoted = {**passage, "insertions": [{"after": "99:21", "verses": [verse]}]}
    with pytest.raises(CheckFailed, match="without its note: GEN 99:22a: 99:22a"):
        promoted(decided(policy, passages={"GEN 99:22a": unnoted}))


def test_every_alexandrine_note_and_supplied_passage_has_its_decision(
    policy: bible.policy.Policy, read: bible.pipeline.Read
) -> None:
    assert alexandrinus.check(policy, read.brenton) == (415, 26)
    # A note left without a decision, or a decision without its note, is refused.
    undecided = decided(
        policy,
        {k: v for k, v in policy.alexandrinus["readings"].items() if k != "GEN 3:22"},
        policy.alexandrinus["passages"],
        policy.alexandrinus["kept"],
    )
    with pytest.raises(CheckFailed, match=r"not exhaustive; missing: \['GEN 3:22'\]"):
        alexandrinus.check(undecided, read.brenton)


def test_the_edition_prints_its_readings_and_supplied_passages(
    edition: bible.pipeline.Edition,
) -> None:
    assert (
        r"\v 22 And \f - \cat edition\cat*\fr 3:22 \fq the Lord God said: \ft Valpy omits"
        in usj.serialize(edition.documents["GEN"])
    )
    kingdoms = usj.serialize(edition.documents["1SA"])
    # Supplied from the Authorized Version, with Brenton's form of the name.
    assert (
        r"\v 12 \f - \cat edition\cat*\fr 23:12 \ft Alex. has the verse. Vat. omits; the English is supplied "
        r"from the KJV.\f*Then said David, Will the men of Keila deliver me"
    ) in kingdoms
    # The names the Alexandrine text omits are noted on the verse before.
    assert "\\v 16a" not in usj.serialize(edition.documents["2SA"])
    # The appendix prints nowhere: its passages stand in their books.
    assert "BAK" not in edition.documents
    # Its words stand in the note on the verse, in the edition's own style.
    kingdoms = usj.serialize(edition.documents["1KI"])
    assert (
        r"sea-shore.\f - \cat edition\cat*\fr 2:35a \ft Alex. \ref verses 35a–35b|1KI 2:35a\ref*. Considerable variation here rather than omission\f*"
        in kingdoms
    )
    gloss = next(
        note
        for _, note in scripture.verses(edition.documents["PRO"])["21:16"].notes
        if "Rephaim" in usj.text_of(note["content"])
    )
    assert gloss["category"] == "edition"
    assert any(
        node.get("marker") == "fqa" and usj.text_of(node["content"]) == "Rephaim"
        for node in usj.walk(gloss["content"])
    )
    assert [
        (node["loc"], usj.text_of(node["content"]))
        for node in usj.walk(gloss["content"])
        if node["type"] == "ref"
    ] == [("2SA 5:18", "2 Kgdms. 5:18")]


def test_a_passage_may_omit_a_verse_and_note_it_on_the_verse_before(
    policy: bible.policy.Policy,
) -> None:
    body = r"\v 21 And they were clothed." "\n" r"\v 22 So he sent him forth."
    passage = {
        "appendix": r"\ip \it Verse\it* 21a. And the Lord spoke.",
        "why": "Alexandrinus has the verse here, and lacks 22.",
        "swete": SWETE,
        "insertions": [
            {
                "after": "99:21",
                "verses": [
                    {
                        "reference": "99:21a",
                        "note": r"\fl Vat. \ft omits this verse.",
                        "english": {"source": "brenton", "span": [23, 42]},
                    }
                ],
            }
        ],
        "edits": [
            {
                "target": "GEN 99:22",
                "omit_verse": True,
                "note_target": "GEN 99:21a",
                "lemma": None,
                "from": "So he sent him forth.",
                "note": r"\fl Vat. \ft adds \fq So he sent him forth\ft .",
                "why": "Alexandrinus lacks the verse.",
                "english": {"source": "from", "edits": [{"span": [0, 21], "to": ""}]},
            }
        ],
    }
    lines = verse_lines(
        promoted(decided(policy, passages={"GEN 99:21a": passage}), body)
    )
    assert list(lines) == ["21", "21a"]
    assert lines["21a"] == (
        r"\f + \cat edition\cat*\fr 99:21a \fl Vat. \ft omits this verse.\f*And the Lord spoke."
        r"\f + \cat edition\cat*\fr 99:21a \fl Vat. \ft adds \fq So he sent him forth\ft .\f*"
    )


def test_an_omission_is_noted_by_itself_or_by_a_note_quoting_it(
    policy: bible.policy.Policy, read: bible.pipeline.Read
) -> None:
    omission = {
        "target": "GEN 99:22",
        "omit_verse": True,
        "note_target": "GEN 99:21",
        "lemma": None,
        "from": "So he sent him forth.",
        "note": None,
        "why": "Alexandrinus lacks the verse.",
        "english": {"source": "from", "edits": [{"span": [0, 21], "to": ""}]},
    }

    def passage(*edits: dict[str, Any]) -> dict[str, Any]:
        return {
            "appendix": r"\ip \it Verse\it* 22. Omitted.",
            "why": "Alexandrinus lacks the verse.",
            "swete": SWETE,
            "edits": [omission, *edits],
        }

    def quoting(words: str) -> dict[str, Any]:
        return {
            "target": "GEN 99:21",
            "from": "clothed.",
            "note": rf"\fl Vat. \fq {words}\ft .",
            "why": "The verse ends otherwise.",
            "english": {"source": "from", "edits": [{"span": [7, 8], "to": "!"}]},
        }

    # Neither its own note nor another quoting it, nor one that misquotes it.
    for edits in ((), (quoting("So he went forth"),)):
        with pytest.raises(CheckFailed, match="Omission without its note"):
            alexandrinus.check(
                decided(policy, passages={"GEN 99:22": passage(*edits)}), read.brenton
            )


def test_a_king_james_passage_may_span_verses_and_be_conformed(
    policy: bible.policy.Policy, read: bible.pipeline.Read
) -> None:
    kjv = {
        "GEN": book(
            "GEN",
            r"\v 24 Then said \sc David\sc* in Sarira, Will they?"
            "\n"
            r"\v 25 And the \sc Lord\sc* said, Go to Tirzah.",
        )
    }
    borrowed: dict[str, Any] = {
        "kjv": True,
        "why": "The verses are missing; Alexandrinus reads Sarira at 25.",
        "swete": SWETE,
        "insertions": [
            {
                "after": "99:23",
                "verses": [{"reference": "99:24"}, {"reference": "99:25"}],
            }
        ],
        "edits": [
            {
                "target": "GEN 99:25",
                "from": "Tirzah",
                "note": r"\fl Heb. \fq Tirzah\ft .",
                "why": "Alexandrinus reads Sarira.",
                "english": {
                    "source": "from",
                    "edits": [{"span": [0, 6], "to": "Sarira"}],
                },
            }
        ],
    }
    lines = verse_lines(
        promoted(decided(policy, passages={"GEN 99:24-25": borrowed}), kjv=kjv)
    )
    assert list(lines) == ["21", "22", "23", "24", "25"]
    assert lines["24"] == "Then said David in Sarira, Will they?"
    assert lines["25"] == (
        r"And the Lord said, Go to \f + \cat edition\cat*\fr 99:25 \fl Heb. \fq Tirzah\ft .\f*Sarira."
    )
    # The verses borrowed are those the decision is keyed by, and only they
    # may be conformed.
    short = {
        **borrowed,
        "insertions": [{"after": "99:23", "verses": [{"reference": "99:24"}]}],
    }
    with pytest.raises(CheckFailed, match="must supply the verses it is keyed by"):
        promoted(decided(policy, passages={"GEN 99:24-25": short}), kjv=kjv)
    astray = {**borrowed, "edits": [{**borrowed["edits"][0], "target": "GEN 99:23"}]}
    with pytest.raises(CheckFailed, match="edits a verse it does not supply"):
        alexandrinus.check(
            decided(policy, passages={"GEN 99:24-25": astray}), read.brenton
        )
    # The words displaced are the King James Bible's, never noted as the
    # Vatican's by default.
    unnoted = {
        **borrowed,
        "edits": [{k: v for k, v in borrowed["edits"][0].items() if k != "note"}],
    }
    with pytest.raises(CheckFailed, match="KJV passage edit without its own note"):
        alexandrinus.check(
            decided(policy, passages={"GEN 99:24-25": unnoted}), read.brenton
        )
    # A flag without a label would still name Brenton.
    agreeing = {**unnoted, "edits": [{**unnoted["edits"][0], "hebrew_agrees": True}]}
    with pytest.raises(CheckFailed, match="KJV passage edit without its own note"):
        alexandrinus.check(
            decided(policy, passages={"GEN 99:24-25": agreeing}), read.brenton
        )
    # A structured label is also an explicit attribution; it cannot silently
    # inherit the default Brenton label for words borrowed from the KJV.
    labelled = {**unnoted, "edits": [{**unnoted["edits"][0], "label": "hebrew"}]}
    alexandrinus.check(
        decided(policy, passages={"GEN 99:24-25": labelled}),
        {
            "GEN": book("GEN", r"\v 21 A."),
            "BAK": usj.parse(r"\id BAK" + "\n" + r"\is1 " + alexandrinus.SUPPLIED),
        },
    )
    lines = verse_lines(
        promoted(decided(policy, passages={"GEN 99:24-25": labelled}), kjv=kjv)
    )
    assert r"\fl Heb. \fqa Tirzah\ft ." in lines["25"]


def test_verses_inserted_before_a_paragraph_are_a_paragraph_of_their_own(
    policy: bible.policy.Policy,
) -> None:
    """The verse they stand before keeps its break."""
    kjv = {"GEN": book("GEN", r"\v 20 Then said \add the \+sc Lord\+sc*\add*, Go.")}
    passage: dict[str, Any] = {
        "kjv": True,
        "why": "The verse is missing.",
        "swete": SWETE,
        "insertions": [{"before": "99:21", "verses": [{"reference": "99:20"}]}],
    }
    doc = promoted(decided(policy, passages={"GEN 99:20": passage}), kjv=kjv)
    paragraphs = [b["content"] for b in doc["content"] if usj.is_type(b, "para")]
    numbers = [[i["number"] for i in p if usj.is_type(i, "verse")] for p in paragraphs]
    assert numbers == [["20"], ["21", "22", "23"]]
    # Small capitals go, even within another style.
    assert verse_lines(doc)["20"] == r"Then said \add the Lord\add*, Go."
    # Before a line of verse, a paragraph of prose would not say which it is.
    poem = r"\q1" "\n" r"\v 21 A line." "\n" r"\v 22 B." "\n" r"\v 23 C."
    with pytest.raises(CheckFailed, match="insertion before a q1"):
        promoted(decided(policy, passages={"GEN 99:20": passage}), poem, kjv=kjv)


@pytest.mark.parametrize("label", [None, "vatican"])
def test_a_passage_moves_whole_paragraphs_before_a_verse_and_notes_both_places(
    policy: bible.policy.Policy,
    label: str | None,
) -> None:
    body = r"\v 21 A." "\n" r"\p" "\n" r"\v 22 B." "\n" r"\p" "\n" r"\v 23 C."
    passage: dict[str, Any] = {
        "appendix": r"\ip \it Verse\it* 23. See it placed at the end in the Vatican copy.",
        "why": "Alexandrinus sets 23 before 22.",
        "swete": SWETE,
        "moves": [{"verses": "99:23", "before": "99:22"}],
    }
    if label is not None:
        passage["moves"][0]["label"] = label
    witness = "Vat." if label else "Brenton"
    lines = verse_lines(
        promoted(decided(policy, passages={"GEN 99:23": passage}), body)
    )
    assert list(lines) == ["21", "23", "22"]
    assert (
        lines["23"]
        == rf"\f + \cat edition\cat*\fr 99:23 \fl {witness} \ft has this verse after verse 22.\f*C."
    )
    assert lines["22"] == (
        rf"B.\f + \cat edition\cat*\fr 99:22 \fl {witness} \ft has here the verse printed at 99:23.\f*"
    )
    # A run that does not fill its paragraphs, or that would move later, is refused.
    joined = r"\v 21 A. \v 22 B." "\n" r"\p" "\n" r"\v 23 C."
    together = {
        **passage,
        "moves": [{**passage["moves"][0], "verses": "99:22-23", "before": "99:21"}],
    }
    with pytest.raises(CheckFailed, match="not of whole paragraphs"):
        promoted(decided(policy, passages={"GEN 99:22-23": together}), joined)
    later = {
        **passage,
        "moves": [{**passage["moves"][0], "verses": "99:21", "before": "99:23"}],
    }
    with pytest.raises(CheckFailed, match="not of whole paragraphs"):
        promoted(decided(policy, passages={"GEN 99:21": later}), body)
    # Nor is a heading carried along or left behind by guess.
    headed = body.replace(r"\p" "\n" r"\v 23", r"\s1 C" "\n" r"\p" "\n" r"\v 23")
    with pytest.raises(CheckFailed, match="not of whole paragraphs"):
        promoted(decided(policy, passages={"GEN 99:23": passage}), headed)
    # The verse left behind must be the Vatican's verse before the run.
    gapped = body.replace(r"\v 23", r"\v 24")
    gap = {**passage, "moves": [{"verses": "99:24", "before": "99:22"}]}
    with pytest.raises(CheckFailed, match="no verse before it by number"):
        promoted(decided(policy, passages={"GEN 99:24": gap}), gapped)
    # Nor may the move stand beside a verse a passage inserts.
    beside = {
        "kjv": True,
        "why": "The verse is missing.",
        "swete": SWETE,
        "insertions": [{"before": "99:22", "verses": [{"reference": "99:20"}]}],
    }
    kjv = {"GEN": book("GEN", r"\v 20 Go.")}
    both = {"GEN 99:23": passage, "GEN 99:20": beside}
    with pytest.raises(CheckFailed, match="beside an inserted verse"):
        promoted(decided(policy, passages=both), body, kjv=kjv)


def test_a_passage_omission_removes_all_its_paragraphs_and_pins_its_notes(
    declared: bible.policy.Policy,
) -> None:
    original = book(
        "GEN",
        r"\v 21 Before."
        "\n\\p\n"
        r"\v 21a First \f + \fr 99:21a \ft A source gloss.\f*addition."
        "\n\\p\nIts continuation.\n"
        r"\v 21b Second addition."
        "\n\\p\n"
        r"\v 22 After.",
    )
    snapshot = copy.deepcopy(original)
    omission = {
        "verses": ["99:21a", "99:21b"],
        "note_target": "99:21",
        "note": r"\fl Vat. \ft adds:",
        "source_notes": {"GEN 99:21a": r"\ft A source gloss."},
        "why": "Alexandrinus omits the complete addition.",
        "swete": SWETE,
    }
    policy = decided(declared, passages={"GEN 99:22": {"omissions": [omission]}})
    result = alexandrinus.with_omissions("GEN", original, policy)
    verses = scripture.verses(result)
    assert list(verses) == ["99:21", "99:22"]
    assert verses["99:21"].text == "Before."
    assert verses["99:22"].text == "After."
    # The run follows its introduction, verse by verse, without its notes.
    assert usj.serialize(verses["99:21"].notes[0][1]["content"]) == (
        r"\fr 99:21 \fl Vat. \ft adds: \+fv 21a\+fv*First addition. Its"
        r" continuation. \+fv 21b\+fv*Second addition."
    )
    assert original == snapshot
    for changed_omission, message in (
        (
            {
                **omission,
                "note": r"\fl Vat. \ft adds \fq First addition\ft :",
            },
            "must introduce its verses",
        ),
        (
            {**omission, "note": r"\fl Vat. \ft adds verses 21a–b."},
            "must introduce its verses",
        ),
        (
            {**omission, "note": r"\fl Vat. \ft adds after \+fv 21\+fv* these:"},
            "must introduce its verses",
        ),
        ({**omission, "verses": []}, "Missing or repeated"),
        ({**omission, "verses": ["99:21a", "99:21a"]}, "Missing or repeated"),
        ({**omission, "verses": ["99:21a", "99:25"]}, "Missing or repeated"),
        ({**omission, "verses": ["99:21b", "99:21a"]}, "one run"),
        ({**omission, "verses": ["99:21b"]}, "one run"),
        ({**omission, "source_notes": {}}, "unaccounted source note"),
        (
            {**omission, "source_notes": {"GEN 99:21a": r"\ft Changed."}},
            "source note changed",
        ),
    ):
        policy = decided(
            declared, passages={"GEN 99:22": {"omissions": [changed_omission]}}
        )
        with pytest.raises(CheckFailed, match=message):
            alexandrinus.with_omissions("GEN", original, policy)
    # Reapplying a completed omission is stale, rather than silently accepted.
    with pytest.raises(CheckFailed, match="Missing or repeated"):
        alexandrinus.with_omissions(
            "GEN",
            result,
            decided(declared, passages={"GEN 99:22": {"omissions": [omission]}}),
        )


def test_kingdoms_has_only_the_alexandrine_account(
    edition: bible.pipeline.Edition,
) -> None:
    verses = scripture.verses(edition.documents["1KI"])
    assert not any(label.startswith("12:24") and label != "12:24" for label in verses)
    labels = list(verses)
    assert labels[labels.index("12:24") + 1] == "12:25"
    assert all(f"14:{n}" in verses for n in range(1, 21))
    for reference, phrase in (
        ("14:4", "too old to see"),
        ("14:5", "she feigned herself to be another woman"),
        ("14:8", "to do that which was right"),
        ("14:9", "other gods, molten images"),
        ("14:5", "say to her. And it came to pass"),
        ("14:12", "thy foot entereth"),
        ("14:14", "this day"),
        ("14:15", "from off this good land"),
        ("14:10", "as dung is gathered"),
        ("14:14", "shall smite the house"),
        ("14:15", "the wind is moved in the water"),
        ("14:15", "make an end of Israel"),
        ("14:16", "the Lord shall give Israel up"),
    ):
        assert phrase in verses[reference].text


def test_a_passage_omission_takes_its_blank_lines_and_refuses_a_heading_before_it(
    declared: bible.policy.Policy,
) -> None:
    omission = {
        "verses": ["99:21a", "99:21b"],
        "note_target": "99:21",
        "note": r"\fl Vat. \ft adds:",
        "source_notes": {},
        "why": "Alexandrinus omits the complete addition.",
        "swete": SWETE,
    }
    policy = decided(declared, passages={"GEN 99:22": {"omissions": [omission]}})
    poem = book(
        "GEN",
        r"\v 21 Before."
        "\n\\q1\n"
        r"\v 21a First addition."
        "\n\\b\n\\q1\n"
        r"\v 21b Second addition."
        "\n\\p\n"
        r"\v 22 After.",
    )
    result = alexandrinus.with_omissions("GEN", poem, policy)
    paragraphs = [block for block in result["content"] if block["type"] == "para"]
    assert [block["marker"] for block in paragraphs] == ["p", "p"]
    assert list(scripture.verses(result)) == ["99:21", "99:22"]
    headed = book(
        "GEN",
        r"\v 21 Before."
        "\n\\s1 The addition\n\\p\n"
        r"\v 21a First addition."
        "\n\\p\n"
        r"\v 21b Second addition."
        "\n\\p\n"
        r"\v 22 After.",
    )
    with pytest.raises(CheckFailed, match="crosses a heading"):
        alexandrinus.with_omissions("GEN", headed, policy)


def test_kjv_passage_supplied_vocabulary_uses_original_sources(
    declared: bible.policy.Policy,
) -> None:
    kjv = {"GEN": book("GEN", r"\v 24 Then said David, Go to Tirzah.")}
    original = book("GEN", VERSES + r"\v 24 Sarira.")
    before = copy.deepcopy((original, kjv))
    passage: dict[str, Any] = {
        "kjv": True,
        "why": "Borrow the verse and adapt its place name.",
        "swete": SWETE,
        "supplied": ["Sarira"],
        "supplied_sources": [
            {
                "source": "brenton",
                "reference": "GEN 99:24",
                "why": "The parallel's name.",
            }
        ],
        "insertions": [{"after": "99:23", "verses": [{"reference": "99:24"}]}],
        "edits": [
            {
                "target": "GEN 99:24",
                "from": "Tirzah",
                "note": None,
                "english": {
                    "source": "from",
                    "edits": [{"span": [0, 6], "to": "Sarira"}],
                },
            }
        ],
    }
    # The Brenton evidence can be a verse the passage later omits or replaces;
    # it must be resolved from the original document, before insertion.
    body = book("GEN", VERSES)
    policy = decided(declared, passages={"GEN 99:24": passage})
    result = alexandrinus.promoted("GEN", body, policy, kjv, {"GEN": original})
    assert "Go to Sarira." in verse_lines(result)["24"]
    assert (original, kjv) == before

    # KJV words outside the displaced phrase are evidence too.
    valid = copy.deepcopy(passage)
    valid.pop("supplied_sources")
    valid.pop("supplied")
    valid["edits"][0]["english"]["edits"][0]["to"] = "David"
    assert (
        "Go to David."
        in verse_lines(
            promoted(decided(declared, passages={"GEN 99:24": valid}), kjv=kjv)
        )["24"]
    )

    # They need no declaring, by the passage or by an edit.
    for owner in (valid, valid["edits"][0]):
        bad = copy.deepcopy(valid)
        (bad if owner is valid else bad["edits"][0])["supplied"] = ["david"]
        with pytest.raises(
            CheckFailed, match=r"in the KJV passage: GEN 99:24: \['david'\]"
        ):
            promoted(decided(declared, passages={"GEN 99:24": bad}), kjv=kjv)

    # An allowance the edits inherit is checked.
    bad = copy.deepcopy(valid)
    bad["supplied"] = ["fabricatedword"]
    with pytest.raises(CheckFailed, match="provenance: GEN 99:24.*fabricatedword"):
        promoted(decided(declared, passages={"GEN 99:24": bad}), kjv=kjv)

    # A passage's allowance that every edit overrides, or that has no edit
    # to inherit it, licenses nothing.
    overridden = copy.deepcopy(passage)
    overridden["edits"][0]["supplied"] = ["Sarira"]
    unedited = {k: v for k, v in passage.items() if k != "edits"}
    for bad in (overridden, unedited):
        with pytest.raises(CheckFailed, match="no edit uses: GEN 99:24"):
            alexandrinus.promoted(
                "GEN",
                body,
                decided(declared, passages={"GEN 99:24": bad}),
                kjv,
                {"GEN": original},
            )

    # An edit's own declaration is checked, rather than just the parent's.
    bad = copy.deepcopy(valid)
    bad["edits"][0]["supplied"] = ["fabricatedword"]
    with pytest.raises(CheckFailed, match="provenance: GEN 99:24.*fabricatedword"):
        promoted(decided(declared, passages={"GEN 99:24": bad}), kjv=kjv)

    # A future promoted reading cannot bootstrap its own vocabulary evidence.
    bad = copy.deepcopy(passage)
    bad["supplied_sources"][0]["reference"] = "GEN 99:22"
    reading: dict[str, Any] = copy.deepcopy(dict(READING))
    reading["supplied"] = ["Sarira"]
    reading["english"]["edits"][0]["to"] = " Sarira"
    with pytest.raises(CheckFailed, match="provenance: GEN 99:24.*sarira"):
        promoted(decided(declared, {"GEN 99:22": reading}, {"GEN 99:24": bad}), kjv=kjv)

    # Notes do not supply scripture vocabulary.
    noted = book(
        "GEN", VERSES.replace("clothed.", r"clothed.\f + \fr 99:21 \ft Sarira.\f*")
    )
    bad["supplied_sources"][0]["reference"] = "GEN 99:21"
    with pytest.raises(CheckFailed, match="provenance: GEN 99:24.*sarira"):
        alexandrinus.promoted(
            "GEN",
            noted,
            decided(declared, passages={"GEN 99:24": bad}),
            kjv,
            {"GEN": noted},
        )

    for evidence, message in (
        (
            {"source": "kjv", "reference": "GEN 99:21", "why": "Wrong source."},
            "Malformed",
        ),
        (
            {"source": "brenton", "reference": "GEN 99:21-23", "why": "A range."},
            "Malformed",
        ),
        ({"source": "brenton", "reference": "GEN 99:21", "why": ""}, "Malformed"),
        ({"source": "brenton", "reference": "GEN 99:30", "why": "Missing."}, "missing"),
        (
            {"source": "brenton", "reference": "EXO 99:21", "why": "Missing book."},
            "missing",
        ),
    ):
        bad = {**passage, "supplied_sources": [evidence]}
        with pytest.raises(CheckFailed, match=f"{message}.*GEN 99:24"):
            promoted(decided(declared, passages={"GEN 99:24": bad}), kjv=kjv)
    bad = {**passage, "supplied_sources": []}
    with pytest.raises(CheckFailed, match="Malformed supplied sources: GEN 99:24"):
        promoted(decided(declared, passages={"GEN 99:24": bad}), kjv=kjv)
    # Each source must license a word supplied, or it would go stale unnoticed.
    for extra, message in (
        (passage["supplied_sources"][0], "Duplicate.*GEN 99:24"),
        (
            {"source": "brenton", "reference": "GEN 99:21", "why": "Idle."},
            r"license nothing: GEN 99:24: \['GEN 99:21'\]",
        ),
    ):
        bad = {**passage, "supplied_sources": [*passage["supplied_sources"], extra]}
        with pytest.raises(CheckFailed, match=message):
            alexandrinus.promoted(
                "GEN",
                body,
                decided(declared, passages={"GEN 99:24": bad}),
                kjv,
                {"GEN": original},
            )

    appendix = {k: v for k, v in passage.items() if k != "kjv"}
    appendix["appendix"] = "An Appendix passage."
    with pytest.raises(
        CheckFailed, match="Supplied sources outside a KJV passage: GEN 99:24"
    ):
        alexandrinus.check(
            decided(declared, passages={"GEN 99:24": appendix}), {"GEN": body}
        )
    # The King James words are vocabulary, never a phrase to derive from.
    spliced = copy.deepcopy(passage)
    spliced["edits"][0]["english"] = {"source": "brenton", "span": [0, 10]}
    with pytest.raises(
        CheckFailed, match="not derived from the words it displaces: GEN 99:24"
    ):
        alexandrinus.check(
            decided(declared, passages={"GEN 99:24": spliced}), {"GEN": body}
        )
