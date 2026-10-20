"""Keep callerless notes from overwriting PTXprint's caller-page records."""

from pathlib import Path


def patch(path: Path) -> None:
    # Callerless margin notes do not increment the automatic counter. Their
    # page records otherwise overwrite the last caller's page, preventing
    # the next page's first bottom note from restarting at a (or 1).
    old = r"""          \x@\write\x@\n@tepages\x@{\m@sg{\the\pageno}}% record the page where this note occurred
"""
    new = r"""          \ifx\them@rk\empty\else
            \x@\write\x@\n@tepages\x@{\m@sg{\the\pageno}}% record the caller's page only
          \fi
"""
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"PTXprint changed in {path}; review the caller-page patch")
    path.write_text(text.replace(old, new), encoding="utf-8")


if __name__ == "__main__":
    patch(Path("/opt/ptxprint/src/ptx-note-style.tex"))
