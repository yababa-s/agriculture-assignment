# AgriAgent (Team 34, Andaman & Nicobar). Every target is also documented as a plain command in the README,
# so Windows users without `make` can copy the command instead.
PY ?= .venv/bin/python
ifeq ($(OS),Windows_NT)
PY = .venv/Scripts/python
endif

.PHONY: help setup fetch test quickstart demo app figures eval reproduce lint backup clean

help:            ## list targets
	@grep -E '^[a-z-]+:.*##' Makefile | awk -F':.*## ' '{printf "  make %-11s %s\n", $$1, $$2}'

setup:           ## create .venv and install requirements
	python3 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt
	$(PY) -m pip install -e . --no-deps

fetch:           ## download database, adapter and corpus from the release (checksums verified)
	$(PY) scripts/fetch_artifacts.py

test:            ## run the test suite (no model needed)
	$(PY) -m pytest

quickstart:      ## status, three sample questions, one live extraction (no model needed)
	$(PY) -m agri.cli status
	$(PY) scripts/ask.py --no-llm "Which agri zone produced the most paddy in 2025-26?"
	$(PY) scripts/ask.py --no-llm "How did paddy production in the UT change from 2019-20 to 2025-26?"
	$(PY) scripts/ask.py --no-llm --show-source --no-open "Which source and page did the 2025-26 coconut production figure for A&N come from?"
	$(PY) scripts/run_pipeline.py --docs D02 --replace --no-llm --db db/quickstart_test.sqlite

demo:            ## the 10 live demo queries with the model planner (Apple Silicon or LLM_BACKEND=hf)
	$(PY) scripts/ask.py --demo

app:             ## web app on http://localhost:8501
	$(PY) -m streamlit run app/streamlit_app.py

figures:         ## rebuild all figures and animations
	$(PY) scripts/make_figures.py

eval:            ## field-level and query evaluation (rules); LLM evaluations: see README
	$(PY) scripts/eval_fields.py
	$(PY) scripts/eval_queries.py --label rules --planner rules
	$(PY) scripts/eval_queries.py --set test --label rules --planner rules

reproduce:       ## rebuild every artifact from the raw corpus (~2.5 h on an M-series Mac)
	bash scripts/reproduce.sh

lint:            ## static checks
	$(PY) -m ruff check agri scripts app tests

backup:          ## back up the database into backups/
	$(PY) -m agri.cli backup

clean:           ## remove caches and generated test databases
	rm -rf .pytest_cache .ruff_cache db/quickstart_test.sqlite outputs/provenance
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
