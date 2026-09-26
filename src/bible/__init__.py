"""Offline preparation, typesetting, and acceptance checks for the combined Bible.

The build runs in stages, one module each:

1. ``validate``: check the pinned sources (``sources``) against the edition
   manifest (``edition``) and the 1611 marginal notes (``notes``).
2. ``prepare`` and ``typography``: turn each source book into the text the
   edition prints, checking that its wording, notes and markup survive.
3. ``project``: write the PTXprint project for those texts.
4. ``typeset``: run PTXprint in the pinned container (``toolchain``).
5. ``verify``: check PTXprint's processed text and the rendered PDF.
6. ``publish``: copy the checked PDF to dist/ with its provenance.

``cli`` chains the stages; ``usfm`` holds the USFM text helpers they share.
"""
