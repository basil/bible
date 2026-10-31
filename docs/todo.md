# TODO

Everything still to do in the text and the notes, apart from names and
spelling, which are in [spelling.md](spelling.md).

## Notes: lemmas and their glosses

Which words a note is about, and whether its gloss can stand in for them.
The adjudication pass settled that a broad contextual lemma around a short
gloss is a convention (`EZK 5:9 CCEL` declares it deliberately), so breadth
alone is not a defect. What remains is editorial judgment.

- [ ] **Declared lemma wider than its own rationale: `EXO 18:21`, `DEU 4:9`,
  `JOS 21:4`, `JDG 3:25`, `2SA 14:4`, `1KI 11:33#2`** [editorial] — each
  `why` in `edition/brenton-notes.json` names the narrow glossed word ("Gr.
  them renders the people") while the stored lemma is the whole phrase.
  Confidence: high that the mismatch exists; low that it needs changing.
  Decide once whether the convention is "lemma = glossed words" or "lemma =
  locating phrase", then make these six agree with it.
- [ ] **`2KI 19:11 CCEL`** [editorial] — "waste them utterly" accepts
  "curse them", but the second gloss "devote to destruction" omits the
  object under strict substitution. Check whether its role needs a scoped
  treatment; do not pad the source wording automatically.
- [ ] **`PSA 35:3 CCEL`** [editorial] — substituting "with regard to the
  discovering" for "to discover" leaves "his iniquity and hate it" with
  doubtful coordination. Judge the complete sentence, allowing the older
  verbal-gerund construction; quotation styling is only a possible outcome.
- [ ] **`PSA 136:1`** [editorial] — "Alex. omits" has no lemma or
  `x-scope`, so it reads as omitting the verse rather than the superscription
  "For David, a Psalm of Jeremias". Decision keeps `agrees: null`.
  Confidence: medium. Fix: a scoped lemma naming the heading.
- [ ] **`JOB 31:16 CCEL`** [editorial] — "cause the eye" truncates "cause …
  to fail". Confidence: low.
- [ ] **`PRO 24:22a`** [source then editorial] — "Heb. omits to the end"
  lost its bracket endpoint (eBible closes the bracket after "repent" in
  24:22f) and now sits before a much longer relocated chapter. Confidence:
  medium. The printed endpoint is checked: Brenton 1879 physical p. 827
  (printed p. 811) closes the bracket after "repent.]", inside the edition's
  22f (printed 30:1). Add a scoped note naming the omitted passage.
  `prose.json` unbracketed-notes handles Esther the same way but has no PRO
  entry. The verse-level `PRO 24:22a CCEL` "The verses of this chapter…"
  note beside it is settled and independent.
- [ ] **Boundary cut mid-constituent: `ECC 10:3 CCEL` ("thinketh of is"),
  `AMO 6:10 CCEL` ("a remnant shall")** [editorial] — length-matched lemma
  ends after a copula/auxiliary. Confidence: medium. A decision rather than a
  rule change. The same trial turned up `AMO 7:9 CCEL` ("joyful altars
  shall: Gr. _altars of laughter_"), `2CH 36:5c CCEL` ("they should: Gr.
  _he_, sc. _Juda_"), `JOB 13:14 CCEL` ("while I may: Gr. _having taken_")
  and `1CH 13:4 CCEL` ("that they would: Gr. _on account of_"). Confidence:
  medium; check each against its printed caller.
- [ ] **`ZEP 3:4 CCEL`, `LAM 3:47 CCEL`** [editorial] — lemma takes in a
  second coordinated term ("and scornful men"; "and destruction") the gloss
  does not cover. Lamentations has the stronger case (Luke 12:29 "suspense").
  Confidence: medium.

## Authored matter

- [ ] **Introduction, Conforming the King James Text
  (`content/introduction.sfm:61`)** [build] — says RV wording is taken only
  where Westcott and Hort agree with the Byzantine reading, but
  `build/review/byzantine.md` lists five manual RV borrowings outside that
  rule: MRK 1:16#1, MRK 6:9#1, REV 2:3#1–2, REV 7:4#1–2, REV 13:8#1.
  Confidence: high. Fix: say agreement gates automatic admission and that
  judged borrowing is recorded by decision. (Memory: introduction-style-rules.)
- [ ] **Order of the Psalter (`content/psalter.sfm:45,53`)** [editorial] —
  the Holy Week footnote says the Psalter is not read from Holy Thursday to
  the Saturday of Renewal Week, but the table gives Kathisma XVII at Holy
  Saturday Matins. Confidence: high. Clarify the exception or the note's
  scope.

## Review and website tooling

- [ ] **Cross-verse readings in the Byzantine review and `XXC.json`**
  [build] — `HEB 1:1#1` (edits 1:2), `2CO 1:6#1` (edits 1:7), `COL 1:24#1`
  (edits 1:23): `build/review/byzantine/<BOOK>.md` shows only the unit's own
  verse, so the English change and its TR note are absent from the review
  (three of 173 TR notes in nine books). The website's variants put the
  Greek change in HEB 1:1 with no English lane and the English in 1:2 beside
  an unrelated movable-nu unit. Scripture itself is right. Confidence: high.
  Repro: `grep -n 'HEB 1:1#1' build/review/byzantine/HEB.md` and look for
  "at the end of these".
- [ ] **`1TH 2:12#1`** [build] — same boundary assumption: the unit's
  English evidence should show 2:11, where "charged" renders the participle.
  Disposition is right. Confidence: high.
