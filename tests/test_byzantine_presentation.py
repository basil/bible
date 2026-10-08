"""Phrase selection retains source text and all lossless differences."""

from pathlib import Path

import pytest

from bible import usj
from bible.byzantine import appendix
from bible.byzantine.presentation import (
    anchored,
    clipped,
    diff_spans,
    greek_display,
    marked,
    phrases,
)


@pytest.mark.parametrize("stop", [",", ":", ";", ".", "?", "!", "·", "·", "∙", "—"])
def test_phrase_boundaries_keep_closing_quotes(stop: str) -> None:
    text = f"One{stop}” Two{stop}"
    assert [text[a:b] for a, b in phrases(text)] == [f"One{stop}” ", f"Two{stop}"]


def test_apostrophes_and_hyphens_do_not_clip() -> None:
    assert marked(
        clipped(diff_spans("man's well-being here", "man's well-being there"))
    ) == ("man's well-being [-here][+there]")


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        (
            "First; old words, last.",
            "First; new words, last.",
            "… [-old][+new] words, …",
        ),
        ("old; middle; old.", "new; middle; new.", "[-old][+new]; … [-old][+new]."),
        ("old, old; last.", "new, new; last.", "[-old][+new], [-old][+new]; …"),
        ("First; word, last.", "First; word: last.", "… word[-,][+:] …"),
        ("First; last.", "First; new last.", "… [+new ]last."),
        ("First; old last.", "First; last.", "… [-old ]last."),
        ("old words.", "", "[-old words.]"),
        ("Same words.", "Same words.", "Same words."),
    ],
)
def test_clipped_comparisons(before: str, after: str, expected: str) -> None:
    assert marked(clipped(diff_spans(before, after))) == expected


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("a; b; c.", "a; new b; c."),
        ("a, b.", "a new, b."),
        ("a; b.", "a; b. new"),
        ("a; b.", "a new; b."),
        ("a; b.", "a b."),
        ("a b.", "a; b."),
        ("a; “old!” c.", "a; “new?” c."),
    ],
)
def test_clipping_keeps_every_change_and_reconstructs_retained_passages(
    before: str, after: str
) -> None:
    spans = diff_spans(before, after)
    retained = clipped(spans)
    for kind in ("delete", "insert"):
        assert "".join(v for k, v in retained if k == kind) == "".join(
            v for k, v in spans if k == kind
        )
    for text, absent in ((before, "insert"), (after, "delete")):
        reconstructed = "".join(v for k, v in retained if k != absent)
        at = 0
        for passage in reconstructed.split("…"):
            if passage.strip():
                at = text.index(passage.strip(), at) + len(passage.strip())


def test_ledger_anchors_keep_repeated_words_in_their_units() -> None:
    spans = anchored("a a; b.", "a; a b.", [(2, 4, 0, 0), (5, 5, 3, 5)])
    assert "".join(v for k, v in spans if k != "insert") == "a a; b."
    assert "".join(v for k, v in spans if k != "delete") == "a; a b."
    assert any(k == "delete" and "a" in v for k, v in spans)
    assert any(k == "insert" and "a" in v for k, v in spans)


@pytest.mark.parametrize("greek", [False, True])
@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("you. Amen.", "you.", "you.[- Amen.]"),
        ("you.” Amen.”", "you.”", "you.”[- Amen.”]"),
        ("you. Amen!", "you.", "you[-. Amen][-!][+.]"),
        ("you Amen next", "you next", "you[- Amen] next"),
        ("you Amenxx", "youxx", "you[- Amen]xx"),
    ],
)
def test_anchors_own_only_identical_closing_marks(
    left: str, right: str, expected: str, greek: bool
) -> None:
    ranges = [(0, left.index("Amen") + len("Amen"), 0, len("you"))]
    original = list(ranges)
    spans = anchored(left, right, ranges, greek=greek)
    assert marked(spans) == expected
    assert "".join(v for k, v in spans if k != "insert") == left
    assert "".join(v for k, v in spans if k != "delete") == right
    assert ranges == original


@pytest.mark.parametrize("quote", ['"', "'", "”", "’", "»", ")", "]", "}"])
def test_anchors_own_matching_closing_quotes(quote: str) -> None:
    left, right = f"you{quote} Amen{quote}", f"you{quote}"
    spans = anchored(left, right, [(0, left.index("Amen") + 4, 0, 3)])
    assert spans == [("equal", right), ("delete", f" Amen{quote}")]
    assert "".join(v for k, v in spans if k != "insert") == left
    assert "".join(v for k, v in spans if k != "delete") == right


def test_extended_anchors_merge_with_adjacent_punctuation_losslessly() -> None:
    left, right = "you. Amen.", "you."
    spans = anchored(left, right, [(0, 9, 0, 3), (9, 10, 3, 4)])
    assert spans == [("equal", "you."), ("delete", " Amen.")]
    assert "".join(v for k, v in spans if k != "insert") == left
    assert "".join(v for k, v in spans if k != "delete") == right


@pytest.mark.parametrize("greek", [False, True])
def test_closing_mark_cannot_split_an_omitted_passage(greek: bool) -> None:
    left, right = "bear record in heaven, the Father.", "bear record,"
    spans = diff_spans(left, right, greek=greek)
    assert spans == [
        ("equal", "bear record"),
        ("insert", ","),
        ("delete", " in heaven, the Father."),
    ]
    assert "".join(v for k, v in spans if k != "insert") == left
    assert "".join(v for k, v in spans if k != "delete") == right
    assert usj.text_of(appendix.comparison(spans, is_greek=greek)) == (
        "bear record, [in heaven, the Father.]"
    )


@pytest.mark.parametrize("quote", ['"', "'", "”", "’", "»", ")", "]", "}"])
def test_closing_quotes_stay_with_the_phrase(quote: str) -> None:
    text = f"old!{quote} next."
    assert [text[a:b] for a, b in phrases(text)] == [f"old!{quote} ", "next."]


def test_overlapping_source_projections_merge_losslessly() -> None:
    # Two ledger tokens share one complete word in the transcription.
    left, right = "Διατί; καί", "διὰ τί; καί"
    spans = anchored(left, right, [(0, 7, 0, 4), (0, 7, 4, 8)])
    assert "".join(v for k, v in spans if k != "insert") == left
    assert "".join(v for k, v in spans if k != "delete") == right
    assert spans == anchored(left, right, [(0, 7, 0, 8)])


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        (
            "She bought a red car.",
            "She bought a blue car.",
            [
                "She bought a ",
                "[",
                "red",
                "]",
                " ",
                usj.char("it", "blue"),
                " car.",
            ],
        ),
        ("word", "new word", [usj.char("it", "new"), " word"]),
        ("old words.", "", ["[", "old words.", "]"]),
        (
            "word,",
            "word:",
            ["word", "[", ",", "]", usj.char("it", ":")],
        ),
        ("Same words.", "Same words.", ["Same words."]),
    ],
)
def test_pdf_english_comparison_styles(
    before: str, after: str, expected: list[usj.Node | str]
) -> None:
    assert appendix.comparison(diff_spans(before, after)) == expected


def test_pdf_unchanged_greek_stays_upright() -> None:
    assert appendix.comparison(diff_spans("καί∙", "καί∙"), is_greek=True) == [
        usj.char("wg", "καί·"),
    ]


def test_greek_bold_export_keeps_punctuation_in_the_greek_font(tmp_path: Path) -> None:
    import usfmtc
    from ptxprint.usxutils import PTXEmitter

    content = appendix.comparison(
        [("delete", "καί,"), ("insert", "καί∙")], is_greek=True
    )
    assert content == [
        "[",
        usj.char("wg", "καί,"),
        "]",
        " ",
        usj.char("bd", usj.char("wg", "καί·")),
    ]
    written = usj.serialize(content)
    assert written == "[\\wg καί,\\wg*] \\bd \\+wg καί·\\+wg*\\bd*"
    document = "\\id XXC\n\\ip " + written + "\n"
    parsed = usj.parse(document)
    assert parsed["content"][1]["content"] == [
        "[",
        usj.char("wg", "καί,"),
        "] ",
        usj.char("bd", usj.char("wg", "καί·")),
    ]
    path = tmp_path / "XXC.usfm"
    path.write_text(document)
    upstream = usfmtc.readFile(str(path))
    theirs = upstream.outUsj(None)
    bold = next(
        node for node in usj.walk(theirs["content"]) if node.get("marker") == "bd"
    )
    assert bold["content"] == [usj.char("wg", "καί·")]
    # PTXprint reads and writes peripheral books before TeX sees them.
    for emitter in (None, PTXEmitter):
        options = {"emitter": emitter} if emitter else {}
        processed = upstream.outUsfm(None, **options)
        assert "\\bd \\+wg καί·\\+wg*\\bd*" in processed
        assert usj.parse(processed) == parsed


@pytest.mark.parametrize(
    ("before", "after", "printed"),
    [
        ("… raise the dead, …", "… …", "… [raise the dead,] …"),
        ("Lord even of", "Lord of", "Lord [even] of"),
        ("said by them of old time,", "said,", "said [by them of old time],"),
        (
            "therefore fruits meet",
            "therefore fruit meet",
            "therefore [fruits] fruit meet",
        ),
        ("word", "new word", "new word"),
        ("word", "word new", "word new"),
        ("old word", "word", "[old] word"),
        ("word old", "word", "word [old]"),
        ("word,", "word:", "word[,]:"),
        ("said old”", "said”", "said [old]”"),
        ("one two", "three four", "[one two] three four"),
        ("  same  words \n", "  same  words \n", "  same  words \n"),
        ("one  two old", "one  two new", "one  two [old] new"),
        ("κύριος καὶ θεός", "κύριος θεός", "κύριος [καὶ] θεός"),
        ("καλός λόγος", "νέος λόγος", "[καλός] νέος λόγος"),
    ],
)
@pytest.mark.parametrize("is_greek", [False, True])
def test_printed_spacing_preserves_spans_and_markdown(
    before: str, after: str, printed: str, is_greek: bool
) -> None:
    spans = diff_spans(before, after)
    original = list(spans)
    markdown = marked(spans)
    result = appendix.comparison(spans, is_greek=is_greek)
    assert usj.text_of(result) == printed
    assert spans == original
    assert marked(spans) == markdown
    assert "".join(v for k, v in spans if k != "insert") == before
    assert "".join(v for k, v in spans if k != "delete") == after
    for node in usj.walk(result):
        if node.get("marker") in {"it", "bd"}:
            assert node["marker"] == ("bd" if is_greek else "it")
            text = usj.text_of(node["content"])
            assert text == text.strip()


def test_adjacent_changes_collapse_boundary_spaces_only() -> None:
    spans = [
        ("equal", "Lord  "),
        ("delete", " even "),
        ("delete", " of  old "),
        ("insert", " new  words "),
        ("equal", " ,"),
    ]
    assert (
        usj.text_of(appendix.comparison(spans)) == "Lord [even] [of  old] new  words,"
    )
    assert marked(spans) == "Lord  [- even ][- of  old ][+ new  words ] ,"


@pytest.mark.parametrize(
    "punctuation", [",", ".", ":", ";", "!", "?", "'", '"', "”", "’", ")"]
)
def test_closing_punctuation_follows_the_bracket_without_a_space(
    punctuation: str,
) -> None:
    spans = [("equal", "said "), ("delete", " old "), ("equal", " " + punctuation)]
    assert usj.text_of(appendix.comparison(spans)) == "said [old]" + punctuation


@pytest.mark.parametrize("is_greek", [False, True])
def test_punctuation_insertion_stays_beside_its_word(is_greek: bool) -> None:
    word = "λόγος" if is_greek else "word"
    assert appendix.comparison(diff_spans(word, word + "."), is_greek=is_greek) == [
        usj.char("wg", word) if is_greek else word,
        usj.char("bd", usj.char("wg", ".")) if is_greek else usj.char("it", "."),
    ]


def test_adjacent_word_readings_are_separated_after_punctuation() -> None:
    spans = [("insert", "new."), ("delete", "old words.")]
    assert usj.text_of(appendix.comparison(spans)) == "new. [old words.]"


@pytest.mark.parametrize("words", ["θεὸς τοῦ", "Λυθείσης δὲ"])
@pytest.mark.parametrize("bold", [False, True])
@pytest.mark.parametrize("leading", [False, True])
def test_greek_font_boundary_spaces_survive_ptxprint(
    words: str, bold: bool, leading: bool, tmp_path: Path
) -> None:
    import usfmtc
    from ptxprint.usxutils import PTXEmitter

    first, second = words.split()
    content = [
        *appendix.greek(first + ("" if leading else " ")),
        *appendix.greek((" " if leading else "") + second),
    ]
    assert content == [usj.char("wg", first), " ", usj.char("wg", second)]
    if bold:
        content = [usj.char("bd", *content)]
    assert usj.text_of(content) == words
    for node in usj.walk(content):
        if node.get("marker") == "wg":
            assert usj.text_of(node["content"]) == usj.text_of(node["content"]).strip()
    written = usj.serialize(content)
    marker = "+wg" if bold else "wg"
    assert f"\\{marker} {first}\\{marker}* \\{marker} {second}\\{marker}*" in written
    document = "\\id XXC\n\\ip " + written + "\n"
    parsed = usj.parse(document)
    assert usj.text_of(parsed["content"][1]["content"]) == words
    path = tmp_path / "XXC.usfm"
    path.write_text(document)
    upstream = usfmtc.readFile(str(path))
    for emitter in (None, PTXEmitter):
        options = {"emitter": emitter} if emitter else {}
        processed = upstream.outUsfm(None, **options)
        assert (
            f"\\{marker} {first}\\{marker}* \\{marker} {second}\\{marker}*" in processed
        )
        assert usj.parse(processed) == parsed


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ("λόγος Καὶ", "Λόγος καὶ", "Λόγος καὶ"),
        ("Θεὸς κύριε Χριστοῦ", "θεὸς Κύριε χριστοῦ", "Θεὸς κύριε Χριστοῦ"),
        ("θεοῦ Κυρίῳ χριστὸν", "Θεοῦ κυρίῳ Χριστὸν", "θεοῦ Κυρίῳ χριστὸν"),
        ("Κυρίους θεῶν Χριστοῖς", "κυρίους Θεῶν χριστοῖς", "Κυρίους θεῶν Χριστοῖς"),
        # A servant's human master follows exactly the same rule.
        ("κύριε δός", "Κύριε δός", "κύριε δός"),
        # Substantive replacements retain both original capitalizations.
        ("Λόγος", "ῥῆμα", "[-Λόγος][+ῥῆμα]"),
        ("Θεός", "θεὸς", "[-Θεός][+θεὸς]"),
        ("ᾍδης", "ᾅδης", "ᾅδης"),
        ("ᾍδης", "ἅδης", "[-ᾍδης][+ἅδης]"),
        ("Καὶ λόγος,", "καὶ λόγος:", "καὶ λόγος[-,][+:]"),
        ("Καὶ  λόγος", "καὶ λόγος", "καὶ[- ] λόγος"),
        ("Καὶ λόγος", "καὶ νέος λόγος", "καὶ [+νέος ]λόγος"),
        ("Καὶ νέος λόγος", "καὶ λόγος", "καὶ [-νέος ]λόγος"),
    ],
)
def test_greek_display_case(before: str, after: str, expected: str) -> None:
    assert marked(diff_spans(before, after, greek=True)) == expected
    # The generic comparison stays lossless.
    spans = diff_spans(before, after)
    assert "".join(v for k, v in spans if k != "insert") == before
    assert "".join(v for k, v in spans if k != "delete") == after


@pytest.mark.parametrize("stem", ["θε", "κυρι", "χριστ"])
@pytest.mark.parametrize(
    "ending", ["ος", "ου", "ω", "ον", "ε", "οι", "ων", "οις", "ους", "οιν"]
)
def test_greek_display_all_name_inflections(stem: str, ending: str) -> None:
    word = stem + ending
    assert diff_spans(word.upper(), word, greek=True) == [("equal", word.upper())]
    assert diff_spans(word, word.upper(), greek=True) == [("equal", word)]


def test_case_suppression_precedes_clipping_and_pdf_styling() -> None:
    spans = anchored(
        "Καὶ Θεὸς; λόγος καλός.",
        "καὶ θεὸς; λόγος νέος.",
        [(16, 21, 16, 20)],
        greek=True,
    )
    retained = clipped(spans)
    assert marked(retained) == "… λόγος [-καλός][+νέος]."
    assert (
        usj.text_of(appendix.comparison(retained, is_greek=True))
        == "… λόγος [καλός] νέος."
    )


def test_greek_display_keeps_anchored_relocation() -> None:
    spans = anchored("Καὶ λόγος;", "λόγος καὶ;", [(4, 9, 0, 5)], greek=True)
    assert marked(spans) == "[-Καὶ ]λόγος[+ καὶ];"


@pytest.mark.parametrize("before", ["·", "·", "∙"])
@pytest.mark.parametrize("after", ["·", "·", "∙"])
def test_equivalent_greek_display_are_displayed_alike(before: str, after: str) -> None:
    left, right = f"καί{before} λόγος", f"καί{after} λόγος"
    spans = diff_spans(left, right, greek=True)
    assert all(kind == "equal" for kind, _ in spans)
    for source, absent in ((left, "insert"), (right, "delete")):
        assert "".join(v for k, v in spans if k != absent) == greek_display(source)
    assert marked(spans) == "καί· λόγος"
    assert appendix.comparison(spans, is_greek=True) == [usj.char("wg", "καί· λόγος")]
    # Raw comparisons reconstruct the pinned characters exactly.
    raw = diff_spans(left, right)
    assert "".join(v for k, v in raw if k != "insert") == left
    assert "".join(v for k, v in raw if k != "delete") == right


@pytest.mark.parametrize("dot", ["·", "·", "∙"])
def test_genuine_greek_punctuation_change_stays_visible(dot: str) -> None:
    spans = diff_spans("καί,", f"καί{dot}", greek=True)
    assert marked(spans) == "καί[-,][+·]"
    assert appendix.comparison(spans, is_greek=True) == [
        usj.char("wg", "καί"),
        "[",
        usj.char("wg", ","),
        "]",
        usj.char("bd", usj.char("wg", "·")),
    ]


@pytest.mark.parametrize("dot", ["·", "·", "∙"])
def test_dot_normalization_precedes_anchored_clipping(dot: str) -> None:
    spans = anchored(f"καί{dot} ἔργον ᾧ.", "καί· ὃ.", [(5, 12, 5, 6)], greek=True)
    assert marked(clipped(spans)) == "… [-ἔργον ᾧ][+ὃ]."
    assert appendix.greek(f" καί{dot} ") == [" ", usj.char("wg", "καί·"), " "]


def test_corresponding_distant_passages_share_omissions() -> None:
    from bible.byzantine.presentation import corresponding, passage_spans

    texts = ("old; gap; old.", "new; gap; new.", "one; space; one.", "two; space; two.")
    links = [
        (0, 0, 3, 1, 0, 3),
        (0, 10, 13, 1, 10, 13),
        (0, 0, 3, 2, 0, 3),
        (0, 10, 13, 2, 12, 15),
        (2, 0, 3, 3, 0, 3),
        (2, 12, 15, 3, 12, 15),
    ]
    seeds = [
        [(0, 3), (0, 3), (-1, -1), (-1, -1)],
        [(10, 13), (10, 13), (-1, -1), (-1, -1)],
    ]
    selected = corresponding(texts, links, seeds)
    assert len(selected) == 2
    for p in selected:
        greek = marked(passage_spans(texts, p, 0, []))
        english = marked(passage_spans(texts, p, 2, []))
        assert greek.startswith("…") == english.startswith("…")
        assert greek.endswith("…") == english.endswith("…")
        for text, (a, b) in zip(texts, p):
            assert text[a:b].strip() in text


def test_corresponding_different_punctuation_closes_shared_construction() -> None:
    from bible.byzantine.presentation import corresponding

    texts = ("a; old, end.", "a new end.", "first; old, last.", "first new last.")
    selected = corresponding(
        texts,
        [(0, 3, 6, 1, 2, 5), (0, 3, 6, 2, 7, 10), (2, 7, 10, 3, 6, 9)],
        [[(3, 6), (2, 5), (-1, -1), (-1, -1)]],
    )
    assert selected == [tuple((0, len(t)) for t in texts)]


def test_corresponding_missing_links_uses_complete_verse() -> None:
    from bible.byzantine.presentation import corresponding

    texts = ("a; old.", "a; new.", "a; one.", "a; two.")
    assert corresponding(texts, [], [[(3, 6), (3, 6), (-1, -1), (-1, -1)]]) == [
        tuple((0, len(t)) for t in texts)
    ]


def test_corresponding_crossed_order_keeps_one_passage() -> None:
    from bible.byzantine.presentation import corresponding

    texts = ("a; middle; b.",) * 4
    seeds = [[(0, 1), (11, 12), (0, 1), (0, 1)], [(11, 12), (0, 1), (11, 12), (11, 12)]]
    assert corresponding(texts, [], seeds) == [tuple((0, len(t)) for t in texts)]


@pytest.mark.parametrize(
    ("word", "punctuation", "reading", "is_greek"),
    [
        ("μαρτυροῦντες", ",", "ἐν τῷ οὐρανῷ…", True),
        ("ῥήματα", ".", "ταῦτα.", True),
        ("witnesses", ",", "in heaven…", False),
        ("words", ".", "these.", False),
    ],
)
def test_pending_space_survives_inserted_closing_punctuation(
    word: str, punctuation: str, reading: str, is_greek: bool
) -> None:
    spans = [("equal", word + " "), ("insert", punctuation), ("delete", reading)]
    result = appendix.comparison(spans, is_greek=is_greek)
    assert usj.text_of(result) == f"{word}{punctuation} [{reading}]"
    assert result == [
        usj.char("wg", word) if is_greek else word,
        (
            usj.char("bd", usj.char("wg", punctuation))
            if is_greek
            else usj.char("it", punctuation)
        ),
        " ",
        "[",
        usj.char("wg", reading) if is_greek else reading,
        "]",
    ]


@pytest.mark.parametrize("before", ["᾽", "’"])
@pytest.mark.parametrize("after", ["᾽", "’"])
def test_equivalent_greek_elision_marks_are_displayed_alike(
    before: str, after: str
) -> None:
    left, right = f"κατ{before} αὐτόν", f"κατ{after} αὐτόν"
    spans = diff_spans(left, right, greek=True)
    assert marked(spans) == "κατ’ αὐτόν"
    assert all(kind == "equal" for kind, _ in spans)
    assert appendix.comparison(spans, is_greek=True) == [usj.char("wg", "κατ’ αὐτόν")]
    assert appendix.greek(left) == [usj.char("wg", "κατ’ αὐτόν")]
    for source, absent in ((left, "insert"), (right, "delete")):
        assert "".join(v for k, v in spans if k != absent) == greek_display(source)
        assert "".join(v for k, v in diff_spans(left, right) if k != absent) == source


def test_elision_equivalence_keeps_genuine_word_and_punctuation_changes() -> None:
    spans = diff_spans("κατ᾽ ἐμέ,", "κατ’ αὐτόν;", greek=True)
    assert marked(spans) == "κατ’ [-ἐμέ,][+αὐτόν;]"
    assert appendix.comparison(spans, is_greek=True) == [
        usj.char("wg", "κατ’"),
        " ",
        "[",
        usj.char("wg", "ἐμέ,"),
        "]",
        " ",
        usj.char("bd", usj.char("wg", "αὐτόν;")),
    ]
    assert marked(diff_spans("κατ᾽", "κατά", greek=True)) == "[-κατ’][+κατά]"
    assert marked(diff_spans("κατ᾽", "κατ", greek=True)) == "κατ[-’]"


@pytest.mark.parametrize("gap", [0, 1, 2, 3])
def test_bounded_correspondence_requires_mapped_passage_boundaries(
    gap: int,
) -> None:
    words = [(0, 2), (3, 5), (6, 8), (9, 11)]
    targets = [[0], [1], [2], [3]]
    targets[gap] = []
    # Either language may lack an interior tag. The omitted first phrase
    # cannot supply the preceding mapped word for a retained boundary gap.
    assert appendix._bounded_correspondence(
        words, targets, words, (3, 11), (3, 11)
    ) == (gap in {0, 2})


def test_bounded_correspondence_checks_all_neighbour_targets() -> None:
    words = [(0, 2), (3, 5), (6, 8), (9, 11)]
    assert not appendix._bounded_correspondence(
        words, [[0], [1, 0], [], [3]], words, (3, 11), (3, 11)
    )
    assert not appendix._bounded_correspondence(
        words, [[], [], [], []], words, (3, 11), (3, 11)
    )
    # Crossed links are safe when both ends remain in the paired passage.
    assert appendix._bounded_correspondence(
        words, [[0], [3], [], [1]], words, (3, 11), (3, 11)
    )
