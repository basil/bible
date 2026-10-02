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

## Swete’s Greek edition

`edition/alexandrinus.json` cites Henry Barclay Swete, *The Old Testament in Greek according to the Septuagint*, third edition: volume I (1901), volume II (1907), and volume III (1905). The manuscript apparatus was consulted from page images, using printed page numbers. It checks Brenton’s reports of Codex Alexandrinus and settles the placement of supplied English passages; it is not an additional English translation printed in the edition.

The scans are consulted editorial evidence. The build reads the recorded decisions and citations in `edition/alexandrinus.json` and does not require the images or network access. See [Alexandrine readings](../docs/edition.md#alexandrine-readings) for the limits of this use and the per-decision audit.

## Versification

[`TVTMS - Translators Versification Traditions with Methodology for Standardisation for Eng+Heb+Lat+Grk+Others - STEPBible.org CC BY.txt`](<TVTMS - Translators Versification Traditions with Methodology for Standardisation for Eng+Heb+Lat+Grk+Others - STEPBible.org CC BY.txt>) is [STEP Bible](https://www.STEPBible.org)'s table of the ways Bibles number their chapters and verses, retrieved on 2026-09-28 from [STEPBible-Data](https://github.com/STEPBible/STEPBible-Data/tree/1f342173b881ba5d1a5a4cae6e7c6c3fcc7cac51/Versification) at commit `1f34217`. Data created by www.STEPBible.org based on work at Tyndale House Cambridge (CC BY 4.0). The file is unaltered. Its header asks users to refer others to [github.com/STEPBible](https://github.com/STEPBible) rather than redistribute it; it is committed here, as its licence allows, so that the checks that read it never need the network. Look there for the current version.

The build doesn't print from the table. It is one of two witnesses to [`edition/versification.json`](../edition/versification.json), which says where each verse of this Old Testament stands in the King James Bible; the other is the words of the two translations. Where that file departs from the table, the run says what it rests on instead, as the licence asks of changes. [The editorial notes](../docs/edition.md#numbering) explain.

## 1611 marginal notes

[`exhaustive-listing-marginal-notes-1611-edition-king-james-bible.md`](exhaustive-listing-marginal-notes-1611-edition-king-james-bible.md) is a Markdown copy of Calvin George's ["An exhaustive listing of the marginal notes of the 1611 edition of the King James Bible"](https://en.literaturabautista.com/exhaustive-listing-marginal-notes-1611-edition-king-james-bible), from Literatura Bautista. It covers the translators' notes on both testaments: alternative translations, literal meanings, and variant readings. It leaves out the Apocrypha, the chapter summaries, and the cross-references. George counts 6,566 notes in the Old Testament and 775 in the New; Scrivener counted 6,637 and 767.

George modernized much of the spelling and sometimes had to judge which words a note refers to, so this is an edited transcription, not a facsimile. The build uses only the New Testament notes. The [editorial notes](../docs/edition.md#the-1611-marginal-notes) explain how they're placed and corrected.

## Fonts

The fonts below are under the SIL Open Font License. Source Code Pro and Erewhon were retrieved on 2026-09-25.

| File                                        | Downloaded from                                                                                                                                 | Version                     | Used for                                                |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------- | ------------------------------------------------------- |
| `GFS_Didot.zip`                             | [Greek Font Society](https://greekfontsociety-gfs.gr/_assets/fonts/GFS_Didot.zip)                                                               |                             | Greek                                                   |
| `erewhon.zip`                               | [CTAN](https://mirrors.ctan.org/fonts/erewhon.zip)                                                                                              | 1.123 (2025-06-08)          | OLEBFont text additions                                 |
| `erewhon-math.zip`                          | [CTAN](https://mirrors.ctan.org/fonts/erewhon-math.zip)                                                                                         | 0.75 (2026-08-27)           | OLEBFont additional symbols and mathematical alphabets  |
| `OTF-source-code-pro-2.042R-u_1.062R-i.zip` | [Adobe](https://github.com/adobe-fonts/source-code-pro/releases/download/2.042R-u/1.062R-i/1.026R-vf/OTF-source-code-pro-2.042R-u_1.062R-i.zip) | 2.042 upright, 1.062 italic | Nothing printed; PTXprint loads it for crop-mark labels |

The main text family, OLEBFont, is assembled by `scripts/build_olebfont.py` from Utopia (the repository pinned in `Dockerfile`), the matching four Erewhon text faces, and Erewhon Math. See [font normalization](../docs/font-normalization.md) for donor selection and scaling.

Utopia supplies overlapping glyphs, spacing, ligatures, kerning and hinting, except that superscript 1, 2 and 3 use Erewhon’s designs for a consistent figure set. Erewhon supplies missing glyphs and alternate forms, followed by Erewhon Math. Both donors are enlarged by 100/94 to restore Utopia size, including their spacing, positioning and hints.

Erewhon and Erewhon Math are build inputs. Production uses the combined OLEBFont family. The Hebrew font, Ezra SIL, comes from Ubuntu.

The generated family includes Erewhon’s `OFL.txt`, Utopia’s original Adobe `COPYING`, the [Adobe/TUG sublicensing notice](https://tug.org/fonts/utopia/LICENSE-utopia.txt) (retrieved 2026-09-30, committed in `scripts/Adobe-TUG-Utopia-LICENSE.txt`), Erewhon Math’s `README.md`, and `OLEBFont-NOTICE.txt`. All copyright, donor attribution and reserved-name declarations are retained. The renamed family is distributed under OFL 1.1 with the Adobe notices; the edition’s text license is separate.
