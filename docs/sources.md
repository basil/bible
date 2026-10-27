# Source ingestion

This unpublished guide describes the boundary between pinned evidence and prepared documents. The reader-facing scholarly account is in [the introduction](../content/introduction.sfm); maintainer conventions, including note substitution, citations, abbreviations, and vocabulary, are in [the house-style checklists](house-style.md), with [New Testament house style and review cases](new-testament.md#the-english-house-style). [The source catalogue](../sources/README.md) records downloads, versions, and notices; keep that information there rather than copying it into this guide.

## Loading and parsing

[`sources.load`](../src/bible/sources.py) checks every registered SHA-256 before conversion. It reads archive contents and authored pages into memory. `byzantine_inputs` selects the members each reader needs and converts the RP2026 PDF with `pdftohtml` and Robinson's collation with `pdftotext`. Their parsers check inventories as well as syntax: for example, the collation has 1,885 rows, Boyd's Greek apparatus 1,948 TR-bearing notes, and the printed RP apparatus 1,735 TR and 150 SCR entries. Treat a changed count as an ingestion investigation, not a reason to loosen the check.

[`pipeline.read`](../src/bible/pipeline.py) repairs Brenton's transcription before parsing it as USJ, then assigns source-note keys before supplementing its notes from CCEL. Every Brenton source is accounted for by the manifest or an explicit exclusion. The King James parser reads the books printed, borrowed from, or needed for verse placement; book and chapter inventories for the remaining files are read without parsing their complete documents.

George's marginal-note listing is read from its New Testament boundary. The reader checks the 775-note inventory, consumes every correction, and rejects remaining bracketed transcriber remarks. The Cambridge scripture used for those books must itself contain no notes. The separate reconciliation is described in [new-testament.md](new-testament.md).

## Repairs and their addresses

[`repairs.py`](../src/bible/repairs.py) requires a correction's `from` to occur once in its target and not occur within its `to`. It recognizes specific slips, including a missing space, a letter or punctuation error, doubled text, a bracketed remark, a missing note, and omitted Greek. An unrecognized correction requires `uncategorized: true`; a recognized one must not retain that flag.

For Brenton's scripture, a repair outside notes may only preserve the wording while mending spacing, or restore a complete missing note. A repair inside a note cannot cross its boundary. The broader slip categories do not permit rewriting scripture. Corrections in `edition/brenton-notes.json` and `edition/kjv-notes.json` operate on their source wording; later spelling and punctuation rules belong in `edition/revisions.json`.

A Brenton note key names its source verse and note number; a marginal-note key includes its source lemma. CCEL has two addresses with different uses:

| Address | Use |
| --- | --- |
| Page and caller, such as `14.iii#7` | HTML transcription corrections and placement, duplication, or omission decisions in `edition/ccel-notes.json`. |
| Source verse and `CCEL`, optionally numbered | The placed note's `x-key`, used by later note and Alexandrinus decisions. |

CCEL candidates receive their verse-local numbers before duplicate and omission dispositions, so suppressing a candidate does not renumber the others. eBible's notes have already been keyed and keep their addresses.

## CCEL placement and duplicate detection

[`ccel.py`](../src/bible/ccel.py) reads page text with callers and note bodies, decodes the legacy Greek and Hebrew fonts, and applies declared note-body repairs. Its scripture words locate callers; they never replace eBible's scripture.

`Finder` ranks possible chapters by shared vocabulary weighted toward rarer words. `chapter_of` aligns each qualifying chapter and selects the best alignment. Equal alignments must place the callers identically or the build stops. A caller is placed before its following word, or at the verse end when it closes that verse. A declared placement supplies a verse and unique anchor only when it differs from automatic placement.

`same_notes` first compares Unicode-normalized text at the same caller word, then compares words with punctuation and capitals removed and citations resolved to their targets. It also accounts for identical eBible notes explicitly moved into the printed verse. A duplicate decision names the retained source note and is rejected if automatic matching already accounts for it.

Unreadable bodies and callers the words cannot place are left out and reported. Do not add an omission decision for a note already excluded this way. An unreadable note mentioning Alexandrinus or the Appendix instead requires a transcription correction. Readable notes mentioning either are held for an Alexandrinus decision; notes on words promotion supplies are deferred until those words exist. The read-stage report accompanies the documents through promotion.

When investigating a mismatch, inspect `build/review/ccel.md`: it identifies the page caller, placed key, caller words, both texts for a duplicate, and the reason a note was held or left out. Verify the printed evidence and record the printing, physical page, and printed page in a decision's reason. Historical note counts from an older review are not ingestion invariants.

## Other source-dependent work

`matter.py` splits and prepares front and back matter using `edition/prose.json`. Restored paragraphs are USJ nodes inserted after an exact, unique source paragraph. The Brenton 1851 scan is checksum-verified evidence for the recorded restoration; the build does not OCR it. The Appendix is read for promoted readings and notes, then its separately placed notes are attached during annotation; it is excluded from printed front matter.

`lines.py` aligns the Updated Brenton's chapter words with the assembled source and transfers line and stanza boundaries without importing its wording. Scrivener's corresponding verses supply the second poetry witness where one exists. Ambiguous or unplaced boundaries require `edition/lines.json`; a prose exception must suppress otherwise retained poetry. Paragraph and unspaced decisions have separate validation. The New Testament keeps Scrivener's paragraphs, the extent of his poetry, and his stanza breaks; it keeps his lines too, except where a `new_testament` decision in `edition/lines.json` sets a verse's line divisions and indentation, using the Berean Standard Bible as a model adapted to the King James wording. The Berean supplies no wording and is not a build input. The decisions act on the assembled, unrevised USJ and preserve its words, styles, notes, and verse numbers; a decision that keeps Scrivener's lines is refused. The Old Testament's lines are indented in the same stage, after the Psalter's divisions. Chapter-opening prose is normalized in both testaments.

Keep source-dependent decisions in source wording and at the stage that owns them. After assembly, references use the edition's numbers: see [numbering.md](numbering.md). The USJ model, export boundary, and required review checks are in [AGENTS.md](../AGENTS.md); adding another parser or a rendered-text workaround would bypass those boundaries.
