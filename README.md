# Brenton-KJV Bible

An English Bible interior: eBible's Brenton Old Testament and Apocrypha (52 scripture units), then the 27 Cambridge Paragraph KJV New Testament books, with Brenton's historical apparatus and the Cambridge dedication, translators' preface, and NT closing notes. Original source archives, the ordered edition manifest, layout overrides, and dependency locks are kept here. There are no submodules.

Requires Docker, Make, Python 3, and approximately 5 GB free disk space. Python on the host is used only for source validation; rendering uses Ubuntu 26.04 and Python 3.14 inside the image.

```sh
make bootstrap  # network: pull the latest Ubuntu 26.04 image and build the environment
make validate   # offline: check original archives and their complete inventories
make sample     # offline: representative scripture, quotations, notes, and apparatus
make pdf        # offline: dist/bible.pdf and dist/bible.provenance.json
make check      # offline: two clean full builds, then compare every rendered page
```

The local build image is named `brenton-kjv-bible:local`. The base image uses the floating `ubuntu:26.04` tag, and bootstrap passes `--pull`. Ubuntu packages come from the current repositories. Python dependencies are listed in root-level `requirements.txt` with versions and no hashes; PTXprint, usfmtc, and Bible source snapshots retain their existing pins. Rebuilding the environment later can change OS packages and pagination; repeatability is checked within the built environment.

The reading order is the new title/source/contents pages; Brenton's abbreviations and 1870 introduction; the KJV dedication and translators' preface; Old Testament; Apocrypha; New Testament; then Brenton's historical appendices. Cambridge closing notes remain with their NT books. The historical Cambridge title page is omitted.

The sample selects the chapters listed in `config/sample.json` and retains the complete apparatus to exercise quotations, tables, and unusual numbering. Outputs and logs are in `dist/` and `build/`; neither is tracked. `make clean` deletes those generated directories. Normal builds never download Bible texts. Docker rendering runs with `--network none` and the invoking user's UID/GID.

The layout is derived at build time from PTXprint 3.0.43's `resources/bsb.zip`: A5, two columns, 9.5-point Charis, its line spacing, margins, column rule, and running headers. This edition replaces BSB publication metadata, adds front matter and section dividers, enables contents, and displays note callers and verse 1. Continuous Arabic pagination includes the front matter. No cover, printer imposition, or historical facsimile pagination is provided.

See [edition and source findings](docs/edition.md), [maintenance](docs/maintenance.md), and [verification](docs/verification.md), and the [visual inspection record](docs/inspection.md). Source notices remain inside the original archives and are also saved under `sources/`.
