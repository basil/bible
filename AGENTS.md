# Working on this repository

This is a hobby project that prepares a printed Bible from two pinned sources. Keep it small and understandable: prefer deleting to adding, and a plain function to a new abstraction. [CONTRIBUTING.md](CONTRIBUTING.md) explains how the edition is built and where each kind of change goes; read it before changing anything.

## Principles

Hold every change to these.

- **Separate the concerns, and change nothing in place.** The build is the fixed sequence of stages in `src/bible/pipeline.py`. Each stage is a function of the stages before it and of the policy, which is read once and frozen. A stage builds what it changes and shares the rest; it never alters a document, the policy or a source it was given.
- **Make transformations simple to write, read and trust across the whole corpus.** A rule applies everywhere, and what departs from it is a decision in `edition/*.json` with its reason as `why`. A decision that no longer fits its source, changes nothing, or is met by nothing stops the build and names itself. Refuse what a transformation does not understand rather than guess at it.
- **Decide on meaning, not on rendered output.** Work on the USJ document and on the words of a verse, not on serialized USFM, exported text or the PDF. A regular expression over markup is a sign the decision is in the wrong place.
- **Marshal at the boundaries.** USFM is parsed once, when the sources are read, and written once, for PTXprint. Between those two ends everything is USJ, extended only by `x-key` and `x-scope`. Do not add a second document model or a new extension without need.
- **Run transformations in the order of their dependencies.** A new transformation goes in the stage where everything it reads is ready, and nothing reaches back to an earlier stage's work. The revision of spelling and punctuation is made last, so every other decision is still written in the sources' own words.
- **Use semantic markup, not hard-coded strings.** Build USJ nodes rather than backslash markers in strings. Take terms and abbreviations from `edition/terminology.json`, and books and their names from the manifest and `edition/citations.json`, rather than writing them into the code.
- **Keep checked-in data normalized.** State each fact once. Do not check in what the build can derive, and do not copy a source's words into a decision unless the build verifies the copy against the source, so that it cannot drift unnoticed. Keys are the short source keys (`GEN 1:9#2`), not hashes.
- **Revise spelling and punctuation in one place.** The edition's revision of the translation, along the lines of the New Cambridge Paragraph Bible, lives in `edition/revisions.json`: a word respelt everywhere it is printed (Jezekiel to Ezekiel), or changes to single verses, grouped under the reason they share. Do not respell the sources, the other decision files or the code to the same end.

## Checking a change

The book should come out the same except where the change means it to differ.

```sh
make test                    # the whole suite
make review-diff BASE=HEAD   # every line of the edition the working tree changes
make pdf                     # the book itself, with the layout checks
```

Read `build/review.diff` after any change to a transformation or a decision: an unintended effect shows there as an extra line. Explain every intended difference when you report the work.
