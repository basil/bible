"""The RV and Boyd's ASV as witnesses, on real verses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pytest

from bible.byzantine import BOYD_ASV, RV, revisers
from bible.byzantine.greek import PATCHES
from bible.byzantine.instructions import bind_plain
from bible.byzantine.rows import BoydNote, Instruction, InstructionEdit, Unit
from bible.byzantine.units import NEUTRAL_CLASSES


@pytest.fixture(scope="module")
def texts(byzantine: Mapping[str, Any]) -> Mapping[str, Mapping[str, str]]:
    return cast(Mapping[str, Mapping[str, str]], byzantine["texts"])


def test_asv_reads_its_poetry_and_indented_paragraphs(
    texts: Mapping[str, Mapping[str, str]],
) -> None:
    assert texts["asv"]["1TI 3:16"].endswith("Received up in glory.")
    assert texts["asv"]["REV 4:11"].startswith("Worthy art thou, our Lord and our God")


def test_spellings_and_compounds_compare_as_the_older_form(
    kjv_text: Mapping[str, str],
) -> None:
    assert "forever" in [w for w, *_ in revisers.comparable(kjv_text["1PE 1:25"])]
    assert [w for w, *_ in revisers.comparable("And straightaway coming up")] == [
        w for w, *_ in revisers.comparable("And straightway coming up")
    ]
    assert [
        (w, first, stop)
        for w, first, stop, *_ in revisers.comparable("endureth for ever. And this")
    ] == [("endureth", 0, 1), ("forever", 1, 3), ("and", 3, 4), ("this", 4, 5)]
    assert [w for w, *_ in revisers.comparable("Asher and Manasseh")] == [
        "aser",
        "and",
        "manasses",
    ]


def test_changes_quote_each_source_and_count_kjv_words(
    kjv_text: Mapping[str, str], texts: Mapping[str, Mapping[str, str]]
) -> None:
    found = list(revisers.changes(kjv_text["MAT 3:8"], texts[BOYD_ASV]["MAT 3:8"]))
    assert [(c["old"], c["new"], c["word_range"], c["kind"]) for c in found] == [
        ("fruits meet for", "fruit worthy of", [3, 6], "replace")
    ]
    found = list(revisers.changes(kjv_text["MAT 21:7"], texts[RV]["MAT 21:7"]))
    assert [(c["old"], c["new"], c["word_range"]) for c in found] == [
        ("clothes", "garments", [12, 13]),
        ("they set him", "he sat", [14, 17]),
    ]
    added = list(
        revisers.changes(
            "the death, the lake of fire.", "the second death, the lake of fire."
        )
    )
    assert [(c["kind"], c["new"], c["side"], c["word_range"]) for c in added] == [
        ("insert", "second", "after", [1, 1])
    ]
    stop = list(revisers.changes("the death. And", "the death, even the lake. And"))
    assert [(c["kind"], c["new"], c["side"]) for c in stop] == [
        ("insert", "even the lake", "after")
    ]


def test_westcott_hort_side_from_boyd_sigla() -> None:
    unit: Unit = {"inventories": [{"inventory": "tcgnt", "entry": 1}]}
    note: BoydNote = {
        "variants": [
            {"reading": "δαβιδ", "sigla": ["HF", "TR"]},
            {"reading": "δαυειδ", "sigla": ["TH", "WH"]},
        ]
    }
    assert revisers.wh_side(unit, {1: note}) == "other"
    note = {"variants": [{"reading": "καρπους αξιους", "sigla": ["TR"]}]}
    assert revisers.wh_side(unit, {1: note}) == "RP"
    note = {"variants": [{"reading": "υπο κρισιν", "sigla": ["CT", "SCR"]}]}
    assert revisers.wh_side(unit, {1: note}) == "TR"
    assert revisers.wh_side({"inventories": []}, {}) is None


def test_readable_units_follow_westcott_hort_and_the_patches(
    units: list[Unit], byzantine: Mapping[str, Any]
) -> None:
    admitted = revisers.readable(units, byzantine["tcgnt"])
    assert "MAT 3:8#1" in admitted[RV] and "MAT 3:8#1" in admitted[BOYD_ASV]
    patched = {u["id"] for u in units if u["ref"] in PATCHES}
    assert patched and not patched & admitted[BOYD_ASV]
    assert "PHM 1:1#1" in patched
    assert len(admitted[RV]) < len(admitted[BOYD_ASV]) < len(units)


def test_boyd_own_change_attaches_to_its_unit(
    kjv_text: Mapping[str, str],
    texts: Mapping[str, Mapping[str, str]],
    byzantine: Mapping[str, Any],
) -> None:
    # ACT 21:33: TR τοτε εγγισας, RP εγγισας δε. Boyd changed the ASV's "Then"
    # to "And"; the ASV's other differences from the KJV are style.
    units: list[Unit] = [
        {
            "id": "ACT 21:33#1",
            "ref": "ACT 21:33",
            "tr": ["tote", "eggisas"],
            "rp": ["eggisas", "de"],
            "tr_range": [0, 2],
            "rp_range": [0, 2],
            "hf": "RP",
            "class": "substitution",
        }
    ]
    rows = revisers.revision_reports(
        BOYD_ASV,
        kjv_text,
        texts[BOYD_ASV],
        byzantine["aligned"],
        units,
        {"ACT 21:33#1"},
        base=texts["asv"],
    )
    assert [
        (r["old"], r["new"], r["reviser"], r["units"][0]["unit"], r["method"])
        for r in rows
    ] == [("Then", "And", "revised", "ACT 21:33#1", "aligned")]
    assert rows[0]["entry"] == "ACT 21:33#1"
    assert (
        revisers.revision_reports(
            BOYD_ASV,
            kjv_text,
            texts[BOYD_ASV],
            byzantine["aligned"],
            units,
            set(),
            base=texts["asv"],
        )
        == []
    )


def test_boyd_is_read_at_rps_address(
    kjv_text: Mapping[str, str],
    texts: Mapping[str, Mapping[str, str]],
    byzantine: Mapping[str, Any],
) -> None:
    # Boyd's MAT 23:13 is the KJV's 23:14, "devour widows' houses"; his 23:14
    # is the KJV's 23:13, "shut up the kingdom of heaven".
    assert "the kingdom of heaven against men" in texts[BOYD_ASV]["MAT 23:13"]
    assert "devour" not in texts[BOYD_ASV]["MAT 23:13"]
    moved = revisers.at_kjv_addresses(
        {"MAT 23:13": "a", "MAT 23:14": "b", "ROM 14:24": "c"},
        {"MAT 23:13": "", "MAT 23:14": "", "ROM 16:25": "", "ROM 16:26": ""},
        byzantine["structure"],
    )
    assert moved == {
        "MAT 23:13": "b",
        "MAT 23:14": "a",
        "ROM 16:25": "c",
        "ROM 16:26": "",
    }
    ref = "MAT 23:13"
    units: list[Unit] = [
        {
            "id": ref + "#1",
            "ref": ref,
            "tr": ["x"],
            "rp": ["y"],
            "tr_range": [0, byzantine["aligned"][ref]["greek_length"]],
            "rp_range": [0, 1],
            "hf": "RP",
            "class": "substitution",
        }
    ]
    rows = revisers.revision_reports(
        BOYD_ASV,
        kjv_text,
        texts[BOYD_ASV],
        byzantine["aligned"],
        units,
        {ref + "#1"},
        base=texts["asv"],
    )
    assert rows and not [r for r in rows if "devour" in r["new"]]


def test_a_change_making_a_placed_instructions_contrast_takes_its_unit(
    kjv_text: Mapping[str, str],
    texts: Mapping[str, Mapping[str, str]],
    byzantine: Mapping[str, Any],
) -> None:
    # MAT 21:7 επεκαθισαν -> επεκαθισεν: CrossWire does not carry "they set
    # him" onto the verb; an instruction placed there lends its unit to the
    # RV's "he sat" on the same words.
    ref = "MAT 21:7"
    units: list[Unit] = [
        {
            "id": ref + "#1",
            "ref": ref,
            "tr": ["epekaqisan"],
            "rp": ["epekaqisen"],
            "tr_range": [14, 15],
            "rp_range": [14, 15],
            "hf": "RP",
            "class": "inflection",
        }
    ]
    edit: InstructionEdit = {
        "kind": "replace",
        "ref": ref,
        "word_range": [14, 17],
        "old": "they set him",
        "new": "he sat",
        "units": [ref + "#1"],
        "scope": "unit",
    }
    instruction: Instruction = {
        "source": "additional",
        "scope": "greek",
        "edits": [edit],
    }

    def read(instructions: list[Instruction]) -> list[tuple[str, str, str]]:
        rows = revisers.revision_reports(
            RV,
            kjv_text,
            texts[RV],
            byzantine["aligned"],
            units,
            {ref + "#1"},
            instructions=instructions,
        )
        return [(r["old"], r["new"], r["method"]) for r in rows]

    assert read([]) == []
    assert read([instruction]) == [("they set him", "he sat", "english")]
    assert read([{**instruction, "edits": [{**edit, "new": "he set"}]}]) == []
    assert read([{**instruction, "scope": "verse"}]) == []


def test_agreeing_instructions_do_not_hide_revision_reports(
    kjv_text: Mapping[str, str],
    texts: Mapping[str, Mapping[str, str]],
    byzantine: Mapping[str, Any],
) -> None:
    # Two instructions place "he sat" on the singular RP verb.
    # CrossWire cannot place these KJV words, so the English fallback must
    # count their shared attachment once rather than call it ambiguous.
    instructions: list[Instruction] = [
        i for i in byzantine["instructions"] if i["ref"] == "MAT 21:7"
    ]
    assert {i["source"] for i in instructions} == {"pierpont"}
    instructions = [
        *instructions,
        {**instructions[0], "source": "additional", "entry": 1},
    ]
    ledger = [u for u in byzantine["units"] if u["ref"] == "MAT 21:7"]
    admitted = revisers.readable(ledger, byzantine["tcgnt"])
    for witness in (RV, BOYD_ASV):
        rows = revisers.revision_reports(
            witness,
            kjv_text,
            texts[witness],
            byzantine["aligned"],
            ledger,
            admitted[witness],
            instructions=instructions,
        )
        assert [(r["old"], r["new"], r["method"], r["units"]) for r in rows] == [
            (
                "they set him",
                "he sat",
                "english",
                [{"unit": "MAT 21:7#1", "scope": "constituent"}],
            )
        ]
        # Repeating evidence cannot change an attachment.
        assert rows == revisers.revision_reports(
            witness,
            kjv_text,
            texts[witness],
            byzantine["aligned"],
            ledger,
            admitted[witness],
            instructions=instructions * 2,
        )


def test_different_units_with_the_same_contrast_remain_ambiguous(
    kjv_text: Mapping[str, str],
    texts: Mapping[str, Mapping[str, str]],
    byzantine: Mapping[str, Any],
) -> None:
    original: Unit = next(u for u in byzantine["units"] if u["id"] == "MAT 21:7#1")
    other: Unit = {**original, "id": "MAT 21:7#ambiguous"}
    source: Instruction = next(
        i
        for i in byzantine["instructions"]
        if i["ref"] == "MAT 21:7" and i["source"] == "pierpont"
    )
    competing: Instruction = {
        **source,
        "edits": [{**e, "units": [other["id"]]} for e in source["edits"]],
    }
    assert (
        revisers.revision_reports(
            RV,
            kjv_text,
            texts[RV],
            byzantine["aligned"],
            [original, other],
            {original["id"], other["id"]},
            instructions=[source, source, competing],
        )
        == []
    )


def test_revision_change_on_a_neutral_unit_is_not_read(
    kjv_text: Mapping[str, str],
    texts: Mapping[str, Mapping[str, str]],
    byzantine: Mapping[str, Any],
) -> None:
    # REV 2:4 αλλ -> αλλα is spelling; the RV's "But" for "Nevertheless" is style.
    units: list[Unit] = [
        {
            "id": "REV 2:4#1",
            "ref": "REV 2:4",
            "tr": ["all"],
            "rp": ["alla"],
            "tr_range": [0, 1],
            "rp_range": [0, 1],
            "hf": "RP",
            "class": "spelling",
        }
    ]
    assert (
        revisers.revision_reports(
            RV, kjv_text, texts[RV], byzantine["aligned"], units, {"REV 2:4#1"}
        )
        == []
    )
    assert list(revisers.changes(kjv_text["REV 2:4"], texts[RV]["REV 2:4"]))


def test_built_revision_rows(
    byzantine: Mapping[str, Any], units: list[Unit], by_id: dict[str, Unit]
) -> None:
    rows = byzantine["revision_rows"]
    admitted = revisers.readable(units, byzantine["tcgnt"])
    assert {r["witness"] for r in rows} == {RV, BOYD_ASV}
    assert (
        sum(r["witness"] == RV for r in rows) >= 450
        and sum(r["witness"] == BOYD_ASV for r in rows) >= 900
    )
    for r in rows:
        assert r["scope"] == "greek" and len(r["units"]) == 1
        assert r["method"] in {"aligned", "english"}
        uid = r["units"][0]["unit"]
        assert uid in admitted[r["witness"]]
        assert by_id[uid]["class"] not in NEUTRAL_CLASSES
        assert (r["witness"] == BOYD_ASV) == ("reviser" in r)
    fruit = {r["witness"]: r for r in rows if r["ref"] == "MAT 3:8"}
    assert {w: (r["old"], r["new"]) for w, r in fruit.items()} == {
        RV: ("fruits meet for", "fruit worthy of"),
        BOYD_ASV: ("fruits meet for", "fruit worthy of"),
    }
    assert fruit[BOYD_ASV]["reviser"] == "kept"
    philemon = next(r for r in rows if r["ref"] == "PHM 1:7")
    assert (
        philemon["witness"],
        philemon["old"],
        philemon["new"],
        philemon["reviser"],
    ) == (BOYD_ASV, "great joy", "much thankfulness", "revised")
    assert sum(r.get("reviser") == "revised" for r in rows) >= 250


@pytest.mark.parametrize(
    ("ref", "old", "new", "reviser"),
    [
        ("MAT 3:8", "fruits meet for", "fruit worthy of", "kept"),
        ("JHN 1:28", "Bethabara", "Bethany", "kept"),
        ("REV 19:1", "And", "", "kept"),
        ("REV 19:1", "", "as it were", "kept"),
        ("MAT 28:19", "therefore", "", "revised"),
        ("ACT 21:33", "Then", "And", "revised"),
        # Mixed constructions: inherited restyling beside Boyd's change.
        ("PHM 1:7", "great joy", "much thankfulness", "revised"),
        ("ACT 9:17", "even Jesus, that", "who", "revised"),
        ("HEB 12:28", "may serve", "offer service well-pleasing to", "revised"),
        ("REV 9:4", "only those", "such", "revised"),
        ("REV 4:7", "as", "of", "revised"),
    ],
)
def test_boyd_rows_record_whether_he_kept_or_revised(
    byzantine: Mapping[str, Any], ref: str, old: str, new: str, reviser: str
) -> None:
    rows = [
        row
        for row in byzantine["revision_rows"]
        if row["witness"] == BOYD_ASV
        and (row["ref"], row["old"], row["new"]) == (ref, old, new)
    ]
    assert len(rows) == 1 and rows[0]["reviser"] == reviser


@pytest.mark.parametrize(
    "witness, ref, old, new, word_range",
    [
        (BOYD_ASV, "REV 13:10", "with the sword", "", [18, 21]),
        (BOYD_ASV, "REV 19:18", "", "and", [41, 41]),
        (RV, "1JN 5:20", "may", "", [18, 19]),
        (RV, "ACT 21:8", "that were of Paul’s company", "", [5, 10]),
    ],
)
def test_null_placements_keep_revision_rows_off_their_words(
    byzantine: Mapping[str, Any],
    witness: str,
    ref: str,
    old: str,
    new: str,
    word_range: list[int],
) -> None:
    # The corresponding directives concern shared Greek or an RP margin:
    # en machaira, the free/bond te, ginoskomen, and hoi peri ton Paulon.
    # Their explicit null placements apply before revision fallbacks run.
    assert not any(
        (r["witness"], r["ref"], r["old"], r["new"], r["word_range"])
        == (witness, ref, old, new, word_range)
        for r in byzantine["revision_rows"]
    )


def test_shared_greek_wording_does_not_borrow_a_nearby_unit(
    byzantine: Mapping[str, Any],
) -> None:
    # The only unit removes the article before Jesus. Both texts already
    # have singular logon, so the revisions' "word" is a rendering change.
    assert not [r for r in byzantine["revision_rows"] if r["ref"] == "JHN 14:23"]


def test_repeated_conjunctions_keep_their_separate_units(
    byzantine: Mapping[str, Any],
    kjv_text: Mapping[str, str],
    texts: Mapping[str, Mapping[str, str]],
) -> None:
    # Explicit additional proposals give the repeated conjunctions distinct
    # anchors; each revision must retain those separate unit attachments.
    ref = "REV 21:13"
    proposals: list[Instruction] = []
    for entry, anchor, uid in (
        (1, "on the north", ref + "#2"),
        (2, "on the south", ref + "#3"),
    ):
        bound = bind_plain(
            {
                "ref": ref,
                "kind": "insert",
                "old": "",
                "new": "and",
                "anchor": anchor,
                "side": "before",
            },
            kjv_text[ref],
        )
        assert bound["bind"] == "unique"
        edit: InstructionEdit = {
            "ref": ref,
            "kind": bound["kind"],
            "old": bound["old"],
            "new": bound["new"],
            "word_range": bound["word_range"],
            "units": [uid],
            "scope": "unit",
        }
        proposals.append(
            {
                "source": "additional",
                "entry": entry,
                "ref": ref,
                "scope": "greek",
                "edits": [edit],
            }
        )
    ledger = [u for u in byzantine["units"] if u["ref"] == ref]
    admitted = revisers.readable(ledger, byzantine["tcgnt"])
    for witness in (RV, BOYD_ASV):
        rows = revisers.revision_reports(
            witness,
            kjv_text,
            texts[witness],
            byzantine["aligned"],
            ledger,
            admitted[witness],
            instructions=proposals,
        )
        found = [r for r in rows if r["ref"] == ref and r["new"] == "and"]
        assert {r["units"][0]["unit"] for r in found} == {ref + "#2", ref + "#3"}
        assert len({tuple(r["word_range"]) for r in found}) == 2


def test_revision_alarms(
    byzantine: Mapping[str, Any],
    kjv_text: Mapping[str, str],
    by_id: dict[str, Unit],
    texts: Mapping[str, Mapping[str, str]],
) -> None:
    alarms = byzantine["alarms"]
    assert set(alarms) == set(by_id)
    fruit = alarms["MAT 3:8#1"]
    assert (
        fruit["applicable"],
        fruit["available"],
        fruit["phrases"],
        fruit["missing"],
        fruit["alarm"],
    ) == (True, True, ["fruits meet"], ["fruits meet"], True)
    # The RV keeps fire and God: no two-revision alarm even though the target
    # changes each of these readings. A negative is not proof.
    assert "and with fire" in texts[RV]["MAT 3:11"]
    assert "Fear God" in texts[RV]["REV 14:7"]
    fire = alarms["MAT 3:11#1"]
    assert (fire["phrases"], fire["missing"], fire["alarm"]) == (
        ["and with fire"],
        [],
        False,
    )
    assert alarms["REV 14:7#2"]["alarm"] is False
    bethabara = alarms["JHN 1:28#1"]
    assert (bethabara["phrases"], bethabara["missing"], bethabara["alarm"]) == (
        ["Bethabara"],
        ["Bethabara"],
        True,
    )
    for uid in ("REV 1:18#1", "MAT 12:28#1"):  # a change of order has no alarm to check
        assert by_id[uid]["class"] == "order"
        assert alarms[uid] == {"applicable": False, "available": False}
    assert (
        by_id["1JN 4:16#1"]["tr_range"][0] == by_id["1JN 4:16#1"]["tr_range"][1]
    )  # RP adds; no TR words
    assert alarms["1JN 4:16#1"] == {"applicable": False, "available": False}
    # A unit the bridge does not reach, or a verse a revision lacks, is not
    # available, and an unavailable comparison is no negative evidence.
    assert (
        alarms["ACT 8:37#1"]["applicable"],
        alarms["ACT 8:37#1"]["available"],
        alarms["ACT 8:37#1"]["alarm"],
    ) == (True, False, False)
    assert alarms["ROM 1:3#1"] == {"applicable": True, "available": False}
    unit = by_id["MAT 3:8#1"]
    partial = revisers.alarms(
        [unit], {}, kjv_text, {RV: texts[RV], BOYD_ASV: texts[BOYD_ASV]}
    )
    assert partial["MAT 3:8#1"] == {"applicable": True, "available": False}
    missing = revisers.alarms(
        [unit], byzantine["aligned"], kjv_text, {RV: texts[RV], BOYD_ASV: {}}
    )
    assert (missing["MAT 3:8#1"]["available"], missing["MAT 3:8#1"]["alarm"]) == (
        False,
        False,
    )
    kept = revisers.alarms(
        [unit],
        byzantine["aligned"],
        kjv_text,
        {RV: {"MAT 3:8": kjv_text["MAT 3:8"]}, BOYD_ASV: texts[BOYD_ASV]},
    )
    assert kept["MAT 3:8#1"]["alarm"] is False


@pytest.mark.parametrize("included", [(), (RV,), (BOYD_ASV,)])
def test_both_revision_maps_are_required_for_an_alarm(
    byzantine: Mapping[str, Any],
    kjv_text: Mapping[str, str],
    texts: Mapping[str, Mapping[str, str]],
    by_id: dict[str, Unit],
    included: tuple[str, ...],
) -> None:
    unit = by_id["MAT 3:8#1"]
    alarm = revisers.alarms(
        [unit],
        byzantine["aligned"],
        kjv_text,
        {name: texts[name] for name in included},
    )[unit["id"]]
    assert alarm["applicable"] is True
    assert alarm["available"] is False
    assert alarm["alarm"] is False
    assert alarm["missing"] == []


@pytest.mark.parametrize(
    "uid, phrase, retained",
    [
        ("MAT 7:20#1", "Wherefore", "Therefore"),
        ("MAT 16:17#1", "Bar-jona", "Bar-Jonah"),
        ("MAT 21:41#1", "will let out his", "will let out the vineyard"),
        ("MRK 3:27#1", "No man can", "one can"),
        ("MRK 7:26#1", "a Syrophenician", "a Syrophoenician"),
        ("MRK 13:30#1", "till", "until"),
        ("LUK 12:36#1", "he will return", "he shall return"),
        ("ACT 26:22#1", "witnessing", "testifying"),
        ("COL 2:17#1", "is of Christ", "is Christ’s"),
        ("REV 6:5#3", "him", "thereon"),
        ("REV 7:9#4", "clothed", "arrayed"),
        ("REV 21:20#3", "an amethyst", "amethyst"),
    ],
)
def test_an_alarm_can_report_restyling_of_retained_content(
    byzantine: Mapping[str, Any],
    kjv_text: Mapping[str, str],
    texts: Mapping[str, Mapping[str, str]],
    by_id: dict[str, Unit],
    uid: str,
    phrase: str,
    retained: str,
) -> None:
    # Each pair names content retained in both pinned revisions. Literal
    # absence alone does not establish that the Greek requires an edit.
    ref = by_id[uid]["ref"]
    assert phrase in kjv_text[ref]
    for witness in (RV, BOYD_ASV):
        assert retained in texts[witness][ref]
    alarm = byzantine["alarms"][uid]
    assert alarm["available"] and alarm["alarm"]
    assert phrase in alarm["missing"]


def test_phrase_presence_is_literal_and_can_match_elsewhere_in_a_verse(
    byzantine: Mapping[str, Any], texts: Mapping[str, Mapping[str, str]]
) -> None:
    # "burnt"/"burned" are compared alike by revision reports but remain
    # different literal words for the alarm.
    assert revisers.phrase_count(texts[RV]["MAT 13:40"], "burnt") == 0
    assert revisers.phrase_count(texts[RV]["MAT 13:40"], "burned") == 1
    # MAT 20:22 changes the conjunction before baptism to "or" in Boyd,
    # while RV omits that clause. Both retain "and" earlier in the verse,
    # so the whole-verse presence test does not raise this local alarm.
    alarm = byzantine["alarms"]["MAT 20:22#1"]
    assert alarm["phrases"] == ["and"] and alarm["alarm"] is False
    for witness in (RV, BOYD_ASV):
        assert "answered and said" in texts[witness]["MAT 20:22"]
    assert "or to be baptized" in texts[BOYD_ASV]["MAT 20:22"]
    assert revisers.phrase_count("fear God; God is good", "GOD") == 2
    assert revisers.phrase_count("godly", "God") == 0
