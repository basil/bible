# Inspection record -- 2026-09-25

This record covers the 2026-09-25 inspection, the subsequent title-heading updates, and the New Testament marginal-note render.

## New Testament marginal-note render

The current sample rendered to 112 A5 pages and the full Bible to 1637 A5 pages. `make validate`, `make sample`, `make pdf`, and `make check` passed. The last includes the protrusion check and two full builds with matching text, page counts, and per-page raster hashes. The build inserted all 775 New Testament notes in 26 books, and the source-to-processed comparison retained their callers and note bodies. The PDF checks found no missing glyphs, TeX errors, reused note callers, or unembedded fonts. The restored Greek on Acts 13:18 and 13:34 is set in GFS Porson, as confirmed by the PDF text runs. The sample's Matthew 5:15 witness passed. Genesis 1 on page 27 retains Brenton's notes and provides a style comparison for the new `Or,` and `Gr.` labels.

| PDF page | Inspection |
| --- | --- |
| 1313, 1315 | Matthew 5:15 and 6:2: callers precede "bushel" and "sound a trumpet"; the notes and italic labels fit below the columns |
| 1371 | Mark 14:72: the note prints "began to wept" without the transcriber's bracketed remark |
| 1405 | Luke 17:36: the caller starts the verse, and the note fits below the columns |
| 1441 | John 16:25: separate callers mark the two occurrences of "proverbs," each with its own note |
| 1466-1467 | Acts 13:18 and 13:34: restored Greek appears in the notes without missing or substituted glyphs |
| 1496, 1501 | Romans 7 and 11-12: dense notes have distinct callers and legible references |
| 1513, 1515 | 1 Corinthians 10:4 and 11-12: the note on "followed" is in verse 4; the crowded note area remains legible |
| 1528 | 2 Corinthians 10:2: the caller marks the second "think," in "which think of us" |
| 1536 | Galatians 4:25: the moved note marks "answereth" in verse 25 |
| 1575-1576 | Hebrews 7-9: the notes and their callers remain legible on crowded pages |
| 1585 | James 3-4: twelve notes fit beneath the columns with distinct callers |
| 1620 | Revelation 20:13: the caller marks "hell" and matches its note |

The current New Testament divider is on page 1289, Matthew begins on page 1310, Revelation ends on page 1622, and the appendices begin on page 1623. An [Acts 13 page scan from the 1611 printing](https://www.kingjamesbibleonline.org/The-Actes_13_1611/) visually corroborates the restored Greek expressions; its small marginal type does not support an accent-by-accent collation. The rest is a representative visual inspection of placement and legibility, not a scholarly collation of all 775 notes.

## Earlier inspection

The earlier Utopia typesetting sample rendered to 111 A5 pages and is labeled as a sample. An earlier full edition rendered to 1602 A5 pages and passed `make check` (two clean builds with matching text, page counts, and per-page raster hashes) and `make check-protrusion`. An intermediate title-aligned edition rendered to 1603 A5 pages. The subsequent edition rendered to 1604 A5 pages; `make validate`, `make sample`, and `make pdf` passed. Automated checks verified the selection of all 52 Brenton and 27 KJV scripture sources, the 78 printed scripture units, the divider and front-matter positions, the three appendices, converged contents and actual heading pages, embedded Utopia/Erewhon/GFS Porson/Ezra SIL, and no missing glyphs or fatal TeX errors. The source-to-generated comparison retained 36,573 scripture verse labels, notes, cross-references, added-word spans, and apparatus tables. The five front-matter and appendix edition headings recorded in `transformations.json` replaced their source headings exactly once each. That TeX log reported three overfull vertical boxes of 21.3pt and two overfull horizontal boxes under 0.25pt.

These are page references from that earlier PDF for the representative inspection. The Kingdoms, Prayer of Manasses, Sirach, and Jeremias table pages were rendered and inspected again after the heading update:

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
