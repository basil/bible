"""Citations read as each source writes them, into the edition's verses."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any, Protocol, Unpack

import pytest
from conftest import changed

import bible.annotate
import bible.citations
import bible.pipeline
import bible.policy
import bible.references
import bible.sources
from bible import annotate, citations, matter, notes, pipeline, usj
from bible.checks import CheckFailed
from bible.policy_schema import CitationsDecisions
from bible.references import parse_verse

HOME = parse_verse("JDG 13:8")
# Names for books whose numbering is read here, which the dialects lack.
MORE = {
    "brenton": {"Mal": "MAL"},
    "george": {"Joel": "JOL", "Psal": "PSA", "Jer": "JER", "Mal": "MAL"},
}


class Cite(Protocol):
    def __call__(
        self,
        text: str,
        dialect: str | None = "brenton",
        decided: CitationsDecisions | Sequence[CitationsDecisions] | None = None,
        home: bible.references.Verse | None = HOME,
    ) -> list[citations.Citation]: ...


@pytest.fixture(scope="module")
def cite(policy: bible.policy.Policy, ctx: bible.annotate.Context) -> Cite:
    """Read a text's citations as a note on Judges 13:8 has them."""

    def cite(
        text: str,
        dialect: str | None = "brenton",
        decided: CitationsDecisions | Sequence[CitationsDecisions] | None = None,
        home: bible.references.Verse | None = HOME,
    ) -> list[bible.citations.Citation]:
        tongue = citations.dialect(dialect, policy=policy)
        more = MORE.get(dialect, {}) if dialect else {}
        tongue = replace(tongue, books={**tongue.books, **more})
        selected = [decided] if isinstance(decided, dict) else decided
        return citations.scan(
            text, tongue, home, "x", ctx.inventory, selected, policy=policy
        )

    return cite


def decision(**fields: Unpack[CitationsDecisions]) -> CitationsDecisions:
    return {"why": "x", **fields}


def named(found: list[bible.citations.Citation]) -> str:
    """What each citation names, a chapter as its book and number."""
    return " | ".join(
        "; ".join(
            str(item.passage(book) or f"{book} {item.chapter}")
            for book, runs in citation.targets
            for run in runs
            for item in run
        )
        for citation in found
    )


def printed(
    text: str, found: list[bible.citations.Citation], books: bible.references.Books
) -> str:
    """The text with each citation as the edition prints it."""
    for citation in reversed(found):
        words = citations.printed(citation, books)
        text = text[: citation.start] + words + text[citation.end :]
    return text


# A text, what its citations name, and how it prints.
BRENTON = [
    ("See Rom. 4. 7,8.", "ROM 4:7; ROM 4:8", "See Romans 4:7, 8."),
    ("See Heb. 2. 6-9.", "HEB 2:6-9", "See Hebrews 2:6–9."),
    ("See 1 Cor 2. 16. Gr.", "1CO 2:16", "See 1 Corinthians 2:16. Gr."),
    (
        "See Lev. 23. 6; Num. 29. 35; 2 Chr. 7. 9.",
        "LEV 23:6 | NUM 29:35 | 2CH 7:9",
        "See Leviticus 23:6; Numbers 29:35; 2 Chronicles 7:9.",
    ),
    (
        "Jer. 40. 10,12;also 1 Cor. 12. 15,16.",
        "JER 40:10; JER 40:12 | 1CO 12:15; 1CO 12:16",
        "Jeremias 40:10, 12;also 1 Corinthians 12:15, 16.",
    ),
    # Brenton's Kings are the four books of Kingdoms, under the edition's names.
    ("See on 3 Kings 8. 53.", "1KI 8:53", "See on 3 Kingdoms 8:53."),
    ("See Hab. 2. 3.", "HAB 2:3", "See Abbacum 2:3."),
    # A chapter, several, and the last verse of one; one psalm is a Psalm.
    ("as in Gen. 43.", "GEN 43", "as in Genesis 43."),
    ("See also Ps. 68; 79, titles", "PSA 68; PSA 79", "See also Psalms 68; 79, titles"),
    ("See Ps. 118. 32.", "PSA 118:32", "See Psalm 118:32."),
    ("See Col. 2. ult.", "COL 2:23", "See Colossians 2:23."),
    # By Brenton's number for a verse the edition relabels, and for one that
    # a decision could say is cited by the King James Bible's.
    ("See Mal. 3. 23.", "MAL 4:5", "See Malachias 4:5."),
    ("Comp. Jer. 9. 24.", "JER 9:24", "Comp. Jeremias 9:24."),
    # A note cites its own book by a verse or chapter, and keeps its capital.
    ("See ver. 6.", "JDG 13:6", "See verse 6."),
    ("See v 8, 9.", "JDG 13:8; JDG 13:9", "See verses 8, 9."),
    ("For vv. 2-5, see above.", "JDG 13:2-5", "For verses 2–5, see above."),
    ("Verses 5 to 8 are read.", "JDG 13:5-8", "Verses 5–8 are read."),
    ("Verse 5 is read.", "JDG 13:5", "Verse 5 is read."),
    ("See chap 6. 13,15.", "JDG 6:13; JDG 6:15", "See chapter 6:13, 15."),
    ("See ch. 10. 12.", "JDG 10:12", "See chapter 10:12."),
    ("See chap 5. 25; 14. 16.", "JDG 5:25; JDG 14:16", "See chapter 5:25; 14:16."),
    ("See chapter 20.", "JDG 20", "See chapter 20."),
    # Figures alone are no citation.
    ("Alex. 187 years.", "", "Alex. 187 years."),
    ("Alex. 62,500.", "", "Alex. 62,500."),
    ("Heb. and Alex. 60 cubits.", "", "Heb. and Alex. 60 cubits."),
    ("p. 92.", "", "p. 92."),
]
# The margin of 1611 cites as the King James Bible does.
GEORGE = [
    ("as Mat. 18.28", "MAT 18:28", "as Matthew 18:28"),
    ("1. Cor. 8.11", "1CO 8:11", "1 Corinthians 8:11"),
    ("Gr. made, 1 Sam. 12.6", "1SA 12:6", "Gr. made, 1 Kingdoms 12:6"),
    ("Esai 55.3", "ISA 55:3", "Esaias 55:3"),
    # A book the King James Old Testament lacks is numbered as it stands.
    ("2. Macc 7.27", "2MA 7:27", "2 Maccabees 7:27"),
    # Its numbering is carried verse by verse, into two places where the
    # edition has the verses apart.
    ("Joel 2.28-32", "JOL 3:1-5", "Joel 3:1–5"),
    ("Psal. 34.12-16", "PSA 33:13-17", "Psalm 33:13–17"),
    ("Jer. 25.13-16", "JER 25:13; JER 32:15-16", "Jeremias 25:13; 32:15–16"),
    ("Mal. 4.4-6", "MAL 4:6; MAL 4:4-5", "Malachias 4:6, 4–5"),
]


@pytest.mark.parametrize(
    "dialect,text,names,prints",
    [
        *(("brenton", *row) for row in BRENTON),
        *(("george", *row) for row in GEORGE),
        # Brenton's preface numbers its chapters in Roman.
        ("brenton-preface", "by Gen. xlvii. 31.", "GEN 47:31", "by Genesis 47:31."),
    ],
)
def test_a_source_cites_in_its_own_way(
    cite: Cite,
    ctx: bible.annotate.Context,
    dialect: str,
    text: str,
    names: str,
    prints: str,
) -> None:
    found = cite(text, dialect)
    assert named(found) == names
    assert printed(text, found, ctx.books) == prints


SEVERAL: CitationsDecisions = {
    "source": "Zac. 3.8 esay 11.1",
    "passages": "ZEC 3:8; ISA 11:1",
}


@pytest.mark.parametrize(
    "text,decided,prints",
    [
        # By another numbering than the source's: the King James Bible's, the
        # Greek psalm with the English verse, and the Hebrew psalm.
        (
            "Comp. Jer. 9. 24.",
            decision(source="Jer. 9. 24", numbering="kjv"),
            "Comp. Jeremias 9:23.",
        ),
        (
            "see Ps. 91. 10.",
            decision(source="Ps. 91. 10", numbering="kjv-verses"),
            "see Psalm 91:11.",
        ),
        (
            "See Ps. 110.",
            decision(source="Ps. 110", numbering="hebrew"),
            "See Psalm 109.",
        ),
        # Figures that are no citation stay as they are.
        (
            "Heb. 300. Alex. 500.",
            decision(source="Heb. 300", not_a_citation=True),
            "Heb. 300. Alex. 500.",
        ),
        # What the edition doesn't print is cited as the decision prints it.
        (
            "Ver. 99 is not in Vat.",
            decision(source="Ver. 99", unprinted=True, print="Verse 99"),
            "Verse 99 is not in Vat.",
        ),
        # A decision may name the passages itself, of several books as one,
        # under the edition's names for them.
        (
            "Vide supra, 13. 22.",
            decision(source="13. 22", passages="ISA 13:22", print="13:22"),
            "Vide supra, 13:22.",
        ),
        (
            "branch, Zac. 3.8 esay 11.1",
            decision(
                source=SEVERAL["source"],
                passages=SEVERAL["passages"],
                print="{ZEC} 3:8; {ISA:upper} 11:1",
            ),
            "branch, Zacharias 3:8; ESAIAS 11:1",
        ),
    ],
)
def test_a_decision_reads_what_the_grammar_cannot(
    cite: Cite,
    ctx: bible.annotate.Context,
    text: str,
    decided: CitationsDecisions,
    prints: str,
) -> None:
    assert printed(text, cite(text, decided=decided), ctx.books) == prints


@pytest.mark.parametrize(
    "dialect,text,decided,refusal",
    [
        # What looks like a citation is read or refused.
        ("brenton", "See Nowhere 1. 1", None, r"can't be read: x \(1. 1\)"),
        ("brenton", "See Heb. 2. 6-9-11", None, r"can't be read: x \(2. 6\)"),
        ("brenton", "Vide supra, 13. 22.", None, r"can't be read: x \(13. 22\)"),
        ("brenton", "See chap. x. 9", None, r"can't be read: x \(x. 9\)"),
        # A unit that cites nothing has no dialect, which reads no book.
        (None, "See Rom. 4. 7.", None, r"can't be read: x \(4. 7\)"),
        # What is cited must be printed, whatever book a decision says it is of.
        ("brenton", "See Rom. 17. 1.", None, r"n't print: x \(Rom. 17. 1: ROM 17\)"),
        ("brenton", "See Rom. 16. 27,28.", None, r"\(Rom. 16. 27,28: ROM 16:28\)"),
        ("brenton", "See ver. 99.", None, r"\(ver. 99: JDG 13:99\)"),
        ("brenton", "Heb. 300. Alex. 500.", None, r"\(Heb. 300: HEB 300\)"),
        ("george", "Jer. 33.14-16", None, "Verses the edition lacks: JER 33:14-16"),
        (
            "brenton",
            "branch, Zac. 3.8 esay 11.1",
            decision(source=SEVERAL["source"], passages="ZEC 3:8; ISA 99:1", print="x"),
            "doesn't print: x .*ISA 99",
        ),
        # The Hebrew's verses aren't the King James Bible's: none is carried.
        (
            "brenton",
            "See Ps. 110. 3.",
            decision(source="Ps. 110. 3", numbering="hebrew"),
            "Verses by the Hebrew's numbering",
        ),
    ],
)
def test_what_cannot_be_read_or_is_not_printed_is_refused(
    cite: Cite,
    dialect: str | None,
    text: str,
    decided: CitationsDecisions | None,
    refusal: str,
) -> None:
    with pytest.raises(CheckFailed, match=refusal):
        cite(text, dialect, decided)


JER = "Jer. 9. 24"


@pytest.mark.parametrize(
    "decided,refusal",
    [
        ({"source": JER, "numbering": "kjv"}, "without a reason"),
        (decision(source="Jer. 9. 25", numbering="kjv"), "not found once"),
        (decision(source=JER), "decides nothing, or too much"),
        (decision(source=JER, numbering="kjv", print="x"), "nothing, or too much"),
        (decision(source=JER, numbering="brenton"), "of no other numbering"),
        (decision(source=JER, numbering="english"), "of no other numbering"),
        (decision(source="Comp.", numbering="kjv"), "of no other numbering"),
        (decision(source=JER, passages="JER 9:23"), "prints nothing"),
        (
            [
                decision(source=JER, numbering="kjv"),
                decision(source="9. 24", not_a_citation=True),
            ],
            "decisions that overlap: x",
        ),
    ],
)
def test_a_malformed_decision_is_refused(
    cite: Cite,
    decided: CitationsDecisions | Sequence[CitationsDecisions],
    refusal: str,
) -> None:
    with pytest.raises(CheckFailed, match=refusal):
        cite("Comp. Jer. 9. 24.", decided=decided)


def test_a_dialect_says_how_it_numbers(policy: bible.policy.Policy) -> None:
    unnumbered = changed(
        policy, "citations", lambda data: data["dialects"]["brenton"].pop("numbering")
    )
    with pytest.raises(CheckFailed, match="without its numbering or numerals"):
        citations.dialect("brenton", policy=unnumbered)


def test_every_decision_and_name_must_be_met(
    policy: bible.policy.Policy, edition: bible.pipeline.Edition
) -> None:
    pipeline.check_met(policy, edition.met)
    figures = decision(source="Heb. 300", not_a_citation=True)
    decided = changed(
        policy, "citations", lambda data: data["decisions"].update(x=figures)
    )
    with pytest.raises(CheckFailed, match=r"Unused citation decisions: \['x'\]"):
        pipeline.check_met(decided, edition.met)
    # A decision is met when the note of its key is read.
    tongue, report = citations.dialect("brenton", policy=decided), annotate.Report()
    found = citations.scan(
        "Heb. 300. See Rom. 4. 7.", tongue, HOME, "x", edition.inventory, policy=decided
    )
    report.read(tongue, "x", found, decided)
    assert named(found) == "ROM 4:7"
    assert (report.decided, report.names) == ({"x"}, {("brenton", "Rom")})
    met = {**edition.met, "decisions": edition.met["decisions"] | report.decided}
    pipeline.check_met(decided, met)
    unnamed = changed(
        policy,
        "citations",
        lambda data: data["dialects"]["brenton"]["books"].update(Nowhere="GEN"),
    )
    with pytest.raises(CheckFailed, match=r"Unused names.*'brenton', 'Nowhere'"):
        pipeline.check_met(unnamed, edition.met)


# In the notes


@pytest.mark.parametrize(
    "pieces,decided,prints",
    [
        (
            [
                ("label", "Gr. "),
                ("cited", "seed"),
                ("text", "; see chap "),
                ("xt", "6. 13,15"),
                ("text", ". Also 1 Cor 2. 16."),
            ],
            None,
            "Gr. [seed]; see <chapter 6:13, 15>. Also <1 Corinthians 2:16>.",
        ),
        # What the edition doesn't print stays among its words.
        (
            [("text", "Verse 99 is not in Vat.")],
            decision(source="Verse 99", unprinted=True, print="Verse 99"),
            "Verse 99 is not in Vat.",
        ),
    ],
)
def test_a_notes_citations_are_references_of_their_own(
    cite: Cite,
    ctx: bible.annotate.Context,
    pieces: list[tuple[str, str]],
    decided: CitationsDecisions | None,
    prints: str,
) -> None:
    plain = "".join(text for _, text in pieces)
    body = notes.source_body(pieces, cite(plain, decided=decided), None, "x", plain)
    marks = {
        "commentary": "{}",
        "reading": "[{}]",
        "quotation": "[{}]",
        "citation": "<{}>",
    }
    runs = notes.displayed(body, books=ctx.books)[0]
    assert "".join(marks[role].format(words) for role, words in runs) == prints


def test_a_citation_of_the_wrong_verse_prints_the_verse_meant(
    edition: bible.pipeline.Edition,
) -> None:
    # The margin of 1611 has "Rom. 1.19" for 15.19, and George after it.
    colossians = usj.serialize(edition.documents["COL"])
    assert "fully to preach the word of God\\ft , \\xt Romans 15:19\\f*" in colossians
    # Brenton's "Rom. 10. 9" is 10. 19, which the link at the verse names, so
    # the note is merged into it as any note is that the link repeats.
    deuteronomy = usj.serialize(edition.documents["DEU"])
    assert "\\xo 32:21 \\xt Romans 10:19 \\xta (Heb. and LXX)\\x*" in deuteronomy
    assert "\\fr 32:21" not in deuteronomy and "Romans 10:9" not in deuteronomy


# In the front and back matter


@pytest.mark.parametrize(
    "unit,prints",
    [
        ("XXB", "than is afforded by Genesis 47:31, compared with Hebrews 11:21."),
        # Decisions, keyed by the unit and the words they decide.
        ("XXB", "The Septuagint rendering of Psalm 4:5, is"),
        ("XXB", "the first Epistle of Peter, 4:18."),
        ("XXB", "one of the acrostic Psalms, (144:13), where"),
        ("XXB", "In Acts 17:28, we find"),
        ("NDX", "studied them. Acts 17:11 and 8:28, 29. They"),
        ("NDX", "See Judges 8:2. \\it Joash\\it* the king"),
        ("BAK", "\\ip 2 Kingdoms 5:18.—Giants."),
        ("BAK", "\\ip Psalm 41:5.—There are"),
        ("BAK", "Mark 4:30; in Hebrews 9:9 and 11:19 it is"),
        # A paragraph that names no book is of the book last cited.
        ("BAK", "see chapter 1:4, 22; 8:5; 14:15; 21:11. For πανοῦργος, 12:16; 13:1,"),
        ("BAK", "see \\it Appendix\\it*. Note on 2 Kingdoms 5:18."),
        # A book that is named and not cited is renamed.
        ("BAK", "\\is2 3 Kingdoms"),
        # The label of a passage retained for editorial review is no citation.
        ("BAK", "\\ip 5 \\vp 17\\vp*And the king commanded"),
        # A book's introduction, set as a note on the book, cites the book.
        ("BAR", "ending at 3:8, was in all probability originally written in Hebrew"),
    ],
)
def test_the_front_and_back_matter_cite_as_the_edition_does(
    edition: bible.pipeline.Edition, unit: str, prints: str
) -> None:
    assert prints in usj.serialize(edition.documents[unit])


def test_a_decision_on_a_unit_is_keyed_by_its_words(
    policy: bible.policy.Policy,
) -> None:
    words = "one of the acrostic Psalms, (cxliv. 13), where"
    found = citations.unit_decisions("XXB", words, policy=policy)
    assert list(found) == ["XXB cxliv. 13"]
    assert found["XXB cxliv. 13"]["source"] == "cxliv. 13"
    # Nor is one met where its words are part of others' words.
    assert citations.unit_decisions("XXB", "Psalm cxliv. 130", policy=policy) == {}
    # The introductions are one unit, read into each book in turn.
    found = citations.unit_decisions("OTH", "ch. 3. 8.", "BAR", policy=policy)
    assert list(found) == ["OTH BAR 3. 8"]
    assert citations.unit_decisions("OTH", "ch. 3. 8.", "TOB", policy=policy) == {}


@pytest.mark.parametrize(
    "change,refusal",
    [
        (
            lambda data: data["units"].pop("XXB"),
            "Unit whose citations nothing reads: XXB",
        ),
        (
            lambda data: data["decisions"].pop("XXB cxliv. 13"),
            r"can't be read: XXB \(cxliv. 13\)",
        ),
        # A decision whose words the unit has twice decides neither.
        (
            lambda data: data["decisions"].update(
                {"XXB Roman": decision(not_a_citation=True)}
            ),
            r"met more than once: \['XXB Roman'\]",
        ),
    ],
    ids=["no dialect", "undecided", "met twice"],
)
def test_a_unit_says_how_it_cites_and_meets_each_decision_once(
    policy: bible.policy.Policy,
    sources: bible.sources.Sources,
    read: bible.pipeline.Read,
    ctx: bible.annotate.Context,
    change: Callable[[dict[str, Any]], object],
    refusal: str,
) -> None:
    policy = changed(policy, "citations", change)
    [preface] = [entry for entry in policy.entries if entry["id"] == "XXB"]
    doc, text = read.brenton["XXB"], sources.brenton["XXB"]
    with pytest.raises(CheckFailed, match=refusal):
        matter.unit(
            preface, doc, doc, text, replace(ctx, policy=policy), annotate.Report()
        )


def test_markup_within_a_citation_goes_with_it(
    cite: Cite, ctx: bible.annotate.Context
) -> None:
    def cited(text: str, dialect: str = "kjv-preface") -> str:
        content = usj.parse(text, fragment=True)
        words = matter.words(content)
        reading = matter.Reading(words, tuple(cite(words, dialect, home=None)))
        return usj.serialize(matter.cited(content, reading, ctx.books, "x"))

    assert cited(r"search. \it John\it* 5. 39. They") == "search. John 5:39. They"
    assert cited(r"2 \it Tim.\it* 3. 15. If") == "2 Timothy 3:15. If"
    # A note in the matter is read without its origin, which it keeps.
    note = r"at all.\f + \fr 1:0 \ft In Acts 17. 28, we find\f* Let us"
    assert cited(note, "brenton-preface") == note.replace("17. 28", "17:28")
    # A span that the citation only begins or ends in is no citation's to close.
    with pytest.raises(CheckFailed, match="Citation across markup"):
        cited(r"\it See John\it* 5. 39.")


def test_a_name_is_changed_once_and_whole(
    policy: bible.policy.Policy, ctx: bible.annotate.Context
) -> None:
    doc = usj.parse("\\id BAK\n\\is2 CHRONICLES I\n\\is2 CHRONICLES II\n")
    unit: matter.Unit = [(block, {}) for block in doc["content"]]

    def renamed(*names: object) -> str:
        declared = changed(
            policy, "citations", lambda data: data["names"].update(x=list(names))
        )
        found = matter.renamed(unit, "x", ctx.books, declared)
        return usj.serialize(usj.with_blocks(doc, [block for block, _ in found]))

    assert renamed(
        {"from": "CHRONICLES I", "to": "{1CH:upper}", "why": "x"},
        {"from": "CHRONICLES II", "to": "{2CH:upper}", "why": "x"},
    ) == ("\\id BAK\n\\is2 1 CHRONICLES\n\\is2 2 CHRONICLES\n")
    with pytest.raises(CheckFailed, match="Change of name not met once: x"):
        renamed({"from": "CHRONICLES", "to": "x", "why": "x"})
    with pytest.raises(CheckFailed, match="without its words or reason"):
        renamed({"from": "CHRONICLES I", "to": "x"})


def test_several_decisions_on_one_note_form_a_list(
    policy: bible.policy.Policy, ctx: bible.annotate.Context
) -> None:
    def both(data: dict[str, Any]) -> None:
        data["decisions"]["JDG 13:8"] = [
            decision(source="Heb. 300", not_a_citation=True),
            decision(source="Jer. 9. 24", numbering="kjv"),
        ]

    decided = changed(policy, "citations", both)
    found = citations.scan(
        "Heb. 300. Comp. Jer. 9. 24.",
        citations.dialect("brenton", policy=decided),
        HOME,
        "JDG 13:8",
        ctx.inventory,
        policy=decided,
    )
    assert [(c.source, str(c.passages[0])) for c in found] == [
        ("Jer. 9. 24", "JER 9:23")
    ]
