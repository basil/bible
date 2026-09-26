# Editorial notes

The [README](../README.md) describes what's in this Bible. This page explains why it's put together that way. The source files are never modified; every change the build makes is logged in `build/full/transformations.json`.

## Texts

- **Old Testament:** [eBible's transcription of Brenton](https://ebible.org/eng-Brenton/), which includes eBible's corrections to the 1870 printing. The corrections are listed in the last appendix. It is neither a facsimile nor the separate "Updated Brenton" translation.
- **New Testament:** [eBible's Cambridge Paragraph Bible](https://ebible.org/engkjvcpb/) (`engkjvcpb`), not its standard KJV (`eng-kjv2006`). Only the 27 books, the translators' dedication to King James, and their preface are used. The text keeps Scrivener's paragraphs and poetry layout.
- **Marginal notes:** [Calvin George's transcription](https://en.literaturabautista.com/exhaustive-listing-marginal-notes-1611-edition-king-james-bible) of the notes in the 1611 King James Bible. Only the 775 New Testament notes are used. The Old Testament notes belong to the KJV's translation from the Hebrew, which this edition doesn't print.

[sources/README.md](../sources/README.md) has the retrieval dates and copyright notices.

## Order and names

The Old Testament follows the [Church of Greece's list of books](https://apostoliki-diakonia.gr/bible/zacharias/). The books that English Bibles set apart as the Apocrypha stay in their places: the Prayer of Manasses follows 2 Chronicles, 4 Maccabees follows 3 Maccabees, and Psalm 151 and the additions to Esther and Daniel stay where Brenton put them.

Brenton's book names are kept, except that the Orthodox names are used for Jesus, the Son of Navi; 1–4 Kingdoms; the Song of Songs; the Lamentations of Jeremias; Ezekiel; and Michaias. Numbered books put the number first, as in "1 Chronicles".

`config/edition.json` sets the order and names. Each book, and each piece of front matter or appendix that the edition renames, can have:

- `title`: the full title, printed in the contents, as in "The First Book of Moses, Called Genesis". Every book has one; front matter without one keeps its source's names.
- `short_title`: used in the running heads, as in "3 Kingdoms". Defaults to the source's.
- `abbreviation`: not printed, but kept consistent. Defaults to the source's.
- `heading`: how the full title breaks into lines at the start of the book. The lines must spell out `title` exactly. Without it, the title is printed on one line.

## Titles and headings

Every book gets a full title in the style of the Cambridge Paragraph Bible, adapted to this edition's names and extended to books the Cambridge Bible doesn't have: "The Book of Jesus, the Son of Navi", "The Third Book of Kingdoms, Otherwise Called, The First Book of the Kings". Where the Cambridge Bible breaks a heading over several lines, this edition does the same. These headings replace Brenton's own subtitles, such as "(1 SAMUEL)".

Where Cambridge punctuation disagrees with the pattern, the pattern wins. For example, Sirach gets a comma after "Jesus" to match "Jesus, the Son of Navi".

In the New Testament, "S." is written out as "Saint", Paul's letters are titled "of Saint Paul", and the letters of James, Peter, John, and Jude are called Catholic Epistles, as in the Greek tradition. No title or heading ends with a period.

## Ezra and Nehemiah

eBible's Brenton has two overlapping files: "Ezra and Nehemiah" (23 chapters) and a separate "Nehemiah" (13 chapters). The edition uses the first, printing chapters 1–10 as 2 Esdras and chapters 11–23 as Nehemias 1–13. The two files aren't identical: they differ in paragraphing, small capitals, spellings like Raphæa and Raphaea, and one verse label. `make validate` writes the full comparison to `build/nehemias-differences.diff`.

## Daniel

Following the Church of Greece, Susanna comes before Daniel 1 and Bel and the Dragon after Daniel 12, each as a titled section. Internally they're chapters 0 and 13, but those numbers aren't printed.

The Song of the Three Children gets its own heading but keeps Brenton's numbering as Daniel 3:24–90. The Church of Greece numbers it separately as verses 1–67, but Brenton merges some of those verses and lacks others, so renumbering would suggest a match that isn't there.

## Malachias

Brenton's Malachias 3:19–24 is printed as chapter 4, verses 1–6, which matches the [Church of Greece's text](https://apostoliki-diakonia.gr/bible/malachias/?file=42.4) and most English Bibles.

## Front matter and appendices

The contents come right after the title page, as in most books, followed by the editor's introduction. The introduction is set like a book of the Bible so that it's listed in the contents.

Each testament opens with the front matter of its own translation, so that the introductions sit next to the text they describe:

- **Old Testament:** Brenton's preface (1844), his introduction (1870), his introduction to the Apocrypha, and his list of abbreviations. The introduction to the Apocrypha belongs here rather than after Revelation, because those books are part of this Old Testament.
- **New Testament:** the translators' dedication to King James and their preface, "The Translators to the Reader".

After Revelation come Brenton's table of chapters in Jeremias, his notes and supplied passages, and eBible's corrections, so that Brenton's material comes before eBible's. Some of these have new headings, which are set in `config/edition.json`.

The Cambridge Paragraph Bible's 1873 title page is left out. It advertises Scrivener's introduction and appendices, which aren't in the digital text, and the editor's introduction says so. The traditional notes at the ends of the epistles, such as "Written to the Romans from Corinthus", are kept.

## New Testament marginal notes

The 1611 notes are printed as footnotes in the same style as Brenton's: "Or," and "Gr." are set as labels, and a note gets a closing period unless it ends with a question mark. As in the 1611 printing, the note's caller goes just before the words it's about. George gives those words for each note, and the build finds them in the verse, ignoring case, punctuation, and markup. It never puts a caller inside words the translators supplied.

For 61 notes, that search doesn't find exactly one match, so `config/marginal-notes.json` says where the caller goes, with the reason for each choice. Usually the spelling differs (boysterous, council, thyine), or the words appear more than once in the verse, like "of" in Matthew 6:1. Two notes that George lists under 1 Corinthians 10:6 and Galatians 4:24 actually belong to 10:4 and 4:25.

The same file makes seven corrections to George's text:

- His own bracketed remarks are removed (Matthew 5:15, Mark 14:72, Revelation 20:13). The 1611's "began to wept" in Mark 14:72 is kept.
- The Greek he left out is restored from the 1611 margin (Acts 13:18 and 13:34).
- Two slips are fixed: "debtOr" in Matthew 23:18, and "Ceasars" in Philippians 1:13, which becomes "Cesars" to match the 1611 and this text.

## Typography

- Words the translators supplied, which many Bibles print in italics, are set in ordinary type.
- Brenton's transcription mixes curly and straight quotation marks. The build converts the straight ones with [SmartyPants](https://pypi.org/project/smartypants/), then checks that nothing changed except quotation marks, dashes, and ellipses. The two backtick quotes in Proverbs 21:18 are handled separately. The Cambridge text already has curly quotes, and the edition's own pages are typed with them.
- The text is set in Utopia, with verse numbers in the superscript figures of Erewhon, a font based on Utopia. Greek is set in GFS Didot and Hebrew in Ezra SIL.

## Known issues

- In Brenton's preface, "There is" prints as "There<sup>a</sup>is", with the footnote caller joined to the next word. The eBible text has no space there, and this edition leaves it as it is.
- At the last check, the title of the Jeremias table was cramped, with its word spaces squeezed.
