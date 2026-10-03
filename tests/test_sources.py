"""Every external text is checked before it enters the pipeline."""

import re
from pathlib import Path

import pytest

from bible import paths, sources
from bible.checks import CheckFailed


@pytest.mark.parametrize("name", ["marginal_notes", "versification"])
def test_changed_source_text_is_refused(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_root = paths.ROOT
    for source_name, source in sources.SOURCES.items():
        relative = source.get("archive", source.get("file"))
        assert relative is not None
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source_name == name:
            destination.write_bytes((original_root / relative).read_bytes() + b"\n")
        else:
            destination.symlink_to(original_root / relative)
    (tmp_path / "content").symlink_to(paths.CONTENT_DIR, target_is_directory=True)
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.setattr(paths, "CONTENT_DIR", tmp_path / "content")
    with pytest.raises(
        CheckFailed,
        match=re.escape(f"Checksum mismatch: {sources.SOURCES[name]['file']}"),
    ):
        sources.load()
