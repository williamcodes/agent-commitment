PY ?= /private/tmp/acx-venv/bin/python
.PHONY: run process analyze site all serve
run:
	ASDF_PYTHON_VERSION=3.12.12 $(PY) experiment/run_experiment.py --tasks all --arms ctx-tempt,ctx-evidence,fresh-tempt,fresh-evidence --reps 2 --concurrency 6
	ASDF_PYTHON_VERSION=3.12.12 $(PY) experiment/run_experiment.py --tasks all --arms ctx-strong --reps 1 --concurrency 5
hangman:
	ACX_MODEL=claude-sonnet-5 $(PY) experiment/hangman/run_hangman.py --games 12 --concurrency 4
	ACX_MODEL=claude-sonnet-5 $(PY) experiment/hangman/run_couplet.py --trials 12 --concurrency 4
	$(PY) experiment/hangman/score_hangman.py
process:
	$(PY) experiment/process.py
analyze:
	$(PY) experiment/analyze.py
	$(PY) experiment/carriers.py
site:
	$(PY) experiment/build_site.py
all: process analyze site
serve:
	cd site && $(PY) -m http.server 8765
