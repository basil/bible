# Notes: open questions

The open questions left over from the footnote reviews of September 2026. None of them is settled yet: each needs a decision, or a check against Brenton's printing or a 1611 facsimile, before anything changes.

## How to read this list

The sections:

1. [Errors in the printed notes](#1-errors-in-the-printed-notes): the book prints something wrong, or probably wrong.
2. [Rules to decide](#2-rules-to-decide): one decision settles many notes.
3. [Readings from Codex Alexandrinus](#3-readings-from-codex-alexandrinus): readings not yet printed in the text, and readings already printed that need another look.

**Keys.** Brenton's notes are named by their keys, the `x-key` the build gives each source note ([AGENTS.md](../AGENTS.md#the-document-model)), which a decision in `edition/` is filed under:

- Books are USFM codes: `1SA`–`2KI` are 1–4 Kingdoms, `PRO` Proverbs, `JOL` Joel, and `BAK` Brenton's Appendix, whose entries in `alexandrinus.json` are named by the verse they concern, as `BAK 1KI 2:35a`.
- Chapters and verses are Brenton's, so the Psalms and Joel are numbered as in the Greek, and some verses are lettered, as `1KI 5:14a`.
- `#2` is a verse's second note; a key without it is the verse's first or only note.
- A note may be a footnote or a cross-reference (`\x` in the source). Some of the references in 1.1 and 1.2 are cross-references; most are footnotes that cite a passage.

A 1611 marginal note is named by its verse and `(1611)`, as `1CO 14:27 (1611)`; its key in `edition/kjv-notes.json` adds the words George prints it under, as `1CO 14:27 two...`.

**Cross-references.** A note with more than one problem is listed under each, and each listing names the others in brackets, as [also 3.6].

**Sources.** eBible is the transcription of Brenton that the build reads, and George is Calvin George's transcription of the 1611 notes ([sources/README.md](../sources/README.md)). Swete is the Greek edition whose apparatus checks Brenton's reports of Codex Alexandrinus. In its sigla, A is Codex Alexandrinus, A¹ its first hand and Aᵃ a corrector, "vid" marks an uncertain reading, and Q and Γ are other manuscripts; Vat. is Codex Vaticanus, the text Brenton translates.

**Closing an item.** Record the decision in `edition/` with its reason, as [AGENTS.md](../AGENTS.md#where-a-change-goes) says, and delete the item here in the same commit.

## 1. Errors in the printed notes

Most of these are probably slips of transcription, by eBible or George, but some may be slips of the printing, Brenton's or the 1611's, so check the printing first. How each is mended:

- A slip in the transcription: an entry in `corrections`, in `edition/brenton-notes.json` or `edition/kjv-notes.json`.
- Brenton's own slip of spelling or punctuation: `edition/revisions.json`.
- A wrong reference: a `corrections` entry, or a decision in `edition/citations.json` if Brenton printed it so.
- A note on the wrong words: its `lemma` in `notes`.
- Italics: the note's `note` override in `notes`, where `_…_` marks an italic run.
- A note on the wrong verse: a `verse` override in `notes`, as GEN 43:13 has.
- A note copied from elsewhere, or with eBible's words in it: its `note` override in `notes`, or an uncategorized `corrections` entry.
- Words missing from the scripture itself: a correction there may mend only word spacing, so this needs its own decision, with evidence.

### 1.1 References with the wrong number

| Note | Prints | Probably |
| --- | --- | --- |
| ISA 29:13 | Mat. 8. 9 | Mat. 15. 8, 9 |
| ISA 53:5#2 | 1 Pet. 2. 22 | 1 Pet. 2. 24 |
| DEU 32:21 | Rom. 10. 9 | Rom. 10. 19; the quotation starts at "I will provoke them to jealousy" |
| NUM 36:7 | Acts 5. 26 | Acts 5. 13 |
| DEU 16:8 | Lev. 23. 6 | Lev. 23. 36 |
| DEU 5:16 | Eph. 6. 1 | Eph. 6. 2, which quotes the verse |
| PRO 3:6 | 2 Tim 2. 13 | 2 Tim 2. 15 [also 2.6] |
| PRO 4:11 | chap 2. 18 | chap 2. 15 [also 2.6] |
| PRO 11:28 | 1 Tim. 5. 8 | 1 Tim. 6. 2 |
| PRO 11:31 | 1 Pet. | 1 Pet. 4. 18 |
| PRO 16:16 | Luke 13. 35 | Luke 13. 34 |
| PRO 14:9 | Job 6. 21 | unknown; Job 6:21 doesn't fit |
| 2KI 16:13 | 2 Chr. 13. 10 | 2 Chr. 13. 11 |
| COL 1:25 (1611) | Rom. 1.19 | Rom. 15.19 |
| GEN 19:13 | See Note, Lam. 3. 21 | unknown; eBible has no note at Lam. 3:21 |

PSA 9:27, PSA 77:25 and PSA 101:25 have wrong numbers too, but are listed in 1.2, because their notes are probably on the wrong verse as well.

Leave alone the references that count in the Hebrew or English way, as Brenton printed them: ISA 26:19 "Ps. 110" (109. 3 in the Greek); PSA 88:21#2 and PSA 91:11, which each point one verse low; and 2KI 12:15 "vide v. 13" (v. 14 here).

### 1.2 Notes on the wrong verse or the wrong words

- **Swapped pairs.**
  - JDG 8:7 and 8:9: the Vatican text has ἀλοήσω ("thresh") at 8:7 and κατασκάψω ("dig down") at 8:9, but 8:7 has "Gr. dig down." and 8:9 "Gr. thresh.". So 8:9 prints "break: Gr. _thresh_", and 8:7 has a lemma override, "tear", fitted to the note as it stands. If Brenton printed them the right way round, swap the two notes' texts back with two uncategorized `corrections`, then check whether the override on 8:7 is still needed.
  - JDG 20:10 and 20:13: "Heb. sons of Belial" belongs on "sons of transgressors" in 20:13, and "Gr. it, sc. Gabas" (a typo for Gabaa) on "they" in 20:10.
  - ISA 61:3: the verse's two notes are swapped. "Alex. reads καταστολὴν as one word" belongs on "the garment of glory", and "Or, anointing" on "oil". [also 3.6]
  - MRK 7:4 (1611): George swaps the notes. "Or, beds" belongs to "tables", and the sextarius note to "pots". The lemmas already put them right; check the 1611 to confirm.
- **A note on the neighbouring verse.**
  - PSA 9:27 prints "Rom. 8. 14", which should be Rom. 3. 14; that verse quotes PSA 9:28, so the note belongs there.
  - PSA 77:25 prints "Mat. 6. 31", which should be John 6. 31; that verse quotes PSA 77:24, so the mark may belong there.
  - PSA 101:25 prints "Heb. 1. 11,13", which should be Heb. 1. 10-12, and the note would sit better at 101:26.
  - EXO 21:17 "Mat. 15. 4" belongs to 21:16 in the Greek's order.
  - DEU 6:4 "Mat. 22. 37; Luke 10. 27": these quote 6:5, so the mark may have been put at the start of the passage.
- **A lemma on the wrong words.**
  - GEN 18:12: the note is about עדנה ("pleasure", or the Greek's "until now"), so its lemma should be "even until now", not "The thing". [also 1.4]
  - 1SA 21:15: "Gr. or man epileptic." is probably "a man epileptic", which would be a `corrections` entry. If so, decide whether the lemma, now "man is mad", should take in "the".
  - DEU 21:5: "bless in his name: Gr. _his name_. Hebraism." fits only if the mark stands before "in".
  - JOS 18:5: "came to him: Gr. _went through_" should be on "came" alone, if the Greek has πρὸς αὐτόν.
  - 2KI 19:25: "destruction: Gr. _captivities_": "captivities" (ἀποικεσιῶν) is what Brenton renders "bands of warlike prisoners". Check where the mark stands.
  - 1KI 11:27: the lemma and the rendering are the same: "of his lifting: Gr. _of his lifting_". The mark stands before "of his lifting up". Perhaps the note means that the Greek lacks "up his hands", and its lemma should say so; perhaps it is about "the occasion" before the mark; or words of the note were lost. Check the printing.
  - PRO 21:29: the marked word already reads "ungodly", so "See Alex. ungodly." changes nothing where it stands. Was it meant for "impudently"? [also 3.4]

### 1.3 Notes copied or repeated from elsewhere

- EXO 32:14 "Gr. dost." is a copy of the note on 32:32; the Greek has ἱλάσθη.
- 2SA 22:27 repeats "Or, upon the haughty" from 22:28, where it belongs.
- DEU 9:22: three notes print the same "Heb. Taberah, Massah, and Kibroth Hattavah."
- 1SA 29:3#2, 29:4, 29:5 and 29:8 all begin "to or", which makes sense only in 29:2.
- MAT 17:27 (1611): George's note ends "is 7.d. ob.", apparently copied from 18:28.
- 2KI 23:36: the note says "a son of 23 years", but the verse and the Greek say twenty-five. Perhaps copied from 23:31.

### 1.4 Notes with eBible's words, or with words missing

- **eBible's paraphrase of the Appendix.** Brenton probably printed only a pointer to the Appendix, but these notes paraphrase it or paste it in:
  - 2SA 5:18: "which refers us to Govett's work…" [also 3.6]
  - PRO 4:5: "See Appendix - Alexandrian codex has:"
  - PRO 8:32 and PRO 11:3 begin in lowercase and quote the reading from Codex Alexandrinus: "appendix has Alexandrine text as: …", "the Alexandrine text reads: …".
  - PRO 11:10 and PRO 13:5 likewise paraphrase the Appendix.
  - ISA 2:6: "see Appendix which has: …" pastes in the Appendix's note. [also 1.5, 3.6]
- **A label with nothing after it, or followed by the wrong thing.** A Greek word may have been lost after "Gr.", or the label may be stray:
  - 1SA 20:41 "Gr. See v. 19."
  - PSA 79:17 "Gr. See Ps. 20. 9."
  - 1SA 13:21 "Gr. Such is the meaning…" [also 1.5]
  - 1SA 20:15 "Gr. The meaning of the Heb. is here greatly obscured."
  - GEN 18:12 "Gr. The difference turns on…" [also 1.2]
  - EXO 4:12 "See 1 Cor 2. 16. Gr."
  - MAL 3:11 "…to be fed. Alex." [also 3.5]
- **Words missing from the verse or the note.**
  - EXO 16:35: the verse seems to lack "inhabited", and the note's οἰκουμένη has a Latin u.
  - PSA 101:17: "Or, then shall be", put in place of the words it is about, leaves the verse without a subject; perhaps "then shall he be seen".

### 1.5 Misspellings and misreadings

eBible's slips or Brenton's own; check the printing to know which file mends them.

- **English.**
  - DEU 28:49 "Gr. bear." for "hear"; 2SA 15:20 "Gr. it." for "if"; PSA 51:1 "Gr. governing.", perhaps for "understanding"
  - GEN 30:27 "argued" for "augured"; GEN 41:51 "things belong to my father" for "belonging"; ISA 2:6 "sound to tense" for "sense" [also 1.4, 3.6]; JOS 15:18 "has thou" for "hast"
  - EXO 39:22 and 2KI 3:17 "posession"; EXO 12:3 "admissable"; JOS 10:34 "vigourously"; 1SA 13:21 "interpretors" [also 1.4]; 1SA 21:8 "repitition"; 2KI 4:39 "colosynth" for "colocynth"; 2KI 24:10 "seige". No category of correction allows a transposition like "seige", so a correction of it must be marked `"uncategorized": true`.
  - 2SA 13:12 "fasciendum" for "faciendum"; PSA 49:18 "1 Pe" for "1 Pet." [also 2.6]
- **Punctuation and capitals.** GEN 15:11 has no closing full stop. 1SA 6:8 begins in lowercase, "in the Alex." [also 3.1]. ZEC 12:2 "porches or, door-posts" lacks the comma before "or".
- **Hebrew that eBible misread**, which no correction mends yet: 1SA 17:52 שעריס; 1SA 21:3 מקוצ and פלכי אלמבי; 2SA 5:23 בכאיס; JDG 9:6 מעכ [also 3.6]; JDG 9:37 מעס; JDG 17:10 ימיס; JDG 18:7 מבליס; ISA 51:3 שוב. Check also the maqaf in 2KI 2:14, where eBible has a space.
- **Greek.** NUM 1:18 ἐπαξοοῦν [also 2.10] and EXO 19:22 ἀπαλλατέω. GEN 3:15 τειρήσει is probably Brenton's own spelling.
- **1611.** GAL 5:16 (1611) has "fulfill", where the text has "fulfil". To check against a facsimile: JHN 18:28 (1611) "Pilats house"; TIT 2:9 (1611) "gain saying" (one word?); REV 6:6 (1611) "The word choenix, signifieth"; 2PE 2:11 (1611) "some read", in lowercase.

### 1.6 Italics to check

Each of these has an override that italicizes the phrase in question. Check the printing to decide whether the phrase is a rendering, and so italic, or the note's own explanation, and so roman.

- NUM 30:7: is "in respect of" a quoted rendering or explanation, and where does the italic end before οὓς?
- EXO 40:15: the quotation "The anointing abideth" from 1 John 2:27. Check where it begins and ends, its opening capital, and how "etc." is set.
- 1CO 14:27 (1611): is "by two or three sentences separately" an alternative rendering or a paraphrase?

## 2. Rules to decide

Each of these is a question about a rule. One decision settles every note it covers.

1. **1611 notes on a whole verse.** LUK 17:36 (1611), "This 36. verse is wanting in most of the Greek copies", reprints the whole verse as its lemma, and JHN 18:13 (1611), a note on the order of events, prints under "year". `kjv-notes.json` now allows `"lemma": null`, as `brenton-notes.json` does. Decide whether to give these two notes no lemma.
2. **Notes on "the words in italics".** 2SA 17:8, 2SA 21:11 [also 2.3], 1SA 17:43 and 1KI 14:26#2 refer to words Brenton set in italics, which this edition prints in square brackets. Either print the bracketed words in italics too, or accept the mismatch.
3. **Lemmas on a long passage.** HAG 2:14 ("Not in Hebrew.") and 2SA 21:11 [also 2.2] are about a whole bracketed passage, but their lemmas cover only its first clause. Decide whether a lemma that long is acceptable.
4. **A rule for additions.** "Alex. + '…'" sets no rendering while "Alex. adds '…'" does, so the rules place the two differently, and about 25 overrides now put an addition's lemma on the words it follows. Proposed: a rule in `inferred_lemma` for notes that add words, taking the clause before the mark, or its last four words if it runs past nine, and the current rule at the start of a verse. It places 35 of the 41 additions correctly and would retire about 23 overrides; 1SA 12:13, 1KI 3:20, PRO 9:6, GEN 1:11#2 [also 3.1], ISA 63:19 and 2SA 6:3 would keep theirs.
5. **"or" inside one rendering.** The rules split "_X_ or _Y_" into two italic runs, which is wrong when the "or" belongs to a single rendering. Overrides join EXO 21:28, NUM 1:52, 1SA 20:6, PSA 25:12, PSA 32:4, PSA 50:21 and ACT 25:6 (1611). Still split: EXO 14:15 "_harness_ or _yoke the horses again_", 2CO 4:8 (1611) "_altogether without help_ or _means_", where the 1611 has a comma before "or", and 1SA 30:12 "_staid_ or _established in him_". Decide whether these three should be joined.
6. **Abbreviations without a full stop.** "chap 5. 25", "ver 16", "ch 1. 14", "Ps 103. 14", "Gen 7. 11", "See v 8." and the like occur about as often as the forms with a stop: JDG 21:4; 1SA 15:3; PSA 146:8; PRO 1:15, PRO 11:13, PRO 20:27, PRO 27:20a; JOL 2:15, JOL 4:18; MAL 3:10; ISA 2:19, ISA 14:16, ISA 23:11, ISA 45:16, ISA 57:21; PSA 49:18 "1 Pe" [also 1.5], PSA 90:6 "ver 3", PRO 3:6 "2 Tim" and PRO 4:11 "chap" [both also 1.1]. Check which way Brenton printed them, and correct all or none.
7. **Two colons.** A lemma that keeps the verse's own colon prints two: "that believed: for there: or, …" (LUK 1:45 (1611); also LUK 4:41 (1611) and REV 14:13 (1611)). Decide whether the lemma should drop its colon.
8. **"Heb. and Alex. Vat."** 36 notes print this, which is ambiguous. Their decisions' `witnesses` already say that Heb. and Alex. support the adopted wording and Vat. the displaced wording, but the printed form doesn't. Decide how to print it.
9. **eBible's remark at PRO 30:1.** The verse is empty and carries eBible's remark "See chapter 24 for the content of chapter 30.", which prints as if it were Brenton's note. Chapter 31 starts at verse 10 with no remark at all. Keep the remark as an editorial note, or say where both passages are some other way.
10. **Names and words written out in full.** `corrections` in `brenton-notes.json` write out "Lambert Bos" (the preface, GEN 33:18 [also 3.6], NUM 1:18 [also 1.5]), "Patrick Junius" (GEN 33:18), "Abraham Trommius" (NUM 25:8), "Professor Samuel Lee" (1KI 20:10), "Charles Pridham" (the Appendix) and "Complut." for "Comp." (1SA 31:9), all marked `uncategorized`, as if they mended slips. Decide whether they are editorial changes instead, and so belong elsewhere, or should stay as Brenton printed them. The same question goes for DEU 24:13, whose correction of "ie." to "i. e." is `uncategorized` too: keep it as a correction, or make it a revision in `edition/revisions.json`.

## 3. Readings from Codex Alexandrinus

The 56 decisions in `kept` in `edition/alexandrinus.json` that carry `"todo": true` are readings that are still only notes. Each is settled by printing the reading, which moves its decision to `readings` or `passages`, or by keeping the note for good, which removes its `todo` and updates its `why`. Sections 3.1–3.6 group them by what stands in the way; 3.7 lists readings already printed.

Not open: NUM 28:24, GEN 5:32 and GEN 6:10 are kept without `todo`, and their decisions give the reasons.

### 3.1 Greek with no English from Brenton (12)

Swete confirms the Greek, but Brenton gives it only in Greek, so printing it needs English of the edition's own. One policy decision settles the group: whether the edition ever supplies its own English.

GEN 1:11#2 [also 2.4], JDG 9:27#2, JDG 13:5#2, JDG 13:19, 1SA 6:8 [also 1.5], 2SA 17:16, 1KI 5:18, 1KI 8:59#3, 2KI 19:24, 2KI 21:6#2, PSA 31:9, ISA 59:7#2.

### 3.2 A pointer with no English (3)

A has a different reading, but Brenton only points to it, and gives no English to print. The policy decision in 3.1 bears on these too.

| Decision | What stands in the way |
| --- | --- |
| BAK 1KI 2:35a | Brenton reports variation here without translating it. Swete records omissions and an addition, but applying them needs English that Brenton doesn't give. 1KI 2:35a, in 3.6, is the note that points here. |
| PSA 41:5 | Brenton gives a reference to the Appendix rather than English. Swete confirms a Greek variant, but its English must be found or supplied. |
| ISA 40:4 | Brenton refers to Luke without giving English. Swete supports the Greek, but borrowing English from Luke needs its own decision. |

### 3.3 Placement and duplicated passages (5)

| Decision | What stands in the way |
| --- | --- |
| BAK 1KI 5:17 | Brenton gives English, and Swete supports its place here, but the same material already stands at 6:1a–b. Printing it would duplicate the passage, and Brenton doesn't mark the existing words for removal. Decide which copy to print. |
| BAK 1KI 6:11-22 | Both portions stay in the Appendix for now. The first Greek anchor recorded is κέδρου in verse 15, but the earlier work placed 6:11–14 after Brenton's 6:10 without recording why. Check that placement, and the second addition's, separately; the record doesn't show that the earlier placement was wrong. |
| BAK 1KI 7:1-12 | Brenton points to verses already printed elsewhere, and Swete confirms A's different order. There is no separate English to insert; moving the existing verses is a structural decision. |
| BAK 1KI 14:1-20 | Brenton says the substance is already at 12:24 in the Vatican text, and Swete confirms A's passage at 14:1–20. The Appendix gives no separate English. Resolve the overlap before moving or inserting anything. |
| 1KI 14:21 | The note that points to BAK 1KI 14:1-20; its Appendix explains the structure rather than translating. Settle the two together. |

### 3.4 Brenton and Swete disagree (9)

Check Brenton's printing, and the manuscript where it matters, before printing any of these.

| Decision | Brenton | Swete |
| --- | --- | --- |
| GEN 6:2 | A has "angels of God" for "sons of God" | stands over an erasure, in an uncertain hand (A?vid); establish the reading and the hand |
| NUM 4:48 | "450" | A reads 8,550 |
| PSA 118:151 | "commands" | "ways", with no substitution in A; check the manuscript and the verse reference |
| PSA 130:1 | A adds "for David" | A omits it |
| PSA 132:1 | A adds "for David" | omitted, apparently by A's first hand |
| PRO 5:13 | a change at verse 13 | keeps the negative, with no difference in A; A omits a negative at 5:10 and 5:16 instead, so the note may belong there |
| PRO 21:29 | "ungodly" | no substitution in A at the marked word, which already reads "ungodly" [also 1.2] |
| ZEC 9:5 | "of her hope" is A's | it is Q's, and A doesn't differ from Vaticanus |
| ZEC 9:15 | A reverses altar and bowls | "as bowls" is Γ's, with no reversal in A |

### 3.5 English to correct or clarify (8)

Brenton's English for the reading is wrong, incomplete or unclear. Check his printing, then record a correction of the English with its reason before printing the reading.

| Decision | What stands in the way |
| --- | --- |
| 1SA 30:26 | Brenton gives "from you", but A's reading in Swete means "to you". Copying his English would reverse the Greek. |
| 2KI 3:21#2 | Printed in the verse, the alternative "and above" would need a starting point (above what?), which Brenton doesn't give. The note as received spells A's Greek ἐπάνα, where Swete has ἐπάνω; check which Brenton printed. The note is restored to its original form meanwhile. Settle the whole clause and its spelling. |
| BAK 2CH 27:8 | Brenton's English gives both twenty-five and sixteen as years reigned, while verse 1 distinguishes age at accession from length of reign. |
| PSA 41:9 | Brenton's alternative gives "his song shall be, etc.", not a whole clause. Reattaching "with me", removing "is" and supplying "and" needs a decision about the prayer that follows and the reading recorded for A¹. |
| ISA 8:1 | The χάρτου added after τόμον doesn't settle what "great new" attaches to, or justify replacing "book" with "a volume of great new paper". |
| ISA 30:8 | A's Greek changes case and order; "days in seasons" would supply a new "in" and drop "many long", with no settled English. |
| JON 1:8 | Swete confirms an addition in A, but Brenton's "for those whose cause" is ungrammatical and doesn't match the Greek question. |
| MAL 3:11 | Swete records a change of case in A, but how it relates to Brenton's "give a charge for you to be fed" is unclear. [also 1.4] |

### 3.6 Probably keep as a note (19)

Nothing here needs printing: the text already follows A, or the note explains rather than offering other English. Confirm each, then remove its `todo`.

| Decision | Why it can probably stay a note |
| --- | --- |
| GEN 33:18 | The verse already translates A's παρενέβαλε as "took up a position"; "pitched his tent" is another translation of the same word. [also 2.10] |
| JDG 9:6 | The Greek εὐρετῆ that A omits has no English words of its own in Brenton's verse, and his "of Sedition" follows A. [also 1.5] |
| JDG 21:22 | Brenton says that "according to the occasion" is translated from A. |
| 2SA 5:18 | Brenton points to Govett's discussion of Isaiah and gives no English; Swete's Greek doesn't supply any. [also 1.4] |
| 2SA 11:25 | The verse already prints "strengthen him", following A. |
| 2SA 15:12 | The verse already follows A's reading of the conspiracy. |
| 1KI 1:9 | The verse already follows A: "by the stone of Zoelethi". |
| 1KI 2:35a | The note points to the Appendix; the passage is BAK 1KI 2:35a in 3.2. |
| 1KI 5:14a | Brenton reports a chapter division, which Swete's layout supports. It changes the numbering, not the words, and the edition keeps Brenton's verse numbers. |
| BAK PRO 21:16-17 | Brenton points to an explanatory note in the Appendix, with no other English, and Swete reports no difference in A at the words cited. |
| PSA 49:19 | The note reports a gap in the manuscript, not English. |
| PRO 8:5 | Brenton's Appendix discusses the Greek vocabulary with no other English, and Swete reports no variant in A. |
| PRO 21:16 | Brenton's pointer concerns Rephaim and 2 Kingdoms, with no other English, and Swete reports no variant in A. Settle with BAK PRO 21:16-17. |
| ISA 2:6 | The Appendix's note explains the Greek rendering of "Philistines"; it isn't a reading of A's. [also 1.4, 1.5] |
| ISA 7:18 | Brenton says the verse's wording is already A's. |
| ISA 54:10 | Brenton says the verse already adopts A's reading. |
| ISA 61:3 | The note is about how the Greek divides words, with no other English. [also 1.2] |
| ISA 66:5 | The verse already says "our", A's reading. |
| ZEC 14:7 | The verse already translates A's ψύχος as "cold"; the note explains it. |

### 3.7 Readings already printed that need another look

These readings are in the text now. Each needs a check against Brenton's printing or an editorial decision; leave the text and notes as they are until then.

- **DEU 32:42**: the English has "their Gentiles". Decide what "their" refers to before keeping or removing the supplied word.
- **1KI 15:2**: Swete confirms sixteen in A but gives six for the Vatican text, while Brenton's text has three. Check whether three is Brenton's or eBible's slip; the note currently distinguishes the two sources.
- **PSA 138:9**: the note as received gives ὄρθον, where Swete has A's ὄρθρον. Check which spelling Brenton printed; the note distinguishes the two forms meanwhile.
- **ZEC 11:14**: the text adopts Brenton's "covenant", but A also adds "my", and the note gives only the displaced "possession", although the decision says the addition is noted. Decide how to disclose the partial adoption and the possessive without supplying new English.
- **PRO 15:33**: the Appendix's original label, "16 (Alex.15) 33", is kept in the decision. Printing a note with it is optional; the moved saying is already in the text.
