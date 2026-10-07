"""Pierpont's booklet: parser fidelity on the printed rows, binding to the
pinned KJV, and admission as instructions by the compatibility check."""

from __future__ import annotations

import copy
import json
from collections import Counter
from collections.abc import Mapping
from typing import Any, cast

import pytest

from bible.byzantine import BOOKS, PIERPONT, pierpont
from bible.byzantine.pierpont import Inventory
from bible.byzantine.rows import Instruction, PierpontRow
from bible.sources import Content


@pytest.fixture(scope="module")
def inventory(byzantine: Mapping[str, Any]) -> Inventory:
    return cast(Inventory, byzantine["pierpont_inventory"])


@pytest.fixture(scope="module")
def rows(inventory: Inventory) -> list[PierpontRow]:
    return inventory["rows"]


@pytest.fixture(scope="module")
def pierpont_rows(
    instructions: dict[tuple[str, int | str], Instruction],
) -> dict[int | str, Instruction]:
    return {
        entry: row
        for (source, entry), row in instructions.items()
        if source == PIERPONT
    }


def row_at(
    rows: list[PierpontRow],
    ref: str,
    role: str = "directives",
    old: str | None = None,
) -> PierpontRow:
    found = [
        r
        for r in rows
        if r.get("ref") == ref
        and r["role"] == role
        and (old is None or old in r.get("quotation", {}).get("text", ""))
    ]
    assert len(found) == 1, (ref, role, old, len(found))
    return copy.deepcopy(found[0])


def bound(row: PierpontRow, kjv: Mapping[str, str]) -> dict[str, Any]:
    return pierpont.bind({**row, "instruction": pierpont.explicit_operations(row)}, kjv)


# --- the inventory -----------------------------------------------------------


def test_complete_inventory_and_lossless_source(
    inventory: Inventory,
    rows: list[PierpontRow],
    byzantine_inputs: Mapping[str, Content],
) -> None:
    source = byzantine_inputs["pierpont"].read_text()
    assert "".join(inventory["source_lines"]) == source
    assert len(rows) == 1122
    assert len(inventory["tables"]) == 53
    assert Counter(r["role"] for r in rows) == {
        "directives": 956,
        "kjv-agrees": 30,
        "alexandrian-examples": 76,
        "fatz-omissions": 25,
        "fatz-reference-list": 16,
        "fatz-additions": 11,
        "statistics": 8,
    }
    assert {
        ref.split()[0]
        for r in rows
        if r["role"] == "directives" and (ref := r.get("ref"))
    } == set(BOOKS)
    lines = source.splitlines()
    assert all(r["source_original"] == lines[r["line"] - 1] for r in rows)
    assert [i["cause"] for r in rows for i in r["issues"]] == []
    assert json.loads(json.dumps(inventory)) == inventory


def test_absent_reference_is_kept_visible_not_invented(
    kjv_text: Mapping[str, str],
) -> None:
    source = (
        "## Textual Notes\n### Matthew\n| Reference | Weight | Berry | KJV | Change |\n"
        "| --- | --- | --- | --- | --- |\n| 99:1 | 5 | D | _fruits_ | fruit |\n"
    )
    inventory = pierpont.read(source, kjv_text)
    assert inventory["rows"][0]["ref"] == "MAT 99:1"
    found = pierpont.instructions(inventory, kjv_text)[0]
    assert (found["bind"], found["edits"]) == (
        "absent",
        [{"kind": "replace", "old": "fruits", "new": "fruit", "bind": "absent"}],
    )


# --- markup, references, weights, Berry --------------------------------------


def test_markup_decodes_underlines_and_insertion_marks(
    rows: list[PierpontRow],
) -> None:
    decoded = pierpont.markup(r"_word_ + \* (it)")
    assert decoded["text"] == "word + * (it)"
    assert decoded["underlines"] == [[0, 4]]
    assert decoded["insertions"] == [5]
    assert decoded["errors"] == []
    assert pierpont.markup("_open")["errors"] == ["unclosed underline"]
    row = row_at(rows, "MAT 14:19")
    assert [
        row["quotation"]["text"][a:b] for a, b in row["quotation"]["underlines"]
    ] == ["and"]
    assert (
        pierpont.operations(row_at(rows, "MAT 3:11"))["edits"][0]["old"]
        == "and (with) fire"
    )


def test_references_expand_ranges_and_inherit_locally() -> None:
    chapters = {("ACT", 24): 27, ("JHN", 7): 53, ("JHN", 8): 59}
    assert pierpont.references("ACTS 24:6b–8a", None, chapters)[0] == [
        "ACT 24:6",
        "ACT 24:7",
        "ACT 24:8",
    ]
    assert pierpont.references("7:53-8:11", "JHN", chapters)[0] == ["JHN 7:53"] + [
        f"JHN 8:{v}" for v in range(1, 12)
    ]
    assert pierpont.references("(9:44,46", "MRK", chapters)[0] == [
        "MRK 9:44",
        "MRK 9:46",
    ]
    assert pierpont.references("25", "JUD", chapters)[0] == ["JUD 1:25"]
    assert pierpont.references("1 PT. 1:4", None, chapters)[0] == ["1PE 1:4"]
    assert pierpont.references("3:8", None, chapters)[2] == "missing book"
    assert (
        pierpont.references("8:11-7:53", "JHN", chapters)[2] == "reversed verse range"
    )
    assert pierpont.references("8", "MAT", chapters)[2] == "missing chapter"


def test_weight_scales_and_berry_locators() -> None:
    assert pierpont.weight("100.", True)["period"]
    assert not pierpont.weight("100", True)["period"]
    assert pierpont.weight("'45", True)["q_group"]
    assert "error" not in pierpont.weight("c", True)
    assert "error" in pierpont.weight("100", False)
    assert "error" in pierpont.weight("65.", True)
    assert pierpont.weight("x", False)["error"] == "unrecognized weight"
    assert pierpont.weight("5", False)["scale"] == "byzantine-band"
    assert pierpont.weight("80", True)["scale"] == "revelation-percent"
    assert pierpont.berry("B'")["main_text"]
    assert pierpont.berry("G.")["qualified"]
    assert pierpont.berry(r"\*")["not_in_berry"]
    assert pierpont.berry("D")["locators"] == ["D"]


def test_weight_and_berry_are_read_from_real_rows(rows: list[PierpontRow]) -> None:
    row = row_at(rows, "MAT 3:8")
    assert (row["weight"]["value"], row["berry"]["locators"]) == (5, ["D"])
    row = row_at(rows, "ACT 10:48", old="baptized")
    assert row["weight"]["value"] == 1
    assert row["berry"]["not_in_berry"]
    assert row["informational"]
    assert row["change"]["text"] == "+ Jesus"
    row = row_at(rows, "REV 1:18")
    assert (row["weight"]["value"], row["weight"]["scale"]) == (
        80,
        "revelation-percent",
    )
    row = row_at(rows, "MAT 23:13")
    assert (row["weight"]["category"], row["weight"]["value"]) == ("b", None)


def test_strength_maps_weights_to_evidence() -> None:
    band = {"scale": "byzantine-band"}
    for raw in ("5", "4", "b", "c", "d"):
        assert pierpont.strength(pierpont.weight(raw), False) == "mandatory", raw
    assert pierpont.strength(pierpont.weight("3"), False) == "strong"
    assert pierpont.strength(pierpont.weight("2"), False) == "weak"
    assert pierpont.strength(pierpont.weight("1"), False) == "weak"
    # A row opening with ( is informational.
    assert pierpont.strength(pierpont.weight("5"), True) == "weak"
    assert pierpont.strength(pierpont.weight("70", True), False) == "mandatory"
    assert pierpont.strength(pierpont.weight("100.", True), False) == "mandatory"
    assert pierpont.strength(pierpont.weight("65", True), False) == "strong"
    assert pierpont.strength(pierpont.weight("55", True), False) == "weak"
    assert pierpont.strength(pierpont.weight("c", True), False) == "mandatory"
    # Off its scale.
    assert pierpont.strength(pierpont.weight("100", False), False) is None
    assert pierpont.strength(None, False) is None
    assert pierpont.strength({**band, "value": None}, False) is None


def test_strength_on_the_bound_instructions(
    pierpont_rows: dict[int | str, Instruction],
) -> None:
    assert pierpont_rows[5]["strength"] == "mandatory"  # MAT 3:8, weight 5
    assert pierpont_rows[19]["strength"] == "strong"  # MAT 9:5, weight 3
    assert pierpont_rows[348]["strength"] == "weak"  # (10:48, informational
    assert pierpont_rows[629]["strength"] == "mandatory"  # REV 1:18, 80
    assert pierpont_rows[618]["strength"] == "weak"  # REV 1:4, 45
    assert pierpont_rows[965]["strength"] is None  # a KJV-agrees row has no weight


# --- roles --------------------------------------------------------------------


def test_comparison_tables_keep_distinct_roles(rows: list[PierpontRow]) -> None:
    row = row_at(rows, "MAT 2:11", "kjv-agrees")
    assert row["cells"][1] == r"\(C)"
    assert row["berry"]["text"] == "L"
    assert (row["quotation"]["text"], row["change"]["text"]) == (
        "saw the young child",
        "found",
    )
    assert "weight" not in row
    row = row_at(rows, "MAT 19:17", "alexandrian-examples")
    assert "Why do you ask" in row["change"]["text"]
    assert "Why do you ask" not in row["quotation"]["text"]
    assert row_at(rows, "REV 20:2", "fatz-additions")["quotation"]["underlines"] == [
        [10, 38]
    ]
    lists = [r for r in rows if r["role"] == "fatz-reference-list"]
    john = next(r for r in lists if r["cells"][0] == "Jn.")
    assert {"JHN 7:53", "JHN 8:11"} <= set(john["refs"])
    assert "quotation" not in john
    acts = row_at(rows, "ACT 9:5", "fatz-omissions")
    assert acts["reference_raw"] == "Acts 9:5b--6a"
    assert acts["refs"] == ["ACT 9:5", "ACT 9:6"]


# --- operations ---------------------------------------------------------------


def test_simple_operations_keep_each_published_span(rows: list[PierpontRow]) -> None:
    assert pierpont.operations(row_at(rows, "ACT 21:29"))["edits"][0]["old"] == "before"
    ops = pierpont.operations(row_at(rows, "MRK 9:40"))
    assert [(e["old"], e["new"]) for e in ops["edits"]] == [
        ("us", "you"),
        ("our", "your"),
    ]
    assert [
        e["kind"] for e in pierpont.operations(row_at(rows, "1CO 11:15"))["edits"]
    ] == ["delete", "delete"]
    assert pierpont.operations(row_at(rows, "MAT 20:22"))["edits"][0]["new"] == "or"
    hell = pierpont.operations(row_at(rows, "REV 1:18"))
    assert hell["status"] == "simple"
    assert (
        hell["edits"][0]["kind"],
        hell["edits"][0]["old"],
        hell["edits"][0]["new"],
    ) == ("transpose", "hell and of death", "death and of hell")
    two = pierpont.operations(row_at(rows, "MAT 10:28"))
    assert two["status"] == "simple"
    assert [e["new"] for e in two["edits"]] == ["the", "the"]
    assert (
        pierpont.operations(row_at(rows, "REV 13:4", old="which gave"))["annotation"]
        is None
    )
    assert (
        pierpont.operations(row_at(rows, "REV 13:4", old="power unto"))["annotation"]
        == "T"
    )


def test_structural_continuation_and_alternatives(rows: list[PierpontRow]) -> None:
    assert pierpont.operations(row_at(rows, "MAT 23:13"))["status"] == "structural"
    continuation = [
        r for r in rows if r["role"] == "directives" and not r["reference_raw"]
    ]
    assert len(continuation) == 1
    assert pierpont.operations(continuation[0])["status"] == "continuation"
    assert continuation[0]["context_ref"] == "REV 18:3"
    row = row_at(rows, "LUK 21:36")
    assert pierpont.operations(row)["status"] == "complex"
    assert row["change"]["raw"] == "omit _or_ the"
    explicit = pierpont.explicit_operations(row)
    assert explicit["status"] == "explicit"
    assert [e["kind"] for e in explicit["edits"]] == ["delete"]
    assert explicit["alternatives"] == [{"kind": "replace", "new": "the"}]


def test_seven_printed_combined_forms_are_explicit(
    rows: list[PierpontRow], kjv_text: Mapping[str, str]
) -> None:
    entries = {198, 404, 454, 473, 679, 694, 939}
    found = [r for r in rows if r["entry"] in entries]
    assert len(found) == 7
    for row in found:
        explicit = pierpont.explicit_operations(row)
        assert explicit["status"] == "explicit", row["source_original"]
        assert bound(row, kjv_text)["bindings"], row["source_original"]
    row = row_at(rows, "2CO 7:13", old="Therefore")
    assert row["change"]["raw"] == ". (Period) + And"
    spaced = pierpont.explicit_operations(row)
    row["change"] = pierpont.markup(".(Period) + And")
    compact = pierpont.explicit_operations(row)
    assert (spaced["status"], spaced["stop"]) == ("explicit", ".")
    assert spaced["edits"] == compact["edits"]
    assert spaced["edits"][0]["new"] == "And"
    assert (
        pierpont.explicit_operations(row_at(rows, "REV 4:8", old="Holy"))[
            "construction"
        ]
        == "nine-holies"
    )


# --- binding ------------------------------------------------------------------


def test_quotations_bind_to_the_pinned_kjv(
    rows: list[PierpontRow], kjv_text: Mapping[str, str]
) -> None:
    for ref, old in (
        ("LUK 19:29", "Bethphage"),
        ("JHN 8:5", "should be"),
        ("ROM 6:3", "Jesus Christ"),
        ("REV 3:18", "anoint"),
    ):
        assert bound(row_at(rows, ref, old=old), kjv_text)["status"] == "unique", ref
    row = row_at(rows, "MAT 26:39")
    before = copy.deepcopy(row)
    binding = bound(row, kjv_text)
    assert binding["status"] == "unique"
    assert "farther" in row["quotation"]["text"] and "further" in binding["kjv"]
    assert row["quotation"] == before["quotation"]


def test_two_insertion_marks_bind_to_distinct_positions(
    rows: list[PierpontRow], kjv_text: Mapping[str, str]
) -> None:
    binding = bound(row_at(rows, "MAT 10:28"), kjv_text)
    assert binding["status"] == "unique"
    assert [(b["kind"], b["word_range"]) for b in binding["bindings"]] == [
        ("insert", [26, 26]),
        ("insert", [28, 28]),
    ]


def test_cross_verse_quotations_bind_in_each_source_verse(
    rows: list[PierpontRow], kjv_text: Mapping[str, str]
) -> None:
    for ref, expected in (
        ("LUK 9:55", [("LUK 9:55", [6, 18]), ("LUK 9:56", [0, 16])]),
        ("1JN 5:7", [("1JN 5:7", [7, 22]), ("1JN 5:8", [0, 9])]),
    ):
        binding = bound(row_at(rows, ref), kjv_text)
        assert binding["status"] == "unique"
        assert [(b["ref"], b["word_range"]) for b in binding["bindings"]] == expected
        assert all(b["context_exact"] for b in binding["bindings"])


def test_instruction_rows_bound_and_counted(
    pierpont_rows: dict[int | str, Instruction],
) -> None:
    assert len(pierpont_rows) == 986
    assert Counter(r["role"] for r in pierpont_rows.values()) == {
        "instruction": 956,
        "agrees": 30,
    }
    assert Counter(r["status"] for r in pierpont_rows.values()) == {
        "simple": 972,
        "explicit": 7,
        "structural": 6,
        "continuation": 1,
    }
    assert Counter(r["bind"] for r in pierpont_rows.values())["unique"] >= 950
    assert all(r["source"] == PIERPONT for r in pierpont_rows.values())
    for row in pierpont_rows.values():
        assert row["refs"][:1] == ([row["ref"]] if row["ref"] else [])
        for edit in row["edits"]:
            assert edit["kind"] in {"replace", "delete", "insert", "transpose"}
            if edit["bind"] in {"unique", "already"}:
                assert edit["ref"] in row["refs"]
                assert 0 <= edit["word_range"][0] <= edit["word_range"][1]


def edits_of(row: Instruction) -> list[tuple[str, str, str, list[int]]]:
    return [(e["kind"], e["old"], e["new"], e["word_range"]) for e in row["edits"]]


def test_specific_rows_by_entry(pierpont_rows: dict[int | str, Instruction]) -> None:
    assert pierpont_rows[5]["ref"] == "MAT 3:8"
    assert edits_of(pierpont_rows[5]) == [("replace", "fruits", "fruit", [3, 4])]
    # MAT 3:11
    assert edits_of(pierpont_rows[6]) == [("delete", "and with fire", "", [34, 37])]
    # MAT 4:10
    assert edits_of(pierpont_rows[7]) == [("replace", "hence", "behind me", [7, 8])]
    assert edits_of(pierpont_rows[19]) == [("delete", "thee", "", [10, 11])]  # MAT 9:5
    assert (
        pierpont_rows[54]["ref"],
        pierpont_rows[54]["bind"],
        pierpont_rows[54]["edits"],
    ) == ("MAT 23:13", "structural", [])
    # REV 1:4
    assert edits_of(pierpont_rows[618]) == [("replace", "him", "God", [16, 17])]
    assert edits_of(pierpont_rows[629]) == [
        ("transpose", "hell and of death", "death and of hell", [21, 25])
    ]
    assert [pierpont_rows[e]["ref"] for e in (959, 960, 961)] == ["REV 22:19"] * 3
    assert [edits_of(pierpont_rows[e])[0][1:3] for e in (959, 960, 961)] == [
        ("shall", "should"),
        ("book", "tree"),
        ("and", ""),
    ]
    comma = pierpont_rows[605]
    assert comma["refs"] == ["1JN 5:7", "1JN 5:8"]
    assert [(e["ref"], e["kind"]) for e in comma["edits"]] == [
        ("1JN 5:7", "delete"),
        ("1JN 5:8", "delete"),
    ]
    # The KJV's own characters stand in `old`; the quotation's in `quoted_old`.
    assert (
        pierpont_rows[131]["edits"][0]["old"],
        pierpont_rows[131]["edits"][0]["quoted_old"],
    ) == ("brother Philip’s", "brother Philip's")


def test_parenthesized_supplied_words_become_kjv_brackets(
    pierpont_rows: dict[int | str, Instruction],
) -> None:
    assert pierpont_rows[565]["edits"][0]["new"] == "out of [from]"  # JAS 2:18
    assert pierpont_rows[881]["edits"][0]["new"] == "fallen [from]"  # REV 18:3
    # REV 21:17
    assert [e["new"] for e in pierpont_rows[939]["edits"]] == ["", "[was]"]
    assert pierpont_rows[939]["status"] == "explicit"


# --- admission: compatibility as the build computed it -------------------------


def test_compatible_rows_include_shape_checked_changes(
    pierpont_rows: dict[int | str, Instruction],
) -> None:
    for entry in (5, 6, 7, 19, 24, 198, 629, 802, 803, 855, 856, 959, 960, 961):
        row = pierpont_rows[entry]
        # compatible, or compatible but taken whole by an override's construction
        assert row["compatibility"] == "compatible" or "takes this construction" in (
            row["compatibility_reason"] or ""
        ), (entry, row["compatibility_reason"])
    # The check is of the shape of the change at the unit, not of Greek proof.
    # MAT 5:47 brethren -> friends
    assert pierpont_rows[11]["compatibility"] == "compatible"
    assert pierpont_rows[13]["compatibility"] == "compatible"  # MAT 7:2 omit "again"
    assert pierpont_rows[24]["units"] == [
        {"unit": "MAT 10:28#3", "scope": "constituent", "method": "aligned"}
    ]
    assert pierpont_rows[198]["alternatives"] == [{"kind": "replace", "new": "the"}]


def test_unbound_and_unattached_rows(
    pierpont_rows: dict[int | str, Instruction],
) -> None:
    assert (
        pierpont_rows[27]["compatibility"],
        pierpont_rows[27]["compatibility_reason"],
    ) == ("unbound", "binding absent")
    assert (
        pierpont_rows[54]["compatibility"],
        pierpont_rows[54]["compatibility_reason"],
    ) == ("unbound", "binding structural")
    # REV 7:7 Issachar: ambiguous "(were) sealed"
    assert pierpont_rows[734]["compatibility"] == "unbound"
    # These bind but the bridge places their words on no unit; a placement
    # places some by hand, after which the code attaches them; those are
    # compatible.
    for entry in (454, 473, 679, 738, 843):
        row = pierpont_rows[entry]
        if row["units"]:
            assert row[
                "compatibility"
            ] == "compatible" or "takes this construction" in (
                row["compatibility_reason"] or ""
            ), entry
        elif row.get("method") == "hand":  # placed out of scope (unit: null)
            assert row["compatibility"] == "out-of-scope", entry
        else:
            assert (row["compatibility"], row["scope"], row["units"]) == (
                "unattached",
                "verse",
                [],
            ), entry


def test_rows_outside_the_greek_ledger_are_out_of_scope(
    pierpont_rows: dict[int | str, Instruction],
) -> None:
    for entry, ref in (
        (29, "MAT 12:24"),
        (67, "MAT 26:53"),
        (296, "ACT 2:13"),
        (155, "LUK 9:55"),
        (939, "REV 21:17"),
        (965, "MAT 2:11"),
    ):
        row = pierpont_rows[entry]
        assert row["ref"] == ref
        assert (row["compatibility"], row["compatibility_reason"]) == (
            "out-of-scope",
            "no Greek unit in the verse",
        ), entry
        assert row["units"] == []


def test_kjv_agrees_rows_and_supplied_only_changes(
    pierpont_rows: dict[int | str, Instruction],
) -> None:
    row = pierpont_rows[968]
    assert (row["role"], row["compatibility"]) == ("agrees", "agrees")
    assert [a["unit"] for a in row["units"]] == ["MAT 10:28#1"]
    assert pierpont_rows[975]["compatibility"] == "agrees"  # LUK 18:9, bound or not
    jude = pierpont_rows[612]
    assert jude["compatibility"] == "compatible"  # only the second "them" is italic
    assert [e["new"] for e in jude["edits"]] == ["them", "[them]"]
    assert pierpont_rows[171]["compatibility"] == "out-of-scope"
    assert not pierpont_rows[171].get("units")
    assert "pros authn" in (pierpont_rows[171]["compatibility_reason"] or "")


def test_comma_johanneum_omission_is_compatible(
    pierpont_rows: dict[int | str, Instruction],
) -> None:
    # Compatible on its own: the italic Comma is a textual omission. A reading
    # joining 5:7-8 into one sentence takes the construction.
    row = pierpont_rows[605]
    assert row["compatibility"] == "compatible" or row.get("displaced") == "compatible"
