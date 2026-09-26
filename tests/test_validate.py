"""Source validation: pinned archives and the manifest's use of them."""

import pytest

from bible import edition, notes, paths, sources, validate
from bible.checks import CheckFailed
from bible.edition import scripture_unit as unit
from bible.files import read_json

BAD_SHA256 = "0" * 64


@pytest.fixture(autouse=True)
def build_dir(tmp_path, monkeypatch):
    # validate() reports into build/; keep the tests' reports out of the checkout.
    monkeypatch.setattr(paths, "BUILD_DIR", tmp_path)
    return tmp_path


def test_validate(build_dir):
    assert set(validate.validate()) == {"brenton", "kjv"}
    report = read_json(build_dir / "validation.json")
    assert report["kjv_marginal_notes"] == notes.EXPECTED_NT_MARGINAL_NOTES
    assert (build_dir / "nehemias-differences.diff").exists()


def test_source_archive_checksum(patched):
    patched(sources, "SOURCES")["kjv"]["sha256"] = BAD_SHA256
    with pytest.raises(CheckFailed, match="Checksum mismatch: sources/engkjvcpb"):
        sources.load_archives()


def test_divided_source_must_be_printed_whole(patched):
    patched(edition, "MANIFEST")
    unit("EZR")["chapters"] = [1, 9]
    with pytest.raises(CheckFailed, match="not printed whole: brenton/EZR"):
        validate.validate()
