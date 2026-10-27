"""The edition's structural roles, checked across its exported corpus."""

from pathlib import Path

import pytest

from bible import export, peripherals, pipeline, usj


@pytest.mark.parametrize(
    "text",
    [
        "\\id FRT\n\\li1 \\lik Label:\\lik* Description.\n",
        '\\id XXA\n\\periph Preface|id="preface"\n\\p A preface.\n'
        "\\esb \\cat colophon\\cat*\n\\p A closing notice.\n\\esbe\n",
        "\\id GEN\n\\c 1\n\\p\\v 1 Words."
        "\\f + \\cat edition\\cat*\\ft See "
        "\\ref Genesis 1:2|GEN 1:2\\ref*.\\f*\n",
    ],
)
def test_standard_containers_and_references_agree_with_usfmtc(
    text: str, tmp_path: Path
) -> None:
    import usfmtc

    path = tmp_path / "unit.usfm"
    path.write_text(text, encoding="utf-8")
    ours = usj.parse(text)
    assert usj.parse(usj.serialize(ours)) == ours
    assert usj.parse(usj.serialize(usfmtc.readFile(str(path)).outUsj(None))) == ours


def test_peripheral_chapters_and_sidebar_boundaries() -> None:
    text = '\\id XXA\n\\periph Index|id="x-index"\n\\c 1\n\\cp A\n\\p Words.\n'
    doc = usj.parse(text)
    assert usj.parse(usj.serialize(doc)) == doc
    with pytest.raises(RuntimeError, match="Unclosed sidebar"):
        usj.parse("\\id GEN\n\\esb\n\\p Open.\n\\id EXO\n")


def test_exported_roles_are_consistent_across_the_edition(
    edition: pipeline.Edition, prepared: list[tuple[str, usj.Document]]
) -> None:
    physical = export.grouped(edition, prepared)
    assert len({code for code, _ in physical}) == len(physical)
    divisions = []
    colophons = []
    for code, grouped in physical:
        doc = usj.parse(usj.serialize(grouped))
        # In particular, independent adjacent tables must not merge.
        assert sum(n["type"] == "table" for n in usj.walk(grouped["content"])) == sum(
            n["type"] == "table" for n in usj.walk(doc["content"])
        )
        assert usj.parse(usj.serialize(doc)) == doc, code
        for block in usj.walk(doc["content"]):
            if block["type"] == "periph":
                assert doc["content"][0]["code"] in {"FRT", "INT"}
                divisions.append(block["id"])
            if block["type"] == "sidebar":
                colophons.append((code, block.get("category")))
            if usj.is_note(block):
                assert block["marker"] != "ef", code
                if block["marker"] == "f":
                    assert all(
                        n.get("marker") != "xt" for n in usj.walk(block["content"])
                    ), code
        block_groups: list[list[usj.Node]] = [doc["content"]]
        block_groups.extend(
            [
                list(usj.objects(n["content"]))
                for n in usj.objects(doc["content"])
                if n["type"] == "periph"
            ],
        )
        for blocks in block_groups:
            for at, block in enumerate(blocks):
                if usj.is_type(block, "para", "b"):
                    assert 0 < at < len(blocks) - 1, code
                    # A testament's title page sets its translation credit
                    # apart from the title and the editorial credit.
                    if code in {"XXF", "XXG"}:
                        if usj.is_type(blocks[at - 1], "para", "b"):
                            continue
                        following = next(
                            (
                                b
                                for b in blocks[at + 1 :]
                                if not usj.is_type(b, "para", "b")
                            ),
                            None,
                        )
                        assert (
                            usj.paragraph(blocks[at - 1]),
                            usj.paragraph(following),
                        ) in {("mt1", "mt2"), ("mt2", "mt3")}, code
                        continue
                    # A blank line also sets a table or a list apart from
                    # the prose.
                    if export.set_apart(blocks[at - 1]):
                        assert usj.paragraph(blocks[at + 1]) in usj.PROSE, code
                        continue
                    assert usj.paragraph(blocks[at - 1]) in usj.BODY, code
                    if export.set_apart(blocks[at + 1]):
                        continue
                    if usj.is_type(blocks[at + 1], "chapter"):
                        assert at + 2 < len(blocks), code
                        before = usj.paragraph(blocks[at - 1])
                        after = usj.paragraph(blocks[at + 2])
                        assert (before in usj.PROSE and after in usj.POEM) or (
                            before in usj.POEM and after in usj.PROSE
                        ), code
                    elif blocks[at + 1]["type"] != "sidebar":
                        assert usj.paragraph(blocks[at + 1]) in usj.BODY, code
    assert divisions == [
        peripherals.UNITS[code]
        for code, _ in pipeline.view(edition, "pdf")
        if code not in edition.scripture
    ]
    assert {code for code, _ in colophons} == set(
        "MAT MRK LUK JHN ROM 1CO 2CO GAL EPH PHP COL 1TH 2TH 1TI 2TI TIT PHM HEB REV".split()
    )
    assert len(colophons) == 19
    assert {category for _, category in colophons} == {"colophon", "closing"}


def test_quotation_roles_preserve_the_edition_grammar(
    edition: pipeline.Edition,
) -> None:
    for code, phrase in [
        ("ISA", "he that sendeth"),
        ("JER", "he hath passed the appointed time"),
    ]:
        quotes = [
            usj.text_of(n["content"])
            for n in usj.walk(edition.documents[code]["content"])
            if usj.is_type(n, "char", "it")
        ]
        assert any(phrase in value for value in quotes), code


def test_unnumbered_chapters_have_native_chapter_headings(
    edition: pipeline.Edition,
) -> None:
    from bible import scripture

    found = []
    for code in edition.scripture:
        blocks = edition.documents[code]["content"]
        for at, block in enumerate(blocks):
            if (
                block["type"] == "chapter"
                and block.get("pubnumber") == scripture.HIDDEN
            ):
                assert usj.is_type(blocks[at + 1], "para", "cl"), (
                    code,
                    block["number"],
                )
                found.append((code, block["number"]))
    assert sorted(found) == [("DAG", "0"), ("DAG", "13")]


@pytest.mark.parametrize(
    "text",
    [
        "\\id FRT\n\\p \\lik Key\\lik* words.\n",
        "\\id FRT\n\\li1 Words \\lik Key\\lik*.\n",
        "\\id FRT\n\\li1 \\lik One\\lik* \\lik Two\\lik*.\n",
        "\\id FRT\n\\li1 \\lik \\lik* words.\n",
    ],
)
def test_list_keys_must_open_their_entries(text: str) -> None:
    with pytest.raises(RuntimeError, match="List key outside"):
        pipeline.check_document(
            "test", usj.parse(text), scripture_unit=False, authored_page=True
        )
