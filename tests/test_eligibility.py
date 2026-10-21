"""Tests for the eligibility engine and optional LLM adapter (no web framework needed).

All dates are passed in explicitly, so results never depend on the real current date.
Policy rule under test: a policy source is only a note. Eligibility outcomes need the user's own
confirmation (policy_confirmed); Refund Guardian never verifies a retailer policy itself.
"""
import os
import urllib.error
from datetime import date
from unittest import mock

from tests.dbtools import use_fresh_db  # keeps DATABASE_PATH pointed at a temp location
from app import services

use_fresh_db()

TODAY = date(2026, 10, 15)
GOOD_SOURCE = "Retailer returns page https://store.test/returns"


def make_case(**over):
    case = {
        "id": 1, "product_name": "Headphones", "retailer": "Store", "purchase_date": "2026-10-01",
        "purchase_price": 100.0, "currency": "INR", "issue_description": "Audio cuts out every few minutes",
        "policy_days": 30, "policy_source": GOOD_SOURCE, "policy_confirmed": True,
        "deadline": "2026-10-31", "status": "new",
    }
    case.update(over)
    return case


def run(**over):
    return services.analyze_eligibility(make_case(**over), today=TODAY)


# ---------------- deterministic engine ----------------
def test_within_known_window():
    r = run()
    assert r["outcome"] == "potentially_eligible"
    assert r["policy_status"] == "user_confirmed"
    assert r["policy_confirmed_by_user"] is True
    assert r["policy_verified"] is False             # Refund Guardian never verifies a policy itself
    assert r["deadline"] == "2026-10-31"
    assert r["days_remaining"] == 16
    assert r["analysis_method"] == "rule_based"
    assert r["missing_information"] == []
    assert r["ai_explanation"] is None
    assert "does not guarantee" in " ".join(r["caveats"]).lower()
    assert "has not verified" in r["explanation"]


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
    assert r["policy_status"] == "missing"
    assert r["policy_confirmed_by_user"] is False    # a stray confirmation without a window is ignored
    assert r["deadline"] is None and r["days_remaining"] is None
    assert any("return window length" in m for m in r["missing_information"])
    assert any("confirmation is recorded" in c for c in r["caveats"])


def test_missing_policy_source_still_unverified():
    for source in (None, "", "   ", "x"):
        r = run(policy_source=source)
        assert r["outcome"] == "needs_policy_verification", source
        assert r["policy_confirmed_by_user"] is False
        assert any("policy source" in m for m in r["missing_information"])
        assert r["deadline"] == "2026-10-31"            # provisional, flagged as unconfirmed
        assert "do not rely on it" in r["explanation"]


def test_source_text_alone_never_implies_verification():
    # Whatever the source says (URL, prose, junk, or "demo"), it is just a note. Without the user's
    # own confirmation the outcome is needs_policy_verification.
    for source in (GOOD_SOURCE, "https://store.test/returns", "DEMO ONLY - illustrative 10-day window",
                   "idk", "asdf", "I think it is 30 days", "Verified by the manager", "Official policy page"):
        r = run(policy_source=source, policy_confirmed=False)
        assert r["outcome"] == "needs_policy_verification", source
        assert r["policy_status"] == "unconfirmed", source
        assert r["policy_verified"] is False and r["policy_confirmed_by_user"] is False
        assert any("confirmation" in m for m in r["missing_information"])
        assert "unconfirmed" in r["explanation"]


def test_no_text_matching_heuristic_in_either_direction():
    # Real-looking names containing old "placeholder" substrings are not penalised once the user confirmed...
    for source in ("Demoulas Market returns page", "Sampler Outlet policy page"):
        assert run(policy_source=source)["outcome"] == "potentially_eligible", source
    # ...and the engine does not claim to have judged the text of the source.
    assert run(policy_source="DEMO ONLY")["policy_status"] == "user_confirmed"


def test_unverified_outside_window_is_not_reported_as_outside():
    r = services.analyze_eligibility(
        make_case(purchase_date="2026-08-01", policy_confirmed=False), today=TODAY)
    assert r["outcome"] == "needs_policy_verification"
    assert "outside the window" not in r["explanation"]


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
    keys = {"case_id", "outcome", "outcome_label", "explanation", "policy_verified", "policy_confirmed_by_user",
            "policy_status", "as_of", "deadline", "days_remaining", "missing_information",
            "recommended_next_steps", "caveats", "analysis_method", "ai_explanation", "llm_note"}
    for over in ({}, {"policy_days": None}, {"purchase_date": ""}, {"purchase_date": "2026-01-01"},
                 {"policy_confirmed": False}, {"issue_description": ""}):
        r = run(**over)
        assert keys <= set(r)
        assert r["outcome"] in services.OUTCOME_LABELS
        assert r["policy_status"] in services.POLICY_STATUSES
        assert r["policy_verified"] is False
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


# ---------------- insufficient information must never claim eligibility ----------------
def test_insufficient_information_never_establishes_eligibility():
    for over in ({"purchase_date": ""}, {"purchase_date": "garbage"}, {"purchase_date": "2026-12-01"},
                 {"issue_description": "bad"}, {"policy_days": -5}, {"policy_days": 99999}, {"policy_days": True}):
        r = run(**over)
        assert r["outcome"] == "insufficient_information", over
        assert r["deadline"] is None and r["days_remaining"] is None, over     # no date presented as established
        assert r["policy_status"] == "not_evaluated", over
        assert r["policy_confirmed_by_user"] is False and r["policy_verified"] is False, over
        text = (r["explanation"]).lower()
        assert "no eligibility conclusion" in text
        assert "appears to be within" not in text and "appears to be outside" not in text
        assert "potentially" not in text


def test_valid_window_but_short_issue_does_not_show_a_deadline():
    r = run(issue_description="bad")
    assert r["outcome"] == "insufficient_information"
    assert r["deadline"] is None


def test_date_overflow_is_insufficient_information_not_a_crash():
    far = date(9999, 12, 31)
    r = services.analyze_eligibility(make_case(purchase_date="9999-12-31", policy_days=30, deadline=None), today=far)
    assert r["outcome"] == "insufficient_information"
    assert "supported date range" in r["explanation"]


def test_lenient_date_formats_are_not_accepted():
    for odd in ("20261001", "2026-W40-4", "2026-10-1"):
        assert run(purchase_date=odd)["outcome"] == "insufficient_information", odd


def test_confirmation_without_source_is_ignored():
    r = run(policy_source=None, policy_confirmed=True)
    assert r["outcome"] == "needs_policy_verification" and r["policy_confirmed_by_user"] is False


def test_legacy_case_without_confirmation_field_is_unconfirmed():
    case = make_case()
    del case["policy_confirmed"]
    r = services.analyze_eligibility(case, today=TODAY)
    assert r["outcome"] == "needs_policy_verification" and r["policy_status"] == "unconfirmed"


# ---------------- AI explanation stays advisory ----------------
def test_ai_explanation_with_promise_or_verification_claim_is_discarded():
    for bad in ("You will be refunded in full.", "Refund Guardian verified the retailer policy.",
                "You are entitled to your money back.", "We checked the store's website and it is fine."):
        fake = {"content": [{"type": "text", "text": bad}]}
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}), mock.patch.object(services, "_post_json", return_value=fake):
            r = services.add_llm_explanation(run())
        assert r["ai_explanation"] is None and r["analysis_method"] == "rule_based", bad
        assert "discarded" in r["llm_note"]


def test_ai_receives_policy_status_but_no_free_text():
    fake = {"content": [{"type": "text", "text": "Your window appears to end on 2026-10-31, based on what you confirmed."}]}
    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}), \
         mock.patch.object(services, "_post_json", return_value=fake) as post:
        r = services.add_llm_explanation(run())
    body = post.call_args.args[2]
    sent = body["messages"][0]["content"]
    assert "policy_status" in sent and "user_confirmed" in sent
    assert "Audio cuts out" not in sent and "store.test" not in sent       # issue text and source are never sent
    assert "never say or imply that refund guardian" in body["system"].lower()
    assert r["outcome"] == "potentially_eligible"                           # the AI cannot change the verdict
