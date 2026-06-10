# ClauseGuard, Contract Conflict Detector

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](./requirements.txt)
[![Model: claude-sonnet-4-6](https://img.shields.io/badge/Model-claude--sonnet--4--6-orange.svg)](./config.py)

A two-tool agentic system that ingests two contract PDFs, extracts up to 120 clauses from each, surfaces material conflicts side-by-side, and produces a risk-ranked redline brief with suggested compromise language. Built as a working FastAPI + React app with an SSE stream that shows tool calls happening live.

**[Run guide](./RUN_GUIDE.md)**

> **Status:** local prototype, runs end-to-end against the Anthropic API. No live deploy. *Decision-support for contract review, not a substitute for a lawyer.*

---

## The problem

A mid-market company receives a vendor's redlined Master Services Agreement at 4:47 PM on a Friday. The vendor wants a signature by Monday. Inside the MSA are 80+ clauses; the legal team's tracked-changes view shows where the language differs from the company's standard terms, but it does not tell counsel which differences are *material*, liability caps, indemnification scope, IP ownership, termination rights, versus which are stylistic.

The first hour of contract review is usually clause triage: which differences are dangerous, which are negotiable, which are noise. ClauseGuard automates that first hour into a redline brief a paralegal or junior attorney can hand to senior counsel.

It does **not** finalize the contract, draft the response, or replace legal review. The user-facing framing throughout this project is consistent: **triage tool for human review**, not autonomous negotiation.

---

## What this proves (AI Engineer signals)

| Signal | Where it shows up |
|---|---|
| **Agentic loop with tight tool surface** | Two tools, not ten, `extract_clauses()` and `generate_redline_brief()`. The agent decides clause-by-clause comparison in its own reasoning between the two tool calls; the tools handle parsing and structured output. See [`backend/tools.py`](./backend/tools.py). |
| **Streaming agent reasoning to the UI** | FastAPI SSE on `/analyze` streams each tool call as it happens. The React frontend shows `[Tool] extract_clauses(party_label=company)` → `[Tool] extract_clauses(party_label=vendor)` → `[Tool] generate_redline_brief(conflicts=[...])` live to the reviewer. |
| **Structured output contract enforced via prompt** | The system prompt mandates a 10-field JSON shape per conflict (`risk`, `topic`, `company_section`, `company_text`, `vendor_section`, `vendor_text`, `conflict_explanation`, `favor`, `resolution`, `id`). Output is rendered as structured cards, not raw markdown. |
| **Risk framework calibrated to legal practice** | 4-tier severity (CRITICAL / HIGH / MEDIUM / LOW) mapped to specific clause categories: CRITICAL covers liability, indemnification, IP, termination, governing law, arbitration; HIGH covers payment, penalties, confidentiality, exclusivity, auto-renewal. See [`config.py`](./config.py) `SYSTEM_PROMPT` for full taxonomy. |
| **HITL by design, not as afterthought** | The output deliverable is a redline brief for human counsel, never an executed amendment. The system surfaces the `favor` field per conflict, "company" vs "vendor", explicitly framed as *from the company's perspective*, with the suggested resolution as a starting point for negotiation, not a final answer. |
| **Defensive caps** | 120-clause cap per contract, 10 MB upload limit, 32K output token cap. Each is a configurable defense against runaway costs and adversarial inputs. |

---

## System at a glance

```
┌─────────────────────┐      ┌─────────────────────┐
│  Contract A (PDF)   │      │  Contract B (PDF)   │
│  company standard   │      │  vendor proposed    │
└──────────┬──────────┘      └──────────┬──────────┘
           │                            │
           └──────────────┬─────────────┘
                          ▼
              ┌───────────────────────┐
              │   /analyze endpoint   │  ← SSE stream to frontend
              │   (FastAPI)           │
              └───────────┬───────────┘
                          ▼
              ┌───────────────────────┐
              │  Agentic loop         │
              │  (Claude sonnet-4-6)  │
              └───────────┬───────────┘
                          │
       ┌──────────────────┴──────────────────┐
       ▼                                     ▼
┌──────────────────┐                  ┌──────────────────┐
│ extract_clauses  │  (called twice, │ extract_clauses  │
│   party=company  │   once per       │   party=vendor   │
└────────┬─────────┘   contract)      └────────┬─────────┘
         │                                     │
         └──────────────────┬──────────────────┘
                            ▼
              ┌───────────────────────┐
              │  Agent reasons over   │
              │  both clause lists,   │
              │  identifies conflicts │
              └───────────┬───────────┘
                          ▼
              ┌───────────────────────────────────┐
              │  generate_redline_brief(conflicts)│
              │  → 10-field JSON per conflict     │
              └───────────┬───────────────────────┘
                          ▼
              ┌───────────────────────┐
              │  Risk-ranked redline  │
              │  cards in React UI    │
              │  CRITICAL → LOW       │
              └───────────────────────┘
```

---

## Honest disclosure

Things this project is NOT, that an interviewer should know:

1. **No eval harness.** Conflict quality is judged by inspection on the two demo contracts (10 hand-crafted conflicts in `sample_contracts/`). No held-out set of gold contract pairs with known-correct conflict lists. This is the single highest-value Phase 2 upgrade, without it, "the agent flagged 12 conflicts" is not a measurable claim about precision or recall.
2. **Hallucination risk on resolution language.** The agent suggests compromise language for every flagged conflict. That language could be wrong, ambiguous, or contractually disadvantageous in ways that look fine to a non-lawyer reader. The UI presents resolutions as *starting points for counsel*, but a careless user could treat them as final. Production hardening would require a separate review step (LLM-as-judge or rule-based) before resolutions surface.
3. **The "expert contract attorney" system prompt is a persona, not a substitute.** Framing Claude as an attorney in the prompt does not give Claude legal training or jurisdiction-specific case-law knowledge. The system prompt is a way to bias the model toward legal-framing language; it is not a credential.
4. **PDF text only, no OCR.** Scanned image-only contracts produce zero clauses. Real legal workflows routinely involve scanned exhibits. OCR (Tesseract or a hosted service) is on the roadmap.
5. **Jurisdiction-blind.** "Governing law" is one of the CRITICAL-risk categories the system identifies, but the system does not actually reason about how the conflict resolves under (say) Delaware vs New York law. It surfaces the difference; it does not resolve it.
6. **Two demo contracts only.** All current quality evidence comes from `sample_contracts/company_standard_terms.pdf` and `vendor_proposed_terms.pdf`, a hand-crafted demo with 10 deliberate conflicts. Generalization to real M&A or commercial paper is untested.
7. **No live deploy.** Standing this up publicly would require an Anthropic API key in the environment and meaningful safeguards against people uploading actual sensitive contracts. Deferred until the eval harness is built.

---

## What I'd want before deploying this for real

1. **Gold-contract eval set.** 30–50 real contract pairs (sanitized) with known conflicts. Score on conflict precision (was every flagged conflict real?), recall (did we miss any?), and severity-classification accuracy.
2. **LLM-as-judge on resolutions.** Second-pass model reviews suggested resolution language for soundness, ambiguity, and one-sidedness. Resolutions that fail the second-pass review get hidden or flagged.
3. **OCR pre-stage** for scanned PDFs, Tesseract for free-tier, a hosted OCR for accuracy. Detection step decides whether to OCR.
4. **Jurisdiction tags.** Let the user select `governing_law=DE` (or whatever); the agent gets that as context and tailors the conflict analysis to actually-applicable doctrine.
5. **PII / sensitive-clause redaction** before clauses leave the user's environment. A real legal workflow cannot send contract text to a third-party API without an enterprise agreement; a self-hosted deployment is the bigger blocker than the code itself.
6. **Audit log immutability.** Every analyzed contract pair, the conflicts surfaced, and the resolution language, append-only, with reviewer identity attached.
7. **Cost ceiling per analysis.** Hard cap on tokens × LLM calls per contract pair, with a UI warning when a contract approaches the 120-clause cap.

---

## Failure modes

- **Surface-similar clauses misclassified as non-conflicts.** Two clauses that both say "30 days notice" but apply to different events (termination vs assignment) read as compatible on surface and may be missed. The agent's reasoning step is the only defense; it's also the unreliable one.
- **Long contracts hit the 120-clause cap silently.** The UI surfaces a warning, but a busy user could miss it and assume full coverage. A larger contract with truncated extraction will under-report conflicts.
- **Adversarial PDFs.** Multi-column layouts, watermarks across clauses, and inline footnotes all confuse the extraction. The agent does not know that extraction was poor; it analyzes whatever it got.
- **Hallucinated section references.** The agent quotes section numbers (e.g., "Section 7.3"). If the source PDF text is garbled, the section references can be invented. Mitigation: every quote is rendered alongside the raw extracted text in the UI so a reviewer can verify.
- **Single-side framing of `favor`.** The system always evaluates conflicts from the company's perspective. Vendor-side review using this tool would systematically misframe the conflicts.

---

## Quick start

Full operational guide (troubleshooting, presentation script, configuration tuning) is in [RUN_GUIDE.md](./RUN_GUIDE.md). Compact version:

```bash
# 1. API key
cp .env.example .env
# Edit .env: ANTHROPIC_API_KEY=sk-ant-...

# 2. Backend (Terminal 1)
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000

# 3. Frontend (Terminal 2)
cd frontend
npm install && npm run dev
# → http://localhost:3000
```

Upload `sample_contracts/company_standard_terms.pdf` on the left, `sample_contracts/vendor_proposed_terms.pdf` on the right, click **Analyze Contracts**, and watch the SSE stream of tool calls in Terminal 1 while the redline brief assembles in the UI.

---

## Repo structure

```
clauseguard/
├── README.md                          ← you are here (portfolio front door)
├── RUN_GUIDE.md                       ← operational guide (setup, demo, troubleshooting, config)
├── LICENSE                            ← MIT
├── config.py                          ← MODEL · MAX_TOKENS · MAX_CLAUSES · SYSTEM_PROMPT
├── requirements.txt
├── backend/
│   ├── tools.py                       ← extract_clauses + generate_redline_brief schemas
│   ├── agent.py                       ← agentic loop (CLI entry point)
│   ├── main.py                        ← FastAPI: /upload + /analyze SSE
│   └── report.py                      ← redline brief rendering
├── frontend/src/
│   ├── App.jsx                        ← upload UI, SSE consumer, redline cards
│   └── App.css                        ← legal-tech design system
├── sample_contracts/
│   ├── company_standard_terms.pdf     ← Contract A with 10 deliberate conflicts
│   └── vendor_proposed_terms.pdf      ← Contract B
└── scripts/                           ← presentation rebuild script
```

---

## License

[MIT](./LICENSE). The two sample contracts in `sample_contracts/` are fabricated demonstration documents, no real business agreement, vendor, or company is represented.

---

## Author

Mamadou Bassirou Diallo · MS Business Analytics & AI, UT Dallas · [LinkedIn](https://www.linkedin.com/in/mamadou9905) · [GitHub](https://github.com/bass990)

