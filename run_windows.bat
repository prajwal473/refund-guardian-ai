@echo off
if not exist .venv py -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
