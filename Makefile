UIDGID := $(shell id -u):$(shell id -g)
# Run as the invoking uid/gid so that files written into the bind mount
# are not owned by root. -T and --interactive=false keep the terminal
# detached, as with plain docker run: otherwise stderr merges into stdout
# and a backgrounded make stops on terminal access. -f skips any
# compose.override.yaml or COMPOSE_FILE that provenance would not record.
COMPOSE := docker compose -f compose.yaml
TOOLCHAIN := $(COMPOSE) run --rm -T --interactive=false --user $(UIDGID) toolchain
PIPELINE := $(TOOLCHAIN) python3 -m bible
.PHONY: bootstrap validate notes-review alexandrinus-review seed-versification test test-python test-tex test-tex-save font-specimen sample pdf clean
bootstrap:
	$(COMPOSE) build --pull
validate:
	$(PIPELINE) validate
alexandrinus-review:
	$(PIPELINE) alexandrinus-review
notes-review:
	$(PIPELINE) notes-review
seed-versification:
	$(PIPELINE) seed-versification
test: test-python test-tex
test-python:
	$(TOOLCHAIN) python3 -m pytest $(PYTEST_ARGS)
test-tex:
	$(TOOLCHAIN) l3build check
test-tex-save:
	$(TOOLCHAIN) l3build save protrusion
# A visual proof of all four faces and native numeral/small-cap features.
font-specimen:
	$(TOOLCHAIN) sh -c 'mkdir -p build/font-specimen dist && xelatex -interaction=nonstopmode -halt-on-error -output-directory=build/font-specimen tests/tex/olebfont-specimen.tex && cp build/font-specimen/olebfont-specimen.pdf dist/'
sample:
	$(PIPELINE) sample
pdf:
	$(PIPELINE) pdf
clean:
	rm -rf build dist