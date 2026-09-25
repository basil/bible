# Brenton-KJV Bible

A complete English Bible, typeset as a single book and ready to print or read on screen.

**[Read the finished Bible (PDF)](https://basil.github.io/bible/bible.pdf)**

## What is in it

The Old Testament is Sir Lancelot Brenton's English translation of the Septuagint, as printed in 1870, arranged in the order followed by the Church of Greece. The New Testament is the King James Version in the text of the _Cambridge Paragraph Bible_, prepared by F. H. A. Scrivener in 1873. Scrivener's own introduction and appendices to that edition are not included. Both translations are in the public domain. The texts are taken from [eBible.org](https://ebible.org/), and Brenton's includes the corrections eBible has made to it.

The book reads in this order:

1. A title page, a table of contents, and the editor's introduction
2. The Old Testament, opening with Brenton's preface (1844), introduction (1870), introduction to the Apocrypha, and list of abbreviations
3. The New Testament, opening with the King James translators' dedication to the king and their preface, "The Translators to the Reader"
4. Appendices: Brenton's table comparing chapter order in Jeremias, his notes and supplied passages, and eBible's corrections to the text

The Old Testament books are called by their Septuagint names: Esaias rather than Isaiah; Jesus, the Son of Navi rather than Joshua; and 1-4 Kingdoms rather than Samuel and Kings. The books that English Bibles set apart as the Apocrypha are printed in their Greek places, so there is no separate Apocrypha section: the Prayer of Manasses comes after 2 Chronicles, 4 Maccabees after 3 Maccabees, and the additions to Esther and Daniel and Psalm 151 stand within the text. Ezra and Nehemiah are printed as 2 Esdras and Nehemias. Each book carries a full title in the style of the Cambridge Paragraph Bible, such as "The First Book of Moses, Called Genesis."

The wording of both translations and of Brenton's notes has not been altered, and the chapter and verse numbers are theirs, apart from the divisions just mentioned and a renumbering of the last verses of Malachias to match the Greek chapters. Brenton's footnotes are printed. The online text of the Cambridge New Testament has no notes, so the New Testament carries instead the marginal notes of the King James Bible of 1611 as transcribed by Calvin George. Words that the translators supplied to complete the English sense, which many Bibles print in italics, are set in ordinary type. The title pages, section dividers, table of contents, and headings are this edition's own.

The original copyright notices are kept alongside the texts in this repository.

## How it looks

The page size is A5, about the size of a paperback novel. Scripture is set in two columns in [Utopia](<https://en.wikipedia.org/wiki/Utopia_(typeface)>). Verse numbers and running heads are included. The page design follows the layout used by [PTXprint](https://software.sil.org/ptxprint/), a free typesetting program for Bibles.

There is no cover, and the page numbering does not match any historical printed edition.

## Building it yourself

Everything needed to produce the PDF is stored in this repository, including the original source archives. See [CONTRIBUTING.md](CONTRIBUTING.md) for the steps.

## Further reading

- [Edition and source findings](docs/edition.md): how the texts were chosen, arranged, and adjusted
- [Maintenance](docs/maintenance.md): updating dependencies, sources, and layout
- [Verification](docs/verification.md): how the output is checked
- [Visual inspection record](docs/inspection.md): notes from reviewing the printed pages

## License

The build scripts and configuration are released under the [MIT License](LICENSE). The Bible texts themselves are public domain.
