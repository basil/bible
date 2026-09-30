"""Declared readings fail closed when their source or audit is damaged."""

from copy import deepcopy
import re

import pytest

from bible import alexandrinus as alex
from bible.alexandrinus_data import expand_decisions
from bible.checks import CheckFailed

HEADING = r"\is1 The Following Passages are Supplied From the Alexandrine Text"
TEXT = (
    "\\id GEN\n\\c 1\n\\v 1 Before \\f + \\fr 1:1 \\fqa Alex. \\ft new.\\f*old after.\n"
)


def exact_english(text, source="brenton", after=None):
    edits = (
        []
        if after is None or after == text
        else [
            {"start": 0, "from": text, "to": after, "why": "Explicit test adaptation."}
        ]
    )
    return {"source": source, "text": text, "edits": edits}


def decision():
    return {
        "from": "old",
        "to": "new",
        "source_notes": {"GEN 1:1": r"\fqa Alex. \ft new."},
        "english": exact_english("new"),
        "why": "A supplies new.",
        "swete": {
            "volume": 1,
            "page": 1,
            "evidence": "apparatus",
            "reading": "new A",
            "agrees": True,
        },
    }


@pytest.fixture
def data(monkeypatch):
    value = {
        "swete": {"1": "Swete I"},
        "readings": {"GEN 1:1": decision()},
        "passages": {},
        "kept": {},
    }
    monkeypatch.setattr(alex, "DATA", value)
    monkeypatch.setattr(
        alex.notes, "corrected_brenton", lambda code, text, record: text
    )
    return value


@pytest.fixture
def normalized():
    return {
        "swete": {"1": "Swete I"},
        "readings": {
            "GEN 1:1": {
                "from": "old",
                "source_note": r"\fqa Alex. \ft new.",
                "english": {"source": "brenton", "span": [15, 18]},
                "why": "A supplies new.",
                "swete": decision()["swete"],
            }
        },
        "passages": {},
        "kept": {},
    }


def test_normalized_derivation_drives_the_printed_words(normalized, monkeypatch):
    entry = normalized["readings"]["GEN 1:1"]
    entry["english"]["edits"] = [{"span": [0, 3], "to": "NEW"}]
    monkeypatch.setattr(alex, "DATA", expand_decisions(normalized))
    result = promote()
    assert "NEW after." in alex.keyed_notes("GEN", result)[0]
    assert "to" not in entry and "text" not in entry["english"]
    assert alex.DATA["readings"]["GEN 1:1"]["english"]["edits"][0] == {
        "start": 0,
        "from": "new",
        "to": "NEW",
        "why": entry["why"],
    }


def test_normalized_caller_uses_offset_in_derived_text(normalized, monkeypatch):
    entry = normalized["readings"]["GEN 1:1"]
    entry["english"]["edits"] = [{"span": [3, 3], "to": " after"}]
    entry["from"] = "old after"
    entry["note_at"] = 4
    monkeypatch.setattr(alex, "DATA", expand_decisions(normalized))
    context = {}
    clean, found = alex.keyed_notes("GEN", promote(context=context))
    assert clean[found[0]["position"] :].startswith("after.")
    assert context["lemmas"]["GEN 1:1"] == "after"


def test_normalized_full_source_deletion_and_reason_override(normalized, monkeypatch):
    entry = normalized["readings"]["GEN 1:1"]
    entry["english"] = {
        "source": "from",
        "edits": [{"span": [0, 3], "to": "", "why": "A omits old."}],
    }
    monkeypatch.setattr(alex, "DATA", expand_decisions(normalized))
    assert "old" not in alex.keyed_notes("GEN", promote())[0]
    assert (
        alex.DATA["readings"]["GEN 1:1"]["english"]["edits"][0]["why"] == "A omits old."
    )


def test_normalized_passage_consumes_snapshot_keys(normalized, monkeypatch):
    reading = normalized["readings"].pop("GEN 1:1")
    paragraph = r"\ip new"
    normalized["passages"]["GEN 1:2"] = {
        "appendix": paragraph,
        "source_notes": {"GEN 1:1": reading["source_note"]},
        "why": reading["why"],
        "swete": reading["swete"],
        "insertions": [
            {
                "after": "1:1",
                "verses": [
                    {
                        "reference": "1:2",
                        "english": {"source": "brenton", "span": [4, 7]},
                    }
                ],
            }
        ],
    }
    monkeypatch.setattr(alex, "DATA", expand_decisions(normalized))
    monkeypatch.setattr(
        alex.notes, "corrected_brenton", lambda code, text, record: text
    )
    assert alex.check_decisions(archives(appendix=HEADING + "\n" + paragraph)) == (1, 1)
    clean, found = alex.keyed_notes("GEN", promote())
    assert "\\v 2 new\n" in clean
    assert found == []


@pytest.mark.parametrize(
    "span", [None, [], [0], [0, 1, 2], [-1, 2], [18, 15], [0, 99], [True, 3], [0, 3.0]]
)
def test_normalized_source_ranges_fail_closed(normalized, span):
    normalized["readings"]["GEN 1:1"]["english"]["span"] = span
    with pytest.raises(CheckFailed, match="source span"):
        expand_decisions(normalized)


@pytest.mark.parametrize(
    "edits",
    [
        [{"span": [0, 2], "to": "x"}, {"span": [1, 3], "to": "y"}],
        [{"span": [0, 4], "to": "x"}],
        [{"span": None, "to": "x"}],
        [{"span": [0, 3], "to": "new"}],
        [{"span": [0, 3], "to": "NEW", "why": ""}],
    ],
)
def test_normalized_invalid_edits_fail_closed(normalized, edits):
    normalized["readings"]["GEN 1:1"]["english"]["edits"] = edits
    with pytest.raises(CheckFailed, match="source span|editorial edit"):
        expand_decisions(normalized)


@pytest.mark.parametrize("at", [-1, 4, True, "0"])
def test_normalized_caller_range_is_checked(normalized, at):
    normalized["readings"]["GEN 1:1"]["note_at"] = at
    with pytest.raises(CheckFailed, match="note position"):
        expand_decisions(normalized)


@pytest.mark.parametrize(
    "damage",
    [
        lambda e: e.update(to="new"),
        lambda e: e.update(book="GEN"),
        lambda e: e.update(consumes=[]),
        lambda e: e.update(source_notes={"GEN 1:1": e["source_note"]}),
        lambda e: e["english"].update(text="new"),
        lambda e: e["english"].update(
            edits=[{"span": [0, 3], "from": "new", "to": "NEW"}]
        ),
    ],
)
def test_normalized_duplicate_representations_are_rejected(normalized, damage):
    damage(normalized["readings"]["GEN 1:1"])
    with pytest.raises(
        CheckFailed, match="Redundant|redundant|malformed|editorial edit"
    ):
        expand_decisions(normalized)


def promote(text=TEXT, context=None):
    return alex.promoted("GEN", text, lambda *args, **kwargs: None, context)


def archives(text=TEXT, appendix=HEADING):
    return {"brenton": {"GEN": text, "BAK": appendix}}


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
def test_number_values(words, expected):
    assert alex.tokens(words) == expected


def test_promotion_retains_other_words_and_demotes_note(data):
    context = {}
    text = promote(context=context)
    clean, notes = alex.keyed_notes("GEN", text)
    assert clean == TEXT.replace(r"\f + \fr 1:1 \fqa Alex. \ft new.\f*", "").replace(
        "old", "new"
    )
    assert notes[0]["body"] == r"\fqa Vat. \ft \+it old\+it*."
    assert context["lemmas"] == {"GEN 1:1": "new"}
    assert alex.check_decisions(archives()) == (1, 0)


@pytest.mark.parametrize(
    "text", [TEXT.replace("Alex.", "Gr."), TEXT.replace(r"\fr 1:1", r"\fr 1:2")]
)
def test_keyed_note_must_exist_and_name_alexandrinus(data, text):
    with pytest.raises(CheckFailed, match="keyed note missing"):
        promote(text)


@pytest.mark.parametrize(
    "text",
    [
        TEXT.replace("old after", "absent after"),
        TEXT.replace("old after", "old old after"),
    ],
)
def test_source_words_must_occur_once_outside_notes(data, text):
    with pytest.raises(CheckFailed, match="from not found once outside notes"):
        promote(text)


def test_invented_english_is_rejected(data):
    data["readings"]["GEN 1:1"]["to"] = "invented"
    with pytest.raises(CheckFailed, match="English not supplied by Brenton"):
        promote()


@pytest.mark.parametrize(
    "damage",
    [
        lambda d: d.pop("swete"),
        lambda d: d["swete"].update(volume=True),
        lambda d: d["swete"].update(page=0),
        lambda d: d["swete"].update(evidence="ocr"),
        lambda d: d["swete"].update(reading=""),
        lambda d: d["swete"].update(agrees=1),
        lambda d: d["swete"].update(unexpected=True),
    ],
)
def test_missing_or_malformed_swete_is_rejected(data, damage):
    damage(data["readings"]["GEN 1:1"])
    with pytest.raises(CheckFailed, match="Malformed Swete record"):
        alex.check_decisions(archives())


@pytest.mark.parametrize("agreement", [False, None])
def test_disagreement_cannot_be_promoted(data, agreement):
    data["readings"]["GEN 1:1"]["swete"]["agrees"] = agreement
    with pytest.raises(CheckFailed, match="Swete does not agree"):
        alex.check_decisions(archives())


def test_supplied_words_require_a_decision_reason(data):
    data["readings"]["GEN 1:1"]["supplied"] = ["invented"]
    data["readings"]["GEN 1:1"]["why"] = ""
    with pytest.raises(CheckFailed, match="decision without a why"):
        alex.check_decisions(archives())


def test_every_alexandrinus_note_needs_a_decision(data):
    data["readings"].clear()
    with pytest.raises(CheckFailed, match="notes not exhaustive"):
        alex.check_decisions(archives())


def test_unused_decision_is_rejected(data):
    data["readings"]["GEN 1:2"] = decision()
    with pytest.raises(CheckFailed, match="notes not exhaustive"):
        alex.check_decisions(archives(text=TEXT + "\\v 2 old after.\n"))


def test_every_appendix_paragraph_needs_a_decision(data):
    with pytest.raises(CheckFailed, match="appendix passages not exhaustive"):
        alex.check_decisions(
            archives(appendix=HEADING + "\n\\ip Unaccounted passage.\n")
        )


def test_appendix_removes_empty_sections_and_logs_cleanup(data):
    text = (
        HEADING + "\n\\is2 EMPTY\n\\ib  \n\\ib\n\\is2 KEPT\n\\ip A retained passage.\n"
    )
    records = []
    result = alex.promoted(
        "BAK", text, lambda operation, **details: records.append((operation, details))
    )
    assert "\\is2 EMPTY" not in result
    assert "\\is2 KEPT\n\\ip A retained passage." in result
    assert records[-1][1]["headings"] == ["\\is2 EMPTY"]


def test_appendix_keeps_populated_sections_and_collapses_blank_paragraphs(data):
    prefix = "\\is2 EARLIER\n\\ib\n\\ib\n"
    text = (
        prefix
        + HEADING
        + "\n\\is2 KEPT\n\\ib\n\\ib  \n\\ip A retained passage.\n\\ib\n\\ib\n"
    )
    result = alex.promoted("BAK", text, lambda *args, **kwargs: None)
    assert "\\is2 KEPT" in result
    assert "\\ip A retained passage." in result
    assert result.startswith(prefix)
    assert result[len(prefix) :].count("\\ib") == 2


def test_overlapping_replacements_are_rejected(data):
    second = deepcopy(decision())
    second.update(
        {
            "from": "old after",
            "to": "new after",
            "source_notes": {"GEN 1:1#2": r"\fqa Alex. \ft new after."},
            "english": exact_english("new after"),
        }
    )
    data["readings"]["GEN 1:1#2"] = second
    text = TEXT.replace(
        "old after", r"old after\f + \fr 1:1 \fqa Alex. \ft new after.\f*"
    )
    with pytest.raises(CheckFailed, match="Overlapping Alexandrine replacements"):
        promote(text)


def test_corruption_outside_declared_span_is_rejected(data, monkeypatch):
    original = alex.place_edits
    monkeypatch.setattr(
        alex,
        "place_edits",
        lambda text, edits: original(text, edits).replace("after", "corrupted"),
    )
    with pytest.raises(CheckFailed, match="changed text outside declared spans"):
        promote()


def test_note_position_defines_lemma_and_preserves_other_note_identity(data):
    data["readings"]["GEN 1:1"].update({"from": "old after", "to": "new {note}after"})
    text = TEXT.replace("Before ", r"Before \x + \xo 1:1 \xt Elsewhere.\x*")
    # The cross-reference is the first keyed note, so consume the original ordinal.
    data["readings"]["GEN 1:1#2"] = data["readings"].pop("GEN 1:1")
    data["readings"]["GEN 1:1#2"]["source_notes"] = {
        "GEN 1:1#2": r"\fqa Alex. \ft new."
    }
    data["readings"]["GEN 1:1#2"]["english"] = exact_english("new", after="new after")
    context = {}
    result = promote(text, context)
    assert context["keys"] == ["GEN 1:1", "GEN 1:1#2"]
    assert context["lemmas"] == {
        "GEN 1:1": {"lemma": None, "glossed": None},
        "GEN 1:1#2": "after",
    }
    assert r"\xt Elsewhere.\x*" in result


def test_alexandrinus_lemma_cannot_also_have_brenton_override(data, monkeypatch):
    context = {}
    text = promote(context=context)
    clean, found = alex.notes.brenton_notes("GEN", text, {}, context["keys"])
    value = deepcopy(alex.notes.BRENTON_NOTES)
    value["notes"] = {
        "GEN 1:1": {"lemma": "Before", "why": "Conflicting old override."}
    }
    monkeypatch.setattr(alex.notes, "BRENTON_NOTES", value)
    with pytest.raises(
        CheckFailed, match="Alexandrine lemma also has a Brenton exception"
    ):
        alex.notes.restyle_brenton_notes(
            "GEN",
            clean,
            found,
            lambda *a, **k: None,
            None,
            set(),
            {},
            context["lemmas"],
        )


@pytest.mark.parametrize(
    "book, reference, words",
    [
        ("1SA", "17:41", "And the Philistine advanced and drew nigh to David"),
        ("PRO", "15:33", "The humble advances in glory."),
    ],
)
def test_promoted_appendix_words_print_once_in_their_book(
    scripture, archives, book, reference, words
):
    from bible.usfm import plain_text, verse_spans

    text = scripture[book]
    verse = next(
        text[start:end] for ref, start, end in verse_spans(text) if ref == reference
    )
    assert words in plain_text(verse)
    assert plain_text(text).count(words) == 1
    appendix = alex.notes.corrected_brenton(
        "BAK", archives["brenton"]["BAK"], lambda *a, **k: None
    )
    appendix = alex.promoted("BAK", appendix, lambda *a, **k: None)
    assert words not in plain_text(appendix)


@pytest.mark.parametrize(
    "replacement",
    [
        r"\v 2 new",
        r"\p new",
        r"\it new\it*",
        r"\+it new\+it*",
        r"\f + \ft new\f*",
    ],
)
def test_replacement_cannot_introduce_unsupported_usfm(data, replacement):
    data["readings"]["GEN 1:1"]["to"] = replacement
    with pytest.raises(CheckFailed, match="Unsupported USFM marker"):
        promote()


def test_replacement_can_retain_added_word_markup(data):
    data["readings"]["GEN 1:1"]["to"] = r"\add new\add*"
    data["readings"]["GEN 1:1"]["english"] = exact_english(
        "new", after=r"\add new\add*"
    )
    clean, _ = alex.keyed_notes("GEN", promote())
    assert r"\add new\add*" in clean


def test_reading_can_make_a_declared_adjacent_punctuation_edit(data):
    data["readings"]["GEN 1:1"]["edits"] = [
        {
            "target": "GEN 1:1",
            "from": " after.",
            "to": ", after.",
            "note": None,
            "english": exact_english(" after.", "from", ", after."),
        }
    ]
    assert alex.check_decisions(archives()) == (1, 0)
    clean, _ = alex.keyed_notes("GEN", promote())
    assert "new, after." in clean


def test_additional_reading_edit_cannot_invent_english(data):
    data["readings"]["GEN 1:1"]["edits"] = [
        {"target": "GEN 1:1", "from": " after.", "to": ", invented.", "note": None}
    ]
    with pytest.raises(CheckFailed, match="English not supplied by Brenton"):
        promote()


def test_additional_reading_edit_must_have_a_real_target(data):
    data["readings"]["GEN 1:1"]["edits"] = [
        {"target": "GEN 1:2", "from": " after.", "to": ", after.", "note": None}
    ]
    with pytest.raises(CheckFailed, match="target verse missing"):
        alex.check_decisions(archives())


def test_omitted_names_are_preserved_at_end_of_previous_verse(scripture, archives):
    from bible import numbering, versification
    from bible.usfm import verse_spans

    clean, found = alex.keyed_notes("2SA", scripture["2SA"])
    spans = {ref: (a, b) for ref, a, b in verse_spans(clean)}
    assert "5:16a" not in spans
    start, end = spans["5:16"]
    assert alex.plain_text(clean[start:end]).endswith("Eliphalath.")
    note = next(n for n in found if "Samae, Jessibath" in n["body"])
    assert note["reference"] == "5:16"
    assert clean[start : note["position"]].rstrip().endswith("Eliphalath.")
    assert alex.DATA["readings"]["2SA 5:16a"]["from"].rstrip(".") in alex.plain_text(
        note["body"]
    )
    inventory = versification.edition_inventory(archives)
    assert "16a" not in inventory["2SA"]["5"]
    rows = numbering.Table("2SA", inventory, numbering.kjv_inventory(archives)).rows()
    assert not any("5:16a" in ours for ours, _ in rows)


def test_seven_day_instructions_keep_corrected_alternative_in_note(scripture):
    from bible.usfm import verse_spans

    clean, found = alex.keyed_notes("NUM", scripture["NUM"])
    verses = {ref: alex.plain_text(clean[a:b]) for ref, a, b in verse_spans(clean)}
    assert "seven days" in verses["28:17"]
    assert "seven days" in verses["28:24"]
    assert "two days" not in verses["28:24"]
    note = next(n for n in found if n["reference"] == "28:24")
    assert "two days" in alex.plain_text(note["body"])
    assert "over an erasure" not in note["body"]


def test_printed_notes_omit_editorial_audit_and_use_requested_labels(scripture):
    from bible.usfm import NOTE, plain_text

    notes = [
        plain_text(n[0]) for text in scripture.values() for n in NOTE.finditer(text)
    ]
    for note in notes:
        assert not re.search(
            r"Swete|over an erasure|correcting hand|Alexandrine margin"
            r"|possible original Alexandrine|recorded Greek difference"
            r"|Vatican Text|[Ss]o the Heb\.|Vat\.\.",
            note,
        )
    assert any("Heb. and Alex." in note for note in notes)
    clean, found = alex.keyed_notes("GEN", scripture["GEN"])
    note = next(n for n in found if n["reference"] == "6:7")
    assert "ἐθυμώθην" not in note["body"]
    assert "Vat." in note["body"]
    assert "I am grieved" in note["body"]
    assert "Gr. I have thought or reasoned" in plain_text(note["body"])
    assert "literally" not in note["body"]


def test_whole_verse_omission_rejects_a_nonadjacent_note_target(monkeypatch, archives):
    data = deepcopy(alex.DATA)
    data["readings"]["2SA 5:16a"]["note_target"] = "2SA 5:15"
    monkeypatch.setattr(alex, "DATA", data)
    with pytest.raises(
        CheckFailed, match="Omission note must attach to the preceding verse"
    ):
        alex.check_decisions(archives)


def test_missing_keila_verse_uses_kjv_verbatim(scripture, archives):
    from bible.usfm import verse_spans

    clean, found = alex.keyed_notes("1SA", scripture["1SA"])
    verse = next(clean[a:b] for ref, a, b in verse_spans(clean) if ref == "23:12")
    # Paragraph markers belong to the surrounding layout, not the borrowed words.
    assert verse.strip().removesuffix(r"\p").strip() == alex.kjv_verse(
        "1SA 23:12", archives
    )
    assert "Verse 12 is here supplied by Alex." not in scripture["1SA"]
    note = next(n for n in found if n["reference"] == "23:12")
    assert "Alex. has the verse" in alex.plain_text(note["body"])
    assert (
        "Vat. omits; the English is supplied from the Authorized Version"
        in note["body"]
    )


@pytest.mark.parametrize(
    "old,new",
    [
        ("Keilah", "Keila"),
        ("hand of Saul", "hands of Saul"),
        ("Then said David", "And David said"),
    ],
)
def test_kjv_supply_rejects_edited_wording(monkeypatch, archives, old, new):
    value = deepcopy(alex.DATA)
    verse = value["passages"]["1SA 23:12"]["insertions"][0]["verses"][0]
    verse["text"] = alex.kjv_verse("1SA 23:12", archives).replace(old, new)
    monkeypatch.setattr(alex, "DATA", value)
    with pytest.raises(CheckFailed, match="Redundant KJV insertion text"):
        alex.check_decisions(archives)


def passage_replacement(data, old, new):
    """Replace a whole marked span without consuming its independent notes."""
    entry = decision()
    data["readings"].clear()
    data["passages"]["GEN 1:1"] = {
        "appendix": "\\ip " + new,
        "why": "Restore the Appendix words with their supplied-word markup.",
        "swete": entry["swete"],
        "edits": [
            {
                "target": "GEN 1:1",
                "from": old,
                "to": new,
                "note": None,
                "english": exact_english(new),
            }
        ],
    }


def test_surviving_note_follows_words_not_markup_spaces_or_ligature_lengths(data):
    old = r"\add Jessae  ﬂed to the camp, ﬁrst in line. \add*"
    new = r"Jessæ fled to the camp, \add first\add* in line."
    passage_replacement(data, old, new)
    body = r"\ft \+it Gr. \+it* foremost. "
    text = (
        "\\id GEN\n\\c 1\n\\v 1 "
        + old.replace("ﬁrst", "\\f + \\fr 1:1 " + body + "\\f*ﬁrst")
        + "\n"
    )
    context = {}
    clean, found = alex.keyed_notes("GEN", promote(text, context))
    assert found[0]["body"] == body
    assert clean == "\\id GEN\n\\c 1\n\\v 1 " + new + "\n"
    assert clean[found[0]["position"] :].startswith("first\\add*")
    assert context["lemmas"]["GEN 1:1"] == {"lemma": "ﬁrst", "glossed": "ﬁrst"}


@pytest.mark.parametrize("new", ["Before after.", "Before target and target after."])
def test_surviving_note_rejects_absent_or_ambiguous_phrase(data, new):
    old = r"\add Before target after. \add*"
    passage_replacement(data, old, new)
    text = (
        "\\id GEN\n\\c 1\n\\v 1 "
        + old.replace("target", r"\f + \fr 1:1 \ft Gr. other.\f*target")
        + "\n"
    )
    with pytest.raises(CheckFailed, match="Surviving note lemma not anchored once"):
        promote(text)


def test_surviving_note_validates_original_exception_before_preserving_it(
    data, monkeypatch
):
    old = r"\add Before target after. \add*"
    passage_replacement(data, old, "Before target after.")
    text = (
        "\\id GEN\n\\c 1\n\\v 1 "
        + old.replace("target", r"\f + \fr 1:1 \ft Gr. other.\f*target")
        + "\n"
    )
    configuration = deepcopy(alex.notes.BRENTON_NOTES)
    configuration["notes"] = {
        "GEN 1:1": {"lemma": "target after", "why": "The gloss covers both words."}
    }
    monkeypatch.setattr(alex.notes, "BRENTON_NOTES", configuration)
    context = {}
    promote(text, context)
    assert context["lemmas"]["GEN 1:1"] == {
        "lemma": "target after",
        "glossed": "target after",
    }
    configuration["notes"]["GEN 1:1"]["lemma"] = "absent"
    with pytest.raises(CheckFailed, match="Lemma override not found exactly once"):
        promote(text)


def test_surviving_note_preserves_widened_lemma_and_smaller_gloss(data):
    old = r"\add Before target and target after. \add*"
    new = "Before first and target after."
    passage_replacement(data, old, new)
    body = r"\ft Gr. other."
    text = (
        "\\id GEN\n\\c 1\n\\v 1 "
        + old.replace("and target", "and \\f + \\fr 1:1 " + body + "\\f*target")
        + "\n"
    )
    context = {}
    _, found = alex.keyed_notes("GEN", promote(text, context))
    assert found[0]["body"] == body
    # The original repeated word needed context in the printed lemma. That
    # context must not become part of the smaller literal rendering's anchor.
    assert context["lemmas"]["GEN 1:1"] == {
        "lemma": "target after",
        "glossed": "target",
    }


SURVIVING_SAMUEL_NOTES = [
    ("17:13", "names", "Gr. name"),
    ("17:14", "was", "Gr. is"),
    ("17:15", "to feed", "Gr. feeding"),
    ("17:18", "these ten cheeses of milk", "lit. the ten cheeses of this milk"),
    ("17:23", "as before", "Gr. according to these words"),
    ("17:29", "Have I no business here", "Gr. is there not a word?"),
    ("17:30", "after the former manner", "lit. according to the word of the first"),
    ("17:31", "to Saul", "Gr. behind Saul"),
]


def test_eight_samuel_glosses_keep_source_bodies_and_complete_word_anchors(archives):
    from bible.usfm import verse_spans, word_spans

    source = alex.notes.corrected_brenton(
        "1SA", archives["brenton"]["1SA"], lambda *a, **k: None
    )
    _, original = alex.keyed_notes("1SA", source)
    context = {}
    result = alex.promoted("1SA", source, lambda *a, **k: None, context)
    clean, found = alex.keyed_notes("1SA", result)
    by_key = dict(zip(context["keys"], found))
    source_by_key = {n["key"]: n for n in original}
    spans = {ref: (a, b) for ref, a, b in verse_spans(clean)}
    for ref, lemma, _ in SURVIVING_SAMUEL_NOTES:
        key = "1SA " + ref
        note = by_key[key]
        assert note["body"] == source_by_key[key]["body"]
        assert context["lemmas"][key] == {"lemma": lemma, "glossed": lemma}
        start, end = spans[ref]
        words = word_spans(clean[start:end])
        hit = next(
            i for i, (_, at, _) in enumerate(words) if at + start == note["position"]
        )
        assert [
            w for w, _, _ in words[hit : hit + len(alex.words_of(lemma))]
        ] == alex.words_of(lemma)


@pytest.mark.parametrize("reference,lemma,body", SURVIVING_SAMUEL_NOTES)
def test_eight_samuel_printed_notes_retain_their_full_lemmas_and_glosses(
    scripture, reference, lemma, body
):
    from bible.usfm import plain_text

    found = [
        m
        for m in alex.notes.BRENTON_NOTE.finditer(scripture["1SA"])
        if m[2] == reference
    ]
    assert len(found) == 1
    assert found[0][3].startswith("\\fq " + lemma + ": ")
    printed_body = re.sub(r"^\\fq .*?: ", "", found[0][3])
    assert plain_text(printed_body) == body


def companion_rewrite(data):
    body = r"\ft Gr. length old."
    text = TEXT.replace("old after", "old after\\f + \\fr 1:1 " + body + "\\f*")
    data["readings"]["GEN 1:1"]["note_edits"] = [
        {
            "key": "GEN 1:1#2",
            "from": body,
            "to": r"\ft Vatican Greek, literally, length old.",
            "lemma": "new",
            "why": "The Greek belongs to the displaced reading.",
        }
    ]
    return text, body


def test_companion_note_rewrite_is_explicit_separate_and_audited(data):
    text, body = companion_rewrite(data)
    records, context = [], {}
    assert alex.check_decisions(archives(text)) == (1, 0)
    result = alex.promoted(
        "GEN",
        text,
        lambda operation, **details: records.append((operation, details)),
        context,
    )
    clean, found = alex.keyed_notes("GEN", result)
    by_key = dict(zip(context["keys"], found))
    assert "new after" in clean
    assert by_key["GEN 1:1#2"]["body"] == r"\ft Vatican Greek, literally, length old."
    assert by_key["GEN 1:1"]["body"].startswith(r"\fqa Vat.")
    assert context["lemmas"] == {"GEN 1:1": "new", "GEN 1:1#2": "new"}
    operation, record = next(r for r in records if r[0].startswith("rewrite companion"))
    assert record["key"] == "GEN 1:1#2"
    assert record["from"] == body
    assert record["why"] == "The Greek belongs to the displaced reading."


def test_companion_note_rewrite_fails_if_source_body_changes(data):
    text, body = companion_rewrite(data)
    text = text.replace(body, body + " changed")
    with pytest.raises(CheckFailed, match="Companion note source changed"):
        promote(text)
    with pytest.raises(CheckFailed, match="Companion note source changed"):
        alex.check_decisions(archives(text))


@pytest.mark.parametrize("conflict", ["duplicate", "consumed", "missing"])
def test_companion_note_rewrite_conflicts_fail_closed(data, conflict):
    text, _ = companion_rewrite(data)
    edits = data["readings"]["GEN 1:1"]["note_edits"]
    if conflict == "duplicate":
        edits.append(deepcopy(edits[0]))
    elif conflict == "consumed":
        edits[0]["key"] = "GEN 1:1"
    else:
        edits[0]["key"] = "GEN 1:2"
    with pytest.raises(
        CheckFailed, match="Companion note missing|Conflicting companion"
    ):
        promote(text)


@pytest.mark.parametrize(
    "after",
    [
        "after new new",
        "new after",
        "new after new new",
        "new after new.",
        "New after new",
        "new  after new",
    ],
)
def test_same_vocabulary_cannot_drift_in_order_count_or_typography(after):
    entry = {"english": exact_english("new after new")}
    with pytest.raises(CheckFailed, match="English differs from exact derivation"):
        alex.check_english("GEN 1:1", entry, "new after new", "", after)


def test_number_spelling_requires_an_explicit_edit():
    entry = {"english": exact_english("187 years")}
    after = "an hundred and eighty and seven years"
    with pytest.raises(CheckFailed, match="English differs from exact derivation"):
        alex.check_english("GEN 1:1", entry, "187 years", "", after)
    entry["english"] = exact_english("187 years", after=after)
    alex.check_english("GEN 1:1", entry, "187 years", "", after)


@pytest.mark.parametrize(
    "run",
    [lambda text: promote(text), lambda text: alex.check_decisions(archives(text))],
)
def test_complete_note_snapshot_rejects_same_vocabulary_changes(data, run):
    with pytest.raises(CheckFailed, match="Alexandrine source note changed"):
        run(TEXT.replace("new.", "new new."))


def test_snapshot_is_required_even_if_source_phrase_still_matches(data):
    data["readings"]["GEN 1:1"].pop("source_notes")
    with pytest.raises(CheckFailed, match="source note snapshots"):
        promote()


def test_retained_note_is_pinned_too(data):
    entry = data["readings"].pop("GEN 1:1")
    data["kept"]["GEN 1:1"] = {k: entry[k] for k in ("why", "swete", "source_notes")}
    with pytest.raises(CheckFailed, match="Alexandrine source note changed"):
        promote(TEXT.replace("new.", "new new."))


@pytest.mark.parametrize(
    "damage",
    [
        lambda e: e.pop("english"),
        lambda e: e["english"].update(source="other"),
        lambda e: e["english"].update(source=[]),
        lambda e: e["english"].update(text="absent"),
        lambda e: e["english"].update(
            edits=[{"start": 0, "from": "wrong", "to": "new", "why": "Test."}]
        ),
        lambda e: e["english"].update(
            edits=[{"start": 0, "from": "new", "to": "new.", "why": ""}]
        ),
        lambda e: e["english"].update(
            edits=[{"start": True, "from": "", "to": ".", "why": "Test."}]
        ),
    ],
)
def test_missing_or_damaged_derivation_fails_closed(data, damage):
    damage(data["readings"]["GEN 1:1"])
    with pytest.raises(CheckFailed, match="derivation|source phrase|editorial edit"):
        promote()


def test_supplied_words_do_not_bypass_exact_derivation(data):
    entry = data["readings"]["GEN 1:1"]
    entry.update(to="new invented", supplied=["invented"])
    with pytest.raises(CheckFailed, match="English differs from exact derivation"):
        promote()


def test_additional_edit_cannot_inherit_parent_derivation(data):
    data["readings"]["GEN 1:1"]["edits"] = [
        {"target": "GEN 1:1", "from": " after.", "to": ", after.", "note": None}
    ]
    with pytest.raises(CheckFailed, match="exact English derivation"):
        promote()


def test_real_genesis_reordering_rejected(patched, archives):
    data = patched(alex, "DATA")
    data["readings"]["GEN 3:22"]["to"] = "God Lord the said"
    with pytest.raises(
        CheckFailed, match="English differs from exact derivation: GEN 3:22"
    ):
        alex.check_decisions(archives)


def test_real_appendix_insertion_omission_rejected(patched, archives):
    data = patched(alex, "DATA")
    entry = next(
        e for e in data["passages"].values() if "appendix" in e and e.get("insertions")
    )
    verse = entry["insertions"][0]["verses"][0]
    verse["text"] = verse["text"].split(" ", 1)[1]
    with pytest.raises(CheckFailed, match="English differs from exact derivation"):
        alex.check_decisions(archives)
