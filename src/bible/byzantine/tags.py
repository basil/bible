"""The closed tag vocabulary: what a disposition and its witnesses are.

Tags come in four groups. `op:` and `ev:` are computed by the build and may
not be written into a decision file; `from:` and `gram:` are the editor's
assertions in the readings of edition/byzantine.json, and the build fills
them in for witnessed units. `LEGEND` defines every tag; a test keeps it
complete.
"""

from __future__ import annotations

from collections.abc import Collection
from enum import StrEnum

from bible.byzantine.rows import Disposition


class Tag(StrEnum):
    # op: what happened to the English
    OP_REPLACE = "op:replace"
    OP_OMIT = "op:omit"
    OP_ADD = "op:add"
    OP_TRANSPOSE = "op:transpose"
    OP_OMIT_VERSE = "op:omit-verse"
    OP_MOVE_VERSE = "op:move-verse"
    OP_SWAP_VERSES = "op:swap-verses"
    OP_NOCHANGE = "op:nochange"
    # from: where the chosen wording comes from
    FROM_PIERPONT = "from:pierpont"
    FROM_ADDITIONAL = "from:additional"
    FROM_KJV_PARALLEL = "from:kjv-parallel"
    FROM_RV = "from:rv"
    FROM_BOYD_ASV = "from:boyd-asv"
    FROM_TCENT = "from:tcent"
    FROM_FAA = "from:faa"
    FROM_EDITOR = "from:editor"
    FROM_KJV_RETAINED = "from:kjv-retained"
    # gram: what kind of difference the English shows
    GRAM_TENSE = "gram:tense"
    GRAM_NUMBER = "gram:number"
    GRAM_PERSON = "gram:person"
    GRAM_MOOD = "gram:mood"
    GRAM_ARTICLE = "gram:article"
    GRAM_NAME = "gram:name"
    GRAM_ORDER = "gram:order"
    GRAM_CONJUNCTION = "gram:conjunction"
    GRAM_PARTICLE = "gram:particle"
    GRAM_PRONOUN = "gram:pronoun"
    GRAM_PREPOSITION = "gram:preposition"
    GRAM_LEXICAL = "gram:lexical"
    GRAM_SUPPLIED_WORD = "gram:supplied-word"
    GRAM_PUNCTUATION = "gram:punctuation"
    GRAM_INFLECTION = "gram:inflection"
    # ev: the shape of the evidence
    EV_CORROBORATED = "ev:corroborated"
    EV_SINGLE_WITNESS = "ev:single-witness"
    EV_WITNESSES_DISAGREE = "ev:witnesses-disagree"
    EV_INSTRUCTION_REFUSED = "ev:instruction-refused"
    EV_HYPER_LITERAL_ONLY = "ev:hyper-literal-only"
    EV_TCENT_REPORTS = "ev:tcent-reports"
    EV_REVISION_AGREES = "ev:revision-agrees"
    EV_REVISION_ALARM = "ev:revision-alarm"
    EV_HF_DIFFERS = "ev:hf-differs"
    EV_RP_ALTERNATE = "ev:rp-alternate"
    EV_PATRIARCHAL_TR = "ev:patriarchal-tr"
    EV_PIERPONT_MANDATORY = "ev:pierpont-mandatory"
    EV_PIERPONT_WEAK = "ev:pierpont-weak"
    EV_KJV_ALREADY = "ev:kjv-already"
    EV_RENDERING_VERIFIED = "ev:lexically-supported"
    EV_RENDERING_UNVERIFIED = "ev:lexically-unresolved"
    EV_FINISHED_VERSE = "ev:finished-verse"
    EV_MULTI_UNIT = "ev:multi-unit"
    EV_SEAM_ADJUSTED = "ev:seam-adjusted"
    EV_UNPLACED_ROW_IN_VERSE = "ev:unplaced-row-in-verse"

    @property
    def group(self) -> str:
        return self.value.split(":", 1)[0]


LEGEND: dict[Tag, str] = {
    Tag.OP_REPLACE: "Words of the KJV are replaced by other words",
    Tag.OP_OMIT: "Words of the KJV are removed",
    Tag.OP_ADD: "Words are added to the KJV",
    Tag.OP_TRANSPOSE: "The same words in another order",
    Tag.OP_OMIT_VERSE: "A whole verse RP does not have is removed",
    Tag.OP_MOVE_VERSE: "A passage stands at another place in RP",
    Tag.OP_SWAP_VERSES: "Two verses exchange places",
    Tag.OP_NOCHANGE: "The Greek differs; the English stands",
    Tag.FROM_PIERPONT: "Wording from Pierpont's Some Improvements",
    Tag.FROM_ADDITIONAL: "Wording from an additional instruction file",
    Tag.FROM_KJV_PARALLEL: "The KJV's own rendering of the same Greek elsewhere",
    Tag.FROM_RV: "Wording from the Revised Version of 1881",
    Tag.FROM_BOYD_ASV: "Wording from Boyd's ASV conformed to RP2018",
    Tag.FROM_TCENT: "Wording from Boyd's TCENT apparatus",
    Tag.FROM_FAA: "Wording from Thomason's Far Above All",
    Tag.FROM_EDITOR: "Wording composed by the editor in KJV register",
    Tag.FROM_KJV_RETAINED: "The KJV's words are kept",
    Tag.GRAM_TENSE: "A verb's tense or aspect changes",
    Tag.GRAM_NUMBER: "Singular and plural exchange",
    Tag.GRAM_PERSON: "Grammatical person changes (we/ye, our/your)",
    Tag.GRAM_MOOD: "A verb's mood or modality changes",
    Tag.GRAM_ARTICLE: "An article is added, dropped or changed",
    Tag.GRAM_NAME: "A proper name differs",
    Tag.GRAM_ORDER: "Word order differs",
    Tag.GRAM_CONJUNCTION: "A conjunction is added, dropped or changed",
    Tag.GRAM_PARTICLE: "A particle (also, even, therefore) changes",
    Tag.GRAM_PRONOUN: "A pronoun is added, dropped or changed",
    Tag.GRAM_PREPOSITION: "A preposition changes",
    Tag.GRAM_LEXICAL: "A different word or phrase",
    Tag.GRAM_SUPPLIED_WORD: "Only a KJV supplied (italic) word is affected",
    Tag.GRAM_PUNCTUATION: "Punctuation or accent only",
    Tag.GRAM_INFLECTION: "An inflection not yet classified (a review pass refines it)",
    Tag.EV_CORROBORATED: "Two or more independent witnesses give this change",
    Tag.EV_SINGLE_WITNESS: "One witness alone gives this change",
    Tag.EV_WITNESSES_DISAGREE: "Witnesses disagree on the English",
    Tag.EV_INSTRUCTION_REFUSED: "An override departs from a bound, compatible instruction",
    Tag.EV_HYPER_LITERAL_ONLY: "Only FAA, MSB or WEB report the difference",
    Tag.EV_TCENT_REPORTS: "Boyd's English apparatus reports the difference",
    Tag.EV_REVISION_AGREES: "The RV or Boyd's ASV made the same change",
    Tag.EV_REVISION_ALARM: "The RV and Boyd's ASV both lack the KJV words of an unreported unit",
    Tag.EV_HF_DIFFERS: "Hodges-Farstad does not read with RP here",
    Tag.EV_RP_ALTERNATE: "The TR reading is RP's own marginal alternate",
    Tag.EV_PATRIARCHAL_TR: "The Patriarchal text of 1904 reads with the TR",
    Tag.EV_PIERPONT_MANDATORY: "Pierpont weight 5, 4, b, c or d; or 70 percent and above in Revelation",
    Tag.EV_PIERPONT_WEAK: "Pierpont weight 1 or 2, or below 60 percent in Revelation",
    Tag.EV_KJV_ALREADY: "The KJV already reads the Majority wording",
    Tag.EV_RENDERING_VERIFIED: "The KJV's own usage ties the changed words to Greek RP2026 changes (evidence, not proof of a correct rendering)",
    Tag.EV_RENDERING_UNVERIFIED: "No Greek in the verse is tagged as rendering the changed words; the wording rests on its witness and on review",
    Tag.EV_FINISHED_VERSE: "The finished verse fails a join check, or a note that does not restore the KJV's words",
    Tag.EV_MULTI_UNIT: "The decision covers several Greek units",
    Tag.EV_SEAM_ADJUSTED: "Deletion punctuation was adjusted at the edit's edge",
    Tag.EV_UNPLACED_ROW_IN_VERSE: "A witness row in this verse is attached to no unit",
}

# How much a tag raises (or lowers) a unit's call for human attention.
WEIGHTS: dict[Tag, int] = {
    Tag.EV_WITNESSES_DISAGREE: 3,
    Tag.EV_INSTRUCTION_REFUSED: 3,
    Tag.EV_TCENT_REPORTS: 3,  # only counted on a silent unit; see decide
    Tag.EV_SINGLE_WITNESS: 2,
    Tag.EV_REVISION_ALARM: 2,
    Tag.EV_HF_DIFFERS: 2,
    Tag.EV_RENDERING_UNVERIFIED: 2,
    Tag.EV_FINISHED_VERSE: 3,
    Tag.FROM_EDITOR: 2,
    Tag.EV_HYPER_LITERAL_ONLY: 1,
    Tag.EV_RP_ALTERNATE: 1,
    Tag.EV_PATRIARCHAL_TR: 1,
    Tag.EV_PIERPONT_WEAK: 1,
    Tag.EV_MULTI_UNIT: 1,
    Tag.EV_SEAM_ADJUSTED: 1,
    Tag.EV_UNPLACED_ROW_IN_VERSE: 1,
    Tag.GRAM_INFLECTION: 1,
    Tag.EV_CORROBORATED: -1,
    Tag.EV_PIERPONT_MANDATORY: -1,
    Tag.EV_REVISION_AGREES: -1,
    Tag.EV_RENDERING_VERIFIED: -1,
}

COMPUTED_GROUPS = {"op", "ev"}
ASSERTED_GROUPS = {"from", "gram"}


def score(row: Disposition) -> int:
    """The row's controversy score, for the review: the sum of its tags'
    weights, and one for an override, never negative."""
    total = sum(WEIGHTS.get(Tag(t), 0) for t in row["tags"])
    return max(total + (row["disposition"] == "override"), 0)


def retag(row: Disposition, tag: Tag) -> None:
    """Add a computed tag to a disposition row."""
    row["tags"] = sorted(set(row["tags"]) | {tag.value})


def asserted(tags: Collection[str]) -> list[Tag]:
    """Fail on a tag the editor may not write: unknown, or computed by the build."""
    for t in tags:
        tag = Tag(t)
        if tag.group not in ASSERTED_GROUPS:
            raise ValueError(f"tag is computed by the build, not asserted: {t}")
    return [Tag(t) for t in tags]
