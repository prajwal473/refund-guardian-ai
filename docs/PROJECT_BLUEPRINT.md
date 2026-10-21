# Refund Guardian AI — Project Blueprint

## One-line pitch
A voice-friendly consumer-support agent that turns a return or warranty problem into a documented case, a user-reviewed support draft, and tracked follow-up tasks.

## User problem
People often do not know what information to gather, what policy applies, or how to follow up when a purchase goes wrong. Ordinary reminders track dates; Refund Guardian organizes the resolution workflow.

## Target user
A consumer managing a purchase return, replacement, repair, or warranty inquiry.

## MVP scope
1. Record product, retailer, purchase date, price, and issue.
2. Calculate a date only when the user supplies a policy window; keep the source visible.
3. Generate a support message draft for user review.
4. Schedule and persist follow-ups.
5. Update status and verify saved state.
6. Expose core actions as MCP tools.

## Explicit non-goals
- Automatically submit a refund claim.
- Guarantee eligibility or quote unverified retailer policies as facts.
- Connect to email, retailer accounts, or payment systems in the MVP.
- Perform OCR on arbitrary images (the included parser accepts receipt text only).
- Give legal advice.

## Architecture
Browser UI → FastAPI → SQLite. Separately, an MCP server exposes tools backed by the same service module and database. The agent host can call the MCP tools and use their results to report progress. For the hackathon demo, a web UI can simulate the conversational front end while clearly identifying simulated actions.

## Agent loop to implement / demonstrate
1. Parse the request into structured intent.
2. Ask for missing required fields.
3. Make a plan with discrete tool calls.
4. Call only tools needed for the plan.
5. Read back persisted records to verify state.
6. If a safe, recoverable validation error occurs, retry at most once after correcting the input.
7. Stop and ask the user when information is uncertain or action is consequential.
8. Report completed, failed, and pending steps separately.

## Trust and safety
- Never invent a return window. Treat a policy as verified only when the user supplies a source or the app retrieves a reliable source.
- Claim drafts are never sent automatically.
- Never promise a refund or legal outcome.
- Use synthetic data in the demo.
- Future production hardening: authentication, authorization, rate limiting, audit log, encryption, data deletion, secret management, tests, and policy-source provenance.

## Stretch goals (only after MVP works)
- OCR for receipt images.
- Search a small, source-cited policy knowledge base.
- Optional Amazon Bedrock provider adapter.
- Simulated Alexa+ voice experience.
- Demo-only failure injection to show bounded recovery.
- Export case timeline as Markdown or PDF.

## Success criteria
- A new case persists and survives refresh.
- Missing policy data produces “unknown,” not an invented deadline.
- Draft generation uses stored case facts.
- Follow-ups persist and appear in the case detail.
- MCP tools can create, list, update, draft, and verify a case.
- Demo distinguishes real local database operations from simulated notifications.
