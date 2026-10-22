# Refund Guardian AI
**Hackathon starter project — Alexa+ / MCP-inspired consumer-support workflow**

Refund Guardian helps a user organize a return or warranty issue from purchase details to a documented next-step plan. The MVP stores cases, calculates a *user-provided / verified-policy-based* deadline, drafts a support message, tracks follow-ups, and exposes tools through an MCP server.

> **Honest MVP boundary:** This starter runs locally and contains no real retailer policy data (the demo loader uses one clearly labelled, illustrative return window). It does not submit claims, contact retailers, provide legal advice, or guarantee refund eligibility. The demo policy data is illustrative and must not be treated as real retailer policy. The receipt parser is a lightweight text parser, not OCR. Add OCR / a model provider only after the workflow is reliable.

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

## MCP tools

Refund Guardian exposes seven tools through its local MCP server using Streamable HTTP at `/mcp` (default address: `http://127.0.0.1:8001/mcp`).

| Tool                         | Purpose                                                                                   |
| ---------------------------- | ----------------------------------------------------------------------------------------- |
| `list_refund_cases`          | List saved refund and warranty cases.                                                     |
| `create_refund_case`         | Create a case after validating purchase details and any user-provided policy information. |
| `draft_support_message`      | Draft a support message for the user to review; it does not send the message.             |
| `update_case_status`         | Update a case's status and optionally its notes.                                          |
| `schedule_followup`          | Save a follow-up task locally; it does not send a notification.                           |
| `analyze_refund_eligibility` | Evaluate recorded case information using the rule-based eligibility engine.               |
| `verify_case`                | Read back a saved case and its follow-up tasks to verify persisted state.                 |

A compatible MCP client must be configured to connect to the server. The server's protocol negotiation and tool discovery have been tested locally. This does not establish that the project is natively integrated with Alexa+.

The MCP server and web application share the same SQLite database. The server records and analyzes information but does not contact retailers, submit claims, or send notifications.
## Demo workflow
1. Open the dashboard.
2. Use **Load demo** to fill the form with sample purchase data, or enter your own synthetic data.
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
- `GET /api/cases/export` - export cases as CSV.
- `POST /api/cases/import` - import cases from CSV.
- `POST /api/receipt/parse-text`


### CSV import/export

The import endpoint accepts a `.csv` file up to 5 MB, encoded as UTF-8. Required columns are `product_name`, `retailer`, `purchase_date`, `purchase_price`, and `issue_description`.

Each imported row is validated. Duplicate cases and invalid rows are rejected and reported; valid rows can still be imported when other rows fail. The response reports the number of imported rows and rejected rows, including row numbers and reasons.

The export endpoint downloads cases as `refund_cases.csv`. Review exported files before sharing them.
## Configure
Settings are read from **environment variables** (see `.env.example`). The app does **not** read a `.env` file by itself; either set variables in your shell, or start uvicorn with `--env-file .env` (uvicorn loads it using `python-dotenv`, which is installed with `uvicorn[standard]`). No API key is required to run the app. Never put API keys in frontend code or commit secrets.

## Input validation (web API and MCP tools share the same rules)
Both the REST API and the MCP tools go through `services.create_case`, which applies `services.validate_case_input`. Invalid input is refused with a clear message (HTTP 422 for the API, an `{"error": ..., "details": [...]}` object for MCP) and nothing is stored.

| Field | Rule |
|---|---|
| `product_name`, `retailer` | Required, not blank, at most 160 characters. |
| `issue_description` | 5 to 3000 characters. |
| `purchase_price` | A finite number, not negative. |
| `currency` | One of `INR, USD, EUR, GBP, AUD, CAD, SGD, AED, JPY` (case-insensitive, stored upper-case). |
| `purchase_date` | Strict `YYYY-MM-DD` and a real calendar date; **not in the future** (you cannot have bought it yet) and not before 1900-01-01 (a sanity bound). "Today" is the server's local date. |
| `policy_days` | Optional whole number from 0 to 3650. |
| `policy_confirmed` | `true` only with both `policy_days` and `policy_source` (see below). |

**Deadline convention (unchanged):** `deadline = purchase_date + policy_days`, counted in calendar days; the deadline day itself is still inside the window. Date overflow cannot occur through the validated paths and is also guarded in the eligibility engine.

**Notes:** in `PATCH /api/cases/{id}` and the MCP `update_case_status` tool, *omitting* `notes` (or sending `null`) leaves existing notes unchanged; sending `""` clears them; any other text replaces them.

**Database upgrade:** a `policy_confirmed` column is added automatically on startup to databases created by earlier versions. Existing cases become "not confirmed", because nobody attested to their policy.

## Receipt text parser
`POST /api/receipt/parse-text` never fails on odd input; anything it cannot read confidently is left out and explained in a `warnings` list. It reads `Product/Item`, `Retailer/Store/Merchant`, `Date/Purchase date` and `Total/Grand total/Price/Amount` lines.
- Amounts: `2999`, `1,499.00 INR`, `INR 1,499`, `Rs. 499`, `₹1,49,999.50`, `USD 29.99`. Malformed or ambiguous amounts (`,`, `1,4,9,9`, `29,99`) are rejected with a warning.
- A bare `$` is read as an amount but **does not set a currency** (it could be USD, CAD, AUD...); choose the currency yourself.
- Dates: `YYYY-MM-DD`, `25/12/2025`, `12 Oct 2026`, `October 12, 2026`. A day/month date that could mean two different days (for example `12/10/2026`) is **not guessed**: the date is left empty and both readings are returned in `purchase_date_candidates`. Two-digit years are not supported.

## Refund eligibility analysis

### What it does
For a saved case, **Analyze Eligibility** (in the case details panel) checks the information recorded on the case and returns one of four outcomes:

| Outcome | Meaning |
|---|---|
| `potentially_eligible` | You recorded a window and a source, **confirmed you checked the window against the retailer's own policy**, and today is on or before the calculated deadline. |
| `outside_known_window` | Same, but the calculated deadline has passed. |
| `needs_policy_verification` | The window or source is missing, or you have not confirmed the window. Any date shown is provisional and labelled unconfirmed. |
| `insufficient_information` | The purchase date or issue description is missing, or the data is invalid. No deadline is presented and no eligibility conclusion is drawn. |

The response also includes `policy_status` (`missing`, `unconfirmed`, `user_confirmed` or `not_evaluated`), the deadline and `days_remaining` when they are established (negative once passed), missing information, next steps, caveats and `analysis_method`.

### What "confirmed" means (and does not mean)
- **Refund Guardian does not look up or verify retailer policies.** `policy_verified` in the response is always `false`.
- A **policy source** (URL or text) is just a note you recorded. It never makes a policy "verified", whatever it says.
- The only confirmation is **your own statement**, made by ticking *"I checked this window against the retailer's own policy myself"* when creating the case (`policy_confirmed: true` in the API/MCP). It is reported as `policy_confirmed_by_user`, and the UI says "Confirmed by you (not checked by Refund Guardian)".
- The demo loader never ticks the box, so demo cases always come out as `needs_policy_verification`.
- Cases created before this change are treated as unconfirmed.

### How to use it
1. Create a case. Enter the return window and source if you know them, and tick the confirmation box only if you really checked the policy yourself.
2. Open the case and click **Analyze Eligibility**.
3. Or call the API: `POST /api/cases/{case_id}/eligibility` with an optional JSON body `{"use_llm": true}`. It returns `404` for an unknown case.

### Dashboard deadlines
Deadlines on cases you have not confirmed are drawn as dashed "unconfirmed" labels, not as urgent coloured entitlements. The **Due in 7 days** card counts only *confirmed* deadlines from today to 7 days ahead; overdue cases are never counted as due (they are shown separately in the card's subtitle, together with how many unconfirmed dates were left out).

### Rule-based engine vs. optional AI explanation
- **The rule-based engine is the source of truth.** It is deterministic Python (`services.analyze_eligibility`) with no network calls, and works with no configuration. `analysis_method: "rule_based"` means no model was involved.
- **The AI explanation is optional and only rewords.** If `ANTHROPIC_API_KEY` is set, the API asks the model to restate the rule-based result in plain language. The text goes in a **separate** `ai_explanation` field and `analysis_method` becomes `rule_based+llm_explanation`. It never changes the outcome, dates, missing information, steps or caveats. The text is discarded if it mentions a date that is not in the analysis, promises a refund, or claims a policy was verified or looked up. If the provider is unreachable, errors, or is not configured, you still get the full rule-based result plus an explanatory `llm_note`.
- Only the structured analysis is sent to the provider (outcome, deadline, days remaining, policy status, missing information, caveats, explanation). The issue description, product, retailer and policy source text are not sent.
- Set `"use_llm": false` to skip the provider even when a key is configured. The MCP tool `analyze_refund_eligibility` is always rule-based.

### Optional provider configuration
| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Enables the AI explanation. Leave unset for rule-based only. |
| `REFUND_GUARDIAN_LLM_MODEL` | Optional model name override (default `claude-sonnet-5-5`, not verified against the live API). |

PowerShell example: `$env:ANTHROPIC_API_KEY = "your-key"` then start uvicorn in the same window. The provider call uses Python's standard library (no extra dependency) and is not needed to run or test the app.

### Limitations and assumptions
- Nothing here checks a retailer's policy. The result is only as good as the window and confirmation you entered.
- The window is counted from the purchase date in calendar days, and the deadline day itself counts as inside it. Retailers may count differently (delivery date, business days, time zones). "Today" is the server's local date.
- It does not model warranty rights, defective-goods rules, consumer law, product categories, item condition or exceptions. Being inside a window does not guarantee a refund; being outside one does not mean other remedies are unavailable.
- Policy fields (including the confirmation) cannot be edited on an existing case yet (the API only updates status and notes), so corrected policy details need a new case.
- It does not contact retailers or submit claims, and there are no retailer integrations.
- The AI explanation path has been tested with a mocked provider but not against the live API.

## Run the tests
```bash
python -m pytest
```
Each test gets its own temporary SQLite database (`tests/dbtools.py`), so tests are independent and never touch `refund_guardian.db`. Dates are fixed in tests, provider calls are mocked, and no API key or network access is needed.
- `tests/test_dashboard_stats.py` runs the dashboard logic in `app/static/stats.js` with Node, and is skipped if Node is not installed.
- `tests/test_mcp_tools.py` calls the MCP tool functions directly (it does not test the MCP protocol) and is skipped if the `mcp` package is not installed.

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
│       ├── stats.js
│       └── styles.css
├── docs/
│   ├── PROJECT_BLUEPRINT.md
│   ├── DEMO_SCRIPT.md
│   └── HACKATHON_SUBMISSION_DRAFT.md
├── tests/
│   ├── test_services.py
│   ├── test_eligibility.py
│   ├── test_eligibility_api.py
│   ├── test_case_validation.py
│   ├── test_receipt_parser.py
│   ├── test_mcp_tools.py
│   ├── test_dashboard_stats.py
│   └── dbtools.py
├── mcp_server.py
├── requirements.txt
├── .env.example
└── README.md
```
