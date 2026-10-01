# ClauseGuard Eval Harness

Status: **v2, five branches, runnable end-to-end.** 30 scenarios across 5
tiers; the production prompt, tool schemas, playbook retrieval and schema
validator are imported, not mirrored. `make eval-small` (~$1) and
`make eval` (~$15-25) are the two entry points; `make regression` gates CI.

## What this measures

The June 2026 question was *does the two-tool agentic loop beat a
single-prompt baseline?* The answer was "equivalent in aggregate, opposite
per tier": the loop won on severity tiering (+10.7pp F1) and lost on
ambiguous clauses (-13.0pp). Two things were built from that finding and
this harness measures both:

1. **Conditional routing** (`backend/router.py`): a rule-plus-cheap-model
   pre-classifier sends "which tier?" contract pairs to the agentic loop
   and "is this even a conflict?" pairs to the single prompt.
2. **Playbook retrieval** (`backend/playbook.py`): a third tool the agent
   consults per topic before assigning a tier or drafting resolution
   language, and inline playbook context for the single prompt.

So the harness now runs five branches on every scenario:

| Branch | What it is |
|---|---|
| `full` | the two-tool agentic loop as evaluated in June 2026 (no playbook) |
| `stripped` | one call, clauses inline, no tools (June 2026 baseline) |
| `full_rag` | the agentic loop with `lookup_playbook` (production "agentic") |
| `stripped_rag` | one call with playbook entries pre-retrieved inline (production "single") |
| `routed` | the router picks `full_rag` or `stripped_rag` per contract pair |

...against 30 gold scenarios across 5 tiers:

| Tier | Count | Purpose |
|---|---|---|
| `clear_conflict` | 7 | Direct contradiction: flag with high precision |
| `clear_no_conflict` | 6 | Different wording, same substance: do NOT flag |
| `ambiguous` | 6 | Defensible to flag or not |
| `severity_tiering` | 5 | Conflict is obvious; the right risk tier is the test |
| `adversarial` | 6 | Prompt injection in clause text and headers, negation traps, missing-context refs |

...and scores five metric families: precision/recall/F1 on conflict detection,
risk-tier accuracy (strict + lenient), favor accuracy (strict + lenient),
false-positive rate on no-conflict scenarios, and total-count calibration.

The report also carries, per run: run-to-run variance (mean per-scenario F1
range across reps, so a lift smaller than the band is read as noise), the
routing decisions per tier, playbook lookups per run, and the number of
schema-repair rounds the production validator forced.

## What it does NOT measure

- PDF parsing: scenarios pre-supply clause arrays, bypassing PyMuPDF and OCR.
  `tests/test_backend.py` covers extraction on real PDFs.
- Resolution-language quality against attorney labels. The resolution judge
  is calibrated separately against 12 hand-labelled cases
  (`make judge-calibrate`, results in `reports/judge_calibration.json`);
  the labels are the author's, not a lawyer's.
- Jurisdiction-specific reasoning: the governing-law tag is context, not doctrine.

See `RUBRIC.md` for what counts as a conflict and the scoring rules.

## Layout

```
eval/
├── README.md               # this file
├── RUBRIC.md               # committed before scenarios; rules quoted from the production prompt
├── schemas.py              # Scenario / ScenarioResult / BranchMetrics / ABLiftResult (5 branches)
├── prompts.py              # imports config.SYSTEM_PROMPT; stripped baseline prompt
├── runners.py              # the five branch runners + CLI
├── scorers.py              # deterministic scorers, macro-averaged per tier
├── rubric_audit.py         # topic canonicalisation shared with backend.router
├── instrumentation.py      # cost + latency traces
├── orchestrator.py         # run, render, save
├── regression_check.py     # CI gate against baseline.json
├── judge_calibration.json  # 12 labelled resolutions
├── judge_calibrate.py      # measures the judge against the labels
├── baseline.json           # frozen F1 floors from the last full run
├── scenarios/              # 30 gold scenarios
└── reports/                # run_*.md + latest_run.json
```

## Running

```bash
make eval-small                                   # 5 scenarios x 5 branches x 1 rep
make eval                                         # 30 x 5 x 3
python -m eval.runners --mode full --branches routed,stripped --reps 2
make regression                                   # compare latest_run.json to baseline.json
make baseline                                     # freeze the latest run as the new floor
```

CI runs `eval-smoke` (routed + stripped on the 5-scenario set) on pushes to
`main` when the `ANTHROPIC_API_KEY` secret is set, then the regression gate.
