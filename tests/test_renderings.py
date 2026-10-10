"""A gloss of Brenton's promoted into his text keeps the former words in its note."""

from __future__ import annotations

import copy

import pytest

from bible import pipeline, policy, renderings, scripture, usj
from bible.checks import CheckFailed


def test_brenton_rendering(read: pipeline.Read, declared: policy.Policy) -> None:
    original = read.brenton["PSA"]
    before = copy.deepcopy(original)
    result = renderings.brenton("PSA", original, declared.brenton_notes["renderings"])
    verses = scripture.verses(result)
    assert (
        verses["67:16"].text
        == "The mountain of God is a rich mountain; a mountain curdled like cheese, a rich mountain."
    )
    assert verses["67:17"].text == scripture.verses(original)["67:17"].text
    note = verses["67:16"].notes[0][1]
    assert note["x-key"] == "PSA 67:16"
    assert note["x-scope"]["declared"] == "mountain curdled like cheese"
    assert usj.text_of(note["content"]) == "67:16 Or, swelling mountain"
    assert original == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("from", "a wrong mountain"),
        ("source_note", "wrong note"),
        ("to", "a swelling mountain"),
        ("lemma", "rich mountain"),
    ],
)
def test_stale_brenton_rendering(
    read: pipeline.Read, declared: policy.Policy, field: str, value: str
) -> None:
    decisions = policy.thaw(declared.brenton_notes["renderings"])
    decisions["PSA 67:16"][field] = value
    with pytest.raises(CheckFailed):
        renderings.brenton("PSA", read.brenton["PSA"], decisions)
