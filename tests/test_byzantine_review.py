"""The review of the reconciliation, one file for each book with every
non-neutral unit once, markdown safe; and the appendix of readings."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping

import pytest

import bible.annotate
import bible.pipeline
from bible import scripture, usj
from bible.byzantine import BOOKS, BOYD_ASV, REVISIONS, appendix, review
from bible.byzantine.decisions import ref_key
from bible.byzantine.greek import ascii_greek, greek_words
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
def test_full_greek_preserves_both_pinned_verses(
    byzantine: Context, ref: str, target: str
) -> None:
    assert_greek_preserved(byzantine, ref, target)


def assert_greek_preserved(byzantine: Context, ref: str, target: str) -> None:
    lines = review.greek_verses(byzantine, ref, target)
    diff = lines[0].split(": ", 1)[1]
    before = re.sub(r"⟦\+[^⟧]*⟧", "", diff)
    before = re.sub(r"⟦−([^⟧]*)⟧", r"\1", before)
    after = re.sub(r"⟦−[^⟧]*⟧", "", diff)
    after = re.sub(r"⟦\+([^⟧]*)⟧", r"\1", after)
    assert greek_words(before) == byzantine["tr"][ref]
    assert greek_words(after) == byzantine["rp"].get(target, [])


def test_greek_comparison_marks_difference_and_keeps_context(
    byzantine: Context, packets: dict[str, str]
) -> None:
    lines = review.greek_verses(byzantine, "MAT 3:8")
    assert "⟦−καρπους αξιους⟧⟦+καρπον αξιον⟧" in lines[0]
    section = section_of(packets, "MAT 3:8#1")
    for line in lines:
        assert line in section
    assert "⟦−fruits⟧⟦+fruit⟧" in section
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
    spans = review.diff_spans(before, after)
    assert "".join(text for kind, text in spans if kind != "insert") == before
    assert "".join(text for kind, text in spans if kind != "delete") == after


def test_readable_diff_marks_words_punctuation_and_absence() -> None:
    assert review.marked_readings("fruits", "fruit") == ("**fruits**", "**fruit**")
    assert review.marked_readings("Go.", "go!") == ("**Go.**", "**go!**")
    assert review.marked_readings("same", "same") == ("same", "same")
    assert review.marked_readings("", "added") == ("∅", "**added**")
    assert review.marked_readings("omitted", "") == ("**omitted**", "∅")


def test_repeated_words_do_not_hide_the_minimal_omission() -> None:
    spans = review.diff_spans("holy " * 210, "holy " * 209)
    assert "".join(text for kind, text in spans if kind == "delete") == "holy "
    assert not any(kind == "insert" for kind, _ in spans)


def test_phrase_replacements_are_not_arbitrary_word_pairs() -> None:
    assert "⟦−have seen⟧⟦+see ye⟧" in review.inline_diff("have seen", "see ye")
    assert "⟦−we will⟧⟦+let us⟧ go" in review.inline_diff("we will go", "let us go")


def test_james_keeps_contextual_diff_and_compact_witnesses(
    byzantine: Context, packets: dict[str, str], index: review.Index
) -> None:
    text = packets["JAS.md"]
    assert "⟦−have seen⟧⟦+see ye⟧" in text
    assert "⟦−υπο κρισιν⟧⟦+εις υποκρισιν⟧" in text
    assert "⟦−μοιχευσης⟧⟦+μοιχευσεις⟧" in text
    section = section_of(packets, "JAS 2:11#2")
    assert "OLEB JAS 2:11 (whole verse):" in section
    assert "Thou shalt" in section
    assert (
        "Greek at this unit · TR → RP2026: ` … μοιχευσης ειπεν και μη ⟦−φονευσης⟧⟦+φονευσεις⟧ ει δε ου μοιχευσεις … `"
        in section
    )
    assert "English for shared construction (executed with JAS 2:11#1)" in section
    assert "Textus Receptus" in section
    assert "### " not in section
    assert len(text.splitlines()) < 900
    assert (
        "at unit: ` … commit adultery, said also, ⟦−Do⟧⟦+Thou shalt⟧ not kill. Now if … ` (includes Boyd revision)"
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
        spans = review.diff_spans(before, after)
        assert "".join(text for kind, text in spans if kind != "insert") == before
        assert "".join(text for kind, text in spans if kind != "delete") == after


def test_greek_diff_ignores_accents(byzantine: Context) -> None:
    lines = review.greek_verses(byzantine, "PHP 3:5")
    assert "⟦" not in lines[0]
    assert "περιτομη" in lines[0]
    assert "περιτομή" not in lines[0]


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
    lines = review.greek_verses(byzantine, "PHM 1:17")
    assert "` ει ουν ⟦−εμε⟧⟦+με⟧ εχεις κοινωνον προσλαβου αυτον ως εμε `" in lines[0]
    text = packets["JAS.md"]
    assert text.count("Greek whole verse · TR JAS 2:11 → RP2026 JAS 2:11: `") == 1
    assert (
        "Greek whole verse · TR JAS 2:11 → RP2026 JAS 2:11: see JAS 2:11#1"
        in section_of(packets, "JAS 2:11#2")
    )


def test_english_diff_keeps_whole_words() -> None:
    assert "⟦−thy⟧⟦+the⟧" in review.inline_diff("thy right cheek", "the right cheek")


def test_witness_diff_shows_shared_context_once() -> None:
    assert review.inline_change("condemned", "judged") == "` ⟦−condemned⟧⟦+judged⟧ `"
    contrast = review.inline_change("shall be condemned", "shall be judged")
    assert contrast == "` shall be ⟦−condemned⟧⟦+judged⟧ `"


def test_witness_excerpt_clips_context_without_changing_neighboring_words() -> None:
    text = "One two three four five six old seven eight nine ten eleven twelve."
    assert review.witness_excerpt("old", "new", text) == (
        "source context: ` … three four five six ⟦−old⟧⟦+new⟧ seven eight nine ten … `"
    )
    assert review.witness_excerpt("old", "new", "old is here.") == (
        "source context: ` ⟦−old⟧⟦+new⟧ is here. `"
    )


def test_witness_excerpt_abstains_on_absent_or_ambiguous_phrases() -> None:
    for text in (None, "old and old", "older wording"):
        assert (
            review.witness_excerpt("old", "new", text)
            == "quoted contrast: ` ⟦−old⟧⟦+new⟧ `"
        )
    assert review.witness_excerpt("old", "new", "old and old", bounds=(8, 11)) == (
        "source context: ` old and ⟦−old⟧⟦+new⟧ `"
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
        "source context: ` one⟦+ new⟧, two `"
    )
    assert review.witness_excerpt("", "new", "one, two").startswith("quoted contrast: ")


def test_boyd_passage_markup_is_compared_as_plain_wording() -> None:
    passage = "his brother&#x27;s <i>wife</i>"
    assert review.source_plain(passage) == "his brother's wife"
    assert review.witness_excerpt(
        "", "brother's", review.source_plain(passage), reading="new"
    ) == ("source context: ` his ⟦+brother's⟧ wife `")


def test_james_witness_excerpts_use_each_sources_own_context(
    byzantine: Context, index: review.Index
) -> None:
    lines = review.witness_lines(unit_of(byzantine, "JAS 4:15#1"), byzantine, index)
    tcent = next(line for line in lines if line.startswith("- TCENT 290"))
    assert (
        "source context: ` … If the Lord wills, ⟦−we will⟧⟦+let us⟧ live and do this … `"
        in tcent
    )
    # A source annotation is never located in the verse; it stays in the quote.
    verse = "If the Lord wills, we will live and do this or that."
    assert review.witness_excerpt("we will (twice)", "let us", verse) == (
        "quoted contrast: ` ⟦−we will (twice)⟧⟦+let us⟧ `"
    )


def test_instruction_witness_lines_show_the_proposal_in_kjv_context(
    byzantine: Context, index: review.Index
) -> None:
    lines = review.witness_lines(unit_of(byzantine, "JAS 2:18#1"), byzantine, index)
    pierpont = next(line for line in lines if line.startswith("- Pierpont 565:"))
    assert "KJV context (proposal): ` … shew me thy faith ⟦−without⟧" in pierpont
    assert "blocked (override JAS 2:18#1 takes this construction)" in pierpont


def test_unit_greek_context_keeps_neighboring_units_out_of_the_diff(
    byzantine: Context,
) -> None:
    excerpt = review.unit_greek_excerpt(unit_of(byzantine, "JAS 2:11#1"), byzantine)
    assert (
        excerpt
        == "` ο γαρ ειπων μη ⟦−μοιχευσης⟧⟦+μοιχευσεις⟧ ειπεν και μη φονευσης … `"
    )
    omitted = unit_of(byzantine, "JAS 1:13#1")
    assert "⟦−του ⟧" in review.unit_greek_excerpt(omitted, byzantine)


def test_every_greek_diff_preserves_both_pinned_verses(byzantine: Context) -> None:
    for ref, target in {(u["ref"], u["target_ref"]) for u in byzantine["units"]}:
        assert_greek_preserved(byzantine, ref, target)


def test_unit_english_comparison_is_separate_from_whole_verse(
    packets: dict[str, str],
) -> None:
    section = section_of(packets, "JAS 4:13#2")
    label = "English for shared construction (executed with JAS 4:13#1) · KJV JAS 4:13 → OLEB JAS 4:13:"
    assert (
        label
        + " ` … now, ye that say, To day ⟦−or⟧⟦+and⟧ to morrow ⟦−we will⟧⟦+let us⟧ go into such a city, … `"
        in section
    )
    assert (
        section.index("Greek at this unit")
        < section.index(label)
        < section.index("Greek whole verse")
    )
    assert "and get gain" not in section.split("Greek whole verse", 1)[0]
    section = section_of(packets, "JAS 1:13#1")
    assert "English at this unit · KJV JAS 1:13 → OLEB JAS 1:13: unchanged" in section


def test_short_form_unit_english_keeps_its_kjv_context(
    packets: dict[str, str],
) -> None:
    # A short-form omission note has no source range; the executed edit's own
    # character range still locates the four words either side.
    assert (
        "English at this unit · KJV COL 1:14 → OLEB COL 1:14: ` … whom we have redemption ⟦−through his blood⟧, even the forgiveness of … `"
        in section_of(packets, "COL 1:14#1")
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
        review.diff_spans(
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
    assert review.revision_excerpt(row, "one, two") == "` one⟦+ new⟧, two `"
    row["side"] = "before"
    assert review.revision_excerpt(row, "one, two") == "` one, ⟦+new ⟧two `"


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

LABELS = {"tr": "TR", "rp": "RP", "kjv": "KJV", "oleb": "OLEB", "omits": "omits"}
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


def test_a_changed_verse_has_four_lines(
    rows: list[appendix.Row], entries: dict[str, list[Node]]
) -> None:
    changed = [row for row in rows if row.kind == "changed"]
    assert len(changed) > 700
    for row in changed:
        heading, *lines = entries[row.reference]
        assert heading["marker"] == "im"
        assert [line["marker"] for line in lines] == ["ili1"] * 4, row.reference
        assert [text_of(line).split(" ", 1)[0] for line in lines] == [
            "TR",
            "RP",
            "KJV",
            "OLEB",
        ]
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
    # The English is plain: no notes, no lemmas marked.
    assert "**" not in "".join(text_of(b) for b in entries["MAT 22:7"])
    assert not usj.notes_of(entries["MAT 22:7"])


def test_a_verse_whose_english_stands_has_one_line(
    rows: list[appendix.Row], entries: dict[str, list[Node]]
) -> None:
    same = [row for row in rows if row.kind == "same"]
    assert same
    for row in same:
        assert row.units and row.kjv is None and row.oleb is None, row.reference
        (line,) = entries[row.reference]
        assert line["marker"] == "im"
        assert text_of(line).startswith(row.reference.split()[1] + " TR ")
    accents = [unit for row in same for unit in row.units if unit.accented]
    assert accents


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
        assert lines[1] == "RP omits the verse"
        assert lines[3] == "OLEB omits the verse"


def test_a_moved_verse_is_labelled_with_the_king_james_number(
    byzantine: Context, rows: list[appendix.Row], entries: dict[str, list[Node]]
) -> None:
    moved = {row.reference: row for row in rows if row.source != row.reference}
    expected = {
        target: origin for origin, target in byzantine["structure"].moved.items()
    }
    assert {ref: row.source for ref, row in moved.items()} == expected
    for ref, row in moved.items():
        assert row.kind == "changed"
        assert ascii_greek(row.greek_tr) == " ".join(byzantine["tr"][row.source])
        heading = text_of(entries[ref][0])
        assert heading == (f"{ref.split()[1]} (KJV {row.source.split()[1]})"), heading


def test_all_appendix_passages_keep_the_unaccented_words(
    byzantine: Context, rows: list[appendix.Row]
) -> None:
    for row in rows:
        assert ascii_greek(row.greek_tr) == " ".join(
            byzantine["tr"][row.source]
        ), row.source
        assert ascii_greek(row.greek_rp) == " ".join(
            byzantine["rp"].get(row.reference, [])
        ), row.reference
        units = [
            u
            for u in byzantine["units"]
            if u["target_ref"] == row.reference
            and u["class"] not in ("structural", "accent")
        ]
        accents = [
            u
            for u in byzantine["units"]
            if u["target_ref"] == row.reference and u["class"] == "accent"
        ]
        for printed, unit in zip(row.units, units + accents, strict=True):
            assert ascii_greek(printed.tr) == " ".join(unit["tr"]), unit["id"]
            assert ascii_greek(printed.rp) == " ".join(unit["rp"]), unit["id"]
            if printed.accented:
                assert printed.accented == (unit["tr_accented"], unit["rp_accented"])
    assert any(not u.tr for row in rows for u in row.units)
    assert any(not u.rp for row in rows for u in row.units)
