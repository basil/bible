# TODO

Everything still to do in the text and the notes, apart from names and
spelling, which are in [spelling.md](spelling.md).

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
