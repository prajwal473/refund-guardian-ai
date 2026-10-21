"""Tests for the eligibility engine and optional LLM adapter (no web framework needed).

All dates are passed in explicitly, so results never depend on the real current date.
"""
import os
import tempfile
import urllib.error
from datetime import date
from unittest import mock

_fd, _path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ.setdefault("DATABASE_PATH", _path)

from app import services

TODAY = date(2026, 10, 15)
GOOD_SOURCE = "Retailer returns page https://store.test/returns"


def make_case(**over):
    case = {
        "id": 1, "product_name": "Headphones", "retailer": "Store", "purchase_date": "2026-10-01",
        "purchase_price": 100.0, "currency": "INR", "issue_description": "Audio cuts out every few minutes",
        "policy_days": 30, "policy_source": GOOD_SOURCE, "deadline": "2026-10-31", "status": "new",
    }
    case.update(over)
    return case


def run(**over):
    return services.analyze_eligibility(make_case(**over), today=TODAY)


# ---------------- deterministic engine ----------------
def test_within_known_window():
    r = run()
    assert r["outcome"] == "potentially_eligible"
    assert r["policy_verified"] is True
    assert r["deadline"] == "2026-10-31"
    assert r["days_remaining"] == 16
    assert r["analysis_method"] == "rule_based"
    assert r["missing_information"] == []
    assert r["ai_explanation"] is None
    assert "does not guarantee" in " ".join(r["caveats"]).lower()


def test_last_day_is_still_inside_and_next_day_is_outside():
    on_last_day = services.analyze_eligibility(make_case(), today=date(2026, 10, 31))
    assert on_last_day["outcome"] == "potentially_eligible"
    assert on_last_day["days_remaining"] == 0
    day_after = services.analyze_eligibility(make_case(), today=date(2026, 11, 1))
    assert day_after["outcome"] == "outside_known_window"
    assert day_after["days_remaining"] == -1


def test_outside_known_window_does_not_rule_out_other_remedies():
    r = services.analyze_eligibility(make_case(purchase_date="2026-08-01", deadline="2026-08-31"), today=TODAY)
    assert r["outcome"] == "outside_known_window"
    assert r["days_remaining"] == -45
    text = (r["explanation"] + " ".join(r["caveats"])).lower()
    assert "warranty" in text
    assert "does not necessarily rule out" in r["explanation"]


def test_missing_policy_duration():
    r = run(policy_days=None, deadline=None)
    assert r["outcome"] == "needs_policy_verification"
    assert r["policy_verified"] is False
    assert r["deadline"] is None and r["days_remaining"] is None
    assert any("return window length" in m for m in r["missing_information"])


def test_missing_policy_source_still_unverified():
    for source in (None, "", "   ", "x"):
        r = run(policy_source=source)
        assert r["outcome"] == "needs_policy_verification", source
        assert r["policy_verified"] is False
        assert any("policy source" in m for m in r["missing_information"])
        assert r["deadline"] == "2026-10-31"            # provisional, flagged as unverified
        assert "Do not rely on that date" in r["explanation"]


def test_demo_or_placeholder_source_is_unverified():
    for source in ("DEMO ONLY — illustrative 10-day window, not a real retailer policy", "TBD", "unknown"):
        r = run(policy_source=source)
        assert r["outcome"] == "needs_policy_verification", source
        assert r["policy_verified"] is False


def test_unverified_outside_window_is_not_reported_as_outside():
    r = services.analyze_eligibility(
        make_case(purchase_date="2026-08-01", policy_source="Demo policy source"), today=TODAY)
    assert r["outcome"] == "needs_policy_verification"


def test_missing_purchase_date():
    for value in (None, "", "  "):
        r = run(purchase_date=value)
        assert r["outcome"] == "insufficient_information"
        assert "purchase date" in r["missing_information"]
        assert r["deadline"] is None


def test_invalid_purchase_date():
    r = run(purchase_date="15/10/2026")
    assert r["outcome"] == "insufficient_information"
    assert "not a valid" in r["explanation"]


def test_future_purchase_date_is_inconsistent():
    r = run(purchase_date="2026-12-01")
    assert r["outcome"] == "insufficient_information"
    assert r["deadline"] is None


def test_invalid_policy_days():
    for bad in (-5, 99999, "abc", 10.5, True):
        r = run(policy_days=bad)
        assert r["outcome"] == "insufficient_information", bad
        assert r["policy_verified"] is False
        assert r["deadline"] is None


def test_zero_day_window():
    r = services.analyze_eligibility(make_case(policy_days=0, deadline="2026-10-01"), today=TODAY)
    assert r["outcome"] == "outside_known_window"


def test_stored_deadline_inconsistent_with_policy_is_recalculated():
    r = run(deadline="2026-12-25")
    assert r["deadline"] == "2026-10-31"
    assert any("differs from the recalculated" in c for c in r["caveats"])


def test_short_issue_description_is_insufficient():
    r = run(issue_description="bad")
    assert r["outcome"] == "insufficient_information"
    assert "issue description" in r["missing_information"]


def test_fault_and_closed_status_caveats():
    r = run(issue_description="Screen cracked on arrival", status="resolved")
    joined = " ".join(r["caveats"])
    assert "possible product fault" in joined
    assert "marked 'resolved'" in joined


def test_response_has_every_documented_key_and_valid_outcome():
    keys = {"case_id", "outcome", "outcome_label", "explanation", "policy_verified", "as_of", "deadline",
            "days_remaining", "missing_information", "recommended_next_steps", "caveats",
            "analysis_method", "ai_explanation", "llm_note"}
    for over in ({}, {"policy_days": None}, {"purchase_date": ""}, {"purchase_date": "2026-01-01"}):
        r = run(**over)
        assert keys <= set(r)
        assert r["outcome"] in services.OUTCOME_LABELS
        assert r["recommended_next_steps"] and r["caveats"]


def test_engine_does_not_mutate_input():
    case = make_case()
    snapshot = dict(case)
    services.analyze_eligibility(case, today=TODAY)
    assert case == snapshot


# ---------------- optional LLM explanation ----------------
def _no_key():
    env = mock.patch.dict(os.environ)
    env.start()
    os.environ.pop("ANTHROPIC_API_KEY", None)
    return env


def test_without_provider_stays_rule_based():
    env = _no_key()
    try:
        with mock.patch.object(services, "_post_json") as post:
            r = services.add_llm_explanation(run())
        post.assert_not_called()
    finally:
        env.stop()
    assert r["analysis_method"] == "rule_based"
    assert r["ai_explanation"] is None
    assert "No model provider is configured" in r["llm_note"]


def test_use_llm_false_never_calls_provider():
    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), \
         mock.patch.object(services, "_post_json") as post:
        r = services.add_llm_explanation(run(), use_llm=False)
    post.assert_not_called()
    assert r["analysis_method"] == "rule_based"
    assert r["llm_note"] is None


def test_llm_explanation_added_without_changing_facts():
    base = run()
    fake = {"content": [{"type": "text", "text": "Your window appears to run until 2026-10-31. This is not a guarantee."}]}
    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), \
         mock.patch.object(services, "_post_json", return_value=fake) as post:
        r = services.add_llm_explanation(run())
    assert r["analysis_method"] == "rule_based+llm_explanation"
    assert r["ai_explanation"].startswith("Your window")
    for k in ("outcome", "deadline", "days_remaining", "explanation", "policy_verified",
              "missing_information", "caveats", "recommended_next_steps"):
        assert r[k] == base[k], k
    # privacy: free text and the key are not sent in the prompt body
    body = post.call_args.args[2]
    assert "Audio cuts out" not in str(body) and "Headphones" not in str(body)
    assert "test-key" not in str(body)


def test_llm_failure_falls_back_to_rule_based_without_leaking_key():
    for exc in (urllib.error.URLError("boom"), TimeoutError(), ValueError("bad json")):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "secret-key-123"}), \
             mock.patch.object(services, "_post_json", side_effect=exc):
            r = services.add_llm_explanation(run())
        assert r["analysis_method"] == "rule_based"
        assert r["ai_explanation"] is None
        assert "secret-key-123" not in str(r)
        assert "rule-based analysis only" in r["llm_note"]


def test_llm_http_error_reports_status_only():
    err = urllib.error.HTTPError("https://x", 401, "Unauthorized", {}, None)
    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}), mock.patch.object(services, "_post_json", side_effect=err):
        r = services.add_llm_explanation(run())
    assert "HTTP 401" in r["llm_note"] and r["analysis_method"] == "rule_based"


def test_llm_output_with_unknown_date_is_discarded():
    fake = {"content": [{"type": "text", "text": "You have until 2027-01-01 to return it."}]}
    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}), mock.patch.object(services, "_post_json", return_value=fake):
        r = services.add_llm_explanation(run())
    assert r["ai_explanation"] is None
    assert r["analysis_method"] == "rule_based"
    assert "discarded" in r["llm_note"]


def test_llm_empty_output_falls_back():
    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}), \
         mock.patch.object(services, "_post_json", return_value={"content": []}):
        r = services.add_llm_explanation(run())
    assert r["ai_explanation"] is None and "empty" in r["llm_note"]