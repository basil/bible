IMAGE := brenton-kjv-bible:local
DOCKER_RUN = docker run --rm --user $$(id -u):$$(id -g) -e HOME=/tmp/home -v "$(CURDIR):/work" $(IMAGE)
.PHONY: bootstrap validate sample pdf check check-protrusion clean
bootstrap:
	docker build --pull -t $(IMAGE) .
validate:
	python3 scripts/pipeline.py validate
sample:
	$(DOCKER_RUN) sample
pdf:
	$(DOCKER_RUN) pdf
check: check-protrusion
	$(DOCKER_RUN) check
check-protrusion:
	mkdir -p build/protrusion
	docker run --rm --user $$(id -u):$$(id -g) -e HOME=/tmp/home -v "$(CURDIR):/work" --entrypoint xelatex $(IMAGE) -interaction=nonstopmode -halt-on-error -output-directory=build/protrusion scripts/check-protrusion.tex
clean:
	rm -rf build dist