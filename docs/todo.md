# Notes: open questions

The open questions left over from the footnote reviews of September 2026. None of them is settled yet: each needs a decision or a check of the Greek before anything changes. Brenton's printings of 1844, 1879 and 1900 have been checked for every note that turned on them; what remains does not.

## How to read this list

The sections:

1. [Rules to decide](#1-rules-to-decide): one decision settles many notes.
2. [Readings from Codex Alexandrinus](#2-readings-from-codex-alexandrinus): readings not yet printed in the text.

**Keys.** Brenton's notes are named by their keys, the `x-key` the build gives each source note ([AGENTS.md](../AGENTS.md#the-document-model)), which a decision in `edition/` is filed under:

- Books are USFM codes: `1SA`–`2KI` are 1–4 Kingdoms, `PRO` Proverbs, `JOL` Joel, and `BAK` Brenton's Appendix, whose entries in `alexandrinus.json` are named by the verse they concern, as `BAK 1KI 2:35a`.
- Chapters and verses are Brenton's, so the Psalms and Joel are numbered as in the Greek, and some verses are lettered, as `1KI 5:14a`.
- `#2` is a verse's second note; a key without it is the verse's first or only note.

A 1611 marginal note is named by its verse and `(1611)`, as `1CO 14:27 (1611)`; its key in `edition/kjv-notes.json` adds the words George prints it under, as `1CO 14:27 two...`.

**Cross-references.** A note with more than one problem is listed under each, and each listing names the others in brackets, as [also 1.2].

**Sources.** eBible is the transcription of Brenton that the build reads, and George is Calvin George's transcription of the 1611 notes ([sources/README.md](../sources/README.md)). Swete is the Greek edition whose apparatus checks Brenton's reports of Codex Alexandrinus. In its sigla, A is Codex Alexandrinus, A¹ its first hand and Aᵃ a corrector, "vid" marks an uncertain reading, and Q and Γ are other manuscripts; Vat. is the Vatican text Brenton translates, Codex Vaticanus supplied from other copies where it is lacking.

**Closing an item.** Record the decision in `edition/` with its reason, as [AGENTS.md](../AGENTS.md#where-a-change-goes) says, and delete the item here in the same commit.

## 1. Rules to decide

Each of these is a question about a rule. One decision settles every note it covers.

1. **Notes on "the words in italics".** 2SA 17:8, 2SA 21:11 [also 1.2], 1SA 17:43 and 1KI 14:26#2 refer to words Brenton set in italics, which this edition prints in square brackets. Either print the bracketed words in italics too, or accept the mismatch.
2. **Lemmas on a long passage.** HAG 2:14 ("Not in Hebrew.") and 2SA 21:11 [also 1.1] are about a whole bracketed passage, but their lemmas cover only its first clause. Decide whether a lemma that long is acceptable.
3. **"or" inside one rendering.** The rules split "_X_ or _Y_" into two italic runs, which is wrong when the "or" belongs to a single rendering. Overrides join EXO 21:28, NUM 1:52, 1SA 20:6, PSA 25:12, PSA 32:4, PSA 50:21 and ACT 25:6 (1611). Still split: EXO 14:15 "_harness_ or _yoke the horses again_", 1SA 30:12 "_staid_ or _established in him_". Decide whether these two should be joined.
4. **Two colons.** A lemma that keeps the verse’s own colon prints two: "to speak: for they knew that he was Christ: or, …" (LUK 4:41 (1611)) and "from henceforth: Yea, saith the Spirit: or, …" (REV 14:13 (1611)). Decide whether these lemmas should keep their internal colon.

## 2. Readings from Codex Alexandrinus

The 26 decisions in `kept` in `edition/alexandrinus.json` that carry `"todo": true` are readings that are still only notes. Each is settled by printing the reading, which moves its decision to `readings` or `passages`, or by keeping the note for good, which removes its `todo` and updates its `why`. Sections 2.1–2.5 group them by what stands in the way.

### 2.1 Greek with no English from Brenton (9)

Swete confirms the Greek, but Brenton gives it only in Greek. The edition supplies such English from Ottley's translation of Alexandrinus Isaiah or from the King James Version or the Revised Version where they render A's text ([docs/edition.md](edition.md#readings-from-codex-alexandrinus)); each of these needs that English found and shown to render A, or a ruling that none does.

GEN 1:11#2, JDG 9:27#2, JDG 13:5#2, JDG 13:19, 1SA 6:8, 2KI 19:24, 2KI 21:6#2, PSA 31:9, MAL 3:11 (A's τὴν βρῶσιν, which Brenton gives after his own alternative rendering).

### 2.2 A pointer with no English (1)

A has a different reading, but Brenton only points to it, and gives no English to print. The rule of 2.1 bears on these too.

| Decision | What stands in the way |
| --- | --- |
| PSA 41:5 | Brenton gives a reference to the Appendix rather than English, and the Appendix discusses the Hebrew behind the verse. Swete cites no variant of A here: εἰσελεύσομαι is R's. Decide whether there is an Alexandrine reading at all. |

### 2.3 Brenton and Swete disagree (1)

| Decision | Brenton | Swete |
| --- | --- | --- |
| GEN 6:2 | A has "angels of God" for "sons of God", in every printing | ἄγγελοι stands over an erasure, and the attribution to A is doubtful (A^{?vid}, confirmed on the scan); establish the reading and the hand |

### 2.4 English to correct or clarify (1)

Brenton's English for the reading is wrong, incomplete or unclear, and his printings read as eBible has them. Record a correction of the English with its reason before printing the reading.

| Decision | What stands in the way |
| --- | --- |
| 2KI 3:21#2 | Printed in the verse, the alternative "and above" would need a starting point (above what?), which Brenton doesn't give. Brenton spells A's Greek ἐπάνα in every printing, where Swete has ἐπάνω; the note keeps his spelling. Settle the whole clause. |

### 2.5 Probably keep as a note (14)

Nothing here needs printing: the text already follows A, or the note explains rather than offering other English. Confirm each, then remove its `todo`.

| Decision | Why it can probably stay a note |
| --- | --- |
| GEN 33:18 | The verse already translates A's παρενέβαλε as "took up a position"; "pitched his tent" is another translation of the same word. |
| JDG 9:6 | The Greek εὐρετῆ that A omits has no English words of its own in Brenton's verse, and his "of Sedition" follows A. |
| JDG 21:22 | Brenton says that "according to the occasion" is translated from A. |
| 2SA 11:25 | The verse already prints "strengthen him", following A. |
| 2SA 15:12 | The verse already follows A's reading of the conspiracy. |
| 1KI 1:9 | The verse already follows A: "by the stone of Zoelethi". |
| 1KI 5:14a | Brenton reports a chapter division, which Swete's layout supports. It changes the numbering, not the words, and the edition keeps Brenton's verse numbers. |
| PSA 49:19 | The note reports a gap in the manuscript, not English. |
| PRO 8:5 | Brenton's Appendix discusses the Greek vocabulary with no other English, and Swete reports no variant in A. |
| ISA 7:18 | Brenton says the verse's wording is already A's. |
| ISA 54:10 | Brenton says the verse already adopts A's reading. |
| ISA 61:3 | The note is about how the Greek divides words, with no other English. |
| ISA 66:5 | The verse already says "our", A's reading. |
| ZEC 14:7 | The verse already translates A's ψύχος as "cold"; the note explains it. |
