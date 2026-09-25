# Brenton-KJV Bible

A complete English Bible, typeset as a single book and ready to print or read on screen.

**[Read the finished Bible (PDF)](https://basil.github.io/bible/bible.pdf)**

## What is in it

The Old Testament is Sir Lancelot Brenton's 1870 English translation of the Septuagint, arranged in the order followed by the Church of Greece. The New Testament is the King James Version from the _Cambridge Paragraph Bible_ prepared by F. H. A. Scrivener in 1873.

The book reads in this order:

1. Title page, a table of contents, and the editor's introduction
2. The Old Testament, opening with Brenton's preface (1844), introduction (1870), introduction to the Apocrypha, and list of abbreviations; 4 Maccabees follows 3 Maccabees among its books
3. The New Testament, opening with the King James translators' dedication to the king and their preface, "The Translators to the Reader"
4. Appendices: Brenton's table comparing chapter order in Jeremias, his notes and supplied passages, and eBible's corrections to the text

The Old Testament books are called by their Septuagint names: Esaias rather than Isaiah, Jesus, the Son of Navi rather than Joshua, and 1–4 Kingdoms rather than Samuel and Kings.

Both translations are in the public domain. The texts are taken from [eBible.org](https://ebible.org/), and the original copyright notices are kept with the source files in this repository.

## How it looks

The page size is A5, about the size of a paperback novel. Scripture is set in two columns in Utopia. Footnotes, verse numbers, and running headers are included. The page design follows the layout used by PTXprint, a free typesetting program for Bibles.

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
