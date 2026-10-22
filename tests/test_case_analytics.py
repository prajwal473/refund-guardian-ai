from datetime import date

from tests.dbtools import use_fresh_db
from app import services


def setup_function():
    use_fresh_db()
    services.init_db()


def test_case_analytics_empty():
    result = services.get_case_analytics(today=date(2026, 10, 22))

    assert result["total_cases"] == 0
    assert result["high_priority_cases"] == 0
    assert result["overdue_followups"] == 0
    assert result["approaching_deadlines"] == 0
    assert result["cases_by_status"] == {}


def test_case_analytics_counts_cases():
    services.create_case({
        "product_name": "Headphones",
        "retailer": "Example Store",
        "purchase_date": "2026-10-10",
        "purchase_price": 2000,
        "currency": "INR",
        "issue_description": "Headphones arrived broken",
    })

    result = services.get_case_analytics(today=date(2026, 10, 22))

    assert result["total_cases"] == 1
    assert sum(result["cases_by_status"].values()) == 1