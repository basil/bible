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

`edition/versification.json` lists every verse of the Old Testament that doesn't keep its number in the King James Bible, in runs. Each run says what it rests on as `by`: `table`, STEP Bible's account of a Bible numbered like this one; `words`, the words the two translations share; `place`, its place between verses that the words fix; or `reading`, the editor's reading of both, which gives its reason as `why`. A verse the file doesn't list keeps its number, unless Brenton letters it. The tests hold each run to its witness, and check that every verse of both Bibles has a place.

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
- `config/ptxprint-mods.tex` holds TeX-level changes: hyphenation and protrusion.

The tests require every setting in `layout.ini` and `ptxprint-mods.sty` to differ from the value it overrides, and a checkbox PTXprint stores under several keys to be set under all of them.

Don't edit anything in `build/`; it's regenerated on every run.

PTXprint uses plain XeTeX, so the microtype package isn't available. Instead, `config/ptxprint-mods.tex` carries a copy of microtype's default protrusion table, which lets punctuation and a few letters hang slightly into the margin so the column edges look straight. Protrusion affects line breaking, so changing it can change pagination. microtype has no settings made for Utopia, GFS Didot, or Ezra SIL, so all three use the defaults.

Run `make test-tex` after changing the table. If the change was intended, save the new expected output with `make test-tex-save` and review the diff.

## Updating dependencies

Renovate opens pull requests for the Python packages in `requirements.txt`, and for the Ubuntu base image and the PTXprint, usfmtc, and Utopia commits in the `Dockerfile`. The font archives in `sources/` are updated by hand. Each has a line in the `Dockerfile`'s `sha256sum` check, an `unzip` line there that says which of its files to install, and a line in `.dockerignore` that admits it. The build refuses to run in an image made from a different `Dockerfile`, `requirements.txt`, or font archive, so run `make bootstrap` after changing any of them.

`requirements.txt` lists only direct dependencies: what the build and tests import, what PTXprint needs at run time (including `psutil`, which it uses without declaring), and what's needed to build PTXprint and usfmtc. Those two are installed with `--no-deps`, because PTXprint's package metadata points at usfmtc's moving main branch instead of the pinned commit.

The base image is an Ubuntu LTS tag with no digest, and packages come from Ubuntu's live repositories. Rebuilding the image later can therefore bring in newer versions of TeX and fonts, which may change pagination. The provenance file lists the OS packages each PDF was built with, so a change in pagination can be traced to the package that caused it.

When upgrading PTXprint, check that the `\s@tfont` wrapper in `config/ptxprint-mods.tex` still matches PTXprint's internals, and that the sample's pagination still looks right. When moving to a new Ubuntu release, which brings a new TeX Live, run `make test-tex`.

## Updating source texts

Replace a source archive only on purpose. Download the new one somewhere else first and compare it with the old one: the copyright notice, the list of books, chapter and verse labels, notes, italics, tables, and appendices. Then commit the new archive together with its updated `SOURCES` entry in `src/bible/sources.py` and the new retrieval date in `sources/README.md`.

## PTXprint quirks

A few things look odd but are on purpose:

- Brenton's `FRT` and `INT` files become `XXD` and `XXE`, and the King James `OTH` and `INT` become `TDX` and `NDX`. This keeps PTXprint from treating them as the edition's own front matter, and keeps the two sources' files from colliding.
- eBible's list of corrections contains literal `|` characters, which PTXprint would read as markup and use to discard text. `config/changes.txt` swaps them out while PTXprint parses the file and puts them back afterwards.
- BSB sets `fnomitcaller` to `True`, which in this PTXprint release means the footnote callers *are* printed in the notes. Only Brenton's preface has callers now; the build checks that this still holds.
- PTXprint's `canonicalise` option is off, so that it doesn't rewrite the source markup.
- PTXprint loads GTK even when it runs without a display, which is why the image includes it.
- PTXprint's font configuration rejects OpenType files, which is how Utopia and the other fonts are installed. The `Dockerfile` adds a system fontconfig rule that accepts the fonts in `/usr/local/share/fonts`, which takes precedence.
