from datetime import date

from tests.dbtools import use_fresh_db
from app import services


def setup_function():
    use_fresh_db()
    services.init_db()


def test_deadline_tracker_approaching():
    case = services.create_case({
        "product_name": "Headphones",
        "retailer": "Example Store",
        "purchase_date": "2026-10-10",
        "purchase_price": 2000,
        "currency": "INR",
        "issue_description": "Headphones arrived broken",
        "policy_days": 30,
        "policy_source": "Example Store return policy",
        "policy_confirmed": True,
    })

    results = services.get_deadline_tracker(today=date(2026, 11, 5))
    item = next(x for x in results if x["case_id"] == case["id"])

    assert item["deadline"] == "2026-11-09"
    assert item["days_remaining"] == 4
    assert item["deadline_status"] == "approaching"


def test_deadline_tracker_expired():
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

    results = services.get_deadline_tracker(today=date(2026, 10, 5))
    item = next(x for x in results if x["case_id"] == case["id"])

    assert item["deadline_status"] == "expired"
    assert item["days_remaining"] < 0