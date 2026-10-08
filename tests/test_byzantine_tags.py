"""The closed tag vocabulary."""

from __future__ import annotations

import pytest

from bible.byzantine import tags
from bible.byzantine.tags import LEGEND, WEIGHTS, Tag


def test_legend_covers_every_tag_and_nothing_else() -> None:
    assert set(LEGEND) == set(Tag)
    assert all(isinstance(text, str) and text for text in LEGEND.values())


def test_every_tag_belongs_to_one_of_four_groups() -> None:
    assert {t.group for t in Tag} == {"op", "from", "gram", "ev"}
    assert tags.COMPUTED_GROUPS | tags.ASSERTED_GROUPS == {"op", "from", "gram", "ev"}
    for tag in Tag:
        assert tag.value == f"{tag.group}:{tag.value.split(':', 1)[1]}"
        assert tag.value == tag.value.lower()


def test_weights_name_real_tags() -> None:
    assert set(WEIGHTS) <= set(Tag)
    assert all(isinstance(w, int) for w in WEIGHTS.values())


def test_asserted_accepts_from_and_gram_tags() -> None:
    assert tags.asserted(["from:pierpont", "gram:tense"]) == [
        Tag.FROM_PIERPONT,
        Tag.GRAM_TENSE,
    ]
    assert tags.asserted([]) == []


@pytest.mark.parametrize(
    "tag", ["op:omit", "ev:corroborated", "op:nochange", "ev:single-witness"]
)
def test_asserted_rejects_computed_tags(tag: str) -> None:
    with pytest.raises(ValueError, match="computed by the build"):
        tags.asserted([tag])


def test_asserted_rejects_an_unknown_tag() -> None:
    with pytest.raises(ValueError):
        tags.asserted(["from:nowhere"])
    with pytest.raises(ValueError):
        tags.asserted(["tier:A"])


def scored(*tagged: str, disposition: str = "witnessed") -> int:
    return tags.score({"tags": list(tagged), "disposition": disposition})


def test_score_sums_weights_and_is_never_negative() -> None:
    assert scored() == 0
    assert scored(Tag.EV_CORROBORATED, Tag.EV_PIERPONT_MANDATORY) == 0
    assert (
        scored("ev:witnesses-disagree", "ev:single-witness")
        == WEIGHTS[Tag.EV_WITNESSES_DISAGREE] + WEIGHTS[Tag.EV_SINGLE_WITNESS]
    )
    assert scored("from:kjv-retained") == 0
    assert scored(disposition="override") == 1
    assert scored("ev:corroborated", "ev:revision-agrees", disposition="override") == 0


def test_refusing_an_instruction_adds_controversy_points() -> None:
    assert (
        scored(Tag.EV_INSTRUCTION_REFUSED, disposition="override")
        == scored(disposition="override") + 3
    )
