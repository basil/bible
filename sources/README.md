# Sources

Everything the build reads is committed here exactly as downloaded, so building never needs the network. `src/bible/sources.py` and the `Dockerfile` record the SHA-256 hash of each archive, and the build refuses to run if an archive doesn't match.

## Bible texts

Both archives were retrieved from eBible.org on 2026-09-23.

| File                   | Downloaded from                                              | Copyright notice                                 |
| ---------------------- | ------------------------------------------------------------ | ------------------------------------------------ |
| `eng-Brenton_usfm.zip` | [eBible](https://ebible.org/Scriptures/eng-Brenton_usfm.zip) | `copr.htm` in the archive; `brenton-notice.html` |
| `engkjvcpb_usfm.zip`   | [eBible](https://ebible.org/Scriptures/engkjvcpb_usfm.zip)   | `copr.htm` in the archive; `kjv-notice.html`     |

Both texts are in the public domain. The King James notice also mentions the Crown's rights over printing it in the United Kingdom. `brenton-notice.html` and `kjv-notice.html` are copies of eBible's [Brenton](https://ebible.org/eng-Brenton/copyright.htm) and [KJV](https://ebible.org/engkjvcpb/copyright.htm) copyright pages, saved the same day.

## 1611 marginal notes

[`exhaustive-listing-marginal-notes-1611-edition-king-james-bible.md`](exhaustive-listing-marginal-notes-1611-edition-king-james-bible.md) is a Markdown copy of Calvin George's ["An exhaustive listing of the marginal notes of the 1611 edition of the King James Bible"](https://en.literaturabautista.com/exhaustive-listing-marginal-notes-1611-edition-king-james-bible), from Literatura Bautista. It covers the translators' notes on both testaments: alternative translations, literal meanings, and variant readings. It leaves out the Apocrypha, the chapter summaries, and the cross-references. George counts 6,566 notes in the Old Testament and 775 in the New; Scrivener counted 6,637 and 767.

George modernized much of the spelling and sometimes had to judge which words a note refers to, so this is an edited transcription, not a facsimile. The build uses only the New Testament notes. The [editorial notes](../docs/edition.md#the-1611-marginal-notes) explain how they're placed and corrected.

## Fonts

All three are under the SIL Open Font License. Source Code Pro and Erewhon were retrieved on 2026-09-25.

| File                                        | Downloaded from                                                                                                                                 | Version                     | Used for                                                |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------- | ------------------------------------------------------- |
| `GFS_Didot.zip`                             | [Greek Font Society](https://greekfontsociety-gfs.gr/_assets/fonts/GFS_Didot.zip)                                                               |                             | Greek                                                   |
| `erewhon.zip`                               | [CTAN](https://mirrors.ctan.org/fonts/erewhon.zip)                                                                                              | 1.123 (2025-06-08)          | Verse numbers                                           |
| `OTF-source-code-pro-2.042R-u_1.062R-i.zip` | [Adobe](https://github.com/adobe-fonts/source-code-pro/releases/download/2.042R-u/1.062R-i/1.026R-vf/OTF-source-code-pro-2.042R-u_1.062R-i.zip) | 2.042 upright, 1.062 italic | Nothing printed; PTXprint loads it for crop-mark labels |

The main text font, Utopia, is built from the repository pinned in the `Dockerfile`. The Hebrew font, Ezra SIL, comes from Ubuntu.
