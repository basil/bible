"""The published PDF's page labels are its folios."""

import json
from pathlib import Path

import pytest

from bible.checks import CheckFailed
from bible.files import write_json
from bible.publish import label_pages
from bible.toolchain import capture


def blank_pdf(path: Path, pages: int) -> None:
    """A PDF of blank pages, its cross-reference table counted out."""
    kids = " ".join(f"{3 + i} 0 R" for i in range(pages))
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>",
        *["<< /Type /Page /Parent 2 0 R /MediaBox [0 0 10 10] /Resources << >> >>"]
        * pages,
    ]
    body = b"%PDF-1.4\n"
    offsets = []
    for number, text in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{number} 0 obj\n{text}\nendobj\n".encode()
    table = len(body)
    body += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    body += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    body += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{table}\n%%EOF\n"
    ).encode()
    path.write_bytes(body)


def test_labels_run_roman_then_arabic_from_the_divider(tmp_path: Path) -> None:
    pdf = tmp_path / "bible.pdf"
    blank_pdf(pdf, 6)
    write_json(
        tmp_path / "book-boundaries.json",
        [
            {"id": "FRT", "title": "Contents", "page": 1, "printed_page": "i"},
            {"id": "XXA", "title": "The Old Testament", "page": 4, "printed_page": "1"},
            {"id": "GEN", "title": "Genesis", "page": 6, "printed_page": "3"},
        ],
    )
    labelled = label_pages(pdf, tmp_path)
    pages = json.loads(capture("qpdf", "--json", "--json-key=pages", labelled))
    assert [p["label"] for p in pages["pages"]] == [
        {"/S": "/r", "/St": n} for n in (1, 2, 3)
    ] + [{"/S": "/D", "/St": n} for n in (1, 2, 3)]
    # The PDF that verification checked is left as it was.
    assert "PageLabels" not in pdf.read_bytes().decode()
    # The same PDF gives the same copy, its /ID included.
    copy = labelled.read_bytes()
    assert label_pages(pdf, tmp_path).read_bytes() == copy


def test_labels_need_the_divider(tmp_path: Path) -> None:
    pdf = tmp_path / "bible.pdf"
    blank_pdf(pdf, 2)
    write_json(
        tmp_path / "book-boundaries.json",
        [{"id": "FRT", "title": "Contents", "page": 1, "printed_page": "i"}],
    )
    with pytest.raises(CheckFailed):
        label_pages(pdf, tmp_path)
