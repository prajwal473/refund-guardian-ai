# Refund Guardian AI
**Hackathon starter project — Alexa+ / MCP-inspired consumer-support workflow**

Refund Guardian helps a user organize a return or warranty issue from purchase details to a documented next-step plan. The MVP stores cases, calculates a *user-provided / verified-policy-based* deadline, drafts a support message, tracks follow-ups, and exposes tools through an MCP server.

> **Honest MVP boundary:** This starter runs locally and uses a small demo policy catalog. It does not submit claims, contact retailers, provide legal advice, or guarantee refund eligibility. The demo policy data is illustrative and must not be treated as real retailer policy. The receipt parser is a lightweight text parser, not OCR. Add OCR / a model provider only after the workflow is reliable.

## What is included
- FastAPI web app + responsive dashboard (HTML/CSS/JS, no Node build required)
- SQLite persistence for cases and follow-up tasks
- Receipt text upload/parser for a demo receipt
- Case creation, deadline calculation, claim draft, status updates, follow-up scheduling
- Separate MCP server using the official Python MCP SDK (`/mcp`)
- Demo data, architecture and pitch documents, and basic tests

## Requirements
- Python 3.11+
- Optional: `uv` or a virtual environment
- Internet is only needed to install Python packages; runtime is local.

## Quick start (Windows PowerShell)
```powershell
cd refund_guardian_ai
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```
Open http://127.0.0.1:8000

## Quick start (macOS / Linux)
```bash
cd refund_guardian_ai
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

## Start the MCP server in a second terminal
Activate the same virtual environment, then run:
```bash
python mcp_server.py
```
The MCP server uses Streamable HTTP and is expected at `http://127.0.0.1:8001/mcp`. Confirm the installed MCP SDK's CLI/runtime behavior if you upgrade its version. The web app and MCP server share the same SQLite database.

## Demo workflow
1. Open the dashboard.
2. Use **Load demo receipt** to fill sample purchase data, or enter your own synthetic data.
3. Create a case.
4. Review the suggested next steps and draft claim message.
5. Schedule a follow-up and update the case status.
6. Show that the dashboard reflects persisted data after refresh.
7. In your video, clearly label policy results and notifications as demo/simulated unless you integrate a verified real source.

## API endpoints
- `GET /api/health`
- `GET /api/cases`
- `POST /api/cases`
- `GET /api/cases/{case_id}`
- `PATCH /api/cases/{case_id}`
- `POST /api/cases/{case_id}/draft`
- `POST /api/cases/{case_id}/followups`
- `GET /api/cases/{case_id}/followups`
- `POST /api/receipt/parse-text`

## Configure
Settings are read from environment variables (see `.env.example`). The current MVP does not require an API key. To integrate an LLM, implement a provider adapter and keep the deterministic workflow / safety checks as the source of truth. Never put API keys in frontend code or commit secrets.

## Safety and privacy
- Use synthetic receipt and personal data in demos.
- Do not upload real medical, payment-card, or identity documents.
- Ask for user approval before sending messages or performing consequential actions.
- Do not claim a refund is guaranteed; retailer policies and legal rights vary.
- Add authentication, encryption, retention controls, rate limits, and security review before any real deployment.

## Project layout
```text
refund_guardian_ai/
├── app/
│   ├── main.py
│   ├── models.py
│   ├── services.py
│   └── static/
│       ├── index.html
│       ├── app.js
│       └── styles.css
├── docs/
│   ├── PROJECT_BLUEPRINT.md
│   ├── DEMO_SCRIPT.md
│   └── HACKATHON_SUBMISSION_DRAFT.md
├── tests/
│   └── test_services.py
├── mcp_server.py
├── requirements.txt
├── .env.example
└── README.md
```
