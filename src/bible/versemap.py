"""Map Turpie's Septuagint references to the prepared Brenton verse labels.

Turpie's Septuagint column normally numbers chapters and verses as Brenton
does, Psalm superscriptions included; where they differ, a checked-in,
justified exception names the printed verse, or a run of verses the printed run.
The printed verse may be one of the lettered verses in which Brenton sets apart
a Septuagint addition, as Proverbs 22:8a, but a lettered verse is never part
of a range.

An exception records what a quotation Turpie gives reads, so each must be used.
The edition's own relabelling of Brenton, as of Malachias 3:19-24, needs none:
a reference to a verse the edition no longer prints under that label fails
preparation, and the exception it then needs is justified by Turpie's page.
"""

import re

from bible import paths
from bible.checks import require
from bible.files import read_json

EXCEPTIONS = read_json(paths.EDITION_DIR / "quotations.json")["lxx_to_edition"]
# A verse, or a range of unlettered verses within one chapter.
RANGE = re.compile(r"([1-4]?[A-Z]{2,3}) (\d+):(\d+[a-z]?)(?:-(\d+))?")


def parse(reference):
    """A verse's book, chapter number, and verse label, as "8" or "8a"."""
    match = RANGE.fullmatch(reference)
    require(
        match is not None and match[4] is None,
        f"Malformed verse reference: {reference}",
    )
    return match[1], int(match[2]), match[3]


def expand(reference):
    """Expand a same-chapter verse range; no implicit cross-chapter guess."""
    match = RANGE.fullmatch(reference)
    require(match is not None, f"Malformed quotation passage: {reference}")
    code, chapter, first, last = match.groups()
    if not first.isdigit():
        require(last is None, f"Lettered verse in a range: {reference}")
        return [reference]
    start, stop = int(first), int(last or first)
    require(stop >= start, f"Reversed quotation passage: {reference}")
    return [f"{code} {chapter}:{verse}" for verse in range(start, stop + 1)]


def _mapped_verses():
    """Each excepted verse's printed verse, every exception checked.

    Checked whole, so an exception is refused whether or not a reference
    reaches it, and two that claim one verse can't shadow each other.
    """
    mapped = {}
    for source, exception in EXCEPTIONS.items():
        verses = expand(source)
        targets = expand(exception.get("target", ""))
        require(
            exception.get("why") and len(targets) == len(verses),
            f"Unjustified or misaligned mapping: {source}",
        )
        for verse, target in zip(verses, targets):
            require(verse not in mapped, f"Overlapping mappings of {verse}")
            mapped[verse] = target
    return mapped


def lxx_to_edition(reference):
    """Map one Turpie/Brenton Septuagint verse to the printed edition."""
    code, chapter, verse = parse(reference)
    reference = f"{code} {chapter}:{verse}"
    return _mapped_verses().get(reference, reference)


def mapped_passages(passage):
    """A Septuagint passage's printed Brenton verses, as same-chapter ranges.

    A mapping exception can carry part of a passage into another chapter, so
    one source passage may print as more than one range. A lettered verse
    prints alone.
    """
    runs = []
    for code, chapter, verse in (parse(lxx_to_edition(ref)) for ref in expand(passage)):
        last = runs[-1] if runs else None
        if (
            last
            and last[:2] == [code, chapter]
            and verse.isdigit()
            and last[3].isdigit()
            and int(last[3]) == int(verse) - 1
        ):
            last[3] = verse
        else:
            runs.append([code, chapter, verse, verse])
    return [
        f"{code} {chapter}:{first}" + (f"-{last}" if last != first else "")
        for code, chapter, first, last in runs
    ]


def unused_exceptions(references):
    """The exceptions that no verse of the references reaches."""
    reached = {verse for reference in references for verse in expand(reference)}
    return sorted(
        source for source in EXCEPTIONS if not reached.intersection(expand(source))
    )
