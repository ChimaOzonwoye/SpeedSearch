#!/usr/bin/env bash
# SpeedSearch one-shot setup.
# Installs Python deps, Ollama (if missing), and pulls the local model.
set -e

echo "==> SpeedSearch setup"

# 1. Python venv
if [ ! -d ".venv" ]; then
  echo "-- creating virtualenv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

# 2. Ollama
if ! command -v ollama >/dev/null 2>&1; then
  echo "-- installing Ollama (requires sudo on Linux)"
  if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "   On macOS, download Ollama from https://ollama.com/download"
    echo "   Then re-run ./setup.sh"
    exit 1
  else
    curl -fsSL https://ollama.com/install.sh | sh
  fi
fi

# 3. Pull the model
MODEL="${OLLAMA_MODEL:-llama3.2:3b}"
echo "-- pulling model: $MODEL"
ollama pull "$MODEL"

# 4. .env template
if [ ! -f ".env" ]; then
  cat > .env <<EOF
# SpeedSearch configuration
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=$MODEL

# Weekly ping interval (days)
PING_DAYS=2

# Optional: SMTP for professor pings. Leave blank to log to console instead.
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
FROM_EMAIL=
APP_HOST=http://localhost:5000
EOF
  echo "-- wrote .env (edit it to enable email pings)"
fi

echo ""
echo "Setup complete. Run:"
echo "  ./run.sh"
echo ""
