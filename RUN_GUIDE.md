# ClauseGuard, Run Guide

Operational guide: setup, demo flow, configuration, and troubleshooting. For project framing and design rationale, see the [README](./README.md).

---

## What You're Running

| Component | What it does | Port |
|---|---|---|
| FastAPI backend | Runs the Claude agent, handles file uploads | 8000 |
| React frontend | Upload UI + results dashboard | 3000 |

You need **two terminals open**, one for the backend, one for the frontend.

---

## Prerequisites

| Tool | Check | Install |
|---|---|---|
| Python 3.10+ | `python3 --version` | python.org |
| Node.js 18+ | `node --version` | nodejs.org |
| npm | `npm --version` | comes with Node |
| Anthropic API key |  | console.anthropic.com |

---

## Step 1, Get your API key into the project

```bash
cd clauseguard
cp .env.example .env
```

Open `.env` and replace `your_api_key_here` with your actual key:

```
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxx
```

---

## Step 2, Set up the Python backend

```bash
# From the clauseguard/ folder:

python3 -m venv venv

# Activate it:
source venv/bin/activate          # Mac / Linux
# OR
venv\Scripts\activate             # Windows

# Install dependencies:
pip install -r requirements.txt
```

---

## Step 3, Start the backend (Terminal 1)

```bash
# Make sure you're in clauseguard/ with venv activated
uvicorn backend.main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

Leave this terminal running.

---

## Step 4, Set up and start the frontend (Terminal 2)

```bash
cd clauseguard/frontend
npm install
npm run dev
```

You should see:
```
  VITE v5.x  ready in XXX ms
  ➜  Local:   http://localhost:3000/
```

Your browser should open automatically. If not, go to **http://localhost:3000**.

---

## Step 5, Run the demo

1. The app opens showing two upload zones
2. Upload `sample_contracts/company_standard_terms.pdf` on the left
3. Upload `sample_contracts/vendor_proposed_terms.pdf` on the right
4. Click **Analyze Contracts →**
5. Watch the progress bar as the agent calls each tool
6. The full redline brief appears with all conflicts ranked by risk

---

## Configuration

All tuneable settings live in `config.py`:

| Setting | Default | Override |
|---|---|---|
| Model | `claude-sonnet-5` | Set `CLAUSEGUARD_MODEL` env var |
| Max output tokens | `32000` | Edit `MAX_TOKENS` in `config.py` |
| Max file size | `10MB` | Edit `MAX_FILE_SIZE` in `config.py` |
| Max clauses per contract | `120` | Edit `MAX_CLAUSES` in `config.py` |

To use a different model without editing code:
```bash
CLAUSEGUARD_MODEL=claude-opus-5 uvicorn backend.main:app --reload --port 8000
```

---

## Troubleshooting

**Backend won't start:**
```bash
# Make sure venv is activated, you should see (venv) in your prompt
# Then try:
pip install -r requirements.txt --force-reinstall
```

**"ANTHROPIC_API_KEY not found" error:**
```bash
# Check your .env file exists and has no spaces around the = sign:
cat .env
# Should show: ANTHROPIC_API_KEY=sk-ant-...
```

**Frontend can't connect to backend (CORS error):**
```bash
# Make sure backend is running on port 8000, not 8001 or another port
# Check Terminal 1 shows: Uvicorn running on http://0.0.0.0:8000
```

**"File too large" error:**
- PDFs must be under 10MB
- If testing with large contracts, increase `MAX_FILE_SIZE` in `config.py`

**Analysis returns no conflicts:**
- This can happen if the PDFs are scanned images (not text-based)
- The sample contracts included are text-based and will always produce results
- If testing with your own PDFs, make sure they are text-searchable

**"Contract has N sections, only the first 120 were analyzed" warning:**
- The agent caps extraction at 120 clauses per contract for token efficiency
- You'll see this warning in the progress bar if your contract is very long
- Increase `MAX_CLAUSES` in `config.py` if you need full coverage

**npm install fails:**
```bash
# Try clearing npm cache:
npm cache clean --force
npm install
```

---

## Regenerating the presentation (if needed)

```bash
# From clauseguard/ folder:
node scripts/build_presentation.js
```

Requires `pptxgenjs` globally installed:
```bash
npm install -g pptxgenjs
```

---


## Docker (v0.3)

One image serves the API and the built UI on port 8000:

```bash
docker build -t clauseguard .
docker run -p 8000:8000 -e CLAUSEGUARD_DEMO=1 clauseguard          # replay demo/sample_trace.json, no key
docker run -p 8000:8000 --env-file .env clauseguard                # live analysis
```

`docker compose up` does the same with `logs/` mounted so the audit log survives restarts.

## v0.3 runtime flags

| Flag | Default | Effect |
|---|---|---|
| `CLAUSEGUARD_ROUTING` | `agentic` | `agentic` (eval winner) or `single` force one architecture; `auto` routes per contract pair (rule pre-router + Haiku classifier) |
| `CLAUSEGUARD_JUDGE` | `1` | second-pass review of every suggested resolution (Haiku) |
| `CLAUSEGUARD_PLAYBOOK` | `1` | `lookup_playbook` tool / inline playbook context |
| `CLAUSEGUARD_REDACT` | `0` | replace emails, phones, SSNs, cards, IBANs with stable tokens before analysis |
| `CLAUSEGUARD_OCR` | `0` | OCR scanned pages with Tesseract (`TESSERACT_CMD` if not on PATH) |
| `CLAUSEGUARD_TOKEN_CEILING` | `250000` | abort an analysis past this many tokens |
| `CLAUSEGUARD_DEMO` | `0` | replay the recorded analysis; uploads disabled |
| `CLAUSEGUARD_API_KEY` | unset | bearer token required on `/upload` and `/analyze` when set |

The UI shows the route decision, judge verdicts and a trace footer (calls, cost, latency, cache reads) for every analysis; `/health` reports whether `logs/audit.jsonl` still verifies.
