"""API tests (need fastapi + httpx from requirements.txt): eligibility, validation, notes, receipts.

Every test gets its own empty database, and "today" is patched to a fixed date.
"""
import os
import urllib.error
from datetime import date
from unittest import mock

from tests.dbtools import use_fresh_db

from fastapi.testclient import TestClient

from app import services
from app.main import app

client = TestClient(app)
TODAY = date(2026, 10, 15)
GOOD_SOURCE = "Retailer returns page https://store.test/returns"
RESPONSE_KEYS = {"case_id", "outcome", "outcome_label", "explanation", "policy_verified", "policy_confirmed_by_user",
                 "policy_status", "as_of", "deadline", "days_remaining", "missing_information",
                 "recommended_next_steps", "caveats", "analysis_method", "ai_explanation", "llm_note"}


def setup_function():
    use_fresh_db()


def fixed_today():
    return mock.patch.object(services, "_today", return_value=TODAY)


def _payload(**over):
    payload = {"product_name": "Headphones", "retailer": "Store", "purchase_date": "2026-10-01",
               "purchase_price": 100, "currency": "INR", "issue_description": "Audio cuts out often",
               "policy_days": 30, "policy_source": GOOD_SOURCE, "policy_confirmed": True}
    payload.update(over)
    return payload


def _case(**over):
    with fixed_today():
        res = client.post("/api/cases", json=_payload(**over))
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _analyze(case_id, **kwargs):
    # Fixed "today" and no provider key, so the test never depends on the clock or the network.
    with fixed_today(), mock.patch.dict(os.environ):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        return client.post(f"/api/cases/{case_id}/eligibility", **kwargs)


# ---------------- eligibility endpoint ----------------
def test_success_within_window():
    cid = _case()
    res = _analyze(cid)
    assert res.status_code == 200
    data = res.json()
    assert RESPONSE_KEYS <= set(data)
    assert data["case_id"] == cid
    assert data["outcome"] == "potentially_eligible"
    assert data["deadline"] == "2026-10-31" and data["days_remaining"] == 16
    assert data["analysis_method"] == "rule_based"
    assert data["policy_status"] == "user_confirmed" and data["policy_verified"] is False


def test_outside_window():
    cid = _case(purchase_date="2026-08-01")
    assert _analyze(cid).json()["outcome"] == "outside_known_window"


def test_missing_and_unconfirmed_policy():
    no_policy = _case(policy_days=None, policy_source=None, policy_confirmed=False)
    data = _analyze(no_policy).json()
    assert data["outcome"] == "needs_policy_verification" and data["deadline"] is None
    unconfirmed = _case(policy_confirmed=False)
    data = _analyze(unconfirmed).json()
    assert data["outcome"] == "needs_policy_verification"
    assert data["policy_status"] == "unconfirmed" and data["policy_confirmed_by_user"] is False


def test_nonexistent_case_returns_404():
    res = _analyze(99999)
    assert res.status_code == 404
    assert res.json()["detail"] == "Case not found"


def test_invalid_case_id_and_invalid_body_are_422():
    assert client.post("/api/cases/abc/eligibility").status_code == 422
    cid = _case()
    assert client.post(f"/api/cases/{cid}/eligibility", json={"use_llm": "maybe"}).status_code == 422


def test_body_is_optional_and_use_llm_false_accepted():
    cid = _case()
    assert _analyze(cid).status_code == 200
    assert _analyze(cid, json={}).status_code == 200
    assert _analyze(cid, json={"use_llm": False}).status_code == 200


def test_provider_failure_still_returns_rule_based_result():
    cid = _case()
    with fixed_today(), mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), \
         mock.patch.object(services, "_post_json", side_effect=urllib.error.URLError("down")):
        res = client.post(f"/api/cases/{cid}/eligibility", json={"use_llm": True})
    assert res.status_code == 200
    data = res.json()
    assert data["analysis_method"] == "rule_based" and data["ai_explanation"] is None
    assert "rule-based analysis only" in data["llm_note"]
    assert "test-key" not in res.text


def test_provider_success_adds_separate_ai_field():
    cid = _case()
    fake = {"content": [{"type": "text", "text": "The window appears to end on 2026-10-31."}]}
    with fixed_today(), mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), \
         mock.patch.object(services, "_post_json", return_value=fake):
        data = client.post(f"/api/cases/{cid}/eligibility", json={}).json()
    assert data["analysis_method"] == "rule_based+llm_explanation"
    assert data["ai_explanation"].startswith("The window")
    assert data["outcome"] == "potentially_eligible" and data["deadline"] == "2026-10-31"


def test_unexpected_engine_error_is_a_clean_500():
    cid = _case()
    with mock.patch.object(services, "analyze_eligibility", side_effect=RuntimeError("secret internals")):
        res = client.post(f"/api/cases/{cid}/eligibility")
    assert res.status_code == 500
    assert res.json()["detail"] == "Eligibility analysis failed. Please try again."
    assert "secret internals" not in res.text


# ---------------- case creation validation (must be 4xx, never 500, never a stack trace) ----------------
def _post_invalid(**over):
    with fixed_today():
        res = client.post("/api/cases", json=_payload(**over))
    assert res.status_code == 422, (over, res.status_code, res.text)
    assert "Traceback" not in res.text and "File \"" not in res.text
    assert client.get("/api/cases").json() == [], f"invalid case stored: {over}"
    return res


def test_invalid_creation_inputs_are_rejected_with_422():
    _post_invalid(product_name="")
    _post_invalid(product_name="   ")
    _post_invalid(purchase_price=-1)
    _post_invalid(currency="XX")
    _post_invalid(currency="BTC")
    _post_invalid(policy_days=-1)
    _post_invalid(policy_days=99999)
    _post_invalid(purchase_date="nope")
    _post_invalid(purchase_date="2026-02-30")
    _post_invalid(purchase_date="20261001")
    _post_invalid(policy_confirmed=True, policy_source=None)


def test_future_and_overflow_purchase_dates_return_422_not_500():
    res = _post_invalid(purchase_date="9999-12-31")
    assert "future" in res.json()["detail"]
    _post_invalid(purchase_date="2026-10-16")


def test_valid_creation_reports_confirmation_as_boolean():
    cid = _case()
    case = client.get(f"/api/cases/{cid}").json()
    assert case["policy_confirmed"] is True and case["deadline"] == "2026-10-31"
    assert client.get("/api/cases").json()[0]["policy_confirmed"] is True


# ---------------- notes over REST ----------------
def test_patch_status_without_notes_preserves_notes_and_empty_string_clears():
    cid = _case()
    assert client.patch(f"/api/cases/{cid}", json={"notes": "Ref #123"}).json()["notes"] == "Ref #123"
    assert client.patch(f"/api/cases/{cid}", json={"status": "in_progress"}).json()["notes"] == "Ref #123"
    assert client.patch(f"/api/cases/{cid}", json={"status": "resolved", "notes": None}).json()["notes"] == "Ref #123"
    assert client.patch(f"/api/cases/{cid}", json={"notes": ""}).json()["notes"] == ""
    assert client.patch(f"/api/cases/{cid}", json={"status": "bogus"}).status_code == 422


# ---------------- receipt route ----------------
def test_receipt_route_never_returns_500_for_malformed_amounts():
    for text in ("Total: ,", "Total: 1,4,9,9", "Total: 99999999999", "Date: 9999-99-99", "Total: ١٢٣"):
        res = client.post("/api/receipt/parse-text", json={"text": text})
        assert res.status_code == 200, (text, res.text)
        assert "purchase_price" not in res.json() or text == "Total: ١٢٣"


def test_receipt_route_common_formats_and_ambiguity():
    body = client.post("/api/receipt/parse-text", json={"text": "Total: 1,499.00 INR\nDate: 12/10/2026"}).json()
    assert body["purchase_price"] == 1499.0 and body["currency"] == "INR"
    assert "purchase_date" not in body and body["purchase_date_candidates"] == ["2026-10-12", "2026-12-10"]
    assert body["warnings"]


def test_existing_routes_still_work():
    cid = _case()
    assert client.get(f"/api/cases/{cid}").status_code == 200
    assert client.post(f"/api/cases/{cid}/draft").status_code == 200
    assert client.post(f"/api/cases/{cid}/followups", json={"due_date": "2026-11-01", "note": "Check reply"}).status_code == 201
    assert client.post(f"/api/cases/{cid}/followups", json={"due_date": "nope", "note": "Check reply"}).status_code == 422
