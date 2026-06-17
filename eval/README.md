# ClauseGuard Eval Harness

Status: **Day 8 — runnable end-to-end**. 30 scenarios committed across 5
tiers. Runners (FULL + STRIPPED) implemented with mocked tools. 5 scorer
families implemented with deterministic tests. Orchestrator wires everything
together; `make eval-small` and `make eval` are executable. Day 9 is the
first paid run + completion-pack thread-through.

## What this measures

The headline question: *does ClauseGuard's two-tool agentic architecture
(extract → reason → redline) detect contract conflicts better than a
single-prompt baseline that sees both contracts at once?*

The eval runs an A/B between:

- **FULL branch** — production agent loop (mocked PDF extraction).
- **STRIPPED branch** — one LLM call with both clause arrays inline.

…against 30 gold scenarios across 5 tiers:

| Tier | Count | Purpose |
|---|---|---|
| `clear_conflict` | 7 | Direct contradiction — agent should flag with high precision |
| `clear_no_conflict` | 6 | Different wording, same substance — agent should NOT flag |
| `ambiguous` | 6 | Defensible to flag or not |
| `severity_tiering` | 5 | Conflict is obvious; right risk tier is the test |
| `adversarial` | 6 | Prompt injection in clause text, very long contracts, missing-context refs |

…and scores five metric families: precision/recall/F1 on conflict detection,
risk-tier accuracy (strict + lenient), favor accuracy (strict + lenient),
false-positive rate on no-conflict scenarios, and total-count calibration.

## What it does NOT measure

- PDF parsing — scenarios pre-supply clause arrays, bypassing PyMuPDF.
- Resolution-language quality — would need an LLM-as-judge harness with
  attorney calibration; deferred.
- Jurisdiction-specific case-law reasoning — the system is jurisdiction-blind
  by design.
- Production hardening (rate limits, retries, queueing) — orthogonal.

See `RUBRIC.md` for what counts as a conflict and the scoring rules. See
`../phase2/14_clauseguard_eval_scope_spec.md` for the full design rationale.

## Layout

```
eval/
├── README.md           # this file
├── RUBRIC.md           # committed Day 1, BEFORE scenarios
├── schemas.py          # Pydantic models — the contract between scenarios,
│                       # runners, and scorers
├── instrumentation.py  # CallTrace + cost arithmetic
├── rubric_audit.py     # programmatic encoding of RUBRIC.md §1-4
├── prompts.py          # mirrored production prompt + STRIPPED prompt
├── runners.py          # FULL + STRIPPED pipeline executors + CLI
├── scorers.py          # 5 scoring functions + aggregation + A/B lift
├── orchestrator.py     # Cartesian product runner + report renderer
├── scenarios/          # one *.json per scenario; lands Days 2-5
└── reports/            # one run_YYYYMMDD_HHMMSS.md per eval run
```

## Running the eval

```
make eval-dry     # status message only, no API calls
make eval-small   # 5 scenarios, 2 branches, 1 rep    ≈ $0.50-$1
make eval         # 30 scenarios, 2 branches, 3 reps  ≈ $5-15
```

Both `eval-small` and `eval` need `ANTHROPIC_API_KEY` in env. The CLI
pauses 3 seconds before spending any credits so you can Ctrl+C to abort.
Reports land in `eval/reports/run_YYYYMMDD_HHMMSS.md` with a sibling
`latest_run.json` snapshot for re-rendering.

The default `eval-small` scenario set is `clear_conflict_001`,
`clear_no_conflict_001`, `ambiguous_001`, `severity_tiering_003`, and
`adversarial_001` — spans all 5 tiers and includes the prompt-injection
scenario as the highest-value single test.

## Honest disclosures

1. **The eval bypasses PDF parsing.** Scenarios pre-supply clause arrays.
   Testing PDF robustness requires a separate harness.
2. **Synthetic mini-contracts, not real MSAs.** Each scenario has ~5-15
   clauses, not 80. Generalization to real legal documents is a known gap.
3. **The rubric encodes the production system prompt.** If `config.py`
   `SYSTEM_PROMPT` changes, the rubric must be re-verified — a
   drift-detection test in `tests/test_runners.py` will catch silent skew.
4. **Conflict matching is by topic + section overlap.** Imperfect — the
   agent might describe the same conflict with different wording or cite a
   parent section. Day 8's first run includes manual spot-checks.
5. **No LLM-as-judge.** Scorers are deterministic, by deliberate choice —
   LLM-as-judge introduces same-model bias when judge and system share a
   model family. Trades human-rater-agreement upside for zero same-model bias.
6. **Cost estimates assume Sonnet 4.6 pricing.** Verify before each full run.

## CI strategy

- `ci.yml` runs ruff + pytest on every push/PR. Zero LLM calls. <1 min, free.
- `eval.yml` is manual-trigger only (`workflow_dispatch`). Needs the
  `ANTHROPIC_API_KEY` GitHub secret. Uploads the markdown report as an
  artifact. Cost: $5-15.
