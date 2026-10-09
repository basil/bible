"""The review of the reconciliation, one file for each book with every
non-neutral unit once, markdown safe; and the appendix of readings."""

from __future__ import annotations

import copy
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping

import pytest

import bible.annotate
import bible.pipeline
from bible import scripture, usj
from bible.byzantine import BOOKS, BOYD_ASV, REVISIONS, appendix, review
from bible.byzantine.decisions import ref_key
from bible.byzantine.english import verses_of
from bible.byzantine.greek import accent_letters, ascii_greek, greek_words
from bible.byzantine.presentation import (
    anchored,
    clipped,
    diff_spans,
    greek_display,
    passage_spans,
)
from bible.byzantine.rows import InstructionEdit, RevisionRow, Unit
from bible.byzantine.stages import Context
from bible.usj import Document, Node

HEADING = re.compile(
    r"^## (?P<unit>[1-3A-Z]{3} \d+:\d+#\S+) · (?P<disposition>\w+)(?: · (?P<action>\w+))? · score (?P<score>\d+)$"
)


@pytest.fixture(scope="module")
def packets(byzantine: Context) -> dict[str, str]:
    return review.packets(byzantine)


@pytest.fixture(scope="module")
def index(byzantine: Context) -> review.Index:
    return review.build_index(byzantine)


def section_of(packets: Mapping[str, str], uid: str) -> str:
    """A unit's section of its book's file, from its heading to the next."""
    lines = packets[f"{uid.split()[0]}.md"].splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"## {uid} · "))
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end])


def unit_of(byzantine: Context, uid: str) -> Unit:
    return next(u for u in byzantine["units"] if u["id"] == uid)


def test_the_books_are_the_only_packet_files(packets: dict[str, str]) -> None:
    assert set(packets) == {f"{b}.md" for b in BOOKS}


def test_each_packet_says_what_it_is(packets: dict[str, str]) -> None:
    for book in BOOKS:
        text = packets[f"{book}.md"]
        assert text.startswith(f"# {book}\n\nEvery Scrivener-RP2026 unit in the book.")
        assert "src/bible/byzantine/tags.py" in text
        assert "rpkjv" not in text


def test_every_non_neutral_unit_has_exactly_one_section(
    byzantine: Context, packets: dict[str, str]
) -> None:
    headings = []
    for book in BOOKS:
        for line in packets[f"{book}.md"].splitlines():
            if line.startswith("## ") and line not in {
                "## Neutral units",
                review.LOOSE_HEADING,
            }:
                m = HEADING.match(line)
                assert m, line
                headings.append(m["unit"])
    expected = [
        r["unit"] for r in byzantine["dispositions"] if r["disposition"] != "neutral"
    ]
    assert sorted(headings) == sorted(expected)
    assert len(headings) == len(set(headings))


def test_every_loose_row_is_in_its_book_packet(
    index: review.Index, packets: dict[str, str]
) -> None:
    loose = {ref: rows for ref, rows in index["loose_in_verse"].items() if rows}
    assert loose
    for ref, rows in loose.items():
        for row in rows:
            assert row in packets[f"{ref.split()[0]}.md"], (ref, row)
    # Verses with no unit section: no units at all, or neutral units only.
    assert "### ACT 21:4\n" in packets["ACT.md"]
    assert "### MAT 12:3\n" in packets["MAT.md"]


def test_neutral_table_shows_score_and_evidence(packets: dict[str, str]) -> None:
    text = packets["MAT.md"]
    assert "| MAT 12:3#1 |" in text
    row = next(line for line in text.splitlines() if line.startswith("| MAT 12:3#1 |"))
    assert "| 3 |" in row and "`ev:unplaced-row-in-verse`" in row


def test_neutral_units_are_tabled_not_sectioned(
    byzantine: Context, packets: dict[str, str]
) -> None:
    neutral = [
        r["unit"] for r in byzantine["dispositions"] if r["disposition"] == "neutral"
    ]
    assert neutral
    text = "\n".join(packets.values())
    for uid in neutral:
        assert f"## {uid} ·" not in text
    for uid in neutral[:20]:
        assert f"| {uid} |" in text


def test_a_shared_greek_verse_names_the_section_that_shows_it(
    packets: dict[str, str],
) -> None:
    for text in packets.values():
        lines = text.splitlines()
        for number, line in enumerate(lines):
            found = re.match(r"^Greek whole verse · .*: see (\S+ \S+)\s*$", line)
            if found:
                assert any(
                    earlier.startswith(f"## {found[1]} · ")
                    for earlier in lines[:number]
                ), line


def test_sections_show_the_disposition_and_tags(
    byzantine: Context, packets: dict[str, str]
) -> None:
    rows = {r["unit"]: r for r in byzantine["dispositions"]}
    for uid in ("MAT 3:8#1", "MAT 23:13#move", "ACT 9:6#1"):
        section = section_of(packets, uid)
        assert (
            f"Disposition {rows[uid]['disposition']} · {rows[uid]['action']}" in section
        )
        assert "Tags " + " ".join(f"`{t}`" for t in rows[uid]["tags"]) in section
        assert "Calculus " in section


def test_esc_neutralizes_pipes_and_newlines() -> None:
    assert review.esc("a|b") == "a\\|b"
    assert review.esc("one\ntwo\n\nthree") == "one two three"
    assert review.esc("  padded   words ") == "padded words"
    assert review.esc(None) == "None"
    assert "\n" not in review.esc("x\r\ny")


@pytest.mark.parametrize(
    "ref,target",
    [
        ("MAT 3:8", "MAT 3:8"),
        ("ACT 9:6", "ACT 9:6"),
        ("MAT 23:13", "MAT 23:14"),
        ("ROM 16:25", "ROM 14:24"),
        ("ACT 8:37", "ACT 8:37"),
    ],
)
def test_full_greek_preserves_pinned_verses_except_display_normalization(
    byzantine: Context, ref: str, target: str
) -> None:
    assert_greek_preserved(byzantine, ref, target)


def assert_greek_preserved(
    byzantine: Context,
    ref: str,
    target: str,
    prepared: appendix.PreparedGreek | None = None,
) -> None:
    prepared = prepared if prepared is not None else appendix.prepare_greek(byzantine)
    lines = review.greek_verses(byzantine, ref, prepared, target)
    diff = lines[0].split(": ", 1)[1].rstrip()
    before = re.sub(r"\[\+[^\]]*\]", "", diff)
    before = re.sub(r"\[-([^\]]*)\]", r"\1", before)
    after = re.sub(r"\[-[^\]]*\]", "", diff)
    after = re.sub(r"\[\+([^\]]*)\]", r"\1", after)
    tr, rp, _ = prepared
    assert before.lower() == greek_display("` " + " ".join(tr[ref]) + " `").lower()
    assert (
        after.lower()
        == greek_display("` " + " ".join(rp.get(target, [])) + " `").lower()
    )


def test_greek_comparison_marks_difference_and_keeps_context(
    byzantine: Context, packets: dict[str, str]
) -> None:
    lines = review.greek_verses(byzantine, "MAT 3:8", appendix.prepare_greek(byzantine))
    assert "[-καρποὺς ἀξίους][+καρπὸν ἄξιον]" in lines[0]
    section = section_of(packets, "MAT 3:8#1")
    for line in lines:
        assert line in section
    assert "[-fruits][+fruit]" in section
    assert section.index("Greek whole verse · TR MAT 3:8") < section.index(
        "English whole verse · KJV MAT 3:8"
    )


@pytest.mark.parametrize(
    "before,after",
    [
        ("fruits", "fruit"),
        ("καρπους αξιους", "καρπον αξιον"),
        ("And he said, Go.", "and he said: Go!"),
        ("and with fire", ""),
        ("", "and Pharisees"),
        ("Jesus Christ", "Christ Jesus"),
        ("holy " * 210, "holy " * 209),
        ("one  two\nthree", "one two three"),
    ],
)
def test_diff_projects_exactly_to_both_inputs(before: str, after: str) -> None:
    spans = diff_spans(before, after)
    assert "".join(text for kind, text in spans if kind != "insert") == before
    assert "".join(text for kind, text in spans if kind != "delete") == after


def test_readable_diff_marks_words_punctuation_and_absence() -> None:
    assert review.marked_readings("fruits", "fruit") == ("**fruits**", "**fruit**")
    assert review.marked_readings("Go.", "go!") == ("**Go.**", "**go!**")
    assert review.marked_readings("same", "same") == ("same", "same")
    assert review.marked_readings("", "added") == ("∅", "**added**")
    assert review.marked_readings("omitted", "") == ("**omitted**", "∅")


def test_repeated_words_do_not_hide_the_minimal_omission() -> None:
    spans = diff_spans("holy " * 210, "holy " * 209)
    assert "".join(text for kind, text in spans if kind == "delete") == "holy "
    assert not any(kind == "insert" for kind, _ in spans)


def test_phrase_replacements_are_not_arbitrary_word_pairs() -> None:
    assert "[-have seen][+see ye]" in review.inline_diff("have seen", "see ye")
    assert "[-we will][+let us] go" in review.inline_diff("we will go", "let us go")


def test_james_keeps_contextual_diff_and_compact_witnesses(
    byzantine: Context, packets: dict[str, str], index: review.Index
) -> None:
    text = packets["JAS.md"]
    assert "[-have seen][+see ye]" in text
    assert "[-ὑπὸ κρίσιν][+εἰς ὑπόκρισιν]" in text
    assert "[-μοιχεύσῃς][+μοιχεύσεις]" in text
    section = section_of(packets, "JAS 2:11#2")
    assert "OLEB JAS 2:11 (whole verse):" in section
    assert "Thou shalt" in section
    assert "Μὴ [-φονεύσῃς][+φονεύσεις]·" in section
    assert "English for shared construction (executed with JAS 2:11#1)" in section
    assert "Textus Receptus" in section
    assert "### " not in section
    assert len(text.splitlines()) < 900
    assert (
        "at unit: ` … [-Do][+Thou shalt] not kill. … ` (includes Boyd revision)"
        in section
    )
    witnesses = review.witness_lines(unit_of(byzantine, "JAS 2:5#1"), byzantine, index)
    assert all(line.startswith("- ") and line.count("\n") <= 1 for line in witnesses)
    assert not any("| Before" in line for line in witnesses)


def test_real_verse_diffs_preserve_both_texts(byzantine: Context) -> None:
    pairs = {(u["ref"], u["target_ref"]) for u in byzantine["units"]}
    inputs = [
        (
            " ".join(byzantine["tr"].get(ref, [])),
            " ".join(byzantine["rp"].get(target, [])),
        )
        for ref, target in pairs
    ]
    for book, doc in byzantine["prepared"].items():
        inputs.extend(
            (byzantine["kjv"].get(f"{book} {address}", ""), verse.text)
            for address, verse in scripture.verses(doc).items()
        )
    for before, after in inputs:
        spans = diff_spans(before, after)
        assert "".join(text for kind, text in spans if kind != "insert") == before
        assert "".join(text for kind, text in spans if kind != "delete") == after


def test_greek_diff_marks_accents(byzantine: Context) -> None:
    lines = review.greek_verses(byzantine, "PHP 3:5", appendix.prepare_greek(byzantine))
    assert "[-περιτομὴ][+περιτομῇ]" in lines[0]


def test_no_table_row_is_broken_by_its_content(
    byzantine: Context, packets: dict[str, str]
) -> None:
    for name, text in {**packets, "summary": review.summary(byzantine)}.items():
        for line in text.splitlines():
            if line.startswith("| ") and not line.startswith("| ---"):
                cells = re.split(r"(?<!\\)\|", line.strip("|"))
                assert len(cells) in {2, 3, 4, 5}, (name, line)


def test_greek_context_uses_ledger_and_is_shown_once(
    byzantine: Context, packets: dict[str, str]
) -> None:
    lines = review.greek_verses(
        byzantine, "PHM 1:17", appendix.prepare_greek(byzantine)
    )
    assert "` Εἰ οὖν [-ἐμὲ][+με] ἔχεις κοινωνόν, προσλαβοῦ αὐτὸν ὡς ἐμέ. `" in lines[0]
    text = packets["JAS.md"]
    assert text.count("Greek whole verse · TR JAS 2:11 → RP2026 JAS 2:11: `") == 1
    assert (
        "Greek whole verse · TR JAS 2:11 → RP2026 JAS 2:11: see JAS 2:11#1"
        in section_of(packets, "JAS 2:11#2")
    )


def test_english_diff_keeps_whole_words() -> None:
    assert "[-thy][+the]" in review.inline_diff("thy right cheek", "the right cheek")


def test_witness_diff_shows_shared_context_once() -> None:
    assert review.inline_change("condemned", "judged") == "` [-condemned][+judged] `"
    contrast = review.inline_change("shall be condemned", "shall be judged")
    assert contrast == "` shall be [-condemned][+judged] `"


def test_witness_excerpt_clips_context_without_changing_neighboring_words() -> None:
    text = "One two three four five six old seven eight nine ten eleven twelve."
    assert review.witness_excerpt("old", "new", text) == (
        "source context: ` One two three four five six [-old][+new] seven eight nine ten eleven twelve. `"
    )
    assert review.witness_excerpt("old", "new", "old is here.") == (
        "source context: ` [-old][+new] is here. `"
    )


def test_witness_excerpt_abstains_on_absent_or_ambiguous_phrases() -> None:
    for text in (None, "old and old", "older wording"):
        assert (
            review.witness_excerpt("old", "new", text)
            == "quoted contrast: ` [-old][+new] `"
        )
    assert review.witness_excerpt("old", "new", "old and old", bounds=(8, 11)) == (
        "source context: ` old and [-old][+new] `"
    )


def test_a_bound_insertion_shows_its_kjv_context() -> None:
    edit: InstructionEdit = {
        "word_range": [1, 1],
        "old": "",
        "new": "new",
        "side": "after",
    }
    bounds = review.kjv_bounds("one, two", edit)
    assert review.witness_excerpt("", "new", "one, two", bounds=bounds) == (
        "source context: ` one[+ new], … `"
    )
    assert review.witness_excerpt("", "new", "one, two").startswith("quoted contrast: ")


def test_boyd_passage_markup_is_compared_as_plain_wording() -> None:
    passage = "his brother&#x27;s <i>wife</i>"
    assert review.source_plain(passage) == "his brother's wife"
    assert review.witness_excerpt(
        "", "brother's", review.source_plain(passage), reading="new"
    ) == ("source context: ` his [+brother's] wife `")


def test_james_witness_excerpts_use_each_sources_own_context(
    byzantine: Context, index: review.Index
) -> None:
    lines = review.witness_lines(unit_of(byzantine, "JAS 4:15#1"), byzantine, index)
    tcent = next(line for line in lines if line.startswith("- TCENT 290"))
    assert (
        "source context: ` … [-we will][+let us] live and do this or that.” `" in tcent
    )
    # A source annotation is never located in the verse; it stays in the quote.
    verse = "If the Lord wills, we will live and do this or that."
    assert review.witness_excerpt("we will (twice)", "let us", verse) == (
        "quoted contrast: ` [-we will (twice)][+let us] `"
    )


def test_instruction_witness_lines_show_the_proposal_in_kjv_context(
    byzantine: Context, index: review.Index
) -> None:
    lines = review.witness_lines(unit_of(byzantine, "JAS 2:18#1"), byzantine, index)
    pierpont = next(line for line in lines if line.startswith("- Pierpont 565:"))
    assert "KJV context (proposal): ` … shew me thy faith [-without]" in pierpont
    assert "blocked (override JAS 2:18#1 takes this construction)" in pierpont


def test_unit_greek_context_uses_corresponding_passage(
    byzantine: Context,
) -> None:
    prepared = appendix.prepare_greek(byzantine)
    verses = verses_of(byzantine["prepared"])
    unit = unit_of(byzantine, "JAS 2:11#1")
    passages = review.unit_passages(unit, byzantine, prepared, verses)
    excerpt = review.unit_greek_excerpt(unit, byzantine, passages)
    assert "[-μοιχεύσῃς][+μοιχεύσεις]" in excerpt
    texts, selected, _ = passages
    assert excerpt == " / ".join(
        review.diff_markup(
            passage_spans(
                texts,
                p,
                0,
                appendix.passage_ranges(
                    byzantine, "JAS 2:11", "JAS 2:11", texts[0], texts[1]
                ),
                greek=True,
            )
        )
        for p in selected
    )
    omitted = unit_of(byzantine, "JAS 1:13#1")
    assert "[-τοῦ ]" in review.unit_greek_excerpt(
        omitted, byzantine, review.unit_passages(omitted, byzantine, prepared, verses)
    )


def test_every_greek_diff_preserves_pinned_verses_except_display_normalization(
    byzantine: Context,
) -> None:
    prepared = appendix.prepare_greek(byzantine)
    for ref, target in {(u["ref"], u["target_ref"]) for u in byzantine["units"]}:
        assert_greek_preserved(byzantine, ref, target, prepared)


def test_unit_english_comparison_is_separate_from_whole_verse(
    packets: dict[str, str],
) -> None:
    section = section_of(packets, "JAS 4:13#2")
    label = "English for shared construction (executed with JAS 4:13#1) · KJV JAS 4:13 → OLEB JAS 4:13:"
    assert label in section
    local = next(line for line in section.splitlines() if line.startswith(label))
    assert (
        "To day [-or][+and] to morrow [-we will][+let us] go into such a city," in local
    )
    assert "and get gain:" in local  # uncertain short correspondence keeps the verse
    assert (
        section.index("Greek at this unit")
        < section.index(label)
        < section.index("Greek whole verse")
    )
    section = section_of(packets, "JAS 1:13#1")
    assert "English at this unit · KJV JAS 1:13 → OLEB JAS 1:13: unchanged" in section


def test_short_form_unit_english_keeps_its_kjv_context(
    packets: dict[str, str],
) -> None:
    # A short-form omission note has no source range: quote the whole verse.
    section = section_of(packets, "COL 1:14#1")
    assert (
        "English at this unit · KJV COL 1:14 → OLEB COL 1:14: ` in whom we have redemption[- through his blood], even the forgiveness of sins: `"
        in section
    )


def test_boyd_witness_compares_to_its_asv_base(
    byzantine: Context, index: review.Index
) -> None:
    unit = unit_of(byzantine, "JAS 2:11#1")
    lines = review.witness_lines(unit, byzantine, index)
    line = next(line for line in lines if line.startswith("- Boyd ASV 2021 ("))
    assert "ASV 1901 → Boyd ASV 2021 (whole verse):" in line
    assert "KJV contrast at unit:" in line
    expected = review.diff_markup(
        diff_spans(
            scripture.plain(byzantine["texts"]["asv"][unit["ref"]]),
            scripture.plain(byzantine["texts"][BOYD_ASV][unit["ref"]]),
        )
    )
    assert expected in line


def test_patriarchal_agreement_is_relative_to_rp2026(
    byzantine: Context, index: review.Index
) -> None:
    assert (
        review.patriarchal_status(unit_of(byzantine, "JAS 2:11#1"), index)
        == "differs from RP2026 (TR reading)"
    )
    assert (
        review.patriarchal_status(unit_of(byzantine, "JAS 1:13#1"), index)
        == "agrees with RP2026"
    )
    unknown = next(
        u
        for u in byzantine["units"]
        if not u.get("patriarchal")
        and not any(a["inventory"] == "tcgnt" for a in u["inventories"])
    )
    assert review.patriarchal_status(unknown, index) == "RP2026 agreement unknown"


def test_revision_excerpt_preserves_insertion_side_at_punctuation() -> None:
    row: RevisionRow = {"word_range": [1, 1], "old": "", "new": "new", "side": "after"}
    assert review.revision_excerpt(row, "one, two") == "` one[+ new], … `"
    row["side"] = "before"
    assert review.revision_excerpt(row, "one, two") == "` … [+new ]two `"


def test_patriarchal_other_reading_is_not_mistaken_for_rp_agreement(
    index: review.Index,
) -> None:
    unit: Unit = {
        "inventories": [{"inventory": "tcgnt", "entry": 1, "scope": "constituent"}]
    }
    other: review.Index = {**index, "tcgnt": {1: {"variants": [{"sigla": ["ANT"]}]}}}
    assert (
        review.patriarchal_status(unit, other) == "differs from RP2026 (other reading)"
    )
    agreeing: review.Index = {**index, "tcgnt": {1: {"variants": []}}}
    assert (
        review.patriarchal_status(unit, agreeing)
        == "agrees with RP2026 in recorded part"
    )


def test_revision_quotations_label_eligibility_and_attachment(
    byzantine: Context, index: review.Index
) -> None:
    for unit in byzantine["units"]:
        if index["rows"][unit["id"]]["disposition"] == "neutral":
            continue
        lines = review.witness_lines(unit, byzantine, index)
        for name in REVISIONS:
            if not byzantine["texts"][name].get(unit["ref"]):
                continue
            line = next(
                line for line in lines if line.startswith(f"- {review.NAMES[name]} (")
            )
            rows = [
                r for r in index["revisions_at"][unit["id"]] if r["witness"] == name
            ]
            if unit["id"] not in byzantine["revision_admitted"][name]:
                assert "not admitted at this unit:" in line
                assert not rows
                assert "KJV contrast" not in line
            else:
                assert "eligible reading;" in line
                assert ("no English contrast attached" in line) == (not rows)
            for r in rows:
                if any(
                    a["unit"] == unit["id"] and a["scope"] == "constituent"
                    for a in r["units"]
                ):
                    assert "KJV contrast part of this unit:" in line
            assert "construction context" not in line


def test_boyd_quote_keeps_patched_verse_explicitly_excluded(
    byzantine: Context, index: review.Index
) -> None:
    lines = review.witness_lines(unit_of(byzantine, "PHM 1:1#1"), byzantine, index)
    line = next(line for line in lines if line.startswith("- Boyd ASV 2021 ("))
    assert "not admitted at this unit: RP2026 Appendix A" in line
    assert "ASV 1901 → Boyd ASV 2021 (whole verse):" in line


def test_report_attachment_scope_is_visible(
    byzantine: Context, index: review.Index
) -> None:
    report = next(
        r
        for r in byzantine["reports"]
        if r["witness"] == "faa"
        and any(a["scope"] == "constituent" for a in r["units"])
    )
    uid = next(a["unit"] for a in report["units"] if a["scope"] == "constituent")
    line = next(
        line
        for line in review.witness_lines(unit_of(byzantine, uid), byzantine, index)
        if re.match(rf"^- FAA {re.escape(str(report['entry']))}(?: \([^)]*\))?:", line)
    )
    assert "attachment: part of this unit" in line


def test_silence_explanation_does_not_deny_attached_revision_evidence(
    byzantine: Context, index: review.Index
) -> None:
    for unit in byzantine["units"]:
        row = index["rows"][unit["id"]]
        if row["disposition"] == "silent" and index["revisions_at"][unit["id"]]:
            text = review.calculus(row, unit, index)
            assert "attached revision contrasts remain for review" in text
            assert "no witness reports an English difference" not in text.lower()


def test_override_citation_brackets_and_faa_note_labels(
    packets: dict[str, str],
) -> None:
    mark, acts = packets["MRK.md"], packets["ACT.md"]
    assert "to sit on my right hand and on [my] left hand” ✓" in mark
    assert (
        "Citation brackets in a reading's evidence record the source's supplied-word markup; a tick verifies quotation accuracy."
        in mark
    )
    assert "ACT 28:11 verse note: “ἤχθημεν, we were transported” ✓" in acts


def test_the_summary_counts_the_dispositions(byzantine: Context) -> None:
    text = review.summary(byzantine)
    assert text.startswith("# The Byzantine New Testament\n")
    counts = Counter(r["disposition"] for r in byzantine["dispositions"])
    for disposition, number in counts.items():
        assert f"| {disposition} | {number} |" in text
    for name, result in byzantine["invariants"].items():
        assert f"- {name}: {result}" in text


# The appendix of readings.

LABELS = {
    "tr": "TR",
    "rp": "RP",
    "kjv": "KJV",
    "oleb": "OLEB",
    "apparatus": "apparatus",
}
OMITTED = {"LUK 17:36", "ACT 8:37", "ACT 15:34", "ACT 24:7"}


@pytest.fixture(scope="module")
def printed(edition: bible.pipeline.Edition) -> dict[str, Document]:
    """The New Testament's books as the edition prints them."""
    return {code: edition.documents[code] for code in BOOKS}


@pytest.fixture(scope="module")
def rows(byzantine: Context, printed: dict[str, Document]) -> list[appendix.Row]:
    return appendix.rows(byzantine, byzantine["documents"], printed)


@pytest.fixture(scope="module")
def entries(
    rows: list[appendix.Row], ctx: bible.annotate.Context
) -> dict[str, list[Node]]:
    """Each row's run of the appendix's blocks, by the verse it is about."""
    blocks, spans = appendix.blocks(rows, ctx.books, LABELS)
    return {row.reference: blocks[start:end] for row, start, end in spans}


def text_of(block: Node) -> str:
    return usj.text_of(block["content"])


def test_romans_amen_keeps_shared_sentence_punctuation(
    entries: dict[str, list[Node]], packets: dict[str, str]
) -> None:
    entry = entries["ROM 16:20"]
    assert "ὑμῶν. [ἀμήν.]" in text_of(entry[1])
    assert "you. [Amen.]" in text_of(entry[2])
    lines = packets["ROM.md"].splitlines()
    greek = next(
        line for line in lines if line.startswith("Greek whole verse · TR ROM 16:20 ")
    )
    english = next(
        line
        for line in lines
        if line.startswith("English whole verse · KJV ROM 16:20 ")
    )
    assert "ὑμῶν.[- ][-ἀμήν.]" in greek
    assert "you.[- Amen.]" in english


def test_johannine_omission_is_one_reading(
    entries: dict[str, list[Node]], packets: dict[str, str]
) -> None:
    omitted = (
        "in heaven, the Father, the Word, and the Holy Ghost: "
        "and these three are one."
    )
    english = entries["1JN 5:7"][2]["content"]
    assert usj.text_of(english) == (
        f"KJV → OLEB For there are three that bear record, [{omitted}]"
    )
    assert usj.char("it", ",") in english
    section = section_of(packets, "1JN 5:7#1")
    assert f"bear record[+,][- {omitted}]" in section


def test_every_verse_with_a_greek_difference_is_listed_once(
    byzantine: Context, rows: list[appendix.Row]
) -> None:
    references = [row.reference for row in rows]
    assert len(references) == len(set(references))
    listed = set(references)
    for unit in byzantine["units"]:
        if unit["class"] != "structural":
            assert unit["target_ref"] in listed, unit["id"]
    keys = [ref_key(r) for r in references]
    assert keys == sorted(keys)


def test_a_changed_verse_has_one_aligned_comparison_per_language(
    rows: list[appendix.Row], entries: dict[str, list[Node]]
) -> None:
    changed = [row for row in rows if row.kjv != row.oleb and row.kind != "omitted"]
    assert len(changed) > 700
    for row in changed:
        heading, *lines = entries[row.reference]
        lines = [line for line in lines if not text_of(line).startswith("apparatus:")]
        assert heading["marker"] == "im"
        assert all(line["marker"] == "ili1" for line in lines)
        labels = [text_of(line).split(" ", 1)[0] for line in lines]
        assert labels == ["TR", "KJV"], row.reference
        greek, english = (text_of(line) for line in lines)
        assert greek.count("…") == english.count("…"), row.reference
        for text in (greek, english):
            assert not re.search(r"…\s*…", text), row.reference
            body = text.split(" ", 3)[3]
            assert len([part for part in body.split("…") if part.strip()]) == len(
                row.passages
            ), row.reference
        assert greek.startswith("TR → RP …") == english.startswith("KJV → OLEB …")
        assert greek.endswith("…") == english.endswith("…")
    fruit = next(row for row in rows if row.reference == "MAT 3:8")
    assert "καρποὺς ἀξίους" in fruit.greek_tr
    assert "καρπὸν ἄξιον" in fruit.greek_rp
    assert fruit.kjv and fruit.kjv.startswith(
        "Bring forth therefore fruits meet for repentance"
    )
    assert fruit.oleb and fruit.oleb.startswith(
        "Bring forth therefore fruit meet for repentance"
    )
    king = next(row for row in rows if row.reference == "MAT 22:7")
    assert king.kjv and king.kjv.startswith("But when the king heard thereof")
    assert king.oleb and king.oleb.startswith("And when that king heard thereof")
    # The English comparison has no notes or note lemmas.
    assert "**" not in "".join(text_of(b) for b in entries["MAT 22:7"])
    assert not usj.notes_of(entries["MAT 22:7"])


@pytest.mark.parametrize("ref", ["REV 13:6", "REV 13:7"])
def test_revelation_grouped_comparisons_include_unchanged_english_context(
    ref: str, rows: list[appendix.Row], entries: dict[str, list[Node]]
) -> None:
    row = next(row for row in rows if row.reference == ref)
    heading, greek, english = entries[ref]
    assert text_of(heading) == ref.split()[1]
    assert len(row.passages) == 2
    greek_text, english_text = text_of(greek), text_of(english)
    assert greek_text.count("TR → RP") == english_text.count("KJV → OLEB") == 1
    assert greek_text.count("…") == english_text.count("…") == 1
    assert " … " in greek_text and " … " in english_text
    if ref == "REV 13:6":
        assert "[ἤνοιξε] ἤνοιξεν" in greek_text
        assert "[καὶ] τοὺς" in greek_text
        assert "And he opened his mouth in blasphemy against God," in english_text
        assert "[and] even them that dwell in heaven." in english_text
    else:
        assert "ποιῆσαι πόλεμον [ποιῆσαι]" in greek_text
        assert "φυλὴν καὶ λαὸν καὶ γλῶσσαν" in greek_text
        assert "And it was given unto him to make war with the saints," in english_text
        assert "all kindreds, and people, and tongues, and nations." in english_text
    first_english = english_text.split(" … ")[0]
    assert "[" not in first_english
    for node in usj.walk(english["content"]):
        if node.get("marker") == "it":
            reading = usj.text_of(node["content"])
            if any(char.isalnum() for char in reading):
                assert reading not in first_english
    assert any(node.get("marker") == "bd" for node in usj.walk(greek["content"]))
    assert any(node.get("marker") == "it" for node in usj.walk(english["content"]))


def test_a_verse_whose_english_stands_has_a_greek_comparison(
    rows: list[appendix.Row], entries: dict[str, list[Node]]
) -> None:
    same = [row for row in rows if row.kind == "same"]
    assert same
    for row in same:
        assert row.units and row.kjv is None and row.oleb is None, row.reference
        heading, greek, *evidence = entries[row.reference]
        assert heading["marker"] == "im"
        assert text_of(heading) == row.reference.split()[1]
        assert greek["marker"] == "ili1"
        assert text_of(greek).startswith("TR → RP ")
        assert all(text_of(line).startswith("apparatus: TR → RP ") for line in evidence)
    accents = [unit for row in same for unit in row.units if unit.accented]
    assert accents


def test_grouped_comparisons_keep_multiple_changes_and_outer_omissions(
    ctx: bible.annotate.Context,
) -> None:
    texts = (
        "ἀρχή; παλαιόν ἕν; κενόν; παλαιόν δύο; τέλος.",
        "ἀρχή; νέον ἕν; κενόν; νέον δύο; τέλος.",
        "start; old … one; gap; old two; end.",
        "start; new … one; gap; new two; end.",
    )
    selected = tuple(
        tuple(
            (text.index(first), text.index(last) + len(last))
            for text, first, last in zip(texts, starts, ends, strict=True)
        )
        for starts, ends in (
            (("παλαιόν", "νέον", "old", "new"), ("ἕν;", "ἕν;", "one;", "one;")),
            (
                ("παλαιόν δύο", "νέον δύο", "old two", "new two"),
                ("δύο;", "δύο;", "two;", "two;"),
            ),
        )
    )
    row = appendix.Row(
        "MAT 1:1",
        "MAT 1:1",
        "changed",
        texts[0],
        texts[1],
        (),
        texts[2],
        texts[3],
        passages=selected,
    )
    blocks, spans = appendix.blocks([row], ctx.books, LABELS)
    heading, greek, english = blocks[spans[0][1] : spans[0][2]]
    assert text_of(heading) == "1:1"
    assert text_of(greek) == "TR → RP … [παλαιόν] νέον ἕν; … [παλαιόν] νέον δύο; …"
    assert text_of(english) == "KJV → OLEB … [old] new … one; … [old] new two; …"
    assert [
        usj.text_of(node["content"])
        for node in usj.walk(english["content"])
        if node.get("marker") == "it"
    ] == ["new", "new"]


def test_the_four_omitted_verses_are_listed(
    byzantine: Context, rows: list[appendix.Row], entries: dict[str, list[Node]]
) -> None:
    omitted = [row for row in rows if row.kind == "omitted"]
    assert (
        {row.reference for row in omitted} == OMITTED == byzantine["structure"].omitted
    )
    for row in omitted:
        assert row.greek_tr and not row.greek_rp and row.oleb is None
        assert row.kjv == scripture.plain(byzantine["kjv"][row.reference])
        lines = [text_of(b) for b in entries[row.reference][1:]]
        assert lines == [
            f"TR → RP [{row.greek_tr}]",
            f"KJV → OLEB [{row.kjv}]",
        ]


def test_a_moved_verse_is_labelled_with_the_king_james_number(
    byzantine: Context,
    rows: list[appendix.Row],
    entries: dict[str, list[Node]],
    printed: dict[str, Document],
) -> None:
    moved = {row.reference: row for row in rows if row.source != row.reference}
    expected = {
        target: origin for origin, target in byzantine["structure"].moved.items()
    }
    assert {ref: row.source for ref, row in moved.items()} == expected
    english = verses_of(printed)
    for ref, row in moved.items():
        assert row.kind == "changed"
        before = scripture.plain(byzantine["kjv"][row.source])
        after = scripture.plain(english[ref].text)
        if before == after:
            assert row.kjv is None and row.oleb is None
            assert not any(text_of(line).startswith("KJV →") for line in entries[ref])
        assert " ".join(
            ascii_greek("".join(accent_letters(w))) for w in row.greek_tr.split()
        ) == " ".join(byzantine["tr"][row.source])
        heading = text_of(entries[ref][0])
        assert heading == (f"{ref.split()[1]} (KJV {row.source.split()[1]})"), heading


def test_all_appendix_passages_keep_source_words(
    byzantine: Context, rows: list[appendix.Row]
) -> None:
    for row in rows:
        assert row.greek_tr == " ".join(byzantine["tr_alignment"].text[row.source])
        assert row.greek_rp == " ".join(
            byzantine["rp_alignment"].text.get(row.reference, [])
        )
        units = [
            u
            for u in byzantine["units"]
            if u["target_ref"] == row.reference and u["class"] != "structural"
        ]
        units.sort(key=lambda u: u["class"] == "accent")
        for printed, unit in zip(row.units, units, strict=True):
            for side, ref, value in (
                ("tr", unit["ref"], printed.tr),
                ("rp", unit["target_ref"], printed.rp),
            ):
                alignment = (
                    byzantine["tr_alignment"]
                    if side == "tr"
                    else byzantine["rp_alignment"]
                )
                span = unit["tr_range"] if side == "tr" else unit["rp_range"]
                assert value == " ".join(
                    alignment.text[ref][slice(*alignment.project(ref, span))]
                )
            if printed.apparatus:
                assert printed.apparatus == (unit["tr_accented"], unit["rp_accented"])
    assert any(not u.tr for row in rows for u in row.units)
    assert any(not u.rp for row in rows for u in row.units)


def test_heli_transcription_and_apparatus_stay_distinct(
    rows: list[appendix.Row], entries: dict[str, list[Node]]
) -> None:
    row = next(r for r in rows if r.reference == "LUK 3:23")
    assert "Ἡλί" in row.greek_tr
    contrast = next(u for u in row.units if u.accented)
    assert contrast.accented is not None and contrast.accented[0] == "Ἡλί,"
    assert contrast.apparatus == ("ἠλι", "ἡλι")
    assert text_of(entries["LUK 3:23"][1]).startswith("TR → RP ")
    assert text_of(entries["LUK 3:23"][2]) == "apparatus: TR → RP [ἠλι] ἡλι"


def test_appendix_passages_and_comparisons_keep_source_case_and_punctuation(
    byzantine: Context, rows: list[appendix.Row]
) -> None:
    def source_features(text: str) -> tuple[list[bool], str]:
        return (
            [letter[0].isupper() for letter in accent_letters(text)],
            "".join(
                c
                for c in unicodedata.normalize("NFD", text)
                if not c.isalpha() and not c.isspace() and not unicodedata.combining(c)
            ),
        )

    for row in rows:
        assert source_features(row.greek_tr) == source_features(
            " ".join(byzantine["tr_accented"][row.source])
        ), row.source
        rp = byzantine["printed"][row.reference]["accented"]
        assert source_features(row.greek_rp) == source_features(
            " ".join(rp)
        ), row.reference
        units = [
            u
            for u in byzantine["units"]
            if u["target_ref"] == row.reference and u["class"] != "structural"
        ]
        units.sort(key=lambda u: u["class"] == "accent")
        for printed, unit in zip(row.units, units, strict=True):
            assert source_features(printed.tr) == source_features(
                " ".join(
                    byzantine["tr_accented"][unit["ref"]][
                        slice(
                            *appendix.projected(
                                byzantine, "tr", unit["ref"], unit["tr_range"]
                            )
                        )
                    ]
                )
            ), unit["id"]
            assert source_features(printed.rp) == source_features(
                " ".join(
                    rp[
                        slice(
                            *appendix.projected(
                                byzantine, "rp", unit["target_ref"], unit["rp_range"]
                            )
                        )
                    ]
                )
            ), unit["id"]
            if printed.accented:
                for text, comparison in zip(
                    (printed.tr, printed.rp), printed.accented, strict=True
                ):
                    if " … " not in comparison:
                        assert comparison == text, unit["id"]
                    else:
                        forms = {
                            ascii_greek("".join(accent_letters(p)))
                            for p in comparison.split(" … ")
                        }
                        assert comparison == " … ".join(
                            w
                            for w in text.split()
                            if ascii_greek("".join(accent_letters(w))) in forms
                        ), unit["id"]


def test_unchanged_english_and_accent_only_entries_use_normal_comparisons(
    ctx: bible.annotate.Context,
) -> None:
    row = appendix.Row(
        "MAT 1:1",
        "MAT 1:1",
        "same",
        "πρῶτον; τὸ τέλος.",
        "πρῶτον; τό τέλος.",
        (appendix.Unit("τὸ", "τό", ("τὸ", "τό")),),
    )
    blocks, spans = appendix.blocks([row], ctx.books, LABELS)
    heading, greek = blocks[spans[0][1] : spans[0][2]]
    assert text_of(heading) == "1:1"
    assert text_of(greek) == "TR → RP πρῶτον; [τὸ] τό τέλος."
    assert any(node.get("marker") == "bd" for node in usj.walk(greek["content"]))


def test_ellipsis_comparisons_keep_case_at_each_occurrence(
    byzantine: Context, printed: dict[str, Document]
) -> None:
    ref = "MRK 4:8"
    unit = next(u for u in byzantine["units"] if u["id"] == ref + "#accent")
    context = byzantine.copy()
    tr = list(byzantine["tr_accented"][ref])
    rp = list(byzantine["printed"][ref]["accented"])
    for words, plain, span in (
        (tr, byzantine["tr"][ref], unit["tr_range"]),
        (rp, byzantine["rp"][ref], unit["rp_range"]),
    ):
        first = next(at for at in range(*span) if plain[at] == "en")
        words[first] = words[first].upper() + ";"
    context["tr_accented"] = {**byzantine["tr_accented"], ref: tr}
    context["printed"] = {
        **byzantine["printed"],
        ref: {**byzantine["printed"][ref], "accented": rp},
    }
    row = next(
        r
        for r in appendix.rows(context, byzantine["documents"], printed)
        if r.reference == ref
    )
    contrast = next(u for u in row.units if u.accented)
    assert contrast.accented == ("ἛΝ; … ἓν … ἓν", "ἘΝ; … ἐν … ἐν")
    assert "ἛΝ" in row.greek_tr and "ἘΝ" in row.greek_rp


def test_preparing_greek_does_not_change_inputs(byzantine: Context) -> None:
    def inputs() -> tuple[object, ...]:
        return (
            byzantine["tr"],
            byzantine["rp"],
            byzantine["tr_accented"],
            byzantine["printed"],
            byzantine["units"],
        )

    before = copy.deepcopy(inputs())
    appendix.prepare_greek(byzantine)
    assert inputs() == before


def test_appendix_and_review_share_all_prepared_readings(
    byzantine: Context,
    rows: list[appendix.Row],
    packets: dict[str, str],
    index: review.Index,
) -> None:
    prepared = appendix.prepare_greek(byzantine)
    tr, rp, contrasts = prepared
    for row in rows:
        assert row.greek_tr == " ".join(tr[row.source])
        assert row.greek_rp == " ".join(rp.get(row.reference, []))
    for unit in byzantine["units"]:
        old = " ".join(
            tr[unit["ref"]][
                slice(
                    *appendix.projected(byzantine, "tr", unit["ref"], unit["tr_range"])
                )
            ]
        )
        new = " ".join(
            rp[unit["target_ref"]][
                slice(
                    *appendix.projected(
                        byzantine, "rp", unit["target_ref"], unit["rp_range"]
                    )
                )
            ]
        )
        packet = packets[unit["ref"].split()[0] + ".md"]
        if index["rows"][unit["id"]]["disposition"] == "neutral":
            assert (
                f"| {unit['id']} | {unit['class']} | {review.esc(old or '∅')} → {review.esc(new or '∅')} |"
                in packet
            )
        else:
            section = section_of(packets, unit["id"])
            assert (
                review.unit_greek_excerpt(
                    unit,
                    byzantine,
                    review.unit_passages(unit, byzantine, prepared, index["prepared"]),
                )
                in section
            )
            if unit["id"] in contrasts:
                old, new = unit["tr_accented"], unit["rp_accented"]
                assert (
                    f"apparatus accent evidence: {review.esc(old)} → {review.esc(new)}"
                    in section
                )


def test_appendix_comparisons_preserve_changes_and_retained_source_passages(
    rows: list[appendix.Row], entries: dict[str, list[Node]]
) -> None:
    for row in rows:
        lines = [
            line
            for line in entries[row.reference][1:]
            if not text_of(line).startswith("apparatus:")
        ]
        for line in lines:
            before, after = (
                (row.greek_tr, row.greek_rp)
                if text_of(line).startswith("TR")
                else (row.kjv or "", row.oleb or "")
            )
            content = line["content"][1:]  # Leave the paragraph's label out.
            insertion_style = "bd" if before == row.greek_tr else "it"
            old: list[str] = []
            new: list[str] = []
            deleted = False
            for i, item in enumerate(content):
                if item == "[":
                    deleted = True
                elif item == "]":
                    deleted = False
                elif (
                    item == " "
                    and i > 0
                    and content[i - 1] == "]"
                    and usj.is_type(content[i + 1], "char", insertion_style)
                ):
                    continue  # The separator between a replaced pair.
                elif deleted:
                    old.append(usj.text_of([item]))
                elif usj.is_type(item, "char", insertion_style):
                    new.append(usj.text_of([item]))
                else:
                    old.append(usj.text_of([item]))
                    new.append(usj.text_of([item]))
            # Printed separators need not belong to either source reading.
            for source, reconstructed in (
                (before, "".join(old)),
                (after, "".join(new)),
            ):
                at = 0
                source_chars = "".join(source.split())
                if before == row.greek_tr:
                    source_chars = greek_display(source_chars).lower()
                for passage in reconstructed.split("…"):
                    chars = "".join(passage.split())
                    if before == row.greek_tr:
                        chars = chars.lower()
                    if chars:
                        at = source_chars.index(chars, at) + len(chars)

            # Source spans still reconstruct both originals exactly; clipping
            # retains exact passages, including their internal whitespace.
            spans = (
                anchored(before, after, row.greek_ranges)
                if before == row.greek_tr
                else diff_spans(before, after)
            )
            for source, absent in ((before, "insert"), (after, "delete")):
                assert "".join(v for k, v in spans if k != absent) == source
                retained = "".join(v for k, v in clipped(spans) if k != absent)
                at = 0
                for passage in retained.split("…"):
                    if passage.strip():
                        at = source.index(passage.strip(), at) + len(passage.strip())
            if before == after:
                assert not any(
                    n.get("marker") in {"bd", "it"} for n in usj.walk(content)
                )
                assert "[" not in usj.text_of(content)


def test_appendix_blocks_leave_rows_unchanged(
    rows: list[appendix.Row], ctx: bible.annotate.Context
) -> None:
    original = copy.deepcopy(rows)
    appendix.blocks(rows, ctx.books, LABELS)
    assert rows == original


def test_rp_dot_is_normalized_inside_the_greek_font() -> None:
    content = appendix.greek("καί∙ καί")
    assert content == [usj.char("wg", "καί· καί")]


def test_acts_13_41_keeps_the_word_change_without_dot_changes(
    byzantine: Context, entries: dict[str, list[Node]]
) -> None:
    markdown = review.greek_verses(
        byzantine, "ACT 13:41", appendix.prepare_greek(byzantine)
    )[0]
    assert "[-ἔργον ᾧ][+ὃ]" in markdown
    assert "[-·]" not in markdown and "[+∙]" not in markdown
    content = entries["ACT 13:41"][1]["content"]
    assert "[ἔργον ᾧ] ὃ οὐ μὴ πιστεύσητε," in usj.text_of(content)
    assert "ἐν ταῖς ἡμέραις ὑμῶν," not in usj.text_of(content)
    assert usj.char("bd", usj.char("wg", "ὃ")) in content
    assert usj.text_of(content).startswith("TR → RP … [ἔργον ᾧ]")
    english = entries["ACT 13:41"][2]["content"]
    assert usj.text_of(english).startswith("KJV → OLEB … [a work]")
    assert "for I work" not in usj.text_of(entries["ACT 13:41"])
    assert "[a work] which you shall in no wise believe," in usj.text_of(english)
    assert not any(n.get("marker") in {"it", "bd"} for n in usj.walk(english))


@pytest.mark.parametrize("ref", ["REV 22:7", "REV 22:8"])
def test_revelation_corresponding_passages_keep_sentence_changes(
    byzantine: Context,
    ref: str,
) -> None:
    from bible.byzantine.presentation import passage_spans

    tr, rp, _ = appendix.prepare_greek(byzantine)
    verse = verses_of(byzantine["prepared"])[ref]
    texts, selected, english = appendix.selections(
        byzantine,
        ref,
        ref,
        " ".join(tr[ref]),
        " ".join(rp[ref]),
        scripture.plain(byzantine["kjv"][ref]),
        scripture.plain(verse.text),
    )
    greek = appendix.passage_ranges(byzantine, ref, ref, texts[0], texts[1])
    for passage in selected:
        comparisons = [
            passage_spans(texts, passage, 0, greek, greek=True),
            passage_spans(texts, passage, 2, english),
        ]
        assert marked_comparison(comparisons[0]).count("…") == marked_comparison(
            comparisons[1]
        ).count("…")
        for side, spans in zip((0, 2), comparisons):
            for offset, absent in ((0, "insert"), (1, "delete")):
                a, b = passage[side + offset]
                quoted = (
                    "".join(v for k, v in spans if k != absent).replace("…", "").strip()
                )
                source = texts[side + offset][a:b].strip()
                if side == 0:
                    assert (
                        greek_display(quoted).lower() == greek_display(source).lower()
                    )
                else:
                    assert quoted == source
    if ref.endswith(":8"):
        # Both occurrences retain their own sentence context and construction.
        assert english
        assert all(texts[2][b:] == texts[3][d:] for _, b, _, d in english)
        spans = anchored(texts[2], texts[3], english)
        assert "".join(v for k, v in spans if k != "insert") == texts[2]
        assert "".join(v for k, v in spans if k != "delete") == texts[3]


def marked_comparison(spans: list[tuple[str, str]]) -> str:
    from bible.byzantine.presentation import marked

    return marked(spans)


def test_uncertain_revision_boundaries_quote_complete_verse(
    byzantine: Context,
) -> None:
    ref = "REV 22:7"
    tr, rp, _ = appendix.prepare_greek(byzantine)
    verse = verses_of(byzantine["prepared"])[ref]
    before, after = scripture.plain(byzantine["kjv"][ref]), scripture.plain(verse.text)
    texts, selected, _ = appendix.selections(
        byzantine,
        ref,
        ref,
        " ".join(tr[ref]),
        " ".join(rp[ref]),
        "A different opening" + before[6:],
        after,
    )
    assert selected == (tuple((0, len(t)) for t in texts),)
    # Missing evidence is an error, not an uncertain correspondence.
    missing: Context = {**byzantine, "aligned": {}, "crosswire": {}}
    with pytest.raises(KeyError):
        appendix.selections(
            missing, ref, ref, " ".join(tr[ref]), " ".join(rp[ref]), before, after
        )


def test_shared_selections_retain_every_change_and_corresponding_omission(
    rows: list[appendix.Row],
) -> None:
    for row in rows:
        texts = (row.greek_tr, row.greek_rp, row.kjv or "", row.oleb or "")
        selected = row.passages or (tuple((0, len(t)) for t in texts),)
        for side, anchors in ((0, row.greek_ranges), (2, row.english_ranges)):
            if side == 2 and row.kjv is None:
                continue
            whole = anchored(texts[side], texts[side + 1], anchors, greek=side == 0)
            excerpts = [
                span
                for p in selected
                for span in passage_spans(texts, p, side, anchors, greek=side == 0)
            ]
            for kind in ("delete", "insert"):
                assert "".join(v for k, v in excerpts if k == kind) == "".join(
                    v for k, v in whole if k == kind
                ), row.reference
        if row.kjv is not None and row.oleb is not None:
            for passage in selected:
                assert len({a == 0 for a, _ in passage}) == 1
                assert len({b == len(t) for (_, b), t in zip(passage, texts)}) == 1


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("1JN 5:7", "μαρτυροῦντες, [ἐν τῷ οὐρανῷ"),
        ("ACT 13:42", "ῥήματα. [ταῦτα.]"),
    ],
)
def test_appendix_separates_readings_after_inserted_punctuation(
    entries: dict[str, list[Node]], ref: str, expected: str
) -> None:
    assert expected in usj.text_of(entries[ref][1]["content"])


def test_unchanged_english_clips_greek_without_a_bridge(
    byzantine: Context, rows: list[appendix.Row], entries: dict[str, list[Node]]
) -> None:
    ref = "ACT 13:22"
    row = next(row for row in rows if row.reference == ref)
    assert row.kjv is None and row.oleb is None
    tr, rp, _ = appendix.prepare_greek(byzantine)
    before = scripture.plain(byzantine["kjv"][ref])
    texts, selected, english = appendix.selections(
        {**byzantine, "aligned": {}},
        ref,
        ref,
        " ".join(tr[ref]),
        " ".join(rp[ref]),
        before,
        before,
    )
    assert selected == row.passages
    assert not english
    assert selected[0][0][0] > 0 and selected[0][1][0] > 0
    assert all(p[2:] == ((0, len(before)), (0, len(before))) for p in selected)
    comparison = " / ".join(
        marked_comparison(passage_spans(texts, p, 0, row.greek_ranges, greek=True))
        for p in selected
    )
    assert comparison.count("[-Δαβὶδ]") == 2
    assert comparison.count("[+Δαυὶδ]") == 2
    assert "…" in comparison
    whole = anchored(texts[0], texts[1], row.greek_ranges, greek=True)
    excerpts = [
        span
        for p in selected
        for span in passage_spans(texts, p, 0, row.greek_ranges, greek=True)
    ]
    for kind in ("delete", "insert"):
        assert "".join(v for k, v in excerpts if k == kind) == "".join(
            v for k, v in whole if k == kind
        )
    assert "KJV → OLEB" not in usj.text_of(entries[ref])


def test_luke_deletion_has_corresponding_clause_excerpts(
    rows: list[appendix.Row], packets: dict[str, str]
) -> None:
    row = next(row for row in rows if row.reference == "LUK 17:4")
    assert row.kjv is not None and row.oleb is not None
    texts = (row.greek_tr, row.greek_rp, row.kjv, row.oleb)
    passage = row.passages[0]
    assert all(a > 0 for a, _ in passage)
    assert texts[0][slice(*passage[0])].startswith("καὶ ἑπτάκις")
    assert texts[2][slice(*passage[2])].startswith("and seven times")
    greek = marked_comparison(
        passage_spans(texts, passage, 0, row.greek_ranges, greek=True)
    )
    english = marked_comparison(passage_spans(texts, passage, 2, row.english_ranges))
    assert "ἐπί σε" in greek and "[- to thee]" in english
    section = section_of(packets, "LUK 17:4#1")
    assert (
        "English at this unit · KJV LUK 17:4 → OLEB LUK 17:4: ` … and seven times"
        in section
    )


@pytest.mark.parametrize("ref", ["LUK 17:4", "REV 22:7", "REV 22:8"])
def test_missing_execution_evidence_keeps_complete_comparisons(
    byzantine: Context, ref: str
) -> None:
    context: Context = {
        **byzantine,
        "dispositions": copy.deepcopy(byzantine["dispositions"]),
    }
    edits = [
        e
        for row in context["dispositions"]
        for e in row.get("edits", [])
        if e["ref"] == ref
    ]
    assert edits
    for edit in edits:
        edit["note_scope"].pop("source_range", None)
        edit.pop("applied_range", None)
    tr, rp, _ = appendix.prepare_greek(context)
    verse = verses_of(context["prepared"])[ref]
    args = (
        ref,
        ref,
        " ".join(tr[ref]),
        " ".join(rp[ref]),
        scripture.plain(context["kjv"][ref]),
        scripture.plain(verse.text),
    )
    if ref == "LUK 17:4":
        # An insertion or omission without the executor's range is an error.
        with pytest.raises(KeyError, match="applied_range"):
            appendix.selections(context, *args)
        return
    texts, selected, _ = appendix.selections(context, *args)
    assert selected == (tuple((0, len(t)) for t in texts),)


@pytest.mark.parametrize("kind", ["insert", "delete"])
def test_english_construction_ranges_are_derived_locally(
    byzantine: Context, kind: str
) -> None:
    tr, rp, _ = appendix.prepare_greek(byzantine)
    verses = verses_of(byzantine["prepared"])
    edit = next(
        e
        for row in byzantine["dispositions"]
        for e in row.get("edits", [])
        if e["kind"] == kind
        and e.get("note_scope", {}).get("range")
        and e["ref"] in byzantine["aligned"]
    )
    ref = edit["ref"]
    dispositions = copy.deepcopy(byzantine["dispositions"])
    for row in dispositions:
        for e in row.get("edits", []):
            if e["ref"] == ref and e["kind"] == kind:
                e["note_scope"].pop("source_range", None)
    context: Context = {**byzantine, "dispositions": dispositions}
    snapshot = copy.deepcopy(dispositions)
    texts, selected, english = appendix.selections(
        context,
        ref,
        ref,
        " ".join(tr[ref]),
        " ".join(rp[ref]),
        scripture.plain(byzantine["kjv"][ref]),
        scripture.plain(verses[ref].text),
    )
    assert english
    assert context["dispositions"] == snapshot
    spans = anchored(texts[2], texts[3], english)
    excerpts = [span for p in selected for span in passage_spans(texts, p, 2, english)]
    for change in ("delete", "insert"):
        assert "".join(v for k, v in spans if k == change) == "".join(
            v for k, v in excerpts if k == change
        )


@pytest.mark.parametrize(
    ("ref", "target"),
    [
        ("MAT 23:14", "MAT 23:13"),
        ("MAT 23:13", "MAT 23:14"),
        ("ROM 16:25", "ROM 14:24"),
        ("ROM 16:26", "ROM 14:25"),
        ("ROM 16:27", "ROM 14:26"),
    ],
)
def test_verified_moves_use_source_and_destination(
    byzantine: Context,
    ref: str,
    target: str,
) -> None:
    tr, rp, _ = appendix.prepare_greek(byzantine)
    texts, selected, english = appendix.selections(
        byzantine,
        ref,
        target,
        " ".join(tr[ref]),
        " ".join(rp[target]),
        scripture.plain(byzantine["kjv"][ref]),
        scripture.plain(verses_of(byzantine["prepared"])[target].text),
    )
    if ref.startswith("MAT"):
        assert len(selected) == 1
        passage = selected[0]
        assert [text[slice(*span)].strip() for text, span in zip(texts, passage)] == (
            ["Οὐαὶ ὑμῖν,", "Οὐαὶ δὲ ὑμῖν,", "Woe unto you,", "But woe unto you,"]
            if ref == "MAT 23:14"
            else ["Οὐαὶ δὲ ὑμῖν,", "Οὐαὶ ὑμῖν,", "But woe unto you,", "Woe unto you,"]
        )
        assert all(b < len(t) for (_, b), t in zip(passage, texts))
        assert english
    elif ref == "ROM 16:27":
        assert english
        assert len(selected) == 1
        assert texts[2][slice(*selected[0][2])].strip().endswith("for ever.")
        assert texts[3][slice(*selected[0][3])].strip().endswith("for ever.")
        assert all(b < len(t) for (_, b), t in zip(selected[0], texts))
    else:
        assert texts[2] == texts[3]
        assert not english
    context: Context = {
        **byzantine,
        "dispositions": [
            row
            for row in byzantine["dispositions"]
            if not (row["ref"] == ref and row["disposition"] == "structural")
        ],
    }
    _, fallback, _ = appendix.selections(
        context, ref, target, texts[0], texts[1], texts[2], texts[3]
    )
    assert fallback == (tuple((0, len(t)) for t in texts),)


@pytest.mark.parametrize("inside", [False, True])
def test_partial_tags_require_only_selected_coverage(
    byzantine: Context, inside: bool
) -> None:
    ref, target = "MAT 23:14", "MAT 23:13"
    tags = copy.deepcopy(byzantine["crosswire"])
    link = tags[ref]["links"][0 if inside else -1]
    link["forms"] = ["wrong"] * len(link["forms"])
    context: Context = {**byzantine, "aligned": {}, "crosswire": tags}
    tr, rp, _ = appendix.prepare_greek(context)
    texts, selected, _ = appendix.selections(
        context,
        ref,
        target,
        " ".join(tr[ref]),
        " ".join(rp[target]),
        scripture.plain(context["kjv"][ref]),
        scripture.plain(verses_of(context["prepared"])[target].text),
    )
    whole = (tuple((0, len(t)) for t in texts),)
    assert (selected == whole) == inside


def test_crossing_bridge_cannot_clip_a_moved_passage(byzantine: Context) -> None:
    ref, target = "MAT 23:13", "MAT 23:14"
    aligned = copy.deepcopy(byzantine["aligned"])
    aligned[ref]["positions"][0].append(len(byzantine["tr"][ref]) - 1)
    context: Context = {**byzantine, "aligned": aligned}
    tr, rp, _ = appendix.prepare_greek(context)
    texts, selected, _ = appendix.selections(
        context,
        ref,
        target,
        " ".join(tr[ref]),
        " ".join(rp[target]),
        scripture.plain(context["kjv"][ref]),
        scripture.plain(verses_of(context["prepared"])[target].text),
    )
    assert selected == (tuple((0, len(t)) for t in texts),)


def test_matthew_moved_comparison_prints_matching_ellipses(
    entries: dict[str, list[Node]], packets: dict[str, str]
) -> None:
    content = entries["MAT 23:13"]
    printed = usj.text_of(content)
    assert "Οὐαὶ δὲ ὑμῖν, …" in printed
    assert "[Woe] But woe unto you, …" in printed
    assert usj.char("it", "But woe") in content[2]["content"]
    section = section_of(packets, "MAT 23:14#1")
    assert "` Οὐαὶ [+δὲ ]ὑμῖν, … `" in section
    assert "` [-Woe][+But woe] unto you, … `" in section


@pytest.mark.parametrize("side", ["greek", "english"])
@pytest.mark.parametrize("boundary", [False, True])
def test_appendix_missing_correspondence_must_be_bounded_in_both_languages(
    byzantine: Context, side: str, boundary: bool
) -> None:
    from bible.byzantine.crosswire import presentation_bridge

    ref = "ACT 13:41"
    tr, rp, _ = appendix.prepare_greek(byzantine)
    before = scripture.plain(byzantine["kjv"][ref])
    after = scripture.plain(verses_of(byzantine["prepared"])[ref].text)
    aligned = copy.deepcopy(byzantine["aligned"])
    aligned[ref] = presentation_bridge(
        byzantine["crosswire"][ref], byzantine["tr"][ref], byzantine["kjv"][ref]
    )
    bridge = aligned[ref]
    if side == "greek":
        position = byzantine["tr"][ref].index("pisteushte" if boundary else "ou")
        assert any(position in ps for ps in bridge["positions"])
        bridge["positions"] = [
            [p for p in ps if p != position] for ps in bridge["positions"]
        ]
    else:
        word = next(
            i
            for i, (a, b) in enumerate(bridge["word_ranges"])
            if before[a:b] == ("believe" if boundary else "no")
        )
        assert bridge["positions"][word]
        bridge["positions"][word] = []
    context: Context = {**byzantine, "aligned": aligned}
    texts, selected, _ = appendix.selections(
        context, ref, ref, " ".join(tr[ref]), " ".join(rp[ref]), before, after
    )
    assert (selected == (tuple((0, len(t)) for t in texts),)) == boundary
    if not boundary:
        assert texts[0][slice(*selected[0][0])].startswith("ἔργον ᾧ")
        assert texts[2][slice(*selected[0][2])].startswith("a work which")


@pytest.mark.parametrize("bad", ["form", "position", "length", "conflict"])
def test_appendix_invalid_interior_tags_keep_complete_verse(
    byzantine: Context, bad: str
) -> None:
    ref = "ACT 13:41"
    tags = copy.deepcopy(byzantine["crosswire"])
    row = tags[ref]
    link = next(
        link for link in row["links"] if "no wise" in row["text"][slice(*link["range"])]
    )
    assert link["src"] and link["forms"]
    if bad == "form":
        link["forms"][0] = "wrong"
    elif bad == "position":
        link["src"][0] = "0"
    elif bad == "length":
        link["forms"] = []
    else:
        row["links"].append({**link, "forms": ["wrong"] * len(link["forms"])})
    context: Context = {**byzantine, "aligned": {}, "crosswire": tags}
    tr, rp, _ = appendix.prepare_greek(context)
    texts, selected, _ = appendix.selections(
        context,
        ref,
        ref,
        " ".join(tr[ref]),
        " ".join(rp[ref]),
        scripture.plain(byzantine["kjv"][ref]),
        scripture.plain(verses_of(byzantine["prepared"])[ref].text),
    )
    assert selected == (tuple((0, len(t)) for t in texts),)
