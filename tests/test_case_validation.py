"""Regression tests: case validation, date safety, notes preservation, DB migration.

Dates are controlled by patching services._today, so nothing depends on the real clock.
"""
import os
import sqlite3
from datetime import date
from unittest import mock

from tests.dbtools import use_fresh_db
from app import services

TODAY = date(2026, 10, 15)
SOURCE = "Retailer returns page https://store.test/returns"


def setup_function():
    use_fresh_db()


def valid(**over):
    data = {"product_name": "Headphones", "retailer": "Store", "purchase_date": "2026-10-01",
            "purchase_price": 100, "currency": "INR", "issue_description": "Audio cuts out often",
            "policy_days": 30, "policy_source": SOURCE}
    data.update(over)
    return data


def create(**over):
    with mock.patch.object(services, "_today", return_value=TODAY):
        return services.create_case(valid(**over))


def assert_rejected(fragment, **over):
    """The case must be refused with a message containing `fragment`, and nothing may be stored."""
    try:
        create(**over)
    except services.CaseValidationError as exc:
        assert any(fragment.lower() in m.lower() for m in exc.errors), (fragment, exc.errors)
        assert "Traceback" not in str(exc)
    else:
        raise AssertionError(f"invalid case was accepted: {over}")
    assert services.list_cases() == [], f"invalid case was stored: {over}"


# ---------------- creation: valid path and the deadline convention ----------------
def test_valid_case_is_created_and_normalised():
    item = create(product_name="  Headphones ", currency=" usd ")
    assert item["product_name"] == "Headphones"
    assert item["currency"] == "USD"
    assert item["policy_confirmed"] is False          # a real boolean, defaulting to "not confirmed"
    assert item["status"] == "new"


def test_deadline_convention_is_unchanged():
    assert create()["deadline"] == "2026-10-31"                        # purchase date + policy days
    assert create(policy_days=0)["deadline"] == "2026-10-01"
    assert create(policy_days=None, policy_source=None)["deadline"] is None   # unknown window -> no deadline


# ---------------- creation: invalid input ----------------
def test_blank_or_missing_names_and_issue_rejected():
    for bad in ("", "   ", None, 123):
        assert_rejected("Product name", product_name=bad)
        assert_rejected("Retailer", retailer=bad)
    assert_rejected("Issue description", issue_description="bad")
    assert_rejected("Issue description", issue_description="    ")


def test_overlong_text_rejected():
    assert_rejected("at most 160", product_name="x" * 161)
    assert_rejected("at most 500", policy_source="x" * 501)


def test_negative_or_non_numeric_price_rejected():
    for bad in (-0.01, -5, float("nan"), float("inf"), True, "10", None):
        assert_rejected("price", purchase_price=bad)
    assert create(purchase_price=0)["purchase_price"] == 0.0           # free items are allowed


def test_unsupported_currency_rejected():
    for bad in ("XX", "ABCD", "", "BTC", None, 5):
        assert_rejected("currency", currency=bad)


def test_negative_or_invalid_policy_days_rejected():
    for bad in (-1, 3651, True, 10.5, "10"):
        assert_rejected("Policy days", policy_days=bad)
    assert create(policy_days=3650)["policy_days"] == 3650


def test_malformed_purchase_dates_rejected():
    for bad in ("", "nope", "2026-13-01", "2026-02-30", "20261001", "2026-10-1", "10/01/2026", None, 20261001):
        assert_rejected("Purchase date", purchase_date=bad)


def test_future_purchase_date_rejected_but_today_allowed():
    assert_rejected("future", purchase_date="2026-10-16")
    assert_rejected("future", purchase_date="9999-12-31")              # must be a clean error, never an OverflowError / HTTP 500
    assert create(purchase_date="2026-10-15")["purchase_date"] == "2026-10-15"


def test_implausibly_old_purchase_date_rejected():
    assert_rejected("on or after", purchase_date="1899-12-31")


def test_date_arithmetic_overflow_is_a_validation_error_not_a_crash():
    data = valid(purchase_date="9999-12-31", policy_days=30)
    try:
        services.validate_case_input(data, today=date(9999, 12, 31))
    except services.CaseValidationError as exc:
        assert any("supported date range" in m for m in exc.errors), exc.errors
    else:
        raise AssertionError("overflowing deadline was accepted")


def test_all_problems_are_reported_together():
    try:
        create(product_name="", purchase_price=-1, currency="XX", policy_days=-3, purchase_date="nope")
    except services.CaseValidationError as exc:
        assert len(exc.errors) >= 5, exc.errors
        assert str(exc) == "; ".join(exc.errors)
    else:
        raise AssertionError("accepted")
    assert services.list_cases() == []


def test_policy_confirmation_requires_window_and_source():
    assert_rejected("requires both", policy_confirmed=True, policy_days=None)
    assert_rejected("requires both", policy_confirmed=True, policy_source=None)
    assert_rejected("requires both", policy_confirmed=True, policy_source="   ")
    assert_rejected("true or false", policy_confirmed="yes")
    item = create(policy_confirmed=True)
    assert item["policy_confirmed"] is True
    assert services.get_case(item["id"])["policy_confirmed"] is True


# ---------------- notes: omitted vs explicit ----------------
def _case_with_notes(text="Called support, ref #123"):
    item = create()
    services.update_case(item["id"], {"notes": text})
    return item["id"]


def test_status_update_without_notes_preserves_existing_notes():
    cid = _case_with_notes()
    assert services.update_case(cid, {"status": "in_progress"})["notes"] == "Called support, ref #123"
    assert services.update_case(cid, {"status": "resolved", "notes": None})["notes"] == "Called support, ref #123"
    assert services.get_case(cid)["status"] == "resolved"


def test_explicit_empty_notes_clears_and_text_replaces():
    cid = _case_with_notes()
    assert services.update_case(cid, {"notes": "New note"})["notes"] == "New note"
    assert services.update_case(cid, {"status": "closed", "notes": ""})["notes"] == ""


def test_update_validation():
    cid = _case_with_notes()
    try:
        services.update_case(cid, {"status": "bogus"})
    except ValueError as exc:
        assert "Unsupported status" in str(exc)
    else:
        raise AssertionError("bad status accepted")
    try:
        services.update_case(cid, {"notes": "x" * 3001})
    except services.CaseValidationError:
        pass
    else:
        raise AssertionError("overlong notes accepted")
    assert services.get_case(cid)["notes"] == "Called support, ref #123"
    assert services.update_case(99999, {"status": "closed"}) is None


# ---------------- follow-ups ----------------
def test_followup_validation():
    cid = create()["id"]
    for bad_date in ("", "tomorrow", "2026-02-30", "20261101"):
        try:
            services.create_followup(cid, bad_date, "Check reply")
        except services.CaseValidationError as exc:
            assert any("Follow-up date" in m for m in exc.errors)
        else:
            raise AssertionError(f"accepted {bad_date!r}")
    try:
        services.create_followup(cid, "2026-11-01", " x ")
    except services.CaseValidationError:
        pass
    else:
        raise AssertionError("short note accepted")
    assert services.create_followup(99999, "2026-11-01", "Check reply") is None
    assert services.list_followups(cid) == []
    assert services.create_followup(cid, "2026-11-01", "Check reply")["case_id"] == cid


# ---------------- database migration ----------------
def test_old_database_without_policy_confirmed_is_migrated_honestly():
    old_path = os.path.join(os.path.dirname(services.DB_PATH), "legacy.db")
    conn = sqlite3.connect(old_path)
    conn.executescript("""
        CREATE TABLE cases (id INTEGER PRIMARY KEY AUTOINCREMENT, product_name TEXT NOT NULL, retailer TEXT NOT NULL,
          purchase_date TEXT NOT NULL, purchase_price REAL NOT NULL, currency TEXT NOT NULL DEFAULT 'INR',
          issue_description TEXT NOT NULL, policy_days INTEGER, policy_source TEXT, deadline TEXT,
          status TEXT NOT NULL DEFAULT 'new', notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
        INSERT INTO cases(product_name,retailer,purchase_date,purchase_price,issue_description,policy_days,policy_source,deadline,created_at)
        VALUES('Old item','Old store','2026-10-01',50,'Stopped working',30,'Some source','2026-10-31','2026-10-02T00:00:00Z');
    """)
    conn.commit(); conn.close()
    services.DB_PATH = old_path
    services.init_db()
    services.init_db()                                       # idempotent
    legacy = services.get_case(1)
    assert legacy["policy_confirmed"] is False               # nobody attested to this policy
    result = services.analyze_eligibility(legacy, today=TODAY)
    assert result["outcome"] == "needs_policy_verification"
