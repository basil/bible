# Sources

Everything the build reads is committed here exactly as downloaded, so building never needs the network. `src/bible/sources.py` and the `Dockerfile` record the SHA-256 hash of each archive, and the build refuses to run if an archive doesn't match.

## New Testament quotations of the Old Testament

[`edition/turpie.json`](../edition/turpie.json) cites the Internet Archive's [scan](https://archive.org/download/oldtestamentinne00turp/oldtestamentinne00turp.pdf) of David McCalman Turpie's *The Old Testament in the New* (1868), retrieved on 2026-09-27, by page for every quotation. The build doesn't read the scan, so at 23 MB it isn't committed. [The editorial notes](../docs/edition.md#quotations) explain how the quotations are chosen and linked. To check a citation, download it and compare its hash:

```sh
curl -LO https://archive.org/download/oldtestamentinne00turp/oldtestamentinne00turp.pdf
echo 'e60c13a1075f7639ddcb60ab4bca58d959e01614b250daad21029429079f692b  oldtestamentinne00turp.pdf' | sha256sum -c
```

## Bible texts

Both archives were retrieved from eBible.org on 2026-09-23.

| File                   | Downloaded from                                              | Copyright notice                                 |
| ---------------------- | ------------------------------------------------------------ | ------------------------------------------------ |
| `eng-Brenton_usfm.zip` | [eBible](https://ebible.org/Scriptures/eng-Brenton_usfm.zip) | `copr.htm` in the archive; `brenton-notice.html` |
| `engkjvcpb_usfm.zip`   | [eBible](https://ebible.org/Scriptures/engkjvcpb_usfm.zip)   | `copr.htm` in the archive; `kjv-notice.html`     |

Both texts are in the public domain outside the United Kingdom. Brenton's is also in the public domain in the UK, where the right to print and publish the King James Version belongs to the Crown and is licensed only to certain publishers under letters patent. See the [UK Intellectual Property Office's guidance](https://www.gov.uk/government/publications/copyright-notice-duration-of-copyright-term/copyright-notice-duration-of-copyright-term). `brenton-notice.html` and `kjv-notice.html` are unaltered copies of eBible's [Brenton](https://ebible.org/eng-Brenton/copyright.htm) and [KJV](https://ebible.org/engkjvcpb/copyright.htm) copyright pages, saved the same day.

## 1611 marginal notes

[`exhaustive-listing-marginal-notes-1611-edition-king-james-bible.md`](exhaustive-listing-marginal-notes-1611-edition-king-james-bible.md) is a Markdown copy of Calvin George's ["An exhaustive listing of the marginal notes of the 1611 edition of the King James Bible"](https://en.literaturabautista.com/exhaustive-listing-marginal-notes-1611-edition-king-james-bible), from Literatura Bautista. It covers the translators' notes on both testaments: alternative translations, literal meanings, and variant readings. It leaves out the Apocrypha, the chapter summaries, and the cross-references. George counts 6,566 notes in the Old Testament and 775 in the New; Scrivener counted 6,637 and 767.

George modernized much of the spelling and sometimes had to judge which words a note refers to, so this is an edited transcription, not a facsimile. The build uses only the New Testament notes. The [editorial notes](../docs/edition.md#the-1611-marginal-notes) explain how they're placed and corrected.

## Fonts

All four are under the SIL Open Font License. Source Code Pro and Erewhon were retrieved on 2026-09-25, and Erewhon Math on 2026-09-27.

| File                                        | Downloaded from                                                                                                                                 | Version                     | Used for                                                |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------- | ------------------------------------------------------- |
| `GFS_Didot.zip`                             | [Greek Font Society](https://greekfontsociety-gfs.gr/_assets/fonts/GFS_Didot.zip)                                                               |                             | Greek                                                   |
| `erewhon.zip`                               | [CTAN](https://mirrors.ctan.org/fonts/erewhon.zip)                                                                                              | 1.123 (2025-06-08)          | Verse numbers                                           |
| `erewhon-math.zip`                          | [CTAN](https://mirrors.ctan.org/fonts/erewhon-math.zip)                                                                                         | 0.76                        | The ≠ in quotation links, which Utopia lacks            |
| `OTF-source-code-pro-2.042R-u_1.062R-i.zip` | [Adobe](https://github.com/adobe-fonts/source-code-pro/releases/download/2.042R-u/1.062R-i/1.026R-vf/OTF-source-code-pro-2.042R-u_1.062R-i.zip) | 2.042 upright, 1.062 italic | Nothing printed; PTXprint loads it for crop-mark labels |

The main text font, Utopia, is built from the repository pinned in the `Dockerfile`. The Hebrew font, Ezra SIL, comes from Ubuntu.
