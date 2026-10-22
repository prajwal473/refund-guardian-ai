from datetime import date

from tests.dbtools import use_fresh_db
from app import services


def setup_function():
    use_fresh_db()
    services.init_db()


def test_followup_reminders_due_today():
    case = services.create_case({
        "product_name": "Headphones",
        "retailer": "Example Store",
        "purchase_date": "2026-10-10",
        "purchase_price": 2000,
        "currency": "INR",
        "issue_description": "Item arrived broken",
    })

    services.create_followup(case["id"], "2026-10-22", "Check refund status")

    reminders = services.get_followup_reminders(today=date(2026, 10, 22))

    assert len(reminders) == 1
    assert reminders[0]["reminder_status"] == "due_today"


def test_followup_reminders_overdue():
    case = services.create_case({
        "product_name": "Mouse",
        "retailer": "Example Store",
        "purchase_date": "2026-10-01",
        "purchase_price": 500,
        "currency": "INR",
        "issue_description": "Item not working",
    })

    services.create_followup(case["id"], "2026-10-20", "Ask for an update")

    reminders = services.get_followup_reminders(today=date(2026, 10, 22))

    assert len(reminders) == 1
    assert reminders[0]["reminder_status"] == "overdue"