# New Testament reconciliation

This maintainer guide covers reconciliation, English house style, and worked review cases. General conventions are in [the house-style checklists](house-style.md). The edition's scholarly policy and account of its witnesses belong in [the introduction](../content/introduction.sfm); download provenance and notices belong in [the source catalogue](../sources/README.md). Start changes to the reconciliation at [`byzantine.reconciled`](../src/bible/byzantine/__init__.py) and [`stages.py`](../src/bible/byzantine/stages.py).

## Dependencies

The promote stage receives the sources already loaded into memory and the parsed King James books. Reconciliation stages return records rather than altering their inputs. The resulting `Reconciliation` supplies the promoted books, review, and textual variants; those consumers do not independently decide readings.

| Stage | Result and dependencies |
| --- | --- |
| `stage_greek` | Corrects the Scrivener transcription, reads the printed RP2026 text against the RP2018 electronic text, checks structural decisions, and constructs the unit ledger from the texts, Robinson's collation, and both Greek apparatuses. |
| `stage_english` | Extracts the Cambridge verses and supplied-word spans, reads RV, ASV, and Boyd's ASV, and bridges CrossWire's tagged KJV to the pinned wording and Greek. |
| `stage_reports` | Attaches TCENT and Far Above All reports first; MSB and WEB contrasts inherit evidence from those placements. |
| `stage_instructions` | Binds Pierpont's instructions to English spans, attaches them to units, applies placements, and checks compatibility. |
| `stage_revisions` | Reads RV and Boyd's ASV changes through the bridge and the admitted Greek readings; computes revision alarms. |
| `stage_decisions` | Validates editorial evidence and lemmas, then groups and chooses instructions by construction. |
| `stage_decide` | Assigns dispositions and rejects redundant readings. |
| `stage_edit` | Executes English edits, applies verse omissions and relocations, finishes notes, and determines their witness labels. |
| `stage_verify` | Independently checks the prepared documents and attaches finished-verse diagnostics. |

CrossWire locates and checks English; it does not supply the printed wording. Parsed Greek annotations are usable only where their transcription agrees with the comparison text. Accented text is aligned separately for quotation and decisions that need it. The `additional` instruction-source identifier is reserved in the code; no second instruction source is currently read.

## Units and decisions

`units.py` reconciles token differences with the inventories and adds supplementary units, including declared accent differences that unaccented comparison cannot find. Read a unit by its source reference, Greek sides, and inventory attachments, not merely its ordinal suffix. Source addresses remain in force until assembly.

`edition/byzantine.json` holds readings, structural changes, accent decisions, Hodges–Farstad sides, note lemmas, and Scrivener transcription corrections. `edition/byzantine-placements.json` attaches witness rows the code cannot place itself. The validators reject missing evidence, stale units, and placements the code now makes without help. A Scrivener correction must be supported by both Greek apparatuses at a resulting unit. Structural decisions must account exactly for RP's empty verses and the addresses present in only one text; an exchange must declare both directions.

`decide.py` applies this precedence:

1. An editorial override owns its units.
2. A structural unit is omitted or moved as declared.
3. A compatible instruction supplies a witnessed disposition; conflicting instructions produce `conflict` with no change.
4. An eligible neutral class with neither reports nor attached instruction sources is `neutral`.
5. The remaining units are `silent`, retaining the KJV.

`covered` is an action for a unit whose edit another unit executes, not a separate disposition. Verse-keyed corrections of shared Greek produce additional `shared` rows. Corroboration, manuscript weights, alternative editions, revision alarms, and unplaced English reports contribute diagnostic tags and the controversy score; they do not authorize or prevent execution. Unplaced Greek apparatus rows that assign a Received Text reading are rejected earlier.

## What compatibility establishes

Binding to unique English words and attaching to a Greek unit are separate from compatibility. `instructions.py` checks the operation's shape against the Greek change and supplied-word spans. `rendering.py` then uses CrossWire's lemma associations to detect content words removed despite retained Greek, or added beyond what the target Greek supports. It distinguishes contradicted, verified, and unverified edits. Function words are excluded from the content-word refusal test. The review tags `ev:lexically-supported` and `ev:lexically-unresolved` describe this limited check, not a proof of translation accuracy.

Instructions whose edits share a unit or touch form groups, including instructions spanning verses. A group executes whole or not at all. Rendering refusals are checked again against the combined edits so that a move is not mistaken for a deletion and addition. Groups from different sources form constructions; source selection covers the construction, and an override touching it takes it whole. Two overrides claiming one construction must be merged. See `instructions.constructions`; changing a single unit's selection without this step can splice incompatible wording together.

A shared-Greek correction cites whole words occurring once in printed RP2026. `decisions.shared_greek` rejects an omitted verse, a cut through an aligned word, or Greek touching a difference, including an omission boundary. Its note gives the former English with “Or,” and names no textual witness.

## Execution, notes, and verification

`edit.py` applies fixed-offset edits to USJ and records changes at their punctuation and capitalization seams. At a seam it mends only spacing, deletion punctuation, and supplied-word marking; a grammatical change such as _a_ to _an_ needs a decision. `notes.py` computes lemmas in the finished verse, combines appropriate notes within constructions and validates hand-widened lemmas. Decisions about a note's meaning use `x-scope`, not its rendered prose.

`received.labels` considers every unit covered by a note, including combined notes. It names the Received Text only if every unit has apparatus support for `TR` and none for `SCR`; otherwise the displaced wording is attributed to the KJV. Altering a note's coverage can therefore alter its attribution.

`verify.py` checks one disposition per unit, character-level agreement with the KJV outside declared edits and independently reconstructed seams, note presence and source quotation, and the verse inventory after omissions and relocations. Broken invariants and notes that cannot restore the KJV wording stop the build. Other finished-verse problems are diagnostic flags (`ev:finished-verse`), not an approval queue.

The Greek shown in the review and textual variants retains Scrivener’s and RP2026’s accents and punctuation, with equivalent raised dots and elision marks displayed alike. An apparatus reading is evidence and never replaces the displayed text.

Verse punctuation is revised later in `edition/revisions.json`. In the New Testament, a verse-specific punctuation revision must keep every word; only a word’s initial case at a changed sentence boundary may change.

For a change, inspect the affected book in `build/review/byzantine/` and the edition diff using the commands in [AGENTS.md](../AGENTS.md#checking-a-change). Check the whole construction's before-and-after wording, note scope, and attribution. Review output is derived evidence; edit the decisions or rules that produced it.

## The notes

Every change for a Greek-text difference that changes words carries a note, labelled TR or KJV according to the apparatus evidence above, in the [style of the edition's notes](house-style.md#notes): the words it is about, a colon, and what the Received Text has. `fruit: TR _fruits_` replaces the lemma with the Received Text's words; `said: TR adds _by them of old time_` puts them after it; `verily: TR omits` takes it out, and `but who: TR omits _but_` takes out a part of it, as Brenton's "Vat. omits" quotes only the part of its lemma that is omitted. The short forms are used only where they give back the King James words exactly: an added phrase that is the whole lemma may carry its stop (`tempting him: TR omits` at John 8:4, where the comma goes with the words); otherwise the note quotes the King James words for the lemma. An omission's lemma stays on one side of the gap, so that the Received Text's words go back exactly before or after it: the words after the gap where a stop or a word like "and" stands before it (`cast: TR _raise the dead, cast_` at Matthew 10:8, `unto the rest: TR _and unto the rest_` at Revelation 2:24), the words before it otherwise. A reading's replacement is carried out on the words it changes: words it keeps at either end, or three or more between its changes, stay outside the operations and their notes (`can: TR _might_` and `hath: TR _had_` at Revelation 13:17). A word is kept only with its supplied marking, a supplied span of the King James text changes whole, and a replacement that moves a word stays whole. A construction that changes words in two places takes a note at each, unless their lemmas overlap or a declared lemma spans both (Mark 14:30, where the moved pronoun is put back by one note). A change that only marks a word supplied, or no longer so, has no note: the words are the King James words, and the edition prints supplied words in roman. The lemma is the smallest phrase that names the change and occurs once in the verse, within its paragraph or line, widened to keep a determiner with its noun, and widened by hand in `edition/byzantine.json` where the rule chooses badly.

An omitted verse is quoted whole in a note on the verse before it (`and the other left: KJV adds verse 36 _Two men shall be in the field…_`), and a moved passage is noted at both its places (`TR has this passage at 16:25–27` at Romans 14:24; `TR has here the verses printed at 14:24–26` at Romans 16:24). The Old Testament's passages that the Greek sets in another order than the Hebrew are noted the same way, with the Hebrew's label (`PRO 29:27 Heb.`).

A 1611 marginal note whose reading is the Byzantine reading the text now prints (Matthew 26:26 "Many Greek copies have, gave thanks"; Revelation 13:1 "Or, names"), or which glosses words of the Received Text that the edition no longer has (Matthew 9:36 "Or, were tired and lay down" for "fainted"), is left out, by a decision in `edition/kjv-notes.json` with its reason; the Received Text's words stand in the TR note. The 1611 translators' own remark on Luke 17:36, that the verse is wanting in most Greek copies, stands at 17:35 beside the note that quotes the verse.

Every applied correction of shared Greek carries an “or,” note quoting the former King James wording from the pinned source, made by the same machinery as the TR notes and in the same stage: the lemma is chosen as a TR note's is, and the former words always stand for it whole, since another rendering has no short form. Each correction names its own Greek, so two corrections in one verse keep separate notes unless their lemmas overlap. These rendering notes carry no TR label, since the Greek is unchanged. Where a reversed 1611 margin (below) says the same, it stands for the edition's note, which is left out; a former-reading decision in a verse with such notes that covers none of them stops the build.

Where a correction of the English adopts a 1611 marginal alternative, the declared notes instead reverse the comparison editorially: the current words are the lemma, followed by roman “or,” and the former King James wording in italics (`going out: or, _gone out_` at Matthew 25:8). Each `former` quotation in `edition/kjv-notes.json` must occur exactly once in the original verse, its `anchor` must bind uniquely to the corrected verse, and the margin's alternative, its words after the label up to any citation, must stand within the anchor. Acts 27:40 fails that test, since its margin has “cut the anchors” where the correction prints “cast off”, so its note is omitted and the correction's own note gives the former words. The review identifies the editorial reversal and retains the source note's key and original body. The replacement puts “or,” and the displaced English in place of the margin's label and alternative, and keeps the citations after them (`for him: or, _in him_, Rom. 11:36` at 1 Corinthians 8:6). Hebrews 2:1 retains its distinct Greek gloss on “drift away”; older omissions and TR notes keep their own decisions.

## What counts as a translatable difference

Several scholars have decided which Greek differences can be seen in English, each by a stated standard. The edition keeps the King James Version's literalness: a difference is translatable when ordinary King James English shows it, in meaning, reference, number, tense, mood, voice, emphasis, or grammatical relation, even if the sense of the passage is unchanged. An article, particle, inflection, or word order does not by itself need its own English; a revised passage is no more literal than its neighbours.

**Pierpont** notes "only those places where the change is translatable, or potentially translatable", in the King James words, and excludes words the translators supplied with no basis in any text, places where the King James Version already agrees with the Majority against the Received Text (he lists thirty), and mere improvements of rendering. He gives each change a weight by manuscript support; the weight is a tag, not a standard of translatability. **Boyd**'s TCENT notes only what shows in an "optimal equivalence" translation and ignores "minor differences involving word order, phrasing, conjunctions, articles, prepositions, and the like", so his list is a lower bound: a difference he notes shows in English, though the King James wording may already carry it. **Thomason**'s _Far Above All_ is hyper-literal and marks a contrast wherever his English can carry one, so his list is close to an upper bound. The **MSB** and **WEB** footnotes are selections: a note is evidence, silence is not. From the loosest to the strictest about what must be reported: Boyd, then the WEB and MSB, then Pierpont, then Thomason.

| Who reports | Meaning | Disposition |
| --- | --- | --- |
| Pierpont, bound and compatible | Proposed King James wording, subject to the house style | witnessed |
| Boyd’s TCENT, and no King James-worded instruction | Shows in English; the King James wording may already carry it | silent, `ev:tcent-reports`: a priority for review, normally a reading |
| Only Thomason, the MSB, or the WEB | Possibly below the King James Version's resolution | silent, `ev:hyper-literal-only` |
| Nobody | No witness reports an English contrast | silent or neutral |

Classes eligible for a neutral disposition when witnesses and attached instruction sources are silent include movable ν and ς; word division and crasis; accents, breathings, and punctuation except where they change the word (Philippians 3:5, 1 Corinthians 5:13, Luke 3:23); spellings of common names (Δαυίδ/Δαβίδ, Μωσῆς/Μωϋσῆς); variant forms of one inflection (εἶπον/εἶπαν). Two that look like spelling and are not: a changed verbal prefix (Acts 3:24), and a transliterated word inside a quotation (Matthew 27:46 λαμά/λιμά).

The Revised Version of 1881 and Boyd's ASV of 2021 are full revisions, never compared with the King James Version to find readings: of some 6,400 verses with no Greek difference, only about 720 are word-identical between the King James Version and Boyd's ASV. A revision's change is read only where the CrossWire bridge places it on the words of one unit, or where it makes the same contrast as a placed instruction; it corroborates an edit, raises the alarm when both revisions lack the King James words of an unreported unit, and supplies wording in King James diction when a reading needs it. Boyd's method for his revision is the model: "every effort has been made to stay within the style and vocabulary of the ASV. When available, alternate renderings in the ASV footnotes were used. Otherwise, modifications to the text were most often derived from the King James Version itself."

Scrivener and Stephanus can differ: do not infer a TR attribution from King James wording alone. The apparatus checks above establish the label for every unit covered by a note. RP's marginal alternates, Hodges–Farstad, and the Patriarchal text inform the review; RP2026's main text remains the target. Current counts belong in the generated review.

## The English house style

**Least disturbance, not fewest words.** A changed case, referent, or clause relation may take its whole phrase with it; dependent words, agreement, and punctuation move only where the change breaks them. A hard reading stays hard, and an ambiguous one ambiguous: do not explain it away, harmonize it with a parallel, or mend it, but put its construction in grammatical King James English.

**Wording.** Start from the selected instruction, where one exists. If none executes or its wording fails the house style, decide with, in order, a King James parallel that fits the sense and grammar here, the words of Pierpont, the Revised Version, or Boyd's ASV in King James diction, with Boyd's TCENT and Thomason's Far Above All occasionally consulted in that order, and only then the editor's own; the reading's `from:` tag says which.

**Diction.** Work in King James diction before the systematic revision stage applies the edition's spelling and grammar conventions: _thou_, _thee_, _thy_, _thine_, nominative _ye_, _-eth_, and _-est_. Choose a word for its meaning, not its age; it need not occur elsewhere in the King James Version. Do not modernize, and do not force one English word on a Greek lemma.

**Verbs.** A changed tense, mood, or voice is rendered as the King James Version renders it in context, not by formula. Judge like constructions together: conditionals, negation, dependent clauses.

**Reference.** A changed name, pronoun, or possessive is rendered where it shows at the King James Version's level. Do not put a name for a pronoun to clarify it, or explain in a parenthesis.

**Order.** Carry changed coordination, attachment, and emphasis where English syntax allows. Move existing phrases rather than rewrite them; do not copy Greek order into unnatural English.

**Capitals and supplied words.** The King James capitals stay unless a changed expression or sentence boundary needs another; no new reverential capitals. (The revise stage then sets emphatic capitals, such as JESUS and the inscriptions, in ordinary case, as [the house style](house-style.md#typography) describes.) A King James supplied word for which RP2026 now has Greek is no longer marked supplied; necessary supplied English is marked, judged by the Greek construction and King James usage; supplied words that served only an omitted construction go with it. (The edition prints supplied words in ordinary type, so the marking shows only in the sources sent to be typeset.)

## Lines of verse

The text keeps Scrivener's paragraphs, and the lines he gave the Beatitudes, the canticles of Luke 1–2, the tribes sealed in Revelation 7, and the fall of Babylon in Revelation 18.

## The cases

These examples describe reconciliation before systematic spelling and punctuation revision. Consult the current decisions and review when checking a particular reading.

The verses that test the executor's seam rules and the trust model, with what the edition does at each. The reading probes in `tests/test_byzantine_cases.py` hold the edition to them.

**Greek differs, English stands.** Matthew 1:1 Δαβίδ/Δαυίδ, a proper-name spelling; John 18:32 ἤμελλεν/ἔμελλεν, a verb spelling; Matthew 5:23 κἀκεῖ/καὶ ἐκεῖ, word division; Acts 19:29 and Mark 11:22, an article with a proper name; Mark 7:24 "a house" and Revelation 9:20, an article with a common noun; Matthew 18:4, a subjunctive for a future the King James "shall humble" already carries; Matthew 12:21, a preposition omitted in Greek that English still requires.

**Omissions.** Matthew 3:11 "and _with_ fire" goes with its supplied word; 5:27 "by them of old time"; 10:8 "raise the dead," with its comma; 27:35, where the colon before the omitted fulfilment quotation becomes a full stop; Luke 3:19 "his brother Philip's wife" becomes "his brother's wife"; 9:1 "his twelve disciples" becomes "the twelve"; John 18:11 "thy sword" becomes "the sword"; Acts 9:5–6, one construction across two verses; 12:23 "God the glory" becomes "glory to God" after the article goes; 20:21 "Christ" goes with no space before the stop; 2 Corinthians 11:31 "of our Lord" becomes "of the Lord"; 1 John 5:7–8, where two verses become one sentence and the punctuation is part of the decision; Revelation 1:8, two units, a clause removed and "God" added; 6:3 "and see", here only.

**Additions and substitutions.** Matthew 4:10 "Get thee hence, Satan" becomes "Get thee behind me, Satan", as the King James Version renders the same Greek at Luke 4:8; 18:19 "Again, verily I say"; 26:26 "blessed _it_" becomes "gave thanks"; 27:41 "and Pharisees"; Luke 6:9 "to destroy _it_" becomes "to kill"; 8:31 "they besought" becomes "he besought"; Acts 3:24 "foretold of" becomes "announced"; Acts 8:16 and 2 Timothy 2:19, where the article changes with the title; 1 Peter 3:1 "may … be won" becomes "shall … be won"; Ephesians 4:6, 1 Thessalonians 4:8, and 2 Corinthians 1:11, where first and second person plural swap; Revelation 20:2, a relative clause that closes before the main clause resumes; 22:21 "our Lord" becomes "the Lord" and "you all" becomes "all the saints".

**Several units in one verse.** 1 Peter 5:10 "us" becomes "you" and three of four verbs change from optative to future; Revelation 13:5 "blasphemies" becomes "blasphemy" and "war" is added; Luke 22:30 omits "in my kingdom" and makes "sit" future; Revelation 9:10, one recast predicate covering several units; 11:10 "shall rejoice" becomes "rejoice", "make merry" gains its own "shall", "send" becomes "give"; 5:14 omits "four and twenty" and "him that liveth for ever and ever".

**Reorderings, transliterations, quotations.** Luke 8:51, Matthew 21:14, and Revelation 1:18, one reordered phrase each, applied as one transposition; Revelation 22:8, a phrase replacement that carries the reordering and removes the supplied object; Philippians 2:21, a unit (an article) at which the names stand in the same order in both texts, so a directive must attach to its own unit; Matthew 27:46 λαμά/λιμά and Mark 15:34, a spelling difference inside a transliterated quotation that does change the English; Matthew 21:1 and Mark 11:1 "Bethphage" becomes "Bethsphage"; John 1:28 "Bethabara" becomes "Bethany"; Romans 16:3 "Priscilla" becomes "Prisca".

**Construction judgments.** Acts 18:17 keeps "cared" by a `nochange` ruling; Matthew 12:6 keeps "one greater" for the neuter comparative; Revelation 21:16's added second "twelve" takes supplied "each" and "thousand furlongs" to carry the elliptical measurement, and its note restores the King James comparison whole.

**Machine output to recognise.** If the executor ever emits anything of this shape, its construction needs a wider decision: "and given thanks" (an auxiliary left out), "a borders" (an article moved without its noun), "shall suffer not suffer", "All. the saints" (punctuation kept inside a replaced phrase), "Thy sins be forgiven Your" (a donor's pronoun in a King James sentence).
