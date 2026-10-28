# TODO

## Scripture grammar: agreement and inflection

All [source]: inherited in eBible and CCEL. Check the printing before a
scoped revision (`verses` in `edition/revisions.json`). Confidence is medium
for each unless noted; the slip is plain, the printing is unchecked.

- [ ] **2SA 15:34** — "if thou shall return" (shalt).
- [ ] **1KI 18:21** (3 Kingdoms) — "How long wilt ye halt".
- [ ] **2MA 7:19** — "thou shall escape"; KJV and RV have "shalt".
- [ ] **DEU 30:8** — "thou shalt return … and shall keep".
- [ ] **1KI 10:12** — "timber had not come … nor have been seen" (had).
- [ ] **1KI 10:28** — "the goings forth … was" (were).
- [ ] **1MA 10:53** — "both he and his host was discomfited" (were).
- [ ] **EZK 30:21** — "I have broken the arms of Pharaoh … it hath not been
  bound up … upon it"; number of "arm" in the Greek decides.

## Scripture meaning and continuity questions

All [source] and [source + Greek]. These are inherited readings that look
wrong against their context. None is an export regression. Confidence is
for "something is odd here", not for any particular fix. Do not harmonize
to the Hebrew or KJV without evidence; the Greek may read this way.

### Probable English or transcription slips (confidence: medium–high)

- [ ] **GEN 17:7** — "between thee and thy seed" lacks "me and", unlike
  17:2 and 17:10–11.
- [ ] **1SA 26:20** — "the king of Israel hath come forth to seek thy life";
  context wants "my life".
- [ ] **NEH 13:28** — "Elisub the high priest, one of the sons of Joada"
  reverses 12:10–11, where Eliasib begets Jodae.
- [ ] **2CH 30:24** — "and the holy things of the priests abundantly" has no
  predicate.
- [ ] **2CH 12:11** — "and they that returned to meet the footmen" has no
  predicate.
- [ ] **JER 51:10** (source 44:10) — "And have not ceased even to this day"
  opens a sentence with no subject.
- [ ] **ISA 41:2** — "so that it should go? shall appoint it an adversary"
  leaves the second predicate without a subject; the question mark may be
  misplaced.
- [ ] **ISA 7:17** — "Ephraim took away from Judah the king of the
  Assyrians" attaches the king to the wrong clause; punctuation.
- [ ] **PRO 27:13** — "Take away the man's garment (for a scorner hath
  passed by) whoever layeth waste another's goods"; "whoever" hangs.
- [ ] **4MA 14:7–8** — "for as the seven days of creation, about religion,
  so the youths…" has no verb in the as-clause.
- [ ] **NUM 6:4** — "vine, wine from the grape-stones to the husk"; second
  "wine" unclear.
- [ ] **NUM 29:4** — "each several ram, for the seven lambs"; animal
  conflicts with the clause.
- [ ] **1KI 15:28** (3 Kingdoms) — "Asa son of Asa"; patronymic.

### Possibly the Greek's own reading (confidence: medium)

- [ ] **GEN 19:33, 19:35** — "he knew not when he slept … he rose" where the
  daughter acts; pronoun referents.
- [ ] **GEN 38:11** — commanded to sit in her father-in-law's house, she
  sits in her father's.
- [ ] **EXO 9:4** — "all that is of the children's of Israel".
- [ ] **LEV 25:28** — "till the sixth year of the release" in the jubilee
  rule.
- [ ] **2SA 4:4** — "as he hasted and retreated" where the nurse flees.
- [ ] **1CH 10:3** — "they were wounded of the bows" makes the archers the
  wounded.
- [ ] **1CH 16:32** — "the tree of the field, and all things in it".
- [ ] **2CH 22:12–24:1** — hidden six years, acts in the eighth, reigns at
  seven.
- [ ] **TOB 6:6, 6:10, 7:1** — near Ecbatane, then near Rages, then lodging
  in Ecbatane.
- [ ] **TOB 6:13, 6:16, 7:9–14, 9:1–6** — marriage promised after returning
  from Rages, held that night, Raphael then sent to Rages alone.
- [ ] **HAG 1:4** — "our house is desolate" where 1:9 says "my house".
- [ ] **JER 20:16** — "Let that man rejoice as the cities which the Lord
  overthrew"; irony or slip.
- [ ] **EZK 4:4–6, 9** — 150 days in verse 4, 190 in verses 5 and 9.
- [ ] **EZK 10:21** — eight wings each, where 1:6 gives four.
- [ ] **EZK 39:19** — "drink wine" amid eating flesh and drinking blood.
- [ ] **JDG 20:35** — 125,000 fallen against an army of 23,700 and a summary
  of 25,000; Paragraph Bible has 25,100.
- [ ] **1MA 12:7, 12:19–20** — the Spartan letter is from Darius, sent by
  Oniares, signed Areus to Onias.

## Scripture punctuation (inherited)

[editorial] unless marked. Any change is a scoped punctuation revision.
Compare the printing before calling one a transcription slip.

- [ ] **EXO 16:35** — no clause boundary between "land" and "they ate the
  manna". Confidence: medium.
- [ ] **1KI 5:25** (3 Kingdoms) — "beaten oil thus Solomon gave"; CCEL has a
  separator, eBible none. Confidence: medium. [source]
- [ ] **PSA 56:2** — "Have mercy, upon me"; the repeat in the verse is
  clean. Confidence: high.
- [ ] **MAL 1:3** — declarative "yet I loved Jacob … wilderness?" ends with a
  question mark. Confidence: medium. [source]
- [ ] **DAG 3:51** — "praised, glorified, and blessed, God". Confidence: low
  (rhetorical punctuation).
- [ ] **our's, your's, their's** — GEN 31:16, JDT 5:18, 1MA 12:23 (three),
  2MA 13:22. Confidence: high that they exist; decide once.

## Orthography: obsolete spellings

All [editorial]. The introduction says obsolete spellings are modernized
even where both sources agree; these candidates remain to be decided in
`edition/revisions.json`. Confidence: high for
each as an omission unless noted. Keep the inflection, change the spelling.

- [ ] **flixe** (ACT 28:8) → flux.
- [ ] **lowring** (MAT 16:3) → lowering or louring. Confidence: medium.
- [ ] **layedst** (LUK 19:21) → laidst.
- [ ] **doateth** (SIR 25:2) → doteth.
- [ ] **carrs** (1ES 5:53) → cars. Confidence: medium (period vehicle noun).
- Repro: `grep -rn -w 'flixe\|lowring\|layedst\|doateth\|carrs' build/review/text/`.

## Orthography: compounds and regional spelling

All [editorial]. The introduction (`content/introduction.sfm:108`) ends
"Compounds outside the declared changes keep their sources' forms", so none
of these is a failed transformation. They are candidates for declared
compound decisions. Confidence: high that the variation exists; the policy
call is open.

- [ ] **preeminence** (COL 1:18, 3JN 1:9) and **turtledoves** (LUK 2:24) —
  the retained-hyphen list names pre-eminence and turtle-dove "wherever they
  stand", but no word rule normalizes the solid source forms. Decide whether
  the preference means all occurrences; if so, declare them.
- [ ] **task-masters / taskmasters** — EXO 1:11, 3:7, 5:6 vs 5:10, 5:13.
- [ ] **olive-yards / oliveyards** — NEH 5:11, 9:25.
- [ ] **waiting-woman / waitingwoman** — JDT 8:10, 8:33.
- [ ] **beforementioned / before-mentioned** — 3MA 2:25, 4:14.
- [ ] **byword / by-word** — JOB 17:6, 30:9, 31:30; EZK 23:10, 36:3.
- [ ] **true-hearted / truehearted** — JOB 4:7, 27:17.
- [ ] **casting net / casting-net** — HAB 1:15–16.
- [ ] **no body** (SIR 23:18) — nobody, as 1SA 21:2 and DAG 0:16 print.
- [ ] **money-changers / moneychangers** — MRK 11:15, MAT 21:12.
- [ ] **market-place / marketplace(s)** — ACT 16:19 (and its 1611 lemma),
  MAT 20:3, LUK 7:32, MRK 12:38; ECC 12:4, TOB 2:3, 1ES 2:17.
- [ ] **paralyzed / paralysed** — 3MA 2:22, 6:20.
- [ ] **Bethmaalo / Beth-maalo** — JDG 9:6, 9:20 (a place; see names too).

## Capitalization of "king" before a name

[editorial]. `edition/revisions.json` capitalizes "king `Name`" but excepts
phrases where a demonstrative qualifies the title (lines 11243, 11284,
11386). In these three the "this/that" is not a demonstrative on "king":

- [ ] **ESG 3:1** — "And after this king Artaxerxes" (temporal "after this").
  Confidence: high.
- [ ] **1MA 8:31** — "the evils that king Demetrius doeth" (relative "that").
  Confidence: high.
- [ ] **4MA 4:13** — "anxious that king Seleucus should not suppose"
  (conjunction "that"). Confidence: high. Contrast 4:3 "King Seleucus".
- [ ] **JER 47:14** — "that king Beleissa"; may be a reported clause.
  Confidence: low. Check the sentence.
- Fix: narrow or remove the three exceptions. Repro:
  `grep -n 'this king Artaxerxes\|that king Demetrius\|that king Seleucus' edition/revisions.json build/review/text/*.usfm`.

## Names: one bearer, several English forms

All [source + Greek]: tabulate Swete (or RP2026 for the NT) and the printed
English before merging; declension alone never separates bearers
(memory: names-check-greek-declension). None has a `names` entry in
`edition/revisions.json`. Confidence is high that the same bearer is meant
unless noted; whether to normalize is the editor's call after the Greek is
seen. Repro for any: `grep -rn -w '<Form>' build/review/text/`.

### Old Testament, history

- [ ] **Achikam / Achicam** — 2KI 22:12 vs 22:14, 25:22, 2CH 34:20, JER (six).
- [ ] **Abener / Abenner** — 1SA 17:55, 17:57 (from the supplied Appendix
  passage `1SA 17:55-58`) vs Abenner elsewhere. Enters by promotion, not
  transcription.
- [ ] **Aben-ezer / Abenezer** — 1SA 4:1 vs 5:1, 7:12.
- [ ] **Chelcias / Chelkias** — 2KI 18:18, 18:37 vs 18:26 (Heliakim's
  father; other Chelcias bearers exist).
- [ ] **Helkana / Helcana** — 1SA 1 (seven) vs 2:20 (other Helcana bearers
  in 1CH).
- [ ] **Phadasur / Phadassur** — NUM 1:10 vs 2:20, 7:54, 7:59, 10:23.
- [ ] **Sapphan / Saphan** — 2KI 22 vs 25:22, 2CH 34 (JOS 13:27 Saphan is a
  place; exclude).
- [ ] **Mala / Maala / Malaa** — NUM 26:37, 27:1, 36:11; JOS 17:3.
- [ ] **Abesa / Abessa / Abesai / Abessai** — 1CH 18:12, 19:11, 19:15;
  1SA 26:6–9; 2SA 19:21, 20:10.
- [ ] **Jectan / Jektan** — 1CH 1:19, 20, 23 (supplied from the Appendix)
  vs GEN 10:25, 26, 29.
- [ ] **Gaddites / Gadites** — 1CH 26:32 vs 1CH 12:38, 2KI 10:33.
- [ ] **Amalec / Amalek** — JDG 6:3 vs 6:33 (44 vs 1).
- [ ] **Adraazar / Adrazaar** — 2SA 8:3–12 vs 1KI 14:26 (17 vs 1).
- [ ] **Cath / Caath** — GEN 46:11 vs EXO 6:16–18 (1 vs 41).
- [ ] **Cariathbaal / Cariath-Baal** — JOS 15:60 vs 18:14–15.
- [ ] **Isaar / Issaar** — NUM 16:1, EXO 6:18, 21, 1CH 23:12, 18 (GEN 46:24
  Issaar is a Nephthalite; exclude).
- [ ] **Jasa / Jassa** — NUM 21:23, DEU 2:32, JDG 11:20.
- [ ] **Jetur / Jettur** — GEN 25:15 vs 1CH 1:31.
- [ ] **Kison / Kisson** — JDG 4:7, 4:13, 5:21 vs 1KI 18:40 (brook; Kison
  the city excluded).
- [ ] **Massecca / Masecca** — GEN 36:36 vs 1CH 1:47.
- [ ] **Rabia / Raabia** — 1CH 23:17 vs 24:21.
- [ ] **Raia / Raaia** — EZR 2:47 vs NEH 7:50.
- [ ] **Rason / Rasson** — EZR 2:48 vs NEH 7:50.
- [ ] **Samellius / Semellius** — 1ES 2:15–16 vs 2:21, 2:25.
- [ ] **Joakim / Joachim** — 2CH 36:4–8.
- [ ] **Sabanasar / Sabanazar** — EZR 5:14 vs 5:16.
- [ ] **Esdrelom / Esdraelon / Esdraelom** — JDT 1:8, 3:9, 4:6, 7:3.
- [ ] **Philopater / Philopator** — 3MA 1:1, 3:12 vs 7:1.
- [ ] **Saucheans / Sauchaeans** — JOB 2:11 vs 42:17e.
- [ ] **Beelphegor / Beel-phegor** — PSA 105:28 vs NUM 25:3, 25:5, DEU 4:3,
  HOS 9:10.

### Old Testament, prophets

- [ ] **Rasin / Rasim / Rassin** — ISA 7:1, 7:8, 8:6.
- [ ] **Heliakim / Eliakim** — ISA 22:20, 36:3, 36:22, 37:2 vs 36:11.
- [ ] **Laches / Lachis** — ISA 36:2 vs 37:8 (and 21 other Lachis verses).
- [ ] **Thogarma / Thorgama** — EZK 27:14 vs GEN 10:3, 1CH 1:6, EZK 38:6.
- [ ] **Mosoch / Mesoch** — EZK 32:26 vs 38:2–3, 39:1 (GEN 10:23 and
  1CH 1:17 Mosoch is an Aramean; exclude).
- [ ] **Selemias / Semelias** — JER 44:3 vs 45:1 (Joachal's father).
- [ ] **Caree / Careë** — JER 47:8, 47:13 vs 48:11, 50:2 (Joanan's father);
  CCEL has Careë throughout.

### New Testament (Greek is one form; confidence high)

- [ ] **Beelzebul / Beelzebub** — MAT 10:25 vs MAT 12:24, 12:27, MRK 3:22,
  LUK 11:15, 11:18, 11:19. RP2026 has Βεελζεβούλ at all seven; Scrivener
  differs only at 10:25, and the existing note there attributes the
  Complutensian reading. Normalize the six, keep the 10:25 attribution.
- [ ] **Jona / Jonas** (Peter's father) — JHN 1:42 vs 21:15–17. RP2026 and
  Scrivener have Ἰωνᾶ at all four. The Jonah→Jonas rule is the prophet's.

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
