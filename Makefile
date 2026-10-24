UIDGID := $(shell id -u):$(shell id -g)
# Run as the invoking uid/gid so that files written into the bind mount
# are not owned by root. -T and --interactive=false keep the terminal
# detached, as with plain docker run: otherwise stderr merges into stdout
# and a backgrounded make stops on terminal access. -f prevents
# compose.override.yaml or COMPOSE_FILE from changing the build configuration.
COMPOSE := docker compose -f compose.yaml
TOOLCHAIN := $(COMPOSE) run --rm -T --interactive=false --user $(UIDGID) toolchain
DOCKERFMT := $(COMPOSE) run --rm -T --interactive=false --user $(UIDGID) dockerfmt
HADOLINT := $(COMPOSE) run --rm -T --interactive=true hadolint
PIPELINE := $(TOOLCHAIN) python3 -m bible
.PHONY: bootstrap validate review review-diff test test-python test-tex test-tex-save font-specimen sample pdf pdf-unfilled web site site-dev clean lint lint-fix
bootstrap:
	sh scripts/collect_valkyrie.sh
	$(COMPOSE) pull dockerfmt hadolint
	$(COMPOSE) build --pull
validate:
	$(PIPELINE) validate
review:
	$(PIPELINE) review
# What a change does to the edition: the review of BASE and of the working
# tree, and every line that differs between them, in build/review.diff.
BASE ?= origin/master
review-diff:
	rm -rf build/review-base
	git worktree prune
	git worktree add --quiet --detach build/review-base $(BASE)
	$(TOOLCHAIN) sh -c 'cd build/review-base && PYTHONPATH=src python3 -m bible review' \
		|| { echo "$(BASE) cannot write a review" >&2; exit 1; }
	$(PIPELINE) review
	diff -ru -x changes.diff build/review-base/build/review build/review > build/review.diff; test $$? -le 1
	git worktree remove --force build/review-base
	@echo "$$(grep -c '^diff \|^Only in ' build/review.diff) files differ from $(BASE): build/review.diff"
# The two suites are independent, and run side by side.
test:
	$(MAKE) --no-print-directory -j2 --output-sync=target test-python test-tex
test-python:
	$(TOOLCHAIN) python3 -m pytest -p xdist.plugin -n 2 --dist=loadscope $(PYTEST_ARGS)
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
	$(PIPELINE) pdf $(FILL_ARGS)
pdf-unfilled:
	$(PIPELINE) pdf-unfilled
web:
	$(PIPELINE) web
site: web
	npm --prefix site ci
	npm --prefix site run build
site-dev:
	npm --prefix site run dev
clean:
	rm -rf build dist site/.vitepress/dist site/.vitepress/cache site/.vitepress/.temp
# All Python code, excluding generated files and review worktrees.
lint:
	$(TOOLCHAIN) sh -c 'black --check src scripts tests && isort --check-only src scripts tests && mypy && mbake format --check Makefile'
	$(DOCKERFMT) -c -n Dockerfile
	$(HADOLINT) <Dockerfile
lint-fix:
	$(TOOLCHAIN) sh -c 'isort src scripts tests && black src scripts tests && mbake format Makefile'
	$(DOCKERFMT) -w -n Dockerfile