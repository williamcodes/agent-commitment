PY ?= /private/tmp/acx-venv/bin/python
.PHONY: run process analyze site all serve
run:
	$(PY) experiment/run_experiment.py --tasks all --arms all --reps 2 --concurrency 6
process:
	$(PY) experiment/process.py
analyze:
	$(PY) experiment/analyze.py
site:
	$(PY) experiment/build_site.py
all: process analyze site
serve:
	cd site && $(PY) -m http.server 8765
