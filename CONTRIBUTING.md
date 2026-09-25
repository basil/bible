# Contributing

This file covers the technical side of the project: how the build works, what it needs, and where things live. For an overview of the edition itself, see [README.md](README.md).

## Requirements

- Docker
- Make
- Python 3 on the host, used only for source validation
- Approximately 5 GB of free disk space

Rendering happens inside a Docker image based on Ubuntu 26.04 with Python 3.14. The host Python version does not affect the output.

## Build targets

```sh
make bootstrap  # network: pull the latest Ubuntu 26.04 image and build the environment
make validate   # offline: check original archives and their complete inventories
make sample     # offline: representative scripture, quotations, notes, and apparatus
make pdf        # offline: dist/bible.pdf and dist/bible.provenance.json
make check      # offline: two clean full builds, then compare every rendered page
make clean      # delete the generated build/ and dist/ directories
```

The local build image is named `brenton-kjv-bible:local`. Docker rendering runs with `--network none` and the invoking user's UID/GID. Normal builds never download Bible texts; they read only the archives committed under `sources/`.

The sample selects the chapters listed in `config/sample.json` and retains the complete apparatus so that quotations, tables, and unusual verse numbering are exercised. Outputs and logs go to `dist/` and `build/`; neither is tracked.

## Sources

- `sources/eng-Brenton_usfm.zip`: eBible's Brenton Old Testament and Apocrypha (52 scripture units) with Brenton's historical apparatus
- `sources/engkjvcpb_usfm.zip`: eBible's Cambridge Paragraph KJV, of which the 27 New Testament books, the dedication, the translators' preface, and the NT closing notes are used
- `sources.json`: SHA-256 hashes, archive member lists, and chapter/verse/marker inventories for both archives
- `sources/README.md`: retrieval dates, original URLs, and saved copyright notices

A hash mismatch is a failure. Replacing an archive is a deliberate step described in [docs/maintenance.md](docs/maintenance.md).

## Configuration

- `config/edition.json`: the ordered manifest of scripture units and peripherals
- `config/front.sfm`: title page and contents
- `config/introduction.sfm`: the editor's introduction, typeset as the first unit after the contents
- `config/layout.ini`: overrides applied on top of PTXprint's BSB layout
- `config/ptxprint-mods.sty`: style overrides
- `config/ptxprint-mods.tex`: TeX customizations
- `config/sample.json`: chapters included in the sample build
- `config/render-witnesses.json`: phrases from unusual content (Psalm 151, the Greek additions to Esther and Daniel, and so on) that must appear in the rendered PDF

The layout is derived at build time from PTXprint 3.0.43's `resources/bsb.zip`, including both its configuration and `ptxprint.sty`: A5, two columns, 9.5-point text, its line spacing, margins, column rule, running headers, and heading/reference spacing. This edition replaces Charis with Utopia, replaces the BSB publication metadata, adds front matter and section dividers, and enables the contents page. Note-caller and verse-one settings are inherited from BSB. Pagination is continuous Arabic numerals and includes the front matter.

The reading order is the new title page, contents, and editor's introduction; the Old Testament divider, Brenton's preface, introduction, introduction to the Apocrypha, and list of abbreviations, and the Old Testament; the New Testament divider, the KJV dedication and translators' preface, and the New Testament; then the appendices (Brenton's Jeremiah table, his notes and supplied passages, and eBible's corrections). Cambridge closing notes remain with their NT books. The historical Cambridge title page is omitted. Details and the reasoning are in [docs/edition.md](docs/edition.md).

## Dependencies

`dependencies.json` records the base image tag, Python version, PTXprint tag and commit, usfmtc commit, and the reproducible timestamp. Python packages are pinned by version, without hashes, in `requirements.txt`. Dependabot proposes updates to that file.

The base image uses the floating `ubuntu:26.04` tag, and `make bootstrap` passes `--pull`, so OS packages come from Ubuntu's current repositories. Rebuilding the environment later can change OS packages and therefore pagination. Repeatability is checked within a single built environment by `make check`, and each PDF's provenance file records the exact environment that produced it.

Upgrade procedure, source updates, and layout customization are covered in [docs/maintenance.md](docs/maintenance.md). Acceptance checks are in [docs/verification.md](docs/verification.md).

## Continuous integration

`.github/workflows/build.yml` runs bootstrap, validate, sample, pdf, and check on every push and pull request. On `master` it also publishes `site/index.html` and `dist/bible.pdf` to GitHub Pages.

## Submitting changes

1. Run `make validate`, `make sample`, `make pdf`, and `make check` locally.
2. Inspect the rendered sample pages and review any pagination changes.
3. Commit configuration, dependency, and source changes together with the reasoning in the commit message.
4. Open a pull request. CI must pass before merging.
