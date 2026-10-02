# Notes: open questions

Left over from the footnote reviews of September 2026. Each remaining item needs a decision, or a check against Brenton's printing or a 1611 facsimile, before anything changes.

## Decisions on the rules

1. **1611 notes on a whole verse.** Luke 17:36 ("This 36. verse is wanting in most of the Greek copies") reprints the whole verse as its lemma, and John 18:13's note on the order of events prints under "year". `kjv-notes.json` now allows `"lemma": null`, as `brenton-notes.json` does; decide whether to give these two notes one.
2. **"`Heb. <Hebrew> <English>`".** The English after a Hebrew word stays roman almost everywhere ("Emec Achor: Heb. עמק עכור valley of trouble"; 1 Kgdms 4:15, 14:6, 14:26, 17:52, 20:12), though it's arguably a rendering. Decide once, and change the rule rather than override each note. The same pattern with Greek is italic by rule ("Alex. ἐντολαί, _commands_"); extending that rule to Hebrew would change 16 notes, some of which are comments, not renderings ("Heb. שוב ambiguous", Isa 51:3; Judg 6:13). Where eBible marks the English as Brenton's italic, it prints italic instead: Judg 9:6 "the word מעא _to find_" (a gloss on the Hebrew, not on the lemma), Judg 17:10 "Heb. ימיס _(year of) days_", and the Latin "_cibus_" in 3 Kgdms 5:25.
3. **Notes on "the words in italics".** 2 Kgdms 17:8, 21:11, 1 Kgdms 17:43 and 3 Kgdms 14:26#2 refer to words Brenton set in italics; this edition prints them in square brackets. Either print the bracketed words in italic, or accept it.
4. **Unlabelled paraphrases.** 1 Cor 14:27 "by two or three sentences separately" has no label and prints roman, though it substitutes cleanly. Probably leave it.
5. **Long passages.** Hag 2:14 ("Not in Hebrew.") and 2 Kgdms 21:11 are about a whole bracketed passage, but their lemmas cover only its first clause. Decide whether lemmas that long are acceptable.
6. **A rule for additions.** "Alex. + '…'" sets no rendering while "Alex. adds '…'" does, so the rules place the two differently, and about 25 overrides now put an addition's lemma on the words it follows. A rule in `inferred_lemma` for notes that add words (the clause before the mark, or its last four words if it runs past nine; the current rule at the start of a verse) gets 35 of the 41 additions right and would retire about 23 overrides. 1 Kgdms 12:13, 3 Kgdms 3:20, Prov 9:6, Gen 1:11#2, Isa 63:19 and 2 Kgdms 6:3 would still need theirs.
7. **"or" inside one rendering.** The rules split "_X_ or _Y_" into two italic runs, which is wrong when the "or" belongs to a single rendering. Overrides join Exod 21:28, Num 1:52, 1 Kgdms 20:6, Ps 25:12, 32:4, 50:21 and Acts 25:6. Still split: Exod 14:15 "_harness_ or _yoke the horses again_", 2 Cor 4:8 "_altogether without help_ or _means_" (the 1611 has a comma before "or"), and 1 Kgdms 30:12 "_staid_ or _established in him_". Zech 9:13 italicizes only "_it with_" of the rendering "it with Ephraim", following eBible.
8. **Brenton's italics for emphasis or citation.** Gen 30:41 ("_from any cause_", "_then_") and 2 Kgdms 5:20#2 ("_Underskiddaw_, _Unterseen_") keep italics that aren't renderings. Decide whether cited words stay italic.
9. **Abbreviations without a full stop.** "chap 5. 25", "ver 16", "ch 1. 14", "Ps 103. 14", "Gen 7. 11", "See v 8." and the like occur about as often as the stopped forms: Judg 21:4; 1 Kgdms 15:3; Ps 146:8; Prov 1:15, 11:13, 20:27, 27:20a; Joel 2:15, 4:18; Mal 3:10; Isa 2:19, 14:16, 23:11, 45:16, 57:21, with Ps 90:6 and Prov 4:11 below. Check which way Brenton printed them, and correct all or none.
10. **Two colons.** A lemma that keeps the verse's own colon prints two: "that believed: for there: or, …" (Luke 1:45; also Luke 4:41 and Rev 14:13).
11. **Prov 30:1** is an empty verse carrying eBible's remark "See chapter 24 for the content of chapter 30.", which prints as if it were Brenton's note. Chapter 31 starts at verse 10 with no remark. Keep the remark as an editorial note, or say where both passages are some other way.

## References that look wrong

Probably slips in Brenton or eBible; check the printed book before correcting.

| Note | Prints | Probably |
| --- | --- | --- |
| Ps 9:27 | Rom. 8. 14 | Rom. 3. 14, which quotes 9:28; the note belongs on 9:28 |
| Isa 29:13 | Mat. 8. 9 | Mat. 15. 8, 9 |
| Isa 53:5 | 1 Pet. 2. 22 | 1 Pet. 2. 24 |
| Deut 32:21 | Rom. 10. 9 | Rom. 10. 19; the quotation starts at "I will provoke them to jealousy" |
| Num 36:7 | Acts 5. 26 | Acts 5. 13 |
| Deut 16:8 | Lev. 23. 6 | Lev. 23. 36 |
| Deut 5:16 | Eph. 6. 1 | Eph. 6. 2, which quotes the verse |
| Prov 3:6 | 2 Tim 2. 13 | 2 Tim. 2. 15 |
| Prov 4:11 | chap 2. 18 | chap. 2. 15 |
| Prov 11:28 | 1 Tim. 5. 8 | 1 Tim. 6. 2 |
| Prov 11:31 | 1 Pet. | 1 Pet. 4. 18 |
| Prov 16:16 | Luke 13. 35 | Luke 13. 34 |
| Prov 14:9 | Job 6. 21 | unknown; Job 6:21 doesn't fit |
| Ps 77:25 | Mat. 6. 31 | John 6. 31, which quotes 77:24, so the mark may belong there |
| Ps 101:25 | Heb. 1. 11,13 | Heb. 1. 10-12, and better at v. 26 |
| 4 Kgdms 16:13 | 2 Chr. 13. 10 | 2 Chr. 13. 11 |
| Col 1:25 (1611) | Rom. 1.19 | Rom. 15.19 |
| Gen 19:13 | See Note, Lam. 3. 21 | eBible has no note there |
| Exod 21:17 | Mat. 15. 4 | belongs to 21:16 in the LXX's order |
| Deut 6:4 | Mat. 22. 37; Luke 10. 27 | these quote 6:5; the mark may stand at the start of the passage |

Some references use Hebrew or English numbering, such as Isa 26:19 "Ps. 110" (LXX 109. 3), Ps 88:21 and 91:11, which each point one verse low, and 4 Kgdms 12:15 "vide v. 13" (v. 14 here); leave them as Brenton printed them.

## Notes that are wrong, swapped or copied in eBible

- **Judg 8:7 and 8:9** look swapped: the Vatican text has ἀλοήσω ("thresh") at 8:7 and κατασκάψω ("dig down") at 8:9, but 8:7 has "Gr. dig down." and 8:9 "Gr. thresh.", which is why 8:9 prints "break: Gr. _thresh_" and 8:7 needs a lemma override.
- **Judg 20:10 and 20:13** are swapped: "Heb. sons of Belial" belongs on "sons of transgressors" in 20:13, and "Gr. it, sc. Gabas" (a typo for Gabaa) on "they" in 20:10.
- **Isa 61:3**: the two notes are swapped. "Alex. reads καταστολὴν as one word" belongs on "the garment of glory", and "Or, anointing" on "oil".
- **Mark 7:4 (1611)**: George swaps the notes. "Or, beds" belongs to "tables", the sextarius note to "pots". The lemmas are already corrected; check the 1611.
- **Exod 32:14** "Gr. dost." is a copy of the note on 32:32; the LXX has ἱλάσθη.
- **2 Kgdms 22:27** repeats "Or, upon the haughty" from 22:28, where it belongs.
- **Deut 9:22**: three notes print the same "Heb. Taberah, Massah, and Kibroth Hattavah."
- **1 Kgdms 29:3–8**: every note begins "to or" (29:3#2, 29:4, 29:5, 29:8), which makes sense only in 29:2.
- **Matt 17:27 (1611)**: George's note ends "is 7.d. ob.", apparently copied from 18:28.
- **eBible's words in Brenton's notes.** Some notes paraphrase the Appendix instead of pointing to it: 2 Kgdms 5:18 ("which refers us to Govett's work…"), Prov 4:5 ("See Appendix - Alexandrian codex has:"), 8:32 and 11:3 (beginning lowercase, "appendix has…" and "the Alexandrine text reads…"), 11:10, 13:5, and Isa 2:6, where "see Appendix which has: “…" pastes in the Appendix's note and never closes the quotation. Brenton probably printed only a pointer to the Appendix.
- **Labels with nothing after them**: 1 Kgdms 20:41 "Gr. See v. 19." (a Greek word lost?), Ps 79:17 "Gr. See Ps. 20. 9.", 1 Kgdms 13:21 "Gr. Such is the meaning...", 1 Kgdms 20:15 "Gr. The meaning of the Heb. is here greatly obscured.", Gen 18:12 "Gr. The difference turns on…", Exod 4:12 "See 1 Cor 2. 16. Gr.", Mal 3:11 "…to be fed. Alex."
- **3 Kgdms 11:27**: the lemma and the rendering are the same, "of his lifting: Gr. _of his lifting_".
- **4 Kgdms 23:36**: the note says "a son of 23 years", but the verse and the Greek say twenty-five (copied from 23:31?).
- **Exod 16:35**: the verse seems to lack "inhabited", and the note's οἰκουμένη has a Latin u.
- **Gen 18:12**: the note is about עדנה ("pleasure", or the Greek's "until now"), so its lemma should be "even until now", not "The thing".
- **1 Kgdms 21:15** "Gr. or man epileptic." is probably "a man epileptic"; if so, the lemma should be "the man is mad".
- **4 Kgdms 19:25** "destruction: Gr. _captivities_": "captivities" (ἀποικεσιῶν) is what Brenton renders "bands of warlike prisoners". Check where the mark stands.
- **Ps 101:17** "Or, then shall be" leaves the verse without a subject when substituted; a word may be lost ("then shall he be seen"?).
- **Prov 21:29**: the marked word already reads “ungodly”, and Swete reports no A substitution there. Check whether “See Alex. ungodly.” belongs on “impudently”; see the retained decision below.
- **Ps 32:2** has a closing quotation mark with no opening one: "Rather, 'confess' or give thanks to.'"
- **Deut 21:5** "bless in his name: Gr. _his name_. Hebraism." fits only if the mark stands before "in". **Josh 18:5** "came to him: Gr. _went through_" should be on "came" alone if the Greek has πρὸς αὐτόν.
- **3 Kgdms 15:2**: Swete confirms A sixteen and B six; Brenton’s Vatican English three still needs checking against Brenton’s printing (see [the editorial queries below](#editorial-queries-on-wording-and-source-text)).
- **Rev 20:13 (1611)** prints "hell: or, _hell_". George marks the 1611's "Or, hell" as a misprint; later printings have "Or, the grave". Correct it as Mark 14:72's "wept" is corrected, or drop the note.

## Probable typos

Could be Brenton's own; check the printing.

- Deut 28:49 "Gr. bear." for "hear"
- Gen 30:27 "argued" for "augured"
- 2 Kgdms 15:20 "Gr. it." for "if"
- Ps 51:1 "Gr. governing." for "understanding"?
- Isa 2:6 "sound to tense" for "sense", and the quotation is never closed
- Isa 52:7 "Joel 2. 2.,'the morning"
- Josh 15:18 "has thou" for "hast"
- 2 Kgdms 13:12 "fasciendum" for "faciendum"
- Exod 39:22 and 4 Kgdms 3:17 "posession"; Exod 12:3 "admissable"
- Ps 49:18 "1 Pe" for "1 Pet."; Ps 90:6 "ver 3" for "ver. 3"
- Gen 41:51 "things belong to my father" for "belonging"; Josh 10:34 "vigourously"; 1 Kgdms 13:21 "interpretors"; 21:8 "repitition"; 4 Kgdms 4:39 "colosynth" for "colocynth"; 24:10 "seige" (a transposition, which no correction category allows)
- 1 Kgdms 6:8 begins lowercase, "in the Alex."; Zech 12:2 "porches or, door-posts" lacks the comma before "or"
- Hebrew that eBible misread and no correction mends yet: 1 Kgdms 17:52 שעריס, 21:3 מקוצ and פלכי אלמבי, 2 Kgdms 5:23 בכאיס, Judg 9:6 מעכ, 9:37 מעס, 17:10 ימיס, 18:7 מבליס; Isa 51:3 שוב
- Greek: Num 1:18 ἐπαξοοῦν, Exod 19:22 ἀπαλλατέω. Gen 3:15 τειρήσει is probably Brenton's own spelling.
- The maqaf in 4 Kgdms 2:14 still needs checking against the printing; eBible has a space.
- Gen 15:11: no closing full stop
- Gal 5:16 (1611) "fulfill" where the text has "fulfil"
- 1611, to check against a facsimile: John 18:28 "Pilats house", Titus 2:9 "gain saying" (one word?), Rev 6:6 "The word choenix, signifieth", 2 Pet 2:11 lowercase "some read"

## Alexandrine readings kept for later work

Numbers 28:24 is intentionally retained as “seven days” for consistency with the surrounding feast instructions. Its footnote gives “two days”; this is a settled editorial choice, rather than an unresolved source query.

### Greek readings without Brenton English (12)

| Decision | Reason retained / remaining issue |
| --- | --- |
| GEN 1:11#2 | Swete supports the fruit-tree reading, but Brenton gives it only in Greek. Printing it in the body would require a new English translation. |
| JDG 9:27#2 | Swete confirms the Greek; Brenton gives no English to insert. A new translation would be needed. |
| JDG 13:5#2 | Swete confirms the Greek; Brenton gives no English to insert. A new translation would be needed. |
| JDG 13:19 | Swete confirms the Greek; Brenton gives no English to insert. A new translation would be needed. |
| 1SA 6:8 | Swete confirms the Greek; Brenton gives no English to insert. A new translation would be needed. |
| 2SA 17:16 | Swete confirms the Greek; Brenton gives no English to insert. A new translation would be needed. |
| 1KI 5:18 | Swete confirms the Greek; Brenton gives no English to insert. A new translation would be needed. |
| 1KI 8:59#3 | Swete confirms the Greek; Brenton gives no English to insert. A new translation would be needed. |
| 2KI 19:24 | Swete confirms the Greek; Brenton gives no English to insert. A new translation would be needed. |
| 2KI 21:6#2 | Swete confirms the Greek; Brenton gives no English to insert. A new translation would be needed. |
| PSA 31:9 | Swete confirms the Greek; Brenton gives no English to insert. A new translation would be needed. |
| ISA 59:7#2 | Swete confirms the Greek; Brenton gives no English to insert. A new translation would be needed. |

### Pointers and explanations without a distinct English reading (8)

| Decision | Reason retained / remaining issue |
| --- | --- |
| 2SA 5:18 | Brenton points to Govett’s discussion of Isaiah without offering replacement English. Checking the Greek in Swete does not supply the missing English; keep the explanation. |
| 1KI 14:21 | Brenton points to the Appendix; Swete confirms A has 14:1–20. The Appendix gives a structural explanation rather than a separate translation, so insertion requires a broader decision about the overlapping passages. |
| BAK 1KI 2:35a | Brenton reports variation here without translating it. Swete records omissions and an addition, but applying them would require English Brenton does not supply. |
| BAK PRO 21:16-17 | Brenton points to an explanatory Appendix note, with no alternative English. Swete reports no A difference at the cited words; there is no distinct passage to insert. |
| PSA 41:5 | Brenton gives an Appendix reference rather than replacement English. Swete confirms a Greek variant, but an English rendering must be identified or supplied before changing the body. |
| PRO 8:5 | Brenton’s Appendix discusses Greek vocabulary without giving a distinct English alternative. Swete reports no A variant here; keep the explanation as a note. |
| PRO 21:16 | Brenton’s pointer concerns Rephaim and 2 Kingdoms, without giving replacement English. Swete reports no A variant here; keep the pointer. |
| ISA 40:4 | Brenton refers to Luke without giving replacement English. Swete supports the Greek reading, but using English from Luke would require a separate editorial decision. |

### Passage placement, chapter divisions, and duplicate text (5)

| Decision | Reason retained / remaining issue |
| --- | --- |
| 1KI 5:14a | Brenton reports a chapter division, which Swete’s layout supports. It changes numbering rather than wording; retain the note under the policy of keeping Brenton’s verse numbers. |
| BAK 1KI 5:17 | Brenton supplies English, and Swete supports its position here, but the same material already appears at 6:1a–b. Inserting it would duplicate the passage; removing the existing words needs a separate decision because Brenton does not mark them for removal. |
| BAK 1KI 6:11-22 | Keep both portions in the Appendix. The first recorded Greek anchor is 15 κέδρου, but the previous promotion placed 6:11–14 after Brenton 6:10 without documenting the anchor mapping. Check that mapping and the second addition’s placement separately; the record does not prove the previous position wrong. |
| BAK 1KI 7:1-12 | Brenton points to verses already printed elsewhere; Swete confirms a different order. There is no separate English passage to insert, and moving the existing verses requires a structural decision. |
| BAK 1KI 14:1-20 | Brenton says the substance is already at Vatican 12:24; Swete confirms A’s passage at 14:1–20. The Appendix supplies no separate English. Resolve the overlap before moving or inserting text. |

### Reports contradicted or unconfirmed by Swete (9)

| Decision | Reason retained / remaining issue |
| --- | --- |
| GEN 6:2 | Keep Brenton’s body wording and Alexandrine note. The recorded angels reading is over an erasure with uncertain attribution (A?vid); establish the reading and hand before promotion. |
| NUM 4:48 | Brenton reports “450”, but Swete’s Alexandrinus reads 8,550. Check Brenton’s printing and establish the correct number before promotion. |
| PSA 118:151 | Brenton offers “commands”, but Swete’s text has “ways” and reports no A substitution at that word. Keep the note until its manuscript basis or verse reference is verified. |
| PSA 130:1 | Brenton reports A adds “for David”; Swete says A omits it. Do not insert the addition while the sources contradict each other; check Brenton’s report. |
| PSA 132:1 | Brenton reports A adds “for David”; Swete records its omission in the apparent original hand of A. Keep the note pending a check of Brenton’s report and the manuscript-hand evidence. |
| PRO 5:13 | Brenton’s proposed change is not supported at verse 13: Swete retains the negative and reports no A difference there. A omits a negative at 5:10 and 5:16 instead; check whether Brenton’s note belongs elsewhere. |
| PRO 21:29 | Brenton’s marked word already reads “ungodly”, and Swete reports no A substitution there. Check whether the note was meant for “impudently” elsewhere in the verse; there is no change to make at its present mark. |
| ZEC 9:5 | Brenton attributes “of her hope” to A; Swete attributes it to Q and gives no A difference from Vaticanus. Keep the note pending an attribution check. |
| ZEC 9:15 | Brenton’s report would reverse altar and bowls. Swete gives “as bowls” to Γ and records no such reversal in A. Keep the note pending a check of its wording and attribution. |

### English requiring correction or clarification (8)

| Decision | Reason retained / remaining issue |
| --- | --- |
| 1SA 30:26 | Brenton offers “from you”, but Swete’s A reading means “to you”. Copying the English would reverse the Greek; check the source and document a correction before insertion. |
| 2KI 3:21#2 | Keep Brenton’s body wording and note. The alternative and above lacks an expressed threshold in the integrated English; the inherited Greek spelling also differs from the Swete record. Resolve the whole clause and source spelling before promotion. |
| BAK 2CH 27:8 | Keep the passage in the Appendix. Brenton’s English gives both twenty-five and sixteen as years reigned, while verse 1 distinguishes age at accession from length of reign. Check the source and document a defensible English correction before promotion. |
| PSA 41:9 | Keep Brenton’s body wording and note. His alternative gives his song shall be, etc., rather than a complete reconstructed clause. Reattaching with me, removing is, and supplying and require a decision about the following prayer phrase and the recorded A¹ reading. |
| ISA 8:1 | Keep Brenton’s body wording and paper/parchment note. The recorded χάρτου addition after τόμον does not settle the attachment of great new or justify replacing the supplied book with the reconstructed phrase a volume of great new paper. |
| ISA 30:8 | Keep Brenton’s body wording and seasons note. The recorded Greek changes case and order; days in seasons would supply a new connecting in and remove many long without a settled English construction. |
| JON 1:8 | Swete confirms an A addition, but Brenton’s “for those whose cause” is ungrammatical and does not match the Greek question. Check the printed wording and document corrected English before insertion. |
| MAL 3:11 | Swete records a noun-case change in A. Its connection to Brenton’s “give a charge for you to be fed” is unclear; establish how the English renders that Greek before replacing the body words. |

### Readings already followed and explanatory notes (14)

Review these current decisions too, including cases where the body already follows Alexandrinus or the note supplies an explanation rather than replacement wording.

| Decision | Current reason retained |
| --- | --- |
| GEN 33:18 | The verse already translates Alexandrinus παρενέβαλε as “took up a position”; the alternative “pitched his tent” is another translation of the same reading. |
| JDG 9:6 | The omitted Greek εὐρετῆ already has no separate English words in Brenton’s verse; his text “of Sedition” follows Alexandrinus here. |
| JDG 21:22 | Brenton expressly says the existing English “according to the occasion” is translated from Alexandrinus. |
| 2SA 11:25 | Brenton’s verse already prints “strengthen him”, following A. |
| 2SA 15:12 | Brenton’s translation already follows A’s conspiracy reading. |
| 1KI 1:9 | The verse already follows A: “by the stone of Zoelethi”. |
| 1KI 2:35a | Appendix pointer; passage handled separately. |
| PSA 49:19 | The note reports a manuscript lacuna rather than English verse wording. |
| ISA 2:6 | The Appendix note explains the LXX rendering Philistines rather than giving an Alexandrine variant. |
| ISA 7:18 | Brenton explicitly says the verse’s existing wording is already the Alexandrine reading. |
| ISA 54:10 | Brenton explicitly adopts the Alexandrine reading already in the verse. |
| ISA 61:3 | The note is about Greek word division, with no alternative English wording. |
| ISA 66:5 | The English already says “our”; the Alexandrine reading is already in the verse. |
| ZEC 14:7 | The verse already translates A’s ψύχος as cold; the footnote explains the adopted reading. |

## Editorial queries on wording and source text

Check the wording and source spellings of promoted readings. The 4 Kingdoms 3:21 spelling check also applies to its deferred decision above.

| Passage | Remaining work |
| --- | --- |
| Deuteronomy 32:42 | The English has “their Gentiles”. Decide what “their” refers to before retaining or removing this supplied word. |
| 3 Kingdoms 15:2 | Swete confirms Alexandrine sixteen but gives Vatican six; Brenton’s body has three. Check Brenton’s printing to establish whether three is his reading or a transcription error. The footnote currently distinguishes the two sources. |
| 4 Kingdoms 3:21; Psalm 138:9 | The inherited notes give ἐπάνα and ὄρθον; the repository’s Swete record gives A’s ἐπάνω and ὄρθρον. Check Brenton’s printing to determine where the discrepant spellings arose. The 4 Kingdoms reading is restored to its original note; the retained Psalm footnote distinguishes the forms. |

### Optional historical-label note

Proverbs 15:33: the original Appendix label “16 (Alex.15) 33” remains in the source metadata. Printing a historical-label note is optional; the relocated saying is present in the body.
