"""The pinned Greek texts: Scrivener, the parsed Scrivener, RP2018, RP2026 as
patched and as printed; the printed Guardian text is compared directly to the
patched RP2018."""

from __future__ import annotations

import copy
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from typing import Any

import pytest

from bible.byzantine import BOOKS
from bible.byzantine.greek import (
    PATCHES,
    Diacritic,
    PrintedVerse,
    Structure,
    Tags,
    Text,
    accent_letters,
    accented_scrivener,
    ascii_greek,
    bp5_line,
    greek_letters,
    greek_words,
    occurrences,
    page_text,
    pages,
    parsed_scrivener,
    printed,
    rp2018,
    rp2026,
)
from bible.sources import Content

Printed = tuple[dict[str, PrintedVerse], list[Diacritic]]


def nfc(words: Iterable[str]) -> list[str]:
    return [unicodedata.normalize("NFC", w) for w in words]


@pytest.fixture(scope="module")
def structure(byzantine: Mapping[str, Any]) -> Structure:
    result = byzantine["structure"]
    assert isinstance(result, Structure)
    return result


@pytest.fixture(scope="module")
def tr(byzantine: Mapping[str, Any]) -> Text:
    found: Text = byzantine["tr"]
    return found


@pytest.fixture(scope="module")
def rp18(byzantine_inputs: Mapping[str, Content]) -> tuple[Text, Tags]:
    return rp2018(byzantine_inputs["rp2018"])


@pytest.fixture(scope="module")
def guardian(byzantine_inputs: Mapping[str, Content], structure: Structure) -> Printed:
    return printed(byzantine_inputs["rp2026"], structure.omitted, "REV 22:21")


# Alphabet and helpers.


def test_alphabets_and_accents(tr: Text) -> None:
    assert (
        ascii_greek("χριστοῦ Ἰησοῦ ψυχή θύρα ξένος") == "xristou ihsou yuxh qura cenos"
    )
    assert tr["MAT 1:1"][2:6] == ["ihsou", "xristou", "uiou", "dabid"]
    # Lunate sigma reads as sigma; capitals fold.
    assert ascii_greek("Ϲ ϲ Σ σ ς") == "s s s s s"
    assert greek_words("Βίβλος γενέσεως, Ἰησοῦ.") == ["biblos", "genesews", "ihsou"]


def test_occurrences_finds_every_start_of_a_phrase() -> None:
    stream = "a b a b a".split()
    assert occurrences(stream, ["a", "b"]) == [0, 2]
    assert occurrences(stream, ["a"]) == [0, 2, 4]
    assert occurrences(stream, ["b", "b"]) == []
    assert occurrences(stream, []) == []


# Scrivener 1894.


def test_scrivener_inventory_and_structural_verses(
    tr: Text, structure: Structure
) -> None:
    assert len(tr) == 7957
    assert tr["MAT 1:1"][:6] == "biblos genesews ihsou xristou uiou dabid".split()
    # Scrivener prints the verses RP omits; they are real tokens here.
    assert all(tr[ref] for ref in structure.omitted)
    assert tr["ACT 8:37"][-3:] == ["ton", "ihsoun", "xriston"]
    assert len(tr["ACT 8:37"]) == 23
    # The bracketed Stephanus alternatives are not Scrivener's text.
    assert all(w.isalpha() and w.isascii() for words in tr.values() for w in words)


def test_parsed_scrivener_selects_second_reading_and_shared_tags(
    tr: Text, byzantine_inputs: Mapping[str, Content]
) -> None:
    text, tags = parsed_scrivener(byzantine_inputs["parsed_tr"])
    assert len(text) == 7957
    assert sum(text[ref] == tr[ref] for ref in text) == 7921
    # Stephanus: found; Scrivener: saw. Both branches have their own tags.
    assert "eidon" in text["MAT 2:11"]
    assert "euron" not in text["MAT 2:11"]
    # Spelling branches share the following Strong's and parsing fields.
    name = next(t for t in tags["MAT 4:13"] if t["word"] == "nazareq")
    assert name["strong"] == [3478]
    assert name["parse"] == ["N-PRI"]
    assert text["PHM 1:25"][-1] == "amhn"
    # Changed boundaries are visible, not silently borrowed as annotations.
    assert text["MAT 15:5"] != tr["MAT 15:5"]


def test_annotation_mismatches_are_excluded_from_the_checked_tags(
    byzantine: Mapping[str, Any],
) -> None:
    assert len(byzantine["annotation_mismatches"]) == 36
    assert "MAT 15:5" in byzantine["annotation_mismatches"]
    assert "TR MAT 15:5" not in byzantine["tr_tags"]
    assert "TR MAT 1:1" in byzantine["tr_tags"]
    assert all(key.startswith("TR ") for key in byzantine["tr_tags"])


# RP2018 from the BP5 files.


def test_multiple_annotations_are_one_word(rp18: tuple[Text, Tags]) -> None:
    _, tags = rp18
    assert tags["MAT 4:15"][0] == {
        "word": "gh",
        "strong": [1093, 1093],
        "parse": ["N-NSF", "N-VSF"],
    }
    assert bp5_line("01.01 logos 3056 {N-NSM}") == (
        "1:1",
        [{"word": "logos", "strong": [3056], "parse": ["N-NSM"]}],
    )
    with pytest.raises(ValueError, match="Unparsed BP5"):
        bp5_line("01.01 logos 3056 {N-NSM} ?")
    with pytest.raises(ValueError, match="Missing BP5 annotation"):
        bp5_line("01.01 logos 3056")


def test_rp2018_inventory_and_omitted_verses(
    rp18: tuple[Text, Tags], structure: Structure
) -> None:
    text, tags = rp18
    assert len(text) == 7957
    assert {ref for ref, words in text.items() if not words} == structure.omitted
    assert all([t["word"] for t in tags[ref]] == text[ref] for ref in text)
    assert text["PHM 1:1"][2:4] == ["xristou", "ihsou"]


# RP2026: Appendix A against the printed Guardian text.


def test_rp2026_applies_appendix_a_without_mutation(
    rp18: tuple[Text, Tags], guardian: Printed
) -> None:
    text, _ = rp18
    snapshot, _ = guardian
    before = copy.deepcopy(text)
    result = rp2026(text, snapshot)
    assert text == before
    assert len(result) == 7957
    assert sum(bool(v) for v in result.values()) == 7953
    assert [ref for ref in text if text[ref] != result[ref]] == list(PATCHES)
    assert len(occurrences(result["PHM 1:1"], ["ihsou", "xristou"])) == 1
    assert occurrences(result["PHM 1:1"], ["xristou", "ihsou"]) == []
    assert result["REV 11:16"].count("qronou") == text["REV 11:16"].count("qronou") - 1
    assert result["MAT 26:29"] == [
        w.replace("gennhmatos", "genhmatos") for w in text["MAT 26:29"]
    ]


def test_rp2026_refuses_stale_patches_and_a_changed_printed_text(
    rp18: tuple[Text, Tags], guardian: Printed
) -> None:
    text, _ = rp18
    snapshot, _ = guardian
    with pytest.raises(ValueError, match="Stale Appendix A patch"):
        rp2026({**text, "MAT 26:29": []}, snapshot)
    changed = {
        **snapshot,
        "MAT 1:1": PrintedVerse({**snapshot["MAT 1:1"], "Greek": ["x"]}),
    }
    with pytest.raises(
        ValueError, match="disagrees with the printed Guardian text.*MAT 1:1"
    ):
        rp2026(text, changed)
    with pytest.raises(ValueError, match="disagrees with the printed Guardian text"):
        rp2026(text, {ref: row for ref, row in snapshot.items() if ref != "JUD 1:25"})


def test_printed_main_text_equals_rp2026_verse_for_verse(
    byzantine: Mapping[str, Any], guardian: Printed, structure: Structure
) -> None:
    snapshot, _ = guardian
    assert len(snapshot) == 7957
    assert all(snapshot[ref]["Greek"] == byzantine["rp"][ref] for ref in snapshot)
    assert snapshot["PHM 1:1"]["Greek"][2:4] == ["ihsou", "xristou"]
    assert nfc(snapshot["MAT 1:1"]["accented"][:3]) == ["Βίβλος", "γενέσεως", "Ἰησοῦ"]
    assert snapshot["MAT 1:1"]["page"] == 29
    assert snapshot["PHM 1:1"]["page"] == 611
    for ref, row in snapshot.items():
        assert len(byzantine["rp_alignment"].spans[ref]) == len(row["Greek"]), ref
        assert "".join(
            ascii_greek("".join(accent_letters(w))) for w in row["accented"]
        ) == "".join(row["Greek"]), ref
    for ref in structure.omitted:
        assert snapshot[ref] == {"Greek": [], "accented": [], "page": None}


def test_printed_pages_run_forward_through_the_canon(guardian: Printed) -> None:
    snapshot, _ = guardian
    numbered = [(ref, page) for ref, row in snapshot.items() if (page := row["page"])]
    assert numbered[-1][1] == 734  # Revelation 22:18-21 stands on printed page 734
    assert [p for _, p in numbered] == sorted(p for _, p in numbered)


def test_printed_apparatus_contrasts_are_accent_only(guardian: Printed) -> None:
    _, diacritics = guardian
    assert [(d["ref"], *nfc([d["from"], d["to"]]), d["page"]) for d in diacritics] == [
        ("LUK 3:23", "ἠλι", "ἡλι", 195),
        ("PHP 3:5", "περιτομή", "περιτομῇ", 567),
    ]
    assert all(ascii_greek(d["from"]) == ascii_greek(d["to"]) for d in diacritics)
    assert all("TR" in d["apparatus"] for d in diacritics)


def test_printed_pages_carry_main_text_and_apparatus_separately(
    byzantine: Mapping[str, Any],
) -> None:
    xml = byzantine["printed_xml"]
    page = pages(xml)[29]
    main = greek_words(page_text([page], True))
    apparatus = greek_words(page_text([page], False))
    assert main[:6] == "biblos genesews ihsou xristou uiou dauid".split()
    assert "dabid" not in main
    assert "dabid" in apparatus
    assert apparatus[:2] == ["kata", "matqaion"]


def test_printed_reader_refuses_a_changed_scripture_font(
    byzantine_inputs: Mapping[str, Content], structure: Structure
) -> None:
    source = byzantine_inputs["rp2026"].read_text()
    changed = source.replace(
        '<fontspec id="25" size="17"', '<fontspec id="25" size="16"', 1
    )
    assert changed != source
    path = Content({"changed.xml": changed.encode()}) / "changed.xml"
    with pytest.raises(ValueError, match="Changed Guardian scripture font"):
        printed(path, structure.omitted, "REV 22:21")


# The structural decisions, omissions and the patches.


def test_moved_and_omitted_verses_are_closed_sets(structure: Structure) -> None:
    assert structure.moved == {
        "MAT 23:13": "MAT 23:14",
        "MAT 23:14": "MAT 23:13",
        "ROM 16:25": "ROM 14:24",
        "ROM 16:26": "ROM 14:25",
        "ROM 16:27": "ROM 14:26",
    }
    assert structure.inverse == {v: k for k, v in structure.moved.items()}
    assert structure.rp_ref("ROM 16:25") == "ROM 14:24"
    assert structure.kjv_ref("ROM 14:24") == "ROM 16:25"
    assert structure.rp_ref("MAT 1:1") == structure.kjv_ref("MAT 1:1") == "MAT 1:1"
    assert structure.omitted == {"LUK 17:36", "ACT 8:37", "ACT 15:34", "ACT 24:7"}
    assert set(PATCHES) == {
        "MAT 26:29",
        "ROM 13:9",
        "PHM 1:1",
        "REV 11:16",
        "REV 13:14",
    }


def accented_input(verses: Mapping[str, list[str]]) -> Content:
    rows = []
    for ref, words in verses.items():
        book, address = ref.split()
        chapter, verse = map(int, address.split(":"))
        rows.append(
            {
                "book_name_short": book,
                "chapter": chapter,
                "verse": verse,
                "words": [{"greek": word} for word in words],
            }
        )
    return Content({"tr.json": json.dumps(rows).encode()}) / "tr.json"


def test_accented_tr_preserves_source_words(
    byzantine: Mapping[str, Any], tr: Text
) -> None:
    alignment = byzantine["tr_alignment"]
    original = json.loads(byzantine["source_inputs"]["accented_tr"].read_text())
    source = {
        f"{r['book_name_short']} {r['chapter']}:{r['verse']}": [
            unicodedata.normalize("NFC", w["greek"]) for w in r["words"]
        ]
        for r in original
    }
    for ref in tr:
        assert len(alignment.spans[ref]) == len(tr[ref])
        assert all(
            w in source[address]
            for w, address in zip(
                alignment.text[ref], alignment.addresses[ref], strict=True
            )
        )
    assert alignment.text["MAT 1:1"][:3] == ["Βίβλος", "γενέσεως", "Ἰησοῦ"]
    assert alignment.text["REV 13:18"][-1] == "χξϛ´."


def test_alignment_crosses_word_and_verse_boundaries() -> None:
    tr = {"MAT 1:1": ["dia", "ti", "estin"], "MAT 1:2": ["mhpote", "outws"]}
    supplied = {"MAT 1:1": ["Διατί"], "MAT 1:2": ["ἐστί", "μή", "ποτε", "οὕτω"]}
    assert accented_scrivener(accented_input(supplied), tr).text == {
        "MAT 1:1": ["Διατί", "ἐστί"],
        "MAT 1:2": ["μή", "ποτε", "οὕτω"],
    }
    assert tr["MAT 1:1"] == ["dia", "ti", "estin"]


def test_alignment_keeps_repeated_words_in_source_order() -> None:
    tr = {"MAT 1:1": ["estin", "estin", "estin"]}
    supplied = {"MAT 1:1": ["ἔστι", "ἐστί", "ἐστὶν"]}
    assert accented_scrivener(accented_input(supplied), tr).text["MAT 1:1"] == [
        "ἔστι",
        "ἐστί",
        "ἐστὶν",
    ]


@pytest.mark.parametrize(
    "plain, marked",
    [
        (["kai"], ["καί", "δέ"]),
        (["kai", "de"], ["καί"]),
        (["logos"], ["λόγον"]),
        (["logos"], ["λόγως"]),
    ],
)
def test_alignment_refuses_other_changes(plain: list[str], marked: list[str]) -> None:
    with pytest.raises(ValueError, match="(Unsupported|Unaligned).*MAT"):
        accented_scrivener(accented_input({"MAT 1:1": marked}), {"MAT 1:1": plain})


def test_alignment_refuses_ambiguous_word_division() -> None:
    with pytest.raises(ValueError, match="Ambiguous.*MAT 1:1 / MAT 1:1"):
        accented_scrivener(accented_input({"MAT 1:1": ["ἄν"]}), {"MAT 1:1": ["a", "n"]})


def test_alignment_refuses_unknown_characters_and_inventory() -> None:
    with pytest.raises(ValueError, match="Unknown Greek"):
        accented_scrivener(accented_input({"MAT 1:1": ["καί@"]}), {"MAT 1:1": ["kai"]})
    with pytest.raises(ValueError, match="Unknown Greek"):
        accented_scrivener(accented_input({"MAT 1:1": ["kai"]}), {"MAT 1:1": ["kai"]})
    with pytest.raises(ValueError, match="verse inventory"):
        accented_scrivener(accented_input({"MAT 1:2": ["καί"]}), {"MAT 1:1": ["kai"]})


@pytest.mark.parametrize(
    "plain, marked",
    [
        (["dia", "ti"], ["(Διατί;)"]),
        (["mhpote"], ["(Μή", "Ποτε);"]),
        (["aparti"], ["ἀπ᾽", "άρτι·"]),
        (["estin"], ["ἘΣΤΊ;"]),
        (["outw"], ["ΟὝΤΩΣ."]),
        (["sws"], ["(ϹῶϹ)"]),
        (["xcs"], ["χξϛ´."]),
    ],
)
def test_alignment_preserves_complete_source_words(
    plain: list[str], marked: list[str]
) -> None:
    alignment = accented_scrivener(
        accented_input({"MAT 1:1": marked}), {"MAT 1:1": plain}
    )
    assert alignment.text == {"MAT 1:1": marked}
    for at in range(len(plain)):
        assert alignment.project("MAT 1:1", (at, at + 1)) == (0, len(marked))
    assert alignment.project("MAT 1:1", (len(plain), len(plain))) == (
        len(marked),
        len(marked),
    )
    with pytest.raises(ValueError, match="Invalid Greek token range"):
        alignment.project("MAT 1:1", (0, len(plain) + 1))


def test_complete_joined_word_projects_across_verse_boundaries() -> None:
    alignment = accented_scrivener(
        accented_input({"MAT 1:1": ["(Διατί;)"], "MAT 1:2": ["ἐστί."]}),
        {"MAT 1:1": ["dia"], "MAT 1:2": ["ti", "estin"]},
    )
    assert alignment.text == {"MAT 1:1": ["(Διατί;)"], "MAT 1:2": ["(Διατί;)", "ἐστί."]}
    assert alignment.addresses["MAT 1:2"] == ["MAT 1:1", "MAT 1:2"]
    assert alignment.spans["MAT 1:2"] == [(0, 1), (1, 2)]


def test_display_punctuation_matches_pinned_sources(
    byzantine: Mapping[str, Any],
) -> None:
    def punctuation(text: str) -> str:
        return "".join(
            c
            for c in unicodedata.normalize("NFD", text)
            if not c.isalpha() and not c.isspace() and not unicodedata.combining(c)
        )

    original = json.loads(byzantine["source_inputs"]["accented_tr"].read_text())
    for book in BOOKS:
        source = " ".join(
            w["greek"]
            for row in original
            if row["book_name_short"] == book
            for w in row["words"]
        )
        aligned = " ".join(
            w
            for ref, words in byzantine["tr_accented"].items()
            if ref.split()[0] == book
            for w in words
        )
        assert punctuation(aligned) == punctuation(source), book

        # Only final nu/sigma may differ in letter count; all other letters
        # retain the raw transcription's case across the whole book.
        def case_without_finals(text: str) -> list[bool]:
            return [
                c[0].isupper()
                for c in accent_letters(text)
                if ascii_greek(c) not in ("n", "s")
            ]

        assert case_without_finals(aligned) == case_without_finals(source), book
    root = ET.fromstring(byzantine["printed_xml"].read_bytes())
    source = " ".join(
        "".join(n.itertext()).strip()
        for n in root.findall("page/text")
        if n.get("font") == "25"
    )
    source = re.sub(r"-\s+(?=\w)", "", source)
    aligned = " ".join(
        w for verse in byzantine["printed"].values() for w in verse["accented"]
    )
    assert punctuation(aligned) == punctuation(source)
    assert [c[0].isupper() for c in accent_letters(aligned)] == [
        c[0].isupper() for c in accent_letters(source)
    ]
