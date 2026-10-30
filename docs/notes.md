# TODO (Notes)

## Commentary classified as an alternative rendering, and the reverse

All [build]. The inference in `src/bible/notes.py` treats roman words after a
label as a reading. Fix each with a scoped classification decision, or narrow
the inference and read the diff. CCEL pages named are the proof of what is
roman and what is italic.

- [ ] **`HOS 6:4 CCEL`** — "and" in "compare Heb. and Dan. 9:16" exported as
  `\fqa`. CCEL 17.v.htm #8. Confidence: high.
- [ ] **`2CH 2:5 CCEL#2`** — "with" in "compare Heb. and Gr. with Zach.
  6:13" exported as `\fqa`. CCEL 4.ii.htm #3. Confidence: high.
- [ ] **`JER 39:5 CCEL`** — "adopted here" after the Complutensian Greek
  exported as `\fqa`. CCEL 13.xxxix.htm #1. Confidence: high.
- [ ] **`EZK 29:14 CCEL`** — "margin" in "KJV margin" exported as `\fqa`.
  CCEL 15.xxix.htm #3. Confidence: high.
- [ ] **`DAG 1:3 CCEL`** — "Hebrew word." exported as `\ft Hebrew \fqa word`.
  CCEL 16.htm #2. Compare the existing `DAG 11:45 CCEL` override, which keeps
  the same wording roman. Confidence: high.
- [ ] **`EZK 10:5 CCEL`, `EZK 21:2 CCEL`, `EZK 21:2 CCEL#2`, `EZK 29:18 CCEL`**
  — "word(s) in Greek letters" exported as `\fqa`. CCEL 15.ix.htm #6,
  15.xix.htm #16–17, 15.xxix.htm #4. Edition 20:46 (Thaeman/Darom) for the
  21:2 pair. Confidence: high.
- [ ] **`EZK 1:20 CCEL#2`** — "the living creatures probably" wholly `\fqa`;
  "probably" is commentary. CCEL 15.htm #9. Confidence: medium.
- [ ] **Reverse case: `2CH 4:16 CCEL`, `JER 20:2 CCEL`, `EZK 21:26 CCEL`,
  `EZK 26:17 CCEL#2`, `EZK 40:27 CCEL`** — hedged alternatives ("or, perhaps,
  tongs"; "or, possibly stocks"; "perhaps, send forth"; "or, perhaps, her
  traders"; "or, possibly, at the south end") come out entirely roman because
  `COMMENTARY` in `notes.py` rejects perhaps/possibly before the rendering is
  classified. CCEL 4.iv.htm #3, 13.xx.htm #1, 15.xxi.htm #9, 15.xxvi.htm #4,
  15.xl.htm #5. Confidence: high. Fix: adverb as commentary, the replacement
  words as `\fqa`; audit other hedged glosses before changing the rule.
  Repro: `grep -n 'perhaps\|possibly' build/review/notes.md`.

## Notes the 1844 printing gives more fully

[source]. The later Bagster printings and CCEL shortened these; a correction
may recover the 1844 information (AGENTS.md). Pages are 1844 vol. 2 printed
pages (physical = printed − 497 in Ezekiel).

- [ ] **`EZK 21:26 CCEL`** (edition 21:21) — 1844 p. 822 "† Perhaps, bring
  forth, _or,_ send forth." where 1879 p. 1006 and CCEL 15.xxi #9 have
  "Perhaps, send forth." Confidence: high that 1844 differs.
- [ ] **`EZK 29:18 CCEL`** — 1844 p. 832 "† μαδών, _Heb._ word probably in
  Greek letters." where 1879 p. 1034 has "_Heb._ word in Greek letters." Swete
  III p. 447 prints μαδῶν, an ordinary Greek participle, which Brenton's
  "probably" allows for. Confidence: high that 1844 differs.
- [ ] **`EZK 21:2 CCEL`** (edition 20:46) — 1844 p. 821 sets a third † before
  the first "Nageb" for the same "_Heb._ words." note; 1879 p. 1021 and CCEL
  have callers at Thaeman and Darom only. Confidence: medium.

## Lemma scope (which words the note is about)

The adjudication pass settled that a broad contextual lemma around a short
gloss is a convention (`EZK 5:9 CCEL` declares it deliberately), so breadth
alone is not a defect. What remains:

### Editorial judgment

- [ ] **Declared lemma wider than its own rationale: `EXO 18:21`, `DEU 4:9`,
  `JOS 21:4`, `JDG 3:25`, `2SA 14:4`, `1KI 11:33#2`** [editorial] — each
  `why` in `edition/brenton-notes.json` names the narrow glossed word ("Gr.
  them renders the people") while the stored lemma is the whole phrase.
  Confidence: high that the mismatch exists; low that it needs changing.
  Decide once whether the convention is "lemma = glossed words" or "lemma =
  locating phrase", then make these six agree with it.
- [ ] **Boundary cut mid-constituent: `ECC 10:3 CCEL` ("thinketh of is"),
  `AMO 6:10 CCEL` ("a remnant shall")** [editorial] — length-matched lemma
  ends after a copula/auxiliary. Confidence: medium. A decision rather than a
  rule change (see the rejected rule below). The same trial
  turned up `AMO 7:9 CCEL` ("joyful altars shall: Gr. _altars of
  laughter_"), `2CH 36:5c CCEL` ("they should: Gr. _he_, sc. _Juda_"),
  `JOB 13:14 CCEL` ("while I may: Gr. _having taken_") and `1CH 13:4 CCEL`
  ("that they would: Gr. _on account of_"). Confidence: medium; check each
  against its printed caller.
- [ ] **`JOB 31:16 CCEL`** [editorial] — "cause the eye" truncates "cause …
  to fail". Confidence: low.
- [ ] **`ZEP 3:4 CCEL`, `LAM 3:47 CCEL`** [editorial] — lemma takes in a
  second coordinated term ("and scornful men"; "and destruction") the gloss
  does not cover. Lamentations has the stronger case (Luke 12:29 "suspense").
  Confidence: medium.
- [ ] **`PSA 136:1`** [editorial] — "Alex. omits" has no lemma or
  `x-scope`, so it reads as omitting the verse rather than the superscription
  "For David, a Psalm of Jeremias". Decision keeps `agrees: null`.
  Confidence: medium. Fix: a scoped lemma naming the heading.
- [ ] **`PRO 24:22a`** [source then editorial] — "Heb. omits to the end"
  lost its bracket endpoint (eBible closes the bracket after "repent" in
  24:22f) and now sits before a much longer relocated chapter. Confidence:
  medium. Check the printed endpoint, then add a scoped note naming the
  omitted passage. `prose.json` unbracketed-notes handles Esther the same way
  but has no PRO entry.

## Duplicate and misplaced notes

- [ ] **JDG 14:1 and `JDG 14:2 CCEL` (CCEL `vii.xxxix#1`)** [build] — the
  ἀλλόφυλοι/Philistines explanation prints twice. `edition/ccel-notes.json`
  has duplicate decisions for `vii.xxxix#4`, `#8`, `#10` but none for `#1`.
  Confidence: high. Fix: duplicate decision keeping one copy.
  Repro: `grep -n 'JDG 14:[12]' build/review/notes.md`.
- [ ] **`PSA 144:1` and `PSA 144:2`** [source] — identical "lit. to the age"
  note in consecutive verses; eBible has both, CCEL has one caller (9.cxliv
  #4, at verse 1) and `build/review/ccel.md` already treats it as a duplicate
  of 144:1. Confidence: medium. Check: callers in 1844 and later printings;
  if one printed note, omit 144:2 by decision.
- [ ] **`NUM 11:34 CCEL` and `NUM 11:35`** [source] — Graves of Lust gloss in
  adjacent verses; eBible has it at 11:35, CCEL's caller is in 11:34.
  Confidence: medium. Check: printed callers; then one duplicate/placement
  decision keeping the fuller Hebrew gloss.

## Sentence detection (introduced punctuation and case)

Both [build]. `notes.is_sentence` keeps a final stop and capital only when
`FINITE_VERB` matches or a `sentence: true` override exists
(`edition/brenton-notes.json` has 32 such overrides, `ccel-notes.json` none).

- [ ] **NEH 12:36, key `EZR 22:36 CCEL`** — "These terminations often vary."
  prints as "these terminations often vary" (no stop, lowercase) because
  `vary` is absent from `FINITE_VERB` (`src/bible/notes.py:150`).
  Confidence: high. Fix: override or extend the verb list with a corpus
  check.
- [ ] **`PRO 24:22a CCEL`** — "Note. The verses of this chapter are much
  intermingled…" loses its final stop; the opening "Note" label blocks
  detection. Confidence: high. Fix: `sentence: true` as at `GEN 15:11`.

## Spelling, punctuation, and grammar inside notes (inherited)

### Editorial judgment (policy says modernize obsolete spellings in notes too)

- [ ] **`EZK 47:4 CCEL`** — "ancles" twice; ankles. Confidence: high.
- [ ] **`DEU 1:15`** — "instructers"; instructors. Confidence: high.
- [ ] **`2KI 9:10`** — "buryer"; burier. Confidence: high.
- [ ] **`MAT 13:33 measures`** — "little more then a pint"; than. The edition
  already revises "an half" in this note. Confidence: high.
- [ ] **`1SA 30:12`** — "Gr. staid or established"; the stayed/staid rule
  (`revisions.json` "stayed as a verb") covers three verses but not this
  gloss. Confidence: medium (could be adjectival).
- [ ] **`RUT 2:2 CCEL`** — note has American "favor" beside the verse's
  "favour". Confidence: medium. One scoped spelling decision.
- [ ] **Missing possessive apostrophes: `LEV 4:3 CCEL` "peoples sinning",
  `MAT 27:27` "governors house", `ACT 12:20 the kings chaberlaine` "kings
  bedchamber", `ACT 13:1 brought up with Herod` "Herods foster brother",
  `ACT 17:19 Areopagus` "Mars hill"** — all inherited (1611 margin or CCEL).
  Confidence: high that the apostrophe is absent; low priority. Decide
  whether note commentary takes modern possessives at all; if so, scoped
  punctuation revisions in `edition/revisions.json`.
- [ ] **`MRK 7:4 tables`, `MRK 13:8 sorrows`** — 1611 commas "Sextarius, is"
  and "importeth, the pains". Confidence: high that they are inherited; low
  that they should change.

## Cross-references

- The Byzantine review and website omit TR notes for cross-verse readings
  (`HEB 1:1#1`, `2CO 1:6#1`, `COL 1:24#1`): tooling, filed under review and
  website in `todo.md`.
