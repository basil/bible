# Inspection record -- 2026-09-23

The complete interior rendered to 1,584 A5 pages. Automated checks verified all 79 scripture units plus the Brenton apparatus, Cambridge dedication and translators' preface, and new dividers in order, converged contents with actual PDF book-heading pages, embedded Charis/Gentium Plus/Ezra SIL, and no missing-glyph or fatal TeX errors. The 100-page sample is explicitly labelled as a typesetting sample.

The complete source-to-typesetter comparison retained 36,573 scripture verse labels, 2,596 scripture footnotes, 150 cross-references, and 14,654 added-word spans; the four additional preface footnotes and all apparatus tables were checked as well. The empty reference-only note in 1 Kings 6:1 remains present.

Representative pages were rendered and visually inspected:

| PDF page | Inspection |
| --- | --- |
| 3 | Contents, long leaders, and page alignment |
| 15-18, 34 | Brenton introduction ending; complete dedication immediately after it; translators' preface opening and ending |
| 47, 438 | Notes and matching callers; Greek/Hebrew notes; reference-only footnote |
| 612 | Esther opening additions and lettered verse labels |
| 733 | Psalm 151, title, seven verse labels, and footnote |
| 967 | Daniel's expanded chapter 3 and preserved source numbering |
| 1040 | Apocrypha divider |
| 1237 | Complete Prayer of Manasses |
| 1269-1270 | NT divider and Matthew opening, paragraphing and ordinary added-word italics |
| 1562-1563 | Historical-apparatus divider and Jeremiah table with its long title |
| 1571 | Errata, including text and Greek quotations after literal vertical bars |
| 1579 | Appendix, Greek quotations and right-to-left Hebrew |

The sample's pages 73, 75, and 76 were also inspected for the Acts closing line and Romans/Hebrews subscriptions. All 14 epistle subscriptions are checked against the rendered full PDF. The sample also exercises the Beatitudes' poetic indentation and the long Psalm 118 (Septuagint numbering). The full PDF's short closing pages and the dedicated dividers intentionally contain white space; these are not missing-text failures. This inspection is representative visual review, not a new scholarly proofreading of the source editions.

Two clean full builds passed: identical extracted text, 1,584 pages, and identical raster hashes for every page at 72 dpi. `dist/check.json` records the clean-build repeatability result and every page's raster SHA-256 at 72 dpi. `dist/bible.provenance.json` records the final PDF checksum, source and dependency pins, build-input hashes, installed OS packages, and font-file hashes. Generated inspection images are under `build/inspection/`; they are not tracked in Git.
