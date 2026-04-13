# SpeedSearch - Contextual matching for university research discovery.
# Copyright (C) 2026 Aadharsh Sakkaravarthy, Ted Erdos, Ali Salama, Chima Ozonwoye.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
"""
SpeedSearch local prototype.

Flask app that:
  1. Accepts a professor's research PDF/text, calls a local Ollama model,
     and extracts structured "opportunity" cards (title, skills, difficulty).
  2. Accepts a student's portfolio PDF/text, extracts their skills, experience,
     and availability.
  3. Matches students to opportunities using the LLM to score contextual fit,
     not just keyword overlap.
  4. Every 2 days, emails professors asking if each opportunity is still open.

Requires Ollama running locally (https://ollama.com) with a model pulled:
    ollama pull llama3.2:3b
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
from flask import Flask, jsonify, render_template, request

load_dotenv()

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "speedsearch.db"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER)
PING_DAYS = int(os.getenv("PING_DAYS", "2"))

app = Flask(__name__)


# ----------------------------- database ----------------------------- #

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS professors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            professor_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            required_skills TEXT,
            difficulty TEXT,
            is_open INTEGER DEFAULT 1,
            last_pinged TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (professor_id) REFERENCES professors(id)
        );
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            skills TEXT,
            experience TEXT,
            availability TEXT,
            raw_portfolio TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            opportunity_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            reason TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(id),
            FOREIGN KEY (opportunity_id) REFERENCES opportunities(id)
        );
        """)


# ----------------------------- helpers ------------------------------ #

def extract_text(file_storage) -> str:
    """Extract text from an uploaded PDF or plain text file."""
    filename = file_storage.filename or ""
    data = file_storage.read()
    if filename.lower().endswith(".pdf"):
        doc = fitz.open(stream=data, filetype="pdf")
        pages = [page.get_text() for page in doc]
        doc.close()
        return "\n".join(pages).strip()
    return data.decode("utf-8", errors="ignore").strip()


def ollama_json(system: str, user: str, schema: dict) -> dict:
    """Call local Ollama with a JSON schema and return parsed JSON."""
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
    content = r.json()["message"]["content"]
    return json.loads(content)


# ----------------------------- LLM prompts -------------------------- #

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
                        "type": "array", "items": {"type": "string"}
                    },
                    "difficulty": {
                        "type": "string",
                        "enum": ["Structured", "Moderate", "High Risk"]
                    },
                },
                "required": ["title", "description", "required_skills", "difficulty"],
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


def extract_opportunities(text: str) -> list[dict]:
    system = (
        "You are an academic research analyst. From a professor's research "
        "document, extract every distinct project a student could join. "
        "Go beyond surface-level skills (e.g. 'Python'): identify the deeper "
        "capabilities required (reverse-engineering, audit design, browser "
        "APIs, ML experimentation, etc.). Difficulty: 'Structured' = well-"
        "scoped, 'Moderate' = needs judgement, 'High Risk' = open-ended."
    )
    result = ollama_json(system, text[:12000], OPPORTUNITY_SCHEMA)
    return result.get("opportunities", [])


def extract_portfolio(text: str) -> dict:
    system = (
        "You are a technical reviewer. Read a student's portfolio, project "
        "writeup, or development journey. Extract concrete skills demonstrated "
        "(not just claimed), real experiences (what they actually built or "
        "discovered), and summarize their engineering identity in 2 sentences. "
        "Be specific: 'Chrome Extension with Flask backend' not 'web dev'."
    )
    return ollama_json(system, text[:12000], PORTFOLIO_SCHEMA)


def score_match(opp: dict, student: dict) -> dict:
    system = (
        "You are SpeedSearch's match engine. Compare a research opportunity "
        "to a student's real portfolio. Score 0-100 based on CONTEXTUAL FIT — "
        "does their actual demonstrated work map to what this project needs? "
        "Reward transferable depth (someone who built a browser extension "
        "fits a project that needs one, even if different domain). Penalize "
        "superficial keyword overlap. In 'reason', cite the specific project "
        "or skill that drives the match."
    )
    user = json.dumps({
        "opportunity": {
            "title": opp["title"],
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


# ----------------------------- email -------------------------------- #

def send_email(to: str, subject: str, body: str) -> bool:
    if not SMTP_HOST or not SMTP_USER:
        print(f"[email] SMTP not configured; would send to {to}: {subject}")
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
        print(f"[email] failed: {e}")
        return False


def ping_professors():
    """Ask profs whether each open opportunity is still active."""
    with db() as conn:
        rows = conn.execute("""
            SELECT o.id, o.title, p.name, p.email
            FROM opportunities o JOIN professors p ON p.id = o.professor_id
            WHERE o.is_open = 1
        """).fetchall()
    host = os.getenv("APP_HOST", "http://localhost:5000")
    for row in rows:
        link_yes = f"{host}/opportunity/{row['id']}/status?open=1"
        link_no = f"{host}/opportunity/{row['id']}/status?open=0"
        body = (
            f"Hi Prof. {row['name']},\n\n"
            f"Is \"{row['title']}\" still open for new students?\n\n"
            f"YES - keep listed: {link_yes}\n"
            f"NO  - position filled: {link_no}\n\n"
            f"-- SpeedSearch"
        )
        send_email(row["email"], f"SpeedSearch: is \"{row['title']}\" still open?", body)
        with db() as conn:
            conn.execute(
                "UPDATE opportunities SET last_pinged = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), row["id"]),
            )
            conn.commit()


# ----------------------------- routes ------------------------------- #

@app.route("/")
def home():
    return render_template("index.html")


@app.post("/api/professor/upload")
def professor_upload():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    if not name or not email:
        return jsonify(error="name and email required"), 400

    text = ""
    if "file" in request.files and request.files["file"].filename:
        text = extract_text(request.files["file"])
    text = (request.form.get("text", "") + "\n" + text).strip()
    if not text:
        return jsonify(error="provide a pdf or paste text"), 400

    try:
        opps = extract_opportunities(text)
    except Exception as e:
        return jsonify(error=f"LLM failed: {e}"), 500

    with db() as conn:
        cur = conn.execute(
            "INSERT INTO professors (name, email) VALUES (?, ?)", (name, email)
        )
        prof_id = cur.lastrowid
        saved = []
        for o in opps:
            cur = conn.execute(
                """INSERT INTO opportunities
                   (professor_id, title, description, required_skills, difficulty)
                   VALUES (?, ?, ?, ?, ?)""",
                (prof_id, o["title"], o.get("description", ""),
                 json.dumps(o.get("required_skills", [])),
                 o.get("difficulty", "Moderate")),
            )
            saved.append({**o, "id": cur.lastrowid})
        conn.commit()
    return jsonify(professor_id=prof_id, opportunities=saved)


@app.post("/api/student/upload")
def student_upload():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    availability = request.form.get("availability", "").strip()
    if not name or not email:
        return jsonify(error="name and email required"), 400

    text = ""
    if "file" in request.files and request.files["file"].filename:
        text = extract_text(request.files["file"])
    text = (request.form.get("text", "") + "\n" + text).strip()
    if not text:
        return jsonify(error="provide a pdf or paste text"), 400

    try:
        portfolio = extract_portfolio(text)
    except Exception as e:
        return jsonify(error=f"LLM failed: {e}"), 500

    with db() as conn:
        cur = conn.execute(
            """INSERT INTO students
               (name, email, skills, experience, availability, raw_portfolio)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, email,
             json.dumps(portfolio.get("skills", [])),
             json.dumps(portfolio.get("experience", [])),
             availability, text[:8000]),
        )
        student_id = cur.lastrowid
        opps = conn.execute(
            "SELECT * FROM opportunities WHERE is_open = 1"
        ).fetchall()

    matches = []
    for opp in opps:
        opp_dict = {
            "title": opp["title"],
            "description": opp["description"] or "",
            "required_skills": json.loads(opp["required_skills"] or "[]"),
            "difficulty": opp["difficulty"] or "",
        }
        try:
            result = score_match(opp_dict, portfolio)
        except Exception as e:
            print(f"[match] skip {opp['id']}: {e}")
            continue
        with db() as conn:
            conn.execute(
                """INSERT INTO matches (student_id, opportunity_id, score, reason)
                   VALUES (?, ?, ?, ?)""",
                (student_id, opp["id"], result["score"], result["reason"]),
            )
            conn.commit()
        matches.append({
            "opportunity_id": opp["id"],
            "title": opp["title"],
            "difficulty": opp["difficulty"],
            "score": result["score"],
            "reason": result["reason"],
        })

    matches.sort(key=lambda m: m["score"], reverse=True)
    return jsonify(
        student_id=student_id,
        portfolio=portfolio,
        matches=matches,
    )


@app.get("/api/opportunities")
def list_opportunities():
    with db() as conn:
        rows = conn.execute("""
            SELECT o.*, p.name AS prof_name, p.email AS prof_email
            FROM opportunities o JOIN professors p ON p.id = o.professor_id
            ORDER BY o.created_at DESC
        """).fetchall()
    return jsonify([{
        "id": r["id"],
        "title": r["title"],
        "description": r["description"],
        "required_skills": json.loads(r["required_skills"] or "[]"),
        "difficulty": r["difficulty"],
        "is_open": bool(r["is_open"]),
        "professor": r["prof_name"],
        "last_pinged": r["last_pinged"],
    } for r in rows])


@app.get("/api/matches/<int:student_id>")
def get_matches(student_id):
    with db() as conn:
        rows = conn.execute("""
            SELECT m.*, o.title, o.difficulty
            FROM matches m JOIN opportunities o ON o.id = m.opportunity_id
            WHERE m.student_id = ? ORDER BY m.score DESC
        """, (student_id,)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/opportunity/<int:opp_id>/status")
def set_status(opp_id):
    is_open = request.args.get("open", "1") == "1"
    with db() as conn:
        conn.execute(
            "UPDATE opportunities SET is_open = ? WHERE id = ?",
            (1 if is_open else 0, opp_id),
        )
        conn.commit()
    msg = "kept listed" if is_open else "closed"
    return f"<h2>SpeedSearch</h2><p>Opportunity {opp_id} {msg}. You can close this tab.</p>"


@app.post("/api/ping-now")
def ping_now():
    """Manually trigger the professor ping (useful for demos)."""
    ping_professors()
    return jsonify(ok=True)


# ----------------------------- scheduler ---------------------------- #

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(ping_professors, "interval", days=PING_DAYS, id="ping")


if __name__ == "__main__":
    init_db()
    scheduler.start()
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
