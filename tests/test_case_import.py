import io

from fastapi.testclient import TestClient

from app.main import app
from app import services
from tests.dbtools import use_fresh_db

client = TestClient(app)


def setup_function():
    use_fresh_db()
    services.init_db()


def test_import_valid_csv():
    csv_content = (
        "product_name,retailer,purchase_date,purchase_price,"
        "issue_description\n"
        "Headphones,Example Store,2026-10-10,2000,"
        "Stopped working\n"
    )

    response = client.post(
        "/api/cases/import",
        files={
            "file": (
                "cases.csv",
                io.BytesIO(csv_content.encode()),
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["imported"] == 1
    assert response.json()["rejected_count"] == 0


def test_import_rejects_missing_columns():
    csv_content = "product_name,retailer\nHeadphones,Example Store\n"

    response = client.post(
        "/api/cases/import",
        files={
            "file": (
                "cases.csv",
                io.BytesIO(csv_content.encode()),
                "text/csv",
            )
        },
    )

    assert response.status_code == 400
    assert "Missing required columns" in response.json()["detail"]


def test_import_rejects_non_csv_file():
    response = client.post(
        "/api/cases/import",
        files={
            "file": (
                "cases.txt",
                io.BytesIO(b"not a csv"),
                "text/plain",
            )
        },
    )

    assert response.status_code == 400


def test_import_rejects_duplicate_cases():
    csv_content = (
        "product_name,retailer,purchase_date,purchase_price,issue_description\n"
        "Headphones,Example Store,2026-10-10,2000,Stopped working\n"
        "Headphones,Example Store,2026-10-10,2000,Stopped working\n"
    )

    response = client.post(
        "/api/cases/import",
        files={
            "file": (
                "cases.csv",
                io.BytesIO(csv_content.encode()),
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["imported"] == 1
    assert response.json()["rejected_count"] == 1
    assert "Duplicate case detected" in response.json()["rejected"][0]["reason"]