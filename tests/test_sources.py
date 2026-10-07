"""Every external text is checked before it enters the pipeline."""

from __future__ import annotations

import io
import re
import subprocess
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from bible import paths, sources
from bible.byzantine import greek
from bible.byzantine.inventories import boyd
from bible.checks import CheckFailed
from bible.sources import Content


def pinned_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, data: bytes | None
) -> str:
    """A checkout whose pinned source `name` holds `data` (or is missing),
    the others linked to the real ones; its path."""
    original_root = paths.ROOT
    for source_name, source in sources.SOURCES.items():
        relative = source.get("archive") or source["file"]
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source_name != name:
            destination.symlink_to(original_root / relative)
        elif data is not None:
            destination.write_bytes(data)
    (tmp_path / "content").symlink_to(paths.CONTENT_DIR, target_is_directory=True)
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.setattr(paths, "CONTENT_DIR", tmp_path / "content")
    source = sources.SOURCES[name]
    return source.get("archive") or source["file"]


@pytest.mark.parametrize(
    "name",
    [
        "marginal_notes",
        "versification",
        "scrivener",
        "accented_tr",
        "collation",
        "msb_tables",
    ],
)
def test_changed_source_text_is_refused(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = sources.SOURCES[name]
    data = (paths.ROOT / (source.get("archive") or source["file"])).read_bytes()
    relative = pinned_copy(tmp_path, monkeypatch, name, data + b"\n")
    # A changed PDF is refused before Poppler is asked to read it.
    monkeypatch.setattr(sources, "converted", None)
    with pytest.raises(CheckFailed, match=re.escape(f"Checksum mismatch: {relative}")):
        sources.load()


def test_missing_source_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relative = pinned_copy(tmp_path, monkeypatch, "faa", None)
    with pytest.raises(FileNotFoundError, match=re.escape(relative)):
        sources.load()


# The archives' members, read once into a snapshot.


def archive(names: Sequence[str]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as output:
        for name in names:
            output.writestr(name, name.encode())
    return stream.getvalue()


@pytest.mark.parametrize(
    "names, message",
    [
        (["other.usx"], "missing or ambiguous"),
        (["one-MAT.usx", "two-MAT.usx"], "missing or ambiguous"),
        (["one-MAT.usx", "one-MAT.usx"], "Duplicate archive member"),
        (["../one-MAT.usx"], "escaping or invalid"),
    ],
)
def test_archive_refuses_bad_inventory(names: list[str], message: str) -> None:
    if len(names) != len(set(names)):
        with pytest.warns(UserWarning, match="Duplicate name"):
            data = archive(names)
    else:
        data = archive(names)
    with pytest.raises(CheckFailed, match=message) as error:
        sources.members(sources.archive_content(data, "witness.zip"), "", ("*MAT.usx",))
    assert "witness.zip" in str(error.value)


def test_archive_selects_bytes_with_named_diagnostics() -> None:
    content = sources.members(
        sources.archive_content(archive(["one-MAT.usx", "intro.usx"]), "witness.zip"),
        "",
        ("*MAT.usx",),
    )
    assert (content / "one-MAT.usx").read_bytes() == b"one-MAT.usx"
    assert str(content / "one-MAT.usx") == "witness.zip/one-MAT.usx"
    assert [p.name for p in content.glob("*MAT.usx")] == ["one-MAT.usx"]
    with pytest.raises(FileNotFoundError, match="witness.zip/absent.usx"):
        (content / "absent.usx").read_bytes()


@pytest.mark.parametrize(
    "name",
    [
        "/absolute",
        "a/../one-MAT.usx",
        "./one-MAT.usx",
        "a//one-MAT.usx",
        "a\\one-MAT.usx",
        "a//",
    ],
)
def test_archive_refuses_unsafe_nested_paths(name: str) -> None:
    with pytest.raises(CheckFailed, match="escaping or invalid"):
        sources.archive_content(archive([name]), "witness.zip")


def test_archive_nested_directory_view_and_missing_directory() -> None:
    data = archive(["repo/", "repo/text/", "repo/text/one-MAT.usx", "repo/LICENSE"])
    content = sources.archive_content(data, "witness.zip")
    view = sources.members(content, "repo/text/", ("*MAT.usx",))
    assert (view / "one-MAT.usx").read_bytes() == b"repo/text/one-MAT.usx"
    assert [p.name for p in view.glob("*.usx")] == ["one-MAT.usx"]
    assert str(view / "one-MAT.usx") == "witness.zip/repo/text/one-MAT.usx"
    with pytest.raises(CheckFailed, match="missing or ambiguous"):
        sources.members(content, "repo/absent/", ("*MAT.usx",))


def test_malformed_archive_xml_names_its_member() -> None:
    content = sources.members(
        sources.archive_content(archive(["one-MAT.usx"]), "witness.zip"),
        "",
        ("*MAT.usx",),
    )
    with pytest.raises(ValueError, match=r"witness.zip/one-MAT.usx"):
        boyd(content)


def test_content_keeps_the_readers_decoding_and_newlines() -> None:
    content = Content({"text": b"caf\xe9\r\nsecond\rthird"}) / "text"
    assert content.read_text(encoding="cp1252").splitlines() == [
        "café",
        "second",
        "third",
    ]
    assert content.open_text(encoding="cp1252").read() == "café\nsecond\nthird"
    assert (
        content.open_text(encoding="cp1252", newline="").read()
        == "café\r\nsecond\rthird"
    )


def test_shared_rp_archive_views(byzantine_inputs: Mapping[str, Content]) -> None:
    name = "byzantine-majority-text-27a45ff1b7be6c17ccbfeac414f3f55732ae8e28.zip/"
    assert str(byzantine_inputs["rp2018"]).startswith(name)
    assert str(byzantine_inputs["rp_margin"]).startswith(name)
    assert byzantine_inputs["rp2018"]._files is byzantine_inputs["rp_margin"]._files
    assert len(byzantine_inputs["rp2018"].glob("*.BP5")) == 27
    assert len(byzantine_inputs["rp_margin"].glob("[0-9][0-9]_*.TXT")) == 27
    assert greek.marginal_alternates(byzantine_inputs["rp_margin"])


# The PDFs, as Poppler reads them.


def test_real_pdf_inputs_are_named_and_complete(
    byzantine_inputs: Mapping[str, Content], byzantine: Mapping[str, Any]
) -> None:
    assert byzantine_inputs["rp2026"].name == "TGNTByzText_081526_0727PM.xml"
    assert byzantine_inputs["collation"].name == "collation-scrivener-rp-2018.txt"
    assert len(byzantine["printed"]) == 7957
    assert len(byzantine["collation"]) == 1885


@pytest.mark.parametrize("failure", ["missing", "conversion"])
def test_pdf_conversion_failures_are_named(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        if failure == "missing":
            raise FileNotFoundError(command[0])
        raise subprocess.CalledProcessError(1, command, stderr=b"broken PDF")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(
        CheckFailed, match=r"TGNTByzText_081526_0727PM.pdf: pdftohtml conversion failed"
    ) as error:
        sources.converted(
            "TGNTByzText_081526_0727PM.pdf", b"%PDF", "pdftohtml", ("-xml",)
        )
    if failure == "conversion":
        assert "broken PDF" in str(error.value)


def test_pdf_conversion_uses_the_pinned_bytes_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pinned = {
        name: (paths.ROOT / (source.get("archive") or source["file"])).read_bytes()
        for name, source in sources.SOURCES.items()
    }
    read: list[Path] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        pdf = Path(command[-2] if command[0] == "pdftotext" else command[-1])
        assert pdf.read_bytes() == next(
            pinned[name]
            for name, source in sources.SOURCES.items()
            if Path(source.get("file", "")).name == pdf.name
        )
        read.append(pdf)
        if command[0] == "pdftohtml":
            assert command[1:-1] == ["-xml", "-i", "-stdout"]
        else:
            assert command[1] == "-layout" and command[-1] == "-"
        return subprocess.CompletedProcess(command, 0, b"converted", b"")

    monkeypatch.setattr(subprocess, "run", run)
    inputs = sources.byzantine_inputs(pinned)
    assert len(read) == 2
    assert all(not path.exists() for path in read)
    assert (
        inputs["rp2026"].read_bytes()
        == inputs["collation"].read_bytes()
        == b"converted"
    )
