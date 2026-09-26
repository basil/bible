# Editorial notes

The [README](../README.md) describes what's in this Bible. This page explains why it's put together that way. The source files are never modified; every change the build makes is logged in `build/pdf/transformations.json`.

## Texts

- **Old Testament:** [eBible's transcription of Brenton](https://ebible.org/eng-Brenton/), which includes eBible's corrections to the 1870 printing. The corrections are listed in the last appendix. It is neither a facsimile nor the separate "Updated Brenton" translation.
- **New Testament:** [eBible's Cambridge Paragraph Bible](https://ebible.org/engkjvcpb/) (`engkjvcpb`), not its standard KJV (`eng-kjv2006`). Only the 27 books, the translators' dedication to King James, and their preface are used. The text keeps Scrivener's paragraphs and poetry layout.
- **Marginal notes:** [Calvin George's transcription](https://en.literaturabautista.com/exhaustive-listing-marginal-notes-1611-edition-king-james-bible) of the notes in the 1611 King James Bible. Only the 775 New Testament notes are used. The Old Testament notes belong to the KJV's translation from the Hebrew, which this edition doesn't print.

[sources/README.md](../sources/README.md) has the retrieval dates and copyright notices.

## Order and names

The Old Testament follows the [Church of Greece's list of books](https://apostoliki-diakonia.gr/bible/zacharias/). The books that English Bibles set apart as the Apocrypha stay in their places: the Prayer of Manasses follows 2 Chronicles, 4 Maccabees follows 3 Maccabees, and Psalm 151 and the additions to Esther and Daniel stay where Brenton put them.

Brenton's book names are kept, except that the Orthodox names are used for Jesus, the Son of Navi; 1–4 Kingdoms; the Song of Songs; the Lamentations of Jeremias; Ezekiel; and Michaias. Numbered books put the number first, as in "1 Chronicles".

`edition/manifest.json` sets the order and names. Each book, and each piece of front matter or appendix that the edition renames, can have:

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

After Revelation come Brenton's table of chapters in Jeremias, his notes and supplied passages, and eBible's corrections, so that Brenton's material comes before eBible's. Some of these have new headings, which are set in `edition/manifest.json`.

The Cambridge Paragraph Bible's 1873 title page is left out. It advertises Scrivener's introduction and appendices, which aren't in the digital text, and the editor's introduction says so. The traditional notes at the ends of the epistles, such as "Written to the Romans from Corinthus", are kept.

## Notes

No note leaves a mark in the text. Each note is printed as a footnote that begins with its verse's reference and names the words it's about, followed by a colon:

> **25:20** I doubted of such manner of questions: or, _I was doubtful how to enquire hereof_

Labels such as "Or," "Gr." and "Alex." are set in roman, and so are comments. Only another rendering of the words is italic, as in "your: some read, _our_". A note runs on from the colon, so its first word is lowercased, unless it's a name ("Gr.", "Heb.", "Alex.", "A. V."), a reference, in capitals, or in quotation marks; a note on a whole verse, with no words before a colon, keeps its capital. No note ends with a full stop, unless its last word is an abbreviation ("etc.", "so the Heb."). A note that is a sentence of its own is the exception: one that opens with neither a label, a rendering, nor a reference, and has a verb outside its renderings, keeps its capital and ends with a full stop, which George's lowercase 1611 notes are given ("measures: The word Batus in the original containeth nine gallons 3. quarts."). A rendering also takes in the words its lemma was widened by (below), so that it still stands in for the whole lemma: "of your Father: or, _with your Father_". Besides their corrections and the "See" before a cross-reference, these are the only changes the edition makes to the words of the notes. A verse with several notes gets several footnotes, each with the reference: "**9:12** elder: or, _greater_ **9:12** younger: or, _lesser_". Each footnote stands where its note's mark was, so it falls on the page with the words it's about. Brenton's preface, which has no verses, keeps its callers.

### The 1611 marginal notes

The New Testament has the 775 notes from the 1611 King James Bible. George gives the words each note is about, and the build finds them in the verse, ignoring case, punctuation, and markup. If they occur more than once in the verse, the build adds the next words until they occur only once, and adds the same words to the rendering: "of: or, _with_" in Matthew 6:1 becomes "of your Father: or, _with your Father_". It does the same to words that end on one like "of" or "the", but a single preposition or conjunction that occurs once stands alone: "for: or, _unto_" (Mark 1:4).

For 115 notes, `edition/kjv-notes.json` says where the note belongs or what it prints, with the reason for each choice. Usually the spelling differs (boysterous, council, thyine), or the words appear more than once in the verse. Two notes that George lists under 1 Corinthians 10:6 and Galatians 4:24 actually belong to 10:4 and 4:25.

The same file makes eleven corrections to George's text:

- His own bracketed remarks are removed (Matthew 5:15, Mark 14:72, Revelation 20:13). The 1611's misprint "began to wept" in Mark 14:72 is corrected to "weep".
- The Greek he left out is restored from the 1611 margin (Acts 13:18 and 13:34).
- Six slips are fixed: "debtOr" in Matthew 23:18, "mat." for "Mat." in Mark 6:8, "or" for "Or," in Romans 9:33, "O," for "Or," in 2 Corinthians 3:18, "Ceasars" in Philippians 1:13, which becomes "Cesars" to match the 1611 and this text, and "being weary" for the 1611's "being wary" in Hebrews 11:7.

### Brenton's notes

Brenton's 2,595 notes and 150 cross-references record only where his mark stood, just before the words the note is about. The build works out how far those words reach:

- A note that renders the words differently is measured by that rendering. If its last word, or a form of it, comes shortly after the mark, the words end there ("Gr. _glean you_" is about "strip you"). Otherwise they run as many words as the rendering has ("Gr. _chief cook_" is about "captain of the guard"), stopping at punctuation and never ending on a word like "the", "his" or "of", unless the rendering is one such word for another: "Alex. _their_" is about "his", and "Gr. _upon_" is about "into" if "into" occurs only once in the verse. If the rendering's first word stands just before the mark, the words take it in ("Alex. _the Chorrhæan_" is about "the Evite").
- A note that comments rather than renders is about its clause, or its first four words if the clause is longer than six.
- A note at the end of a verse is about the words before it if it renders them, and about the whole verse if it doesn't.
- A cross-reference within the first three words of its verse needs no words; the New Testament quotes the verse. Later in the verse, the words show where the quotation begins: its clause, or its first four words if the clause is longer than eight. Each cross-reference is printed as a footnote of "See" and its reference.

Like the 1611 notes, the words are extended until they occur only once in the verse, and the rendering with them ("your: Gr. _thy_" becomes "your soul: Gr. _thy soul_"). Where the rules' words were too few, so that the rendering already covers the words added ("was moved: Gr. _repented_"), the lemma is given as an exception, which the rendering doesn't take in. An exception's lemma that occurs more than once in the verse names its occurrence, and is widened like the rules' ("explore", the first of two in Joshua 18:8, prints "to explore: or, _to walk through_").

Brenton set his labels in italic, and eBible marks them the same way as the words he cites in italic. The build tells them apart by the label names, and italicizes what follows a label unless it's a comment ("probably", "has the following", "from the Heb.", a verse reference, or quoted Greek or Hebrew). English after quoted Greek is a rendering ("Alex. ἐντολαί, _commands_"), and so are the words a note quotes as added ("Heb. and Alex. insert '_priest_'").

`edition/brenton-notes.json` corrects the rules in 763 places, with the reason for each: 682 notes get other words, 108 get other italics, and one that reads as a sentence is printed as none. Often Brenton's mark follows the words it's about instead of preceding them, as in Genesis 2:19, or the rendering is shorter or longer than the words it replaces. Two kinds of correction follow a convention of their own. After "i. e.", "q. d.", "sc." or "That is," the words are italic only if they could stand in place of the words the note is about ("son of Jemeni: i. e. _Benjamite_") or name what a pronoun stands for ("sc. _the people_"); an explanation that adds to them stays roman ("instruct: sc. as a law-giver"). A note that records words a manuscript adds is about the words they follow, since those show where they go ("Tell us: Alex. + '_for those whose cause this evil is upon us_'").

The same file corrects 24 slips in eBible's text, among them a doubled "Gr." in Genesis 21:11, an empty note in 3 Kingdoms 6:1, eBible's own remark inside a note in Proverbs 11:10, misspellings such as "appeaars" and "nanda" for "hands", missing full stops, and missing word spaces, as in Exodus 21:28 ("he or she"), Ezekiel 11:7 ("thiscity"), and Brenton's preface, where "There is" printed as "There<sup>a</sup>is".

`make notes-review` lists every note with the words it's about and its italics in `build/notes-review.md`, and those that changed since the last review in `build/notes-review-changes.md`.

## Typography

- Words the translators supplied, which many Bibles print in italics, are set in ordinary type.
- Brenton's transcription mixes curly and straight quotation marks. The build converts the straight ones with [SmartyPants](https://pypi.org/project/smartypants/), then checks that nothing changed except quotation marks, dashes, and ellipses. The two backtick quotes in Proverbs 21:18 are handled separately. The Cambridge text already has curly quotes, and the edition's own pages are typed with them.
- The text is set in Utopia, with verse numbers in the superscript figures of Erewhon, a font based on Utopia. Greek is set in GFS Didot and Hebrew in Ezra SIL.

## Known issues

- At the last check, the title of the Jeremias table was cramped, with its word spaces squeezed.
