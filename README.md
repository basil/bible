# Brenton-KJV Bible

A complete English Bible, typeset as a single book and ready to print or read on screen.

**[Read the finished Bible (PDF)](https://basil.github.io/bible/bible.pdf)**

## What is in it

The Old Testament comes from Sir Lancelot Brenton's 1870 English translation of the Septuagint, the ancient Greek Old Testament. Its books are divided and arranged in the order used by the Church of Greece. The New Testament is the King James Version, in the Cambridge Paragraph edition prepared by F. H. A. Scrivener in 1873.

The book reads in this order:

1. Title page, a statement of sources, and a table of contents
2. Brenton's list of abbreviations and his 1870 introduction
3. The King James translators' dedication to the king and their preface, "The Translators to the Reader"
4. The Old Testament, followed by 4 Maccabees as an appendix
5. The New Testament
6. Brenton's introduction to the Apocrypha and his historical appendices: his 1844 preface, errata, and a table comparing chapter order in Jeremiah

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
