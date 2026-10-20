# Orthodox Liturgical English Bible (OLEB)

The Orthodox Liturgical English Bible (OLEB) is a complete English Bible in one volume, ready to print or read on screen. Its Old Testament is the Septuagint, with its books in the order of the Orthodox Church, and both testaments are in the style of English of the King James Bible.

**[Read the Bible online](https://oleb.bible) · [Download the PDF](https://oleb.bible/bible.pdf)**

## What is in it

This volume brings together two English translations that have long been read apart. The Old Testament is Sir Lancelot Brenton's English translation of the Septuagint, as printed in 1870. The New Testament is the King James Version in the text prepared by F. H. A. Scrivener for the _Cambridge Paragraph Bible_ of 1873, conformed to the Byzantine text of the Greek New Testament edited by Maurice A. Robinson and William G. Pierpont (2026) wherever that text differs from the Received Text in a way English can show. Both English texts come from [eBible.org](https://ebible.org/), and Brenton's includes the corrections eBible has made to it. Both are in the public domain outside the United Kingdom. Brenton's is also in the public domain in the UK, where the right to print the King James Version belongs to the Crown.

The volume is arranged as follows:

1. The title page, the table of contents, a list of abbreviations, the editor's introduction, including a table of books whose names differ from the King James Bible’s
2. The Old Testament, opening with Brenton's preface and introduction
3. The New Testament, opening with the King James translators' dedication to the king and their preface, "The Translators to the Reader"

Most Old Testament books use their Septuagint names: Esaias rather than Isaiah; Jesus, the Son of Navi rather than Joshua; and 1-4 Kingdoms rather than Samuel and Kings. The books that English Bibles set apart as the Apocrypha are printed in their Greek places, so there is no separate Apocrypha section: the Prayer of Manasses follows 2 Chronicles, 4 Maccabees follows 3 Maccabees, and the additions to Esther and Daniel and Psalm 151 stand within the text.

The translations are preserved with a few exceptions. Brenton translated Valpy's printed Greek edition, derived from the Sixtine edition of 1587 (itself based chiefly on Codex Vaticanus), and gave readings from Codex Alexandrinus in his notes and Appendix. Where Swete's edition supports the wording and placement of a reading from Codex Alexandrinus, it is printed in the main text and the displaced reading appears in a footnote. In the New Testament, where the Byzantine text differs from the Received Text the King James translators followed and the difference can be seen in English, the King James words are conformed to the Byzantine text and the displaced reading appears in a footnote. The English changes are based on Pierpont's _Some Improvements to the King James Version from the Majority Greek Manuscripts_ (1990), with further wording drawn from Boyd's _American Standard Version, Byzantine Text_ (2021). Brenton's footnotes are printed, those eBible's transcription lacks supplied from the Christian Classics Ethereal Library's, and the New Testament carries the marginal notes of the King James Bible of 1611. The [editorial notes](docs/edition.md) and [the New Testament text](docs/new-testament.md) explain these choices in detail.

## How it looks

The page size is ISO B5 (176 × 250 mm). Scripture is set in one column in [Valkyrie](https://mbtype.com/fonts/valkyrie/) at 9 pt, with the notes in the inside margin beside their verses, and at the foot of the page those that would crowd it. Greek is set in GFS Heraklit and Hebrew in Ezra SIL, in print and online. Valkyrie is a proprietary typeface, so a build made without it, such as one checking a pull request, is set instead in [Utopia](<https://en.wikipedia.org/wiki/Utopia_(typeface)>), with Greek in GFS Didot. In print, Valkyrie builds use newpx’s regular TeX Gyre PagellaX face for large chapter-opening numerals; Utopia builds keep Utopia’s numerals. The design is based on the Berean Standard Bible layout that comes with [PTXprint](https://software.sil.org/ptxprint/), a free program for typesetting Bibles.

The website presents the same prepared scripture, with notes below each chapter, the front matter of the book, each translation's before its testament, and the website-only [tables of chapters and verses](https://oleb.bible/read/numbering) and [textual variants](https://oleb.bible/variants/). The variants list every New Testament verse in which the Greek texts differ, with the Greek of both and, where the English changes, the words of both Bibles.

## Building it yourself

Everything needed to produce the PDF is stored in this repository, including the original source archives. See [AGENTS.md](AGENTS.md) for the steps.

## Further reading

- [Editorial notes](docs/edition.md): why the texts were chosen, arranged, and adjusted as they were
- [The New Testament text](docs/new-testament.md): how the King James Version is conformed to the Byzantine text, and the standard of a translatable difference
- [Sources](sources/README.md): where each text and font came from
- [Working on this repository](AGENTS.md): building, checking, and changing the edition
- [Contributing](CONTRIBUTING.md): the editorial work, the layout, the dependencies and the sources

## License

Copyright © 2026 Basil Crow. Basil Crow’s original editorial material and the assembled edition, to the extent copyright protects them, are licensed under [Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International (CC BY-NC-ND 4.0)](https://creativecommons.org/licenses/by-nc-nd/4.0/).

This edition’s license does not change the status of the source translations or other third-party materials. Those materials retain their own public-domain status, licenses, and permissions. CC BY-NC-ND applies only to rights held by Basil Crow. The build scripts and configuration are released under the [MIT License](LICENSE).
