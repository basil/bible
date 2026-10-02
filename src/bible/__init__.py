"""Offline preparation, typesetting, and acceptance checks for the combined Bible.

The build runs in this order:

1. ``sources`` and ``policy``: read the pinned sources and the edition's
   decisions (edition/*.json), each once.
2. ``pipeline``: prepare the edition from them, stage by stage, as USJ
   (``usj``), and export it as USFM.
3. ``project``: write the PTXprint project for those texts.
4. ``typeset``: run PTXprint in the pinned container (``toolchain``).
5. ``verify``: check PTXprint's processed text and the rendered PDF.
6. ``publish``: copy the checked PDF to dist/ with its provenance.

``cli`` chains them; ``review`` writes what the decisions come to.
"""
