IMAGE := brenton-kjv-bible:local
DOCKER_RUN = docker run --rm --user $$(id -u):$$(id -g) -e HOME=/tmp/home -v "$(CURDIR):/work" $(IMAGE)
.PHONY: bootstrap validate sample pdf check clean
bootstrap:
	docker build --pull -t $(IMAGE) .
validate:
	python3 scripts/pipeline.py validate
sample:
	$(DOCKER_RUN) sample
pdf:
	$(DOCKER_RUN) pdf
check:
	$(DOCKER_RUN) check
clean:
	rm -rf build dist