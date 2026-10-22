import logging
import os
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.models import (CaseCreate, CaseUpdate, EligibilityRequest, EligibilityResponse,
                        FollowupCreate, ReceiptTextRequest)
from app import services

app = FastAPI(title="Refund Guardian AI", version="0.1.0",
              description="Consumer-support case organizer demo. Does not submit claims.")
logger = logging.getLogger("refund_guardian")
services.init_db()
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/api/health")
def health():
    return {"ok": True, "app": "Refund Guardian AI", "mode": "demo"}

@app.get("/api/cases")
def cases():
    return services.list_cases()

@app.post("/api/cases", status_code=201)
def create_case(payload: CaseCreate):
    try:
        return services.create_case(payload.model_dump())
    except ValueError as e:
        raise HTTPException(422, str(e))

@app.get("/api/cases/{case_id}")
def get_case(case_id: int):
    result = services.get_case(case_id)
    if not result:
        raise HTTPException(404, "Case not found")
    return result

@app.patch("/api/cases/{case_id}")
def update_case(case_id: int, payload: CaseUpdate):
    try:
        result = services.update_case(case_id, payload.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not result:
        raise HTTPException(404, "Case not found")
    return result

@app.post("/api/cases/{case_id}/draft")
def make_draft(case_id: int):
    item = services.get_case(case_id)
    if not item:
        raise HTTPException(404, "Case not found")
    return services.draft_claim(item)

@app.post("/api/cases/{case_id}/eligibility", response_model=EligibilityResponse)
def analyze_case_eligibility(case_id: int, payload: Optional[EligibilityRequest] = None):
    item = services.get_case(case_id)
    if not item:
        raise HTTPException(404, "Case not found")
    use_llm = payload.use_llm if payload is not None else True
    try:
        analysis = services.analyze_eligibility(item)
        return services.add_llm_explanation(analysis, use_llm=use_llm)
    except Exception:
        logger.exception("Eligibility analysis failed for case %s", case_id)
        raise HTTPException(500, "Eligibility analysis failed. Please try again.")

@app.post("/api/cases/{case_id}/followups", status_code=201)
def add_followup(case_id: int, payload: FollowupCreate):
    try:
        result = services.create_followup(case_id, payload.due_date, payload.note)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not result:
        raise HTTPException(404, "Case not found")
    return result

@app.get("/api/cases/{case_id}/followups")
def followups(case_id: int):
    if not services.get_case(case_id):
        raise HTTPException(404, "Case not found")
    return services.list_followups(case_id)

@app.post("/api/receipt/parse-text")
def parse_receipt(payload: ReceiptTextRequest):
    try:
        return services.parse_receipt_text(payload.text)
    except Exception:
        logger.exception("Receipt parsing failed")
        raise HTTPException(500, "Could not parse the receipt text.")


@app.post("/api/cases/{case_id}/evidence-checklist")
def evidence_checklist(case_id: int):
    item = services.get_case(case_id)

    if not item:
        raise HTTPException(status_code=404, detail="Case not found")

    return services.generate_evidence_checklist(item)


@app.get("/api/deadlines")
def get_deadline_tracker():
    return services.get_deadline_tracker()

@app.get("/api/followup-reminders")
def get_followup_reminders():
    return services.get_followup_reminders()

@app.get("/api/case-priorities")
def get_case_priorities():
    return services.get_case_priorities()

@app.get("/api/case-analytics")
def get_case_analytics():
    return services.get_case_analytics()