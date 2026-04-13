#!/usr/bin/env bash
# Launch SpeedSearch locally.
set -e

if [ ! -d ".venv" ]; then
  echo "-- first run detected; running setup"
  ./setup.sh
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# Make sure Ollama is up
if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "-- starting Ollama in background"
  (ollama serve >/tmp/ollama.log 2>&1 &) || true
  sleep 2
fi

echo ""
echo "==> SpeedSearch running at http://localhost:5000"
echo "    (Ctrl-C to stop)"
echo ""
python app.py
