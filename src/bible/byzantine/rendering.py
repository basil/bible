"""Does an instruction's English render what RP2026 changed?

An instruction binds to KJV words and attaches to a Greek unit; neither says
that the words it removes render Greek RP2026 lacks, or that the words it
adds render Greek RP2026 has. This module asks that, word by word, from the
KJV's own usage: CrossWire tags every KJV phrase with the Strong's number of
the Greek it renders, so `lexicon` knows which English words render which
Greek lemma anywhere in the New Testament.

For one edit:
- an omission is *contradicted* when a word it removes renders Greek inside
  its own unit and RP2026's side keeps the same lemma as often, or when it
  extends into neighbouring Greek that both texts retain:
  Rev 7:5, where RP keeps Judah's participle "sealed" in another gender;
- an addition is *contradicted* when the verse would hold more of a word
  it adds than RP2026 has
  Greek to render it: Rev 4:8, nine "holy" for three ἅγιος;
- a word with evidence for it is *verified*; one with none either way is
  *unverified*.
Function words (articles, conjunctions, prepositions, pronouns, auxiliaries)
are not tested: English uses them for grammar, not for single Greek words.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence

from bible.byzantine.crosswire import (
    FUNCTION_WORDS,
    Aligned,
    Tagged,
    edit_offsets,
    equal_positions,
    words,
)
from bible.byzantine.greek import MarginalAlternate, Structure, occurrences
from bible.byzantine.rows import InstructionEdit, Token, Unit

SUFFIXES = ("eth", "est", "ing", "ed", "es", "s", "en", "e")

# A verse's Greek as the check reads it: each word with its Strong's numbers
# and its parsings.
Lemmas = list[tuple[str, set[int], set[str]]]


def stems(word: str) -> set[str]:
    """The word and its plausible stems, lower case, for matching KJV forms."""
    w = word.lower().strip("[]’'").removesuffix("’s").removesuffix("'s")
    found = {w}
    for suffix in SUFFIXES:
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            found.add(w[: -len(suffix)])
    if w.endswith("ied"):
        found.add(w[:-3] + "y")
    return found


def content(text: str) -> list[str]:
    """The content words of an English phrase, supplied [brackets] excluded."""
    text = re.sub(r"\[[^\]]*\]", " ", text)
    return [w for w in words(text) if w not in FUNCTION_WORDS and not w.isdigit()]


def lexicon(
    crosswire: Mapping[str, Tagged],
) -> tuple[dict[int, set[str]], dict[int, set[str]]]:
    """Strong's number -> the stems of every KJV word CrossWire tags with it:
    without function words (for refusal), and with them (for evidence)."""
    found: defaultdict[int, set[str]] = defaultdict(set)
    full: defaultdict[int, set[str]] = defaultdict(set)
    # The article is tagged together with its noun throughout, so it would
    # "render" almost every word; it renders none here.
    article = 3588
    for row in crosswire.values():
        text = row["text"]
        for link in row["links"]:
            if not link.get("strongs"):
                continue
            phrase = [
                (w, stems(w)) for w in words(text[link["range"][0] : link["range"][1]])
            ]
            for n in link["strongs"]:
                if n == article or n > 5624:
                    continue
                for w, forms in phrase:
                    full[n] |= forms
                    if w not in FUNCTION_WORDS:
                        found[n] |= forms
    return found, full


class Checker:
    """Renders one verdict per edit from the pinned texts and their tags."""

    def __init__(
        self,
        crosswire: Mapping[str, Tagged],
        aligned: Mapping[str, Aligned],
        tr: Mapping[str, list[str]],
        rp: Mapping[str, list[str]],
        tr_tags: Mapping[str, list[Token]],
        rp_tags: Mapping[str, list[Token]],
        units: Sequence[Unit],
        kjv: Mapping[str, str],
        structure: Structure,
        alternates: Mapping[str, list[MarginalAlternate]] | None = None,
    ) -> None:
        self.structure = structure
        self.alternates = alternates or {}
        self.lexicon, self.full = lexicon(crosswire)
        self.kjv = kjv
        self.aligned, self.tr, self.rp = aligned, tr, rp
        self.tr_tags, self.rp_tags = tr_tags, rp_tags
        self.by_ref: defaultdict[str, list[Unit]] = defaultdict(list)
        for u in units:
            if u.get("kind") != "relocation":
                self.by_ref[u["ref"]].append(u)
        self.by_id = {u["id"]: u for u in units}

    def tokens(self, side: str, ref: str) -> Lemmas | None:
        """[(word, strong's numbers, parses)] for a verse, or None if the tags
        do not match the text word for word."""
        if side == "tr":
            words_, tags = self.tr[ref], self.tr_tags.get("TR " + ref)
        else:
            target = self.structure.rp_ref(ref)
            words_, tags = self.rp[target], self.rp_tags.get(target)
        if not tags or [t["word"] for t in tags] != words_:
            return None
        # Numbers above 5624 in the tags are Robinson's tense codes, not lemmas.
        return [
            (
                t["word"],
                {n for n in t.get("strong", []) if 0 < n <= 5624},
                set(t.get("parse", [])),
            )
            for t in tags
        ]

    def renders(self, word: str, strong_sets: Iterable[Iterable[int]]) -> bool:
        mine = stems(word)
        return any(
            mine & self.lexicon.get(n, set())
            for numbers in strong_sets
            for n in numbers
        )

    def applied(self, ref: str, edits: Iterable[InstructionEdit]) -> str:
        """The verse text after a set of edits on it, by their word ranges."""
        verse = self.kjv.get(ref, "")
        planned = sorted(
            (edit_offsets(verse, e) + (e["new"],) for e in edits if e["ref"] == ref),
            reverse=True,
        )
        for lo, hi, new in planned:
            verse = verse[:lo] + " " + new + " " + verse[hi:]
        return verse

    def check(
        self,
        edit: InstructionEdit,
        unit_ids: Iterable[str],
        group: Sequence[InstructionEdit] | None = None,
    ) -> tuple[str, str | None]:
        """(verdict, reason) for one bound, attached edit. With `group`, the
        edits of its whole construction in the verse: a word one edit removes
        and another puts back is moved, not omitted or added, and counts are
        taken from the verse after the whole construction."""
        ref = edit["ref"]
        attached = [self.by_id[u] for u in unit_ids if u in self.by_id]
        units = self.by_ref[ref]
        tr_tok, rp_tok = self.tokens("tr", ref), self.tokens("rp", ref)
        verse = self.kjv.get(ref, "")
        evidence = 0
        old_words, new_words = Counter(content(edit.get("old", ""))), Counter(
            content(edit.get("new", ""))
        )
        removed, added = old_words - new_words, new_words - old_words
        group = [e for e in (group or [edit]) if e["ref"] == ref]
        whole_after = self.applied(ref, group)
        if len(group) > 1:
            before_c, after_c = Counter(content(self.kjv.get(ref, ""))), Counter(
                content(whole_after)
            )
            removed &= before_c - after_c
            added &= after_c - before_c
        marginal = self.marginal(edit, ref)
        if marginal:
            return "contradicted", marginal
        # An omission removes words; the Greek they render must be what RP drops.
        bridge = self.aligned.get(ref)
        if edit["kind"] == "delete" and removed and bridge and tr_tok and rp_tok:
            english = words(verse)
            i, j = edit["word_range"]
            for k in range(i, min(j, len(bridge["direct"]))):
                if english[k] not in removed or not bridge["direct"][k]:
                    continue
                inside = [
                    u
                    for u in attached
                    if all(
                        u["tr_range"][0] <= p < u["tr_range"][1]
                        for p in bridge["direct"][k]
                    )
                ]
                if not inside:
                    # A bound omission can extend beyond its unit. Do not
                    # let the removed reading authorize deleting neighbouring
                    # retained Greek. CrossWire groups phrases, so first allow
                    # a word the omitted Greek itself can render ("Now" in
                    # Mark 12:20 is tagged with "there were", not omitted oun).
                    omitted = [
                        tr_tok[p][1]
                        for u in attached
                        if not u["rp"]
                        for p in range(*u["tr_range"])
                    ]
                    changed_tr = {p for u in units for p in range(*u["tr_range"])}
                    positions = bridge["direct"][k]
                    if (
                        all(p not in changed_tr for p in positions)
                        and self.renders(english[k], [tr_tok[p][1] for p in positions])
                        and not self.renders(english[k], omitted)
                    ):
                        return (
                            "contradicted",
                            f"RP2026 keeps the Greek that '{english[k]}' renders outside the attached unit",
                        )
                    continue
                u = inside[0]
                tr_lemmas = Counter(
                    n for p in range(*u["tr_range"]) for n in tr_tok[p][1]
                )
                rp_lemmas = Counter(
                    n for q in range(*u["rp_range"]) for n in rp_tok[q][1]
                )
                lemmas = {n for p in bridge["direct"][k] for n in tr_tok[p][1]}
                if lemmas and all(rp_lemmas[n] >= tr_lemmas[n] for n in lemmas):
                    return (
                        "contradicted",
                        f"RP2026 keeps the Greek that '{english[k]}' renders (G{min(lemmas)} in {u['id']})",
                    )
                evidence += 1
        # An addition adds words; the verse may not end up with more of a word
        # than RP2026 has Greek it can render, even where RP adds that lemma.
        if added:
            if rp_tok is None:
                return "unverified", "no tagged RP text for the verse"
            changed_rp = {q for u in units for q in range(*u["rp_range"])}
            changed = [rp_tok[q][1] for q in sorted(changed_rp) if q < len(rp_tok)]
            names = any("N-PRI" in rp_tok[q][2] for q in changed_rp if q < len(rp_tok))
            after = whole_after
            for w, count in added.items():
                mine = stems(w)
                in_verse = sum(1 for x in words(after) if stems(x) & mine)
                greek = sum(1 for _, numbers, _ in rp_tok if self.renders(w, [numbers]))
                before = sum(1 for x in words(verse) if stems(x) & mine)
                # A change of form (kingdoms -> kingdom) is not an added
                # occurrence, even when the KJV already repeats the rendering
                # of one Greek word elsewhere in the sentence (Rev 11:15).
                if greek and in_verse > greek and in_verse > before:
                    return (
                        "contradicted",
                        f"the verse would have {in_verse} '{w}' for {greek} Greek word(s) RP2026 has that render it",
                    )
                if self.renders(w, changed) or (
                    names and any(c.isupper() for c in w[:1] + edit["new"][:1])
                ):
                    evidence += 1
        if not evidence:
            evidence = self.function_evidence(
                edit, attached, bridge, tr_tok, rp_tok, verse
            )
        return (
            ("verified", None)
            if evidence
            else (
                "unverified",
                "no Greek in the verse is tagged as rendering the changed words",
            )
        )

    def function_evidence(
        self,
        edit: InstructionEdit,
        attached: Sequence[Unit],
        bridge: Aligned | None,
        tr_tok: Lemmas | None,
        rp_tok: Lemmas | None,
        verse: str,
    ) -> int:
        """Positive evidence from function words: a removed word CrossWire ties
        to the unit's changed Greek, or an added word the unit's new Greek is
        rendered by elsewhere (and the article for an added article)."""
        found = 0
        if bridge and edit["kind"] in {"delete", "replace"}:
            i, j = edit["word_range"]
            for k in range(i, min(j, len(bridge["direct"]))):
                if any(
                    u["tr_range"][0] <= p < u["tr_range"][1]
                    for p in bridge["direct"][k]
                    for u in attached
                    if u["tr_range"][0] < u["tr_range"][1]
                ):
                    found += 1
        if rp_tok and edit["kind"] in {"insert", "replace"}:
            new = set(words(re.sub(r"\[[^\]]*\]", " ", edit["new"]))) - set(
                words(edit.get("old", ""))
            )
            changed = [
                rp_tok[q][1]
                for u in attached
                for q in range(*u["rp_range"])
                if q < len(rp_tok)
            ]
            for w in new:
                if w in {"the", "a", "an"} and any(
                    3588 in numbers for numbers in changed
                ):
                    found += 1
                elif any(
                    stems(w) & self.full.get(n, set())
                    for numbers in changed
                    for n in numbers
                ):
                    found += 1
        return found

    def marginal(self, edit: InstructionEdit, ref: str) -> str | None:
        """The edit renders RP's marginal alternate, not its main text: every
        KJV word it removes or replaces renders Greek both texts share, and
        that Greek is the main side of one `{B main > alternate}` group that
        touches no unit (Rev 3:1, 8:3, 13:10; John 6:39)."""
        bridge = self.aligned.get(ref)
        groups = self.alternates.get(self.structure.rp_ref(ref), [])
        if not groups or not bridge or edit["kind"] not in {"delete", "replace"}:
            return None
        tr_words = self.tr.get(ref, [])
        rp_words = self.rp.get(self.structure.rp_ref(ref), [])
        to_rp = equal_positions(tr_words, rp_words)
        in_units = {p for u in self.by_ref[ref] for p in range(*u["tr_range"])}
        i, j = edit["word_range"]
        positions = {
            p
            for k in range(i, min(j, len(bridge["direct"])))
            for p in bridge["direct"][k]
        }
        if (
            not positions
            or positions & in_units
            or any(p not in to_rp for p in positions)
        ):
            return None
        rp_positions = {to_rp[p] for p in positions}
        changed_rp = {q for u in self.by_ref[ref] for q in range(*u["rp_range"])}
        for g in groups:
            # The margins are RP2018's: a group stands at the occurrence of
            # its main words in RP2026 nearest its RP2018 place (Appendix A
            # shifted Rev 11:16 and 13:14 by a word); one whose words RP2026
            # no longer prints says nothing.
            starts = occurrences(rp_words, g["main"])
            if not starts:
                continue
            a = min(starts, key=lambda s: abs(s - g["range"][0]))
            b = a + len(g["main"])
            # A margin that spans a real difference (Acts 21:8) is not this case.
            if rp_positions <= set(range(a, b)) and not changed_rp & set(range(a, b)):
                alternate = " ".join(g["alternate"]) or "omits them"
                return f"follows RP's marginal reading ({' '.join(g['main'])} > {alternate}); its main text keeps the Greek these words render"
        return None
