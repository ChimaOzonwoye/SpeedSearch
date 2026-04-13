# SpeedSearch

**Contextual matching for university research.** A professor uploads a research
document; SpeedSearch parses it into discrete project opportunities with required
skills and difficulty. A student uploads a portfolio or development journey; the
app reads what they've *actually built* and scores each opportunity by
contextual fit — not keyword overlap. Every two days, professors get a one-click
email: is this project still open?

This is a local prototype: Flask + a local LLM via [Ollama](https://ollama.com).
No data leaves the machine.

## Why this is different

Traditional research/job boards list "Python, CSS, ML" and let students
self-select. SpeedSearch reads the *shape* of a project (e.g. "designing audit
trails for agents") and the *shape* of a student's work (e.g. "built a Chrome
extension that instruments a local LLM") and reasons about transfer.

## Quick start

Requires: Python 3.10+, macOS or Linux, ~4 GB free disk for the model.

```bash
git clone https://github.com/chimaozonwoye/speedsearch.git
cd speedsearch
./setup.sh     # installs python deps, Ollama, pulls llama3.2:3b
./run.sh       # starts the server at http://localhost:5000
```

Open http://localhost:5000 and either:

1. **As a professor** — upload a research-project PDF (or paste the text). The
   LLM extracts structured opportunities.
2. **As a student** — upload a portfolio PDF or paste your development journey
   with availability. You see a ranked list of matches with reasoning.
3. **Browse** — every opportunity across the platform.

## Configuration

`setup.sh` creates a `.env` you can edit:

- `OLLAMA_MODEL` — default `llama3.2:3b`. Swap in any Ollama model.
- `PING_DAYS` — how often to email professors (default `2`).
- `SMTP_*` — optional SMTP creds. If blank, pings are logged to the console
  instead of sent.

## How it works

- **PDF parsing** — PyMuPDF (`fitz`) extracts text from uploaded documents.
- **Extraction** — Ollama's `/api/chat` is called with a JSON schema so the
  LLM returns structured opportunities and portfolios.
- **Matching** — for each open opportunity, the LLM scores contextual fit
  against the student's extracted portfolio and explains the match.
- **Scheduler** — APScheduler fires every `PING_DAYS` days and emails every
  professor a YES/NO link to keep or close each opportunity.

## Files

```
app.py                Flask backend, LLM calls, scheduler
templates/index.html  SPA frontend (student / professor / browse tabs)
static/style.css      styling
static/app.js         fetch logic and rendering
setup.sh              install deps + Ollama + pull model
run.sh                launch server
requirements.txt      Python deps
```

## Roadmap

- Hosted version with managed LLM and FERPA-compliant storage.
- Calendar integration for interview scheduling.
- Verified student credentials tied to GitHub / university SSO.

## License

Licensed under the [GNU GPL v3](LICENSE). For commercial institutional
licenses (provosts, deans, research administrators), contact the team.

**Founders:** Aadharsh Sakkaravarthy, Ted Erdos, Ali Salama, Chima Ozonwoye.
