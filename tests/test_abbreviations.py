"""Brenton's list of abbreviations, completed with those the printed notes use,
and the abbreviations printed in Chicago's forms."""

import re

import pytest

from bible import abbreviations, edition, notes
from bible.abbreviations import ABBREVIATIONS, chicago
from bible.checks import CheckFailed
from bible.prepare import front_matter_text
from bible.usfm import NOTE, plain_text

ADDED = [
    form
    for entry in ABBREVIATIONS["added"]
    for form in entry["abbreviation"].split(", ")
]


def listed(text):
    """The abbreviations a list gives, as it prints them."""
    return [plain_text(cell) for cell in re.findall(r"^\\tc1 (.*)$", text, re.M)]


def forms(text, notes_only=True, code="TST"):
    return chicago(code, text, lambda *a, **k: None, notes_only=notes_only)


@pytest.fixture(scope="module")
def front_matter(archives):
    """Both translations' front and back matter as printed, by id."""
    return {
        e["id"]: front_matter_text(e, archives)
        for e in edition.ordered_entries()
        if "section" not in e and "file" not in e
    }


@pytest.fixture(scope="module")
def printed(scripture, front_matter):
    """Every printed note, and the front and back matter, the list apart, in
    plain text."""
    notes = [
        plain_text(note[0])
        for text in scripture.values()
        for note in NOTE.finditer(text)
    ]
    return notes + [
        plain_text(text) for code, text in front_matter.items() if code != "XXD"
    ]


@pytest.fixture(scope="module")
def source(archives):
    return archives["brenton"][abbreviations.SOURCE]


@pytest.mark.parametrize("form", ADDED)
def test_every_added_abbreviation_is_printed(printed, form):
    used = re.compile(rf"(?<![A-Za-z&]){re.escape(form)}(?![A-Za-z])")
    assert any(used.search(text) for text in printed)


def test_the_added_rows_are_in_alphabetical_order():
    # By their letters as printed: "absol." before "AD", "LXX" before "MS, MSS".
    def letters(abbreviation):
        return re.sub(r"[^a-z]", "", abbreviation.lower())

    added = [e["abbreviation"] for e in ABBREVIATIONS["added"]]
    lettered = [a for a in added if letters(a) and not a[0].isdigit()]
    assert lettered == sorted(lettered, key=letters)


def test_nothing_is_listed_twice(source):
    brenton = listed(source)
    assert len(brenton) == 12
    retained = [a for a in brenton if a not in ABBREVIATIONS["expanded"]["removed"]]
    assert len(set(retained + ADDED)) == len(retained) + len(ADDED)


def test_the_list_keeps_brentons_rows_and_adds_the_rest(front_matter, source):
    text = front_matter["XXD"]
    removed = ABBREVIATIONS["expanded"]["removed"]
    assert listed(text) == [
        forms(a, notes_only=False) for a in listed(source) if a not in removed
    ] + [e["abbreviation"] for e in ABBREVIATIONS["added"]]
    assert not {"A. V.", "Ald.", "Vat.", "Complut.", "Vulg.", "Comp."} & set(
        listed(text)
    )
    assert {"LXX", "Alex.", "p., pp."} <= set(listed(text))


@pytest.mark.parametrize(
    "old, new",
    [
        ("Vat.", "Vatican Text"),
        ("Ald.", "Aldine Text"),
        ("Complut.", "Complutensian Text"),
        ("Vulg.", "Vulgate"),
        ("Sept.", "LXX"),
        ("LXX.", "LXX"),
        ("A. V.", "Authorized Version"),
        ("AV:", "Authorized Version:"),
    ],
)
def test_text_names_are_printed_inline(old, new):
    assert forms(f"\\f - \\ft {old} reads\\f*") == f"\\f - \\ft {new} reads\\f*"


def test_printed_notes_use_full_text_names(printed):
    for old, full in abbreviations.TEXT_NAMES.items():
        assert any(full in text for text in printed)
        assert not any(re.search(rf"(?<!\w){re.escape(old)}", text) for text in printed)
    assert not any(re.search(r"\bSept\.", text) for text in printed)


def test_meanings_are_capitalized_as_chicago_does(front_matter):
    text = front_matter["XXD"]
    meanings = [m.strip() for m in re.findall(r"^\\tc2 for (.*)$", text, re.M)]
    assert {"literally.", "sign of addition.", "sign of omission."} <= set(meanings)
    assert {"Hebrew.", "Septuagint.", "saint."} <= set(meanings)


def test_a_note_that_is_no_sentence_ends_without_a_period(scripture):
    assert "\\fqa guard\\ft , Authorized Version\\f*" in scripture["2KI"]
    assert "\\ft ' in the Old Testament\\f*" in scripture["1KI"]
    # A sentence keeps it.
    assert "the general meaning of κάρπωμα in LXX.\\f*" in scripture["NUM"]


def test_latin_is_italic():
    (ie,) = [e for e in ABBREVIATIONS["added"] if e["abbreviation"] == "i.e."]
    assert abbreviations.row(ie) == (
        "\\tr\n\\tc1 \\it i.e.\\it*\n\\tc2 for \\it id est\\it*, that is."
    )


@pytest.mark.parametrize(
    "source, printed",
    [
        ("\\ft i. e. \\fqa Nachor", "\\ft i.e., \\fqa Nachor"),
        ("(\\it i.e.\\it* in those", "(\\it i.e.\\it*, in those"),
        ("\\ft q. d. \\fqa had almost", "\\ft q.d. \\fqa had almost"),
        ("Heb. תמים scil. 'that I", "Heb. תמים sc. 'that I"),
        ("\\+wg*. Scil. \\+wg πόλιν", "\\+wg*. Sc. \\+wg πόλιν"),
        # Brenton's "Comp." for "Compare" is printed in full.
        ("\\ft Comp. \\xt Romans 1:19", "\\ft Compare \\xt Romans 1:19"),
        ("\\ft comp. Heb.", "\\ft compare Heb."),
        ("to call\\ft , &c. The LXX. seem", "to call\\ft , etc. The LXX seem"),
        # A period that ends the sentence, or the note, stays.
        ("edition of the LXX.\\f*", "edition of the LXX.\\f*"),
        ("So the Vat. The Alex. reads", "So the Vatican Text. The Alex. reads"),
        ("in LXX.; the singular", "in LXX; the singular"),
        (
            "\\ft A. V. \\fqa Mattaniah",
            "\\ft Authorized Version \\fqa Mattaniah",
        ),
        (
            "\\ft A. V. '\\fqa my people",
            "\\ft Authorized Version '\\fqa my people",
        ),
        # A note that isn't a sentence has already lost its closing period.
        ("\\ft guard, \\fqa A. V", "\\ft guard, \\fqa Authorized Version"),
        ("century \\+sc b.c.\\+sc* It has", "century BC. It has"),
        ("century \\+sc b.c.\\+sc*, who", "century BC, who"),
        ("century \\+sc a.d.\\+sc* by a", "century AD by a"),
        # AD before its year, BC after.
        ("date (\\+sc b.c.\\+sc* 217–209).", "date (217–209 BC)."),
        ("the year \\+sc a.d.\\+sc* 126.", "the year AD 126."),
        ("the year 285 \\+sc b.c.\\+sc* the", "the year 285 BC the"),
        ("date (\\+sc b.c.\\+sc* 217-209).", "date (217-209 BC)."),
        # "Sept." is "LXX", at a note's end too, where it has lost its period.
        ("the Sept. and so", "the LXX and so"),
        ("\\ft so the Sept", "\\ft so the LXX"),
        # A period before a closing quotation mark ends its sentence.
        ("the LXX.’ The Heb.", "the LXX.’ The Heb."),
        # Only a line in capitals takes "ETC.".
        ("Heb. and LXX, &c. so", "Heb. and LXX, etc. so"),
    ],
)
def test_chicago_forms(source, printed):
    assert forms(f"\\f - {source}\\f*") == f"\\f - {printed}\\f*"


def test_an_era_other_than_ad_or_bc_is_refused():
    # "a.c." is ante Christum, which printing as "AD" would reverse.
    with pytest.raises(CheckFailed, match="not in Chicago's forms"):
        forms("\\f - \\ft the year 285 a.c. the\\f*")


def test_ad_after_its_year_is_refused():
    # Chicago sets "AD" before its year, which the rule reads only after it.
    with pytest.raises(CheckFailed, match="not in Chicago's forms"):
        forms("\\f - \\ft the year 126 \\+sc a.d.\\+sc* the\\f*")


def test_a_paragraph_end_keeps_its_period():
    text = "\\ip the edition of the LXX.\n\\ip in the century \\sc b.c.\\sc*\n"
    assert forms(text, notes_only=False) == (
        "\\ip the edition of the LXX.\n\\ip in the century BC.\n"
    )


def test_compare_at_a_notes_end_is_refused():
    # The note has lost the period that "Comp." is read by.
    with pytest.raises(CheckFailed, match="not in Chicago's forms"):
        forms("\\f - \\ft so Heb. Comp\\f*")


def test_a_form_printed_without_its_period_loses_it_at_a_notes_end():
    # A period that notes.unclosed keeps at a note's end would be kept there as
    # a sentence's, so no form printed without one may be among its abbreviations.
    for form in abbreviations.UNSTOPPED:
        assert not notes.ABBREVIATION.search(form + ".")


def test_only_notes_change_in_scripture():
    text = "\\v 1 the LXX. seem \\f - \\ft the LXX. seem\\f*"
    assert forms(text) == "\\v 1 the LXX. seem \\f - \\ft the LXX seem\\f*"


def test_the_king_james_front_matter_takes_chicagos_forms(front_matter):
    reader, dedication = front_matter["NDX"], front_matter["TDX"]
    assert "&c" not in reader and "i. e." not in reader
    assert "\\it etc\\it*." in reader and ", etc. i.e., \\it The" in reader
    assert "\\mt2 DEFENDER OF THE FAITH, ETC." in dedication
    assert "S. \\it" not in reader and "Thus St. \\it Augustine\\it*." in reader
    assert "\\it The doctrine of St\\it*. John" in reader


@pytest.mark.parametrize(
    "code, printed",
    [
        ("MAT", "after five shillings the ounce is seven pence halfpenny."),
        ("MAT", "A talent is 187 pounds 10 shillings"),
        ("MRK", "The Roman penny is seven pence halfpenny as"),
        ("LUK", "nine gallons three quarts."),
        ("LUK", "This 36th verse"),
        ("LUK", "is three pounds two shillings six pence."),
        ("NDX", "in his 4th \\it Catechesis\\it*. Saint"),
        ("OTH", "save 1 and 2 Esdras [of the English Apocrypha]"),
        ("NDX", "Acts 17:11 and 8:28, 29."),
        ("PSA", "\\xt Psalm 44 \\ft title"),
        ("ACT", "\\xt Deuteronomy 1:31\\ft ; \\xt 2 Maccabees 7:27\\ft , according"),
        ("ACT", "\\xt Esaias 55:3 \\ft and in many others"),
        ("PRO", "\\xt Mark 14:72 \\ft and margin, with"),
    ],
)
def test_numbers_take_chicagos_forms(scripture, front_matter, code, printed):
    assert printed in {**scripture, **front_matter}[code]


@pytest.mark.parametrize("section", ["numbers", "expanded"])
def test_every_decision_names_a_unit_the_build_prepares(section):
    # A change to any other unit would never be met, and so never refused.
    prepared = {e["id"] for e in edition.ordered_entries() if "file" not in e}
    assert {c["unit"] for c in ABBREVIATIONS[section]["changes"]} <= prepared


def test_a_decision_in_scripture_must_fall_in_a_note(patched):
    data = patched(abbreviations, "ABBREVIATIONS")
    data["expanded"]["changes"] = [{"unit": "TST", "from": "Rom. penny", "to": "x"}]
    with pytest.raises(CheckFailed, match="changes the text outside the notes: TST"):
        forms("\\v 1 the Rom. penny \\f - \\ft Gr.\\f*")


def test_a_number_change_must_be_met_once(patched):
    data = patched(abbreviations, "ABBREVIATIONS")
    data["numbers"]["changes"] = [{"unit": "TST", "from": "3. quarts", "to": "x"}]
    with pytest.raises(CheckFailed, match="met 0 times: TST 3. quarts"):
        forms("\\f - \\ft nine gallons\\f*")


def test_nothing_printed_keeps_the_sources_forms(scripture, front_matter):
    for text in scripture.values():
        for note in NOTE.finditer(text):
            assert not abbreviations.UNCHICAGO.search(note[0]), note[0]
    for text in front_matter.values():
        assert not abbreviations.UNCHICAGO.search(text)


def test_a_form_left_is_refused(monkeypatch):
    monkeypatch.setattr(abbreviations, "REPLACED", [])
    with pytest.raises(CheckFailed, match="not in Chicago's forms"):
        forms("\\f - \\ft i. e. \\fqa Nachor\\f*")


@pytest.mark.parametrize(
    "note",
    [
        "\\f - \\ft Gr. infin. for imper\\f*",
        "\\f - \\ft according to the Sept. and so Chrysost\\f*",
        "\\f - \\ft the ounce is 187.li 10.s.\\f*",
        "\\f - \\ft in the O. T\\f*",
    ],
)
def test_a_form_the_file_prints_in_full_must_be_decided(note):
    with pytest.raises(CheckFailed, match="not in Chicago's forms"):
        forms(note)


@pytest.mark.parametrize(
    "note",
    [
        "\\f - \\ft after 5. shillings\\f*",
        "\\f - \\ft compare \\xt Mark 14:72\\ft . and margin\\f*",
    ],
)
def test_a_number_left_with_its_period_in_a_note_is_refused(note):
    with pytest.raises(CheckFailed, match="Number with a period within a note's"):
        forms(note)


def test_a_label_outside_the_notes_keeps_its_number_period():
    text = "\\im 1870. captives | Authorized Version: burned"
    assert forms(text, notes_only=False) == text


@pytest.mark.parametrize(
    "code, printed",
    [
        ("1SA", "\\fq turned him: \\ft Complutensian Text reads, "),
        ("BAK", "participle Niphal feminine of"),
        ("BAK", "2 \\it last verse\\it*. 3."),
        ("BAK", "(query item struthiocamelus)"),
        ("BAK", "\\it Charles Pridham\\it*."),
        ("BAK", "16. (\\it Alex. \\it* 15.)"),
        ("XXB", "\\im \\it Authorized Version\\it* bowed himself"),
        ("1KI", "Heb. Grammar, p. 92"),
        ("DEU", "note in the margin of the Authorized Version on"),
        ("JOS", "\\fq Nephthali: \\ft or, \\fqa of Nephthali\\f*"),
    ],
)
def test_abbreviations_printed_in_full_or_in_one_form(
    scripture, front_matter, code, printed
):
    assert printed in {**scripture, **front_matter}[code]


def test_compare_and_the_authorized_version_are_in_full(printed, front_matter):
    assert not any(re.search(r"\b[Cc]omp\.", text) for text in printed)
    assert any(re.search(r"\bCompare\b", text) for text in printed)
    assert not re.search(r"English [Vv]ersion|Eng\. Ver", front_matter["XXB"])
    assert not any(re.search(r"\bA\. ?V\b|\bAV\b", text) for text in printed)
    assert any("Authorized Version" in text for text in printed)


@pytest.mark.parametrize(
    "code, printed",
    [
        # "Alex." keeps its period, as an abbreviation does...
        ("1KI", "So the Alex. The Vatican Text renders"),
        ("1SA", "Verse 12 is here supplied by Alex.\\f*"),
        ("1KI", "supplied by the Alex. See Appendix.\\f*"),
        ("MAL", "\\fqa give a charge for you to be fed\\ft . Alex.\\f*"),
        # ...and a sum printed in full keeps the period that ends its sentence.
        ("MAT", "which after five shillings the ounce is seven pence halfpenny.\\f*"),
        ("MAT", "the ounce is 187 pounds 10 shillings.\\f*"),
        # A note that is no sentence ends without one.
        (
            "MAT",
            "six pence, after five shillings the ounce is seven pence halfpenny\\f*",
        ),
    ],
)
def test_a_sentence_keeps_its_full_stop_after_a_form_in_full(scripture, code, printed):
    assert printed in scripture[code]
