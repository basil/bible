"""The review of the reconciliation, one file for each book with every
non-neutral unit once, markdown safe; and the textual variants."""

from __future__ import annotations

import copy
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping
from dataclasses import replace
from typing import Literal, cast

import pytest
from conftest import amended

import bible.annotate
import bible.pipeline
from bible import revision, scripture, usj
from bible.byzantine import BOOKS, BOYD_ASV, REVISIONS, review, variants
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
from bible.byzantine.rows import Disposition, InstructionEdit, RevisionRow, Unit
from bible.byzantine.stages import Reconciliation
from bible.checks import CheckFailed
from bible.usj import Document

HEADING = re.compile(
    r"^## (?P<unit>[1-3A-Z]{3} \d+:\d+#\S+) · (?P<disposition>\w+)(?: · (?P<action>\w+))? · score (?P<score>\d+)$"
)


@pytest.fixture(scope="module")
def finished(edition: bible.pipeline.Edition) -> dict[str, Document]:
    """The New Testament's books as the edition finished them."""
    return {code: edition.documents[code] for code in BOOKS}


@pytest.fixture(scope="module")
def packets(byzantine: Reconciliation, finished: dict[str, Document]) -> dict[str, str]:
    return review.packets(byzantine, finished)


@pytest.fixture(scope="module")
def index(byzantine: Reconciliation, finished: dict[str, Document]) -> review.Index:
    return review.build_index(byzantine, finished)


def section_of(packets: Mapping[str, str], uid: str) -> str:
    """A unit's section of its book's file, from its heading to the next."""
    lines = packets[f"{uid.split()[0]}.md"].splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"## {uid} · "))
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end])


def unit_of(byzantine: Reconciliation, uid: str) -> Unit:
    return next(u for u in byzantine.greek.units if u["id"] == uid)


def test_the_books_are_the_only_packet_files(packets: dict[str, str]) -> None:
    assert set(packets) == {f"{b}.md" for b in BOOKS}


def test_each_packet_says_what_it_is(packets: dict[str, str]) -> None:
    for book in BOOKS:
        text = packets[f"{book}.md"]
        assert text.startswith(f"# {book}\n\nEvery Scrivener-RP2026 unit in the book.")
        assert "src/bible/byzantine/tags.py" in text
        assert "rpkjv" not in text


def test_every_non_neutral_unit_has_exactly_one_section(
    byzantine: Reconciliation, packets: dict[str, str]
) -> None:
    headings = []
    for book in BOOKS:
        for line in packets[f"{book}.md"].splitlines():
            if line.startswith("## ") and line not in {
                "## Neutral units",
                review.LOOSE_HEADING,
                "## Corrections of shared Greek",
            }:
                m = HEADING.match(line)
                assert m, line
                headings.append(m["unit"])
    expected = [
        r["unit"]
        for r in byzantine.verified.dispositions
        if r["disposition"] not in {"neutral", "shared"}
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
    byzantine: Reconciliation, packets: dict[str, str]
) -> None:
    neutral = [
        r["unit"]
        for r in byzantine.verified.dispositions
        if r["disposition"] == "neutral"
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
    byzantine: Reconciliation, packets: dict[str, str]
) -> None:
    rows = {r["unit"]: r for r in byzantine.verified.dispositions}
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
    byzantine: Reconciliation, ref: str, target: str
) -> None:
    assert_greek_preserved(byzantine, ref, target)


def assert_greek_preserved(
    byzantine: Reconciliation,
    ref: str,
    target: str,
    prepared: variants.PreparedGreek | None = None,
) -> None:
    prepared = prepared if prepared is not None else variants.prepare_greek(byzantine)
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
    byzantine: Reconciliation, packets: dict[str, str]
) -> None:
    lines = review.greek_verses(byzantine, "MAT 3:8", variants.prepare_greek(byzantine))
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
    byzantine: Reconciliation, packets: dict[str, str], index: review.Index
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
    assert "Thou shalt not kill: TR Do not kill" in section
    assert "### " not in section
    assert len(text.splitlines()) < 900
    assert (
        "at unit: ` … [-Do][+Thou shalt] not kill. … ` (includes Boyd revision)"
        in section
    )
    witnesses = review.witness_lines(unit_of(byzantine, "JAS 2:5#1"), byzantine, index)
    assert all(line.startswith("- ") and line.count("\n") <= 1 for line in witnesses)
    assert not any("| Before" in line for line in witnesses)


def test_a_note_names_the_witness_the_edition_prints(
    packets: dict[str, str], index: review.Index
) -> None:
    # Scrivener alone has "joy", after the Complutensian, which the note names.
    section = section_of(packets, "PHM 1:7#1")
    assert "Received Text: Scrivener alone (SCR)" in section
    assert "thankfulness: Complutensian text joy" in section
    # Every note the packets show is one the edition prints, an omitted
    # verse's included.
    printed = sorted(
        {review.esc(review.note_text(n)) for n in index["printed"].values()},
        key=len,
        reverse=True,
    )
    for text in packets.values():
        for line in text.splitlines():
            rest = line.removeprefix("⁺ ").rstrip() if line.startswith("⁺ ") else ""
            while rest:
                note = next(
                    (p for p in printed if rest == p or rest.startswith(p + "; ")),
                    None,
                )
                assert note, line
                rest = rest[len(note) + 2 :]
    assert "⁺ 17:35 " in section_of(packets, "LUK 17:36#1")
    # An epistle's subscription is no part of its last verse.
    assert index["finished"]["PHP 4:23"].text.endswith("Amen.")


def test_real_verse_diffs_preserve_both_texts(byzantine: Reconciliation) -> None:
    pairs = {(u["ref"], u["target_ref"]) for u in byzantine.greek.units}
    inputs = [
        (
            " ".join(byzantine.greek.tr.get(ref, [])),
            " ".join(byzantine.greek.rp.get(target, [])),
        )
        for ref, target in pairs
    ]
    for book, doc in byzantine.edited.prepared.items():
        inputs.extend(
            (byzantine.english.kjv.get(f"{book} {address}", ""), verse.text)
            for address, verse in scripture.verses(doc).items()
        )
    for before, after in inputs:
        spans = diff_spans(before, after)
        assert "".join(text for kind, text in spans if kind != "insert") == before
        assert "".join(text for kind, text in spans if kind != "delete") == after


def test_greek_diff_marks_accents(byzantine: Reconciliation) -> None:
    lines = review.greek_verses(byzantine, "PHP 3:5", variants.prepare_greek(byzantine))
    assert "[-περιτομὴ][+περιτομῇ]" in lines[0]


def test_no_table_row_is_broken_by_its_content(
    byzantine: Reconciliation, packets: dict[str, str]
) -> None:
    for name, text in {**packets, "summary": review.summary(byzantine)}.items():
        for line in text.splitlines():
            if line.startswith("| ") and not line.startswith("| ---"):
                cells = re.split(r"(?<!\\)\|", line.strip("|"))
                assert len(cells) in {2, 3, 4, 5}, (name, line)


def test_greek_context_uses_ledger_and_is_shown_once(
    byzantine: Reconciliation, packets: dict[str, str]
) -> None:
    lines = review.greek_verses(
        byzantine, "PHM 1:17", variants.prepare_greek(byzantine)
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
    byzantine: Reconciliation, index: review.Index
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
    byzantine: Reconciliation, index: review.Index
) -> None:
    lines = review.witness_lines(unit_of(byzantine, "JAS 2:18#1"), byzantine, index)
    pierpont = next(line for line in lines if line.startswith("- Pierpont 565:"))
    assert "KJV context (proposal): ` … shew me thy faith [-without]" in pierpont
    assert "blocked (override JAS 2:18#1 takes this construction)" in pierpont


def test_unit_greek_context_uses_corresponding_passage(
    byzantine: Reconciliation,
) -> None:
    prepared = variants.prepare_greek(byzantine)
    verses = verses_of(byzantine.edited.prepared)
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
                variants.passage_ranges(
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
    byzantine: Reconciliation,
) -> None:
    prepared = variants.prepare_greek(byzantine)
    for ref, target in {(u["ref"], u["target_ref"]) for u in byzantine.greek.units}:
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
    byzantine: Reconciliation, index: review.Index
) -> None:
    unit = unit_of(byzantine, "JAS 2:11#1")
    lines = review.witness_lines(unit, byzantine, index)
    line = next(line for line in lines if line.startswith("- Boyd ASV 2021 ("))
    assert "ASV 1901 → Boyd ASV 2021 (whole verse):" in line
    assert "KJV contrast at unit:" in line
    expected = review.diff_markup(
        diff_spans(
            scripture.plain(byzantine.english.texts["asv"][unit["ref"]]),
            scripture.plain(byzantine.english.texts[BOYD_ASV][unit["ref"]]),
        )
    )
    assert expected in line


def test_patriarchal_agreement_is_relative_to_rp2026(
    byzantine: Reconciliation, index: review.Index
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
        for u in byzantine.greek.units
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
    byzantine: Reconciliation, index: review.Index
) -> None:
    for unit in byzantine.greek.units:
        if index["rows"][unit["id"]]["disposition"] == "neutral":
            continue
        lines = review.witness_lines(unit, byzantine, index)
        for name in REVISIONS:
            if not byzantine.english.texts[name].get(unit["ref"]):
                continue
            line = next(
                line for line in lines if line.startswith(f"- {review.NAMES[name]} (")
            )
            rows = [
                r for r in index["revisions_at"][unit["id"]] if r["witness"] == name
            ]
            if unit["id"] not in byzantine.revisions.admitted[name]:
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
    byzantine: Reconciliation, index: review.Index
) -> None:
    lines = review.witness_lines(unit_of(byzantine, "PHM 1:1#1"), byzantine, index)
    line = next(line for line in lines if line.startswith("- Boyd ASV 2021 ("))
    assert "not admitted at this unit: RP2026 Appendix A" in line
    assert "ASV 1901 → Boyd ASV 2021 (whole verse):" in line


def test_report_attachment_scope_is_visible(
    byzantine: Reconciliation, index: review.Index
) -> None:
    report = next(
        r
        for r in byzantine.apparatuses.reports
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
    byzantine: Reconciliation, index: review.Index
) -> None:
    for unit in byzantine.greek.units:
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


def test_a_correction_of_shared_greek_has_its_section_in_its_book(
    packets: dict[str, str],
) -> None:
    packet = packets["LUK.md"]
    section = packet[packet.index("### LUK 23:42\n") :]
    assert packet.index("## Corrections of shared Greek") < packet.index(
        "### LUK 23:42\n"
    )
    assert "Greek whole verse · TR LUK 23:42 → RP2026 LUK 23:42" in section
    assert "KJV LUK 23:42 → OLEB LUK 23:42" in section
    assert (
        "- into thy kingdom → in thy kingdom · shared Greek ἐν τῇ βασιλείᾳ σου"
        in section
    )
    # Only the verses corrected are shown, not every verse without a unit.
    assert "### LUK 23:41\n" not in packet


def test_the_summary_counts_the_dispositions(byzantine: Reconciliation) -> None:
    text = review.summary(byzantine)
    assert text.startswith("# The Byzantine New Testament\n")
    counts = Counter(r["disposition"] for r in byzantine.verified.dispositions)
    # Only the dispositions table: the sources of wording tabulate the rows
    # executed by disposition too.
    table = text.split("## Dispositions\n")[1].split("\n## ")[0]
    for disposition, number in counts.items():
        assert f"| {disposition} | {number} |\n" in table
    for name, result in byzantine.verified.invariants.items():
        assert f"- {name}: {result}" in text


def test_the_summary_tallies_the_sources_of_wording(
    byzantine: Reconciliation,
) -> None:
    text = review.summary(byzantine)
    all_executed = [
        r for r in byzantine.verified.dispositions if r.get("execution") == "applied"
    ]
    # A row that only marks or unmarks supplied words prints the same words
    # and writes no note: it is counted apart from the changes of wording.
    marking = [r for r in all_executed if review.marking_only(r)]
    assert marking and all(
        e["old"] == e["new"] and "note" not in e for r in marking for e in r["edits"]
    )
    executed = [r for r in all_executed if not review.marking_only(r)]
    assert executed
    froms = [
        [t.removeprefix("from:") for t in r["tags"] if t.startswith("from:")]
        for r in executed
    ]
    # Every row carried out, a change of marking alone included, says where
    # its wording comes from, one source or more, but a verse moved or
    # omitted and a correction of shared Greek, which have no wording of
    # their own.
    assert all(
        any(t.startswith("from:") for t in r["tags"])
        == (r["disposition"] not in {"structural", "shared"})
        for r in all_executed
    )
    sources = Counter(t for tags in froms for t in tags or ["(none)"])
    dispositions = Counter(r["disposition"] for r in executed)
    section = text.split("## Sources of wording\n")[1].split("\n## ")[0]
    assert (
        f"Of the rows executed, {len(marking)} only mark or unmark a supplied "
        f"word, printing the same words with no note; the tables count the "
        f"{len(executed)} that change the words."
    ) in section
    assert len(marking) + len(executed) == len(all_executed)
    marking_froms = Counter(
        t.removeprefix("from:")
        for r in marking
        for t in [t for t in r["tags"] if t.startswith("from:")] or ["(none)"]
    )
    line = section.split("Changes of marking alone, by source: ")[1].split("\n")[0]
    listed = [item.rsplit(" ", 1) for item in line.removesuffix(".").split(", ")]
    # Ranked as the tables are: most rows first, then by name, and rows with
    # no source last.
    assert [(k, int(n)) for k, n in listed] == sorted(
        marking_froms.items(), key=lambda kv: (kv[0] == "(none)", -kv[1], kv[0])
    )
    several = Counter(len(tags) for tags in froms if len(tags) > 1)
    assert several[2]
    assert (
        "Rows drawing on more than one source: "
        + ", ".join(f"{n} on {k} sources" for k, n in sorted(several.items()))
        + "."
    ) in section
    printed: dict[str, list[str]] = {}
    for head, counts in (("Source", sources), ("Disposition", dispositions)):
        rows = (
            section.split(f"| {head} | Rows | Share |\n| --- | --- | --- |\n")[1]
            .split("\n\n")[0]
            .splitlines()
        )
        assert len(rows) == len(counts)
        for name, number in counts.items():
            share = f"{100 * number / len(executed):.1f}%"
            assert f"| {name} | {number} | {share} |" in rows
        printed[head] = rows
    # The source table's total reconciles with the rows executed.
    assert sum(int(row.split(" | ")[1]) for row in printed["Source"]) == len(
        executed
    ) + sum(n * (k - 1) for k, n in several.items())


# The textual variants.

OMITTED = {"LUK 17:36", "ACT 8:37", "ACT 15:34", "ACT 24:7"}


def greek_label(row: variants.Row) -> str:
    """The Received Text's, or Scrivener's where the apparatuses do not
    establish its readings as the Received Text's (received.py)."""
    return "TR" if row.received else "Scrivener"


GAP: variants.Gap = {"gap": True}


def readings(lane: variants.Lane) -> list[tuple[str | None, str | None]]:
    """A lane's readings in order, each witness's words without the spaces
    about them, or None where it has nothing."""
    return [
        (
            cast(variants.Reading, s).get("from", "").strip() or None,
            cast(variants.Reading, s).get("to", "").strip() or None,
        )
        for s in lane["segments"]
        if not isinstance(s, str) and ("from" in s or "to" in s)
    ]


def shown(lane: variants.Lane) -> str:
    """A lane's words in one line: the words the witnesses share, both
    readings where they differ, and an ellipsis for each gap."""
    return "".join(
        (
            variants.witness([s], "from")
            if isinstance(s, str) or "gap" in s or "about" in s
            else " ".join(s[k] for k in ("from", "to") if k in s)
        )
        for s in lane["segments"]
    )


@pytest.fixture(scope="module")
def printed(
    byzantine: Reconciliation, policy: bible.policy.Policy
) -> dict[str, Document]:
    """The New Testament's books after the readings, with the edition's
    systematic spelling and punctuation but before its verse-specific
    revisions, as the variants quote them."""
    return {
        code: revision.regularized(revision.named(code, doc, policy, set()), policy)
        for code, doc in byzantine.edited.prepared.items()
        if code in BOOKS
    }


@pytest.fixture(scope="module")
def regularized(
    byzantine: Reconciliation, policy: bible.policy.Policy
) -> dict[str, Document]:
    """The King James books before the readings, with the edition's
    systematic spelling and punctuation, as the variants compare them."""
    return {
        code: revision.regularized(doc, policy)
        for code, doc in byzantine.english.documents.items()
    }


@pytest.fixture(scope="module")
def rows(
    byzantine: Reconciliation,
    regularized: dict[str, Document],
    printed: dict[str, Document],
) -> list[variants.Row]:
    return variants.rows(byzantine, regularized, printed)


@pytest.fixture(scope="module")
def entries(
    rows: list[variants.Row], ctx: bible.annotate.Context
) -> dict[str, list[variants.Lane]]:
    """Each row's lanes, by the verse it is about."""
    return {row.reference: variants.lanes(row, ctx.terms) for row in rows}


def test_romans_amen_keeps_shared_sentence_punctuation(
    entries: dict[str, list[variants.Lane]], packets: dict[str, str]
) -> None:
    greek, english = entries["ROM 16:20"]
    for lane, shared, dropped in (
        (greek, "ὑμῶν.", "ἀμήν."),
        (english, "you.", "Amen."),
    ):
        *_, before, last = lane["segments"]
        assert isinstance(before, str) and before.endswith(shared)
        assert last == {"from": f" {dropped}"}
    lines = packets["ROM.md"].splitlines()
    greek_line = next(
        line for line in lines if line.startswith("Greek whole verse · TR ROM 16:20 ")
    )
    english_line = next(
        line
        for line in lines
        if line.startswith("English whole verse · KJV ROM 16:20 ")
    )
    assert "ὑμῶν.[- ][-ἀμήν.]" in greek_line
    assert "you.[- Amen.]" in english_line


def test_johannine_omission_is_one_reading(
    entries: dict[str, list[variants.Lane]], packets: dict[str, str]
) -> None:
    omitted = (
        "in heaven, the Father, the Word, and the Holy {}: and these three are one."
    )
    english = entries["1JN 5:7"][1]
    # The variants quote the King James text as the edition spells it; the
    # review quotes it as the source does.
    assert english["segments"] == [
        "For there are three that bear record",
        {"from": f" {omitted.format('Spirit')}", "to": ","},
    ]
    section = section_of(packets, "1JN 5:7#1")
    assert f"bear record[+,][- {omitted.format('Ghost')}]" in section


def test_every_verse_with_a_greek_difference_is_listed_once(
    byzantine: Reconciliation, rows: list[variants.Row]
) -> None:
    references = [row.reference for row in rows]
    assert len(references) == len(set(references))
    listed = set(references)
    for unit in byzantine.greek.units:
        if unit["class"] != "structural":
            assert unit["target_ref"] in listed, unit["id"]
    keys = [ref_key(r) for r in references]
    assert keys == sorted(keys)


def test_a_changed_verse_has_one_aligned_comparison_per_language(
    rows: list[variants.Row], entries: dict[str, list[variants.Lane]]
) -> None:
    changed = [row for row in rows if row.kjv != row.oleb and row.kind != "omitted"]
    assert len(changed) > 700
    for row in changed:
        lanes = [lane for lane in entries[row.reference] if "apparatus" not in lane]
        assert [(lane["from"], lane["to"]) for lane in lanes] == [
            (greek_label(row), "RP26"),
            ("KJV", "OLEB"),
        ], row.reference
        greek, english = (lane["segments"] for lane in lanes)
        assert greek.count(GAP) == english.count(GAP), row.reference
        for lane in lanes:
            text = shown(lane)
            assert not re.search(r"…\s*…", text), row.reference
            assert len([part for part in text.split("…") if part.strip()]) == len(
                row.passages
            ), row.reference
        assert (greek[0] == GAP) == (english[0] == GAP), row.reference
        assert (greek[-1] == GAP) == (english[-1] == GAP), row.reference
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
    # The English comparison has no note lemmas.
    assert "**" not in "".join(map(shown, entries["MAT 22:7"]))


@pytest.mark.parametrize("ref", ["REV 13:6", "REV 13:7"])
def test_revelation_grouped_comparisons_include_unchanged_english_context(
    ref: str, rows: list[variants.Row], entries: dict[str, list[variants.Lane]]
) -> None:
    row = next(row for row in rows if row.reference == ref)
    greek, english = entries[ref]
    assert len(row.passages) == 2
    for lane in (greek, english):
        assert lane["segments"].count(GAP) == 1
        assert " … " in shown(lane)
    adopted = variants.witness(english["segments"], "to")
    if ref == "REV 13:6":
        assert ("ἤνοιξε", "ἤνοιξεν") in readings(greek)
        assert ("καὶ", None) in readings(greek)
        assert "And he opened his mouth in blasphemy against God," in adopted
        assert ("and", "even") in readings(english)
        assert "even them that dwell in heaven." in adopted
    else:
        assert (None, "ποιῆσαι") in readings(greek)
        assert ("ποιῆσαι", None) in readings(greek)
        assert "φυλὴν καὶ λαὸν καὶ γλῶσσαν" in variants.witness(greek["segments"], "to")
        assert "And it was given unto him to make war with the saints," in adopted
        assert "all kindreds, and people, and tongues, and nations." in adopted
    # The first passage of the English stands unchanged, for context.
    first = english["segments"][: english["segments"].index(GAP)]
    assert first and all(isinstance(s, str) for s in first)
    assert readings(greek) and readings(english)


def test_a_verse_whose_english_stands_has_a_greek_comparison(
    rows: list[variants.Row], entries: dict[str, list[variants.Lane]]
) -> None:
    same = [row for row in rows if row.kind == "same"]
    assert same
    for row in same:
        assert row.units and row.kjv is None and row.oleb is None, row.reference
        greek, *evidence = entries[row.reference]
        assert "apparatus" not in greek
        assert (greek["from"], greek["to"]) == (greek_label(row), "RP26")
        for lane in evidence:
            assert lane.get("apparatus")
            assert (lane["from"], lane["to"], lane["language"]) == ("TR", "RP26", "grc")
    accents = [unit for row in same for unit in row.units if unit.accented]
    assert accents


def test_the_four_omitted_verses_are_listed(
    byzantine: Reconciliation,
    regularized: dict[str, Document],
    rows: list[variants.Row],
    entries: dict[str, list[variants.Lane]],
) -> None:
    omitted = [row for row in rows if row.kind == "omitted"]
    assert (
        {row.reference for row in omitted}
        == OMITTED
        == byzantine.greek.structure.omitted
    )
    for row in omitted:
        assert row.greek_tr and not row.greek_rp and row.oleb is None
        book, verse = row.reference.split()
        kjv = scripture.verses(regularized[book])[verse].text
        assert row.kjv == scripture.plain(kjv)
        greek, english = entries[row.reference]
        assert (greek["from"], greek["to"]) == (greek_label(row), "RP26")
        assert greek["segments"] == [{"from": row.greek_tr}]
        assert (english["from"], english["to"]) == ("KJV", "OLEB")
        assert english["segments"] == [{"from": row.kjv}]


def test_a_moved_verse_is_labelled_with_the_king_james_number(
    byzantine: Reconciliation,
    rows: list[variants.Row],
    entries: dict[str, list[variants.Lane]],
    printed: dict[str, Document],
) -> None:
    moved = {row.reference: row for row in rows if row.source != row.reference}
    expected = {
        target: origin for origin, target in byzantine.greek.structure.moved.items()
    }
    assert {ref: row.source for ref, row in moved.items()} == expected
    english = verses_of(printed)
    for ref, row in moved.items():
        assert row.kind == "changed"
        before = scripture.plain(byzantine.english.kjv[row.source])
        after = scripture.plain(english[ref].text)
        if before == after:
            assert row.kjv is None and row.oleb is None
            assert not any(lane["language"] == "en" for lane in entries[ref])
        assert " ".join(
            ascii_greek("".join(accent_letters(w))) for w in row.greek_tr.split()
        ) == " ".join(byzantine.greek.tr[row.source])


def test_all_variants_passages_keep_source_words(
    byzantine: Reconciliation, rows: list[variants.Row]
) -> None:
    for row in rows:
        assert row.greek_tr == " ".join(byzantine.greek.tr_alignment.text[row.source])
        assert row.greek_rp == " ".join(
            byzantine.greek.rp_alignment.text.get(row.reference, [])
        )
        units = [
            u
            for u in byzantine.greek.units
            if u["target_ref"] == row.reference and u["class"] != "structural"
        ]
        units.sort(key=lambda u: u["class"] == "accent")
        for printed, unit in zip(row.units, units, strict=True):
            for side, ref, value in (
                ("tr", unit["ref"], printed.tr),
                ("rp", unit["target_ref"], printed.rp),
            ):
                alignment = (
                    byzantine.greek.tr_alignment
                    if side == "tr"
                    else byzantine.greek.rp_alignment
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
    rows: list[variants.Row], entries: dict[str, list[variants.Lane]]
) -> None:
    row = next(r for r in rows if r.reference == "LUK 3:23")
    assert "Ἡλί" in row.greek_tr
    contrast = next(u for u in row.units if u.accented)
    assert contrast.accented is not None and contrast.accented[0] == "Ἡλί,"
    assert contrast.apparatus == ("ἠλι", "ἡλι")
    assert entries["LUK 3:23"][0]["from"] == "TR"
    assert entries["LUK 3:23"][-1] == {
        "from": "TR",
        "to": "RP26",
        "language": "grc",
        "segments": [{"from": "ἠλι", "to": "ἡλι"}],
        "apparatus": True,
    }


def test_variants_passages_and_comparisons_keep_source_case_and_punctuation(
    byzantine: Reconciliation, rows: list[variants.Row]
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
            " ".join(byzantine.greek.tr_alignment.text[row.source])
        ), row.source
        rp = byzantine.greek.printed[row.reference]["accented"]
        assert source_features(row.greek_rp) == source_features(
            " ".join(rp)
        ), row.reference
        units = [
            u
            for u in byzantine.greek.units
            if u["target_ref"] == row.reference and u["class"] != "structural"
        ]
        units.sort(key=lambda u: u["class"] == "accent")
        for printed, unit in zip(row.units, units, strict=True):
            assert source_features(printed.tr) == source_features(
                " ".join(
                    byzantine.greek.tr_alignment.text[unit["ref"]][
                        slice(
                            *variants.projected(
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
                            *variants.projected(
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


def test_unchanged_english_and_accent_only_entries_have_one_lane(
    ctx: bible.annotate.Context,
) -> None:
    row = variants.Row(
        "MAT 1:1",
        "MAT 1:1",
        "same",
        "πρῶτον; τὸ τέλος.",
        "πρῶτον; τό τέλος.",
        (variants.Unit("τὸ", "τό", ("τὸ", "τό")),),
    )
    (greek,) = variants.lanes(row, ctx.terms)
    assert (greek["from"], greek["to"]) == ("TR", "RP26")
    assert greek["segments"] == ["πρῶτον; ", {"from": "τὸ", "to": "τό"}, " τέλος."]


def test_lanes_pair_each_difference_and_keep_both_witnesses_words(
    ctx: bible.annotate.Context,
) -> None:
    row = variants.Row(
        "MAT 19:19",
        "MAT 19:19",
        "changed",
        "τίμα τὸν πατέρα σου καὶ τὴν μητέρα.",
        "τίμα τὸν πατέρα καὶ τὴν μητέρα.",
        (),
        "honour thy father and the mother.",
        "honour thy father and thy mother.",
    )
    greek, english = variants.lanes(row, ctx.terms)
    assert (greek["from"], greek["to"], greek["language"]) == ("TR", "RP26", "grc")
    assert (english["from"], english["to"], english["language"]) == (
        "KJV",
        "OLEB",
        "en",
    )
    # An omission is a reading with the source's side alone; a substitution
    # pairs both sides. Each witness's words are read whole from its side.
    assert greek["segments"] == [
        "τίμα τὸν πατέρα ",
        {"from": "σου "},
        "καὶ τὴν μητέρα.",
    ]
    assert english["segments"] == [
        "honour thy father and ",
        {"from": "the", "to": "thy"},
        " mother.",
    ]
    for lane, before, after in (
        (greek, row.greek_tr, row.greek_rp),
        (english, row.kjv, row.oleb),
    ):
        assert variants.witness(lane["segments"], "from") == before
        assert variants.witness(lane["segments"], "to") == after
    # A run of differences is one reading: here the Byzantine text drops a
    # word with the space before it, and keeps the sentence's full stop.
    dropped = variants.Row(
        "MAT 19:26",
        "MAT 19:26",
        "same",
        "τοῦτο ἀδύνατόν ἐστι, παρὰ δὲ Θεῷ πάντα δυνατά ἐστι.",
        "τοῦτο ἀδύνατόν ἐστιν, παρὰ δὲ Θεῷ πάντα δυνατά.",
        (),
    )
    (greek,) = variants.lanes(dropped, ctx.terms)
    assert greek["segments"] == [
        "τοῦτο ἀδύνατόν ",
        {"from": "ἐστι", "to": "ἐστιν"},
        ", παρὰ δὲ Θεῷ πάντα δυνατά",
        {"from": " ἐστι"},
        ".",
    ]
    # The spaces both sides open or close with are words they share, so a
    # word dropped between two is a reading of the word and one space.
    even = variants.Row(
        "MAT 12:8",
        "MAT 12:8",
        "changed",
        "ἐστι.",
        "ἐστι.",
        (),
        "For the Son of man is Lord even of the sabbath day.",
        "For the Son of man is Lord of the sabbath day.",
    )
    assert variants.lanes(even, ctx.terms)[1]["segments"] == [
        "For the Son of man is Lord ",
        {"from": "even "},
        "of the sabbath day.",
    ]
    # An addition is a reading with the adopted text's side alone, keeping
    # the space that joins it to the word before.
    added = variants.Row(
        "MAT 20:21",
        "MAT 20:21",
        "same",
        "καὶ εἷς ἐξ εὐωνύμων, ἐν τῇ βασιλείᾳ σου.",
        "καὶ εἷς ἐξ εὐωνύμων σου, ἐν τῇ βασιλείᾳ σου.",
        (),
    )
    (greek,) = variants.lanes(added, ctx.terms)
    assert greek["segments"] == [
        "καὶ εἷς ἐξ εὐωνύμων",
        {"to": " σου"},
        ", ἐν τῇ βασιλείᾳ σου.",
    ]


def test_lanes_mark_the_greek_a_correction_of_the_english_is_about(
    ctx: bible.annotate.Context,
) -> None:
    row = variants.Row(
        "ACT 1:13",
        "ACT 1:13",
        "changed",
        "Ἰάκωβος Ἀλφαίου καὶ Ἰούδας Ἰακώβου.",
        "Ἰάκωβος Ἀλφαίου καὶ Ἰούδας Ἰακώβου.",
        (),
        "James the son of Alpheus, and Judas the brother of James.",
        "James the son of Alpheus, and Judas the son of James.",
        about=("ἰούδας ἰακώβου",),
    )
    greek, english = variants.lanes(row, ctx.terms)
    # Found without case, and without the full stop after it.
    assert greek["segments"] == [
        "Ἰάκωβος Ἀλφαίου καὶ ",
        {"about": "Ἰούδας Ἰακώβου"},
        ".",
    ]
    assert variants.witness(english["segments"], "to") == row.oleb
    # Greek the lane does not hold once stops the build.
    stray = replace(row, about=("Ἰακώβου Ἀλφαίου",))
    with pytest.raises(CheckFailed, match="not once in its lane"):
        variants.lanes(stray, ctx.terms)
    # The Greek is RP2026's, found in the adopted text: a movable ν or a
    # mark the texts print otherwise within it stays a reading, and the
    # words they share about it are set apart.
    nu = variants.Row(
        "MRK 11:17",
        "MRK 11:17",
        "changed",
        "κληθήσεται πᾶσι τοῖς ἔθνεσιν; ὑμεῖς δὲ",
        "κληθήσεται πᾶσιν τοῖς ἔθνεσιν; ὑμεῖς δὲ",
        (),
        "shall be called of all nations; but ye",
        "shall be called for all nations; but ye",
        about=("κληθήσεται πᾶσιν τοῖς ἔθνεσιν",),
    )
    assert variants.lanes(nu, ctx.terms)[0]["segments"] == [
        {"about": "κληθήσεται"},
        " ",
        {"from": "πᾶσι", "to": "πᾶσιν"},
        " ",
        {"about": "τοῖς ἔθνεσιν"},
        "; ὑμεῖς δὲ",
    ]
    # A grave accent is not the acute it stands for, as the decision's Greek
    # was checked; and words two corrections cite are set apart once.
    accents = replace(
        row,
        greek_tr="εἶδεν αὐτὸν καὶ ἐκάλεσεν αὐτόν.",
        greek_rp="εἶδεν αὐτὸν καὶ ἐκάλεσεν αὐτόν.",
        about=("αὐτὸν καὶ", "αὐτὸν"),
    )
    assert variants.lanes(accents, ctx.terms)[0]["segments"] == [
        "εἶδεν ",
        {"about": "αὐτὸν καὶ"},
        " ἐκάλεσεν αὐτόν.",
    ]


def test_lanes_mark_the_words_left_out_between_passages_as_gaps(
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
    row = variants.Row(
        "MAT 1:1", "MAT 1:1", "changed", *texts[:2], (), *texts[2:], passages=selected
    )
    greek, english = variants.lanes(row, ctx.terms)
    assert greek["segments"] == [
        GAP,
        " ",
        {"from": "παλαιόν", "to": "νέον"},
        " ἕν; ",
        GAP,
        " ",
        {"from": "παλαιόν", "to": "νέον"},
        " δύο; ",
        GAP,
    ]
    # An ellipsis in the source wording is not a gap.
    assert variants.witness(english["segments"], "from") == "… old … one; … old two; …"
    assert variants.witness(english["segments"], "to") == "… new … one; … new two; …"


def test_lanes_add_the_apparatus_where_its_accents_differ(
    ctx: bible.annotate.Context,
) -> None:
    def lanes_for(unit: variants.Unit) -> list[variants.Lane]:
        row = variants.Row(
            "MAT 1:1",
            "MAT 1:1",
            "same",
            "πρῶτον; τὸ τέλος.",
            "πρῶτον; τό τέλος.",
            (unit,),
        )
        return variants.lanes(row, ctx.terms)

    # Grave for acute is the same accent.
    assert len(lanes_for(variants.Unit("τὸ", "τό", ("τὸ", "τό"), ("τό", "τὸ")))) == 1
    printed, apparatus = lanes_for(
        variants.Unit("τὸ", "τό", ("τὸ", "τό"), ("τό", "τῷ"))
    )
    assert "apparatus" not in printed
    assert apparatus["apparatus"] is True
    assert (apparatus["from"], apparatus["to"]) == ("TR", "RP26")
    assert apparatus["segments"] == [{"from": "τό", "to": "τῷ"}]
    # The ellipsis an apparatus quotes words apart with is a gap.
    _, apart = lanes_for(
        variants.Unit(
            "τὸ … τὸ", "τό … τό", ("τὸ … τὸ", "τό … τό"), ("τό … τό", "τῷ … τῷ")
        )
    )
    assert apart["segments"] == [
        {"from": "τό", "to": "τῷ"},
        " ",
        {"gap": True},
        " ",
        {"from": "τό", "to": "τῷ"},
    ]


@pytest.mark.parametrize("authored", [False, True])
def test_every_lane_reads_its_witnesses_words_in_order(
    rows: list[variants.Row],
    entries: dict[str, list[variants.Lane]],
    edition: bible.pipeline.Edition,
    authored: bool,
) -> None:
    """Each side of a lane, between its gaps, is its witness's own words in
    order: the English exactly, the Greek but for the case the shared words
    take and the dots and elision marks it displays alike; in the lanes of
    the rows here and in the edition's."""
    listed = (
        list(edition.variants)
        if authored
        else [(row, entries[row.reference]) for row in rows]
    )
    assert listed
    for row, lanes in listed:
        assert lanes[0]["language"] == "grc"
        assert lanes[0]["from"] == ("TR" if row.received else "Scrivener")
        compared = [lane["language"] for lane in lanes if "apparatus" not in lane]
        assert compared == (["grc", "en"] if row.kjv is not None else ["grc"])
        for lane, before, after in (
            (lanes[0], row.greek_tr, row.greek_rp),
            *(((lanes[1], row.kjv, row.oleb),) if row.kjv is not None else ()),
        ):
            # An omitted verse has nothing on the adopted side.
            witnesses: tuple[tuple[Literal["from", "to"], str], ...] = (
                ("from", before or ""),
                ("to", after or ""),
            )
            for key, text in witnesses:
                read = variants.witness(lane["segments"], key)
                if lane["language"] == "grc":
                    read, text = read.lower(), greek_display(text).lower()
                if not row.passages:
                    assert read == text, row.reference
                    continue
                at = 0
                for passage in read.split("…"):
                    found = text.find(passage.strip(), at)
                    assert found >= 0, (row.reference, key, passage)
                    at = found + len(passage.strip())


def test_ellipsis_comparisons_keep_case_at_each_occurrence(
    byzantine: Reconciliation, printed: dict[str, Document]
) -> None:
    ref = "MRK 4:8"
    unit = next(u for u in byzantine.greek.units if u["id"] == ref + "#accent")
    tr = list(byzantine.greek.tr_alignment.text[ref])
    rp = list(byzantine.greek.printed[ref]["accented"])
    for words, plain, span in (
        (tr, byzantine.greek.tr[ref], unit["tr_range"]),
        (rp, byzantine.greek.rp[ref], unit["rp_range"]),
    ):
        first = next(at for at in range(*span) if plain[at] == "en")
        words[first] = words[first].upper() + ";"
    context = replace(
        byzantine,
        greek=replace(
            byzantine.greek,
            tr_alignment=replace(
                byzantine.greek.tr_alignment,
                text={**byzantine.greek.tr_alignment.text, ref: tr},
            ),
            printed={
                **byzantine.greek.printed,
                ref: {**byzantine.greek.printed[ref], "accented": rp},
            },
        ),
    )
    row = next(
        r
        for r in variants.rows(context, byzantine.english.documents, printed)
        if r.reference == ref
    )
    contrast = next(u for u in row.units if u.accented)
    assert contrast.accented == ("ἛΝ; … ἓν … ἓν", "ἘΝ; … ἐν … ἐν")
    assert "ἛΝ" in row.greek_tr and "ἘΝ" in row.greek_rp


def test_preparing_greek_does_not_change_inputs(byzantine: Reconciliation) -> None:
    def inputs() -> tuple[object, ...]:
        return (
            dict(byzantine.greek.tr),
            dict(byzantine.greek.rp),
            dict(byzantine.greek.tr_alignment.text),
            dict(byzantine.greek.printed),
            byzantine.greek.units,
        )

    before = copy.deepcopy(inputs())
    variants.prepare_greek(byzantine)
    assert inputs() == before


def test_variants_lanes_leave_rows_unchanged(
    rows: list[variants.Row], ctx: bible.annotate.Context
) -> None:
    original = copy.deepcopy(rows)
    for row in rows:
        variants.lanes(row, ctx.terms)
    assert rows == original


def test_acts_13_41_keeps_the_word_change_without_dot_changes(
    byzantine: Reconciliation, entries: dict[str, list[variants.Lane]]
) -> None:
    markdown = review.greek_verses(
        byzantine, "ACT 13:41", variants.prepare_greek(byzantine)
    )[0]
    assert "[-ἔργον ᾧ][+ὃ]" in markdown
    assert "[-·]" not in markdown and "[+∙]" not in markdown
    greek, english = entries["ACT 13:41"]
    assert readings(greek) == [("ἔργον ᾧ", "ὃ")]
    assert greek["segments"][:2] == [GAP, " "]
    assert "ὃ οὐ μὴ πιστεύσητε," in variants.witness(greek["segments"], "to")
    assert "ἐν ταῖς ἡμέραις ὑμῶν," not in shown(greek)
    assert readings(english) == [("a work", None)]
    assert english["segments"][:2] == [GAP, " "]
    assert "which you shall in no wise believe," in variants.witness(
        english["segments"], "to"
    )
    assert "for I work" not in shown(english)


@pytest.mark.parametrize("ref", ["REV 22:7", "REV 22:8"])
def test_revelation_corresponding_passages_keep_sentence_changes(
    byzantine: Reconciliation,
    ref: str,
) -> None:
    from bible.byzantine.presentation import passage_spans

    tr, rp, _ = variants.prepare_greek(byzantine)
    verse = verses_of(byzantine.edited.prepared)[ref]
    texts, selected, english = variants.selections(
        byzantine,
        ref,
        ref,
        " ".join(tr[ref]),
        " ".join(rp[ref]),
        scripture.plain(byzantine.english.kjv[ref]),
        scripture.plain(verse.text),
    )
    greek = variants.passage_ranges(byzantine, ref, ref, texts[0], texts[1])
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
    byzantine: Reconciliation,
) -> None:
    ref = "REV 22:7"
    tr, rp, _ = variants.prepare_greek(byzantine)
    verse = verses_of(byzantine.edited.prepared)[ref]
    before, after = scripture.plain(byzantine.english.kjv[ref]), scripture.plain(
        verse.text
    )
    texts, selected, _ = variants.selections(
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
    missing = amended(byzantine, "english", aligned={}, crosswire={})
    with pytest.raises(KeyError):
        variants.selections(
            missing, ref, ref, " ".join(tr[ref]), " ".join(rp[ref]), before, after
        )


def test_shared_selections_retain_every_change_and_corresponding_omission(
    rows: list[variants.Row],
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


def test_a_reading_keeps_the_marks_the_texts_share_outside_it(
    entries: dict[str, list[variants.Lane]],
) -> None:
    # A comma takes the place of the clause the Byzantine text lacks.
    greek = entries["1JN 5:7"][0]
    clause = next(r for r in readings(greek) if r[1] == ",")
    assert clause[0] is not None and clause[0].startswith("ἐν τῷ οὐρανῷ")
    # The stop that closes both texts' sentence is theirs, not the reading's.
    greek = entries["ACT 13:42"][0]
    assert readings(greek) == [("ταῦτα", None)]
    assert greek["segments"][-2:] == [{"from": " ταῦτα"}, "."]


def test_unchanged_english_clips_greek_without_a_bridge(
    byzantine: Reconciliation,
    regularized: dict[str, Document],
    rows: list[variants.Row],
    entries: dict[str, list[variants.Lane]],
) -> None:
    ref = "ACT 13:22"
    row = next(row for row in rows if row.reference == ref)
    assert row.kjv is None and row.oleb is None
    tr, rp, _ = variants.prepare_greek(byzantine)
    before = scripture.plain(scripture.verses(regularized["ACT"])["13:22"].text)
    texts, selected, english = variants.selections(
        amended(byzantine, "english", aligned={}),
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
    assert not any(lane["language"] == "en" for lane in entries[ref])


def test_luke_deletion_has_corresponding_clause_excerpts(
    rows: list[variants.Row], packets: dict[str, str]
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
    byzantine: Reconciliation, ref: str
) -> None:
    context = amended(
        byzantine,
        "verified",
        dispositions=copy.deepcopy(byzantine.verified.dispositions),
    )
    edits = [
        e
        for row in context.verified.dispositions
        for e in row.get("edits", [])
        if e["ref"] == ref
    ]
    assert edits
    for edit in edits:
        edit["note_scope"].pop("source_range", None)
        edit.pop("applied_range", None)
    tr, rp, _ = variants.prepare_greek(context)
    verse = verses_of(context.edited.prepared)[ref]
    args = (
        ref,
        ref,
        " ".join(tr[ref]),
        " ".join(rp[ref]),
        scripture.plain(context.english.kjv[ref]),
        scripture.plain(verse.text),
    )
    if ref == "LUK 17:4":
        # An insertion or omission without the executor's range is an error.
        with pytest.raises(KeyError, match="applied_range"):
            variants.selections(context, *args)
        return
    texts, selected, _ = variants.selections(context, *args)
    assert selected == (tuple((0, len(t)) for t in texts),)


@pytest.mark.parametrize("kind", ["insert", "delete"])
def test_english_construction_ranges_are_derived_locally(
    byzantine: Reconciliation, kind: str
) -> None:
    tr, rp, _ = variants.prepare_greek(byzantine)
    verses = verses_of(byzantine.edited.prepared)
    edit = next(
        e
        for row in byzantine.verified.dispositions
        for e in row.get("edits", [])
        if e["kind"] == kind
        and e.get("note_scope", {}).get("range")
        and e["ref"] in byzantine.english.aligned
    )
    ref = edit["ref"]
    dispositions = copy.deepcopy(list(byzantine.verified.dispositions))
    for row in dispositions:
        for e in row.get("edits", []):
            if e["ref"] == ref and e["kind"] == kind:
                e["note_scope"].pop("source_range", None)
    context = amended(byzantine, "verified", dispositions=tuple(dispositions))
    snapshot = copy.deepcopy(dispositions)
    texts, selected, english = variants.selections(
        context,
        ref,
        ref,
        " ".join(tr[ref]),
        " ".join(rp[ref]),
        scripture.plain(byzantine.english.kjv[ref]),
        scripture.plain(verses[ref].text),
    )
    assert english
    assert list(context.verified.dispositions) == snapshot
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
    byzantine: Reconciliation,
    ref: str,
    target: str,
) -> None:
    tr, rp, _ = variants.prepare_greek(byzantine)
    texts, selected, english = variants.selections(
        byzantine,
        ref,
        target,
        " ".join(tr[ref]),
        " ".join(rp[target]),
        scripture.plain(byzantine.english.kjv[ref]),
        scripture.plain(verses_of(byzantine.edited.prepared)[target].text),
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
    context = amended(
        byzantine,
        "verified",
        dispositions=tuple(
            row
            for row in byzantine.verified.dispositions
            if not (row["ref"] == ref and row["disposition"] == "structural")
        ),
    )
    _, fallback, _ = variants.selections(
        context, ref, target, texts[0], texts[1], texts[2], texts[3]
    )
    assert fallback == (tuple((0, len(t)) for t in texts),)


@pytest.mark.parametrize("inside", [False, True])
def test_partial_tags_require_only_selected_coverage(
    byzantine: Reconciliation, inside: bool
) -> None:
    ref, target = "MAT 23:14", "MAT 23:13"
    tags = copy.deepcopy(dict(byzantine.english.crosswire))
    link = tags[ref]["links"][0 if inside else -1]
    link["forms"] = ["wrong"] * len(link["forms"])
    context = amended(byzantine, "english", aligned={}, crosswire=tags)
    tr, rp, _ = variants.prepare_greek(context)
    texts, selected, _ = variants.selections(
        context,
        ref,
        target,
        " ".join(tr[ref]),
        " ".join(rp[target]),
        scripture.plain(context.english.kjv[ref]),
        scripture.plain(verses_of(context.edited.prepared)[target].text),
    )
    whole = (tuple((0, len(t)) for t in texts),)
    assert (selected == whole) == inside


def test_crossing_bridge_cannot_clip_a_moved_passage(byzantine: Reconciliation) -> None:
    ref, target = "MAT 23:13", "MAT 23:14"
    aligned = copy.deepcopy(dict(byzantine.english.aligned))
    aligned[ref]["positions"][0].append(len(byzantine.greek.tr[ref]) - 1)
    context = amended(byzantine, "english", aligned=aligned)
    tr, rp, _ = variants.prepare_greek(context)
    texts, selected, _ = variants.selections(
        context,
        ref,
        target,
        " ".join(tr[ref]),
        " ".join(rp[target]),
        scripture.plain(context.english.kjv[ref]),
        scripture.plain(verses_of(context.edited.prepared)[target].text),
    )
    assert selected == (tuple((0, len(t)) for t in texts),)


def test_matthew_moved_comparison_prints_matching_ellipses(
    entries: dict[str, list[variants.Lane]], packets: dict[str, str]
) -> None:
    greek, english = entries["MAT 23:13"]
    assert variants.witness(greek["segments"], "to").startswith("Οὐαὶ δὲ ὑμῖν, …")
    assert readings(english)[0] == ("Woe", "But woe")
    assert variants.witness(english["segments"], "to").startswith("But woe unto you, …")
    section = section_of(packets, "MAT 23:14#1")
    assert "` Οὐαὶ [+δὲ ]ὑμῖν, … `" in section
    assert "` [-Woe][+But woe] unto you, … `" in section


@pytest.mark.parametrize("side", ["greek", "english"])
@pytest.mark.parametrize("boundary", [False, True])
def test_variants_missing_correspondence_must_be_bounded_in_both_languages(
    byzantine: Reconciliation, side: str, boundary: bool
) -> None:
    from bible.byzantine.crosswire import presentation_bridge

    ref = "ACT 13:41"
    tr, rp, _ = variants.prepare_greek(byzantine)
    before = scripture.plain(byzantine.english.kjv[ref])
    after = scripture.plain(verses_of(byzantine.edited.prepared)[ref].text)
    aligned = copy.deepcopy(dict(byzantine.english.aligned))
    aligned[ref] = presentation_bridge(
        byzantine.english.crosswire[ref],
        byzantine.greek.tr[ref],
        byzantine.english.kjv[ref],
    )
    bridge = aligned[ref]
    if side == "greek":
        position = byzantine.greek.tr[ref].index("pisteushte" if boundary else "ou")
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
    context = amended(byzantine, "english", aligned=aligned)
    texts, selected, _ = variants.selections(
        context, ref, ref, " ".join(tr[ref]), " ".join(rp[ref]), before, after
    )
    assert (selected == (tuple((0, len(t)) for t in texts),)) == boundary
    if not boundary:
        assert texts[0][slice(*selected[0][0])].startswith("ἔργον ᾧ")
        assert texts[2][slice(*selected[0][2])].startswith("a work which")


@pytest.mark.parametrize("bad", ["form", "position", "length", "conflict"])
def test_variants_invalid_interior_tags_keep_complete_verse(
    byzantine: Reconciliation, bad: str
) -> None:
    ref = "ACT 13:41"
    tags = copy.deepcopy(dict(byzantine.english.crosswire))
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
    context = amended(byzantine, "english", aligned={}, crosswire=tags)
    tr, rp, _ = variants.prepare_greek(context)
    texts, selected, _ = variants.selections(
        context,
        ref,
        ref,
        " ".join(tr[ref]),
        " ".join(rp[ref]),
        scripture.plain(byzantine.english.kjv[ref]),
        scripture.plain(verses_of(byzantine.edited.prepared)[ref].text),
    )
    assert selected == (tuple((0, len(t)) for t in texts),)


def test_corrections_of_shared_greek_have_english_comparisons(
    rows: list[variants.Row],
) -> None:
    for ref in ("LUK 23:42", "LUK 23:15", "3JN 1:2"):
        row = next(r for r in rows if r.source == ref)
        assert row.kjv and row.oleb and row.kjv != row.oleb


def test_a_real_correction_beside_a_variant_keeps_english(
    byzantine: Reconciliation,
) -> None:
    inputs = (
        dict(byzantine.english.documents),
        dict(byzantine.edited.prepared),
        byzantine.verified.dispositions,
    )
    original = copy.deepcopy(inputs)
    found = variants.rows(
        byzantine, byzantine.english.documents, byzantine.edited.prepared
    )
    row = next(r for r in found if r.source == "2JN 1:3")
    assert row.units and row.kjv and row.oleb
    assert "Grace be with you" in row.kjv
    assert "Grace shall be with us" in row.oleb
    assert row.kjv.replace("be with you", "shall be with us") == row.oleb
    assert inputs == original


@pytest.fixture(scope="module")
def unpunctuated_rows(byzantine: Reconciliation) -> dict[str, variants.Row]:
    """The variants' rows from the books before the punctuation pass, by
    source verse."""
    return {
        row.source: row
        for row in variants.rows(
            byzantine, byzantine.english.documents, byzantine.edited.prepared
        )
    }


def test_john_first_cast_retains_the_king_james_wording(
    byzantine: Reconciliation,
    index: review.Index,
    unpunctuated_rows: dict[str, variants.Row],
) -> None:
    ref = "JHN 8:7"
    verse = index["prepared"][ref]
    assert "let him first cast a stone at her" in verse.text
    assert scripture.plain(verse.text) == byzantine.english.kjv[ref]
    row = index["rows"][f"{ref}#1"]
    assert row["disposition"] == "override"
    assert row["kind"] == row["action"] == "nochange"
    assert not any(n.get("x-key", "").endswith(" TR") for _, n in verse.notes)
    listed = unpunctuated_rows[ref]
    assert listed.kind == "same"
    assert listed.kjv is None and listed.oleb is None


def test_every_shared_greek_correction_is_kept_whole_in_the_variants(
    byzantine: Reconciliation, unpunctuated_rows: dict[str, variants.Row]
) -> None:
    found = unpunctuated_rows
    for disposition in byzantine.verified.dispositions:
        if disposition["disposition"] != "shared":
            continue
        for edit in disposition["edits"]:
            row = found[edit["ref"]]
            assert row.kjv and row.oleb
            texts = (row.greek_tr, row.greek_rp, row.kjv, row.oleb)
            assert row.passages == (tuple((0, len(t)) for t in texts),)


@pytest.mark.parametrize("ref", ["LUK 17:18", "2CO 12:2", "JAS 4:5", "JHN 20:29"])
def test_punctuation_revisions_preserve_wording_comparisons(
    unpunctuated_rows: dict[str, variants.Row], ref: str
) -> None:
    # The variants consume wording before the separate punctuation pass.
    row = unpunctuated_rows[ref]
    assert row.kjv and row.oleb and row.kjv != row.oleb


@pytest.mark.parametrize("ref", ["2JN 1:3", "EPH 4:32"])
def test_review_separates_corrections_from_variants(
    byzantine: Reconciliation, packets: dict[str, str], index: review.Index, ref: str
) -> None:
    assert index["corrected"][ref].text != byzantine.english.kjv[ref]
    packet = packets[f"{ref.split()[0]}.md"]
    correction = packet[packet.index(f"### {ref}\n") :].split("\n### ", 1)[0]
    assert f"KJV {ref} → Corrected KJV {ref}" in correction
    assert f"KJV {ref} → OLEB {ref} (all changes)" in correction
    for unit in byzantine.greek.units:
        if unit["ref"] != ref:
            continue
        row = index["rows"][unit["id"]]
        if row["disposition"] == "neutral":
            continue
        section = section_of(packets, unit["id"])
        assert f"Corrected KJV {ref} → OLEB {ref}" in section
        assert f"KJV {ref} → OLEB {ref} (all changes)" in section
        passages = review.unit_passages(
            unit,
            byzantine,
            variants.prepare_greek(byzantine),
            index["prepared"],
            index["corrected"],
        )
        assert passages[0][2] == scripture.plain(index["corrected"][ref].text)


def test_review_baseline_preserves_source_documents_and_decisions(
    byzantine: Reconciliation, finished: dict[str, Document]
) -> None:
    inputs = (
        dict(byzantine.english.documents),
        byzantine.verified.dispositions,
        byzantine.decisions.overrides,
    )
    original = copy.deepcopy(inputs)
    review.build_index(byzantine, finished)
    assert inputs == original


@pytest.mark.parametrize(
    "ref, old, new",
    [
        ("MRK 7:3", "oft", "with the fist"),
        ("MRK 14:69", "a maid", "the maid"),
        ("JHN 10:16", "one fold", "one flock"),
        ("ACT 10:20", "arise therefore", "but arise"),
        ("ROM 4:24", "if we", "who"),
        ("1TH 2:16", "for the wrath", "but the wrath"),
        ("2TI 1:18", "unto me ", ""),
        ("1PE 2:13", "Submit yourselves", "Submit yourselves therefore"),
    ],
)
def test_eight_shared_greek_corrections(
    byzantine: Reconciliation, index: review.Index, ref: str, old: str, new: str
) -> None:
    before = byzantine.english.kjv[ref]
    after = index["corrected"][ref]
    assert scripture.plain(after.text) == before.replace(old, new)
    correction = index["rows"][ref]
    assert correction["disposition"] == "shared"
    assert correction["execution"] == "applied"
    assert not correction.get("note")
    if ref == "JHN 10:16":
        assert "this fold" in after.text


def test_excluded_recommendations_are_visible(
    byzantine: Reconciliation, packets: dict[str, str], index: review.Index
) -> None:
    excluded = [
        i
        for i in byzantine.decisions.instructions
        if i["scope"] == "out-of-scope" and i["role"] != "agrees"
    ]
    assert excluded
    for i in excluded:
        for ref in i["refs"]:
            line = review.instruction_line(i, byzantine)
            assert line in packets[f"{ref.split()[0]}.md"]
            assert line in index["loose_in_verse"][ref]
            assert f"bound {i['bind']}" in line
            assert review.esc(i["compatibility_reason"]) in line
            strength = i.get("strength")
            if strength:
                assert strength in line
    for ref in (
        "MRK 7:3",
        "MRK 14:69",
        "JHN 10:16",
        "ACT 10:20",
        "ROM 4:24",
        "1TH 2:16",
        "2TI 1:18",
        "1PE 2:13",
    ):
        recommendation = next(i for i in excluded if i["refs"] == [ref])
        assert review.addressed(recommendation, byzantine)


def test_summary_lists_unaddressed_exclusions(byzantine: Reconciliation) -> None:
    text = review.summary(byzantine).split("## Unaddressed recommendations", 1)[1]
    text = text.split("## Invariants", 1)[0]
    excluded = [
        i
        for i in byzantine.decisions.instructions
        if i["scope"] == "out-of-scope"
        and i["role"] != "agrees"
        and i["compatibility"] != "agrees"
    ]
    addressed = [i for i in excluded if review.addressed(i, byzantine)]
    unaddressed = [i for i in excluded if not review.addressed(i, byzantine)]
    assert addressed and unaddressed
    for i in unaddressed:
        assert review.instruction_line(i, byzantine)[2:] in text
    for i in addressed:
        assert review.instruction_line(i, byzantine)[2:] not in text


def test_english_comparison_keeps_hyphenated_compounds_whole() -> None:
    before = "if they have found any evil-doing in me"
    after = "what evil-doing they have found in me"
    spans = diff_spans(before, after)
    assert spans == [
        ("delete", "if"),
        ("insert", "what evil-doing"),
        ("equal", " they have found "),
        ("delete", "any evil-doing "),
        ("equal", "in me"),
    ]
    for source, absent in ((before, "insert"), (after, "delete")):
        assert "".join(value for kind, value in spans if kind != absent) == source
