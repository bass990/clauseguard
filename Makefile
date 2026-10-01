# ClauseGuard dev, eval and container targets.

PYTHON ?= python

.PHONY: install test lint run eval-dry eval-small eval eval-report regression baseline \
        judge-calibrate record-demo docker-build docker-run docker-demo clean

install:
	$(PYTHON) -m pip install -U pip
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install "pytest>=8.0" "ruff>=0.6" "pydantic>=2.8" httpx pytesseract Pillow
	cd frontend && npm ci --no-audit --no-fund

test:
	$(PYTHON) -m pytest tests/ -q

lint:
	$(PYTHON) -m ruff check backend eval tests

run:
	$(PYTHON) -m uvicorn backend.main:app --reload --port 8000

# ---- eval -----------------------------------------------------------------
eval-dry:
	$(PYTHON) -m eval.runners --mode dry

# 5 scenarios x 5 branches x 1 rep, ~$1.
eval-small:
	$(PYTHON) -m eval.runners --mode small

# 30 scenarios x 5 branches x 3 reps, ~$15-25.
eval:
	$(PYTHON) -m eval.runners --mode full

eval-report:
	$(PYTHON) -c "from eval.orchestrator import render_report; import json; \
	snapshot = json.load(open('eval/reports/latest_run.json')); \
	print(render_report(**snapshot))"

regression:
	$(PYTHON) -m eval.regression_check

baseline:
	$(PYTHON) -m eval.regression_check --write-baseline

# Agreement of the resolution judge with hand-labelled verdicts, ~$0.05.
judge-calibrate:
	$(PYTHON) -m eval.judge_calibrate

# Re-record demo/sample_trace.json from a real run, ~$0.25.
record-demo:
	$(PYTHON) scripts/record_demo.py

# ---- containers -----------------------------------------------------------
docker-build:
	docker build -t clauseguard .

docker-run:
	docker run --rm -p 8000:8000 --env-file .env clauseguard

docker-demo:
	docker run --rm -p 8000:8000 -e CLAUSEGUARD_DEMO=1 clauseguard

clean:
	rm -rf .pytest_cache .ruff_cache __pycache__ */__pycache__ */*/__pycache__ frontend/dist
