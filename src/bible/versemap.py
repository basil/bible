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

from bible import paths
from bible.checks import require
from bible.files import read_json
from bible.references import parse_passage, runs

EXCEPTIONS = read_json(paths.EDITION_DIR / "quotations.json")["lxx_to_edition"]


def _mapped_verses():
    """Each excepted verse's printed verse, every exception checked.

    Checked whole, so an exception is refused whether or not a reference
    reaches it, and two that claim one verse can't shadow each other.
    """
    mapped = {}
    for source, exception in EXCEPTIONS.items():
        verses = parse_passage(source).verses
        targets = parse_passage(exception.get("target", "")).verses
        require(
            exception.get("why") and len(targets) == len(verses),
            f"Unjustified or misaligned mapping: {source}",
        )
        for verse, target in zip(verses, targets):
            require(verse not in mapped, f"Overlapping mappings of {verse}")
            mapped[verse] = target
    return mapped


def lxx_to_edition(verse):
    """Map one Turpie/Brenton Septuagint verse to the printed edition."""
    return _mapped_verses().get(verse, verse)


def mapped_passages(passage):
    """A Septuagint passage's printed Brenton verses, as same-chapter ranges.

    A mapping exception can carry part of a passage into another chapter, so
    one source passage may print as more than one range. A lettered verse
    prints alone.
    """
    return runs(lxx_to_edition(verse) for verse in passage.verses)


def unused_exceptions(passages):
    """The exceptions that no verse of the passages reaches."""
    reached = {verse for passage in passages for verse in passage.verses}
    return sorted(
        source
        for source in EXCEPTIONS
        if not reached.intersection(parse_passage(source).verses)
    )
