# OLEBFont assembly

OLEBFont is the edition's text family, assembled once, when the image is
built, by `scripts/build_olebfont.py` from whichever base the image has: from
Valkyrie OT where `make bootstrap` found its four faces on the host, and from
Utopia otherwise. Both recipes give a family named OLEBFont with the features
the layout and stylesheet select (`onum`, `pnum`, `sups`, `smcp`, `c2sc`), so
nothing downstream knows which base it came from; the Greek face paired with
the base is installed beside it (GFS Heraklit with Valkyrie, GFS Didot with
Utopia), and the build reads both from the image.

## From Valkyrie OT

Valkyrie is proprietary and never committed. `scripts/collect_valkyrie.sh`
copies the faces fontconfig finds on the host into `build/valkyrie/`, by their
PostScript names, and the Dockerfile copies that directory, empty or full, into
the image; one to three faces stop the image build.

The faces stay as designed: outlines, hints, metrics, kerning and features
are untouched, the word space included, and Valkyrie's copyright, trademark
and licence notices remain embedded, as its licence requires of a licensee's
modified copy. What Valkyrie lacks for the edition is the superior lowercase
and the superior colon: its `sups` feature covers figures only, and the
edition sets `35a` and `30:1` labels and alphabetic note callers with `sups`.
These twenty-seven glyphs come from `npxsups`, the superiors font of Michael
Sharpe's newpx package (`sources/newpx.zip`), in the matching face. One
transform places them all, measured from the fonts rather than fixed: the
donor's superior one is laid on Valkyrie's superior one (both flat-topped,
without overshoot), which gives a uniform scale, about 0.85 in Regular, and a
raise that sets the donor's superior baseline on Valkyrie's. Every donated
letter, and the colon, then stands to Valkyrie's figures exactly as it stands
to npxsups' own: the same x-height, capital height, descent and baseline in
proportion, and the same weight relative to the figures (the donor's stems
come to about 60 units beside Valkyrie's 71; uniform scaling cannot change
weight apart from size). Nothing is stretched or placed by hand.
The glyphs are written unhinted,
in Valkyrie's own hint dictionary, as `a.sups` to `z.sups` and `colon.sups`,
and `sups` is extended to select them, and to select the superior figures from
every form of a figure (`onum`, `tnum`, `tallfig`, small-cap), so that the
layout's `onum` and `pnum` cannot keep a verse number from its superior.
Nothing else of the donor is imported: no capitals, punctuation, code points
or kerning. The family's names change to OLEBFont; its description (name ID
10) says what it was assembled from, which the tests read to know the recipe.

## From Utopia

OLEBFont combines the pinned Utopia, Erewhon and Erewhon Math sources:

- Utopia supplies overlapping glyphs and character mappings, except superscript
  1, 2 and 3, which use Erewhon to match its superior figure set.
- The matching Erewhon text face supplies missing characters and alternates.
- Erewhon Math supplies the remaining glyphs. Regular and Italic prefer Regular
  Math; Bold and BoldItalic prefer Bold Math. Each falls back to the other Math
  face for missing glyphs, without synthesizing weight or slant.

### Scale

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

### Coverage and provenance

Private-use collisions retain the higher-priority character mapping. Math
glyphs with conflicting identities receive separate internal names so their
alternate lookups remain valid. Supplementary mathematical alphabets use
format-12 Unicode cmaps.

Each generated font, in either recipe, has a `.glyphs.csv` sidecar recording
every output slot, its source face and glyph, the scale and raise it was
placed with, its Unicode mappings and its metrics. These reports are generated alongside the fonts rather
than committed. Original copyright and license notices are embedded and
included with the generated family.

OLEBFont imports Math substitutions and pair positioning for added glyphs.
It does not import a MATH table or replace an extensible equation font.

## Numerals, superiors and word spacing

PTXprint's font settings enable `onum` and `pnum` on all four faces, so the
text, headings, notes, front matter and contents use proportional oldstyle
numbers. Chapter figures and labels name OLEBFont directly in the stylesheet,
with `lnum` and `pnum`, since the base font name's embedded `onum` setting
cannot be turned off by a feature-list subtraction; they are set in lining
figures. The stylesheet selects `sups` for verse numbers, note origins,
embedded verse numbers and callers, and `smcp`/`c2sc` for the running heads
(the footer's folio turns them off again, since Valkyrie's `c2sc` would set it
in small-cap lining figures). A mixed label, `35a` or `30:1`, is set whole in
`sups`: the figures, the letter and the colon are all designed superiors,
Erewhon's in the Utopia recipe and Valkyrie's figures with npxsups' letters
in the Valkyrie one, so no TeX shrinks or raises anything. No digits in the
content are rewritten. `\XeTeXgenerateactualtext=1` records the input Unicode
in the PDF, so that these alternate glyphs can still be copied and searched.

XeTeX takes a font's interword glue from its space glyph: the stretch is half
the advance and the shrink a third. The Utopia recipe widens the space advance
by a fifth when it assembles the font (225 to 270 units in Regular and Italic,
210 to 252 in the bold faces), which gives Utopia's narrow word space about
0.27 em, 0.135 em and 0.09 em at the same proportions. The Valkyrie recipe
leaves Valkyrie's own spacing alone. No TeX adjusts the glue.

The assembler corrects the advance of Erewhon Italic's tabular oldstyle zero
from 498 to 500 units, and makes the superscripts accept every numeral form.
It recentres Regular `zero.oldstyle`, `six.oldstyle`, and `eight.oldstyle`
because their round outlines had markedly unequal sidebearings. It also
recentres Regular `three.oldstyle` by eight units toward the left. Their
advances stay unchanged. Between proportional `.oldstyle` figures, Regular
and Italic add shared left and right spacing allowances, and all four faces
add their own pair exceptions. These allowances are pair positioning, not
changes to glyph metrics; tabular figures remain unkerned. The shifts are in
`font_sources.py`, and the allowances and exceptions are in `FIGURE_SPACING`
and `FIGURE_KERNS` in `build_olebfont.py`.

## Validation and inspection

`tests/test_olebfont.py` reads which recipe the installed faces came from and
checks what holds for both: the names and features, that `sups` sets every
figure form, every lowercase letter and the colon in designed superiors, that
every Latin character the exported edition prints is encoded, that the
installed Greek covers the variants, and that assembling the recipe again from
its sources gives the installed bytes. For the Utopia recipe it then checks all
four serialized faces against independently transformed source outlines and
metrics, verifies donor preference and Unicode coverage, and checks hint edges,
numeral features, small capitals, kerning, ligatures and the widened space.
Normalized Erewhon basic Latin bounds agree with Utopia within 1.1 units in
Regular, Italic and BoldItalic; advances agree within one unit. Bold retains
Erewhon's deliberate widening. For the Valkyrie recipe it checks that every
glyph, metric, lookup and notice of the base survives unchanged and that each
added superior is the donor's glyph under the measured placement.

For a complete inventory of all 12 source faces, including unencoded glyphs:

```sh
python /work/scripts/inventory_fonts.py --utopia /opt/utopia \
  --archives /opt/sources --output /work/build/font-inventory
```

Run this inside the toolchain container. `make bootstrap` rebuilds the fonts,
`make test` runs regressions, and `make font-specimen` renders the assembled
family. A change to either recipe can change advances and so line breaks;
review sample pages before publication.
