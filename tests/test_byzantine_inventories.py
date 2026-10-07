"""The published Greek variation inventories: Robinson's collation, Boyd's
TCGNT and TCENT apparatuses, and the Appendix C word breaks."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Mapping
from typing import Any

import pytest

from bible.byzantine import BOOKS
from bible.byzantine.inventories import (
    boyd,
    collation,
    reading_words,
    tcent,
    word_breaks,
)
from bible.byzantine.rows import BoydNote, CollationRow, Unit
from bible.sources import Content


@pytest.fixture(scope="module")
def tcgnt(byzantine_inputs: Mapping[str, Content]) -> Content:
    return byzantine_inputs["tcgnt"]


@pytest.fixture(scope="module")
def coll(byzantine: Mapping[str, Any]) -> list[CollationRow]:
    found: list[CollationRow] = byzantine["collation"]
    return found


@pytest.fixture(scope="module")
def notes(byzantine: Mapping[str, Any]) -> list[BoydNote]:
    found: list[BoydNote] = byzantine["tcgnt"]
    return found


@pytest.fixture(scope="module")
def english(byzantine_inputs: Mapping[str, Content]) -> list[BoydNote]:
    return tcent(byzantine_inputs["tcent"])


@pytest.fixture(scope="module")
def splits(tcgnt: Content) -> dict[str, list[str]]:
    return word_breaks(tcgnt / "095XXC.usx")


def changed(path: Content, text: str) -> Content:
    """A file of the same name with other contents."""
    return Content({path.name: text.encode()}) / path.name


# Reading notation.


def test_reading_notation_is_closed_and_retains_primary_words() -> None:
    assert reading_words("ειπε(ν)") == ["eipen"]
    assert reading_words("λευιν (λευειν TH WH)") == ["leuin"]
    assert reading_words("ιβ΄") == ["ib"]
    assert reading_words("δωδεκα … χιλιαδες") is None
    assert reading_words("{include verses 24–26}") is None
    assert reading_words("λεγει (unexplained remark)") is None
    assert reading_words("---") == []


# Robinson's collation.


def test_collation_counts_and_wrapped_omission(coll: list[CollationRow]) -> None:
    assert len(coll) == 1885
    assert [r["entry"] for r in coll] == list(range(1, 1886))
    omitted = next(r for r in coll if r["target_ref"] == "ACT 8:37")
    assert omitted["rp"] == []
    assert omitted["tr"][-3:] == ["ton", "ihsoun", "xriston"]
    # Keep RP2018, not the separate RP2005 row.
    rows = [r for r in coll if r["target_ref"] == "REV 2:17"]
    assert any(r["rp"] == ["tou", "manna"] for r in rows)
    assert not any("(RP 2005)" in r["raw"] for r in rows)
    assert all(r["raw"].count("]") == 1 for r in coll)


def test_collation_entries_are_readings_of_the_two_texts(
    byzantine: Mapping[str, Any], coll: list[CollationRow]
) -> None:
    tr, rp = byzantine["tr"], byzantine["rp"]
    first = coll[0]
    assert first["target_ref"] == "MAT 1:1"
    assert (first["tr"], first["rp"]) == (["dabid"], ["dauid"])
    located = sum(
        1
        for r in coll
        if (not r["tr"] or " ".join(r["tr"]) in " ".join(tr.get(r["target_ref"], [])))
        and (not r["rp"] or " ".join(r["rp"]) in " ".join(rp.get(r["target_ref"], [])))
    )
    # Every entry but the few the ledger lists as unmatched quotes both texts.
    assert located >= 1885 - 5
    assert {r["target_ref"].split()[0] for r in coll} >= {"MAT", "REV", "PHM"}


def test_collation_reader_refuses_a_changed_count(
    byzantine_inputs: Mapping[str, Content],
) -> None:
    path = byzantine_inputs["collation"]
    source = path.read_text()
    shorter = re.sub(r"^1:1\s+δαυιδ \] δαβιδ$", "", source, count=1, flags=re.M)
    assert shorter != source
    with pytest.raises(ValueError, match="Collation inventory"):
        collation(changed(path, shorter))


# Boyd's TCGNT apparatus.


def test_boyd_retains_every_source_note_naming_tr_or_scr(
    tcgnt: Content, notes: list[BoydNote]
) -> None:
    expected: Counter[tuple[str, str, str]] = Counter()
    for book in BOOKS:
        (path,) = tcgnt.glob(f"*{book}.usx")
        for note in ET.fromstring(path.read_bytes()).iter("note"):
            if note.get("style") != "f":
                continue
            fields = [c for c in note if c.get("style") == "fr"]
            if not fields:
                continue
            body = (note.text or "") + "".join(
                ("" if c.get("style") == "fr" else "".join(c.itertext()))
                + (c.tail or "")
                for c in note
            )
            body = " ".join(body.split())
            if re.search(r"(?<!\w)(?:TR|SCR)(?!\w)", body):
                expected[book, "".join(fields[0].itertext()).strip(), body] += 1
    actual = Counter(
        (r["target_ref"].split()[0], r["fr"], r["source_original"]) for r in notes
    )
    assert actual == expected


def test_boyd_main_side_parenthetical_variant_keeps_context(
    notes: list[BoydNote], units: list[Unit]
) -> None:
    (row,) = [r for r in notes if r["target_ref"] == "ACT 10:30"]
    assert row["rp"] == "νηστευων και την ενατην ωραν"
    assert row["tr"] == [{"reading": "νηστευων και την εννατην ωραν", "sigla": ["TR"]}]
    assert "ενατην (εννατην TR)" in row["source_original"]
    assert row["raw"] == row["source_original"]
    (unit,) = [u for u in units if u["id"] == "ACT 10:30#1"]
    assert (unit["tr"], unit["rp"]) == (["ennathn"], ["enathn"])
    assert {
        "inventory": "tcgnt",
        "entry": row["entry"],
        "scope": "unit",
        "hf": "RP",
    } in unit["inventories"]


def test_boyd_preserves_structural_tails_and_repeated_notes(
    notes: list[BoydNote],
) -> None:
    assert len(notes) == 1948
    assert sum(r["hf"] == "RP" for r in notes) == 1798
    assert sum(r["rp_alternate"] for r in notes) == 376
    assert sum(r["patriarchal"] for r in notes) == 530
    assert [r["entry"] for r in notes] == list(range(1, 1949))
    structural = [r for r in notes if r["target_ref"] == "ACT 8:36"]
    assert any("37" in r["tr"][0]["reading"] for r in structural)
    repeated = [r for r in notes if r["target_ref"] == "MAT 1:6" and r["rp"] == "δαυιδ"]
    assert len(repeated) == 2
    positions = [r["position"] for r in repeated]
    assert [p and p["offset"] for p in positions] == [4, 7]
    assert all(p and p["ref"] == "MAT 1:6" for p in positions)


def test_bare_percentages_and_sigla_are_metadata(notes: list[BoydNote]) -> None:
    row = next(r for r in notes if r["target_ref"] == "MAT 4:10")
    assert row["rp"] == "οπισω μου"
    assert "%" not in row["rp"]
    assert all("%" not in v["reading"] for r in notes for v in r["variants"])
    assert all({"TR", "SCR"} & set(v["sigla"]) for r in notes for v in r["tr"])
    first = notes[0]
    assert first["target_ref"] == "MAT 1:1"
    assert (first["rp"], first["tr"][0]["reading"]) == ("δαυιδ", "δαβιδ")
    assert first["hf"] == "TR"
    assert "¦" in first["raw"]
    assert first["source_original"].startswith(first["raw"].split("¦")[0].strip()[:5])


def test_boyd_structural_descriptions_keep_their_braces(notes: list[BoydNote]) -> None:
    romans = {(r["target_ref"], r["rp"], r["tr"][0]["reading"]) for r in notes}
    assert ("ROM 14:24", "{include verses 24–26}", "{omit verses 24–26}") in romans
    assert ("ROM 16:24", "{omit verses 25–27}", "{include verses 25–27}") in romans
    matthew = next(
        r for r in notes if r["target_ref"] == "MAT 23:13" and r["fr"] == "23:13–14"
    )
    assert reading_words(matthew["rp"]) and reading_words(matthew["tr"][0]["reading"])
    mark = [
        r
        for r in notes
        if r["target_ref"] in {"MRK 4:8", "MRK 4:20"} and r["rp"] == "ἐν … ἐν … ἐν"
    ]
    assert [r["tr"][0]["reading"] for r in mark] == ["ἓν … ἓν … ἓν"] * 2
    assert [r["entry"] for r in mark] == [173, 175]


def test_boyd_source_discrepancy_is_kept_as_published(notes: list[BoydNote]) -> None:
    row = next(r for r in notes if r["entry"] == 1627)
    assert row["rp"] == "ισχυσενε"
    assert row["target_ref"] == "REV 12:8"


def test_the_build_leaves_the_notes_as_read(
    tcgnt: Content, notes: list[BoydNote]
) -> None:
    assert boyd(tcgnt) == notes


# Boyd's TCENT English apparatus, same syntax.


def test_tcent_inventory_and_english_passages(english: list[BoydNote]) -> None:
    assert len(english) == 552
    assert len({r["target_ref"] for r in english}) == 489
    assert all(r["position"] is None for r in english)
    first = english[0]
    assert first["target_ref"] == "MAT 3:8"
    assert (first["rp"], first["tr"][0]["reading"], first["hf"]) == (
        "fruit",
        "fruits",
        "RP",
    )
    assert first["source_main_html"] == "Produce fruit consistent with repentance."
    assert first["source_main_passages"] == {"MAT 3:8": first["source_main_html"]}


def test_tcent_own_passage_and_complete_editorial_note_survive_matching(
    english: list[BoydNote],
) -> None:
    row = next(r for r in english if r["target_ref"] == "JHN 10:8")
    assert "stylistic purposes" not in row["raw"]
    assert "stylistic purposes" in row["source_original"]
    assert (row["source_main_html"] or "").startswith(
        "All who came before are thieves and robbers"
    )
    assert "<i>before</i>" in row["source_original_html"]


def test_tcent_cross_verse_source_passage_has_each_address(
    english: list[BoydNote],
) -> None:
    row = next(r for r in english if r["target_ref"] == "ACT 24:6")
    assert row["fr"] == "24:6–8"
    assert set(row["source_main_passages"]) == {"ACT 24:6", "ACT 24:7", "ACT 24:8"}
    # RP has no verse 7; Boyd's main text has nothing at that address.
    assert row["source_main_passages"]["ACT 24:7"] is None
    assert row["source_main_passages"]["ACT 24:6"].startswith(
        "He even tried to desecrate the temple"
    )
    assert row["source_main_passages"]["ACT 24:8"].startswith("By examining him")
    assert "double brackets" in row["source_original"]


def test_tcent_reads_its_one_misprinted_siglum_as_its_tcgnt_note(
    english: list[BoydNote], notes: list[BoydNote]
) -> None:
    # Boyd's TCGNT note on the same reading at Jas 5:11 has ANT for TCENT's ACT.
    row = next(
        r for r in english if r["target_ref"] == "JAS 5:11" and "ACT" in r["raw"]
    )
    greek = next(
        r for r in notes if r["target_ref"] == "JAS 5:11" and "κυριος" in r["raw"]
    )
    assert row["tr"] == [{"reading": "the Lord", "sigla": ["ANT", "CT", "TR"]}]
    assert row["tr"][0]["sigla"] == greek["tr"][0]["sigla"]
    assert row["patriarchal"] and "ACT CT TR" in row["source_original"]


def test_tcent_refuses_the_greek_folder(tcgnt: Content) -> None:
    with pytest.raises(ValueError, match="Changed TCENT inventory"):
        tcent(tcgnt)


# Appendix C word breaks.


def test_appendix_c_splits_preserve_every_letter(splits: dict[str, list[str]]) -> None:
    assert len(splits) == 39
    assert splits["ennenhkontaennea"] == ["ennenhkonta", "ennea"]
    assert splits["epautofwrw"] == ["ep", "autofwrw"]
    assert all(word == "".join(parts) for word, parts in splits.items())
    assert all(len(parts) > 1 for parts in splits.values())


def test_appendix_c_reader_refuses_a_changed_table(tcgnt: Content) -> None:
    path = tcgnt / "095XXC.usx"
    source = path.read_text()
    with pytest.raises(ValueError, match="Missing Appendix C numeral explanation"):
        word_breaks(
            changed(
                path,
                source.replace("for the purposes of comparison", "for comparison", 1),
            )
        )
