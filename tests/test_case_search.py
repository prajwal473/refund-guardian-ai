from datetime import date

from tests.dbtools import use_fresh_db
from app import services


def setup_function():
    use_fresh_db()
    services.init_db()


def create_test_case(name, retailer, purchase_date):
    return services.create_case({
        "product_name": name,
        "retailer": retailer,
        "purchase_date": purchase_date,
        "purchase_price": 1000,
        "currency": "INR",
        "issue_description": "Product is not working",
    })


def test_search_by_product_name():
    create_test_case("Headphones", "Example Store", "2026-10-10")
    create_test_case("Keyboard", "Another Store", "2026-10-11")

    results = services.search_cases(query="headphones")

    assert len(results) == 1
    assert results[0]["product_name"] == "Headphones"


def test_search_by_retailer():
    create_test_case("Mouse", "Example Store", "2026-10-10")

    results = services.search_cases(query="example store")

    assert len(results) == 1
    assert results[0]["retailer"] == "Example Store"


def test_sort_by_purchase_date():
    create_test_case("Older Item", "Store A", "2026-10-10")
    create_test_case("Newer Item", "Store B", "2026-10-15")

    results = services.search_cases(sort_by="purchase_date")

    assert results[0]["product_name"] == "Newer Item"


def test_invalid_sort_option():
    try:
        services.search_cases(sort_by="invalid")
        assert False, "Expected ValueError"
    except ValueError:
        pass