"""Preserve nested character markers in the pinned usfmtc USFM writer."""

from pathlib import Path

from usfmtc import usfmgenerate


def patch(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    changes = (
        (
            "    innote = None\n    for (ev, el) in iterels",
            "    innote = None\n"
            "    parents = {child: parent for parent in root.iter() for child in parent}\n"
            "    for (ev, el) in iterels",
        ),
        (
            '        s = el.get("style", "")\n',
            '        s = el.get("style", "")\n'
            "        parent = parents.get(el)\n"
            '        prefix = "+" if el.tag in ("char", "link") and parent is not None and parent.tag in ("char", "link") else ""\n',
        ),
        (
            '            elif el.tag in ("link", "char"):\n                emit.tag(el)',
            '            elif el.tag in ("link", "char"):\n'
            '                tag = el.makeelement(el.tag, {**el.attrib, "style": prefix + s})\n'
            "                emit.tag(tag)",
        ),
        (
            '                emit("\\\\{}*".format(s))\n            elif el.tag == "sidebar":',
            '                emit("\\\\{}{}*".format(prefix, s))\n            elif el.tag == "sidebar":',
        ),
    )
    for old, new in changes:
        if text.count(old) != 1:
            raise RuntimeError(f"usfmtc changed in {path}; review the nesting patch")
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch(Path(usfmgenerate.__file__))
