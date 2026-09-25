# Inspection record -- 2026-09-25

This record covers the 2026-09-25 inspection and the subsequent title-heading updates.

The current Utopia typesetting sample rendered to 111 A5 pages and is labeled as a sample. The earlier full edition rendered to 1602 A5 pages and passed `make check` (two clean builds with matching text, page counts, and per-page raster hashes) and `make check-protrusion`. An intermediate title-aligned edition rendered to 1603 A5 pages. The current edition rendered to 1604 A5 pages; `make validate`, `make sample`, and `make pdf` passed. Automated checks verified the selection of all 52 Brenton and 27 KJV scripture sources, the 78 printed scripture units, the divider and front-matter positions, the three appendices, converged contents and actual heading pages, embedded Utopia/Erewhon/GFS Porson/Ezra SIL, and no missing glyphs or fatal TeX errors. The source-to-generated comparison retained 36,573 scripture verse labels, notes, cross-references, added-word spans, and apparatus tables. The five front-matter and appendix edition headings recorded in `transformations.json` replaced their source headings exactly once each. The current TeX log reports three overfull vertical boxes of 21.3pt and two overfull horizontal boxes under 0.25pt.

These are page references from the current PDF for the representative inspection. The Kingdoms, Prayer of Manasses, Sirach, and Jeremias table pages were rendered and inspected again after the latest heading update:

| PDF page | Inspection |
| --- | --- |
| 1-5 | Title page; contents listing every unit in manifest order with correct page numbers; editor's introduction following the contents |
| 7-8, 14, 16 | Old Testament divider; Preface (1844) with its footnote; Introduction (1870) and its Greek quotations in GFS Porson |
| 22, 26-27 | The Books of the Apocrypha; abbreviations table; Genesis opening with dense footnotes and matching callers |
| 581-582 | Prayer of Manasses after 2 Chronicles; 1 Esdras opening |
| 602-603, 615-616 | 2 Esdras heading after 1 Esdras 9; Nehemias heading after 2 Esdras 10, with running headers |
| 662 | Esther opening additions and lettered verse labels |
| 756-757 | 4 Maccabees immediately after 3 Maccabees, inside the Old Testament |
| 780, 855 | Psalms with poetic indentation and titles; Psalm 151 |
| 1049-1050 | Malachias 4 with the relabeled 4:5 cross-reference; Esaias opening |
| 1247, 1269-1271 | Susanna before Daniel 1; Bel and the Dragon after Daniel 12 as titled sections, running header Daniel 13 |
| 1272-1275 | New Testament divider; Epistle Dedicatory; The Translators to the Reader |
| 1292-1293 | End of the translators' preface; Matthew opening |
| 1589-1592, 1597 | Revelation 22 ending; Appendices divider; Jeremias table; Notes and Supplied Passages with right-to-left Hebrew and the supplied Alexandrine passages; Corrections to the Text |
| 27, 89, 140, 178, 233, 424, 581, 915, 947, 1050, 1111, 1187 | Expanded Old Testament headings matching their long contents titles |

Findings:

- The Jeremias table title on page 1591 fits on one line, but its word spaces are visibly compressed. The title spacing needs a separate layout change; the contents and printed heading use the same Jeremias name.
- Brenton's preface (page 8) reads "There^a is" with the footnote caller inside the word, because the source has no space after the note marker. This is a source defect present in the eBible archive and is not altered by the pipeline.

The short ending pages and dedicated dividers intentionally contain white space. This inspection is representative visual review, not a new scholarly proofreading of the source editions.
