"""The closed tag vocabulary: what a disposition and its witnesses are.

The build computes `op:` and `ev:` tags. Wording sources and kinds of
grammatical difference are separate fields, asserted in the readings of
edition/byzantine.json and filled in by the build for witnessed units.
`LEGEND` defines every value; a test keeps it complete.
"""

from __future__ import annotations

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


class Wording(StrEnum):
    # where the chosen wording comes from
    PIERPONT = "pierpont"
    ADDITIONAL = "additional"
    KJV_PARALLEL = "kjv-parallel"
    RV = "rv"
    BOYD_ASV = "boyd-asv"
    TCENT = "tcent"
    FAA = "faa"
    EDITOR = "editor"
    KJV_RETAINED = "kjv-retained"


class Grammar(StrEnum):
    # what kind of difference the English shows
    TENSE = "tense"
    NUMBER = "number"
    PERSON = "person"
    MOOD = "mood"
    ARTICLE = "article"
    NAME = "name"
    ORDER = "order"
    CONJUNCTION = "conjunction"
    PARTICLE = "particle"
    PRONOUN = "pronoun"
    PREPOSITION = "preposition"
    LEXICAL = "lexical"
    SUPPLIED_WORD = "supplied-word"
    PUNCTUATION = "punctuation"
    INFLECTION = "inflection"


LEGEND: dict[Tag | Wording | Grammar, str] = {
    Tag.OP_REPLACE: "Words of the KJV are replaced by other words",
    Tag.OP_OMIT: "Words of the KJV are removed",
    Tag.OP_ADD: "Words are added to the KJV",
    Tag.OP_TRANSPOSE: "The same words in another order",
    Tag.OP_OMIT_VERSE: "A whole verse RP does not have is removed",
    Tag.OP_MOVE_VERSE: "A passage stands at another place in RP",
    Tag.OP_SWAP_VERSES: "Two verses exchange places",
    Tag.OP_NOCHANGE: "The Greek differs; the English stands",
    Wording.PIERPONT: "Wording from Pierpont's Some Improvements",
    Wording.ADDITIONAL: "Wording from an additional instruction file",
    Wording.KJV_PARALLEL: "The KJV's own rendering of the same or a like construction",
    Wording.RV: "Wording from the Revised Version of 1881",
    Wording.BOYD_ASV: "Wording from Boyd's ASV conformed to RP2018",
    Wording.TCENT: "Wording from Boyd's TCENT apparatus",
    Wording.FAA: "Wording from Thomason's Far Above All",
    Wording.EDITOR: "Wording composed by the editor in KJV register",
    Wording.KJV_RETAINED: "The KJV's words are kept",
    Grammar.TENSE: "A verb's tense or aspect changes",
    Grammar.NUMBER: "Singular and plural exchange",
    Grammar.PERSON: "Grammatical person changes (we/ye, our/your)",
    Grammar.MOOD: "A verb's mood or modality changes",
    Grammar.ARTICLE: "An article is added, dropped or changed",
    Grammar.NAME: "A proper name differs",
    Grammar.ORDER: "Word order differs",
    Grammar.CONJUNCTION: "A conjunction is added, dropped or changed",
    Grammar.PARTICLE: "A particle (also, even, therefore) changes",
    Grammar.PRONOUN: "A pronoun is added, dropped or changed",
    Grammar.PREPOSITION: "A preposition changes",
    Grammar.LEXICAL: "A different word or phrase",
    Grammar.SUPPLIED_WORD: "Only a KJV supplied (italic) word is affected",
    Grammar.PUNCTUATION: "Punctuation or accent only",
    Grammar.INFLECTION: "An inflection not yet classified (a review pass refines it)",
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
    Tag.EV_PIERPONT_MANDATORY: "Pierpont weight 5, 4, b, c, or d; or 70 percent and above in Revelation",
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
WEIGHTS: dict[Tag | Wording | Grammar, int] = {
    Tag.EV_WITNESSES_DISAGREE: 3,
    Tag.EV_INSTRUCTION_REFUSED: 3,
    Tag.EV_TCENT_REPORTS: 3,  # only counted on a silent unit; see decide
    Tag.EV_SINGLE_WITNESS: 2,
    Tag.EV_REVISION_ALARM: 2,
    Tag.EV_HF_DIFFERS: 2,
    Tag.EV_RENDERING_UNVERIFIED: 2,
    Tag.EV_FINISHED_VERSE: 3,
    Wording.EDITOR: 2,
    Tag.EV_HYPER_LITERAL_ONLY: 1,
    Tag.EV_RP_ALTERNATE: 1,
    Tag.EV_PATRIARCHAL_TR: 1,
    Tag.EV_PIERPONT_WEAK: 1,
    Tag.EV_MULTI_UNIT: 1,
    Tag.EV_SEAM_ADJUSTED: 1,
    Tag.EV_UNPLACED_ROW_IN_VERSE: 1,
    Grammar.INFLECTION: 1,
    Tag.EV_CORROBORATED: -1,
    Tag.EV_PIERPONT_MANDATORY: -1,
    Tag.EV_REVISION_AGREES: -1,
    Tag.EV_RENDERING_VERIFIED: -1,
}


def score(row: Disposition) -> int:
    """The row's controversy score, for the review: the sum of its tag, wording, and grammar
    weights, and one for an override, never negative."""
    total = (
        sum(WEIGHTS.get(Tag(t), 0) for t in row["tags"])
        + sum(WEIGHTS.get(Wording(w), 0) for w in row["wording"])
        + sum(WEIGHTS.get(Grammar(g), 0) for g in row["grammar"])
    )
    return max(total + (row["disposition"] == "override"), 0)


def tagged(row: Disposition, tag: Tag) -> Disposition:
    """The disposition row with a computed tag added."""
    return {**row, "tags": sorted(set(row["tags"]) | {tag.value})}
