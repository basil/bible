"""Canonical Turpie transcription and editorial input checks."""

import copy

import pytest

from bible import quotations
from bible.checks import CheckFailed


def test_complete_review():
    assert len(quotations.reviewed_rows()) == 273


@pytest.mark.parametrize("change", ["missing", "duplicate"])
def test_missing_or_duplicate_heads_are_rejected(patched, change):
    heads = patched(quotations, "TURPIE")["rows"]
    if change == "missing":
        heads.pop()
    else:
        heads.append(copy.deepcopy(heads[0]))
    with pytest.raises(CheckFailed, match="once each in order"):
        quotations.reviewed_rows()


@pytest.mark.parametrize("key,reason", [("Q283", "x"), ("Q001", "")])
def test_exclusion_needs_a_head_and_a_reason(patched, key, reason):
    patched(quotations, "DECISIONS")["excluded"][key] = reason
    with pytest.raises(CheckFailed, match="Exclusion of no Turpie head"):
        quotations.reviewed_rows()


def test_note_merge_decision_needs_a_link(patched):
    merges = patched(quotations, "DECISIONS")["note_merges"]
    merges["GEN 1:1"] = {"action": "merge", "why": "x"}
    with pytest.raises(CheckFailed, match="Note merge decision at no link"):
        quotations.reviewed_rows()


def test_missing_printed_source_heading_is_rejected(patched):
    patched(quotations, "TURPIE")["rows"][0]["hebrew"].pop("printed")
    with pytest.raises(CheckFailed, match="Missing printed Hebrew heading"):
        quotations.reviewed_rows()


def test_appendix_discussion_cannot_be_included(patched):
    del patched(quotations, "DECISIONS")["excluded"]["Q281"]
    with pytest.raises(CheckFailed, match="Unclassified appendix discussion"):
        quotations.reviewed_rows()


def test_a_head_is_linked_only_from_its_printed_heading(patched):
    # Q087's passages are read from Turpie's prose; he heads no source column.
    del patched(quotations, "DECISIONS")["excluded"]["Q087"]
    with pytest.raises(CheckFailed, match="No printed Septuagint heading: Q087"):
        quotations.reviewed_rows()


def test_a_narrowed_head_links_only_its_part():
    [row] = [r for r in quotations.reviewed_rows() if r["id"] == "Q052"]
    assert row["ot"] == ["ISA 8:17"]


@pytest.mark.parametrize("part", ["ISA 8:17-18", "ISA 8:16"])
def test_a_narrowing_must_be_part_of_its_head(patched, part):
    patched(quotations, "DECISIONS")["narrowed"]["Q052"]["lxx"] = part
    with pytest.raises(CheckFailed, match="isn't part of its head: Q052"):
        quotations.reviewed_rows()


@pytest.mark.parametrize("key,why", [("Q283", "x"), ("Q049", "x"), ("Q001", "")])
def test_narrowing_needs_a_linked_head_and_a_reason(patched, key, why):
    patched(quotations, "DECISIONS")["narrowed"][key] = {"lxx": "EXO 20:13", "why": why}
    with pytest.raises(CheckFailed, match="Narrowing of no linked Turpie head"):
        quotations.reviewed_rows()
