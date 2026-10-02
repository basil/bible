# Orthodox Liturgical English Bible (OLEB)

The Orthodox Liturgical English Bible (OLEB) is a complete English Bible in one volume, ready to print or read on screen. Its Old Testament is the Septuagint, with its books in the order of the Church of Greece, and both testaments are in the style of English of the King James Bible.

**[Read the finished Bible (PDF)](https://basil.github.io/bible/bible.pdf)**

## What is in it

This volume brings together two English translations that have long been read apart. The Old Testament is Sir Lancelot Brenton's English translation of the Septuagint, as printed in 1870. The New Testament is the King James Version in the text prepared by F. H. A. Scrivener for the _Cambridge Paragraph Bible_ of 1873. Both texts come from [eBible.org](https://ebible.org/), and Brenton's includes the corrections eBible has made to it. Both are in the public domain outside the United Kingdom. Brenton's is also in the public domain in the UK, where the right to print the King James Version belongs to the Crown.

The volume is arranged as follows:

1. The title page, the table of contents, a list of abbreviations, the editor's introduction, and a table of chapters and verses whose numbers differ from the King James Bible’s
2. The Old Testament, opening with Brenton's preface (1844) and introduction (1870) and a later introduction to the Apocrypha
3. The New Testament, opening with the King James translators' dedication to the king and their preface, "The Translators to the Reader"
4. Appendices: Brenton's notes and supplied passages

Most Old Testament books use their Septuagint names: Esaias rather than Isaiah; Jesus, the Son of Navi rather than Joshua; and 1-4 Kingdoms rather than Samuel and Kings. The books that English Bibles set apart as the Apocrypha are printed in their Greek places, so there is no separate Apocrypha section: the Prayer of Manasses follows 2 Chronicles, 4 Maccabees follows 3 Maccabees, and the additions to Esther and Daniel and Psalm 151 stand within the text.

The translations are preserved with a few exceptions. Brenton translated the Vatican text and gave readings from Codex Alexandrinus in his notes and Appendix. Where Swete's edition supports the wording and placement of a reading, it is printed in the main text and the displaced reading appears in a footnote. The wording of the New Testament is unchanged. Brenton's footnotes are printed, and the New Testament carries the marginal notes of the King James Bible of 1611. The [editorial notes](docs/edition.md) explain these choices in detail.

## How it looks

The page size is ISO B5 (176 × 250 mm). Scripture is set in one column in [Utopia](<https://en.wikipedia.org/wiki/Utopia_(typeface)>) at 10 pt, with the notes in the inside margin. The design is based on the Berean Standard Bible layout that comes with [PTXprint](https://software.sil.org/ptxprint/), a free program for typesetting Bibles.

## Building it yourself

Everything needed to produce the PDF is stored in this repository, including the original source archives. See [CONTRIBUTING.md](CONTRIBUTING.md) for the steps.

## Further reading

- [Editorial notes](docs/edition.md): why the texts were chosen, arranged, and adjusted as they were
- [Sources](sources/README.md): where each text and font came from
- [Contributing](CONTRIBUTING.md): building, checking, and changing the edition

## License

Copyright © 2026 Basil Crow. Basil Crow’s original editorial material and the assembled edition, to the extent copyright protects them, are licensed under [Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International (CC BY-NC-ND 4.0)](https://creativecommons.org/licenses/by-nc-nd/4.0/).

This edition’s license does not change the status of the source translations. The build scripts and configuration are released under the [MIT License](LICENSE).
