# Notes: open questions

Open questions and source discrepancies from the footnote reviews. Every reading from Codex Alexandrinus has its decision in `edition/alexandrinus.json`; the questions below need an editor's decision or further evidence, and each names the evidence already gathered.

## How to read this list

The sections:

- [Rules to decide](#1-rules-to-decide): one decision settles many notes.
- [Questions from the source review](#2-questions-from-the-source-review): Brenton's reports of Codex Alexandrinus that the evidence does not settle, printed oddities, witness labels, and lemmas left for a decision.

**Keys.** Brenton's notes are named by their keys, the `x-key` the build gives each source note ([AGENTS.md](../AGENTS.md#the-document-model)), which a decision in `edition/` is filed under:

- Books are USFM codes: `1SA`–`2KI` are 1–4 Kingdoms, `PRO` Proverbs, `JOL` Joel, and `BAK` Brenton's Appendix, whose entries in `alexandrinus.json` are named by the verse they concern, as `BAK 1KI 2:35a`, and whose notes `appendix.json` names by the verse they stand at.
- Chapters and verses are eBible's, as its transcription of Brenton numbers them, so the Psalms and Joel are numbered as in the Greek, and some verses are lettered, as `1KI 5:14a`. Where the edition numbers a verse otherwise, by [docs/numbering.md](numbering.md), a key still names it by eBible's number.
- `#2` is a verse's second note; a key without it is the verse's first or only note.

A 1611 marginal note is named by its verse and `(1611)`, as `1CO 14:27 (1611)`; its key in `edition/kjv-notes.json` adds the words George prints it under, as `1CO 14:27 two...`.

**Cross-references.** A note with more than one problem is listed under each, and each listing names the others in brackets, as [also **Two colons**].

**Sources.** eBible is the transcription of Brenton that the build reads, and George is Calvin George's transcription of the 1611 notes ([sources/README.md](../sources/README.md)). Swete is the Greek edition whose apparatus checks Brenton's reports of Codex Alexandrinus. In its sigla, A is Codex Alexandrinus, A* its first hand and A¹ and Aᵃ correcting hands, "vid" marks an uncertain reading, and Q and Γ are other manuscripts. A displaced reading is labelled `Vat.` only where Swete's B main text positively supports it, with the hand where a corrector of B changes the unit; otherwise it is labelled `Brenton`, whose English renders Valpy's printed Greek (the introduction, `content/introduction.sfm`).

**Closing an item.** Record the decision in `edition/` with its reason, as [AGENTS.md](../AGENTS.md#where-a-change-goes) says, and delete the item here in the same commit.

## 1. Rules to decide

Each of these is a question about a rule. One decision settles every note it covers.

- **Two colons.** A lemma that keeps the verse’s own colon prints two: "to speak: for they knew that he was Christ: or, …" (LUK 4:41 (1611)) and "from henceforth: Yea, saith the Spirit: or, …" (REV 14:13 (1611)), and "because of their early burdens: they shall be pained because of their toils; and ye have hated him that reproved in the gates: not in Hebrew" (HAG 2:14), whose lemma takes in the whole passage the Hebrew lacks. Decide whether these lemmas should keep their internal colon.
- **Footnote callers that Brenton sets elsewhere.** A lemma override puts a note on the words Brenton's caller marks, but a footnote's printed caller stays where eBible has it: GEN 2:23#3 (before “of”, where the 1879 and 1900 printings set τ before “her”), DEU 21:5 (before “bless”; Brenton's before “in”), and ISA 19:3 (seven words before its lemma, where CCEL has it before the lemma). Decide whether a footnote's caller should follow its lemma.
- **A corrector's reading printed without its hand.** 2CH 3:4 CCEL (A^a over an erasure and in the margins, A* apparently lacking the clause), PSA 92:3, and EZK 1:27 print readings Swete gives to a corrector of A, and their notes name only the displaced witness, while a corrector of B is named (“Vat. first hand”). Decide whether these notes should say that the printed reading is a corrector's.
- **“Vat.” for a free rendering of B's Greek.** 2CH 34:8 CCEL labels Brenton's free “after having cleansed” Vat., PSA 16:14 labels his “uncleanness” (for B's ὑείων) Brenton, and 2CH 28:12 CCEL labels his “Udias” Vat. though B reads Οὐδειά. Decide whether displaced English that renders B's Greek freely, or spells a name otherwise, takes “Vat.” or “Brenton”.
- **A silent unit that a report already settles.** `REV 21:2#2` (RP's εἶδον re-placed after καινήν) is flagged as wanting an override because Boyd's apparatus reports a translatable difference there; but that report (TCENT 529, “I, John” for “I”) is the one `REV 21:2#1` already carries out, and the FAA placement spans both units. Decide whether a `nochange` reading on #2, or a placement of TCENT 529 on #1 alone, closes it. The 69 silent units whose only reports come from the hyper-literal lists (FAA, MSB, WEB) need a ruling on whether those lists alone can establish a change.
- **Revised Version and Boyd's ASV borrowed by hand where the automatic witness is not admitted.** The automatic rule takes the RV only where Westcott–Hort agrees with the Byzantine reading; seven readings borrow it by hand at units the review marks not admitted (REV 2:3#1+#2, REV 7:4#1+#2, REV 13:8#1, MRK 1:16#1, MRK 6:9#1), and two borrow Boyd's ASV at REV 13:14#3+#4, where Appendix A changes the verse. Admission is a heuristic for the automatic witness, and hand borrowing is allowed where the RV's words render the Byzantine Greek; decide whether the review should list these, or the build check that the quoted wording renders RP's Greek rather than Westcott–Hort's.
- **Reports Swete supports that stay notes.** The promotion rule prints a kept report whose `agrees` is true and whose note gives Brenton's English, unless the reading is doubtful or a slip. Three stay notes on other grounds: EZK 16:21 CCEL (“Alex. omits ‘them’”; Swete III p. 412 αυτα αυτοις] εν αυτοις A, confirmed on the scan, so A also adds the unreported ἐν), 2CH 15:11 CCEL (“seven rams”; Swete II p. 85 επτακοσιους] επτα·|κριους A, whose point after επτα separates seven from rams; `agrees` is still false), and EZK 44:14 CCEL (“and they shall appoint”; A's και ταξουσιν αυτου looks like a slip for κατάξουσιν αὐτούς). Decide whether each is promoted, kept as a slip, or kept under a further exception the rule should name.

## 2. Questions from the source review

Found while checking notes against the 1844, 1879, and 1900 printings and against Swete. Each note stays as it is now, with its evidence in the decision's `why` where it has one; none changes without the decision named.

### 2.1 Promoted readings: what the verse prints

How the verse reads once a report of Codex Alexandrinus is carried out.

#### How far a reading reaches

The verse changes more, or less, than Brenton's report covers.

- `EZK 1:26 CCEL`: Besides Brenton’s reported “when they stood their wings were let down”, the verse prints “; and above the firmament that was over their head”, the King James clause of 1:26 with “heads” changed to “head” and its italic “was” made roman, for the rest of A’s addition (Swete III p. 387); “above the firmament that was over their head” is also Brenton’s own wording for the same Greek at 1:25, so only “and” needs the King James. Decide whether to print Brenton’s reported clause alone.
- `ISA 40:4`: Brenton’s note (“Luke 3. 5, with which Alex. agrees”) covers a clause where Swete III p. 173 records two A differences, om παντα A and πεδια] οδους λιας A. The decision carries out only the second, so the verse prints “and all the crooked ways shall become straight, and the rough places smooth ways”, B’s πάντα beside A’s ὁδοὺς λείας. Decide whether “all” goes too, with the displaced note naming Vat. for it.
- `HOS 13:3 CCEL`: The decision drops the article of “as a smoke”, outside the words Brenton's caller marks. Decide whether to keep “a”.

#### English from no single source

Splices, compositions, and the editor's own words.

- `EZK 11:6 CCEL`: The verse prints “the ways thereof”: Brenton’s “ways” in the King James frame “the streets thereof”, for A’s αυτης (Swete III p. 402). No source has these words together. Decide whether to keep the splice, or keep Brenton’s “your ways” and report A in a kept note.
- `EZK 23:32 CCEL`: The verse prints “it shall be for derision and scorn”, where Brenton’s note has “derision, or, scorn”; the “and” is the editor’s, for A’s εις γελωτα και εις μυκτηρισμον (Swete III p. 433), and the displaced note quotes that form. The verse also drops the “and” before “full” for Swete’s om και 2° AQ, which Brenton does not report. Decide whether Brenton’s “or” offers two renderings of one word or names two, and print accordingly.
- `1KI 5:31`: The completion of 6:1, “that he began to build the house to the Lord”, is the King James “that he began to build the house of the LORD” with “to” for “of”, rendering A's τω κ̅ω̅ (Brenton's own phrase at 6:2), and the decision names no source for it. Decide whether to take the King James words exactly or declare the composition.
- `JOB 39:22 CCEL`: The verse prints “as he meeteth it”; “it” is declared supplied but comes from no named translation. Decide whether to narrow the `from` to “a king” and keep Brenton's “as he meets him”.

### 2.2 Passages and verse structure

Supplied passages, omitted verses, and words moved across verses.

- `EZK 33:25`: A has the divine-speech formula twice (Swete III p. 457): ουτως ειπεν αδωναι κ̅ς̅ opening its prefixed 25, and ταδε λεγει kept before ζω εγω at 27. The passage edit replaces eBible’s “Therefore say to them, Thus saith the Lord God,” with the Appendix’s 33:25, so the edition prints the formula once and 33:27 opens “As I live”. Narrowing the edit’s `from` does not help: the remaining formula would stand at the end of 25, before the inserted 26. A working alternative is a passage edit on 33:27 that sets Brenton’s “Thus saith the Lord God” (Appendix span [41, 65]) before “As I live”, with a note that Brenton has it at 33:25. Decide whether to move Brenton’s words across his verse boundary so.
- `1KI 5:14a`: Brenton's “Here the chapter ends, according to Heb. and Alex.” agrees with Swete I p. 683, “om και ελαβεν…Γαζερ 2° A”: A lacks 5:14a–b here. The entry is kept with `agrees` null as a remark on chapter division. Decide whether to omit 5:14a–b with their words in a note on 5:14, as at 2SA 5:16a.

### 2.3 Promote or keep: the evidence

Whether Swete settles a report well enough to print it, or it stays a note.

- `JER 51:28 CCEL`: Brenton's “Alex. ‘who go down to’” is kept; promoting it would leave A's unreported και untranslated. Decide whether to promote it.
- `EZK 43:7 CCEL#2`: The kept entry rests on Swete's silence at XLIII 7 (III p. 481); Swete's Appendix (III p. 881) is still rough and has not been read there. Decide whether to have it read for an orthographic entry of A.
- `1CH 1:11-23`: The passage prints 1:12, which Swete writes as wholly over an erasure, perhaps by A^a (“sup ras A^a?”), without a note; the doubtful-reading rule keeps such a reading as a note. Decide whether 1:12 prints with a note saying so, is omitted, or is recorded as an exception.

### 2.4 Where a note stands

Callers and lemmas.

#### Notes the words do not place

- `JER 50:10 CCEL` (`13.l#3`): “Or, such as are, and so on.” is confirmed as printed (1879 physical 983 / 1900 physical 979, printed 967; 1844 vol. 2 physical 293, printed 790), with caller δ (1844 †) before “lift up weapons against them” in all three. The gloss renders verse 11: “such as are” is the KJV's wording at the parallel Jer. 43:11 for οὓς εἰς θάνατον, which Brenton renders “delivering some for death to death” with “delivering” supplied in italics; nothing in verse 10 (Swete III p. 342) fits it. Decide whether to keep Brenton's caller or to move the note before “delivering some” in 50:11 with a placement in `ccel-notes.json`, as at EZK 17:20.
- CCEL notes the words do not place: of the ten listed in the review as left out, eight are already in eBible at their verses. Two are not: `iv.39#1` (“Setting forth of it.”, EXO 40, at “shalt set forth that which is to be set forth”) and `14#1` (“Words bracketed not in Heb.”, on the prologue before Lamentations 1:1, whose brackets the edition does not print). Decide whether to bring the first in with a placement in `ccel-notes.json`; the second stays out.

### 2.5 What a note or verse prints

Wording and punctuation.

#### Punctuation

- `EZK 40:38 CCEL`: The printed note splits Brenton's quotation into two italic runs and drops his comma before “(39)”. Decide whether to keep the comma.
- `JDG 13:5#2`: Brenton's “Matt. 2 ult.” prints as “Matt. 2:23. Ναζειραῖον”, keeping the full stop of “ult.” Decide whether to drop it by a revision.
- `EZK 48:35 CCEL#2`: The city's name keeps Brenton's quotation marks (“‘the Lord is there’ shall be the name thereof”). Decide whether it prints bare, as the King James's does.

## 3. Future work

### Website tables of mechanical changes

Publish searchable, website-only tables of the edition’s changes in spelling, vocabulary, grammar, punctuation, capitalization, and presentation, after the documentary example of Scrivener’s introduction and appendices to the _Cambridge Paragraph Bible_: his Appendix A catalogues every change of text with the edition that introduced it, his Section V treats orthography, grammar, and capitals, and the end of Section III describes the list of italic changes, with reasons, that he deposited with the Press. These are models for recording exact changes and reasons, not evidence that this edition follows his individual decisions. The printed introduction explains the conventions and gives representative examples; it does not yet promise the full tables, so mention them there once they are published.

Derive the tables from the decisions and the transformations actually applied, with links back to the reader’s verses. Do not maintain a second hand-copied catalogue. Each row should identify the source form, printed form, kind of change, reason, affected passages, and exceptions; distinguish the number of rules from the number of affected occurrences. Record the baseline, decision key, and source of each comparison, and distinguish source-transcription repairs from editorial revision. A reader should be able to recover the precise before-and-after wording without confusing a source address with the edition’s numbering.

The tables need these separate scopes:

- **Spelling and vocabulary:** unscoped whole-word and phrase revisions in `edition/revisions.json` can affect scripture, notes, and source front or back matter. Give their declared exceptions; do not describe vocabulary changes as spelling alone.
- **Grammar:** scripture-scoped rules affect numbered scripture, including Psalm superscriptions, and marked note lemmas and readings. They do not automatically affect headings, introductions, or explanatory commentary. Include note-key restrictions where a form can also be a noun, along with the article, possessive, and participle rules and their actual scopes. Plain quotation marks do not establish scripture scope.
- **Names:** group `names.decisions` by the identified person or place, with both the verses respelled and the explicitly kept occurrences. Commentary and front matter retain the source names. Do not merge Azarias and Ozias for the king of Judah or turn bearer-specific decisions into global substitutions.
- **Punctuation:** distinguish systematic rules from verse-specific decisions and from `passages` decisions on a keyed note or a front/back-matter unit. Show the context and before-and-after form; do not imply that a verse’s local revision also applies to every occurrence elsewhere.
- **Capitalization and type:** distinguish removal of selective emphatic small capitals from retained decorative openings and structural headings. Record supplied-word italics becoming ordinary type separately from wording changes: supplied-word markup remains in the prepared document, and italic titles and alternative readings still print. Do not infer changes in wording by comparing PDF glyphs.
- **Paragraphs and poetry:** record the line and stanza divisions supplied by the Updated Brenton and the role of Scrivener’s poetic setting as a second witness where a counterpart exists. No Updated Brenton wording is borrowed. Distinguish explicit line decisions, inferred boundaries, chapter-opening paragraphs, and retained New Testament paragraphing.

The provenance should come from `edition/revisions.json`, `edition/lines.json`, the semantic document stages, and their actual results; the maintainer source catalogue is `sources/README.md`. Keep textual readings, shared-Greek corrections, and numbering correspondence linked to their existing reviews or website tables, rather than recategorizing them as mechanical changes. Verify the exported counts against applied occurrences and check both scope exclusions and representative changed passages before publishing. This is deferred work: no new export, route, or table is implemented by this task.
