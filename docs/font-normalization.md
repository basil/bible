# OLEBFont normalization

OLEBFont combines the pinned Utopia, Erewhon and Erewhon Math sources:

- Utopia supplies overlapping glyphs and character mappings, except superscript
  1, 2 and 3, which use Erewhon to match its superior figure set.
- The matching Erewhon text face supplies missing characters and alternates.
- Erewhon Math supplies the remaining glyphs. Regular and Italic prefer Regular
  Math; Bold and BoldItalic prefer Bold Math. Each falls back to the other Math
  face for missing glyphs, without synthesizing weight or slant.

## Scale

Utopia uses the original Utopia size convention. Erewhon and Erewhon Math use
UtopiaStd size, so their outlines, spacing, positioning and hints are enlarged
by **100/94**. This classification applies to every glyph in the source face,
including small capitals, superior figures, large delimiters and empty glyphs.

The [Erewhon documentation](https://mirrors.mit.edu/CTAN/fonts/erewhon/doc/erewhon-doc.pdf)
documents a 6% reduction from Heuristica, which matched old Utopia, to commercial
UtopiaStd size. The pinned Erewhon Math source documents scaling Fourier designs
to 94% to match Erewhon text; its letters and digits derive from Erewhon.
See the [Math user's guide](https://tug.ctan.org/fonts/erewhon-math/Erewhon-Math.pdf).
All sources use 1000 units/em. Utopia's `H` height is 692 units; Erewhon's is 650,
which becomes 691.49 after normalization. The inverse restores the size
convention while retaining donor rounding, design changes and spacing choices.

`scripts/font_sources.py` expands donor CFF subroutines before scaling Type 2
operands and private hint dictionaries. Ghost-hint markers `-20` and `-21`
remain literal sentinels while their edge positions scale. BlueScale is divided
by the factor to retain its pixel-size threshold. Integer OpenType metrics and
positioning use OpenType rounding; explicit CFF widths match the rounded hmtx
advances. Erewhon Italic's tabular oldstyle zero advance is repaired from 498
to 500 before scaling. Utopia programs, subroutines, hints, original lookups and
line metrics remain intact; glyph bounding boxes grow to fit the additions.

## Coverage and provenance

Private-use collisions retain the higher-priority character mapping. Math
glyphs with conflicting identities receive separate internal names so their
alternate lookups remain valid. Supplementary mathematical alphabets use
format-12 Unicode cmaps.

Each generated font has a `.glyphs.csv` sidecar recording every output slot,
source face and glyph, native size convention, scale factor, Unicode mappings
and normalized metrics. These reports are generated alongside the fonts rather
than committed. Original copyright and license notices are embedded and
included with the generated family.

OLEBFont imports Math substitutions and pair positioning for added glyphs.
It does not import a MATH table or replace an extensible equation font.

## Validation and inspection

`tests/test_olebfont.py` checks all four serialized faces against independently
transformed source outlines and metrics, verifies donor preference and Unicode
coverage, and checks hint edges, numeral features, small capitals, kerning,
ligatures and deterministic builds. Normalized Erewhon basic Latin bounds agree
with Utopia within 1.1 units in Regular, Italic and BoldItalic; advances agree
within one unit. Bold retains Erewhon's deliberate widening.

For a complete inventory of all 12 source faces, including unencoded glyphs:

```sh
python /work/scripts/inventory_fonts.py --utopia /opt/utopia \
  --archives /opt/sources --output /work/build/font-inventory
```

Run this inside the toolchain container. `make bootstrap` rebuilds the fonts,
`make test` runs regressions, and `make font-specimen` renders the assembled
family. Donor scaling changes advances and can change line breaks; review
sample pages before publication.
