UIDGID := $(shell id -u):$(shell id -g)
# Run as the invoking uid/gid so that files written into the bind mount
# are not owned by root. -T and --interactive=false keep the terminal
# detached, as with plain docker run: otherwise stderr merges into stdout
# and a backgrounded make stops on terminal access. -f skips any
# compose.override.yaml or COMPOSE_FILE that provenance would not record.
COMPOSE := docker compose -f compose.yaml
TOOLCHAIN := $(COMPOSE) run --rm -T --interactive=false --user $(UIDGID) toolchain
PIPELINE := $(TOOLCHAIN) python3 scripts/pipeline.py
.PHONY: bootstrap validate sample pdf check check-protrusion clean
bootstrap:
	$(COMPOSE) build --pull
validate:
	$(PIPELINE) validate
sample:
	$(PIPELINE) sample
pdf:
	$(PIPELINE) pdf
check: check-protrusion
	$(PIPELINE) check
check-protrusion:
	mkdir -p build/protrusion
	$(TOOLCHAIN) xelatex -interaction=nonstopmode -halt-on-error -output-directory=build/protrusion scripts/check-protrusion.tex
clean:
	rm -rf build dist