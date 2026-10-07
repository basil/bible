"""The modern-English apparatuses: Boyd's TCENT paired with his TCGNT, FAA's
own Greek, and the selected lists placed by exact English contrast."""

from __future__ import annotations

import copy
import itertools
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from bible.byzantine import (
    FAA,
    MSB,
    PIERPONT,
    TCENT,
    WEB,
    apparatus,
    instructions,
    inventories,
)
from bible.byzantine.greek import Structure
from bible.byzantine.rows import (
    BoydNote,
    FaaRow,
    Instruction,
    Report,
    SelectedListRow,
    Unit,
)
from bible.sources import Content


@pytest.fixture(scope="module")
def structure(byzantine: Mapping[str, Any]) -> Structure:
    found = byzantine["structure"]
    assert isinstance(found, Structure)
    return found


@pytest.fixture(scope="module")
def tcent(byzantine_inputs: Mapping[str, Content]) -> list[BoydNote]:
    return inventories.tcent(byzantine_inputs["tcent"])


@pytest.fixture(scope="module")
def tcgnt(byzantine: Mapping[str, Any]) -> list[BoydNote]:
    return list(byzantine["tcgnt"])


@pytest.fixture(scope="module")
def faa(byzantine: Mapping[str, Any]) -> dict[str, FaaRow]:
    return dict(byzantine["faa_rows"])


@pytest.fixture(scope="module")
def tr(byzantine: Mapping[str, Any]) -> dict[str, list[str]]:
    return dict(byzantine["tr"])


@pytest.fixture(scope="module")
def rp(byzantine: Mapping[str, Any]) -> dict[str, list[str]]:
    return dict(byzantine["rp"])


@pytest.fixture(scope="module")
def msb(
    byzantine_inputs: Mapping[str, Content], structure: Structure
) -> list[SelectedListRow]:
    return apparatus.msb(
        byzantine_inputs["msb"], byzantine_inputs["msb_tables"], structure
    )


@pytest.fixture(scope="module")
def msb_rows(msb: list[SelectedListRow]) -> dict[int | str, SelectedListRow]:
    return {r["entry"]: r for r in msb}


@pytest.fixture(scope="module")
def web(
    byzantine_inputs: Mapping[str, Content], structure: Structure
) -> list[SelectedListRow]:
    return apparatus.web(byzantine_inputs["web"], structure)


def synthetic_units(
    ref: str,
    ranges: Sequence[tuple[int, int, int, int]],
    tr: Mapping[str, list[str]],
    rp: Mapping[str, list[str]],
) -> list[Unit]:
    return [
        {
            "id": f"{ref}#{n}",
            "ref": ref,
            "tr_range": [a, b],
            "rp_range": [c, d],
            "tr": tr[ref][a:b],
            "rp": rp[ref][c:d],
        }
        for n, (a, b, c, d) in enumerate(ranges, 1)
    ]


# --- counts in the built reports ------------------------------------------------------


def test_report_counts_by_witness(
    byzantine: Mapping[str, Any],
    tcent: list[BoydNote],
    faa: dict[str, FaaRow],
    msb: list[SelectedListRow],
    web: list[SelectedListRow],
) -> None:
    reports: list[Report] = byzantine["reports"]
    assert Counter(r["witness"] for r in reports) == {
        FAA: 862,
        TCENT: 552,
        MSB: 354,
        WEB: 116,
    }
    assert len(tcent) == 552
    assert len({r["target_ref"] for r in tcent}) == 489
    assert (len(faa), len(msb), len(web)) == (7960, 354, 116)
    # out-of-scope only by a hand placement (unit: null)
    assert all(
        r["scope"] in {"greek", "verse"} or r.get("method") == "hand" for r in reports
    )
    assert all((r["scope"] == "greek") == bool(r["units"]) for r in reports)
    by_scope = Counter((r["witness"], r["scope"]) for r in reports)
    assert by_scope[FAA, "greek"] >= 830 and by_scope[TCENT, "greek"] >= 540
    assert by_scope[MSB, "greek"] >= 130 and by_scope[WEB, "greek"] >= 50


# --- Boyd ------------------------------------------------------------------------------


def test_boyd_english_can_omit_only_complete_non_tr_groups() -> None:
    def row(*groups: tuple[str, ...]) -> dict[str, Any]:
        return {"variants": [{"sigla": list(g)} for g in groups]}

    greek = row(("ANT", "TR"), ("TH", "WH"), ("BYZ",))
    assert apparatus.boyd_partition_subset(greek, row(("ANT", "TR"))) == [1, 2]
    assert apparatus.boyd_partition_subset(greek, row(("ANT", "TR"), ("BYZ",))) == [1]
    assert apparatus.boyd_partition_subset(greek, greek) == []
    for english in (
        row(("TR",)),
        row(("ANT",)),
        row(("ANT", "TR"), ("TH",)),
        row(("ANT", "TR"), ("NA",)),
        row(("ANT", "TR"), ("ANT",)),
    ):
        assert apparatus.boyd_partition_subset(greek, english) is None, english
    assert apparatus.boyd_partition_subset(greek, row(("ANT", "TR", "TH", "WH"))) == [2]
    assert apparatus.boyd_partition_subset(greek, row(("BYZ",), ("ANT", "TR"))) == [1]
    assert (
        apparatus.boyd_partition_subset(row(("TR",), ("TH",), ("TH",)), row(("TR",)))
        is None
    )


def test_order_pairing_equals_exhaustive_assignments() -> None:
    choices: list[list[int]] = [[], [0], [1], [0, 1], [1, 2], [0, 1, 2]]
    for candidates in itertools.product(choices, repeat=3):
        active = [(i, c) for i, c in enumerate(candidates) if c]
        assignments = [
            a
            for a in itertools.product(*(c for _, c in active))
            if all(x < y for x, y in zip(a, a[1:]))
        ]
        expected: dict[int, int] = {}
        for n, (i, _) in enumerate(active):
            values = {a[n] for a in assignments}
            if len(values) == 1:
                expected[i] = next(iter(values))
        assert apparatus.ordered_pairs(candidates) == expected


def test_tcent_pairs_with_tcgnt_in_the_built_reports(
    reports: dict[tuple[str, int | str], Report], tcgnt: list[BoydNote]
) -> None:
    fruit = reports[TCENT, 1]
    assert (fruit["target_ref"], fruit["greek_entry"], fruit["pairing"]) == (
        "MAT 3:8",
        9,
        "identical-partitions",
    )
    assert (fruit["old"], fruit["new"]) == ("fruits", "fruit")
    assert fruit["units"] == [{"unit": "MAT 3:8#1", "scope": "unit"}]
    span = reports[TCENT, 393]
    assert (span["ref"], span["greek_entry"]) == ("REV 6:1", 1438)
    note = next(n for n in tcgnt if n["entry"] == 1438)
    assert (note["fr"], note["tr"][0]["reading"]) == ("6:1–2", "βλεπε και ειδον")
    assert [a["unit"] for a in span["units"]] == ["REV 6:1#4", "REV 6:2#1"]
    laodicea = reports[TCENT, 368]
    assert (laodicea["target_ref"], laodicea["greek_entry"], laodicea["pairing"]) == (
        "REV 3:14",
        1361,
        "ordered-partition-subset",
    )
    assert laodicea["units"] == [{"unit": "REV 3:14#1", "scope": "unit"}]
    assert (
        laodicea["omitted_greek_variants"][0]["sigla"],
        laodicea["omitted_greek_variants"][0]["reading"],
    ) == (["TH", "WH"], "εν λαοδικια εκκλησιας")
    assert (reports[TCENT, 185]["greek_entry"], reports[TCENT, 185]["pairing"]) == (
        847,
        "coarsened-partitions",
    )  # ACT 21:8
    assert (reports[TCENT, 79]["greek_entry"], reports[TCENT, 79]["units"]) == (
        385,
        [{"unit": "LUK 8:51#2", "scope": "unit"}],
    )


def test_tcent_reports_contract_on_real_matthew_3_8(
    tcent: list[BoydNote], tcgnt: list[BoydNote], structure: Structure
) -> None:
    greek = [r for r in tcgnt if r["target_ref"] == "MAT 3:8"]
    english = [r for r in tcent if r["target_ref"] == "MAT 3:8"]
    unit: Unit = {
        "id": "MAT 3:8#1",
        "ref": "MAT 3:8",
        "class": "inflection",
        "tr_range": [2, 4],
        "rp_range": [2, 4],
        "inventories": [{"inventory": "tcgnt", "entry": 9, "scope": "unit"}],
    }
    before = copy.deepcopy((english, greek, unit))
    report = apparatus.tcent_reports(english, greek, [unit], structure)[0]
    assert (report["greek_entry"], report["units"], report["old"], report["new"]) == (
        9,
        [{"unit": "MAT 3:8#1", "scope": "unit"}],
        "fruits",
        "fruit",
    )
    assert (english, greek, unit) == before
    unusual: list[BoydNote] = [
        {**english[0], "tr": [{"reading": "yoʋr", "sigla": ["TR"]}]}
    ]
    assert apparatus.tcent_reports(unusual, greek, [unit], structure)[0]["old"] is None
    omission: list[BoydNote] = [
        {**english[0], "tr": [{"reading": "---", "sigla": ["TR"]}]}
    ]
    assert apparatus.tcent_reports(omission, greek, [unit], structure)[0]["old"] == ""
    unplaced = apparatus.tcent_reports(
        english, greek, [{**unit, "inventories": []}], structure
    )[0]
    assert (unplaced["units"], unplaced["scope"]) == (
        [{"unit": "MAT 3:8#1", "scope": "unit"}],
        "greek",
    )  # sole fallback
    assert unplaced["method"] == "sole"


def test_tcent_order_resolves_repeated_partitions_without_reusing_notes(
    structure: Structure,
) -> None:
    def row(entry: int) -> BoydNote:
        return {
            "entry": entry,
            "target_ref": "MAT 3:8",
            "fr": "3:8",
            "variants": [{"sigla": ["TR"]}],
            "raw": "fixture",
        }

    greek, english = [row(9), row(10)], [row(1), row(2)]
    unit: Unit = {
        "id": "MAT 3:8#1",
        "ref": "MAT 3:8",
        "class": "inflection",
        "tr_range": [2, 4],
        "rp_range": [2, 4],
        "inventories": [{"inventory": "tcgnt", "entry": 9, "scope": "constituent"}],
    }
    reports = apparatus.tcent_reports(english, greek, [unit], structure)
    assert [r["greek_entry"] for r in reports] == [9, 10]
    assert reports[0]["units"][0]["scope"] == "constituent"
    assert reports[1]["scope"] == "verse"
    assert (
        "greek_entry"
        not in apparatus.tcent_reports(english[:1], greek, [unit], structure)[0]
    )
    ambiguous: list[BoydNote] = [
        {
            **row(1),
            "target_ref": "REV 3:14",
            "fr": "3:14",
            "variants": [{"sigla": ["TR"]}, {"sigla": ["TH", "WH"]}],
        },
        {**row(2), "target_ref": "REV 3:14", "fr": "3:14"},
    ]
    report = apparatus.tcent_reports(
        [{**row(1), "target_ref": "REV 3:14", "fr": "3:14"}], ambiguous, [], structure
    )[0]
    assert "greek_entry" not in report and report["scope"] == "verse"


def test_tcent_crossverse_note_abstains_when_two_greek_notes_fit(
    structure: Structure,
) -> None:
    english: list[BoydNote] = [
        {
            "entry": 1,
            "target_ref": "1TH 5:20",
            "fr": "5:20–21",
            "rp": "prophecies, but test",
            "raw": "prophecies, but test",
            "tr": [{"reading": "prophecies. Test", "sigla": ["TR"]}],
            "variants": [{"reading": "prophecies. Test", "sigla": ["TR"]}],
            "source_main_passages": {"1TH 5:20": "prophecies", "1TH 5:21": "but test"},
        }
    ]
    greek: list[BoydNote] = [
        {
            "entry": n,
            "target_ref": f"1TH 5:{verse}",
            "fr": f"5:{verse}",
            "rp": "δε",
            "tr": [{"reading": "---", "sigla": ["TR"]}],
            "variants": [{"reading": "---", "sigla": ["TR"]}],
        }
        for n, verse in enumerate((20, 21), 1)
    ]
    report = apparatus.tcent_reports(english, greek, [], structure)[0]
    assert report["units"] == []
    assert "greek_entry" not in report
    assert report["reason"] == "ambiguous or conflicting apparatus order"


def test_tcent_crossverse_note_reports_added_de_in_its_verse(
    reports: dict[tuple[str, int | str], Report], by_id: dict[str, Unit]
) -> None:
    report = reports[TCENT, 256]
    assert (report["old"], report["new"]) == (
        "prophecies. Test",
        "prophecies, but test",
    )
    assert report["source_address"] == "5:20–21"
    assert [a["unit"] for a in report["units"]] == ["1TH 5:21#1"]
    unit = by_id["1TH 5:21#1"]
    assert (unit["tr"], unit["rp"]) == ([], ["de"])


def test_tcent_greek_support_figures_do_not_replace_english_readings(
    reports: dict[tuple[str, int | str], Report],
) -> None:
    expected = {
        307: ("magnificent and precious", "precious and magnificent"),
        343: (None, "name, and have not grown weary"),
        479: ("Another", "A second"),
        501: ("drunk", "fallen because of"),
        530: ("them as their God", "them"),
        531: ("It is done! I", "I"),
    }
    for entry, contrast in expected.items():
        report = reports[TCENT, entry]
        assert (report["old"], report["new"]) == contrast, entry
        assert "%" in report["source_original"] and "%" in report["raw"]


# --- FAA -----------------------------------------------------------------------------------


def test_faa_priorities_are_local_and_colons_remain_reading_text() -> None:
    text = "a {RP TR: first} [RP2018: second] b {RP: third: fourth} [TR: fifth]"
    assert apparatus.faa_reading(text, "RP")[0] == "a second b third: fourth"
    assert apparatus.faa_reading(text, "TR")[0] == "a first b fifth"
    with pytest.raises(ValueError, match="no TR reading"):
        apparatus.faa_reading("{RP S1550: - } [P1904 E1624: the]", "TR")
    with pytest.raises(ValueError, match="Unparsed FAA markup"):
        apparatus.faa_reading("{RP TR: word} [unlabelled]", "RP")


def test_faa_inventory_and_missing_scrivener_label(faa: dict[str, FaaRow]) -> None:
    assert len(faa) == 7960
    assert all(f"ROM 14:{v}" in faa for v in (24, 25, 26))
    assert faa["ACT 21:4"]["TR_Greek"] is None
    assert "no TR reading" in faa["ACT 21:4"]["TR_Greek_unavailable"]
    assert "might be fulfilled:" in (faa["MAT 27:35"]["TR_English"] or "")
    assert (faa["LUK 17:36"]["RP_Greek"] or "").strip() == ""
    assert (faa["LUK 17:36"]["TR_Greek"] or "").strip().startswith("δύο ἔσονται")


def test_faa_greek_attachment_can_fall_back_to_sole(
    faa: dict[str, FaaRow],
    tr: dict[str, list[str]],
    rp: dict[str, list[str]],
    structure: Structure,
) -> None:
    row = {"MAT 3:8": faa["MAT 3:8"]}
    unit: Unit = {
        "id": "MAT 3:8#1",
        "ref": "MAT 3:8",
        "tr_range": [2, 4],
        "rp_range": [2, 4],
    }
    before = copy.deepcopy((row, unit))
    reports = apparatus.faa_reports(row, tr, rp, [unit], structure)
    assert reports[0]["units"] == [{"unit": "MAT 3:8#1", "scope": "unit"}]
    assert (reports[0]["old"], reports[0]["new"], reports[0]["greek_group"]) == (
        "fruits",
        "fruit",
        1,
    )
    assert (row, unit) == before
    wrong = copy.deepcopy(row)
    wrong["MAT 3:8"]["TR_Greek"] = (wrong["MAT 3:8"]["TR_Greek"] or "") + " ἄλλο"
    reports = apparatus.faa_reports(wrong, tr, rp, [unit], structure)
    assert reports[0]["method"] == "greek"
    reports = apparatus.faa_reports(
        row, tr, rp, [{**unit, "tr_range": [1, 4]}], structure
    )
    assert (reports[0]["method"], reports[0]["units"][0]["scope"]) == (
        "greek",
        "constituent",
    )
    reports = apparatus.faa_reports(
        {"JHN 18:11": faa["JHN 18:11"]}, tr, rp, [], structure
    )
    assert reports == []
    reports = apparatus.faa_reports(
        {"ACT 21:4": faa["ACT 21:4"]}, tr, rp, [], structure
    )
    assert (reports[0]["entry"], reports[0]["scope"]) == (
        "ACT 21:4#unavailable",
        "verse",
    )


def test_faa_groups_and_units_of_different_widths(
    faa: dict[str, FaaRow],
    tr: dict[str, list[str]],
    rp: dict[str, list[str]],
    structure: Structure,
) -> None:
    unit: Unit = {
        "id": "2CO 7:12#1",
        "ref": "2CO 7:12",
        "class": "substitution",
        "tr_range": [19, 23],
        "rp_range": [19, 23],
    }
    reports = apparatus.faa_reports(
        {"2CO 7:12": faa["2CO 7:12"]}, tr, rp, [unit], structure
    )
    assert [(r["old"], r["new"]) for r in reports] == [("our", "your"), ("you", "us")]
    assert all(
        r["method"] == "greek"
        and r["units"] == [{"unit": unit["id"], "scope": "constituent"}]
        for r in reports
    )
    units: list[Unit] = [
        {
            "id": "ACT 13:23#1",
            "ref": "ACT 13:23",
            "class": "substitution",
            "tr_range": [8, 9],
            "rp_range": [8, 9],
        },
        {
            "id": "ACT 13:23#2",
            "ref": "ACT 13:23",
            "class": "substitution",
            "tr_range": [11, 13],
            "rp_range": [11, 12],
        },
    ]
    reports = apparatus.faa_reports(
        {"ACT 13:23": faa["ACT 13:23"]}, tr, rp, units, structure
    )
    assert not reports[0]["units"]
    assert all(
        r["method"] == "greek"
        and r["units"] == [{"unit": "ACT 13:23#2", "scope": "constituent"}]
        for r in reports[1:]
    )
    unit = {
        "id": "LUK 16:25#1",
        "ref": "LUK 16:25",
        "class": "substitution",
        "tr_range": [22, 23],
        "rp_range": [22, 23],
    }
    reports = apparatus.faa_reports(
        {"LUK 16:25": faa["LUK 16:25"]}, tr, rp, [unit], structure
    )
    assert [(r["old"], r["new"]) for r in reports] == [("this man", "he"), ("", "here")]
    assert [r["greek_group"] for r in reports] == [1, 1]


def test_faa_order_precedes_the_shape_of_an_english_deletion(
    faa: dict[str, FaaRow],
    tr: dict[str, list[str]],
    rp: dict[str, list[str]],
    structure: Structure,
) -> None:
    cases: tuple[tuple[str, list[tuple[int, int, int, int]], int, int], ...] = (
        ("JHN 8:9", [(16, 19, 16, 16), (29, 30, 26, 27)], 4, 2),
        (
            "REV 6:8",
            [(1, 3, 1, 1), (18, 21, 16, 18), (23, 24, 20, 21), (25, 31, 22, 28)],
            2,
            2,
        ),
        ("REV 2:19", [(9, 13, 9, 13), (21, 22, 21, 21)], 2, 2),
        ("REV 16:12", [(3, 4, 3, 3), (13, 14, 12, 12), (28, 29, 26, 27)], 1, 1),
        ("REV 22:21", [(4, 5, 4, 4), (9, 10, 8, 10)], 1, 1),
    )
    for ref, ranges, entry, chosen in cases:
        units = synthetic_units(ref, ranges, tr, rp)
        reports = apparatus.faa_reports({ref: faa[ref]}, tr, rp, units, structure)
        report = next(r for r in reports if r["entry"] == f"{ref}#{entry}")
        assert [a["unit"] for a in report["units"]] == [f"{ref}#{chosen}"], ref


def test_faa_explanatory_note_reads_only_the_published_greek(
    faa: dict[str, FaaRow],
    tr: dict[str, list[str]],
    rp: dict[str, list[str]],
    units: list[Unit],
    structure: Structure,
    reports: dict[tuple[str, int | str], Report],
) -> None:
    note = reports[FAA, "REV 13:4#note1"]
    assert (note["old"], note["new"], note["greek_note"]) == ("gave", "had given", True)
    assert "who gave, TR" in note["source_notes"]
    assert note["units"] == [{"unit": "REV 13:4#1", "scope": "constituent"}]
    altered = {**rp, "REV 13:4": tr["REV 13:4"]}
    found = apparatus.faa_reports(
        {"REV 13:4": faa["REV 13:4"]},
        tr,
        altered,
        [u for u in units if u["ref"] == "REV 13:4"],
        structure,
    )
    assert not any(r.get("greek_note") for r in found)


def test_faa_shared_words_do_not_exclude_a_greek_omission(
    faa: dict[str, FaaRow],
    tr: dict[str, list[str]],
    rp: dict[str, list[str]],
    units: list[Unit],
    structure: Structure,
) -> None:
    ref = "REV 5:6"
    found = apparatus.faa_reports(
        {ref: faa[ref]}, tr, rp, [u for u in units if u["ref"] == ref], structure
    )
    assert [(r["old"], r["new"]) for r in found] == [
        ("And I looked, and behold,", "And I saw"),
        ("elders was", "elders,"),
        ("which have been sent", "which are being sent"),
    ]
    # FAA's first two English phrases follow the omitted kai idou, despite
    # retaining words on both sides. Neither concerns the pronoun oi -> a
    # or the order of pneumata tou theou. Repeated partitions cannot prove
    # these pairs; the separate placement decisions name their construction.
    assert all(r["units"] == [] for r in found)
    assert all("greek_group" not in r for r in found)


def test_faa_explicit_empty_side_still_locates_repeated_omissions(
    faa: dict[str, FaaRow],
    tr: dict[str, list[str]],
    rp: dict[str, list[str]],
    units: list[Unit],
    structure: Structure,
) -> None:
    ref = "REV 7:6"
    found = apparatus.faa_reports(
        {ref: faa[ref]}, tr, rp, [u for u in units if u["ref"] == ref], structure
    )
    assert [(r["old"], r["new"]) for r in found] == [("sealed", "")] * 3
    assert [[a["unit"] for a in r["units"]] for r in found] == [
        ["REV 7:6#1"],
        ["REV 7:6#2"],
        ["REV 7:6#3"],
    ]
    assert all(r["method"] == "greek" for r in found)


def test_pierpont_colon_does_not_inherit_a_punctuation_report_or_amen(
    byzantine: Mapping[str, Any],
    units: list[Unit],
    reports: dict[tuple[str, int | str], Report],
) -> None:
    source: Instruction = next(
        r
        for r in byzantine["instructions"]
        if r["source"] == PIERPONT and r["entry"] == 694
    )
    row = copy.deepcopy(source)
    for edit in row["edits"]:
        edit.pop("units", None)
        edit.pop("scope", None)
        edit.pop("method", None)
        edit.pop("positions", None)
    # FAA's closing quote follows the added Amen, but neither its lexical
    # contrast nor the Greek addition can identify Pierpont's earlier colon.
    quote = reports[FAA, "REV 5:13#5"]
    assert (quote["old"], quote["new"]) == ("ages.”", "ages.")
    assert quote["units"][0]["unit"] == "REV 5:13#5"
    verse = [u for u in units if u["ref"] == "REV 5:13"]
    attached = instructions.attach([row], verse, byzantine["aligned"], [quote])[0]
    assert [a["unit"] for a in attached["units"]] == ["REV 5:13#4"]
    colon = attached["edits"][1]
    assert colon["new"] == ":" and colon["method"] is None
    assert not colon.get("units")
    # Nor does reducing the verse to its sole addition prove a punctuation
    # edit renders that addition. This also exercises the sole fallback.
    punctuation: Instruction = {**row, "edits": [row["edits"][1]]}
    amen = next(u for u in verse if u["id"] == "REV 5:13#5")
    isolated = instructions.attach([punctuation], [amen], {}, [quote])[0]
    assert isolated["units"] == []


# --- MSB, WEB ----------------------------------------------------------------------


def test_selected_inventories_start_unattached(
    msb: list[SelectedListRow], web: list[SelectedListRow]
) -> None:
    assert all(r["units"] == [] for r in (*msb, *web))


def test_msb_rows_keep_position_shared_mentions_and_third_readings(
    msb: list[SelectedListRow],
) -> None:
    fruit = next(r for r in msb if r["ref"] == "MAT 3:8")
    assert (
        fruit["old"],
        fruit["new"],
        fruit["greek"],
        fruit["source_original_html"],
    ) == ("fruits", "fruit ,", "καρπὸν", "TR <i>fruits</i>")
    assert any("Stephanus TR" in r["raw"] for r in msb) and any(
        "MT, and TR" in r["raw"] for r in msb
    )
    expected = {
        "MAT 12:35": ("of the heart", ""),
        "MAT 18:19": ("", "truly"),
        "MAT 3:16": (None, None),
        "MAT 10:25": ("Beelzebub", "Beelzebul ,"),
        "MAT 27:46": ("lama", "lima"),
        "MRK 15:34": ("lamma", "lima"),
        "JHN 1:28": ("Bethabara", "Bethany"),
        "REV 15:3": ("King of the saints", "nations !"),
        "MAT 5:47": ("brothers", "friends ,"),
        "LUK 9:23": ("daily", ""),
    }
    for ref, pair in expected.items():
        found = next(r for r in msb if r["ref"] == ref)
        assert (found["old"], found["new"]) == pair, ref
    assert next(r for r in msb if r["ref"] == "MAT 3:16")["new_scope"] == "unavailable"
    nested = next(r for r in msb if "TR includes <i><span" in r["source_original_html"])
    assert (nested["old"], nested["new"]) == (None, None)


@pytest.mark.parametrize(
    "entry,ref,reading",
    [
        (154677, "1CO 15:49", "let us bear"),
        (219653, "REV 22:19", "of life"),
        (129680, "ACT 26:3", "[since] you"),
        (202775, "1JN 3:16", "- :"),
    ],
)
def test_msb_scope_does_not_cross_clauses_or_cut_brackets(
    msb_rows: dict[int | str, SelectedListRow], entry: int, ref: str, reading: str
) -> None:
    row = msb_rows[entry]
    assert row["ref"] == ref
    assert row["new"] == reading
    assert row["new_scope"] == "footnoted-token"


def test_msb_closed_phrase_and_transposition_remain_available(
    msb_rows: dict[int | str, SelectedListRow],
) -> None:
    assert msb_rows[28275]["new"] == "we will believe in Him"
    assert msb_rows[58983]["new"] == "Peter , John , James"
    assert msb_rows[159023]["new"] == "your earnestness on our behalf"


def test_msb_surface_decodes_split_html(
    msb_rows: dict[int | str, SelectedListRow],
) -> None:
    row = msb_rows[65762]
    assert row["ref"] == "LUK 13:15"
    assert row["new"] == "“ You hypocrites !”"
    assert "</span>" not in row["english_context"]
    assert "</span>" not in row["source_table_transcription"]
    assert apparatus.msb_text(["<span>You ", "hypocrites</span> &amp; others"]) == (
        "You hypocrites & others"
    )


def test_msb_contrast_reads_joint_labels_and_abstains_elsewhere() -> None:
    for labels in (
        "CT and TR",
        "GOC, F35, TR",
        "TR and GOC",
        "CT, Scrivener TR",
        "ALT, CT, and TR",
    ):
        assert apparatus.msb_contrast(labels + " <i>brothers</i>", "friends") == (
            "brothers",
            "friends",
        )
        assert apparatus.msb_contrast(
            labels + " include <i>daily</i>.", "unrelated"
        ) == ("daily", "")
        assert apparatus.msb_contrast(
            labels + " do not include <i>Him</i>.", "unrelated"
        ) == ("", "Him")
    for source in (
        "Stephanus TR <i>they found</i>",
        "GOC, CT, Stephanus TR <i>staff</i>",
        "NA, MT, and TR <i>words</i>",
        "Unknown and TR <i>words</i>",
        "CT <i>words</i>",
        "TR <i>words</i> or <i>other words</i>",
        "TR includes <i><span>36</span>words</i>",
        "CT <i>words</i>; TR <i>other words</i> or <i>another</i>",
        "TR <i>words</i>; see John 1:1",
        "WH <i>one</i>; TR <i>two</i>; TR <i>three</i>",
        "TR <i>two</i>; Scrivener TR <i>three</i>",
        "CT and TR <i>two</i>; CT <i>three</i>",
        "WH, WH <i>one</i>; TR <i>two</i>",
        "WH <i>one</i>; Unknown TR <i>two</i>",
        "WH <i>one</i>; MT and TR <i>two</i>",
        "WH <i>one</i>; Stephanus TR <i>two</i>",
        "Or <i>one</i>; TR <i>two</i>",
        "WH <i>one</i>; TR includes <i>two</i>",
        "WH <i>one</i>; TR <i>two</i>; see John 1:1",
    ):
        assert apparatus.msb_contrast(source, "text") == (None, None), source
    assert apparatus.msb_contrast(
        "WH <i>Beezeboul</i>; Scrivener TR <i>Beelzebub</i>", "Beelzebul"
    ) == ("Beelzebub", "Beelzebul")


def test_web_notes_and_contrast_forms(web: list[SelectedListRow]) -> None:
    expected = {
        "MAT 7:14": ("Because", "How"),
        "MAT 3:11": ("and with fire", ""),
        "MRK 3:32": ("", "your sisters"),
        "2CO 1:11": ("our", "your"),
        "1CO 7:3": ("what is owed her", "the affection owed her"),
        "REV 3:2": ("which were about to die", "which you were about to throw away"),
        "ACT 9:38": ("two men", ""),
        "ACT 10:19": ("three", ""),
        "LUK 20:9": ("certain", ""),
    }
    for ref, pair in expected.items():
        found = next(r for r in web if r["ref"] == ref)
        assert (found["old"], found["new"]) == pair, ref
    assert (
        next(r for r in web if r["ref"] == "MAT 3:11")["raw"]
        == "TR and NU add “and with fire”"
    )
    assert all("TR" in r["raw"] for r in web)
    for labels in ("TR", "TR and NU", "TR & NU", "TR, NU", "NU, TR"):
        assert apparatus.web_contrast(labels + " read “lama” instead of “lima”") == (
            "lama",
            "lima",
        )
        assert apparatus.web_contrast(labels + " omit “him”.") == ("", "him")
        assert apparatus.web_contrast(labels + " add “daily”") == ("daily", "")
    for raw in (
        "So MT and TR. NU reads “other”",
        "TR adds “words” [see John 1:1]",
        "TR, NU, and FH MT omit: words",
        "NU reads “lama” instead of “lima”",
        "+ MT: your; TR and NU: our; see verse 12",
        "+ MT and TR: your; NU: our",
        "NU & TR read “one” instead of “two” or “three”",
        "NU have “one” instead of “two”",
        "Reading from TR. MT omits “one” and adds “two”",
        "Reading from NU; MT omits “one”",
        "Reading from MT and TR. MT omits “one”",
        "NU (in brackets) and TR add “certain” [see verse 10]",
        "NU (in brackets) and MT add “certain”",
    ):
        assert apparatus.web_contrast(raw) == (None, None), raw


def test_an_unattached_selected_row_keeps_its_source_reason(
    msb: list[SelectedListRow],
) -> None:
    # The selected lists attach from their source rows, so a row the placed
    # anchors no longer confirm keeps the reason its reader gave it.
    reason = "selected TR mention has no verified two-sided English contrast"
    rows = [r for r in msb if r["witness"] == MSB]
    assert rows and all(r["reason"] == reason and not r["units"] for r in rows)
    assert all(
        r.get("reason") != "no exact two-sided Greek-bound English contrast"
        for r in apparatus.attach_contrasts(rows, [])
    )


def test_attach_contrasts_needs_an_exact_two_sided_greek_bound_match(
    msb: list[SelectedListRow], web: list[SelectedListRow]
) -> None:
    row = next(r for r in msb if r["ref"] == "MAT 3:8")
    faa: Report = {
        "witness": FAA,
        "entry": "MAT 3:8#1",
        "ref": "MAT 3:8",
        "old": "fruits",
        "new": "fruit",
        "units": [{"unit": "MAT 3:8#1", "scope": "unit"}],
    }
    before = copy.deepcopy((row, faa))
    placed = apparatus.attach_contrasts([row], [faa])[0]
    assert (placed["scope"], placed["method"], placed["via"]) == (
        "greek",
        "english",
        {"witness": FAA, "entry": "MAT 3:8#1"},
    )
    assert placed["units"] == faa["units"] and "reason" not in placed
    # Attaching again starts from the source row, never from its attachment.
    assert apparatus.attach_contrasts([row], [faa])[0] == placed
    with pytest.raises(ValueError, match="already attached"):
        apparatus.attach_contrasts([placed], [faa])
    removed = apparatus.attach_contrasts([row], [{**faa, "units": []}])[0]
    assert (removed["units"], removed["scope"]) == ([], "verse")
    assert removed["raw"] == row["raw"]
    assert not {"method", "via", "contrast_evidence"}.intersection(removed)
    others: list[Report] = [
        {**faa, "new": "different"},
        {**faa, "units": []},
        {**faa, "method": "sole"},
    ]
    for other in others:
        assert apparatus.attach_contrasts([row], [other])[0]["scope"] == "verse"
    assert (
        apparatus.attach_contrasts([row], [faa, faa])[0]["reason"]
        == "ambiguous exact English contrasts"
    )
    assert (
        apparatus.attach_contrasts([{**row, "new": "{fruit}"}], [faa])[0]["scope"]
        == "verse"
    )
    assert (row, faa) == before
    name = next(r for r in msb if r["ref"] == "MAT 10:25")
    bound: Report = {
        **faa,
        "entry": "MAT 10:25#1",
        "ref": "MAT 10:25",
        "old": "Beelzebub",
        "new": "Beelzebul",
        "units": [{"unit": "MAT 10:25#1", "scope": "unit"}],
    }
    assert apparatus.attach_contrasts([name], [bound])[0]["scope"] == "greek"
    assert (
        apparatus.attach_contrasts([name], [{**bound, "old": "Beezeboul"}])[0]["scope"]
        == "verse"
    )
    title = next(r for r in msb if r["ref"] == "REV 15:3")
    assert (
        apparatus.attach_contrasts(
            [title], [{**bound, "ref": "REV 15:3", "old": "saints", "new": "nations"}]
        )[0]["scope"]
        == "verse"
    )
    our = next(r for r in web if r["ref"] == "2CO 1:11")
    boyd: Report = {
        "witness": TCENT,
        "entry": 228,
        "ref": "2CO 1:11",
        "old": "our",
        "new": "your",
        "units": [{"unit": "2CO 1:11#1", "scope": "unit"}],
    }
    assert apparatus.attach_contrasts([our], [], [boyd])[0]["scope"] == "greek"
    assert (
        apparatus.attach_contrasts([our], [], [{**boyd, "new": "their"}])[0]["scope"]
        == "verse"
    )
    three = next(r for r in web if r["ref"] == "ACT 10:19")
    some: Report = {
        **faa,
        "entry": "ACT 10:19#2",
        "ref": "ACT 10:19",
        "old": "three",
        "new": "some",
        "units": [{"unit": "ACT 10:19#2", "scope": "unit"}],
    }
    assert (
        apparatus.attach_contrasts([three], [some])[0]["scope"] == "verse"
    )  # omission is not replacement


def test_independent_witnesses_confirm_one_location(
    reports: dict[tuple[str, int | str], Report],
) -> None:
    row: SelectedListRow = {
        "witness": WEB,
        "entry": 1,
        "ref": "MAT 5:47",
        "old": "brothers",
        "new": "friends",
        "units": [],
        "scope": "verse",
    }
    boyd: Report = {
        "witness": TCENT,
        "entry": 6,
        "ref": "MAT 5:47",
        "old": "brothers",
        "new": "friends",
        "units": [{"unit": "MAT 5:47#1", "scope": "unit"}],
    }
    faa: Report = {**boyd, "witness": FAA}
    assert apparatus.attach_contrasts([row], [], [boyd])[0]["via"]["witness"] == TCENT
    matched = apparatus.attach_contrasts([row], [faa], [boyd])[0]
    assert (len(matched["contrast_evidence"]), matched["method"]) == (2, "english")
    others: list[Report] = [
        {**boyd, "units": [{"unit": "MAT 5:47#2", "scope": "unit"}]},
        {**boyd, "units": [{"unit": "MAT 5:47#1", "scope": "constituent"}]},
    ]
    for other in others:
        assert apparatus.attach_contrasts([row], [faa], [other])[0]["scope"] == "verse"
    unreadable: list[Report] = [{**boyd, "old": None}, {**boyd, "old": "brothersʋ"}]
    for other in unreadable:
        assert apparatus.attach_contrasts([row], [], [other])[0]["scope"] == "verse"
    assert (
        apparatus.attach_contrasts([{**row, "old": "---"}], [], [{**boyd, "old": ""}])[
            0
        ]["scope"]
        == "verse"
    )
    fruit = next(
        r for (w, _), r in reports.items() if w == MSB and r["ref"] == "MAT 3:8"
    )
    assert (fruit["scope"], fruit["method"], fruit["via"]) == (
        "greek",
        "english",
        {"witness": FAA, "entry": "MAT 3:8#1"},
    )
    assert fruit["units"] == [{"unit": "MAT 3:8#1", "scope": "unit"}]


@pytest.mark.parametrize(
    "witness, entry, anchor_entry, ref, tr_words, rp_words",
    [
        (MSB, 217332, "REV 19:15#1", "REV 19:15", [], ["distomos"]),
    ],
)
def test_english_attachment_uses_the_placed_faa_anchor(
    units: list[Unit],
    reports: dict[tuple[str, int | str], Report],
    witness: str,
    entry: int,
    anchor_entry: str,
    ref: str,
    tr_words: list[str],
    rp_words: list[str],
) -> None:
    report = reports[witness, entry]
    anchor = reports[FAA, anchor_entry]
    expected = next(
        u["id"]
        for u in units
        if u["ref"] == ref and u["tr"] == tr_words and u["rp"] == rp_words
    )
    assert report["method"] == "english"
    assert report["via"] == {"witness": FAA, "entry": anchor_entry}
    assert [a["unit"] for a in report["units"]] == [expected]
    assert [a["unit"] for a in anchor["units"]] == [expected]
