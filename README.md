# SpeedSearch

**Indeed for university research, with contextual matching instead of
keyword overlap.** A student installs the SpeedSearch Chrome extension
and runs a small local backend. When they visit any university
research or faculty page, the extension reads it, a local LLM extracts
the discrete opportunities, and each one is ranked against the
student's own portfolio by the *shape* of the work rather than a bag
of skills.

No data leaves the machine. The extension talks only to the local
backend at `http://localhost:5000`, which talks only to Ollama at
`http://localhost:11434`.

## How it works

```
  Chrome tab  ->  content.js (scrape)  ->  background.js  ->  localhost:5000
                                                                   |
                                                                   v
                                                              Ollama (local LLM)
                                                                   |
                                       +---------------------------+
                                       |
                                       v
          1. Extract opportunity cards from the page
          2. Score each card vs. the student's saved portfolio
          3. Persist to SQLite
          4. Every 2 days, email each professor asking whether
             the listed opportunity is still open (one-click YES / NO)
```

The match prompt is designed to reward **transferable depth**: a student
whose portfolio shows they built a browser extension from scratch will
score high on any project that calls for browser-API work, even if the
application domains differ. A student who only *listed* a skill will
not.

## Requirements

- Python 3.10 or newer
- Google Chrome (or any Chromium-based browser that supports MV3
  unpacked extensions)
- About 4 GB of free disk for the default local model
- macOS or Linux (Windows via WSL works too)

## Install and run

```bash
git clone https://github.com/ChimaOzonwoye/speedsearch.git
cd speedsearch
./setup.sh      # creates venv, installs deps, installs Ollama, pulls llama3.2:3b
./run.sh        # starts Ollama (if needed) and the Flask backend on :5000
```

Then load the extension:

1. Open `chrome://extensions` in Chrome.
2. Toggle **Developer mode** on (top-right).
3. Click **Load unpacked** and choose the `extension/` folder in this
   repo.
4. Pin the SpeedSearch icon to the toolbar.
5. Click the icon, open **Edit your profile**, and either paste a
   description of your work or upload a portfolio PDF. The local model
   extracts what you have actually built; that becomes the input to
   every future match.

From that point on, open any research or faculty page at your
university and click the SpeedSearch icon. The badge shows the top
match score for the page; the popup shows each opportunity, the
difficulty, the required capabilities, and a one-sentence reason for
the score.

## Configuration

`setup.sh` writes a `.env` file you can edit:

| Variable       | Purpose                                                 |
|----------------|---------------------------------------------------------|
| `OLLAMA_MODEL` | Which Ollama model to use. Default `llama3.2:3b`.      |
| `PING_DAYS`    | How often to email professors. Default `2`.             |
| `SMTP_*`       | Optional SMTP credentials. Leave blank to log-only.     |
| `APP_HOST`     | Base URL the YES / NO email links point at.             |

Larger models (`llama3.1:8b`, `qwen2.5:7b`) give noticeably better
match reasoning on machines with enough RAM.

## Project layout

```
app.py                Flask backend, Ollama calls, SQLite, scheduler
extension/
  manifest.json       MV3 manifest
  background.js       service worker, per-tab state, badge
  content.js          page scraper + research-page heuristic
  popup.html / .js    toolbar popup that shows matches
  options.html / .js  profile setup and backend selection
  icons/              toolbar icons
setup.sh              installs dependencies and Ollama
run.sh                starts Ollama and the backend
requirements.txt      Python dependencies
LICENSE               GNU GPL v3
```

## License

SpeedSearch is released under the [GNU General Public License,
version 3](LICENSE). The text of the GPL itself may not be modified.

Every source file in this repository carries the standard GPL v3
header. Anyone is free to study, modify, and redistribute SpeedSearch
under the terms of the GPL; any derivative work must be released under
the same license and with source available.

If you want to use SpeedSearch inside a proprietary product, or you
need a license without GPL-style obligations (for example an
institutional deployment that needs vendor indemnification), contact
the founding team directly. SpeedSearch is offered under dual
licensing: free for the GPL-compliant open-source community, and
available under separate commercial terms for institutions.

**Founders:** Aadharsh Sakkaravarthy, Ted Erdos, Ali Salama,
Chima Ozonwoye.

**Warranty disclaimer.** As stated in the GPL, SpeedSearch is provided
"as is" without any warranty. Any compliance obligations that apply to
a deployment (FERPA, ADA, NYC bias-audit requirements, university
copyright disclaimers) must be addressed in a separate agreement, not
by the license.
