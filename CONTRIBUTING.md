# Contributing

This file covers the technical side of the project: how the build works, what it needs, and where things live. For an overview of the edition itself, see [README.md](README.md).

## Requirements

- Docker with the Compose plugin
- Make
- Approximately 5 GB of free disk space

Every build step runs inside a Docker image based on the Ubuntu LTS release named in the `Dockerfile`, with its system Python, so the host needs no Python.

## Build targets

```sh
make bootstrap  # network: pull the latest image for the Ubuntu LTS tag and build the environment
make validate   # offline: check original archives and their complete inventories
make test       # offline: run the pytest and l3build test suites (test-python, test-tex)
make sample     # offline: representative scripture, quotations, notes, and apparatus
make pdf        # offline: dist/bible.pdf and dist/bible.provenance.json
make check      # offline: the tests, then two clean full builds, comparing every rendered page
make clean      # delete the generated build/ and dist/ directories
```

The `toolchain` service in `compose.yaml` defines the local build image, named `brenton-kjv-bible:local`, and runs it without network access. Make runs the validation, rendering, and check commands in that service as the invoking user's UID/GID; `bootstrap` builds the image and `clean` runs on the host. If the image is missing, Compose builds it on first use, with network access and without `--pull`, so run `make bootstrap` first. Normal builds never download Bible texts; they read only the archives committed under `sources/`.

The tests live under `tests/`: pytest tests of the edition's editorial policy, the text helpers, and the build's guards, configured in `pyproject.toml`, and an l3build regression test of the TeX protrusion customization, configured in `build.lua`. To run a subset, pass arguments through the toolchain service, for example `docker compose -f compose.yaml run --rm --user "$(id -u):$(id -g)" toolchain python3 -m pytest -k marginal`. After an intended change to the protrusion output, regenerate its expected log with `docker compose -f compose.yaml run --rm --user "$(id -u):$(id -g)" toolchain l3build save protrusion` and review the diff. [docs/verification.md](docs/verification.md) describes what each check covers.

The sample selects the chapters listed in `config/sample.json` and retains the complete apparatus so that quotations, tables, and unusual verse numbering are exercised. Outputs and logs go to `dist/` and `build/`; neither is tracked.

## Sources

- `sources/eng-Brenton_usfm.zip`: eBible's Brenton Old Testament and Apocrypha (52 scripture units) with Brenton's historical apparatus
- `sources/engkjvcpb_usfm.zip`: eBible's Cambridge Paragraph KJV, of which the 27 New Testament books, the dedication, the translators' preface, and the NT closing notes are used
- `sources/exhaustive-listing-marginal-notes-1611-edition-king-james-bible.md`: Calvin George's transcription of the 1611 KJV marginal notes, of which only the 775 New Testament notes are read
- `sources.json`: SHA-256 hashes, archive member lists, and chapter/verse/marker inventories for both archives, and the SHA-256 hash of the marginal notes
- `sources/README.md`: retrieval dates, original URLs, and saved copyright notices

A hash mismatch is a failure. Replacing an archive is a deliberate step described in [docs/maintenance.md](docs/maintenance.md).

## Configuration

- `config/edition.json`: the ordered manifest of scripture units and peripherals
- `config/front.sfm`: title page and contents
- `config/introduction.sfm`: the editor's introduction, typeset as the first unit after the contents
- `config/layout.ini`: overrides applied on top of PTXprint's BSB layout
- `config/ptxprint-mods.sty`: style overrides
- `config/ptxprint-mods.tex`: TeX customizations
- `config/marginal-notes.json`: book names, anchors, and corrections for the 1611 New Testament marginal notes
- `config/sample.json`: chapters included in the sample build
- `config/render-witnesses.json`: phrases from unusual content (Psalm 151, the Greek additions to Esther and Daniel, and so on) that must appear in the rendered PDF

The layout is derived at build time from PTXprint 3.0.43's `resources/bsb.zip`, including both its configuration and `ptxprint.sty`: A5, two columns, 9.5-point text, its line spacing, margins, column rule, running headers, and heading/reference spacing. This edition replaces Charis with Utopia, replaces the BSB publication metadata, adds front matter and section dividers, and enables the contents page. Verse-one settings and footnote callers are inherited from BSB; cross-references have their own caller symbols. Pagination is continuous Arabic numerals and includes the front matter.

The reading order is the new title page, contents, and editor's introduction; the Old Testament divider, Brenton's preface, introduction, introduction to the Apocrypha, and list of abbreviations, and the Old Testament; the New Testament divider, the KJV dedication and translators' preface, and the New Testament; then the appendices (Brenton's Jeremias table, his notes and supplied passages, and eBible's corrections). Cambridge closing notes remain with their NT books. The historical Cambridge title page is omitted. Details and the reasoning are in [docs/edition.md](docs/edition.md).

## Dependencies

`dependencies.json` records the base image tag, PTXprint tag and commit, and usfmtc commit. PTXprint 3.0.43 records the build time in the PDF's creation and modification dates, so PDF bytes differ between builds; `make check` compares rendered page images instead. Direct Python dependencies, including pytest, are pinned by version, without hashes, in `requirements.txt`; pip resolves their own dependencies. Renovate proposes updates to that file.

The base image uses an Ubuntu LTS codename tag, which floats within that release and which Renovate moves to each new LTS, and `make bootstrap` passes `--pull`, so OS packages come from Ubuntu's current repositories. Rebuilding the environment later can change OS packages and therefore pagination. Repeatability is checked within a single built environment by `make check`, and each PDF's provenance file records the exact environment that produced it.

Upgrade procedure, source updates, and layout customization are covered in [docs/maintenance.md](docs/maintenance.md). Acceptance checks are in [docs/verification.md](docs/verification.md).

## Continuous integration

`.github/workflows/build.yml` runs bootstrap, validate, test, and pdf on pushes to `master` and on pull requests. It does not run `make sample` or the full `make check` repeatability build; run those locally before submitting. On `master` it also publishes `site/index.html` and `dist/bible.pdf` to GitHub Pages.

## Submitting changes

1. Run `make validate`, `make test`, `make sample`, `make pdf`, and `make check` locally.
2. Inspect the rendered sample pages and review any pagination changes.
3. Commit configuration, dependency, and source changes together with the reasoning in the commit message.
4. Open a pull request. CI must pass before merging.
