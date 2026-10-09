# Contributing

[AGENTS.md](AGENTS.md) explains how to build the edition, how it is prepared, the principles every change holds to, and how a change is checked. This page covers the editorial work, the layout, the dependencies and the sources. The [README](README.md) describes what the edition contains, and the [editorial notes](docs/edition.md) give the reasons for its choices.

## Editorial changes

### Reviewing the readings from Codex Alexandrinus

Each reading printed in the text is a decision in `edition/alexandrinus.json`. It records the note of Brenton's that it rests on, the words it replaces, how its English is derived from Brenton's, and Swete's evidence. The English must be Brenton's own: every change of wording, order or punctuation is declared, and the build rejects a word that is neither his nor declared as supplied.

After changing a decision, run `make review` and read its entry in `build/review/alexandrinus.md`: the passage before and after with its neighbours, the footnote printed, and the Swete record. Check grammar, punctuation, names, numbers, and the words the note identifies.

Print a reading when Swete gives an unambiguous position and Brenton supplies the English without substantive rewriting. Agreement with Swete does not by itself settle the English or the point of insertion, so consult the page image whenever Swete changes the placement or the interpretation. Keep a doubtful reading as a note, with its reason and a `todo`, rather than supply an unresolved English reconstruction.

### Reviewing the Byzantine readings

The New Testament's changes are decided by the build from the Greek texts and the published witnesses, as [the New Testament text](docs/new-testament.md) explains; what the build cannot decide, or decides otherwise than the editor, is a reading in `edition/byzantine.json`. A reading is keyed by the unit it concerns (the verse, and the Received Text's and the Byzantine text's words there, as `MAT 5:39#1`), and gives the edits or a `nochange` ruling, one `from:` tag for where the wording comes from and one `gram:` tag for the kind of difference, a reason of at most two sentences, and evidence quoted from the sources, which the build checks verbatim: a verse of the Revised Version or Boyd's ASV, or a row of Pierpont's or an apparatus. A placement in `edition/byzantine-placements.json` says which unit a witness's row is about where the code cannot tell; it is objective, with one right answer. A lemma widened by hand is under `lemmas` in `edition/byzantine.json`, keyed by the note. A reading already recorded may be revised when another wording follows RP2026 and the house style better: judge the alternatives on their merits, for a reading has no preference merely because the build accepts it.

After changing a decision, run `make review` and read the unit in `build/review/byzantine/<BOOK>.md`: the Greek of both texts at the unit and in the whole verse, the King James words before and after, the note as printed with its lemma in bold, every witness in its own words, the disposition with its tags and a sentence saying how it follows, and the reading if there is one. `build/review/byzantine.md` gives the figures. For a unit that changes, ask in order: is the Greek difference real at this unit, and not orthography; does the instruction bind to the pinned King James text; is the new wording what RP2026's main text says, and not the Received Text's, Hodges–Farstad's or a marginal alternate's; is it King James English, by the house style; does the seam read; and does the note, put back, give the King James words exactly. For a unit that does not change, ask whether any witness shows the difference at the King James Version's level of literalness: `ev:tcent-reports` on a silent unit is the strongest sign that it does.

Where the Received Text and RP2026 share the Greek and the King James English mistranslates it, a reading keyed by the verse (`LUK 23:42`) gives the edits, each with the printed RP2026 Greek it renders as `greek`, a reason and quoted evidence; it needs no tags and makes no TR note. The build checks that the Greek is RP2026's and touches no difference from the Received Text. Its review follows the units in `build/review/byzantine/<BOOK>.md`, under the corrections of shared Greek, comparing original KJV with the corrections-only baseline. Unit comparisons show that baseline to the prepared edition, while labelled whole-verse comparisons and the printed appendix retain all wording changes. The appendix applies systematic spelling and punctuation to both sides before verse-specific punctuation revisions. Disagreement among the English witnesses does not by itself justify one.

A reading the build would decide the same way without it is redundant, and a placement the code now makes on its own is stale: each stops the build and names itself, so that the files cannot drift. Remove it.

### Reviewing the notes

The build works out by rule which words each note is about and which of its words are italic. Where a rule goes wrong, a decision under `notes` in `edition/brenton-notes.json` or `edition/kjv-notes.json` gives the note's `lemma`, the words it is about, or its `note`, the note's own words with its italics between underscores. In such a decision, `quotation: true` identifies the italic spans as quotations rather than alternative renderings: they keep their opening capital and do not widen with the lemma.

The tests flag a note whose lemma is much longer than its rendering. Read a flagged note. If the rule is wrong, give the note a `lemma`. If it is right, list the note under `shapes` in `edition/brenton-notes.json`.

### Reviewing the citations

A citation that the build can't read stops it and names the note and the words. So does a citation of something the edition doesn't print, which is usually a citation by another numbering. Read the note and the verse it means, and add a decision to `edition/citations.json`. The commonest kinds:

- `numbering` reads the citation by the King James Bible's numbering or the Hebrew's.
- `passages` and `print` say what is cited and what is printed, where the build can't tell.
- `unprinted` is for a citation of something the edition doesn't print, such as a verse that the Vatican text lacks.
- `not_a_citation` is for figures that only look like a citation.

### Reviewing the numbering

The build works out where each verse stands in the King James Bible: the Old Testament's from the table and the words, the New Testament's from the verses the Byzantine text lacks or places elsewhere, which are decisions in `edition/byzantine.json`. It uses STEP Bible's table, the words the two translations share, and the editor's readings in `edition/versification.json`. The result is worked out afresh on each build, so a change to the text carries through to the numbering.

`build/review/numbering.md` lists every run of verses and what it rests on. To correct a run, read both translations and add a reading with its reason. A chapter that a transcription numbers without words (eBible's Proverbs 30) is a `stub` in `edition/versification.json`, and a passage that stands at other numbers than the King James Bible's may be given a note saying so, as a `relocation` there; both are checked against the source and the runs.

### Revising spelling, vocabulary and punctuation

`edition/revisions.json` holds the edition's revision of the translation. It has two sections, `words` and `verses`.

A word is respelt or modernized by an explicit editorial vocabulary decision wherever it is printed as a whole word: in the translation, its notes, and the front and back matter. Each decision gives its reason and preserves the surrounding wording. Changes to single verses are grouped under the reason they share, and a change may add a `why` of its own. A verse's change is made to that verse alone, as the edition numbers it; the verse must have the words once, only what differs gives way, and a note of the verse that quotes the words changes with them. Two changes may revise one verse, but not the same words of it.

As the principles say, the revision is made last, so a lemma or a `from` names "Jezekiel" if the source does.

### Outstanding editorial work

The open questions are listed in [the open notes](docs/todo.md), including the readings from Codex Alexandrinus that carry a `todo`.

## Changing the layout

PTXprint's configuration is in `config/`, on top of its layout for the Berean Standard Bible (BSB):

- `layout.ini` overrides the layout settings. The title page is printed from the title and subtitle given here.
- `ptxprint-mods.sty` overrides paragraph and character styles.
- `ptxprint-mods.tex` holds the TeX changes: hyphenation, note placement and folios.
- `protrusion.tex` lets punctuation hang slightly into the margin, and `word-spacing.tex` widens the word space. Both affect line breaking, so changing them can change pagination.
- `changes.txt` holds PTXprint's text substitutions.

The tests require every setting in `layout.ini` and `ptxprint-mods.sty` to change the value it overrides, so a setting that repeats the default must be removed.

Run `make test-tex` after changing the TeX files. If a difference was intended, save the new expected output of the protrusion test with `make test-tex-save` and review the diff.

The Latin typeface is OLEBFont, which is Utopia with the characters it lacks added from Erewhon. [Font normalization](docs/font-normalization.md) explains how it is assembled and tested. `make font-specimen` renders a specimen to `dist/olebfont-specimen.pdf`.

## Code style

`make lint` checks the Python with Black, isort and strict mypy, and checks the Makefile and Dockerfile. `make lint-fix` applies the formatting.

Annotate every Python function, and do not suppress type errors. Keep the shapes of the decision files in `policy_schema.py` and of USJ in `usj.py`, and keep dynamic typing and casts at the JSON and upstream-library boundaries.

The tests share one prepared edition (`edition` in `tests/conftest.py`). A test of a decision declares a changed policy with `changed(policy, name, change)` and runs the stage that reads it, on a small document of its own where it can, not on the whole edition.

## Updating dependencies

Renovate opens pull requests for the Python packages in `requirements.txt`, and for the base image and the PTXprint, usfmtc and Utopia commits in the `Dockerfile`. The font archives in `sources/` are updated by hand, each with its hash in the `Dockerfile`.

The build refuses to run in an image made from a different `Dockerfile`, `requirements.txt`, font script or font archive, so run `make bootstrap` after changing any of them.

The base image is an Ubuntu LTS tag, and its packages come from Ubuntu's live repositories. Rebuilding the image later can bring in a newer TeX, which may change pagination. The provenance file lists the packages each PDF was built with, so that such a change can be traced. After a new Ubuntu release, run `make test` and look at the sample.

When upgrading PTXprint, check the places that depend on its internals:

- `config/protrusion.tex` and `config/ptxprint-mods.tex` wrap PTXprint's private macros for fonts, tables and margin notes. The TeX tests run outside PTXprint, so only the build exercises them.
- The `Dockerfile` and `scripts/patch_margin_convergence.py` patch PTXprint's placement of margin notes. The image build fails if the patched lines have changed upstream. Drop each patch once PTXprint has the fix.

Then look at the sample: the notes should stand beside their verses in the margin, the front matter's footnotes at the foot of the page, and the numbering and abbreviations tables should be intact.

## Updating source texts

Replace a source archive only on purpose. Download the new one somewhere else first and compare it with the old one: the copyright notice, the list of books, chapter and verse labels, notes, italics, tables, and appendices. Then commit the new archive together with its hash in `src/bible/sources.py` and the new retrieval date in `sources/README.md`. The New Testament's Greek texts and witnesses are pinned the same way; the two PDFs among them are read by Poppler inside the container on every build, and the readers' counts (7,957 verses printed, 1,885 rows of the collation) say if a conversion changed.

## Submitting changes

1. Check the change as [AGENTS.md](AGENTS.md#checking-a-change) says, and look at the rendered pages.
2. Explain every intended difference there, in the commit message or pull request. Commit configuration, dependency and source changes together.
3. Open a pull request. CI must pass before merging.

CI runs the lint, the tests and the full build on pull requests and on pushes to `master`, and publishes the PDF from `master`. On a pull request, it writes the review diff into the run's summary. It also lints the Markdown, which no Make target does.
