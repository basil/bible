"""Canonical Turpie transcription and editorial input checks."""

import pytest
from conftest import changed

from bible import quotations
from bible.checks import CheckFailed


def test_complete_review(policy):
    rows = {row["id"]: row for row in quotations.reviewed_rows(policy=policy)}
    assert len(rows) == 273
    # A narrowed head links only its part.
    assert list(map(str, rows["Q052"]["ot"])) == ["ISA 8:17"]


@pytest.mark.parametrize(
    "change,refusal",
    [
        (lambda heads: heads.pop(), "once each in order"),
        (lambda heads: heads.append(heads[0]), "once each in order"),
        (lambda heads: heads[0]["hebrew"].pop("printed"), "Missing printed Hebrew"),
    ],
)
def test_a_transcription_must_be_whole(policy, change, refusal):
    lacking = changed(policy, "turpie", lambda data: change(data["rows"]))
    with pytest.raises(CheckFailed, match=refusal):
        quotations.reviewed_rows(policy=lacking)


def part(lxx, why="x"):
    return {"lxx": lxx, "why": why}


@pytest.mark.parametrize(
    "section,key,decision,refusal",
    [
        # An exclusion needs a head and a reason.
        ("excluded", "Q283", "x", "Exclusion of no Turpie head"),
        ("excluded", "Q001", "", "Exclusion of no Turpie head"),
        # Without theirs: an appendix discussion has no class, and Q087's
        # passages are read from Turpie's prose; he heads no source column.
        ("excluded", "Q281", None, "Unclassified appendix discussion"),
        ("excluded", "Q087", None, "No printed Septuagint heading: Q087"),
        ("note_merges", "GEN 1:1", {"action": "merge", "why": "x"}, "at no link"),
        # A narrowing is to part of a head that is linked, and has a reason.
        ("narrowed", "Q052", part("ISA 8:17-18"), "isn't part of its head: Q052"),
        ("narrowed", "Q052", part("ISA 8:16"), "isn't part of its head: Q052"),
        ("narrowed", "Q283", part("EXO 20:13"), "Narrowing of no linked Turpie head"),
        ("narrowed", "Q049", part("EXO 20:13"), "Narrowing of no linked Turpie head"),
        ("narrowed", "Q001", part("EXO 20:13", ""), "Narrowing of no linked Turpie"),
    ],
)
def test_a_decision_must_be_of_a_head_and_have_its_reason(
    policy, section, key, decision, refusal
):
    def decide(data):
        if decision is None:
            del data[section][key]
        else:
            data[section][key] = decision

    with pytest.raises(CheckFailed, match=refusal):
        quotations.reviewed_rows(policy=changed(policy, "quotations", decide))
