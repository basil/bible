# Maintaining the build

## Dependency upgrades

`dependencies.json` records the floating Ubuntu image tag, Python major/minor version, PTXprint repository/tag/commit, independent usfmtc commit, and reproducible timestamp. The Dockerfile uses `ubuntu:26.04` without a digest or dated package snapshot. `make bootstrap` uses `--pull`, so it retrieves the current image for that tag. OS packages are resolved from Ubuntu's current repositories when the installation layer is built. Use `make bootstrap` with Docker's cache cleared for this project when deliberately refreshing an otherwise cached package layer.

Python packages have ordinary version entries without hashes in the root `requirements.txt`. This includes `psutil`, which upstream imports without declaring it. Ubuntu 26.04 supplies Python 3.14, XeTeX, GTK, Fontconfig, PDF tools, and their transitive packages. Gentium Plus and Ezra SIL are installed from the current Ubuntu repositories. Each PDF provenance manifest contains `/etc/os-release`, the actual Python version, the complete installed OS package list, and font-file hashes. Charis still comes from the pinned PTXprint release.

For a dependency upgrade, edit `requirements.txt` or select and verify the intended upstream release commit, update the dependency lock and Dockerfile as needed, and rebuild the image. Never relax the PTXprint tag-to-commit check or use the moving usfmtc branch during a normal build. Run `make validate`, `make sample`, `make pdf`, and `make check`, then inspect the rendered sample pages and review pagination changes. Commit the reviewed dependency files and configuration together. No submodule initialization is required.

The Ubuntu base and repositories intentionally track updates. A later bootstrap is therefore not guaranteed to reproduce an earlier environment. `make check` verifies two clean renders within the same built image; provenance records which installed environment produced each PDF.

## Source updates

Download replacement archives deliberately to a temporary location. Retain the previous archive until reviewing the differences. Inspect the source notices, scripture unit set, chapter/verse labels, notes, references, italics, tables, and apparatus. Update the tracked archives, retrieval dates, URLs, SHA-256 values, and per-file inventories in `sources.json` together. Update the source statement date in `config/front.sfm`. A lock mismatch is a failure, not an invitation for a normal build to fetch newer data.

The inventory implementation lives in `scripts/source_inventory.py`. It stores exact string labels rather than coercing verses into integers: `1b`, `6a`, and source verse bridges are meaningful. A source upgrade must explicitly review any changed inventory instead of assuming a standard Protestant versification.

## Layout customization

Change `config/layout.ini` to override the upstream BSB configuration; do not edit generated `build/` files. Use `config/ptxprint-mods.sty` for style overrides, `config/ptxprint-mods.tex` for necessary TeX hooks, and `config/front.sfm` for title/source/contents pages. Change `config/edition.json` only when deliberately revising the edition's selection or order. A5 dimensions are an acceptance requirement and checked on every PDF page.

Diagnostics include the effective Paratext project and configuration, the actual PTXprint console/TeX logs, source comparison, PDF inspection outputs, contents and book-boundary records, and extracted PDF text. CI uploads these even when a render fails.
