# SpeedSearch - Contextual matching for university research discovery.
# Copyright (C) 2026 Aadharsh Sakkaravarthy, Ted Erdos, Ali Salama,
#                    Chima Ozonwoye.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
Local backend for the SpeedSearch Chrome extension.

Responsibilities
----------------
* Receive scraped page text from the extension, ask a locally-running
  Ollama model to extract research-opportunity cards, and persist them.
* Store a single student's portfolio (skills, experience, availability)
  so the extension can score every page it sees.
* Score contextual fit between the student's portfolio and each extracted
  opportunity using the same local model.
* Run a recurring job that pings professors (via SMTP or console) asking
  whether each listed opportunity is still open.

Nothing leaves the machine.  The extension talks only to this server
(default http://localhost:5000) and this server talks only to Ollama
(default http://localhost:11434).
"""

import json
import os
import sqlite3
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

import fitz  # PyMuPDF
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

load_dotenv()

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "speedsearch.db"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER)
PING_DAYS = int(os.getenv("PING_DAYS", "2"))
APP_HOST = os.getenv("APP_HOST", "http://localhost:5000")

app = Flask(__name__)
# The extension loads from a chrome-extension:// origin; Flask-CORS with
# the default "*" rule covers that while keeping this server reachable
# only on localhost.
CORS(app)


# --------------------------- database ------------------------------- #

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            required_skills TEXT,
            difficulty TEXT,
            source_url TEXT,
            professor_name TEXT,
            professor_email TEXT,
            is_open INTEGER DEFAULT 1,
            last_pinged TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS student_profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            name TEXT,
            email TEXT,
            skills TEXT,
            experience TEXT,
            summary TEXT,
            availability TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (opportunity_id) REFERENCES opportunities(id)
        );
        CREATE INDEX IF NOT EXISTS idx_match_opp
            ON matches (opportunity_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_opp_source
            ON opportunities (source_url, title);
        """)


# --------------------------- Ollama glue ---------------------------- #

def ollama_json(system: str, user: str, schema: dict) -> dict:
    """Call Ollama's chat endpoint with a JSON schema and parse the reply."""
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "format": schema,
        "stream": False,
        "options": {"temperature": 0.2},
    }
    r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=300)
    r.raise_for_status()
    return json.loads(r.json()["message"]["content"])


OPPORTUNITY_SCHEMA = {
    "type": "object",
    "properties": {
        "opportunities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "required_skills": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "difficulty": {
                        "type": "string",
                        "enum": ["Structured", "Moderate", "High Risk"],
                    },
                    "professor_name": {"type": "string"},
                    "professor_email": {"type": "string"},
                },
                "required": ["title", "description",
                             "required_skills", "difficulty"],
            },
        }
    },
    "required": ["opportunities"],
}

PORTFOLIO_SCHEMA = {
    "type": "object",
    "properties": {
        "skills": {"type": "array", "items": {"type": "string"}},
        "experience": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "required": ["skills", "experience", "summary"],
}

MATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "reason": {"type": "string"},
    },
    "required": ["score", "reason"],
}


# --------------------------- prompts -------------------------------- #

def extract_opportunities(text: str, source_url: str = "") -> list[dict]:
    """Turn arbitrary webpage text into structured opportunity cards.

    The model is instructed to skip non-research content (navigation,
    marketing copy) and to identify the *shape* of each project, not just
    the keywords.
    """
    system = (
        "You are an academic research analyst.  You are given raw text "
        "scraped from a university webpage.  Identify every distinct "
        "research project, lab opening, or student position a student "
        "could join.  Ignore navigation, footers, and marketing copy.\n\n"
        "For each project, describe the underlying capability the "
        "student must bring - the *shape* of the work - not just the "
        "tools named on the page.  Examples of shape: reverse-"
        "engineering, empirical measurement, protocol design, data "
        "pipeline construction, qualitative interviewing.\n\n"
        "If the page clearly lists no projects a student could join, "
        "return an empty array.  Do not invent projects."
    )
    user = f"Source URL: {source_url}\n\nPAGE TEXT:\n{text[:16000]}"
    result = ollama_json(system, user, OPPORTUNITY_SCHEMA)
    return result.get("opportunities", [])


def extract_portfolio(text: str) -> dict:
    """Pull skills/experience/summary out of a student's writeup."""
    system = (
        "You are a technical reviewer.  Read a student's portfolio, "
        "project writeup, or development journey.  Extract concrete "
        "skills they have actually demonstrated (not claimed), specific "
        "experiences (what they actually built or discovered), and a "
        "two-sentence summary of their engineering identity.  Be "
        "specific about the shape of their work, not generic labels."
    )
    return ollama_json(system, text[:16000], PORTFOLIO_SCHEMA)


def score_match(opp: dict, student: dict) -> dict:
    """Score contextual fit between one opportunity and the student."""
    system = (
        "You are SpeedSearch's match engine.  Compare a research "
        "opportunity to a student's real portfolio and score contextual "
        "fit from 0 to 100.  Reward transferable depth - similar shape "
        "of work in a different domain still counts.  Penalize "
        "superficial keyword overlap where the student has not actually "
        "done that kind of work.  In 'reason', cite the specific past "
        "project or capability that drives the match in one sentence."
    )
    user = json.dumps({
        "opportunity": {
            "title": opp.get("title", ""),
            "description": opp.get("description", ""),
            "required_skills": opp.get("required_skills", []),
            "difficulty": opp.get("difficulty", ""),
        },
        "student": {
            "skills": student.get("skills", []),
            "experience": student.get("experience", []),
            "summary": student.get("summary", ""),
        },
    })
    return ollama_json(system, user, MATCH_SCHEMA)


# --------------------------- helpers -------------------------------- #

def get_profile() -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM student_profile WHERE id = 1"
        ).fetchone()
    if not row:
        return None
    return {
        "name": row["name"],
        "email": row["email"],
        "availability": row["availability"],
        "summary": row["summary"],
        "skills": json.loads(row["skills"] or "[]"),
        "experience": json.loads(row["experience"] or "[]"),
    }


def save_opportunities(opps: list[dict], source_url: str) -> list[dict]:
    saved = []
    with db() as conn:
        for o in opps:
            try:
                cur = conn.execute(
                    """INSERT OR IGNORE INTO opportunities
                       (title, description, required_skills, difficulty,
                        source_url, professor_name, professor_email)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        o.get("title", "").strip(),
                        o.get("description", ""),
                        json.dumps(o.get("required_skills", [])),
                        o.get("difficulty", "Moderate"),
                        source_url,
                        o.get("professor_name", ""),
                        o.get("professor_email", ""),
                    ),
                )
                if cur.lastrowid:
                    opp_id = cur.lastrowid
                else:
                    # Row already existed; fetch its id.
                    row = conn.execute(
                        "SELECT id FROM opportunities "
                        "WHERE source_url = ? AND title = ?",
                        (source_url, o.get("title", "").strip()),
                    ).fetchone()
                    opp_id = row["id"] if row else None
                saved.append({**o, "id": opp_id})
            except sqlite3.IntegrityError:
                continue
        conn.commit()
    return saved


def score_opportunities(opps: list[dict], student: dict) -> list[dict]:
    out = []
    for o in opps:
        if not o.get("id"):
            continue
        try:
            r = score_match(o, student)
        except Exception as e:
            app.logger.warning("score failed for %s: %s", o.get("id"), e)
            continue
        with db() as conn:
            conn.execute(
                """INSERT INTO matches (opportunity_id, score, reason)
                   VALUES (?, ?, ?)""",
                (o["id"], r["score"], r["reason"]),
            )
            conn.commit()
        out.append({
            "opportunity_id": o["id"],
            "title": o.get("title", ""),
            "difficulty": o.get("difficulty", ""),
            "required_skills": o.get("required_skills", []),
            "score": r["score"],
            "reason": r["reason"],
        })
    out.sort(key=lambda m: m["score"], reverse=True)
    return out


# --------------------------- routes --------------------------------- #

@app.get("/health")
def health():
    try:
        requests.get(f"{OLLAMA_URL}/api/tags", timeout=2).raise_for_status()
        ollama_ok = True
    except Exception:
        ollama_ok = False
    return jsonify(
        ok=True, ollama=ollama_ok,
        model=OLLAMA_MODEL, profile=bool(get_profile()),
    )


@app.get("/")
def home():
    return (
        "<h1>SpeedSearch backend</h1>"
        "<p>Running.  Load the Chrome extension in "
        "<code>chrome://extensions</code> (Developer mode &rarr; "
        "Load unpacked &rarr; choose the <code>extension/</code> folder).</p>"
        f"<p>Model: <code>{OLLAMA_MODEL}</code></p>"
    )


@app.post("/api/detect")
def detect():
    """Extract opportunities from scraped page text and score them."""
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    source_url = (data.get("url") or "").strip()
    if not text:
        return jsonify(error="text is required"), 400

    try:
        opps = extract_opportunities(text, source_url)
    except Exception as e:
        return jsonify(error=f"extraction failed: {e}"), 500

    saved = save_opportunities(opps, source_url)

    profile = get_profile()
    matches = score_opportunities(saved, profile) if profile else []
    return jsonify(
        opportunities=saved,
        matches=matches,
        has_profile=bool(profile),
    )


@app.get("/api/profile")
def profile_get():
    p = get_profile()
    return jsonify(p or {})


@app.post("/api/profile")
def profile_put():
    """Create or update the single local student profile.

    Accepts either a posted PDF (multipart) and/or pasted text plus
    name/email/availability fields.  The LLM turns free-form text into
    structured portfolio signals.
    """
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    availability = (request.form.get("availability") or "").strip()
    pasted = request.form.get("text") or ""

    text = pasted
    f = request.files.get("file")
    if f and f.filename:
        raw = f.read()
        if f.filename.lower().endswith(".pdf"):
            with fitz.open(stream=raw, filetype="pdf") as doc:
                text += "\n" + "\n".join(p.get_text() for p in doc)
        else:
            text += "\n" + raw.decode("utf-8", errors="ignore")
    text = text.strip()
    if not text:
        return jsonify(error="paste text or upload a file"), 400

    try:
        portfolio = extract_portfolio(text)
    except Exception as e:
        return jsonify(error=f"portfolio analysis failed: {e}"), 500

    with db() as conn:
        conn.execute(
            """INSERT INTO student_profile
               (id, name, email, skills, experience, summary,
                availability, updated_at)
               VALUES (1, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name,
                 email=excluded.email,
                 skills=excluded.skills,
                 experience=excluded.experience,
                 summary=excluded.summary,
                 availability=excluded.availability,
                 updated_at=CURRENT_TIMESTAMP""",
            (name, email,
             json.dumps(portfolio.get("skills", [])),
             json.dumps(portfolio.get("experience", [])),
             portfolio.get("summary", ""),
             availability),
        )
        conn.commit()
    return jsonify(get_profile())


@app.get("/api/opportunities")
def list_opportunities():
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM opportunities ORDER BY created_at DESC"
        ).fetchall()
    return jsonify([{
        "id": r["id"],
        "title": r["title"],
        "description": r["description"],
        "required_skills": json.loads(r["required_skills"] or "[]"),
        "difficulty": r["difficulty"],
        "is_open": bool(r["is_open"]),
        "source_url": r["source_url"],
        "professor_name": r["professor_name"],
        "professor_email": r["professor_email"],
        "last_pinged": r["last_pinged"],
    } for r in rows])


@app.get("/opportunity/<int:opp_id>/status")
def set_status(opp_id):
    """One-click link the scheduler email contains."""
    is_open = request.args.get("open", "1") == "1"
    with db() as conn:
        conn.execute(
            "UPDATE opportunities SET is_open = ? WHERE id = ?",
            (1 if is_open else 0, opp_id),
        )
        conn.commit()
    msg = "kept open" if is_open else "marked closed"
    return (
        f"<h2>SpeedSearch</h2><p>Opportunity {opp_id} {msg}."
        " You can close this tab.</p>"
    )


@app.post("/api/ping-now")
def ping_now():
    ping_professors()
    return jsonify(ok=True)


# --------------------------- scheduler ------------------------------ #

def send_email(to: str, subject: str, body: str) -> bool:
    if not SMTP_HOST or not SMTP_USER or not to:
        app.logger.info("[email/stub] %s -> %s", subject, to or "(no addr)")
        return False
    msg = EmailMessage()
    msg["From"] = FROM_EMAIL
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        return True
    except Exception as e:
        app.logger.warning("[email] failed: %s", e)
        return False


def ping_professors():
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM opportunities WHERE is_open = 1"
        ).fetchall()
    for row in rows:
        yes = f"{APP_HOST}/opportunity/{row['id']}/status?open=1"
        no = f"{APP_HOST}/opportunity/{row['id']}/status?open=0"
        body = (
            f"Hi{' Prof. ' + row['professor_name'] if row['professor_name'] else ''},\n\n"
            f'Is "{row["title"]}" still open for new students?\n\n'
            f"  YES - keep listed: {yes}\n"
            f"  NO  - position filled: {no}\n\n"
            "Source: " + (row["source_url"] or "(uploaded)") + "\n\n"
            "-- SpeedSearch"
        )
        send_email(
            row["professor_email"] or "",
            f'SpeedSearch: is "{row["title"]}" still open?',
            body,
        )
        with db() as conn:
            conn.execute(
                "UPDATE opportunities SET last_pinged = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), row["id"]),
            )
            conn.commit()


scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(ping_professors, "interval", days=PING_DAYS, id="ping")


if __name__ == "__main__":
    init_db()
    scheduler.start()
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
