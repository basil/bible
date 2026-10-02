# Contributing

This covers building the PDF, how the edition is prepared and checked, and how to change things. For what the edition contains, see the [README](README.md). For the reasons behind its choices, see the [editorial notes](docs/edition.md).

## Building

You need Docker with the Compose plugin, Make, and about 5 GB of disk space. Everything runs in a container, so you don't need Python or TeX on your machine.

```sh
make bootstrap  # build the container image (the only step that uses the network)
make pdf        # build dist/bible.pdf
```

Run `make bootstrap` first. The other targets run with networking turned off and read the texts only from the archives committed in `sources/`:

```sh
make sample     # a short PDF of selected chapters, for checking layout quickly
make validate   # prepare the whole edition, checking every source and decision, without typesetting
make review     # write what the edition prints, for reading through, to build/review/
make review-diff  # what the working tree changes in the edition, against origin/master
make test       # run the tests
make clean      # delete build/ and dist/
```

Alongside the PDF, the build writes `dist/bible.provenance.json`, which records the environment that produced it: the OS release, installed packages, Python version, and font hashes. Logs and intermediate files go to `build/`.

The sample prints the chapters listed in `edition/sample.json`. They were picked to cover the awkward cases, such as Psalm 151, the additions to Esther and Daniel, the Ezra–Nehemiah split, the end of Malachias, quoted Greek and Hebrew, and pages crowded with notes.

## How the edition is prepared

The sources are never modified. Every departure from them is a decision in `edition/*.json` with its reason as `why`, and the build is the fixed sequence of stages in `src/bible/pipeline.py` that carries those decisions out:

1. **read:** the pinned archives, with the corrections to their transcription, parsed once. Nothing is read after this.
2. **promote:** the readings from Codex Alexandrinus, on Brenton's books as their source numbers them.
3. **assemble:** the edition's books from the sources' chapters, under its names: Nehemias from the file that holds Esdras, Daniel with Susanna and Bel and the Dragon, the close of Malachias as its fourth chapter. What the edition prints is read from the assembled books.
4. **place:** where each verse of the Old Testament stands in the King James Bible, by STEP Bible's table, the words of both translations, and the editor's readings (`edition/versification.json`). The notes, the links and the table of chapters and verses read it.
5. **matter:** the translations' front and back matter, citing and abbreviating as the edition does, and the introductions that go to the books.
6. **annotate:** Brenton's notes and the 1611 margin as footnotes on the words they are about, the quotation links, and the books' introductions.
7. **authored:** the edition's own pages, with the passages and tables they ask for.
8. **revise:** the edition's spelling and punctuation (`edition/revisions.json`).
9. **view:** the whole edition or the sample's chapters, with typographic quotes.
10. **export:** USFM for PTXprint, with the few things only it needs.

Each stage is a function of the stages before it and of the policy, which is read once and can't be changed. No stage changes a document in place: it builds what it changes and shares the rest.

### The document model

Every document between the sources and PTXprint is [USJ](https://docs.usfm.bible/usfm/latest/usj/), the JSON form of USFM: plain objects, lists and strings, read and written by `src/bible/usj.py` and checked against usfmtc, the USFM committee's own parser, which the image pins. The build adds two things to it and no more:

- A note carries `x-key`, the address of the source note it was made from: `GEN 1:9#2` is the second note of Genesis 1:9 as the source numbers it, and `MAT 6:1 of` is the 1611 note on "of" at Matthew 6:1. The decision files name notes by these keys. They are stable while the source archive is, and the archive is pinned by its hash.
- A note that a decision about Codex Alexandrinus writes or moves carries `x-scope`, the words the decision says it is about, and the standard `category` of `edition`.

A stage decides on a document's words, not on its markup. `usj.py` and `scripture.py` read the words of a verse or a paragraph as one string, whatever notes and styles stand among them, and make a change at its offsets: `replaced` and `inserted` set content in place of words, and `substituted` rewrites words in the styles they stand in. USFM as text is read at the two ends: `repairs.py` corrects a source's transcription before it is parsed, and `verify.py` reads what PTXprint wrote (`usfm.py` holds the helpers both use). Three things between them still meet it. The names of the sources' books and the numbers of their chapters and verses are in places read from the sources' text (`assembly.py`, `pipeline.authored`): of the King James Bible only the books the edition prints, borrows from or places its verses in are parsed. The editor's own pages are parsed when the passages and tables they ask for have been filled in (`numbering.page`). And a decision that gives words with their markup, as the `to` or `source_note` of a decision about Codex Alexandrinus, is written in USFM: it is parsed where it is carried out, and a source's note is written out to be compared with it (`notes.source_text`).

### Where a change goes

| To change | Edit | Read by |
| --- | --- | --- |
| which books are printed, their order, names and headings | `edition/manifest.json` | `assembly.py` |
| a slip in a source's transcription | `corrections` in `edition/brenton-notes.json` or `edition/kjv-notes.json` | `repairs.py` |
| the words a note is about, its italics, or whether it is a sentence | `notes` in the same files | `notes.py`, `lemmas.py`, `annotate.py` |
| a reading from Codex Alexandrinus, a supplied passage, a kept note | `edition/alexandrinus.json` | `alexandrinus.py` |
| how a citation is read or printed | `edition/citations.json` | `citations.py` |
| the wording of a note or of front matter | `edition/prose.json` | `annotate.py`, `matter.py` |
| an abbreviation's printed form, or the list of abbreviations | `edition/terminology.json`, `edition/abbreviations.json` | `terminology.py` |
| where a book's introduction goes | `edition/book-introductions.json` | `matter.py` |
| a quotation link | `edition/quotations.json` (over `edition/turpie.json`) | `quotations.py`, `crossrefs.py` |
| where a verse stands in the King James Bible | a reading in `edition/versification.json` | `places.py`, `versification.py`, `numbering.py` |
| the spelling of a word everywhere, or the punctuation of a verse | `edition/revisions.json` | `revision.py` |

A decision that no longer fits its source, changes nothing, or is met by nothing stops the build and names itself, so the files can't go stale. In a note exception, `quotation: true` identifies its declared italic spans as quotations rather than alternative renderings: they retain their opening capital and do not widen with the lemma.

### Revising spelling and punctuation

`edition/revisions.json` is where the translation's spelling and punctuation are revised, along the lines of the New Cambridge Paragraph Bible. It has two sections:

```json
{
  "words": {
    "Jezekiel": { "to": "Ezekiel", "why": "..." }
  },
  "verses": {
    "semicolons": {
      "why": "...",
      "changes": [
        { "verse": "GEN 1:2", "from": "unfurnished, and", "to": "unfurnished; and" }
      ]
    }
  }
}
```

A word is respelt wherever it is printed as a whole word: in the translation, its notes, and the front and back matter. Changes to single verses stand in groups, named as you please, each under the one `why` its changes share; a change may add a `why` of its own. A verse's change is made to that verse alone, as the edition numbers it; the verse must have the words once, only what differs gives way, and a note of the verse that quotes the words changes with them. Two changes may revise one verse, but not the same words of it. The revision is made last, so every other decision is still written in the sources' own words: a lemma or a `from` for a Codex Alexandrinus reading names "Jezekiel" if the source does. Run `make review` after a change and read `build/review/changes.diff`, which shows every place it reached.

### Review

`make review` writes what the decisions come to, for reading through, under `build/review/`:

- `notes.md`: every note, with its verse, the words it is about between asterisks, the place of the source's caller (‸), the rule that found them, and the note with its italics between underscores.
- `alexandrinus.md`: every decision about Codex Alexandrinus with its source, the passage before and after with its neighbours, the footnotes printed, the derivation of its English, its reason, and Swete's evidence, and an audit table of the Swete records.
- `text/`: every unit as it is sent to be typeset.
- `changes.diff`: what differs in all of these from the last review.

The review is written from the prepared edition and never read by the build.

`make review-diff` shows what a change does without reading the whole review. It writes the review of the base branch (`BASE`, by default `origin/master`) and of the working tree, and every line that differs between them to `build/review.diff`: the whole effect of the change, in context, and nothing else. A respelling shows each place it reached, in whichever book; a rule changed in `lemmas.py` shows each note it moved. Read that diff before committing. CI writes the same diff into the summary of every pull request. The decisions and their reasons are the record of why the edition reads as it does; there is no other log.

## Where things are

- `sources/`: the Bible texts, the 1611 marginal notes, and the fonts, committed as downloaded. [sources/README.md](sources/README.md) says where each came from.
- `content/`: the edition's own pages: the introduction, the table of chapters and verses (`numbering.sfm`), and the three divider pages (`old-testament.sfm`, `new-testament.sfm`, `appendices.sfm`). The title page isn't among them: PTXprint's template prints it from the title and subtitle in `config/layout.ini`. The dividers' subtitles repeat the title page's wording. A page names a passage between braces, by its code, and the build prints it; `numbering.sfm` also says where its tables go, which the build writes. Its inline Psalms section, after `{books}` and ending with `{psalms}`, is inserted in the manifest’s book order.
- `config/`: PTXprint's configuration. `layout.ini`, `ptxprint-mods.sty`, and `ptxprint-mods.tex` hold layout, style, and TeX changes on top of PTXprint's layout for the Berean Standard Bible (BSB), and `changes.txt` holds its text substitutions.
- `edition/`: the build's own settings, which PTXprint never reads:
  - `manifest.json`: which books are printed, in what order, and what they're called and how their headings break into lines.
  - `kjv-notes.json`: placements and corrections for the 1611 New Testament notes.
  - `alexandrinus.json`: the printed readings from Codex Alexandrinus, the passages supplied from the Appendix, the notes kept, and the Swete evidence for every decision.
  - `brenton-notes.json`: corrections to the words and italics the build works out for Brenton's notes, and to a few slips in eBible's text; and the lemmas of unusual shape that have been read.
  - `book-introductions.json`: which paragraphs of the introduction to the Apocrypha stay at the front and which introduce each book as a footnote, with the editorial glosses, book-name changes, and their reasons.
  - `abbreviations.json`: the rows added to Brenton's list of abbreviations and dropped from it, and the corrections to his meanings.
  - `terminology.json`: each term's printed form and meaning, and the ways the sources write it.
  - `prose.json`: changes to the wording of particular notes and paragraphs: abbreviations printed in full, numbers and their punctuation. A note is named by its key, a paragraph by its unit and the words changed, which must be the unit's once.
  - `revisions.json`: the edition's revision of spelling and punctuation: words respelt everywhere, and changes to single verses, grouped by their reason.
  - `citations.json`: how each source writes its citations (its names for the books, its numerals and stops, and the numbering it cites by); which way each piece of front and back matter writes them; the editor's decisions on the citations that the grammar can't read, or reads by the wrong numbering; and the names that are changed where a book is named but not cited.
  - `versification.json`: the editor's readings of where a verse of the Old Testament stands in the King James Bible, the verses the edition relabels, and what the King James Bible sets apart in its Apocrypha.
  - `sample.json`: the chapters the sample prints.
  - `witnesses.json`: phrases that must appear in the finished PDF, to catch unusual passages going missing.
- `Dockerfile`: the tool image, with the pinned PTXprint, usfmtc, and Utopia commits and the hashes of the font archives.
- `src/bible/`: the Python package. `pipeline.py` is the sequence of stages and the place to start reading; `cli.py` runs it, `project.py` writes PTXprint's project, `typeset.py` runs the pinned backend, `verify.py` checks the result, and `publish.py` writes `dist/`. `places.py`, `tvtms.py` and `alignment.py` work out where each verse stands in the King James Bible.
- `pyproject.toml`: pytest's settings. The Python dependencies are pinned in `requirements.txt`.
- `tests/`: the pytest tests, named after the modules they test, and the TeX tests of the font adapters.

## Checks

The build stops on a changed source hash; a correction, exception or decision that is malformed, changes nothing, or is met by nothing; a note or passage from Codex Alexandrinus without its decision; a citation it can't read or that names what the edition doesn't print; an abbreviation left in a source's form; a number with a period inside a note's sentence; and a change of wording or spelling that doesn't apply. It also checks PTXprint's processed copy of every unit against what was sent.

After typesetting it checks B5 geometry, embedded fonts, missing glyphs, the contents and its page numbers, declared witnesses, source-form citations and margin-note collisions. These checks supplement visual inspection.

`make test` runs the Python tests, the font tests and the TeX tests side by side, in under a minute. To run some of the Python tests:

```sh
make test-python PYTEST_ARGS="-k marginal"
```

The tests share one prepared edition (`edition` in `tests/conftest.py`). A test of a decision declares a changed policy with `changed(policy, name, change)` and runs the stage that reads it, on a small document of its own where it can. Use focused tests while editing, then run `make test` and `make review`, and read `changes.diff`. Build and inspect the sample when presentation can change, and the full PDF when layout or pagination can change.

### Looking at the pages

The checks catch missing text, not bad pages. After any change that could move text around, read through the sample, and the full PDF if the page count changed. The places most likely to go wrong are:

- pages crowded with footnotes, and whether each note falls on the page with its verse
- the New Testament marginal notes, including the Greek in Acts 13:18 and 13:34
- Greek and right-to-left Hebrew in Brenton's notes
- poetry in the Psalms
- the contents and the table of chapters and verses
- the joins between 2 Esdras and Nehemias and between Malachias 3 and 4, and the additions to Daniel
- the opening pages of each testament and of the appendices

### Reviewing the readings from Codex Alexandrinus

`edition/alexandrinus.json` declares every promoted reading with the source words it replaces (`from`), the derivation of its English, and its reason. A decision is keyed by the note it rests on, as `GEN 5:25`, or for a passage by the verses it supplies. Appendix decisions pin the paragraph they take (`appendix`) and say which verses it replaces or supplies. The declared KJV source for 1 Kingdoms 23:12 (`kjv: true`) is read verbatim from the pinned archive; its English is not edited. Every decision, including those kept as notes, records Swete's volume, printed page, Greek reading, evidence type and agreement, with any qualifications explained in its `why`.

Each source note a decision rests on is stored once in full and must match the corrected text of the pinned archive exactly: `source_note` for a reading or a kept note, and `source_notes`, by note key, for the notes an Appendix passage takes up. Every replacement and every supplied verse has its own `english` derivation. `source` selects the Brenton note or Appendix paragraph (`brenton`) or the words replaced (`from`); an optional `span: [start, end]` selects a zero-based, half-open character range of it, otherwise the whole is used. Ordered, non-overlapping `edits` each select a `span` within that phrase and give its replacement `to`, in USFM, so that supplied words are written `\add ...\add*`; equal start and end declare an insertion. An edit's optional `why` overrides the decision's reason. The build derives the final wording from these declarations, and its vocabulary must be Brenton's or listed as `supplied`: spelling, punctuation, word order and supplied-word markup can't change without a declared edit. An optional `note_at` gives the caller's character offset in the derived words. A further replacement in a neighbouring verse is an entry of `edits` with its `target`.

A note the edition writes says what each of its parts is, by the note markers of USFM: `\fl` a label ("Vat.", "Heb."), `\fqa` an alternative rendering, `\fq` words quoted, `\xt` a citation, and `\ft` the rest. Without a `note`, a reading's footnote is "Vat." and the words displaced; `"note": null` leaves none. A `lemma` says which words the note is about where they aren't the words printed after its caller. `witnesses` records which texts support the adopted and the displaced wording where the printed note leaves it ambiguous. A reading's `note_edits`, by note key, rewrites a neighbouring note whose attribution must change, with its source words as `from`, the new note as `to`, and a `lemma` if its words change. A note of Brenton's that survives within replaced words keeps the lemma and the narrower gloss it had, found again as whole words in the verse; if they are gone or repeated the build stops. A whole-verse omission declares `omit_verse: true` and a `note_target` naming the preceding verse: the build removes the verse's number and sets the note at the end of that verse.

Run `make review` after changing a decision or its implementation, and read every before and after passage with its neighbours, the printed footnote, and the Swete record in `build/review/alexandrinus.md`; `changes.diff` shows what moved. Check grammar, punctuation, names, numbers, conjunctions, and the words identified by each note. Consult the page image whenever Swete changes the placement or interpretation. A recorded `agrees: true` does not by itself settle the English or insertion point. Proceed when Swete gives an unambiguous position and Brenton supplies the English without substantive rewriting; record corrected and marginal manuscript readings in the editorial evidence. Label displaced Vatican readings "Vat."; record any uncertainty about their attribution in the decision and todo. Keep a doubtful reading as a note or Appendix passage with its reason and a todo, rather than supply an unresolved English reconstruction.

### Reviewing the notes

The build works out which words each note is about, and which of its words are italic, by rule; `edition/brenton-notes.json` and `edition/kjv-notes.json` correct the rules where they go wrong. After changing `src/bible/notes.py`, `src/bible/lemmas.py` or either file, run `make review` and read `build/review/changes.diff`, which shows every note whose words or italics changed since the last review. A correction the rules no longer need fails the build, so remove it.

Most lemmas are found by rule and read by nobody. The tests hold each of those to the shape of its rendering: a lemma three or more words longer than the rendering that measured it is flagged, as "Gr. _hands_" on a clause of seven words would be. Read a flagged note. If the rule is wrong, give the note a `lemma`; if it is right, list the note under `shapes` in `edition/brenton-notes.json` with what you found. A note listed there that is no longer flagged fails the test, so remove it.

An exception is keyed by its note: `GEN 2:9#2` is Brenton's second note on Genesis 2:9, and `MAT 6:1 of` the 1611 note on "of". Its `lemma` gives the words the note is about (`null` for the whole verse), with an `occurrence` where they occur more than once; its `note` gives the note's own words with its renderings between underscores, as `"Not in the Heb. _friend of bridegroom_, or _attendant at marriage_."`, as the source writes them, before its citations are printed in the edition's form; `sentence` says whether it is a sentence of its own. A `note` declares all of the note's italics: the words it leaves outside underscores stay roman, even in quotation marks, which the rules alone set in italic. A Brenton exception with a repeated lemma may give `"widen": false` to keep precisely the words it glosses, where widening would obscure the meaning of the note. A note that its source sets in the wrong verse gives the right one as `verse`, as the edition numbers it: George's lemma is then looked for there, and a note of Brenton's, which has no caller there, must give its `lemma`. A 1611 note may also give the `anchor` where George's lemma is spelt otherwise than the Cambridge text.

A correction to eBible's text is keyed by its verse. If it changes a note, the bare verse key means the first note; `#2` means the second, `#3` the third. Put several corrections to one note in a list under that note's key. In a file without verses, such as the preface, a correction to a note is keyed by the words the note stands among, and one outside the notes by the words it mends. The build fails if the source text is not found once, in that place. Outside a note, a correction may mend only word spaces in the translation, a book's verses or a passage the appendix supplies, so that its wording stays eBible's; the words of a preface, an introduction, or the appendix's notes and labels may be mended. Every entry in either file gives its reason as `why`. Each correction, and each anchor that differs from George's lemma, must also fit one of the kinds of slip that `src/bible/repairs.py` defines (a missing word space, a stray letter, a bracketed remark, and so on), or be marked `"uncategorized": true`.

### Reviewing the citations

A citation that the build can't read stops it, and names the note or the unit and the words: `Citation that can't be read: ISA 34:11 (13. 22)`. So does one that names what the edition doesn't print, which is usually a citation by another numbering. Read the note, and the verse it means, and add a decision to `edition/citations.json` with its reason as `why`:

- `numbering` reads the citation by another numbering than its source's: `kjv`, the King James Bible's; `hebrew`, for a psalm by the Hebrew's number; or `kjv-verses`, for Brenton's chapter with the King James Bible's verse. The edition's numbers are worked out from `edition/versification.json`.
- `passages` and `print` say what is cited and what prints, where the grammar can't: `print` names a book by its code between braces, as `{PSA} 41:5`, so that the edition's name for it prints.
- `unprinted` and `print` are for a citation of what the edition doesn't print, as a verse that the Vatican text lacks. It stays among the note's words.
- `not_a_citation` is for figures that only look like one.

A decision on a note is keyed as the note is. One on front or back matter is keyed by the unit and the words it decides, as `XXB Psalm iv. 4`. A name for a book that a source uses, and the dialects don't have, goes under the source's dialect. A decision that nothing meets, or a name that nothing uses, stops the build, so remove it.

### Reviewing the numbering

The build works out where each verse of the Old Testament stands in the King James Bible, in runs of verses. Each run says what it rests on as `by`: `table`, STEP Bible's account of a Bible numbered like this one; `words`, the words the two translations share; `place`, its place between verses that the words fix; or `reading`, the editor's reading of both. A verse that no run lists keeps its number, unless Brenton letters it. The tests hold each run to its witness, and check that every verse of both Bibles has a place.

Only the readings are checked in, under `readings` in `edition/versification.json`, each with its reason as `why`. The build works out the rest afresh each time, so a change to the text carries through to the numbering with nothing to reconcile. A reading stands whatever the witnesses give, and one that changes nothing they give stops the build. Runs of equal length pair verse for verse. An optional `pairs` object gives each edition verse's exact King James passage where only part of a verse overlaps another; its keys and targets must cover exactly the declared run.

`make review` lists every run in `build/review/numbering.md`, and gives both translations' words for the runs that rest on words or place alone. To correct a run, read both translations, and add it to the file as a reading. `make review-diff` shows what a change does to the numbering.

## Submitting changes

1. Run `make test`, `make review-diff` and `make sample`, and read `build/review.diff`.
2. Look at the rendered pages, as above.
3. Commit configuration, dependency, and source changes together, and explain why in the commit message.
4. Open a pull request. CI must pass before merging.

CI runs `make bootstrap`, `validate`, `test`, and `pdf` on pull requests and on pushes to `master`, and publishes the PDF to GitHub Pages from `master`. It doesn't run `make sample`, so run that yourself.

## Changing the layout

- `config/layout.ini` overrides PTXprint's BSB layout settings.
- `config/ptxprint-mods.sty` overrides paragraph and character styles.
- `config/ptxprint-mods.tex` holds TeX-level changes: hyphenation, note placement, folios, and the loader for `config/protrusion.tex`.

The tests require every setting in `layout.ini` and `ptxprint-mods.sty` to change the value it overrides (an explicit `FontSize` also clears inherited `FontScale`), and a checkbox PTXprint stores under several keys to be set under all of them.

Don't edit anything in `build/`; it's regenerated on every run.

PTXprint uses plain XeTeX, so the microtype package isn't available. Instead, `config/protrusion.tex` carries a copy of microtype's default protrusion table, which lets punctuation and a few letters hang slightly into the margin so the column edges look straight. Production and the isolated font regression test load the same adapter; the test does not need PTXprint's note-layout macros. Protrusion affects line breaking, so changing it can change pagination. microtype has no settings made for OLEBFont, GFS Didot, or Ezra SIL, so all three use the defaults.

Run `make test-tex` after changing the table. If the change was intended, save the new expected output with `make test-tex-save` and review the diff.

`config/word-spacing.tex` multiplies OLEBFont's inherited Utopia word space, stretch and shrink by 6/5 (1.2), once per font instance. The factor increases each dimension by 20% and retains Utopia's spacing proportions. The resulting dimensions are approximately 0.27em, 0.135em and 0.09em. The adapter wraps font selection after protrusion and leaves other families alone. BSB's global spacing limits remain disabled. `make test-tex` checks the resulting word glue, scaling, feature combinations and repeated selection. This changes line breaks and pagination without changing the font files.

OLEBFont is the edition’s combined Latin family. `scripts/build_olebfont.py` runs after the pinned Utopia conversion and pairs regular, italic, bold and bold italic with their Erewhon counterparts. Utopia wins overlapping glyphs and character mappings, with one exception: Unicode superscript 1, 2 and 3 use Erewhon’s outlines, widths and hint dictionary so they match the rest of the superscript figures. Erewhon Math supplies glyphs missing from both text sources, with Bold Math preferred in bold faces and Regular Math filling its coverage gaps. Donor outlines, spacing, positioning and hints are enlarged by 100/94 to restore Utopia size. Donor subroutines are expanded before scaling; Utopia programs and local subroutines remain unchanged in separate CID hint dictionaries. See the [normalization and validation](docs/font-normalization.md). It refuses unsupported global subroutines or seac composites; the pinned sources use neither. It retains Utopia’s layout metrics and expands clipping bounds for added glyphs.

Native PTXprint font settings enable `onum` and `pnum` on all four faces, so chapter figures, headings, notes, front matter and contents inherit proportional oldstyle numbers. The stylesheet selects `sups` for verses and note origins, and `smcp`/`c2sc` for running furniture. These settings preserve the nominal sizes, zero extra superscript raise and fixed 1 pt origin gap. No content digits are rewritten. Native `\XeTeXgenerateactualtext=1` records the input Unicode as PDF ActualText, preserving copy/search for CID glyph alternates that would otherwise extract as private-use codes or disappear. The assembler corrects Erewhon Italic’s tabular oldstyle zero advance from 498 to 500 units without changing its outline or hints. It repairs donor numeral transitions and makes superscripts accept every numeral form, including an inherited oldstyle form.

`tests/test_olebfont.py` checks all four serialized faces against all selected sources: outlines, widths, sidebearings, hint programs and subroutines, original ligature and kerning lookups, layout metrics, names, donor additions and repeatable bytes. HarfBuzz shapes all ten digits under each numeral style and superscripts, including feature combinations, plus small caps and original kerning/ligatures, and every pair of Latin letters with an added glyph, which must be positioned as Erewhon positions it. `make test-tex` checks OLEBFont’s margin protrusion, including the oldstyle figures that production's font features set in place of the mapped ones. The font build scripts and notices are included in image checks and publication provenance. Generated fonts and their licenses reside in `/usr/local/share/fonts/olebfont` inside the image. `make font-specimen` renders `tests/tex/olebfont-specimen.tex` to `dist/olebfont-specimen.pdf`, a manual XeLaTeX specimen for the numeral forms, four faces, small caps, note-origin spacing and added accents; review it alongside actual PTXprint sample and Bible pages.

## Linting and typing

Run `make lint` before submitting a change. It checks `src`, `scripts` and
`tests` with Black, isort and strict mypy, and checks the Makefile and Dockerfile
with mbake, dockerfmt and hadolint. CI runs the same target after bootstrap.

`make lint-fix` applies isort before Black and formats the Makefile and
Dockerfile. Mypy and hadolint findings require a manual fix. Both targets use
pinned container tools, run without networking, and write files as the invoking
user. Run `make bootstrap` first to build the toolchain and pull the two lint
images; subsequent lint runs use those local images.

Annotate every Python function, fixture and callback, including collection
elements and optional values. Keep JSON decision shapes in `policy_schema.py`
and USJ shapes in `usj.py`; these describe the existing dictionaries, tuples and
frozen mappings. Keep dynamic typing and casts at JSON or upstream-library
boundaries. Do not suppress type errors in first-party modules.

Rebuild with `make bootstrap` after formatting changes `Dockerfile`,
`requirements.txt`, or the font scripts: their copies in the image must match
the checkout before typesetting. Check that a second `make lint-fix` makes no
further changes.

## Updating dependencies

Renovate opens pull requests for the Python packages in `requirements.txt`, and for the Ubuntu base image and the PTXprint, usfmtc, and Utopia commits in the `Dockerfile`. The font archives in `sources/` are updated by hand. Each has a line in the `Dockerfile`'s `sha256sum` check and a line in `.dockerignore` that admits it. GFS Didot and Source Code Pro are extracted directly; Erewhon and Erewhon Math are consumed by the font assembler. The build refuses to run in an image made from a different `Dockerfile`, `requirements.txt`, font assembly script or notice, or font archive, so run `make bootstrap` after changing any of them.

`requirements.txt` lists only direct dependencies: what the build and tests import, what PTXprint needs at run time (including `psutil`, which it uses without declaring), and what's needed to build PTXprint and usfmtc. Those two are installed with `--no-deps`, because PTXprint's package metadata points at usfmtc's moving main branch instead of the pinned commit.

The base image is an Ubuntu LTS tag with no digest, and packages come from Ubuntu's live repositories. Rebuilding the image later can therefore bring in newer versions of TeX and fonts, which may change pagination. The provenance file lists the OS packages each PDF was built with, so a change in pagination can be traced to the package that caused it.

When upgrading PTXprint, check the places that depend on its internals, and that the sample's pagination still looks right:

- `config/protrusion.tex` wraps `\s@tfont`.
- `config/ptxprint-mods.tex` wraps `\startt@ble` to select the reference-table category before the table opens its group. Check the numbering and abbreviations tables in the PDF after upgrading.
- `config/ptxprint-mods.tex` builds the margin notes from PTXprint's private note macros (`\marginaln@te`, `\n@test@rt`, `\n@te@nd`, `\n@teid`, the `nm-cref-` and `nm-count-` names, the `note-no-insert-` hooks, `\p@ranotes`, `\NotStudyNotes`) and reads `\ch@pter`, `\ifhe@dings` and `\m@kechapterbox`. No test loads these apart from the build itself, so look at the notes in the sample: beside their verses in the margin, and at the foot of the page in the front matter and introductions.
- The `Dockerfile` patches two lines of PTXprint's `marginnotes.py`: notes on the same line of text keep the text's order, and a block of notes lifted in a crowded margin stays under the top of the page. The image build fails if either line has changed; drop each patch once PTXprint has the fix.
- `scripts/patch_margin_convergence.py` patches the pinned note convergence check: offset changes of at most one TeX scaled point (1/65536 pt) settle without another pass. The same tolerance applies only to note coordinates in the paragraph-position cache; note identities, pages and all other records still compare exactly. Larger changes still request a rerun; reaching the five-pass cap with an unsettled layout fails the build and records the reason in `ptxprint.log`. The guarded replacements fail on changed upstream code and must be reviewed on upgrades.

The build refuses a PDF in which a margin note overlaps the note before it, stands above it, or runs off the text block. PTXprint doesn't move the notes of an overfull margin to the foot of the page, so such a page has to be rebalanced by hand. When moving to a new Ubuntu release, which brings a new TeX Live, run `make test-tex`.

## Updating source texts

Replace a source archive only on purpose. Download the new one somewhere else first and compare it with the old one: the copyright notice, the list of books, chapter and verse labels, notes, italics, tables, and appendices. Then commit the new archive together with its updated `SOURCES` entry in `src/bible/sources.py` and the new retrieval date in `sources/README.md`.

## PTXprint quirks

A few things look odd but are on purpose:

- Brenton's `FRT` and `INT` files become `XXD` and `XXE`, and the King James `OTH` and `INT` become `TDX` and `NDX`. This keeps PTXprint from treating them as the edition's own front matter, and keeps the two sources' files from colliding.
- eBible's list of corrections contains literal `|` characters, which PTXprint would read as markup and use to discard text. `config/changes.txt` swaps them out while PTXprint parses the file and puts them back afterwards.
- BSB sets `fnomitcaller` to `True`, which in this PTXprint release means the footnote callers _are_ printed in the notes. Only Brenton's preface and the table of chapters and verses have callers now, which `layout.ini` numbers; the build checks that scripture has none.
- PTXprint's `canonicalise` option is off, so that it doesn't rewrite the source markup.
- PTXprint drops chapter markers outside scripture unless told to show them. `showxtrachapnums` keeps the chapter 1 that opens Brenton's appendix in eBible's text, which numbers nothing and prints nothing, because with it PTXprint sets the appendix's paragraphs flush left. Without the setting they would be indented, as the other introductions' paragraphs are.
- PTXprint loads GTK even when it runs without a display, which is why the image includes it.
- PTXprint's font configuration rejects OpenType files, which is how OLEBFont and the other fonts are installed. The `Dockerfile` adds a system fontconfig rule that accepts the fonts in `/usr/local/share/fonts`, which takes precedence.

## Outstanding editorial work

No correction to these cases is included in the accepted output:

- The 36 notes printed as “Heb. and Alex. Vat.”: the decisions' `witnesses` separately name Heb./Alex. support for the adopted wording and Vat. for the displaced wording, but their ambiguous printed form remains unchanged. Brenton supports the Hebrew/Vatican attribution; Swete confirms the reading from Codex Alexandrinus.
- The 56 retained decisions about Codex Alexandrinus carrying `todo` in `edition/alexandrinus.json`, individually listed and grouped in [the open notes](docs/notes-todo.md#readings-from-codex-alexandrinus-kept-for-later-work).
- The scope/italic questions, suspect references, misplaced/copied notes, transcription and spelling queries, English wording questions and optional historical-label note in [the open notes](docs/notes-todo.md).
- The personal-name expansions Lambert Bos, Charles Pridham and Abraham Trommius remain filed as source repairs; their editorial classification has not been reconsidered.
- Deuteronomy 24:13 retains the declared `ie.` source repair before final explanatory-label rendering; the recorded normalization round trip has not been corrected.

Editorial corrections require a separate decision, evidence, exact scope and a before/after comparison in `make review`. Do not infer new English or witness attribution from a formatting rule. Typeset and inspect anything that moves text.
