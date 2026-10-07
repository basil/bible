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

The scans are consulted editorial evidence. The build reads the recorded decisions and citations in `edition/alexandrinus.json` and does not require the images or network access. See [Readings from Codex Alexandrinus](../docs/edition.md#readings-from-codex-alexandrinus) for the limits of this use, and [CONTRIBUTING.md](../CONTRIBUTING.md#reviewing-the-readings-from-codex-alexandrinus) for the review of each decision.

## Versification

[`TVTMS - Translators Versification Traditions with Methodology for Standardisation for Eng+Heb+Lat+Grk+Others - STEPBible.org CC BY.txt`](<TVTMS - Translators Versification Traditions with Methodology for Standardisation for Eng+Heb+Lat+Grk+Others - STEPBible.org CC BY.txt>) is [STEP Bible](https://www.STEPBible.org)'s table of the ways Bibles number their chapters and verses, retrieved on 2026-09-28 from [STEPBible-Data](https://github.com/STEPBible/STEPBible-Data/tree/1f342173b881ba5d1a5a4cae6e7c6c3fcc7cac51/Versification) at commit `1f34217`. Data created by <www.STEPBible.org> based on work at Tyndale House Cambridge (CC BY 4.0). The file is unaltered. Its header asks users to refer others to [github.com/STEPBible](https://github.com/STEPBible) rather than redistribute it; it is committed here, as its licence allows, so that the checks that read it never need the network. Look there for the current version.

The table is one of two witnesses to where each verse of this Old Testament stands in the King James Bible; the other is the words of the two translations. The build hears both, and the editor's readings in [`edition/versification.json`](../edition/versification.json) stand over both. Where the numbering departs from the table, the run says what it rests on instead, as the licence asks of changes; `make review` lists every run in `build/review/numbering.md`. [The editorial notes](../docs/edition.md#numbering) explain.

## The New Testament Greek and its witnesses

The New Testament is conformed to the Byzantine text from these sources, read as [the New Testament text](../docs/new-testament.md) describes; `src/bible/sources.py` pins each by its hash and gives its URL and the date it was retrieved. The three GitHub archives are whole downloads at the commits in their names. Nothing is extracted to disk: the build reads the archives' members in memory, and runs Poppler's `pdftohtml -xml -i -stdout` on the Greek New Testament and `pdftotext -layout` on the collation inside the container on every build, committing no conversion; the readers' counts (7,957 verses printed, 1,885 rows of the collation) say if Poppler ever reads them otherwise.

### The Greek texts

| File | Downloaded from | What it is | Notice |
| --- | --- | --- | --- |
| `greektext-scrivener-6049a43b135ed870f843b83eb6a04764fc796678.zip` | [byztxt/greektext-scrivener](https://github.com/byztxt/greektext-scrivener) at that commit, 2026-10-07 | Robinson's electronic text of Scrivener's 1894 reconstruction of the Greek the King James Version follows, text only, one file per book | The archive's `README.md`, "License?": public domain, copy freely |
| `textus-receptus-2bac2dae4a0961c84d6d544a40cbef8b8d8c4e32.zip` | [honza/textus-receptus](https://github.com/honza/textus-receptus/tree/2bac2dae4a0961c84d6d544a40cbef8b8d8c4e32), 2026-10-07 | Honza Pokorny's accented Scrivener 1894 transcription, `data/gnt.flat.json`; only its diacritics are transferred onto the pinned unaccented Scrivener words for the readings appendix, checking book-wide alignment across word divisions, final ν/ς and verse boundaries (ϛ is the numeral form of the pinned ς in Revelation 13:18) | The archive's `README.md`: data free of charge without any limitation on use; associated software GPL v3 or later. The original README and LICENSE are retained in the archive |
| `greektext-textus-receptus-7fd4d02c3e5adebd379ebfbc824040820dde10fc.zip` | [byztxt/greektext-textus-receptus](https://github.com/byztxt/greektext-textus-receptus) at that commit, 2026-10-07 | Stephanus 1550 with Scrivener's variants, parsed with Strong's numbers; the build takes Scrivener's side, and uses it to classify the differences | The archive's `README.md`: public domain |
| `byzantine-majority-text-27a45ff1b7be6c17ccbfeac414f3f55732ae8e28.zip` | [byztxt/byzantine-majority-text](https://github.com/byztxt/byzantine-majority-text) at that commit, 2026-10-07 | Robinson's electronic RP2018, parsed (`source/Strongs`), and with its marginal alternates (`source/CCAT`) | The archive's `LICENSE.txt`: the Unlicense |
| `TGNTByzText_081526_0727PM.pdf` | [byzantinetext.com](https://byzantinetext.com/study/editions/robinson-pierpont/), linking to a [Google Drive file](https://drive.google.com/file/d/1zOfeQw-7UBcEF1zk0v5ymj2jJCHlSFCv/view); verified against a fresh download 2026-10-07 | *The Greek New Testament According to the Byzantine Text*, Guardian Press, typeset 2026-08-25: the printed RP2026, which the build reads by its fonts and checks RP2018 with Appendix A's six changes against | Physical page 6: dedicated to the public domain on release |
| `collation-scrivener-rp-2018.pdf` | [byzantinetext.com](https://byzantinetext.com/wp-content/uploads/2022/04/collation-scrivener-rp-2018.pdf); verified 2026-10-07 | Robinson's collation of Scrivener 1894 against RP2005/2018: 1,885 differences, which bound the build's units | The [editions page](https://byzantinetext.com/study/editions/robinson-pierpont/) permits unrestricted redistribution |
| `tcgnt-usx-files.zip` | [archive.org/details/TCGNT](https://archive.org/download/TCGNT/tcgnt-usx-files.zip), 2026-10-03 | Boyd's *Text-Critical Greek New Testament* (2022): RP2018 with an apparatus of eleven editions as footnotes, 1,948 of them citing the Received Text, and Appendix C's word breaks | `100FRT.usx`: released to the public domain, asking that the editors' names, the title and their disclaimer be kept: the permitted use "does not imply doctrinal or theological agreement by the present editors and publisher with whatever views may be maintained or promulgated by other publishers" |

### The English witnesses

| File | Downloaded from | What it is | Notice |
| --- | --- | --- | --- |
| `pierpont.md` | [Byzantine Music](https://byzantinemusic.org/holy-scriptures/improvements-kjv.html), 2026-10-07 | William G. Pierpont, *Some Improvements to the King James Version from the Majority Greek Manuscripts*, revised June 1990, with Peter and Chris Fatz's page and their locators into Berry's interlinear: the transcription of the 54 scanned sides, checked against them; 960 instructions in the King James words, with manuscript weights. The primary English witness | The booklet's own: "Permission is granted to copy this material, so long as it is copied in full." |
| `pierpont-1990.pdf` | The scan the transcription was made from, as Maurice A. Robinson supplied it to a forum; no cleaner original is known | The booklet's 54 sides | As above, on its first side |
| `tcent-usx-files.zip` | [archive.org/details/TCENT](https://archive.org/download/tcent/tcent-usx-files.zip), 2026-10-03 | Boyd's *Text-Critical English New Testament* / *Byzantine Text Version* (2022): his translation with the TCGNT apparatus restricted to the differences that show in his English, 552 of them citing the Received Text | © 2021 Robert Adam Boyd, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); the two titles are his trademarks, and may not name a changed translation or changed notes. The notice is on physical page 6 of the [paperback PDF](https://archive.org/download/tcent/TCENT%20Paperback%20%28ISBN%20979-8-84726-292-7%29.pdf), SHA-256 `6f61a27d056845d280026797c4071a55d19cfe61c04dd18704ac40c89fa3776f`, which the build does not read and so is not committed |
| `NTinHTML_AVorder_Unicode.html` | [faraboveall.com](https://www.faraboveall.com/050_BibleTranslation/NTinHTML_AVorder_Unicode.html), 2026-10-03 | Graham G. Thomason, *Far Above All*: a literal translation of RP with every Received Text and Patriarchal variant inline, Greek and English; its accented Received Text also serves the review | Its embedded copyright section: copying permitted with the notice retained |
| `msb.txt`, `msb_nt_tables.tsv` | [majoritybible.com](https://majoritybible.com/msb.txt) and its [tables](https://majoritybible.com/msb_nt_tables.tsv), 2026-10-03, verified 2026-10-07 | The Majority Standard Bible, the Berean Standard Bible conformed to RP, with its word-alignment tables and about 350 notes mentioning the Received Text | Dedicated to the public domain: `msb.txt` line 2 and the Berean [licensing](https://berean.bible/licensing.htm) page |
| `eng-web_usfm.zip` | [eBible](https://ebible.org/Scriptures/eng-web_usfm.zip), 2026-10-06 | The World English Bible, with about 100 notes of the form "TR reads … instead of …" | `copr.htm` in the archive: public domain; the name is eBible.org's trademark |
| `eng-rv_usfm.zip`, `eng-asv_usfm.zip` | [eBible](https://ebible.org/Scriptures/eng-rv_usfm.zip), [eBible](https://ebible.org/Scriptures/eng-asv_usfm.zip), 2026-10-06 | The Revised Version of 1881 and the American Standard Version of 1901, as witnesses to whether a reviser of the King James Version made the same change | `copr.htm` in each archive: public domain |
| `boyd-asv-byz-2021-scrape.zip` | Each member from [gojes.us](https://gojes.us/documents/bible/all_html/asv_byzantine_text/) under its unchanged name, 2026-10-03, packaged with fixed metadata 2026-10-07 | Boyd's *American Standard Version, Byzantine Text* of February 2021, the ASV revised to RP2018: 260 chapter pages and its introduction, the complete RP English closest to the King James diction | `boyd-asv-byz-2021-copyright.htm`, a copy of its [notice](https://gojes.us/documents/bible/all_html/asv_byzantine_text/copyright.htm): Boyd's changes dedicated to the public domain |
| `kjv-osis-201602070816-2_9a.zip` | [CrossWire](https://www.crosswire.org/~dmsmith/kjv2011/kjv2.9a/kjv-osis-201602070816-2_9a.zip), 2026-10-07 | The King James Version in OSIS, each phrase tagged with the Received Text word it renders (CrossWire KJV 2.9a, member `kjv.tr.xml`): the bridge from the King James words to the Greek, used to locate and test wording, never to supply it | `crosswire-kjv-notice.html`, the publisher's directory listing; CrossWire's [project page](https://wiki.crosswire.org/CrossWire_KJV#Copyright) grants use of the text for any purpose and identifies its rights in the markup and tagging |

Three Latin alphabets transliterate the Greek of these files, and the build converts each with one simultaneous table and compares everything lower-case and unaccented. The Boyd scrape is a local package, not a publisher download: its members are the pages as served, and its metadata is fixed (sorted names, deflated at level 9, dated 1980-01-01) so that the archive's hash is reproducible.

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
