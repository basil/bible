"""The closed tag vocabulary."""

from __future__ import annotations

from bible.byzantine import tags
from bible.byzantine.tags import LEGEND, WEIGHTS, Grammar, Tag, Wording


def test_legend_covers_every_tag_and_nothing_else() -> None:
    assert set(LEGEND) == set(Tag) | set(Wording) | set(Grammar)
    assert all(isinstance(text, str) and text for text in LEGEND.values())


def test_only_computed_tags_have_prefixes() -> None:
    assert {t.value.split(":")[0] for t in Tag} == {"op", "ev"}
    assert all(":" not in value for value in (*Wording, *Grammar))
    # LEGEND and WEIGHTS share one key space, where equal values would merge.
    assert not {w.value for w in Wording} & {g.value for g in Grammar}


def test_weights_name_real_tags() -> None:
    assert set(WEIGHTS) <= set(Tag) | set(Wording) | set(Grammar)
    assert all(isinstance(w, int) for w in WEIGHTS.values())


def scored(*tagged: str, disposition: str = "witnessed") -> int:
    return tags.score(
        {
            "tags": [t for t in tagged if t in Tag],
            "wording": [t for t in tagged if t in Wording],
            "grammar": [t for t in tagged if t in Grammar],
            "disposition": disposition,
        }
    )


def test_score_sums_weights_and_is_never_negative() -> None:
    assert scored() == 0
    assert scored(Tag.EV_CORROBORATED, Tag.EV_PIERPONT_MANDATORY) == 0
    assert (
        scored("ev:witnesses-disagree", "ev:single-witness")
        == WEIGHTS[Tag.EV_WITNESSES_DISAGREE] + WEIGHTS[Tag.EV_SINGLE_WITNESS]
    )
    assert scored(Wording.KJV_RETAINED) == 0
    assert scored(disposition="override") == 1
    assert scored("ev:corroborated", "ev:revision-agrees", disposition="override") == 0


def test_refusing_an_instruction_adds_controversy_points() -> None:
    assert (
        scored(Tag.EV_INSTRUCTION_REFUSED, disposition="override")
        == scored(disposition="override") + 3
    )


def test_wording_and_grammar_contribute_to_the_score() -> None:
    assert scored(Wording.EDITOR, Grammar.INFLECTION) == 3
