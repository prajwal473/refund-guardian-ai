# Refund Guardian AI
**Hackathon starter project — Alexa+ / MCP-inspired consumer-support workflow**

Refund Guardian helps a user organize a return or warranty issue from purchase details to a documented next-step plan. The MVP stores cases, calculates a *user-provided / verified-policy-based* deadline, drafts a support message, tracks follow-ups, and exposes tools through an MCP server.

> **Honest MVP boundary:** This starter runs locally and uses a small demo policy catalog. It does not submit claims, contact retailers, provide legal advice, or guarantee refund eligibility. The demo policy data is illustrative and must not be treated as real retailer policy. The receipt parser is a lightweight text parser, not OCR. Add OCR / a model provider only after the workflow is reliable.

## What is included
- FastAPI web app + responsive dashboard (HTML/CSS/JS, no Node build required)
- SQLite persistence for cases and follow-up tasks
- Receipt text upload/parser for a demo receipt
- Rule-based refund **eligibility analysis** (with an optional AI explanation, see below)
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
- `POST /api/cases/{case_id}/eligibility`
- `POST /api/cases/{case_id}/followups`
- `GET /api/cases/{case_id}/followups`
- `POST /api/receipt/parse-text`

## Configure
Settings are read from **environment variables** (see `.env.example`). The app does **not** read a `.env` file by itself; either set variables in your shell, or start uvicorn with `--env-file .env` (uvicorn loads it using `python-dotenv`, which is installed with `uvicorn[standard]`). No API key is required to run the app. Never put API keys in frontend code or commit secrets.

## Refund eligibility analysis

### What it does
For a saved case, **Analyze Eligibility** (in the case details panel) checks the information recorded on the case and returns one of four outcomes:

| Outcome | Meaning |
|---|---|
| `potentially_eligible` | A return window and source were recorded, and today is on or before the calculated deadline. |
| `outside_known_window` | A return window and source were recorded, and the calculated deadline has passed. |
| `needs_policy_verification` | The window length or policy source is missing, or the source looks like demo/placeholder text. Any date shown is provisional and unconfirmed. |
| `insufficient_information` | The purchase date or issue description is missing, or the data is invalid or inconsistent (for example a future purchase date or an out-of-range window). |

The response also includes the deadline and `days_remaining` when they can be calculated (negative once passed), the missing information, recommended next steps, caveats, and `analysis_method`.

### How to use it
1. Create a case. Enter a **verified** return window and a **policy source** (URL or policy name) if you know them.
2. Open the case and click **Analyze Eligibility**.
3. Or call the API: `POST /api/cases/{case_id}/eligibility` with an optional JSON body `{"use_llm": true}`. It returns `404` for an unknown case.

### Rule-based engine vs. optional AI explanation
- **The rule-based engine is the source of truth.** It is deterministic Python (`services.analyze_eligibility`): date arithmetic and checks on the fields stored on the case. It makes no network calls and works with no configuration. Responses with `analysis_method: "rule_based"` come from this engine alone.
- **The AI explanation is optional and only rewords.** If `ANTHROPIC_API_KEY` is set, the API asks the model to restate the rule-based result in plain language. That text is returned in a **separate** `ai_explanation` field and `analysis_method` becomes `rule_based+llm_explanation`. It never changes the outcome, dates, missing information, steps or caveats. Output that mentions a date not present in the analysis is discarded. If the provider is unreachable, errors, or is not configured, you still get the full rule-based result plus an explanatory `llm_note`.
- What is sent to the provider: only the structured analysis (outcome, deadline, days remaining, verification flag, missing information, caveats, explanation). The issue description, product, retailer and policy source text are **not** sent.
- Set `"use_llm": false` in the request to skip the provider even when a key is configured. The MCP tool `analyze_refund_eligibility` is always rule-based.

### Optional provider configuration
| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Enables the AI explanation. Leave unset for rule-based only. |
| `REFUND_GUARDIAN_LLM_MODEL` | Optional model name override (default `claude-sonnet-5-5`). |

PowerShell example: `$env:ANTHROPIC_API_KEY = "your-key"` then start uvicorn in the same window. The provider call uses Python's standard library (no extra dependency) and is not required to run or test the app.

### Limitations and assumptions
- **Refund Guardian does not look up or check retailer policies.** It only uses what you entered. "Verified" means a window length and a non-placeholder source were recorded, not that anyone confirmed them.
- A source containing words such as *demo, illustrative, placeholder, sample, unverified, unknown, TBD, n/a* is treated as unverified. This is a simple text check and can be wrong in either direction.
- The window is counted from the purchase date, in calendar days, and the deadline day itself counts as inside the window. Retailers may count differently (delivery date, business days, time zones).
- It does not model warranty rights, defective-goods rules, consumer law, product categories, item condition or exceptions. Being inside a window does not guarantee a refund; being outside one does not mean other remedies are unavailable.
- Policy fields on an existing case cannot be edited yet (the API only updates status and notes), so corrected policy details need a new case.
- "Today" is the server's local date.
- It does not contact retailers or submit claims, and there are no retailer integrations.
- The AI explanation path has been tested with a mocked provider but not against the live API in this repository's test suite.

## Run the tests
```bash
python -m pytest
```
Eligibility tests use fixed dates and mocked provider calls, so they do not depend on the current date, network access or an API key.

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
│   ├── test_services.py
│   ├── test_eligibility.py
│   └── test_eligibility_api.py
├── mcp_server.py
├── requirements.txt
├── .env.example
└── README.md
```