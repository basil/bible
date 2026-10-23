# Font assembly and selection

[scripts/build_olebfont.py](../scripts/build_olebfont.py) builds the four
OLEBFont faces during `make bootstrap`. Preparation reads the installed fonts
through [typeface.py](../src/bible/typeface.py). The reader-facing account of
the typography belongs in [the introduction](../content/introduction.sfm);
source notices are listed in [sources/README.md](../sources/README.md).

| Base supplied to the image | Greek family | Printed chapter numeral |
| --- | --- | --- |
| All four Valkyrie OT A faces | GFS Heraklit | TeX Gyre PagellaX Regular from newpx |
| No Valkyrie faces | GFS Didot | OLEBFont Regular |

[collect_valkyrie.sh](../scripts/collect_valkyrie.sh) finds the host's faces
through fontconfig and copies them to `build/valkyrie/` by PostScript name.
Conflicting copies fail collection; a partial set fails font assembly.
`make bootstrap WITHOUT_VALKYRIE=1` explicitly selects the Utopia build.
Valkyrie files are proprietary and must not be committed. Rebuild the image
after changing a recipe or the available base fonts.

## Valkyrie recipe

The original glyph programs, metrics, spacing, and layout lookups are retained.
The family is renamed OLEBFont, with its original notices retained and donor
notices added. Name ID 10 identifies the recipe for the regression tests.

The matching `npxsups` face supplies 26 superior lowercase letters and a
superior colon. One scale and vertical translation per face fits the donor's
superior one to Valkyrie's superior one; that same transform places every
donated glyph. The added outlines are unhinted. No donor character mappings
or kerning are imported.

The superior one is used because both designs are flat-topped, without overshoot. One uniform transform retains the donor letters' proportions and their baseline relationship to its figures; it does not independently match stem weight. In Regular the measured scale is about 0.85, and the donor stems remain lighter than Valkyrie's figures. Nothing is stretched or individually placed.

The appended `sups` lookup also covers the existing numeral variants, so
`onum` or `tnum` cannot prevent superior verse figures. It decomposes letter
ligatures such as `fi` into their superior letters. These details matter for
alphabetic note callers and mixed labels such as `35a` and `30:1`.

## Utopia recipe

Utopia supplies overlapping glyphs and mappings, except encoded superscript
1, 2, and 3, which are replaced by the matching Erewhon superiors. The matching
Erewhon text face supplies missing glyphs, then Erewhon Math supplies the
remainder. Regular and Italic prefer Regular Math; Bold and BoldItalic prefer
Bold Math, falling back to the other Math face for missing glyphs.

[font_sources.py](../scripts/font_sources.py) enlarges Erewhon donors by
`100/94` at unchanged 1000 units per em. This is a source-size normalization
applied to the whole donor, including superiors and delimiters, rather than
a fit calculated separately for each glyph. Utopia does not take this path.
The pinned donors and the outline/metric tests are the basis for retaining
this factor when updating sources; a replacement font requires rechecking it.

The [Erewhon documentation](https://mirrors.mit.edu/CTAN/fonts/erewhon/doc/erewhon-doc.pdf)
documents a 6% reduction from Heuristica, which matched old Utopia, to commercial
UtopiaStd size. The pinned Erewhon Math source documents scaling Fourier designs
to 94% to match Erewhon text; its letters and digits derive from Erewhon.
See the [Math user's guide](https://tug.ctan.org/fonts/erewhon-math/Erewhon-Math.pdf).
All sources use 1000 units/em. Utopia's `H` height is 692 units; Erewhon's is 650,
which becomes 691.49 after normalization. The inverse restores the size
convention while retaining donor rounding, design changes, and spacing choices.

Donor CFF subroutines are expanded before transformation. Coordinates and hint
edges scale, ghost-hint sentinels remain literal, and BlueScale is divided by
the factor. Integer OpenType metrics are rounded; explicit CFF widths are
made consistent with the resulting advances. Separate CFF font dictionaries
preserve the donors' hint environments. The Italic tabular oldstyle zero's
known 498-unit advance is corrected to 500 before scaling.

The recipe widens Utopia's word space by one fifth: 225 to 270 units in
Regular and Italic, 210 to 252 in Bold and BoldItalic. Regular oldstyle figure
shifts live in `OLDSTYLE_SHIFTS`; proportional-figure positioning allowances
and pair exceptions live in `FIGURE_SPACING` and `FIGURE_KERNS`. The latter
change positioning, not advances, and leave tabular figures unkerned.

Character-map collisions keep the higher-priority source; conflicting Math
glyph identities receive separate names. Supplementary characters receive
format-12 Unicode mappings. Math substitutions and relevant pair positioning
are imported, but no MATH table is added: this is a text family, not an
extensible equation font.

### Spacing rationale

XeTeX takes a font's interword glue from its space glyph: the stretch is half
the advance and the shrink a third. The Utopia recipe widens the space advance
by a fifth when it assembles the font (225 to 270 units in Regular and Italic,
210 to 252 in the bold faces), which gives Utopia's narrow word space about
0.27 em, 0.135 em, and 0.09 em at the same proportions. The Valkyrie recipe
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

## Print and web consumers

The image installs OLEBFont and its paired Greek fonts under
`/usr/local/share/fonts`; Ezra SIL supplies Hebrew. Each OLEBFont face has a
generated `.glyphs.csv` sidecar recording source glyphs, mappings, scale,
vertical translation and metrics. Preserve embedded notices and the notice
files copied by the assembler when changing the recipe.

[config/layout.ini](../config/layout.ini) selects proportional oldstyle
figures with `onum` and `pnum` on all four body faces.
[ptxprint-mods.sty](../config/ptxprint-mods.sty) selects `sups` for verse
figures, note origins, and callers, and `smcp`/`c2sc` for running heads.
The footer disables those small-cap features for its folio. Chapter labels
select OLEBFont directly with lining figures. The large chapter numeral uses
the installed face selected by `typeface.chapter_face`, again with `lnum`
and `pnum`, through the generated `c` style in
[project.py](../src/bible/project.py). Its selection uses the installed Greek
family's pairing and fails if the selected file is absent.

For Valkyrie, the chapter face is copied unchanged from
`newpx/opentype/TeXGyrePagellaX-Regular.otf`, alongside the package's README
and manifest. It is distinct from the `npxsups` superior donor. Its embedded notice names the GUST Font License; the package README also identifies LPPL material. These are not OFL fonts. Its bytes enter
every book's page-fill cache key. PDF verification checks for its PostScript
name along with the expected text and quotation families.

The TeX configuration enables `\XeTeXgenerateactualtext=1` so alternate
glyphs retain their input Unicode for copying and searching.
[web.py](../src/bible/web.py) exports complete WOFF files and CSS declarations
from the shared installed faces. The separate chapter numeral face is
print-only and excluded from that list.

## Checking a change

`make test-fonts` runs [tests/test_olebfont.py](../tests/test_olebfont.py):
recipe-specific outline, metric, hint, and lookup checks; shared shaping and
character-coverage checks; and byte-for-byte reconstruction of the installed
fonts and sidecars. `make font-specimen` produces
`dist/olebfont-specimen.pdf`. The full `make test` also runs the TeX regressions.
Run these after `make bootstrap` has rebuilt the changed image. The Utopia regressions compare serialized outlines and metrics with independently transformed donors. Normalized Erewhon basic Latin bounds agree with Utopia within 1.1 units in Regular, Italic, and BoldItalic, and advances within one unit; Bold retains Erewhon's deliberate widening. Valkyrie checks require original glyphs, metrics, lookups, and notices to survive unchanged and added superiors to match their measured donor transform.

For source-glyph inspection, run this inside the toolchain container:

```sh
python /work/scripts/inventory_fonts.py --utopia /opt/utopia \
  --archives /opt/sources --output /work/build/font-inventory
```

Font metrics and feature changes can alter wrapping throughout the book.
Follow the sample and full-PDF inspection procedure in
[AGENTS.md](../AGENTS.md); text equality alone cannot verify the resulting
pages. Generated fonts, reports, and build output remain disposable.
