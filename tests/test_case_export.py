import csv
import io

from fastapi.testclient import TestClient

from app.main import app
from app import services
from tests.dbtools import use_fresh_db


client = TestClient(app)


def setup_function():
    use_fresh_db()
    services.init_db()


def test_export_cases_returns_csv():
    services.create_case({
        "product_name": "Headphones",
        "retailer": "Example Store",
        "purchase_date": "2026-10-10",
        "purchase_price": 2000,
        "currency": "INR",
        "issue_description": "Stopped working",
    })

    response = client.get("/api/cases/export")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert 'filename="refund_cases.csv"' in response.headers["content-disposition"]

    rows = list(csv.DictReader(io.StringIO(response.text)))

    assert len(rows) == 1
    assert rows[0]["product_name"] == "Headphones"
    assert rows[0]["retailer"] == "Example Store"


def test_export_cases_when_empty():
    response = client.get("/api/cases/export")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "No cases available" in response.text