import os
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

DB_PATH = os.getenv("DATABASE_PATH", "refund_guardian.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            retailer TEXT NOT NULL,
            purchase_date TEXT NOT NULL,
            purchase_price REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'INR',
            issue_description TEXT NOT NULL,
            policy_days INTEGER,
            policy_source TEXT,
            deadline TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS followups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            due_date TEXT NOT NULL,
            note TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        """)
        conn.commit()

def _validate_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("Dates must use YYYY-MM-DD format.")

def row_to_dict(row):
    return dict(row) if row else None

def create_case(data: dict[str, Any]) -> dict:
    purchase = _validate_date(data["purchase_date"])
    days = data.get("policy_days")
    deadline = (purchase + timedelta(days=int(days))).isoformat() if days is not None else None
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    with get_conn() as conn:
        cur = conn.execute("""
          INSERT INTO cases(product_name, retailer, purchase_date, purchase_price, currency,
          issue_description, policy_days, policy_source, deadline, status, notes, created_at)
          VALUES(?,?,?,?,?,?,?,?,?,'new','',?)
        """, (data["product_name"].strip(), data["retailer"].strip(), purchase.isoformat(),
              float(data["purchase_price"]), data.get("currency", "INR").upper(),
              data["issue_description"].strip(), days, data.get("policy_source"), deadline, now))
        conn.commit()
        row = conn.execute("SELECT * FROM cases WHERE id=?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row)

def list_cases() -> list[dict]:
    with get_conn() as conn:
        return [row_to_dict(r) for r in conn.execute(
            "SELECT * FROM cases ORDER BY created_at DESC, id DESC").fetchall()]

def get_case(case_id: int) -> dict | None:
    with get_conn() as conn:
        return row_to_dict(conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone())

def update_case(case_id: int, updates: dict) -> dict | None:
    allowed = {"status", "notes"}
    updates = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if not updates:
        return get_case(case_id)
    if "status" in updates and updates["status"] not in {
        "new", "in_progress", "waiting_for_user", "resolved", "closed"
    }:
        raise ValueError("Unsupported status.")
    current = get_case(case_id)
    if not current:
        return None
    merged_notes = updates.get("notes", current["notes"])
    fields = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [case_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE cases SET {fields} WHERE id=?", values)
        conn.commit()
    return get_case(case_id)

def create_followup(case_id: int, due_date: str, note: str) -> dict | None:
    _validate_date(due_date)
    if not get_case(case_id):
        return None
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO followups(case_id,due_date,note,created_at) VALUES(?,?,?,?)",
            (case_id, due_date, note.strip(), now))
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM followups WHERE id=?",
                                        (cur.lastrowid,)).fetchone())

def list_followups(case_id: int) -> list[dict]:
    with get_conn() as conn:
        return [row_to_dict(r) for r in conn.execute(
            "SELECT * FROM followups WHERE case_id=? ORDER BY due_date, id",
            (case_id,)).fetchall()]

def draft_claim(case_data: dict) -> dict:
    # This is a draft for user review, not an automatically sent message.
    deadline_note = (
        f"The return-window date recorded in my notes is {case_data['deadline']} "
        f"(source: {case_data.get('policy_source') or 'not recorded'})."
        if case_data.get("deadline") else
        "Please confirm the applicable return or warranty terms and any relevant deadline."
    )

    message = f"""Hello {case_data['retailer']} support,

I purchased {case_data['product_name']} on {case_data['purchase_date']} for \
{case_data['currency']} {case_data['purchase_price']:.2f}. The issue is:
{case_data['issue_description']}

{deadline_note}

Could you please advise on the applicable return, replacement, repair, or warranty process and the evidence you need? I can provide the receipt and any requested troubleshooting details.

Thank you."""

    return {
        "case_id": case_data["id"],
        "draft": message,
        "warning": "Draft only. Review the facts and retailer policy before sending."
    }

def parse_receipt_text(text: str) -> dict:
    """Lightweight demo parser. It does not perform OCR and may miss formats."""
    result = {}
    # Common demo patterns: Product: Headphones; Retailer: Example Store; Date: 2026-10-12
    patterns = {
        "product_name": r"(?im)^\s*(?:product|item)\s*:\s*(.+?)\s*$",
        "retailer": r"(?im)^\s*(?:retailer|store|merchant)\s*:\s*(.+?)\s*$",
        "purchase_date": r"(?im)^\s*(?:purchase date|date)\s*:\s*(\d{4}-\d{2}-\d{2})\s*$",
        "purchase_price": r"(?im)^\s*(?:total|price|amount)\s*:\s*(?:INR|₹|Rs\.?)?\s*([\d,]+(?:\.\d{1,2})?)\s*$",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            value = match.group(1).strip()
            if key == "purchase_price":
                result[key] = float(value.replace(",", ""))
            else:
                result[key] = value
    result["parser_note"] = "Demo text parser only; check every extracted field before saving."
    return result

	
def analyze_eligibility(case_data: dict, as_of: date | None = None) -> dict:
    """Assess the recorded return window without guaranteeing a refund."""
    today = as_of or date.today()

    policy_days = case_data.get("policy_days")
    deadline = case_data.get("deadline")
    source = case_data.get("policy_source")

    result = {
        "case_id": case_data["id"],
        "assessment": "unknown",
        "explanation": "",
        "policy_evidence": {
            "policy_days": policy_days,
            "policy_source": source,
            "deadline": deadline,
        },
        "missing_information": [],
        "recommended_next_steps": [],
        "warning": (
            "This is a preliminary return-window assessment, "
            "not a guarantee of refund eligibility."
        ),
    }

    if policy_days is None or deadline is None:
        result["explanation"] = (
            "No return window has been recorded, so the deadline "
            "cannot be assessed."
        )
        result["missing_information"].append(
            "Verified retailer return or warranty policy"
        )
        result["recommended_next_steps"].append(
            "Check the retailer's applicable policy."
        )
        return result

    deadline_date = _validate_date(deadline)

    if today <= deadline_date:
        result["assessment"] = "within_recorded_window"
        result["explanation"] = (
            f"The recorded deadline is {deadline_date.isoformat()}, "
            "which has not passed."
        )
        result["recommended_next_steps"].append(
            "Contact the retailer promptly and confirm applicable conditions."
        )
    else:
        result["assessment"] = "outside_recorded_window"
        result["explanation"] = (
            f"The recorded deadline was {deadline_date.isoformat()}, "
            "which has passed."
        )
        result["recommended_next_steps"].append(
            "Ask the retailer whether warranty, repair, or an exception applies."
        )

    result["missing_information"].append(
        "Confirmation of retailer-specific conditions and exceptions"
    )

    return result