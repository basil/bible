# Working on this repository

This is a hobby project that prepares a printed Bible from pinned sources. Keep it small and understandable: prefer deleting to adding, and a plain function to a new abstraction.

## Building

You need Docker with the Compose plugin, Make, and about 5 GB of disk space. Everything runs in a container, so you don't need Python, TeX, or Poppler on your machine.

```sh
make bootstrap  # build the container image (needs the network)
make pdf        # fill pages, check, and build dist/bible.pdf
```

Run `make bootstrap` first, and again when the build says the image is stale. The build and test targets run with networking turned off and read the texts from the archives committed in `sources/`.

The edition's text family is OLEBFont, which the image build assembles once (`scripts/build_olebfont.py`): from Valkyrie OT where the host has its four faces, with GFS Heraklit for Greek, and otherwise from Utopia, with GFS Didot. Valkyrie is proprietary and never committed; `make bootstrap` finds its faces through fontconfig and copies them into the image's build context, and the image installs OLEBFont and the Greek face paired with it under `/usr/local/share/fonts`. With Valkyrie the image also installs newpx’s unchanged regular TeX Gyre PagellaX face for the large chapter-opening numeral only; Utopia keeps its own chapter numerals. Python selects the chapter face from the installed Greek family's pairing, for print only. PTXprint's settings name OLEBFont, and generated styles name the installed Greek and chapter faces. CI installs Valkyrie on `master` alone, from repository secrets, so the published PDF and site are set in it while a pull request's build is set in Utopia.

```sh
make sample    # a short PDF of selected chapters, for checking layout quickly
make pdf-unfilled # a full unfilled proof at dist/bible-unfilled.pdf
make validate  # prepare the whole edition, checking every source and decision, without typesetting it
make web       # write prepared scripture as USJ JSON in build/web/
make site      # export scripture and build the VitePress website (Node >= 22)
make site-dev  # serve the site locally after make web and npm --prefix site ci
make clean     # delete build/ and dist/
```

`make pdf` runs PTXprint's page filler with four workers before typesetting
the complete book. A cold run can take an hour or more; a matching cache
avoids repeating the searches, but final typesetting and checks still run.
`FILL_ARGS="--jobs 2"` changes concurrency.

Adjustments and saved probes live in `build/page-fill-cache/`, keyed by each
book's generated USFM, shared layout, fonts, and pinned tools. Matching books
are reused automatically; only completed books are cached, and interrupted
or failed books start fresh next time. A change confined to Revelation refills
Revelation, while a margin or font change refills every book. Corrupt entries
are recomputed.
`make pdf FILL_ARGS=--fresh` discards the cache, and `make clean` removes it.

The runner refuses concurrent filled builds, caches each completed book,
and reports progress every minute, including completed, reused, and pending
books. Its rough remaining-time estimate starts once enough books have
finished; it covers filling alone, not final typesetting. Logs and the
machine-readable report are in `build/page-fill/`; complete typesetting and
verification output is in `build/pdf/`. A failed or interrupted build
preserves valid checkpoints and the last checked `dist/bible.pdf`. Any
unresolved filler pages, failed convergence or failed publication checks
stop publication.

The filler checks its final page measurements rather than retaining every
page it failed on earlier in its search. A short page is permitted when the
next page opens with a heading: TeX breaks before a heading only when it and
the lines it keeps cannot follow the page's last line, and the filler cannot
reflow a heading. These protected breaks are recorded by book in the cache
and report; a gap before a verse paragraph, or inside one, still fails.

The baseline grid keeps lines registered front and back on thin paper; it
does not require every row to contain text. Paragraph protection can leave
a row empty. Filling changes paragraph wrapping to improve page breaks
while retaining the baseline spacing. Samples and `make pdf-unfilled` skip
filling. CI fills master builds and caches their checkpoints; pull requests
build unfilled proofs in Utopia rather than the published Valkyrie face.

The sample prints the chapters listed in `edition/sample.json`, which were picked to cover the awkward cases: Psalm 151, the additions to Esther and Daniel, the join between 2 Esdras and Nehemias, the end of Malachias, the verses of 3 Kingdoms 5–7 and 12 supplied, omitted, or reordered after Codex Alexandrinus, the displaced passages of Proverbs 24 under the Hebrew's numbers, Sirach's Prologue and the Epistle of Jeremias's unnumbered title, quoted Greek and Hebrew, the verses the Byzantine text lacks or moves (Luke 17, Acts 24, Romans 14, Matthew 23, 1 John 5), Revelation 13 with its many readings, the four Gospel endings with their publication colophons, and pages crowded with notes.

Logs and intermediate files go to `build/`, which is regenerated on every run except for the page filler's cache.

The `web` command writes the prepared scripture as USJ JSON, one file per chapter, each with its book, a separate file for Sirach’s Prologue as a book introduction, and an ordered chapter manifest with each book's names and each chapter's label, marking the chapters whose heading stands for their number; the front matter the book prints and the website-only tables of chapters and verses, one file per unit in `build/web/matter/`, each with its book and its printed title, without the names the manifest lists it under, in its order, all before the testaments (the divider pages are left out), and the back matter and the colophon after them, listed apart; the passages of the comparison page, quoted from the edition and from the King James verses the place stage pairs with them, with their highlights, the textual variants, with their opening prose and their entries by book, each the verse it is about, with the King James Bible's number where it differs, and its lanes: the Greek of both texts and, where the English changes, the words of both Bibles, each lane the words the two witnesses share and, where they differ, both readings, and the fonts as complete WOFF files in `build/web/fonts/`, with the stylesheet that declares them: the four OLEBFont faces, the Greek face installed beside them, and Ezra SIL, in which the Greek and Hebrew are set as in print, tagged in the exported chapters as the typesetter has them. The website in `site/` is its only consumer; it renders one static page per chapter, the Prologue at `/read/sir/prologue`, one per unit of front or back matter (the colophon under the title the manifest carries, since it prints none), and one per book's variants. Run `make web` before developing or building the site directly with npm; `make site` does this automatically. Node runs on the host, while preparing the scripture and fonts still runs in the container. If the image is stale or its fonts are missing, run `make bootstrap` again.

For the website, `npm --prefix site run lint` checks JavaScript, TypeScript, and Vue with ESLint, formatting with Prettier, and types with vue-tsc. `npm --prefix site run lint:fix` applies automatic fixes and checks types. The website checks run separately from `make lint` and `make lint-fix`; they need Node and `npm --prefix site ci` first. Generated files are excluded from formatting. `npm --prefix site test` runs isolated unit tests without generated scripture or a site build; `npm --prefix site run test:watch` watches them. `npm --prefix site run test:integration` checks the exported corpus and built site; run `make web` and `npm --prefix site run build` first. `npm --prefix site run dev` serves with hot reload; `preview` serves the last static build.

## How the edition is prepared

Every departure from the sources is a decision recorded in `edition/*.json`, and the build carries those decisions out in a fixed sequence of stages:

1. **Read:** the pinned archives are parsed, with the slips in their transcription corrected. The footnotes eBible's Brenton lacks are supplied from CCEL's transcription of Brenton (`src/bible/ccel.py`): each page's words are read with the note callers among them, each run of a chapter is found among eBible's chapters by its words (of the chapters that share its rarer words, the one its words align with best; two that align alike and would set the notes differently stop the build), and each note is set in eBible's verse before the word its caller stands before, or at the end of the verse its caller closes, unless the verse has the same note at the same caller word, differing at most in punctuation, capitals, or the form of its citations, or an explicit duplicate decision accounts for it; what cannot be read or placed is left out and listed in the review, and a note that mentions Codex Alexandrinus or the Appendix is held back until `edition/alexandrinus.json` decides it. Of the King James Bible only the books the edition prints, borrows from, or places its verses in are parsed. The New Testament's Greek texts and witnesses are read from their archives and files into memory, the two PDFs among them by Poppler. The four Gospel publication colophons are read from Boyd’s TCENT notes selected in `edition/prose.json`, without copying their wording into decisions. Nothing is read after this.
2. **Promote:** the readings from Codex Alexandrinus are put into Brenton's text, and the readings of the Byzantine text into the King James text: the Greek texts are compared unit by unit, the witnesses attached, the decisions validated against them, every unit given its disposition, the edits and the structural changes carried out, and the Textus Receptus notes set (`src/bible/byzantine/`). In both, the chosen text goes into the verse and the displaced reading becomes a note that names its witness; the editor's corrections of the English where the Greek texts agree are carried out with an "Or," note giving the former King James words, which names no witness unless a note witness decision cites one. A CCEL note on words the Alexandrine readings supply is set once they are in the verse. A note names the Received Text (TR) only where Boyd's apparatus or the printed RP2026's gives its words as TR, Scrivener and Stephanus agreeing, and neither as Scrivener's alone; otherwise it names the printed edition the King James translators followed there, Beza, Erasmus, or another, where `editions` in `edition/byzantine.json` shows it from that edition or Scrivener's account of their sources, and failing that the King James Version (KJV) (`src/bible/byzantine/received.py`). A note that would name the KJV or no witness may instead cite a version for the former English words, where `note_witnesses` in `edition/byzantine.json` lists it and the note quotes the version's reading: the seven notes on Beelzebul cite the Vulgate's Beelzebub. A Received Text or `editions` label is never replaced. The reconciliation's own stages are in `src/bible/byzantine/stages.py`, each a function of the results of the stages before it, gathered as the `Reconciliation` that the promotion, the review, and the textual variants read.
3. **Assemble:** the edition's books are made from the sources' chapters, under the edition's names: Nehemias from the file that holds Esdras, Daniel with Susanna and Bel and the Dragon, and without the empty chapter eBible left in Proverbs. Their verses are then numbered as the Septuagint numbers them where eBible numbers them otherwise, relabelled, and divided again by `edition/versification.json` (implementation: [docs/numbering.md](docs/numbering.md)), and a verse that prints another label than its own, or none, is given it: Proverbs' passages in the Hebrew's order under the Hebrew's numbers, and the Epistle of Jeremias's superscription unnumbered. Sirach's Prologue becomes the book's introduction, without chapter or verse markers. Everything before this stage, note keys included, names eBible's verses; everything after it names the edition's. What the edition prints is read from the assembled books.
4. **Place:** each verse is matched to its place in the King James Bible: the Old Testament's from the table and the words, the New Testament's from the verses the Byzantine text lacks or places elsewhere. The notes, the links, and the table of chapters and verses read it.
5. **Line:** the poetry is set in lines after the Updated Brenton (`src/bible/lines.py`): each of its chapters is aligned word by word with Brenton's, and its lines and stanza breaks are placed in Brenton's words, in the verses Scrivener's King James Bible sets as verse too or has no counterpart of, and throughout the Apocrypha, where the Updated Brenton's lines stand alone; the breaks the words cannot place are in `edition/lines.json`. A line that goes on with a verse is indented. A prose paragraph that opens with a small-capital title ending in a period has the title set apart as a descriptive title (`\d`). The New Testament keeps Scrivener's paragraphs, the extent of his poetry, his stanza breaks, and his lines, except where `new_testament` decisions in `edition/lines.json` divide a verse's lines and set their indentation otherwise, using the Berean Standard Bible as a model adapted to the King James wording. They change no words, notes, or verse numbers. The Psalter's kathismata and stases are then marked from `edition/psalter.json`.
6. **Matter:** the translations' front and back matter is brought into the edition's style, citing and abbreviating as the edition does; the four Gospel colophons read from Boyd are appended as terminal subscriptions, apart from Scripture like the fourteen epistle subscriptions retained from the KJV; Brenton's Appendix is read for its notes and printed nowhere.
7. **Annotate:** Brenton's notes, the 1611 margin, and the edition's own notes are set as footnotes on the words they are about, with the quotation links and the notes of Brenton's Appendix. A note whose words are declared stands before the first of them, wherever its source’s caller stood: a lemma override moves its note there, and the edition’s notes, and a note whose verse a reading from Codex Alexandrinus changes, with the words it was about before the change, are set there. A note whose words are inferred from its caller in the verse as it stands, and a note about no words, keep the caller’s place.
8. **Revise:** spelling and punctuation are revised, and the small capitals of selective emphasis go, keeping only those that open a unit.
9. **Authored:** the edition's own pages are filled in with the passages and tables they ask for, among them the back matter that follows Revelation (the Biblical Odes and the Order of Reading the Psalter, listed under `back` in `edition/manifest.json`) and the colophon that closes the book (`content/colophon.sfm`, a constant of `src/bible/policy.py`), and the tables of chapters and verses and the textual variants, which the website publishes and the book does not print; they quote both Bibles with the edition's systematic spelling and punctuation, before the verse-specific revisions, so that they show the readings' differences alone.
10. **View:** the whole edition or the sample is selected, and typographic quotes are applied.
11. **Export:** USFM is written for PTXprint, with the few things only it needs, among them the notes `edition/margin.json` sets below the text to relieve a page, and PTXprint typesets it.

The stages are in `src/bible/pipeline.py`, which is the place to start reading the code; the last of them, the export of USFM for PTXprint, is `src/bible/export.py`.

## Principles

- **Separate the concerns, and change nothing in place.** The build is the fixed sequence of stages above. Each stage is a function of the stages before it and of the policy: the decisions, loaded once as the `Policy` in `src/bible/policy.py` and frozen. A stage builds what it changes and shares the rest. It never alters a document, the policy, or a source it was given; a stage that adds to the policy returns a new one.
- **Make transformations simple to write, read, and trust across the whole corpus.** A rule applies everywhere, and what departs from it is a decision in `edition/*.json`, with its reason. A decision that no longer fits its source, changes nothing, or matches nothing stops the build and names itself, so the files can't go stale: fix or remove it. Refuse what a transformation does not understand rather than guess at it.
- **The build decides; it does not wait.** Every Greek difference of the New Testament gets one disposition on every build, from the sources, the code, and the decisions, and nothing else: no approval, sign-off, or review status gates what executes. A text that is wrong is fixed by changing a decision or a rule, then rebuilding. An instruction is judged and carried out by construction, never in parts, so that a finished sentence is always one source's wording or the editor's, never a splice. The target is RP2026's main text; other editions are evidence about readings, never the target.
- **Decide on meaning, not on rendered output.** Work on the USJ document and on the words of a verse, not on serialized USFM, exported text, or the PDF. A regular expression over markup is a sign that the decision is in the wrong place.
- **Marshal at the boundaries.** USFM is parsed once, when the sources are read, and written once, for PTXprint. Between those two ends everything is [USJ](https://docs.usfm.bible/usfm/latest/usj/), the JSON form of USFM, extended only by `x-key` and `x-scope`. Do not add a second document model or a new extension without need. The few places that still meet USFM text between the ends are listed under [the document model](#the-document-model); do not add to them.
- **Run transformations in the order of their dependencies.** A new transformation goes in the stage where everything it reads is ready, and nothing reaches back to an earlier stage's work. Revision finishes the translations after source-dependent decisions, so those decisions are still written in the sources' own words. Authored pages then consume the revised text and receive their own punctuation finishing pass, retaining the source names they discuss.
- **Use semantic markup, not hard-coded strings.** Build USJ nodes rather than backslash markers in strings. Take terms and abbreviations from `edition/terminology.json`, and books and their names from `edition/manifest.json` and `edition/citations.json`.
- **Keep checked-in data normalized.** State each fact once. Do not check in what the build can derive, and do not copy a source's words into a decision unless the build verifies the copy against the source, so that it cannot drift unnoticed. Keys are the short source keys (`GEN 1:9#2`), not hashes or positions.
- **Revise spelling and punctuation in one place.** That place is `edition/revisions.json`. Do not respell the sources, the other decision files, or the code. A King James name spelled after another language against the Greek's letters, as the Latin Beelzebub for Βεελζεβούλ, is no respelling but a rendering, corrected with the New Testament's Greek (`edition/byzantine.json`) and not in `names`. A proper name is respelled by its bearer, in the verses, subscriptions, and units of front matter its decision lists and nowhere else; the verses that keep the source form are listed too, with who keeps it, and the build refuses an occurrence listed neither way, in a verse or in the front matter. A note's commentary keeps the source's names. Two bearers may share a source spelling, each in its own verses, and where one verse names two bearers alike each lists its occurrence by number (`LUK 6:16#1`).
- **Leave the sources and the build output alone.** Do not edit the files in `sources/` or anything in `build/`. A change to the English needs its own decision, with evidence, exact scope, and a before-and-after comparison in the review diff. A formatting rule must not change the English, or the witness a reading is attributed to.

## The document model

Every document between the sources and PTXprint is USJ: plain objects, lists, and strings, read and written by `src/bible/usj.py` and checked in the tests against usfmtc, the USFM committee's own parser. The build adds two things to it and no more:

- A note carries `x-key`, the address of the source note it was made from: `GEN 1:9#2` is the second note of Genesis 1:9 as the source numbers it, `MAT 6:1 of` is the 1611 note on "of" at Matthew 6:1, and `LEV 4:2 CCEL` (`LEV 4:2 CCEL#2` for the verse's second) is a note of CCEL's transcription set in Leviticus 4:2, numbered by its place among the successfully placed CCEL notes of that verse, before duplicate and omission decisions. The keys are stable while the source archive is, and the archive is pinned by its hash.
- A note that the edition writes carries `x-scope`, the words it is about, and the standard `category` of `edition`: the notes that a decision about Codex Alexandrinus writes or moves; the Textus Receptus notes, keyed by the Greek unit they are about (`MAT 3:8#1 TR`, and `MAT 3:8#1 TR#2` for a unit's second note) or, for a verse omitted or moved, by the verse they stand at (`LUK 17:35 TR`, `ROM 14:24 TR`), where `TR` names the kind of note, a note on the Received Text's reading, and not its printed label, which `received.labels` decides from the apparatus and the `editions` in `edition/byzantine.json` (`LUK 17:35 TR` prints Beza); the "Or," notes on the corrections of the English where the Greek is shared, keyed by their verse (`LUK 23:42 rendering`); and the note that says where the Hebrew has the passages the Greek sets elsewhere, keyed by the verse it stands at and the Hebrew's label (`PRO 29:27 Heb.`), in the same form as the New Testament's notes on moved verses. The notes of Brenton's Appendix, set at the foot of the page at the verses they discuss, carry `x-key` in the same form, as `2SA 5:18 Appendix`. While the promote stage finishes a Textus Receptus note, its `x-scope` also says what the note says the Received Text has (its `kind`: other words, words added or omitted, a verse added, a passage elsewhere) and the verse or passage it names; every step decides on that, never on the note's words, and the note as printed declares only its lemma.

A stage decides on a document's words, not on its markup. `usj.py` and `scripture.py` read the words of a verse or a paragraph as one string, whatever notes and styles stand among them, and make a change at its offsets: `replaced` and `inserted` set content in place of words, and `substituted` rewrites words in the styles they stand in.

USFM as text is read at the two ends: `repairs.py` corrects a source's transcription before it is parsed, the read stage takes the King James Bible's names and chapters for the table of chapters and verses from the files it does not parse, and `verify.py` reads what PTXprint wrote (`usfm.py` holds the helpers all three use). Two things between them still meet it, and nothing else should. The editor's own pages are parsed once the passages and tables they ask for have been filled in (`numbering.page`). And a decision that gives words with their markup is written in USFM and parsed where it is carried out: the `from`, `note`, `appendix`, `to`, `source_note`, and `source_notes` of a decision about Codex Alexandrinus, for which a source's note is written out to be compared with it (`notes.source_text`).

## Decisions

Each decision gives its reason, usually as `why`. The shape of each file is declared in `src/bible/policy_schema.py`, and the existing entries are the best examples of each kind.

A decision about a note is keyed by the note's `x-key`. A decision about front or back matter is keyed by its unit and the words it concerns, as `XXB There is`. A decision about a Greek difference of the New Testament is keyed by its unit: the verse and the Received Text's and Byzantine text's words there, as `MAT 5:39#1`; a placement by the witness and its row, as `faa 1PE 5:10#2`.

A correction to a slip in transcription must match the source text exactly once, and in the scripture itself it may mend only word spacing or restore a whole note Brenton printed that the transcription lacks, so that the wording stays eBible's. It must also fit one of the kinds of slip that `src/bible/repairs.py` defines (a missing word space, a stray letter, a bracketed remark, a dropped note, and so on), or be marked `"uncategorized": true`, so that no correction can rewrite the translation unnoticed. A note a correction restores may be one of the 1844 printing that the later Bagster printings, and so eBible, dropped, and a correction within a note may recover information they shortened, retaining genuine corrections in later printings. Its `why` names the printing and page that has the information and the pages of the later printings that lack it, and explains any disagreement checked against the printed sources and Swete's images.

### Where a change goes

| To change | Edit |
| --- | --- |
| Which books and units of front and back matter are printed, their order, names, and headings, and whether their chapters are labelled | `edition/manifest.json` |
| The Biblical Odes, the Order of Reading the Psalter, and the colophon | `content/odes.sfm`, `content/psalter.sfm`, `content/colophon.sfm` |
| A slip in a source's transcription, or a note of Brenton's 1844 printing that the later printings dropped or shortened | `corrections` in `edition/brenton-notes.json` or `edition/kjv-notes.json` |
| The words a note is about, its quotations and alternative renderings, or whether it is a sentence | `notes` in the same files |
| A reading from Codex Alexandrinus, a supplied passage, a verse omitted or moved after it, a kept note, or an Appendix entry moved into the note on its verse | `edition/alexandrinus.json` |
| A Byzantine reading the build does not decide, a ruling that a difference is not applied, a verse omitted or moved, a difference of accent alone, Hodges–Farstad's side where no apparatus gives it, or the lemma of a TR note | `edition/byzantine.json` |
| A correction of the King James English where TR and RP2026 share the Greek | `readings` in `edition/byzantine.json`, keyed by the verse |
| The printed edition a TR note names (Beza, Erasmus, Stephanus 1549, the Complutensian or Aldine text) where the apparatuses establish no Received Text | `editions` in `edition/byzantine.json`, keyed by the note |
| A version (the Vulgate) a note cites for the former English words, where it would otherwise name the KJV or no witness | `note_witnesses` in `edition/byzantine.json`, listing the notes |
| A note set below the text to relieve a page whose margin overruns | `edition/margin.json`, keyed by the note, with its reason |
| Which Greek unit a witness's row is about, including a row of Boyd's Greek apparatus or of the printed RP2026's that the code cannot place | `edition/byzantine-placements.json` |
| A slip in an electronic transcription of Scrivener's Greek, where both apparatuses give his words | `scrivener` in `edition/byzantine.json` |
| A 1611 note left out, or set on other words, because the text changed | `notes` in `edition/kjv-notes.json` |
| A slip in CCEL's transcription of a note, or a CCEL note accounted for by a named eBible note, left out, or placed in a verse the words do not place it in | `corrections` and `notes` in `edition/ccel-notes.json`, keyed by page and note number (`14.iii#7`) |
| A CCEL note that mentions Codex Alexandrinus or the Appendix, held back until decided | `edition/alexandrinus.json`, under the note's key (`LEV 4:2 CCEL`) |
| How a citation is read or printed | `edition/citations.json` |
| The wording of a note or of front matter, how front matter's paragraphs are marked, or a sourced Gospel colophon (`sourced_colophons`) | `edition/prose.json` |
| An abbreviation, or the list of abbreviations | `edition/terminology.json`, `edition/abbreviations.json` |
| Where a note of Brenton's Appendix stands, and the words its caller stands before | `edition/appendix.json` |
| A quotation link, or Turpie's judgment of it | `edition/quotations.json`, `edition/turpie.json` |
| How a chapter or verse is numbered where eBible numbers it otherwise than the Septuagint (`relabel`, `breaks`), with the editorial account in [the introduction](content/introduction.sfm) and the mechanics in [docs/numbering.md](docs/numbering.md), and a verse that prints no number (`unnumbered`) | `edition/versification.json` |
| Where a verse stands in the King James Bible, an empty chapter of a transcription, or a note saying where a passage stands | `edition/versification.json` |
| The spelling of a word, a misprint in the printed English (a missing word, or two words printed for one, among them), an explicitly scoped correction of an Old Testament English construction, or the punctuation of a verse, a note, or a paragraph of front or back matter | `edition/revisions.json` |
| The spelling of a proper name, by its bearer: the verses, subscriptions, and units of front matter that respell it and the verses that keep the source form, an occurrence by its number where a verse names two bearers alike | `names` in `edition/revisions.json` |
| The Psalter's kathismata and stasis divisions, and a title of Brenton's that stays a verse | `edition/psalter.json` |
| A passage the website compares with the King James Bible, and the phrases it highlights | `edition/comparisons.json` |
| Where an Old Testament line of verse begins when alignment cannot place it, or the New Testament poetry's line divisions and indentation | `edition/lines.json` |
| The acknowledgments, the scholarly introduction, the list of abbreviations, the numbering table, the divider pages, and the textual variants; numbering and variants are website-only | `content/` |
| Page layout, styles, and TeX | `config/` |
| How OLEBFont is assembled from Valkyrie or Utopia, and which Greek face goes with each | `scripts/build_olebfont.py` |
| The website | `site/` |

A page in `content/` names a passage between braces, by its code, and the build prints it. A page also says, on a line of its own, where a table the build writes goes: `numbering.sfm` the tables of chapters and verses, `introduction.sfm` the book names and the glosses of the quotation links, and `abbreviations.sfm` the list of abbreviations.

### Where things are

The rest of the repository:

- `sources/`: the Bible texts, the Updated Brenton (read for its lines of verse and the prose markers at their end), CCEL's Brenton (read for its notes alone), the 1611 marginal notes, the Greek New Testament in both its texts with its collations and apparatus, the English witnesses to its differences, and the fonts, committed as downloaded. [sources/README.md](sources/README.md) says where each came from.
- `src/bible/`: the Python package that prepares the edition; `src/bible/byzantine/` is the reconciliation of the New Testament with the Byzantine text, run by the promote stage.
- `tests/`: the tests.
- `scripts/`: the font assembly and the PTXprint patches, run when the image is built.
- `Dockerfile`: the tool image, with the pinned versions of PTXprint and the fonts.

## Checking a change

The book should come out the same except where the change means it to differ.

```sh
make lint         # formatting and types
make test         # the whole suite
make review-diff BASE=HEAD  # every line of the edition that the working tree changes
make sample       # the selected chapters, typeset
```

`make test` runs the Python suite with two workers, keeping each module together so its fixtures are reused, alongside the TeX suite. To run some Python tests serially, use `make test-python PYTEST_ARGS="-n 0 -k marginal"`.

`make review-diff` compares the edition as the working tree prepares it with the edition at `BASE`, by default `origin/master`, and writes every line that differs to `build/review.diff`. Read the diff after any change to a rule or a decision: an unintended effect shows there as an extra line. Explain every intended difference when you report the work.

`make review` writes the full review to `build/review/`, for reading through:

- `notes.md`: every note, with its verse and the words it is about.
- `ccel.md`: what came of CCEL's notes: how many were set, which eBible note accounts for every duplicate with both texts and callers, which were held back for a decision about Codex Alexandrinus, and which were left out, each with its reason and its source.
- `alexandrinus.md`: every decision about Codex Alexandrinus, with the passage before and after.
- `byzantine.md`: the reconciliation of the New Testament in figures, and `byzantine/`, one file per book: every place the Greek texts differ, with its witnesses in their own words, its disposition and tags, and the English before and after, then the corrections of the English where the Greek is shared. This is the review a reader of the New Testament's changes works from; [CONTRIBUTING.md](CONTRIBUTING.md#reviewing-the-byzantine-readings) says how.
- `numbering.md`: where the verses stand in the King James Bible.
- `text/`: every book as it is sent to be typeset, and the numbering page and textual variants as the website publishes them (`XXA.json` and `XXC.json`).
- `changes.diff`: what differs from the last review.

The review is written from the prepared edition and never read by the build. The decisions and their reasons are the record of why the edition reads as it does; there is no other log.

### What the build checks

Before typesetting, the build stops on a changed source archive, a stale or malformed decision (among them a CCEL correction or placement that applies to nothing, or places a note where the words already do), a reading from Codex Alexandrinus without its decision, a citation it can't read, an abbreviation left in a source's form, a number with a period inside a note's sentence, and a change of wording or spelling that doesn't apply. In the New Testament it stops on a Poppler conversion that gives other counts than the sources have, a structural decision that disagrees with the Greek inventories, a reading whose evidence is not in its source or that the build would decide alike without it, a placement the code now makes on its own, a TR note lemma that is not unique, a correction of shared Greek whose Greek is not RP2026's or touches a difference, and any verse whose characters differ from the pinned King James text outside a declared edit and its seams. It also checks PTXprint's processed copy of every unit against what was sent.

After typesetting, it checks the B5 geometry, the embedded fonts (OLEBFont, the installed Greek face, Ezra SIL, and, with Valkyrie, TeX Gyre PagellaX, and no other), missing glyphs, the contents and its page numbers, that each unit of back matter opens a recto and the colophon a verso bearing its words alone, followed by the two blank pages that close the book, the phrases listed in `edition/witnesses.json` (to catch unusual passages going missing), source-form citations, and that every margin note stands in its page's margin below the note above it.

### Looking at the pages

The checks cannot judge how a page looks. After any change that could move text between pages, read through the sample, then run `make pdf` as well and read the pages around the change. The places most likely to go wrong are:

- pages crowded with notes, and whether each note falls on the page with its verse
- the New Testament marginal notes, including the Greek in Acts 13:18 and 13:34, and the TR notes, densest in Revelation
- the verses the Byzantine text lacks or moves: Luke 17:35, Acts 8:36, 15:33, and 24:6, Romans 14:24–26 and 16:24, Matthew 23:13–14, 1 John 5:7–8
- the displaced passages of Proverbs 24, under the Hebrew's numbers, and the join from chapter 29 to 31:10
- Sirach's Prologue, set as the book's introduction, and the Epistle of Jeremias's unnumbered title
- Greek and right-to-left Hebrew in Brenton's notes
- poetry in the Psalms
- the contents and the table of book names in the introduction
- the joins between 2 Esdras and Nehemias and between Malachias 3 and 4, and the additions to Daniel
- the opening pages of each testament
- the end matter: the Odes and the Order of the Psalter on their rectos, the Psalter's tables with their footnotes, the colophon on its verso, and the two blank pages after it
