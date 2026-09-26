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


def test_brenton_exceptions_must_name_a_printed_book(patched):
    patched(notes, "BRENTON_NOTES")["notes"]["GNE 1:1"] = {"lemma": "x", "why": "x"}
    with pytest.raises(CheckFailed, match=r"outside the edition: \['GNE'\]"):
        validate.validate()


def test_note_exceptions_must_have_known_fields(patched):
    patched(notes, "BRENTON_NOTES")["notes"]["GEN 2:19"]["lemmma"] = "x"
    with pytest.raises(CheckFailed, match=r"unknown fields: \['GEN 2:19'\]"):
        validate.validate()


@pytest.mark.parametrize(
    "file, kind, key",
    [
        ("BRENTON_NOTES", "notes", "GEN 2:19"),
        ("BRENTON_NOTES", "corrections", "GEN 21:11"),
        ("KJV_NOTES", "notes", "MAT 14:30 boisterous"),
        ("KJV_NOTES", "corrections", "MAT 23:18 guilty"),
    ],
)
def test_note_exceptions_must_give_a_why(patched, file, kind, key):
    del patched(notes, file)[kind][key]["why"]
    with pytest.raises(CheckFailed, match=rf"without a why: \['{key}'\]"):
        validate.validate()


@pytest.mark.parametrize(
    "file, key, field",
    [
        ("BRENTON_NOTES", "GEN 21:11", "uncategorised"),
        ("KJV_NOTES", "MAT 23:18 guilty", "form"),
    ],
)
def test_note_corrections_must_have_known_fields(patched, file, key, field):
    patched(notes, file)["corrections"][key][field] = "x"
    with pytest.raises(CheckFailed, match=rf"unknown fields: \['{key}'\]"):
        validate.validate()


def test_each_of_several_corrections_to_a_note_is_checked(patched):
    del patched(notes, "BRENTON_NOTES")["corrections"]["1SA 27:8"][1]["why"]
    with pytest.raises(CheckFailed, match=r"without a why: \['1SA 27:8'\]"):
        validate.validate()


@pytest.mark.parametrize(
    "file, key",
    [
        ("BRENTON_NOTES", "GEN 21:11"),
        # Checked before parsing the 1611 notes, which applies their corrections.
        ("KJV_NOTES", "MAT 23:18 guilty"),
    ],
)
def test_note_corrections_must_say_what_they_replace(patched, file, key):
    del patched(notes, file)["corrections"][key]["to"]
    with pytest.raises(CheckFailed, match=rf"missing or unknown fields: \['{key}'\]"):
        validate.validate()


def test_occurrence_needs_a_lemma(patched):
    exception = patched(notes, "BRENTON_NOTES")["notes"]["GEN 2:19"]
    del exception["lemma"]
    exception["occurrence"] = 2
    with pytest.raises(CheckFailed, match=r"no lemma: \['GEN 2:19'\]"):
        validate.validate()


def test_brenton_corrections_must_mend_a_printed_source(patched):
    # The standalone Nehemias is a witness the edition doesn't print.
    patched(notes, "BRENTON_NOTES")["corrections"]["NEH 1:1"] = {
        "from": "\\id NEH",
        "to": "\\id NEH",
        "why": "x",
    }
    with pytest.raises(CheckFailed, match=r"doesn't print: \['NEH'\]"):
        validate.validate()


def test_brenton_corrections_must_stand_where_their_key_says(patched):
    corrections = patched(notes, "BRENTON_NOTES")["corrections"]
    corrections["GEN 21:12"] = corrections.pop("GEN 21:11")
    with pytest.raises(CheckFailed, match="not where its key says: GEN 21:12"):
        validate.validate()


def test_brenton_corrections_are_applied_in_turn(patched):
    # The second correction's text exists only until the first has been made.
    corrections = patched(notes, "BRENTON_NOTES")["corrections"]
    corrections["GEN 21:11b"] = {
        "from": "\\fqa Gr. \\fqa Gr. ",
        "to": "\\fqa Gr. ",
        "why": "x",
    }
    with pytest.raises(CheckFailed, match="does not apply: GEN 21:11b"):
        validate.validate()


def test_divided_source_must_be_printed_whole(patched):
    patched(edition, "MANIFEST")
    unit("EZR")["chapters"] = [1, 9]
    with pytest.raises(CheckFailed, match="not printed whole: brenton/EZR"):
        validate.validate()


def test_uncategorized_flag_needs_an_anchor(patched):
    patched(notes, "KJV_NOTES")["notes"]["MRK 2:21 new"]["uncategorized"] = True
    with pytest.raises(CheckFailed, match=r"without an anchor: \['MRK 2:21 new'\]"):
        validate.validate()
