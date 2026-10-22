from datetime import date

from tests.dbtools import use_fresh_db
from app import services


def setup_function():
    use_fresh_db()
    services.init_db()


def test_expired_case_has_high_priority():
    case = services.create_case({
        "product_name": "Mouse",
        "retailer": "Example Store",
        "purchase_date": "2026-09-01",
        "purchase_price": 500,
        "currency": "INR",
        "issue_description": "Mouse not working",
        "policy_days": 30,
        "policy_source": "Example Store return policy",
        "policy_confirmed": True,
    })

    results = services.get_case_priorities(today=date(2026, 10, 5))
    item = next(x for x in results if x["case_id"] == case["id"])

    assert item["priority"] == "high"
    assert item["priority_score"] == 100
    assert "Refund deadline has expired" in item["priority_reasons"]


def test_case_without_urgent_issues_has_low_priority():
    services.create_case({
        "product_name": "Keyboard",
        "retailer": "Example Store",
        "purchase_date": "2026-10-20",
        "purchase_price": 1000,
        "currency": "INR",
        "issue_description": "Keyboard not working",
        "policy_days": 30,
        "policy_source": "Example Store return policy",
        "policy_confirmed": True,
    })

    results = services.get_case_priorities(today=date(2026, 10, 22))

    assert results[0]["priority"] == "low"
    assert results[0]["priority_score"] == 0