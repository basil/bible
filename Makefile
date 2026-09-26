UIDGID := $(shell id -u):$(shell id -g)
# Run as the invoking uid/gid so that files written into the bind mount
# are not owned by root. -T and --interactive=false keep the terminal
# detached, as with plain docker run: otherwise stderr merges into stdout
# and a backgrounded make stops on terminal access. -f skips any
# compose.override.yaml or COMPOSE_FILE that provenance would not record.
COMPOSE := docker compose -f compose.yaml
TOOLCHAIN := $(COMPOSE) run --rm -T --interactive=false --user $(UIDGID) toolchain
PIPELINE := $(TOOLCHAIN) python3 -m bible
.PHONY: bootstrap validate notes-review test test-python test-tex test-tex-save sample pdf clean
bootstrap:
	$(COMPOSE) build --pull
validate:
	$(PIPELINE) validate
notes-review:
	$(PIPELINE) notes-review
test: test-python test-tex
test-python:
	$(TOOLCHAIN) python3 -m pytest $(PYTEST_ARGS)
test-tex:
	$(TOOLCHAIN) l3build check
test-tex-save:
	$(TOOLCHAIN) l3build save protrusion
sample:
	$(PIPELINE) sample
pdf:
	$(PIPELINE) pdf
clean:
	rm -rf build dist