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

def test_import_rejects_empty_csv():
    response = client.post(
        "/api/cases/import",
        files={"file": ("cases.csv", io.BytesIO(b""), "text/csv")},
    )

    assert response.status_code == 400


def test_import_rejects_duplicate_column_names():
    csv_content = (
        "product_name,retailer,purchase_date,purchase_price,"
        "issue_description,retailer\n"
        "Headphones,Example Store,2026-10-10,2000,"
        "Stopped working,Another Store\n"
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

    assert response.status_code == 400
    assert "duplicate column names" in response.json()["detail"]


def test_import_rejects_negative_purchase_price():
    csv_content = (
        "product_name,retailer,purchase_date,purchase_price,"
        "issue_description\n"
        "Headphones,Example Store,2026-10-10,-2000,"
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
    assert response.json()["imported"] == 0
    assert response.json()["rejected_count"] == 1


def test_import_rejects_unsupported_currency():
    csv_content = (
        "product_name,retailer,purchase_date,purchase_price,"
        "issue_description,currency\n"
        "Headphones,Example Store,2026-10-10,2000,"
        "Stopped working,XYZ\n"
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
    assert response.json()["imported"] == 0
    assert response.json()["rejected_count"] == 1


def test_import_rejects_duplicate_of_existing_case():
    services.create_case(
        {
            "product_name": "Headphones",
            "retailer": "Example Store",
            "purchase_date": "2026-10-10",
            "purchase_price": 2000,
            "currency": "INR",
            "issue_description": "Stopped working",
        }
    )

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
    assert response.json()["imported"] == 0
    assert response.json()["rejected_count"] == 1
    assert "Duplicate case detected" in response.json()["rejected"][0]["reason"]


def test_import_rejects_oversized_file():
    content = (
        b"product_name,retailer,purchase_date,purchase_price,"
        b"issue_description\n"
        + b" " * (5 * 1024 * 1024)
        + b"\n"
    )

    response = client.post(
        "/api/cases/import",
        files={"file": ("cases.csv", io.BytesIO(content), "text/csv")},
    )

    assert response.status_code == 413


def test_import_rejects_invalid_utf8():
    content = (
        b"product_name,retailer,purchase_date,purchase_price,"
        b"issue_description\n"
        b"\xff\xfe\xfa\n"
    )

    response = client.post(
        "/api/cases/import",
        files={"file": ("cases.csv", io.BytesIO(content), "text/csv")},
    )

    assert response.status_code == 400
    assert "UTF-8" in response.json()["detail"]


def test_import_reports_invalid_row_and_imports_valid_row():
    csv_content = (
        "product_name,retailer,purchase_date,purchase_price,"
        "issue_description\n"
        "Headphones,Example Store,2026-10-10,2000,"
        "Stopped working\n"
        "Keyboard,Example Store,2026-10-10,-100,"
        "Keys stopped working\n"
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
    assert response.json()["rejected"][0]["row"] == 3
