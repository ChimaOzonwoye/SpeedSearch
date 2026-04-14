#!/usr/bin/env bash
# SpeedSearch - Contextual matching for university research discovery.
# Copyright (C) 2026 Aadharsh Sakkaravarthy, Ted Erdos, Ali Salama,
#                    Chima Ozonwoye.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.  See LICENSE for the full text.
#
# One-shot installer: creates a Python venv, installs Ollama if missing,
# pulls the default local model, and writes a starter .env.
set -e

echo "==> SpeedSearch setup"

if [ ! -d ".venv" ]; then
  echo "-- creating virtualenv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

if ! command -v ollama >/dev/null 2>&1; then
  if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "-- please install Ollama from https://ollama.com/download"
    echo "   then re-run ./setup.sh"
    exit 1
  else
    echo "-- installing Ollama (may prompt for sudo)"
    curl -fsSL https://ollama.com/install.sh | sh
  fi
fi

MODEL="${OLLAMA_MODEL:-llama3.2:3b}"
echo "-- pulling model: $MODEL"
ollama pull "$MODEL"

if [ ! -f ".env" ]; then
  cat > .env <<EOF
# SpeedSearch configuration
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=$MODEL

# Days between professor pings asking "is this still open?"
PING_DAYS=2

# Optional SMTP.  If blank, pings are logged to the console instead.
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
FROM_EMAIL=
APP_HOST=http://localhost:5000
EOF
  echo "-- wrote .env (edit to enable real email pings)"
fi

echo ""
echo "Setup complete."
echo "  1. Run the backend:  ./run.sh"
echo "  2. Load the extension:"
echo "       chrome://extensions  ->  Developer mode  ->  Load unpacked"
echo "       point it at the extension/ folder in this repo"
echo ""
