"""The Alexandrine readings: declared, derived from Brenton's words, and
carried out on his books before anything else reads them."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from conftest import book, changed, verse_lines

import bible.annotate
import bible.pipeline
import bible.policy
from bible import alexandrinus, annotate, scripture, usj
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
    return alexandrinus.promoted("GEN", book("GEN", body), policy, kjv or {})


def test_a_reading_replaces_the_vatican_words_and_notes_them(
    policy: bible.policy.Policy, ctx: bible.annotate.Context
) -> None:
    doc = promoted(decided(policy, {"GEN 99:22": READING}))
    assert verse_lines(doc)["22"] == (
        r"And \f + \fr 99:22 \fl Vat. \ft omits “the Lord”.\f*the Lord God said, Behold, "
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
        r"And \f - \fr 99:22 \fq the Lord God said: \ft Vat. omits \fqa the Lord\f*the Lord God said,"
    )


def test_a_reading_without_a_note_of_its_own_quotes_brentons_words(
    policy: bible.policy.Policy,
) -> None:
    reading = {k: v for k, v in READING.items() if k != "note"}
    doc = promoted(decided(policy, {"GEN 99:22": reading}))
    assert r"\fl Brenton \fq God said\ft ." in verse_lines(doc)["22"]


def test_a_reading_without_a_note_names_the_witness_its_label_declares(
    policy: bible.policy.Policy,
) -> None:
    reading = {k: v for k, v in READING.items() if k != "note"} | {"label": "vatican"}
    doc = promoted(decided(policy, {"GEN 99:22": reading}))
    assert r"\fl Vat. \fq God said\ft ." in verse_lines(doc)["22"]


@pytest.mark.parametrize(
    "label,message",
    [("brenton", "label changes nothing"), ("vatican", "label beside a note")],
)
def test_a_reading_label_must_change_something_and_stand_alone(
    policy: bible.policy.Policy, label: str, message: str
) -> None:
    reading = dict(READING) | {"label": label}
    if label == "brenton":
        del reading["note"]
    with pytest.raises(CheckFailed, match=message):
        promoted(decided(policy, {"GEN 99:22": reading}))


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
    with pytest.raises(CheckFailed, match="English not supplied by Brenton"):
        alexandrinus.derived("key", supplied, NOTE)
    assert (
        alexandrinus.derived("key", supplied, NOTE, ["Almighty"])
        == r"\add Almighty\add* God said"
    )
    # Brenton's numbers may be spelt out, whichever way he wrote them.
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
        == r"And Elisama, and Eliphalath.\f + \fr 99:16 \fl Vat. \ft adds \fq Samae, Nathan\ft .\f*"
    )


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
        r"\f + \fr 99:22a \fl Vat. \ft omits this verse.\f*And the Philistine \add drew\add* nigh."
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
        r"\v 22 And \f - \fr 3:22 \fq the Lord God said: \ft Brenton omits"
        in usj.serialize(edition.documents["GEN"])
    )
    kingdoms = usj.serialize(edition.documents["1SA"])
    # Supplied from the Authorized Version, with Brenton's form of the name.
    assert (
        r"\v 12 \f - \fr 23:12 \ft Alex. has the verse. Vat. omits; the English is supplied "
        r"from the KJV.\f*Then said David, Will the men of Keila deliver me"
    ) in kingdoms
    # The names the Alexandrine text omits are noted on the verse before.
    assert "\\v 16a" not in usj.serialize(edition.documents["2SA"])
    # The appendix prints nowhere: its passages stand in their books.
    assert "BAK" not in edition.documents
    # Its words stand in the note on the verse, in the edition's own style.
    kingdoms = usj.serialize(edition.documents["1KI"])
    assert (
        r"\v 35a \f - \fr 2:35a \ft Alex. Considerable variation here rather than omission\f*and"
        in kingdoms
    )
    proverbs = usj.serialize(edition.documents["PRO"])
    assert (
        r"\fq giants: \ft Heb. \fqa Rephaim\ft . See note on \xt 2 Kgdms. 5:18\f*giants"
        in proverbs
    )


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
        r"\f + \fr 99:21a \fl Vat. \ft omits this verse.\f*And the Lord spoke."
        r"\f + \fr 99:21a \fl Vat. \ft adds \fq So he sent him forth\ft .\f*"
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
            r"\v 24 Then said \sc David\sc*, Will they?"
            "\n"
            r"\v 25 And the \sc Lord\sc* said, Go to Tirzah.",
        )
    }
    borrowed: dict[str, Any] = {
        "kjv": True,
        "why": "The verses are missing; Alexandrinus reads Sarira at 25.",
        "swete": SWETE,
        "supplied": ["Sarira"],
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
    assert lines["24"] == "Then said David, Will they?"
    assert lines["25"] == (
        r"And the Lord said, Go to \f + \fr 99:25 \fl Heb. \fq Tirzah\ft .\f*Sarira."
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
        == rf"\f + \fr 99:23 \fl {witness} \ft has this verse after verse 22.\f*C."
    )
    assert lines["22"] == (
        rf"B.\f + \fr 99:22 \fl {witness} \ft has here the verse printed at 99:23.\f*"
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
