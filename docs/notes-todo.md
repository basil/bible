# Notes: open questions

Left over from the footnote reviews of September 2026. Each item needs a decision, or a check against Brenton's 1851 printing or a 1611 facsimile, before anything changes. Nothing here is fixed yet.

## Decisions on the rules

1. **1611 notes on a whole verse.** Luke 17:36 ("This 36. verse is wanting in most of the Greek copies") reprints the whole verse as its lemma, and John 18:13's note on the order of events prints under "year". `kjv-notes.json` now allows `"lemma": null`, as `brenton-notes.json` does; decide whether to give these two notes one.
2. **"Heb. <Hebrew> <English>".** The English after a Hebrew word stays roman almost everywhere ("Emec Achor: Heb. עמק עכור valley of trouble"; 1 Kgdms 4:15, 14:6, 14:26, 17:52, 20:12), though it's arguably a rendering. Decide once, and change the rule rather than override each note. The same pattern with Greek is italic by rule ("Alex. ἐντολαί, _commands_"); extending that rule to Hebrew would change 16 notes, some of which are comments, not renderings ("Heb. שוב ambiguous", Isa 51:3; Judg 6:13). Where eBible marks the English as Brenton's italic, it prints italic instead: Judg 9:6 "the word מעא _to find_" (a gloss on the Hebrew, not on the lemma), Judg 17:10 "Heb. ימיס _(year of) days_", and the Latin "_cibus_" in 3 Kgdms 5:25.
3. **Notes on "the words in italics".** 2 Kgdms 17:8, 21:11, 1 Kgdms 17:43 and 3 Kgdms 14:26#2 refer to words Brenton set in italics; this edition prints them in square brackets. Either print the bracketed words in italic, or accept it.
4. **Unlabelled paraphrases.** 1 Cor 14:27 "by two or three sentences separately" has no label and prints roman, though it substitutes cleanly. Probably leave it.
5. **Long passages.** Hag 2:14 ("Not in Hebrew.") and 2 Kgdms 21:11 are about a whole bracketed passage, but their lemmas cover only its first clause. Decide whether lemmas that long are acceptable.
6. **The Hebrew in the notes.** eBible confuses similar letters throughout (ב/כ, ם/ס, צ/ע, ט/ס, ת/ה, ת/ח, ד/ר, ג/ו, ז/ו, נ/כ), e.g. Judg 2:1 ככיס for בכים, 13:12 משפס for משפט, 1 Kgdms 14:41 חמיס for תמים, 19:13 כבר for כבד, 4 Kgdms 23:5 הבמויס for הכמרים. Others: Num 16:15 (חמד for חמור), 18:11; Deut 33:2; Judg 2:18, 4:7; 1 Kgdms 13:3, 14:26, 14:40, 15:8, 20:12, 23:15, 27:8, 29:3; 2 Kgdms 1:19, 2:23; 3 Kgdms 5:25, 14:28, 16:28e, 21:10; 4 Kgdms 2:14, 12:16, 14:7, 15:5, 15:10, 23:5#3; Isa 51:3. This needs one pass against the printed book, not note-by-note corrections.
7. **A rule for additions.** "Alex. + '…'" sets no rendering while "Alex. adds '…'" does, so the rules place the two differently, and about 25 overrides now put an addition's lemma on the words it follows. A rule in `inferred_lemma` for notes that add words (the clause before the mark, or its last four words if it runs past nine; the current rule at the start of a verse) gets 35 of the 41 additions right and would retire about 23 overrides. 1 Kgdms 12:13, 3 Kgdms 3:20, Prov 9:6, Gen 1:11#2, Isa 63:19 and 2 Kgdms 6:3 would still need theirs.
8. **"or" inside one rendering.** The rules split "_X_ or _Y_" into two italic runs, which is wrong when the "or" belongs to a single rendering. Overrides join Exod 21:28, Num 1:52, 1 Kgdms 20:6, Ps 25:12, 32:4, 50:21 and Acts 25:6. Still split: Exod 14:15 "_harness_ or _yoke the horses again_", 2 Cor 4:8 "_altogether without help_ or _means_" (the 1611 has a comma before "or"), and 1 Kgdms 30:12 "_staid_ or _established in him_". Zech 9:13 italicizes only "_it with_" of the rendering "it with Ephraim", following eBible.
9. **Brenton's italics for emphasis or citation.** Gen 30:41 ("_from any cause_", "_then_") and 2 Kgdms 5:20#2 ("_Underskiddaw_, _Unterseen_") keep italics that aren't renderings. Decide whether cited words stay italic.
10. **Abbreviations without a full stop.** "chap 5. 25", "ver 16", "ch 1. 14", "Ps 103. 14", "Gen 7. 11", "See v 8." and the like occur about as often as the stopped forms: Judg 21:4; 1 Kgdms 15:3; Ps 146:8; Prov 1:15, 11:13, 20:27, 27:20a; Joel 2:15, 4:18; Mal 3:10; Isa 2:19, 14:16, 23:11, 45:16, 57:21, with Ps 90:6 and Prov 4:11 below. Check which way Brenton printed them, and correct all or none.
11. **Two colons.** A lemma that keeps the verse's own colon prints two: "that believed: for there: or, …" (Luke 1:45; also Luke 4:41 and Rev 14:13).
12. **Prov 30:1** is an empty verse carrying eBible's remark "See chapter 24 for the content of chapter 30.", which prints as if it were Brenton's note. Chapter 31 starts at verse 10 with no remark. Keep the remark as an editorial note, or say where both passages are some other way.

## References that look wrong

Probably slips in Brenton or eBible; check the printed book before correcting.

| Note | Prints | Probably |
|---|---|---|
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
- **Gen 43:13** "Gr. one." fits nothing in the verse; it glosses "other" in 43:14 (τὸν ἀδελφὸν ὑμῶν τὸν ἕνα).
- **Exod 32:14** "Gr. dost." is a copy of the note on 32:32; the LXX has ἱλάσθη.
- **2 Kgdms 22:27** repeats "Or, upon the haughty" from 22:28, where it belongs.
- **4 Kgdms 11:9** "Gr. hands." fits nothing in the verse; it probably glosses "two parties" in 11:7 (δύο χεῖρες).
- **Deut 9:22**: three notes print the same "Heb. Taberah, Massah, and Kibroth Hattavah."
- **1 Kgdms 29:3–8**: every note begins "to or" (29:3#2, 29:4, 29:5, 29:8), which makes sense only in 29:2.
- **Matt 17:27 (1611)**: George's note ends "is 7.d. ob.", apparently copied from 18:28.
- **Missing Alexandrine verses**: notes announce verses that aren't in the text: 1 Kgdms 17:41, 17:50, 17:55–58, 18:9–11, 18:17–19 (and 18:1–5, with no note), 23:12, 3 Kgdms 13:27, 14:1–20, 15:32. "Alex. has the following." is followed by nothing. Brenton's Appendix, printed after Revelation, has all of them except 1 Kgdms 23:12, so the notes could send the reader there.
- **1 Kgdms 17:11** says "See Appendix" for verses 12–31, which this edition prints in the text as well as in the Appendix. The notes on 17:11–31 also have a space after the mark and the ligature ﬁ in "ﬁrst-born".
- **eBible's words in Brenton's notes.** Some notes paraphrase the Appendix instead of pointing to it: 2 Kgdms 5:18 ("which refers us to Govett's work…"), Prov 4:5 ("See Appendix - Alexandrian codex has:"), 8:32 and 11:3 (beginning lowercase, "appendix has…" and "the Alexandrine text reads…"), 11:10, 13:5, and Isa 2:6, where "see Appendix which has: “…" pastes in the Appendix's note and never closes the quotation. Brenton probably printed only a pointer to the Appendix.
- **Labels with nothing after them**: 1 Kgdms 20:41 "Gr. See v. 19." (a Greek word lost?), Ps 79:17 "Gr. See Ps. 20. 9.", 1 Kgdms 13:21 "Gr. Such is the meaning...", 1 Kgdms 20:15 "Gr. The meaning of the Heb. is here greatly obscured.", Gen 18:12 "Gr. The difference turns on…", Exod 4:12 "See 1 Cor 2. 16. Gr.", Mal 3:11 "…to be fed. Alex."
- **3 Kgdms 11:27**: the lemma and the rendering are the same, "of his lifting: Gr. _of his lifting_".
- **4 Kgdms 23:36**: the note says "a son of 23 years", but the verse and the Greek say twenty-five (copied from 23:31?).
- **Exod 16:35**: the verse seems to lack "inhabited", and the note's οἰκουμένη has a Latin u.
- **Gen 18:12**: the note is about עדנה ("pleasure", or the Greek's "until now"), so its lemma should be "even until now", not "The thing".
- **1 Kgdms 21:15** "Gr. or man epileptic." is probably "a man epileptic"; if so, the lemma should be "the man is mad".
- **4 Kgdms 19:25** "destruction: Gr. _captivities_": "captivities" (ἀποικεσιῶν) is what Brenton renders "bands of warlike prisoners". Check where the mark stands.
- **Ps 101:17** "Or, then shall be" leaves the verse without a subject when substituted; a word may be lost ("then shall he be seen"?).
- **Prov 21:29** "See Alex. ungodly." probably records an Alexandrine "ungodly" for "impudently"; if so, it's a rendering on "impudently".
- **Ps 32:2** has a closing quotation mark with no opening one: "Rather, 'confess' or give thanks to.'"
- **Deut 21:5** "bless in his name: Gr. _his name_. Hebraism." fits only if the mark stands before "in". **Josh 18:5** "came to him: Gr. _went through_" should be on "came" alone if the Greek has πρὸς αὐτόν.
- **3 Kgdms 15:2** "Alex. 16 years" for Abiu's three-year reign; 6 would be expected.
- **Rev 20:13 (1611)** prints "hell: or, _hell_". George marks the 1611's "Or, hell" as a misprint; later printings have "Or, the grave". Correct it as Mark 14:72's "wept" is corrected, or drop the note.

## Probable typos

Could be Brenton's own; check the printing.

- Deut 28:49 "Gr. bear." for "hear"
- Gen 30:27 "argued" for "augured"
- 2 Kgdms 15:20 "Gr. it." for "if"
- Ps 51:1 "Gr. governing." for "understanding"?
- Isa 2:6 "sound to tense" for "sense", and the quotation is never closed
- Isa 52:7 "Joel 2. 2.,'the morning"
- Deut 24:13 "ie." for "i. e."
- Josh 15:18 "has thou" for "hast"
- 2 Kgdms 13:12 "fasciendum" for "faciendum"
- Exod 39:22 and 4 Kgdms 3:17 "posession"; Exod 12:3 "admissable"
- Ps 49:18 "1 Pe" for "1 Pet."; Ps 90:6 "ver 3" for "ver. 3"
- Gen 41:51 "things belong to my father" for "belonging"; Josh 10:34 "vigourously"; 1 Kgdms 13:21 "interpretors"; 21:8 "repitition"; 4 Kgdms 4:39 "colosynth" for "colocynth"; 24:10 "seige" (a transposition, which no correction category allows); 24:17 "Mattanaiah" for "Mattaniah"
- 1 Kgdms 6:8 begins lowercase, "in the Alex."; Zech 12:2 "porches or, door-posts" lacks the comma before "or"
- Greek: Prov 8:5 ἄκατος for ἄκακος, Isa 59:7 ὐφρόνων for ἀφρόνων, Ps 93:19 ἠὺφπαναν for ηὔφραναν, Num 1:18 ἐπαξοοῦν, Judg 18:7 θησανροὺς, 13:19 θανμαστὰ
- More Greek: Gen 6:7 ἐθμώθην for ἐθυμώθην, Exod 19:22 ἀπαλλατέω, Judg 9:27 χορὺς, 9:37 ὐπὸ for ἀπὸ, 13:5 Ναζίραῖον, 2 Kgdms 1:19 τεθηκότων and τραυματτιῶν, 15:12 σὺστρεμμα, 3 Kgdms 5:18 ἀπαντήμα, 18:21 γόνν for γόνυ, 4 Kgdms 3:21 ἐπάνα for ἐπάνω, 8:28 ἀλλοφύλοι, 17:21 ἀπ᾿οἴκου (no space), 19:30 οἴκον for οἴκου, Joel 4:4 ἀλλοφυλων. Gen 3:15 τειρήσει is probably Brenton's own spelling.
- 1 Kgdms 17:8 "עברי being read as if עברי": the first should be עבדי
- Gen 15:11: no closing full stop
- Gal 5:16 (1611) "fulfill" where the text has "fulfil"
- 1611, to check against a facsimile: John 18:28 "Pilats house", Titus 2:9 "gain saying" (one word?), Rev 6:6 "The word choenix, signifieth", 2 Pet 2:11 lowercase "some read"
