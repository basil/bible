# Pending names and spelling

Spelling, compounds, and proper names still to decide, in the text and in
the notes. Every change goes through `edition/revisions.json` (`names` for
a proper name, by its bearer); nothing here is approved wording.

## Text: compounds and regional spelling

All [editorial]. The introduction (`content/introduction.sfm:109`) says
"Compounds outside the declared changes keep their sources' forms", so none
of these is a failed transformation. They are candidates for declared
compound decisions. Confidence: high that the variation exists; the policy
call is open.

- [ ] **task-masters / taskmasters** — EXO 1:11, 3:7, 5:6 vs 5:10, 5:13.
- [ ] **olive-yards / oliveyards** — NEH 5:11, 9:25.
- [ ] **waiting-woman / waitingwoman** — JDT 8:10, 8:33.
- [ ] **beforementioned / before-mentioned** — 3MA 2:25, 4:14.
- [ ] **byword / by-word** — JOB 17:6, 30:9, 31:30; EZK 23:10, 36:3.
- [ ] **true-hearted / truehearted** — JOB 4:7, 27:17.
- [ ] **casting net / casting-net** — HAB 1:15–16.
- [ ] **no body** (SIR 23:18) — nobody, as 1SA 21:2 and DAG 0:16 print.
- [ ] **paralyzed / paralysed** — 3MA 2:22, 6:20.
- [ ] **Bethmaalo / Beth-maalo** — JDG 9:6, 9:20 (a place; see names too).

## Text: one bearer, several English forms

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

## Notes: spelling and punctuation (inherited)

All editorial judgment, from the 1611 margin or CCEL, each a scoped entry
in `edition/revisions.json`. Policy already says obsolete spellings in
notes are modernized; whether note commentary takes modern punctuation is
still open.

- [ ] **Missing possessive apostrophes: `LEV 4:3 CCEL` "peoples sinning",
  `MAT 27:27` "governors house", `ACT 12:20 the kings chaberlaine` "kings
  bedchamber", `ACT 13:1 brought up with Herod` "Herods foster brother",
  `ACT 17:19 Areopagus` "Mars hill"** — all inherited (1611 margin or CCEL).
  Confidence: high that the apostrophe is absent; low priority. Decide
  whether note commentary takes modern possessives at all; if so, scoped
  punctuation revisions in `edition/revisions.json`.
- [ ] **`DEU 1:15`** — "instructers"; instructors. Confidence: high.
- [ ] **`RUT 2:2 CCEL`** — note has American "favor" beside the verse's
  "favour". Confidence: medium. One scoped spelling decision.
- [ ] **`1SA 30:12`** — "Gr. staid or established"; the stayed/staid rule
  (`revisions.json` "stayed as a verb") covers three verses but not this
  gloss. Confidence: medium (could be adjectival).
- [ ] **`2KI 9:10`** — "buryer"; burier. Confidence: high.
- [ ] **`EZK 47:4 CCEL`** — "ancles" twice; ankles. Confidence: high.
- [ ] **`MAT 13:33 measures`** — "little more then a pint"; than. The edition
  already revises "an half" in this note. Confidence: high.
- [ ] **`MRK 7:4 tables`, `MRK 13:8 sorrows`** — 1611 commas "Sextarius, is"
  and "importeth, the pains". Confidence: high that they are inherited; low
  that they should change.
