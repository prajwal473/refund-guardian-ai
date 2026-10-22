import logging
import os
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.models import (CaseCreate, CaseUpdate, EligibilityRequest, EligibilityResponse,
                        FollowupCreate, ReceiptTextRequest)
from app import services
import csv
import io
from fastapi.responses import StreamingResponse

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
@app.get("/api/cases/export")
def export_cases():
    import csv
    import io
    from fastapi.responses import StreamingResponse

    cases = services.list_cases()
    output = io.StringIO()

    if not cases:
        output.write("No cases available\n")
    else:
        writer = csv.DictWriter(output, fieldnames=cases[0].keys())
        writer.writeheader()
        writer.writerows(cases)

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="refund_cases.csv"'
        },
    )

@app.post("/api/cases/import")
async def import_cases(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a CSV file.")

    try:
        content = await file.read()

        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(413, "CSV file must be 5 MB or smaller.")

        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))

        required_fields = {
            "product_name",
            "retailer",
            "purchase_date",
            "purchase_price",
            "issue_description",
        }

        if not reader.fieldnames:
            raise HTTPException(400, "The CSV file is empty or has no header.")

        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise HTTPException(400, "The CSV contains duplicate column names.")

        missing = required_fields - set(reader.fieldnames)
        if missing:
            raise HTTPException(
                400,
                detail=f"Missing required columns: {', '.join(sorted(missing))}",
            )

        existing = services.list_cases()
        existing_keys = {
            (
                str(case.get("product_name", "")).strip().casefold(),
                str(case.get("retailer", "")).strip().casefold(),
                str(case.get("purchase_date", "")).strip(),
            )
            for case in existing
        }

        imported = 0
        rejected = []
        seen_in_file = set()

        for row_number, row in enumerate(reader, start=2):
            try:
                if None in row:
                    raise ValueError("Row contains more values than the CSV header.")

                data = {
                    key: (value.strip() if value is not None else "")
                    for key, value in row.items()
                }

                case_data = CaseCreate(**data)
                validated = case_data.model_dump()

                key = (
                    validated["product_name"].strip().casefold(),
                    validated["retailer"].strip().casefold(),
                    validated["purchase_date"].strip(),
                )

                if key in existing_keys or key in seen_in_file:
                    raise ValueError("Duplicate case detected.")

                services.create_case(validated)
                seen_in_file.add(key)
                imported += 1

            except Exception as exc:
                rejected.append({
                    "row": row_number,
                    "reason": str(exc),
                })

        return {
            "imported": imported,
            "rejected_count": len(rejected),
            "rejected": rejected,
        }

    except UnicodeDecodeError:
        raise HTTPException(400, "The CSV file must use UTF-8 encoding.")
    finally:
        await file.close()

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

@app.get("/api/cases/search")
def search_cases(
    q: str = "",
    status: str | None = None,
    priority: str | None = None,
    deadline_status: str | None = None,
    sort_by: str = "purchase_date",
):
    try:
        return services.search_cases(
            query=q,
            status=status,
            priority=priority,
            deadline_status=deadline_status,
            sort_by=sort_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

