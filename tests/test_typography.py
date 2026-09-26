"""Typographic quotes, ellipses and dashes."""

import pytest

from bible.checks import CheckFailed
from bible.typography import typographic_quotes


def test_typographic_quotes():
    text = "\\c 1\n\\v 1 He said, \"Go--now.\" It's `done'...\n"
    result, count = typographic_quotes(text)
    assert result == "\\c 1\n\\v 1 He said, “Go—now.” It’s ‘done’…\n"
    assert count == 7


@pytest.mark.parametrize(
    "text, message",
    [
        ("\\v 1 a <b> c", "looks like HTML"),
        ('\\v 1 a \\"b', "SmartyPants escape"),
        ("\\v 1 a ''b''", "Ambiguous doubled quote"),
        ("\\v 1 a `1", "Backtick is not an opening quote"),
    ],
)
def test_typographic_quotes_refuses_ambiguous_text(text, message):
    with pytest.raises(CheckFailed, match=message):
        typographic_quotes(text)
