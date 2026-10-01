# Contributing

This covers building the PDF, how the build checks itself, and how to change things. For what the edition contains, see the [README](README.md). For the reasons behind its choices, see the [editorial notes](docs/edition.md).

## Building

You need Docker with the Compose plugin, Make, and about 5 GB of disk space. Everything runs in a container, so you don't need Python or TeX on your machine.

```sh
make bootstrap  # build the container image (the only step that uses the network)
make pdf        # build dist/bible.pdf
```

Run `make bootstrap` first. The other targets run with networking turned off and read the texts only from the archives committed in `sources/`:

```sh
make sample     # a short PDF of selected chapters, for checking layout quickly
make validate   # check the source archives against their recorded hashes
make alexandrinus-review  # review Alexandrine readings and their Swete evidence
make notes-review  # list every note with the words it's about and its italics
make seed-versification  # propose where each verse stands in the King James Bible
make test       # run the tests
make clean      # delete build/ and dist/
```

Alongside the PDF, the build writes `dist/bible.provenance.json`, which records the environment that produced it: the OS release, installed packages, Python version, and font hashes. Logs and intermediate files go to `build/`. The most useful of these is `build/pdf/transformations.json` (or `build/sample/…`), which lists every change the build made to the source text.

The sample prints the chapters listed in `edition/sample.json`. They were picked to cover the awkward cases, such as Psalm 151, the additions to Esther and Daniel, the Ezra–Nehemiah split, the end of Malachias, quoted Greek and Hebrew, and pages crowded with notes.

## Where things are

- `sources/`: the Bible texts, the 1611 marginal notes, and the fonts, committed as downloaded. [sources/README.md](sources/README.md) says where each came from.
- `content/`: the edition's own pages: the introduction, the table of chapters and verses (`numbering.sfm`), and the three divider pages (`old-testament.sfm`, `new-testament.sfm`, `appendices.sfm`). The title page isn't among them: PTXprint's template prints it from the title and subtitle in `config/layout.ini`. The dividers' subtitles repeat the title page's wording. A page names a passage between braces, by its code, and the build prints it; `numbering.sfm` also says where its tables go, which the build writes.
- `config/`: PTXprint's configuration. `layout.ini`, `ptxprint-mods.sty`, and `ptxprint-mods.tex` hold layout, style, and TeX changes on top of PTXprint's layout for the Berean Standard Bible (BSB), and `changes.txt` holds its text substitutions.
- `edition/`: the build's own settings, which PTXprint never reads:
  - `manifest.json`: which books are printed, in what order, and what they're called and how their headings break into lines.
  - `kjv-notes.json`: placements and corrections for the 1611 New Testament notes.
  - `alexandrinus.json`: explicit Alexandrine replacements, Appendix insertions, retained readings, and the Swete evidence for every decision.
  - `brenton-notes.json`: corrections to the words and italics the build works out for Brenton's notes, and to a few slips in eBible's text.
  - `book-introductions.json`: which paragraphs of the introduction to the Apocrypha stay at the front and which introduce each book as a footnote, with the editorial glosses, book-name changes, and their reasons.
  - `abbreviations.json`: the rows that complete Brenton's list of abbreviations, and the editor's decisions on the abbreviations printed in full and the numbers that lose their period.
  - `citations.json`: how each source writes its citations (its names for the books, its numerals and stops, and the numbering it cites by); which way each piece of front and back matter writes them; the editor's decisions on the citations that the grammar can't read, or reads by the wrong numbering; and the names that are changed where a book is named but not cited.
  - `versification.json`: where each verse of the Old Testament stands in the King James Bible, the verses the edition relabels, and what the King James Bible sets apart in its Apocrypha.
  - `sample.json`: the chapters the sample prints.
  - `witnesses.json`: phrases that must appear in the finished PDF, to catch unusual passages going missing.
- `Dockerfile`: the tool image, with the pinned PTXprint, usfmtc, and Utopia commits and the hashes of the font archives.
- `src/bible/`: the build, a Python package run as `python3 -m bible`. It has one module per stage, in the order the build runs them:
  - `sources.py`: the pinned Bible texts and their hashes; `edition.py`: the manifest; `notes.py`: the notes of both testaments, set as footnotes without callers; `introductions.py`: the introduction to the Apocrypha, divided between its front matter and footnotes on the books. `validate.py` checks them against each other.
  - `prepare.py` and `typography.py`: each book as the edition prints it, checked against its source.
  - `project.py`: the PTXprint project; `typeset.py`: running PTXprint in the image that `toolchain.py` checks.
  - `verify.py`: the checks on PTXprint's output and the PDF; `publish.py`: the copy in `dist/` and its provenance.
  - `cli.py` chains the stages, and `usfm.py` holds the text helpers they share. `numbering.py` writes the table of chapters and verses and prints the passages that the edition's own pages name. `references.py` holds a verse and a passage, as the files write them and the pages print them, `versification.py` the numberings they are written in, and `citations.py` reads the citations in the notes as each source writes them. `abbreviations.py` completes Brenton's list of abbreviations and, last, prints the abbreviations in the notes and the front and back matter as The Chicago Manual of Style does.
  - `seed.py` proposes `edition/versification.json` from two witnesses: STEP Bible's table (`tvtms.py`) and the words of both translations (`alignment.py`). The build never reads what it proposes.
- `pyproject.toml`: pytest's settings. The Python dependencies are pinned in `requirements.txt`.
- `tests/`: the pytest tests, named after the modules they test, and the TeX protrusion test.

## Checks

The build checks its own work and stops rather than produce a PDF from bad input.

- **First**, it checks the hash of every source archive. Replacing a source is a deliberate step (see below), never something a build does on its own.
- **While preparing the text**, it compares each book it changes against the original. Apart from the intended changes, every word, punctuation mark, verse, note, and piece of markup must come through intact. PTXprint's own preprocessing is checked the same way. It reads every citation, in the notes and in the front and back matter, and stops at one that it can't read or that names a verse the edition doesn't print. It stops as well at an abbreviation left in a source's form, at a number left with its period within a note's sentence, and at a decision in `edition/abbreviations.json` that it doesn't meet exactly once.
- **After typesetting**, it checks the PDF: every page is A5, all fonts are embedded, no glyphs are missing, the contents list every book once with the right page numbers, each phrase in `edition/witnesses.json` is there, and nothing on its pages cites as a source writes ("Rom. 4. 7") instead of as the edition prints ("Romans 4:7").

`make test` runs two suites. The pytest suite in `tests/` is organized by module: `test_usfm.py` tests `src/bible/usfm.py`, and so on, and `test_config.py` tests `config/`. Besides the editorial rules (book order, titles, and headings) and the text helpers, it tests the build's own checks by breaking one input at a time and making sure the build refuses it. It prepares every book but typesets nothing, so it takes seconds. The [l3build](https://ctan.org/pkg/l3build) test in `tests/tex/` compares the protrusion settings (see below) against real microtype.

To run only some of the tests, pass pytest's options through `PYTEST_ARGS`:

```sh
make test-python PYTEST_ARGS="-k marginal"
```

### Looking at the pages

The checks catch missing text, not bad pages. After any change that could move text around, read through the sample, and the full PDF if the page count changed. The places most likely to go wrong are:

- pages crowded with footnotes, and whether each note falls on the page with its verse
- the New Testament marginal notes, including the Greek in Acts 13:18 and 13:34
- Greek and right-to-left Hebrew in Brenton's notes
- poetry in the Psalms
- the contents and the table of chapters and verses
- the joins between 2 Esdras and Nehemias and between Malachias 3 and 4, and the additions to Daniel
- the opening pages of each testament and of the appendices

### Reviewing the Alexandrine readings

`edition/alexandrinus.json` declares every promoted reading with exact source words, replacement words, and its reason. Appendix decisions identify the exact paragraph removed and the verses or additions placed in the book. The declared KJV source for 1 Kingdoms 23:12 is checked verbatim against the pinned archive; its English is not edited. Punctuation in a neighbouring verse is declared in an additional `edits` entry with its exact `target`, `from`, and `english` derivation. A reading’s `note_edits` declares an exact `key`, `from`, `to`, `lemma`, and `why` for any surviving note whose attribution must change. Surviving notes within replaced passages keep their original lemma and narrower gloss, anchored to unique complete words rather than character offsets; an ambiguous anchor fails the build. Every decision, including those kept as notes, records Swete’s volume, printed page, Greek reading, evidence type, agreement, with any qualifications explained in the decision’s `why`. Words supplied by the editor must be listed explicitly.

Run `make alexandrinus-review` after changing a decision or the stage. Read every before and after passage with its neighbours, the printed footnote, and the Swete record in `build/alexandrinus-review.md`; later runs also write `build/alexandrinus-review-changes.md`. Check grammar, punctuation, names, numbers, conjunctions, and the words identified by each note. Run `make notes-review` to inspect the resulting footnotes. Consult the page image whenever Swete changes the placement or interpretation. A recorded `agrees: true` does not by itself settle the English or insertion point. Proceed when Swete gives an unambiguous position and Brenton supplies the English without substantive rewriting; record corrected and marginal manuscript readings in the editorial evidence. Label displaced Vatican readings “Vat.”; record any uncertainty about their attribution in the decision and todo. Keep a doubtful reading as a note or Appendix passage with its reason and a todo, rather than supply an unresolved English reconstruction.

Each keyed source note is stored once in full and must match the corrected text from the pinned Brenton archive exactly: `source_note` for a reading or retained note, and `source_notes` keyed by identity for notes consumed by an Appendix passage. Those keys also declare which notes the passage consumes; its book comes from the decision key. Every replacement and non-KJV inserted verse has its own `english` derivation. `source` selects the Brenton note/Appendix (`brenton`) or the unchanged scripture span (`from`); an optional `span: [start, end]` selects a zero-based, half-open character range, otherwise the whole source is used. Ordered, non-overlapping `edits` each select a `span` within that phrase and give its replacement `to`; equal start and end declare an insertion. An edit’s optional `why` overrides the operation or decision’s reason. The build derives the final wording, source excerpts, and edited source strings from these declarations; they are not stored again as replacement `to`, verse `text`, or derivation `text` and edit `from`. An optional `note_at` gives the caller’s character offset in the derived replacement. A whole-verse omission can declare `omit_verse: true` and a `note_target` naming the preceding verse: the build removes the empty verse label, attaches the omission note to the end of that verse, and updates the printed inventory. A retained decision may supply an edited `note` while its pinned `source_note` stays unchanged. `kjv: true` borrows the decision key’s verse verbatim from the pinned Authorized Version archive, without copying its text into JSON. Spelling, punctuation, whitespace, word order, repeated words, and supplied-word markup therefore cannot change without a declared edit. Omission decisions start from the scripture span and declare the deletion; their pinned source note supplies Brenton’s instruction. The vocabulary check remains an additional guard, not the proof of provenance. Expanded derivations and final wording appear in the Alexandrine review and transformation log. The existing editorial decisions are preserved in these declarations; the checks do not independently verify their interpretation of Swete.

The build requires complete coverage of Alexandrine notes and Appendix passages, exact matches for declared changes, a Swete record for each decision, and preservation of words outside the declared spans. It records the operation as “print the Alexandrine reading” in `transformations.json`. `alexandrinus.py` applies this stage after Brenton’s source corrections and before note styling, links, and typography.

### Reviewing the notes

The build works out which words each note is about, and which of its words are italic, by rule; `edition/brenton-notes.json` and `edition/kjv-notes.json` correct the rules where they go wrong. After changing `src/bible/notes.py` or either file, run `make notes-review` and read `build/notes-review-changes.md`, which lists every note whose words or italics changed since the last review. A correction the rules no longer need fails the build, so remove it. A correction to eBible's text is keyed by its verse. If it changes a note, the bare verse key means the first note; `#2` means the second, `#3` the third, as in the note exceptions. Put several corrections to one note in a list under that note's key. In a file without verses, such as the preface, a correction to a note is keyed by the words the note stands among, and one outside the notes by the words it mends. The build fails if the source text is not found once, in that place. Outside a note, a correction may mend only word spaces in the translation, a book's verses or a passage the appendix supplies, so that its wording stays eBible's; the words of a preface, an introduction, or the appendix's notes and labels may be mended. Every entry in either file gives its reason as `why`. Each correction, and each anchor that differs from George's lemma, must also fit one of the kinds of slip that `src/bible/notes.py` defines (a missing word space, a stray letter, a bracketed remark, and so on), or be marked `"uncategorized": true`.

### Reviewing the citations

A citation that the build can't read stops it, and names the note or the unit and the words: `Citation that can't be read: ISA 34:11 (13. 22)`. So does one that names what the edition doesn't print, which is usually a citation by another numbering. Read the note, and the verse it means, and add a decision to `edition/citations.json` with its reason as `why`:

- `numbering` reads the citation by another numbering than its source's: `kjv`, the King James Bible's; `hebrew`, for a psalm by the Hebrew's number; or `kjv-verses`, for Brenton's chapter with the King James Bible's verse. The edition's numbers are worked out from `edition/versification.json`.
- `passages` and `print` say what is cited and what prints, where the grammar can't: `print` names a book by its code between braces, as `{PSA} 41:5`, so that the edition's name for it prints.
- `unprinted` and `print` are for a citation of what the edition doesn't print, as a verse that the Vatican text lacks. It stays among the note's words.
- `not_a_citation` is for figures that only look like one.

A decision on a note is keyed as the note is. One on front or back matter is keyed by the unit and the words it decides, as `XXB Psalm iv. 4`. A name for a book that a source uses, and the dialects don't have, goes under the source's dialect. A decision that nothing meets, or a name that nothing uses, stops the build, so remove it.

### Reviewing the numbering

`edition/versification.json` lists every verse of the Old Testament that doesn't keep its number in the King James Bible, in runs. Each run says what it rests on as `by`: `table`, STEP Bible's account of a Bible numbered like this one; `words`, the words the two translations share; `place`, its place between verses that the words fix; or `reading`, the editor's reading of both, which gives its reason as `why`. Equal-length runs normally pair verse for verse. An optional `pairs` object gives each edition verse's exact King James passage where only part of a verse overlaps another; its keys and targets must cover exactly the declared run. A verse the file doesn't list keeps its number, unless Brenton letters it. The tests hold each run to its witness, and check that every verse of both Bibles has a place.

`make seed-versification` hears the witnesses again and writes what they propose to `build/versification-seed.json`, what differs from the file to `build/versification-changes.md`, and the runs that rest on words or place alone, with both translations' words, to `build/versification-to-read.md`. What has been read stands, whatever they propose. To correct a run, read both translations, and write it into the file as a `reading`.

## Submitting changes

1. Run `make sample` and `make test`.
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

OLEBFont is the edition’s combined Latin family. `scripts/build_olebfont.py` runs after the pinned Utopia conversion and pairs regular, italic, bold and bold italic with their Erewhon counterparts. Utopia wins overlapping glyphs and character mappings, with one exception: Unicode superscript 1, 2 and 3 use Erewhon’s outlines, widths and hint dictionary so they match the rest of the superscript figures. The assembler copies CFF charstrings and local subroutines into separate CID font dictionaries, preserving source hints and width defaults rather than redrawing outlines. It refuses unsupported global subroutines or seac composites; the pinned sources use neither. It retains Utopia’s layout metrics and expands clipping bounds for added glyphs.

Native PTXprint font settings enable `onum` and `pnum` on all four faces, so chapter figures, headings, notes, front matter and contents inherit proportional oldstyle numbers. The stylesheet selects `sups` for verses and note origins, and `smcp`/`c2sc` for running furniture. These settings preserve the nominal sizes, zero extra superscript raise and fixed 1 pt origin gap. No content digits are rewritten. Native `\XeTeXgenerateactualtext=1` records the input Unicode as PDF ActualText, preserving copy/search for CID glyph alternates that would otherwise extract as private-use codes or disappear. The assembler corrects Erewhon Italic’s tabular oldstyle zero advance from 498 to 500 units without changing its outline or hints. It repairs donor numeral transitions and makes superscripts accept every numeral form, including an inherited oldstyle form.

`tests/test_olebfont.py` checks all four serialized faces against both sources: outlines, widths, sidebearings, hint programs and subroutines, original ligature and kerning lookups, layout metrics, names, donor additions and repeatable bytes. HarfBuzz shapes all ten digits under each numeral style and superscripts, including feature combinations, plus small caps and original kerning/ligatures, and every pair of Latin letters with an added glyph, which must be positioned as Erewhon positions it. `make test-tex` checks OLEBFont’s margin protrusion, including the oldstyle figures that production's font features set in place of the mapped ones. The font build scripts and notices are included in image checks and publication provenance. Generated fonts and their licenses reside in `/usr/local/share/fonts/olebfont` inside the image. `make font-specimen` renders `tests/tex/olebfont-specimen.tex` to `dist/olebfont-specimen.pdf`, a manual XeLaTeX specimen for the numeral forms, four faces, small caps, note-origin spacing and added accents; review it alongside actual PTXprint sample and Bible pages.

## Updating dependencies

Renovate opens pull requests for the Python packages in `requirements.txt`, and for the Ubuntu base image and the PTXprint, usfmtc, and Utopia commits in the `Dockerfile`. The font archives in `sources/` are updated by hand. Each has a line in the `Dockerfile`'s `sha256sum` check and a line in `.dockerignore` that admits it. GFS Didot and Source Code Pro are extracted directly; Erewhon is consumed by the font assembler. The build refuses to run in an image made from a different `Dockerfile`, `requirements.txt`, font assembly script or notice, or font archive, so run `make bootstrap` after changing any of them.

`requirements.txt` lists only direct dependencies: what the build and tests import, what PTXprint needs at run time (including `psutil`, which it uses without declaring), and what's needed to build PTXprint and usfmtc. Those two are installed with `--no-deps`, because PTXprint's package metadata points at usfmtc's moving main branch instead of the pinned commit.

The base image is an Ubuntu LTS tag with no digest, and packages come from Ubuntu's live repositories. Rebuilding the image later can therefore bring in newer versions of TeX and fonts, which may change pagination. The provenance file lists the OS packages each PDF was built with, so a change in pagination can be traced to the package that caused it.

When upgrading PTXprint, check the places that depend on its internals, and that the sample's pagination still looks right:

- `config/protrusion.tex` wraps `\s@tfont`.
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
- BSB sets `fnomitcaller` to `True`, which in this PTXprint release means the footnote callers *are* printed in the notes. Only Brenton's preface has callers now; the build checks that this still holds.
- PTXprint's `canonicalise` option is off, so that it doesn't rewrite the source markup.
- PTXprint loads GTK even when it runs without a display, which is why the image includes it.
- PTXprint's font configuration rejects OpenType files, which is how OLEBFont and the other fonts are installed. The `Dockerfile` adds a system fontconfig rule that accepts the fonts in `/usr/local/share/fonts`, which takes precedence.
