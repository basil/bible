-- l3build configuration for the TeX regression tests in tests/tex.
-- Run through `make test-tex`; the tests typeset nothing for distribution.
module = "bible"

testfiledir = "tests/tex"
-- Keep l3build's scratch directories apart from the pipeline's build/ outputs.
builddir = "./build/l3build"

-- PTXprint typesets with XeTeX, so only that engine is checked.
checkengines = {"xetex"}
stdengine = "xetex"
checkruns = 1
-- Stop at the first TeX error: the log is only compared between \START and
-- \END, so an error while loading the preamble would otherwise pass.
checkopts = "-interaction=nonstopmode -halt-on-error"

-- There is no package to unpack: the tests read the live TeX customizations.
sourcefiles = {}
installfiles = {}
unpackfiles = {}
supportdir = "config"
checksuppfiles = {"ptxprint-mods.tex"}
