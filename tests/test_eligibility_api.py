"""API tests for POST /api/cases/{case_id}/eligibility (needs fastapi + httpx from requirements.txt)."""
import os
import tempfile
import urllib.error
from datetime import date
from unittest import mock

_fd, _path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ.setdefault("DATABASE_PATH", _path)

from fastapi.testclient import TestClient

from app import services
from app.main import app

client = TestClient(app)
TODAY = date(2026, 10, 15)
GOOD_SOURCE = "Retailer returns page https://store.test/returns"
RESPONSE_KEYS = {"case_id", "outcome", "outcome_label", "explanation", "policy_verified", "as_of", "deadline",
                 "days_remaining", "missing_information", "recommended_next_steps", "caveats",
                 "analysis_method", "ai_explanation", "llm_note"}


def setup_function():
    services.init_db()
    with services.get_conn() as conn:
        conn.execute("DELETE FROM followups")
        conn.execute("DELETE FROM cases")
        conn.commit()


def _case(**over):
    payload = {"product_name": "Headphones", "retailer": "Store", "purchase_date": "2026-10-01",
               "purchase_price": 100, "currency": "INR", "issue_description": "Audio cuts out often",
               "policy_days": 30, "policy_source": GOOD_SOURCE}
    payload.update(over)
    res = client.post("/api/cases", json=payload)
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _analyze(case_id, **kwargs):
    # Fixed "today" and no provider key so the test never depends on the clock or the network.
    with mock.patch.object(services, "_today", return_value=TODAY), mock.patch.dict(os.environ):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        return client.post(f"/api/cases/{case_id}/eligibility", **kwargs)


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
    assert data["policy_verified"] is True


def test_outside_window():
    cid = _case(purchase_date="2026-08-01")
    assert _analyze(cid).json()["outcome"] == "outside_known_window"


def test_missing_policy_and_unverified_source():
    no_policy = _case(policy_days=None, policy_source=None)
    data = _analyze(no_policy).json()
    assert data["outcome"] == "needs_policy_verification" and data["deadline"] is None
    demo = _case(policy_source="DEMO ONLY — illustrative")
    data = _analyze(demo).json()
    assert data["outcome"] == "needs_policy_verification" and data["policy_verified"] is False


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
    with mock.patch.object(services, "_today", return_value=TODAY), \
         mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), \
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
    with mock.patch.object(services, "_today", return_value=TODAY), \
         mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), \
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


def test_existing_routes_still_work():
    cid = _case()
    assert client.get(f"/api/cases/{cid}").status_code == 200
    assert client.post(f"/api/cases/{cid}/draft").status_code == 200