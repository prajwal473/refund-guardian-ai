"""MCP tool tests. They call the tool functions directly (they are plain functions), so they verify
the tools' logic but NOT the MCP wire protocol. Skipped automatically when the `mcp` SDK is absent."""
from datetime import date
from unittest import mock

import pytest

from tests.dbtools import use_fresh_db
from app import services

pytest.importorskip("mcp")
import mcp_server  # noqa: E402

TODAY = date(2026, 10, 15)
SOURCE = "Retailer returns page https://store.test/returns"


def setup_function():
    use_fresh_db()


def fixed_today():
    return mock.patch.object(services, "_today", return_value=TODAY)


def _create(**over):
    args = dict(product_name="Headphones", retailer="Store", purchase_date="2026-10-01", purchase_price=100.0,
                issue_description="Audio cuts out often", currency="INR", policy_days=30, policy_source=SOURCE)
    args.update(over)
    with fixed_today():
        return mcp_server.create_refund_case(**args)


def test_status_update_without_notes_preserves_existing_notes():
    cid = _create()["id"]
    services.update_case(cid, {"notes": "Called support, ref #123"})
    result = mcp_server.update_case_status(cid, "in_progress")            # notes omitted
    assert result["status"] == "in_progress"
    assert result["notes"] == "Called support, ref #123"
    assert mcp_server.update_case_status(cid, "waiting_for_user", None)["notes"] == "Called support, ref #123"
    assert services.get_case(cid)["notes"] == "Called support, ref #123"


def test_explicit_notes_replace_or_clear():
    cid = _create()["id"]
    services.update_case(cid, {"notes": "old"})
    assert mcp_server.update_case_status(cid, "resolved", "Refund received")["notes"] == "Refund received"
    assert mcp_server.update_case_status(cid, "closed", "")["notes"] == ""


def test_update_errors_are_returned_not_raised():
    cid = _create()["id"]
    assert "Unsupported status" in mcp_server.update_case_status(cid, "bogus")["error"]
    assert "not found" in mcp_server.update_case_status(99999, "closed")["error"]


BAD_CREATIONS = [
    {"product_name": ""}, {"product_name": "   "}, {"purchase_price": -1.0}, {"currency": "XX"},
    {"policy_days": -1}, {"policy_days": 99999}, {"purchase_date": "nope"}, {"purchase_date": "2026-02-30"},
    {"purchase_date": "9999-12-31"}, {"purchase_date": "2026-10-16"},
    {"policy_confirmed": True, "policy_source": None},
]


def test_invalid_creation_returns_a_clear_error_and_stores_nothing():
    for over in BAD_CREATIONS:
        result = _create(**over)
        assert "error" in result and result["details"], over
        assert "Traceback" not in str(result)
    assert services.list_cases() == []


def test_web_and_mcp_creation_paths_reject_exactly_the_same_inputs():
    for over in BAD_CREATIONS:
        with fixed_today():
            try:
                services.create_case({"product_name": "Headphones", "retailer": "Store", "purchase_date": "2026-10-01",
                                      "purchase_price": 100.0, "issue_description": "Audio cuts out often",
                                      "currency": "INR", "policy_days": 30, "policy_source": SOURCE, **over})
                web_rejected = False
            except services.CaseValidationError:
                web_rejected = True
        assert web_rejected, over
        assert "error" in _create(**over), over


def test_valid_creation_and_analysis_through_mcp():
    case = _create(policy_confirmed=True)
    assert case["policy_confirmed"] is True and case["deadline"] == "2026-10-31"
    with fixed_today():
        analysis = mcp_server.analyze_refund_eligibility(case["id"])
    assert analysis["outcome"] == "potentially_eligible" and analysis["policy_verified"] is False
    assert "not found" in mcp_server.analyze_refund_eligibility(99999)["error"]
