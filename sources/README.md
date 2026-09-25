# Original source snapshots

Retrieved 2026-09-23; the original ZIP files are committed without repacking. `sources.json` records SHA-256 hashes, archive member names and hashes, and chapter/verse/marker inventories.

| Snapshot               | Original URL                                       | Notice                                                                                             |
| ---------------------- | -------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `eng-Brenton_usfm.zip` | https://ebible.org/Scriptures/eng-Brenton_usfm.zip | `copr.htm` inside ZIP; https://ebible.org/eng-Brenton/copyright.htm saved as `brenton-notice.html` |
| `engkjvcpb_usfm.zip`   | https://ebible.org/Scriptures/engkjvcpb_usfm.zip   | `copr.htm` inside ZIP; https://ebible.org/engkjvcpb/copyright.htm saved as `kjv-notice.html`       |

The standalone notice pages were downloaded on the same retrieval date. They include references to external site assets that are not needed for the build. The original notices inside the ZIPs are covered by the archive hashes. Normal builds read only the snapshots, never the URLs.

## 1611 KJV marginal notes

[`exhaustive-listing-marginal-notes-1611-edition-king-james-bible.md`](exhaustive-listing-marginal-notes-1611-edition-king-james-bible.md) is a Markdown conversion of Calvin George's ["An exhaustive listing of the marginal notes of the 1611 edition of the King James Bible"](https://en.literaturabautista.com/exhaustive-listing-marginal-notes-1611-edition-king-james-bible) on Literatura Bautista. It transcribes the translators' marginal notes for the Old and New Testaments, including alternative renderings, literal-language glosses, and textual-variant notes. George reports 6,566 Old Testament notes and 775 New Testament notes; he also cites Scrivener's different counts of 6,637 and 767, respectively.

The transcription omits the Apocrypha, chapter headings, and the general marginal cross-references. George modernized much of the spelling and sometimes used his judgment to identify the exact phrase a note applies to, so this file is an edited transcription rather than a facsimile of the 1611 printing. Entries give a book, chapter and verse, the relevant words from the biblical text, and the note; several verses have multiple entries. The Markdown has wrapped lines, so any parser must join continuation lines before reading entries. This file is source material for possible note integration; it is not USFM, is not inventoried in `sources.json`, and is not read by the current build.
