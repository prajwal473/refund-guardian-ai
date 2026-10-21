import os
import tempfile
from datetime import date, timedelta

# Set DB path before importing services.
_fd, _path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["DATABASE_PATH"] = _path

from app import services

def setup_function():
    with services.get_conn() as conn:
        conn.execute("DELETE FROM followups")
        conn.execute("DELETE FROM cases")
        conn.commit()

def test_create_case_and_deadline():
    services.init_db()
    purchase = date.today().isoformat()
    item = services.create_case({
        "product_name":"Demo headphones", "retailer":"Example Store",
        "purchase_date":purchase, "purchase_price":1000, "currency":"INR",
        "issue_description":"Device disconnects", "policy_days":10,
        "policy_source":"Demo policy source"
    })
    assert item["deadline"] == (date.today() + timedelta(days=10)).isoformat()
    assert services.get_case(item["id"])["product_name"] == "Demo headphones"

def test_unknown_policy_has_no_deadline():
    services.init_db()
    item = services.create_case({
        "product_name":"Demo item", "retailer":"Example Store",
        "purchase_date":date.today().isoformat(), "purchase_price":100,
        "currency":"INR", "issue_description":"Broken on arrival",
        "policy_days":None, "policy_source":None
    })
    assert item["deadline"] is None

def test_draft_and_followup():
    services.init_db()
    item = services.create_case({
        "product_name":"Demo item", "retailer":"Example Store",
        "purchase_date":date.today().isoformat(), "purchase_price":100,
        "currency":"INR", "issue_description":"Broken on arrival",
        "policy_days":None, "policy_source":None
    })
    draft = services.draft_claim(item)
    assert "Demo item" in draft["draft"]
    followup = services.create_followup(item["id"], date.today().isoformat(), "Check support response")
    assert followup["case_id"] == item["id"]
    assert len(services.list_followups(item["id"])) == 1
