# ClauseGuard dev + eval targets. Mirrors the ChainPilot Makefile convention.

PYTHON ?= python

.PHONY: install test lint eval-dry eval-small eval eval-report clean

install:
	$(PYTHON) -m pip install -U pip
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install pytest>=8.0 ruff>=0.6 pydantic>=2.8

test:
	$(PYTHON) -m pytest tests/ -q

lint:
	$(PYTHON) -m ruff check eval/ tests/

# Day 1 — status only, no API calls.
eval-dry:
	$(PYTHON) -m eval.runners --mode dry

# Day 8+ — 5 scenarios × 2 branches × 1 rep ≈ $0.50-$1.
eval-small:
	$(PYTHON) -m eval.runners --mode small

# Day 9+ — 30 scenarios × 2 branches × 3 reps ≈ $5-15.
eval:
	$(PYTHON) -m eval.runners --mode full

# Re-render the latest report from the JSON snapshot without re-running LLMs.
eval-report:
	$(PYTHON) -c "from eval.orchestrator import render_report; import json; \
	snapshot = json.load(open('eval/reports/latest_run.json')); \
	print(render_report(**snapshot))"

clean:
	rm -rf .pytest_cache __pycache__ */__pycache__ */*/__pycache__
