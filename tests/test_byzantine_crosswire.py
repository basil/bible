"""The CrossWire bridge from KJV words to Scrivener's tokens and the word-level
helpers. Explicit instruction fixtures exercise attachment independently of
the source parsers."""

from __future__ import annotations

import copy
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

import pytest

from bible.byzantine.crosswire import (
    Tagged,
    attach_sole,
    bridge,
    bridged_words,
    contrast,
    fitting_unit,
    reported_operation,
    spans,
    words,
)
from bible.byzantine.rows import Report, Unit


@pytest.fixture(scope="module")
def cw(byzantine: Mapping[str, Any]) -> dict[str, Tagged]:
    found: dict[str, Tagged] = byzantine["crosswire"]
    return found


@pytest.fixture(scope="module")
def by_ref(units: list[Unit]) -> dict[str, list[Unit]]:
    result: defaultdict[str, list[Unit]] = defaultdict(list)
    for unit in units:
        result[unit["ref"]].append(unit)
    return result


# Words.


def test_latin_ae_ligature_is_one_word_with_original_offsets() -> None:
    text = "Æneas in Judæa’s towns"
    assert spans(text) == [
        ("aeneas", 0, 5),
        ("in", 6, 8),
        ("judaea's", 9, 16),
        ("towns", 17, 22),
    ]
    assert text[9:16] == "Judæa’s"
    assert (
        words("Bring forth therefore fruits meet for repentance:")
        == "bring forth therefore fruits meet for repentance".split()
    )
    assert words("Christ’s; don't") == ["christ's", "don't"]


def test_contrast_strips_shared_ends_only() -> None:
    assert contrast(
        "Bring forth therefore fruits meet", "Bring forth therefore fruit meet"
    ) == (("fruits",), ("fruit",))
    assert contrast("a b c", "a c b") == (("b", "c"), ("c", "b"))
    assert contrast("same", "same") == ((), ())
    assert contrast("the fowls of the air came", "the fowls came") == (
        ("of", "the", "air"),
        (),
    )
    assert contrast("", "added") == ((), ("added",))


def test_reported_operation_reads_rows_of_every_witness() -> None:
    assert reported_operation({"op": "omit"}) == (True, False, False)
    assert reported_operation({"kind": "insert"}) == (False, True, False)
    assert reported_operation({"old": "nations", "new": ""}) == (True, False, False)
    assert reported_operation({"old": "", "new": "thy"}) == (False, True, False)
    assert reported_operation({"old": "a b c", "new": "a c b"}) == (False, False, True)
    assert reported_operation({"old": "fruits", "new": "fruit"}) == (
        False,
        False,
        False,
    )


# CrossWire and the bridge.


def test_crosswire_reader_keeps_every_verse_with_its_links(
    cw: dict[str, Tagged], kjv_text: Mapping[str, str]
) -> None:
    assert len(cw) == 7957
    row = cw["MAT 3:8"]
    assert row["text"] == kjv_text["MAT 3:8"]
    assert row["links"][:2] == [
        {"range": [0, 11], "src": ["1"], "forms": ["ποιησατε"], "strongs": [4160]},
        {"range": [12, 21], "src": ["2"], "forms": ["ουν"], "strongs": [3767]},
    ]
    assert all(
        row["text"][a:b].strip() for link in row["links"] for a, b in [link["range"]]
    )


def test_bridge_covers_the_canon_but_for_ten_conflicting_verses(
    byzantine: Mapping[str, Any], kjv_text: Mapping[str, str]
) -> None:
    aligned, failures = byzantine["aligned"], byzantine["bridge_failures"]
    assert len(aligned) + len(failures) == 7957
    assert sorted(failures) == [
        "1PE 1:1",
        "1PE 1:2",
        "2CO 1:7",
        "2CO 8:14",
        "MAT 23:14",
        "ROM 1:10",
        "ROM 1:3",
        "ROM 1:9",
        "ROM 3:25",
        "ROM 3:26",
    ]
    assert set(failures.values()) == {
        "incomplete or conflicting CrossWire Greek positions"
    }
    for ref in (
        "ACT 9:33",
        "ACT 9:34",
        "JHN 3:23",
        "2CO 1:11",
        "MAT 22:7",
        "ACT 13:17",
        "JHN 4:3",
        "ACT 2:7",
    ):
        assert len(aligned[ref]["positions"]) == len(spans(kjv_text[ref]))
        assert aligned[ref]["word_ranges"] == [
            [s, e] for _, s, e in spans(kjv_text[ref])
        ]
        assert aligned[ref]["greek_length"] == len(byzantine["tr"][ref])
    # English spelling differences retain links to the same Greek tokens.
    assert aligned["MAT 22:7"]["positions"][20] == [18]
    assert aligned["MAT 22:7"]["direct"][20] == [18]
    assert aligned["MAT 22:7"]["positions"][0] == [1]
    assert aligned["JHN 4:3"]["positions"][2] == [1, 2]
    assert aligned["JHN 4:3"]["direct"][2] == [1, 2]
    assert aligned["JHN 4:3"]["positions"][5] == [5]
    # CrossWire's different Greek verb cannot support Scrivener's "saw".
    saw = words(kjv_text["MAT 2:11"]).index("saw")
    assert aligned["MAT 2:11"]["positions"][saw] == []
    assert aligned["MAT 2:11"]["direct"][saw] == []


def test_bridge_maps_the_kjv_words_of_a_real_unit(byzantine: Mapping[str, Any]) -> None:
    row = byzantine["aligned"]["MAT 3:8"]
    assert row["positions"] == [[0], [0], [1], [2], [3], [4, 5], [4, 5]]
    assert bridged_words(row, 2, 4) == [3, 4]
    assert bridged_words(row, 1, 2) == [2]
    assert bridged_words(row, 6, 7) == []


def test_bridge_keeps_agreeing_words_across_greek_and_english_changes(
    byzantine: Mapping[str, Any], cw: dict[str, Tagged], kjv_text: Mapping[str, str]
) -> None:
    ref = "MAT 3:8"
    tr, aligned = byzantine["tr"], byzantine["aligned"]
    wrong = {ref: ["other"] + tr[ref][1:]}
    partial = bridge({ref: cw[ref]}, wrong, kjv_text)[0][ref]
    assert not any(0 in ps for ps in partial["positions"])
    assert any(1 in ps for ps in partial["positions"])
    partial = bridge({ref: cw[ref]}, tr, {ref: "Other " + kjv_text[ref]})[0][ref]
    assert partial["positions"][0] == []
    assert partial["positions"][1:] == aligned[ref]["positions"]


def test_supplied_words_close_over_both_neighbours_without_mutation() -> None:
    row: Tagged = {
        "text": "one supplied two",
        "links": [
            {"range": [0, 3], "src": ["1"], "forms": ["α"], "strongs": []},
            {"range": [13, 16], "src": ["2"], "forms": ["β"], "strongs": []},
        ],
    }
    before = copy.deepcopy(row)
    aligned, failures = bridge(
        {"MAT 3:8": row}, {"MAT 3:8": ["a", "b"]}, {"MAT 3:8": "one supplied two"}
    )
    assert aligned["MAT 3:8"]["positions"] == [[0], [0, 1], [1]]
    assert failures == {}
    assert row == before
    broken: Tagged = {
        **row,
        "links": [{"range": [0, 3], "src": ["1", "2"], "forms": ["α"], "strongs": []}],
    }
    assert bridge(
        {"MAT 3:8": broken}, {"MAT 3:8": ["a", "b"]}, {"MAT 3:8": "one supplied two"}
    )[1] == {"MAT 3:8": "incomplete or conflicting CrossWire Greek positions"}


def test_spelling_variants_bridge_crosswire_to_the_cambridge_text() -> None:
    row: Tagged = {
        "text": "shew honour",
        "links": [
            {"range": [0, 4], "src": ["1"], "forms": ["α"], "strongs": []},
            {"range": [5, 11], "src": ["2"], "forms": ["β"], "strongs": []},
        ],
    }
    aligned, _ = bridge({"X 1:1": row}, {"X 1:1": ["a", "b"]}, {"X 1:1": "show honor"})
    assert aligned["X 1:1"]["positions"] == [[0], [1]]


# Laying English changes on Greek units.


def test_fitting_unit_takes_the_unit_whose_greek_the_words_render(
    byzantine: Mapping[str, Any], by_ref: dict[str, list[Unit]]
) -> None:
    aligned = byzantine["aligned"]
    found = fitting_unit(by_ref["MAT 3:8"], aligned["MAT 3:8"], 3, 4, "replace")
    assert found is not None
    chosen, scope, ps = found
    assert (chosen["id"], scope, ps) == ("MAT 3:8#1", "constituent", {2})
    assert fitting_unit(by_ref["MAT 3:8"], aligned["MAT 3:8"], 2, 3, "replace") is None
    # MAT 7:2: "again" renders the changed verb; the whole unit.
    found = fitting_unit(by_ref["MAT 7:2"], aligned["MAT 7:2"], 22, 23, "delete")
    assert found is not None
    chosen, scope, ps = found
    assert (chosen["id"], scope, ps) == ("MAT 7:2#1", "unit", {11})
    # MRK 4:4 "of the air" is the omitted του ουρανου.
    found = fitting_unit(by_ref["MRK 4:4"], aligned["MRK 4:4"], 17, 20, "delete")
    assert found is not None
    chosen, scope, _ = found
    assert (chosen["id"], scope) == ("MRK 4:4#1", "unit")


def test_english_addition_can_align_to_an_inflected_greek_word(
    byzantine: Mapping[str, Any],
    by_ref: dict[str, list[Unit]],
    kjv_text: Mapping[str, str],
) -> None:
    # HEB 8:5: "thou shalt make" for "thou make"; ποιησης → ποιησεις.
    assert words(kjv_text["HEB 8:5"])[29:31] == ["thou", "make"]
    assert [u["class"] for u in by_ref["HEB 8:5"]] == ["spelling", "inflection"]
    found = fitting_unit(
        by_ref["HEB 8:5"], byzantine["aligned"]["HEB 8:5"], 30, 30, "insert"
    )
    assert found is not None
    chosen, scope, _ = found
    assert (chosen["id"], scope) == ("HEB 8:5#2", "constituent")


def test_several_fitting_units_narrow_to_the_one_whose_greek_does_what_the_english_does(
    byzantine: Mapping[str, Any],
    by_ref: dict[str, list[Unit]],
    kjv_text: Mapping[str, str],
) -> None:
    # PHP 2:21 "Jesus Christ's" / "Christ Jesus'": the real unit is a dropped
    # article under those words. Alone it fits; beside an order unit on the
    # same Greek, only the order unit fits a transposition.
    assert words(kjv_text["PHP 2:21"])[10:12] == ["jesus", "christ's"]
    [article] = by_ref["PHP 2:21"]
    assert (article["class"], article["tr_range"], article["rp_range"]) == (
        "article",
        [8, 9],
        [8, 8],
    )
    aligned = byzantine["aligned"]["PHP 2:21"]
    found = fitting_unit([article], aligned, 10, 12, "replace", transpose=True)
    assert found is not None
    chosen, scope, ps = found
    assert (chosen["id"], scope, ps) == ("PHP 2:21#1", "unit", {8, 9, 10})
    order: Unit = {
        "id": "PHP 2:21#order",
        "ref": "PHP 2:21",
        "class": "order",
        "tr_range": [9, 11],
        "rp_range": [8, 10],
    }
    found = fitting_unit([article, order], aligned, 10, 12, "replace", transpose=True)
    assert found is not None
    chosen, scope, _ = found
    assert (chosen["id"], scope) == ("PHP 2:21#order", "unit")
    # A dropped article is not a replacement either; the order unit is still the
    # one compatible unit. Two compatible units leave nothing chosen.
    found = fitting_unit([article, order], aligned, 10, 12, "replace")
    assert found is not None and found[0]["id"] == "PHP 2:21#order"
    substitution: Unit = {
        "id": "PHP 2:21#sub",
        "ref": "PHP 2:21",
        "class": "substitution",
        "tr_range": [9, 10],
        "rp_range": [9, 10],
    }
    assert fitting_unit([substitution, order], aligned, 10, 12, "replace") is None


def test_fitting_unit_skips_relocations_and_accents(
    byzantine: Mapping[str, Any], by_ref: dict[str, list[Unit]]
) -> None:
    aligned = byzantine["aligned"]
    assert [u["kind"] for u in by_ref["1CO 5:13"] if u.get("kind")] == ["accent"]
    accent_only = [u for u in by_ref["1CO 5:13"] if u.get("kind") == "accent"]
    assert fitting_unit(accent_only, aligned["1CO 5:13"], 0, 1, "replace") is None
    moves = [u for u in by_ref["ROM 16:25"] if u.get("kind") == "relocation"]
    assert moves and fitting_unit(moves, aligned["ROM 16:25"], 0, 1, "replace") is None


def test_sole_attachment_uses_one_unit_and_one_row(
    by_ref: dict[str, list[Unit]],
) -> None:
    rows: list[Report] = [
        {
            "witness": "synthetic",
            "entry": 1,
            "ref": "MAT 3:11",
            "scope": "verse",
            "old": "and with fire",
            "new": "",
            "units": [],
        }
    ]
    before = copy.deepcopy(rows)
    [placed] = attach_sole(rows, by_ref["MAT 3:11"])
    assert (placed["method"], placed["scope"]) == ("sole", "greek")
    assert placed["units"] == [{"unit": "MAT 3:11#1", "scope": "unit"}]
    assert rows == before
    assert all(not r["units"] for r in attach_sole(rows + rows, by_ref["MAT 3:11"]))
    already: Report = {
        **rows[0],
        "units": [{"unit": "MAT 3:11#1", "scope": "constituent"}],
    }
    assert attach_sole([already], by_ref["MAT 3:11"])[0]["method"] == "greek"


def test_sole_report_attachment_refuses_transposition_at_a_substitution(
    by_ref: dict[str, list[Unit]],
) -> None:
    report: Report = {
        "witness": "faa",
        "entry": 1,
        "ref": "REV 15:4",
        "kind": "replace",
        "old": "pious",
        "new": "holy",
        "scope": "verse",
        "units": [],
    }
    assert attach_sole([report], by_ref["REV 15:4"])[0]["method"] == "sole"
    # An equal-length substitution may still be reported as an English omission.
    omit: Report = {**report, "kind": "delete", "old": "nations", "new": ""}
    assert attach_sole([omit], by_ref["REV 15:4"])[0]["method"] == "sole"
    transpose: Report = {**report, "kind": "transpose", "old": "a b", "new": "b a"}
    assert attach_sole([transpose], by_ref["REV 15:4"])[0]["units"] == []
