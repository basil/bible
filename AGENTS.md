# Working on this repository

This is a hobby project that prepares a printed Bible from pinned sources. Keep it small and understandable: prefer deleting to adding, and a plain function to a new abstraction.

## Building

You need Docker with the Compose plugin, Make, and about 5 GB of disk space. Everything runs in a container, so you don't need Python, TeX or Poppler on your machine.

```sh
make bootstrap  # build the container image (needs the network)
make pdf        # build dist/bible.pdf
```

Run `make bootstrap` first, and again when the build says the image is stale. The build and test targets run with networking turned off and read the texts from the archives committed in `sources/`:

```sh
make sample    # a short PDF of selected chapters, for checking layout quickly
make validate  # prepare the whole edition, checking every source and decision, without typesetting it
make clean     # delete build/ and dist/
```

The sample prints the chapters listed in `edition/sample.json`, which were picked to cover the awkward cases: Psalm 151, the additions to Esther and Daniel, the join between 2 Esdras and Nehemias, the end of Malachias, the displaced passages of Proverbs 24, quoted Greek and Hebrew, the verses the Byzantine text lacks or moves (Luke 17, Acts 24, Romans 14, Matthew 23, 1 John 5), Revelation 13 with its many readings, and pages crowded with notes. The appendix of readings prints the entries of the sampled chapters alone.

Alongside the PDF, the build writes `dist/bible.provenance.json`, which records the packages and fonts that produced it. Logs and intermediate files go to `build/`, which is regenerated on every run.

## How the edition is prepared

Every departure from the sources is a decision recorded in `edition/*.json`, and the build carries those decisions out in a fixed sequence of stages:

1. **Read:** the pinned archives are parsed, with the slips in their transcription corrected. Of the King James Bible only the books the edition prints, borrows from or places its verses in are parsed. The New Testament's Greek texts and witnesses are read from their archives and files into memory, the two PDFs among them by Poppler. Nothing is read after this.
2. **Promote:** the readings from Codex Alexandrinus are put into Brenton's text, and the readings of the Byzantine text into the King James text: the Greek texts are compared unit by unit, the witnesses attached, the decisions validated against them, every unit given its disposition, the edits and the structural changes carried out, and the Textus Receptus notes set (`src/bible/byzantine/`). In both, the chosen text goes into the verse and the displaced reading becomes a note that names its witness; the editor's corrections of the English where the Greek texts agree are carried out with an "Or," note giving the former King James words, which names none.
3. **Assemble:** the edition's books are made from the sources' chapters, under the edition's names: Nehemias from the file that holds Esdras, Daniel with Susanna and Bel and the Dragon, the close of Malachias as its fourth chapter, and without the empty chapter eBible left in Proverbs. What the edition prints is read from the assembled books.
4. **Place:** each verse is matched to its place in the King James Bible: the Old Testament's from the table and the words, the New Testament's from the verses the Byzantine text lacks or places elsewhere. The notes, the links and the table of chapters and verses read it.
5. **Line:** the poetry is set in lines after the Updated Brenton (`src/bible/lines.py`): each of its chapters is aligned word by word with Brenton's, and its lines and stanza breaks are placed in Brenton's words, in the verses Scrivener's King James Bible sets as verse too or has no say in; the breaks the words cannot place are in `edition/lines.json`. The New Testament keeps Scrivener's paragraphs and poetry. The Psalter's kathismata and stases are then marked from `edition/psalter.json`.
6. **Matter:** the translations' front and back matter is brought into the edition's style, citing and abbreviating as the edition does.
7. **Annotate:** Brenton's notes, the 1611 margin and the edition's own notes are set as footnotes on the words they are about, with the quotation links and the books' introductions.
8. **Revise:** spelling and punctuation are revised.
9. **Authored:** the edition's own pages are filled in with the passages and tables they ask for, among them the appendix of readings, which quotes the books as revised.
10. **View:** the whole edition or the sample is selected, and typographic quotes are applied.
11. **Export:** USFM is written for PTXprint, with the few things only it needs, and PTXprint typesets it.

The stages are in `src/bible/pipeline.py`, which is the place to start reading the code.

## Principles

- **Separate the concerns, and change nothing in place.** The build is the fixed sequence of stages above. Each stage is a function of the stages before it and of the policy: the decisions, loaded once as the `Policy` in `src/bible/policy.py` and frozen. A stage builds what it changes and shares the rest. It never alters a document, the policy or a source it was given; a stage that adds to the policy returns a new one.
- **Make transformations simple to write, read and trust across the whole corpus.** A rule applies everywhere, and what departs from it is a decision in `edition/*.json`, with its reason. A decision that no longer fits its source, changes nothing, or matches nothing stops the build and names itself, so the files can't go stale: fix or remove it. Refuse what a transformation does not understand rather than guess at it.
- **The build decides; it does not wait.** Every Greek difference of the New Testament gets one disposition on every build, from the sources, the code and the decisions, and nothing else: no approval, sign-off or review status gates what executes. A text that is wrong is fixed by changing a decision or a rule, then rebuilding. An instruction is judged and carried out by construction, never in parts, so that a finished sentence is always one source's wording or the editor's, never a splice. The target is RP2026's main text; other editions are evidence about readings, never the target.
- **Decide on meaning, not on rendered output.** Work on the USJ document and on the words of a verse, not on serialized USFM, exported text or the PDF. A regular expression over markup is a sign that the decision is in the wrong place.
- **Marshal at the boundaries.** USFM is parsed once, when the sources are read, and written once, for PTXprint. Between those two ends everything is [USJ](https://docs.usfm.bible/usfm/latest/usj/), the JSON form of USFM, extended only by `x-key` and `x-scope`. Do not add a second document model or a new extension without need. The few places that still meet USFM text between the ends are listed under [the document model](#the-document-model); do not add to them.
- **Run transformations in the order of their dependencies.** A new transformation goes in the stage where everything it reads is ready, and nothing reaches back to an earlier stage's work. Revision finishes the translations after source-dependent decisions, so those decisions are still written in the sources' own words. Authored pages then consume the revised text and receive their own punctuation finishing pass, retaining the source names they discuss.
- **Use semantic markup, not hard-coded strings.** Build USJ nodes rather than backslash markers in strings. Take terms and abbreviations from `edition/terminology.json`, and books and their names from `edition/manifest.json` and `edition/citations.json`.
- **Keep checked-in data normalized.** State each fact once. Do not check in what the build can derive, and do not copy a source's words into a decision unless the build verifies the copy against the source, so that it cannot drift unnoticed. Keys are the short source keys (`GEN 1:9#2`), not hashes or positions.
- **Revise spelling and punctuation in one place.** That place is `edition/revisions.json`. Do not respell the sources, the other decision files or the code.
- **Leave the sources and the build output alone.** Do not edit the files in `sources/` or anything in `build/`. A change to the English needs its own decision, with evidence, exact scope and a before-and-after comparison in the review diff. A formatting rule must not change the English, or the witness a reading is attributed to.

## The document model

Every document between the sources and PTXprint is USJ: plain objects, lists and strings, read and written by `src/bible/usj.py` and checked in the tests against usfmtc, the USFM committee's own parser. The build adds two things to it and no more:

- A note carries `x-key`, the address of the source note it was made from: `GEN 1:9#2` is the second note of Genesis 1:9 as the source numbers it, and `MAT 6:1 of` is the 1611 note on "of" at Matthew 6:1. The keys are stable while the source archive is, and the archive is pinned by its hash.
- A note that the edition writes carries `x-scope`, the words it is about, and the standard `category` of `edition`: the notes that a decision about Codex Alexandrinus writes or moves; the Textus Receptus notes, keyed by the Greek unit they are about (`MAT 3:8#1 TR`, and `MAT 3:8#1 TR#2` for a unit's second note) or, for a verse omitted or moved, by the verse they stand at (`LUK 17:35 TR`, `ROM 14:24 TR`); the "Or," notes on the corrections of the English where the Greek is shared, keyed by their verse (`LUK 23:42 rendering`); and the notes that say where the Hebrew has a passage the Greek sets elsewhere, keyed by the verse they stand at and the Hebrew's label (`PRO 24:22f Heb.`), in the same form as the New Testament's notes on moved verses. While the promote stage finishes a Textus Receptus note, its `x-scope` also says what the note says the Received Text has (its `kind`: other words, words added or omitted, a verse added, a passage elsewhere) and the verse or passage it names; every step decides on that, never on the note's words, and the note as printed declares only its lemma.

A stage decides on a document's words, not on its markup. `usj.py` and `scripture.py` read the words of a verse or a paragraph as one string, whatever notes and styles stand among them, and make a change at its offsets: `replaced` and `inserted` set content in place of words, and `substituted` rewrites words in the styles they stand in.

USFM as text is read at the two ends: `repairs.py` corrects a source's transcription before it is parsed, and `verify.py` reads what PTXprint wrote (`usfm.py` holds the helpers both use). Three things between them still meet it, and nothing else should. The names of the sources' books and the numbers of their chapters and verses are in places read from the sources' text (`assembly.py`, `pipeline.authored`). The editor's own pages are parsed once the passages and tables they ask for have been filled in (`numbering.page`). And a decision that gives words with their markup is written in USFM and parsed where it is carried out: the `from`, `note`, `appendix`, `to` and `source_note` of a decision about Codex Alexandrinus, for which a source's note is written out to be compared with it (`notes.source_text`), and the `from` and `to` of a name change in `edition/book-introductions.json` or `edition/citations.json`.

## Decisions

Each decision gives its reason, usually as `why`. The shape of each file is declared in `src/bible/policy_schema.py`, and the existing entries are the best examples of each kind.

A decision about a note is keyed by the note's `x-key`. A decision about front or back matter is keyed by its unit and the words it concerns, as `XXB There is`. A decision about a Greek difference of the New Testament is keyed by its unit: the verse and the Received Text's and Byzantine text's words there, as `MAT 5:39#1`; a placement by the witness and its row, as `faa 1PE 5:10#2`.

A correction to a slip in transcription must match the source text exactly once, and in the scripture itself it may mend only word spacing, so that the wording stays eBible's. It must also fit one of the kinds of slip that `src/bible/repairs.py` defines (a missing word space, a stray letter, a bracketed remark, and so on), or be marked `"uncategorized": true`, so that no correction can rewrite the translation unnoticed.

### Where a change goes

| To change | Edit |
| --- | --- |
| Which books are printed, their order, names and headings | `edition/manifest.json` |
| A slip in a source's transcription | `corrections` in `edition/brenton-notes.json` or `edition/kjv-notes.json` |
| The words a note is about, its italics, or whether it is a sentence | `notes` in the same files |
| A reading from Codex Alexandrinus, a supplied passage, or a kept note | `edition/alexandrinus.json` |
| A Byzantine reading the build does not decide, a ruling that a difference is not applied, a verse omitted or moved, a difference of accent alone, Hodges–Farstad's side where no apparatus gives it, or the lemma of a TR note | `edition/byzantine.json` |
| A correction of the King James English where TR and RP2026 share the Greek | `readings` in `edition/byzantine.json`, keyed by the verse |
| Which Greek unit a witness's row is about | `edition/byzantine-placements.json` |
| A 1611 note left out, or set on other words, because the text changed | `notes` in `edition/kjv-notes.json` |
| How a citation is read or printed | `edition/citations.json` |
| The wording of a note or of front matter | `edition/prose.json` |
| An abbreviation, or the list of abbreviations | `edition/terminology.json`, `edition/abbreviations.json` |
| Where a book's introduction goes | `edition/book-introductions.json` |
| A quotation link, or Turpie's judgment of it | `edition/quotations.json`, `edition/turpie.json` |
| Where a verse stands in the King James Bible, an empty chapter of a transcription, or a note saying where a passage stands | `edition/versification.json` |
| The spelling of a word, or the punctuation of a verse, a note or a paragraph of front or back matter | `edition/revisions.json` |
| The Psalter's kathismata and stasis divisions | `edition/psalter.json` |
| Where a line of verse begins, when the words of the Updated Brenton and the source do not place it | `edition/lines.json` |
| The editor's introduction, the numbering table, the divider pages and the appendix of readings | `content/` |
| Page layout, styles and TeX | `config/` |

A page in `content/` names a passage between braces, by its code, and the build prints it; `numbering.sfm` also says where its tables go, which the build writes.

### Where things are

The rest of the repository:

- `sources/`: the Bible texts, the Updated Brenton (read for its lines of verse alone), the 1611 marginal notes, the Greek New Testament in both its texts with its collations and apparatus, the English witnesses to its differences, and the fonts, committed as downloaded. [sources/README.md](sources/README.md) says where each came from.
- `src/bible/`: the Python package that prepares the edition; `src/bible/byzantine/` is the reconciliation of the New Testament with the Byzantine text, run by the promote stage.
- `tests/`: the tests.
- `scripts/`: the font assembly and the PTXprint patch, run when the image is built.
- `Dockerfile`: the tool image, with the pinned versions of PTXprint and the fonts.

## Checking a change

The book should come out the same except where the change means it to differ.

```sh
make lint         # formatting and types
make test         # the whole suite
make review-diff BASE=HEAD  # every line of the edition that the working tree changes
make sample       # the selected chapters, typeset
```

`make test` runs the Python tests, the font tests and the TeX tests side by side, in about two minutes. To run some of the Python tests, use `make test-python PYTEST_ARGS="-k marginal"`.

`make review-diff` compares the edition as the working tree prepares it with the edition at `BASE`, by default `origin/master`, and writes every line that differs to `build/review.diff`. Read the diff after any change to a rule or a decision: an unintended effect shows there as an extra line. Explain every intended difference when you report the work.

`make review` writes the full review to `build/review/`, for reading through:

- `notes.md`: every note, with its verse and the words it is about.
- `alexandrinus.md`: every decision about Codex Alexandrinus, with the passage before and after.
- `byzantine.md`: the reconciliation of the New Testament in figures, and `byzantine/`, one file per book: every place the Greek texts differ, with its witnesses in their own words, its disposition and tags, and the English before and after, then the corrections of the English where the Greek is shared. This is the review a reader of the New Testament's changes works from; [CONTRIBUTING.md](CONTRIBUTING.md#reviewing-the-byzantine-readings) says how.
- `numbering.md`: where the verses stand in the King James Bible.
- `text/`: every book as it is sent to be typeset.
- `changes.diff`: what differs from the last review.

The review is written from the prepared edition and never read by the build. The decisions and their reasons are the record of why the edition reads as it does; there is no other log.

### What the build checks

Before typesetting, the build stops on a changed source archive, a stale or malformed decision, a reading from Codex Alexandrinus without its decision, a citation it can't read, an abbreviation left in a source's form, a number with a period inside a note's sentence, and a change of wording or spelling that doesn't apply. In the New Testament it stops on a Poppler conversion that gives other counts than the sources have, a structural decision that disagrees with the Greek inventories, a reading whose evidence is not in its source or that the build would decide alike without it, a placement the code now makes on its own, a TR note lemma that is not unique, a correction of shared Greek whose Greek is not RP2026's or touches a difference, and any verse whose characters differ from the pinned King James text outside a declared edit and its seams. It also checks PTXprint's processed copy of every unit against what was sent.

After typesetting, it checks the B5 geometry, the embedded fonts, missing glyphs, the contents and its page numbers, the phrases listed in `edition/witnesses.json` (to catch unusual passages going missing), source-form citations, and that every margin note stands in its page's margin below the note above it.

### Looking at the pages

The checks cannot judge how a page looks. After any change that could move text between pages, read through the sample, then run `make pdf` as well and read the pages around the change. The places most likely to go wrong are:

- pages crowded with notes, and whether each note falls on the page with its verse
- the New Testament marginal notes, including the Greek in Acts 13:18 and 13:34, and the TR notes, densest in Revelation
- the verses the Byzantine text lacks or moves: Luke 17:35, Acts 8:36, 15:33 and 24:6, Romans 14:24–26 and 16:24, Matthew 23:13–14, 1 John 5:7–8
- the displaced passages of Proverbs 24 and the join from chapter 29 to 31:10
- the appendix of readings, with its Greek
- Greek and right-to-left Hebrew in Brenton's notes
- poetry in the Psalms
- the contents and the table of chapters and verses
- the joins between 2 Esdras and Nehemias and between Malachias 3 and 4, and the additions to Daniel
- the opening pages of each testament and of the appendices
