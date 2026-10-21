from fastapi.testclient import TestClient

from app.main import app
from app import services

client = TestClient(app)


def test_evidence_checklist_success():
    case = services.create_case({
        "product_name": "Headphones",
        "retailer": "Example Store",
        "purchase_date": "2026-10-10",
        "purchase_price": 2000,
        "currency": "INR",
        "issue_description": "Headphones arrived broken",
        "policy_days": 30,
        "policy_source": "Example Store return policy",
    })

    response = client.post(
        f"/api/cases/{case['id']}/evidence-checklist"
    )

    assert response.status_code == 200

    data = response.json()
    assert data["case_id"] == case["id"]
    assert "suggested_evidence" in data
    assert "warning" in data

    items = [item["item"] for item in data["suggested_evidence"]]
    assert "Purchase receipt or order confirmation" in items
    assert "Photos showing the damage" in items


def test_evidence_checklist_case_not_found():
    response = client.post("/api/cases/999999/evidence-checklist")

    assert response.status_code == 404
    assert response.json()["detail"] == "Case not found"