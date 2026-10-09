#!/usr/bin/env bash
# One-command setup + launch (macOS / Linux / Codespaces).
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
. .venv/bin/activate
pip install -q -r requirements.txt
# Keys are pasted into the app's sidebar - no .env needed for the web app.
exec streamlit run app.py
