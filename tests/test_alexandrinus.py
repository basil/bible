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
        r"And \f - \fr 99:22 \fq the Lord God said: \ft Vat. omits “the Lord”\f*the Lord God said,"
    )


def test_a_reading_without_a_note_of_its_own_quotes_the_vatican_words(
    policy: bible.policy.Policy,
) -> None:
    reading = {k: v for k, v in READING.items() if k != "note"}
    doc = promoted(decided(policy, {"GEN 99:22": reading}))
    assert r"\fl Vat. \fq God said\ft ." in verse_lines(doc)["22"]


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
        "why": "The verse is wanting.",
        "swete": SWETE,
        "insertions": [{"before": "99:23", "verses": [{"reference": "99:22b"}]}],
    }
    kjv = {"GEN": book("GEN", r"\v 22b Then said \sc David\sc*, Will they?")}
    lines = verse_lines(
        promoted(decided(policy, passages={"GEN 99:22b": borrowed}), kjv=kjv)
    )
    assert list(lines) == ["21", "22", "22b", "23"]
    assert lines["22b"] == r"Then said \sc David\sc*, Will they?"
    # A note declared without its words is refused by name.
    english = {"source": "brenton", "span": [22, 61]}
    verse = {"reference": "99:22a", "note": None, "english": english}
    unnoted = {**passage, "insertions": [{"after": "99:21", "verses": [verse]}]}
    with pytest.raises(CheckFailed, match="without its note: GEN 99:22a: 99:22a"):
        promoted(decided(policy, passages={"GEN 99:22a": unnoted}))


def test_every_alexandrine_note_and_supplied_passage_has_its_decision(
    policy: bible.policy.Policy, read: bible.pipeline.Read
) -> None:
    assert alexandrinus.check(policy, read.brenton) == (198, 26)
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
        r"\v 22 And \f - \fr 3:22 \fq the Lord God said: \ft Vat. omits"
        in usj.serialize(edition.documents["GEN"])
    )
    kingdoms = usj.serialize(edition.documents["1SA"])
    # Supplied verbatim from the Authorized Version, whose small capitals it keeps.
    assert (
        r"\v 12 \f - \fr 23:12 \ft Alex. has the verse. Vat. omits; the English is supplied "
        r"from the Authorized Version\f*Then said David, Will the men of Keilah deliver me"
    ) in kingdoms
    # The names the Alexandrine text omits are noted on the verse before.
    assert "\\v 16a" not in usj.serialize(edition.documents["2SA"])
    # What the edition promotes leaves the appendix; what it keeps stays.
    appendix = usj.serialize(edition.documents["BAK"])
    assert "And the Philistine advanced and drew nigh" not in appendix
    assert "Considerable variation here rather than omission" in appendix
