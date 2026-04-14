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
# Launches Ollama (if not already running) and the Flask backend.
set -e

if [ ! -d ".venv" ]; then
  echo "-- first run detected; running setup"
  ./setup.sh
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "-- starting Ollama in background"
  (ollama serve >/tmp/ollama.log 2>&1 &) || true
  sleep 2
fi

echo ""
echo "==> SpeedSearch backend running at http://localhost:5000"
echo "    Load extension/ in chrome://extensions (Developer mode)."
echo "    Ctrl-C to stop."
echo ""
python app.py
