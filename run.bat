@echo off
REM One-command setup + launch (Windows).
cd /d "%~dp0"

if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
REM Keys are pasted into the app's sidebar - no .env needed for the web app.
streamlit run app.py
