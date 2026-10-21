"""Receipt parser regression tests. The parser must never raise and must never guess ambiguous dates."""
from datetime import date
from unittest import mock

from tests.dbtools import use_fresh_db  # keeps DATABASE_PATH pointed at a temp location
from app import services

use_fresh_db()
parse = services.parse_receipt_text


def total(raw):
    return parse(f"Total: {raw}")


def test_original_demo_format_still_works():
    r = parse("Product: Wireless headphones\nRetailer: Example Store\nDate: 2026-10-12\nTotal: 2999")
    assert r["product_name"] == "Wireless headphones"
    assert r["retailer"] == "Example Store"
    assert r["purchase_date"] == "2026-10-12"
    assert r["purchase_price"] == 2999.0
    assert "warnings" not in r and "purchase_date_candidates" not in r
    assert "Demo text parser only" in r["parser_note"]


def test_original_prefix_and_label_variants_still_work():
    assert parse("Amount: INR 1,200.50")["purchase_price"] == 1200.5
    assert parse("Price: ₹ 499")["purchase_price"] == 499.0
    assert parse("Price: Rs. 499")["purchase_price"] == 499.0
    assert parse("Item: Kettle\nStore: Shop X\nPurchase Date: 2026-01-02")["purchase_date"] == "2026-01-02"
    assert parse("Merchant: Big Shop")["retailer"] == "Big Shop"


def test_malformed_amounts_do_not_crash_and_are_not_guessed():
    for raw in (",", ",,", ".", "1,4,9,9", "29,99", "1,23", "12,3456", "abc", "1.2.3", "--", "", "1,499,", "99999999999"):
        r = total(raw)
        assert "purchase_price" not in r, (raw, r)
        if raw.strip():
            assert r["warnings"], raw
        assert "Demo text parser only" in r["parser_note"]


def test_total_with_trailing_currency_code():
    r = total("1,499.00 INR")
    assert r["purchase_price"] == 1499.0 and r["currency"] == "INR"


def test_dollar_amount_is_read_but_currency_is_not_guessed():
    r = total("$29.99")
    assert r["purchase_price"] == 29.99
    assert "currency" not in r
    assert any("'$'" in w for w in r["warnings"])


def test_explicit_currency_codes_and_symbols():
    assert total("USD 29.99")["currency"] == "USD"
    assert total("29.99 EUR")["currency"] == "EUR"
    assert total("£12.50")["currency"] == "GBP"
    assert total("€12,500.00")["purchase_price"] == 12500.0
    assert total("₹1,49,999.50")["purchase_price"] == 149999.5     # Indian digit grouping
    assert "currency" not in total("1499")                        # nothing stated -> nothing assumed


def test_conflicting_currencies_are_not_guessed():
    r = total("USD 10 EUR")
    assert r["purchase_price"] == 10.0 and "currency" not in r and r["warnings"]


def test_iso_dates_validated():
    assert parse("Date: 2026-10-12")["purchase_date"] == "2026-10-12"
    for bad in ("2026-13-45", "2026-02-30"):
        r = parse(f"Date: {bad}")
        assert "purchase_date" not in r and r["warnings"], bad


def test_ambiguous_day_month_date_is_not_guessed():
    r = parse("Date: 12/10/2026")
    assert "purchase_date" not in r
    assert r["purchase_date_candidates"] == ["2026-10-12", "2026-12-10"]
    assert any("ambiguous" in w for w in r["warnings"])
    assert "purchase_date" not in parse("Date: 03-04-2026")        # other separators too


def test_unambiguous_slash_dates_are_resolved():
    assert parse("Date: 25/12/2025")["purchase_date"] == "2025-12-25"   # 25 cannot be a month -> day first
    assert parse("Date: 12/25/2025")["purchase_date"] == "2025-12-25"   # 25 cannot be a month -> month first
    assert parse("Date: 10/10/2026")["purchase_date"] == "2026-10-10"   # both readings are the same day
    assert "purchase_date" not in parse("Date: 31/02/2026")             # not a real date either way


def test_month_name_dates():
    assert parse("Date: 12 Oct 2026")["purchase_date"] == "2026-10-12"
    assert parse("Date: October 12, 2026")["purchase_date"] == "2026-10-12"
    assert parse("Date: 3rd March 2026")["purchase_date"] == "2026-03-03"
    r = parse("Date: 31 Feb 2026")
    assert "purchase_date" not in r and r["warnings"]


def test_unsupported_dates_are_reported_not_guessed():
    for bad in ("12/10/26", "yesterday", "2026", "12.10", "Octember 5, 2026"):
        r = parse(f"Date: {bad}")
        assert "purchase_date" not in r and r["warnings"], bad


def test_future_receipt_date_is_flagged():
    with mock.patch.object(services, "_today", return_value=date(2026, 10, 15)):
        r = parse("Date: 2026-12-01")
    assert r["purchase_date"] == "2026-12-01"
    assert any("future" in w for w in r["warnings"])


def test_parser_never_raises_on_hostile_input():
    samples = ["", " ", "\n\n", "Total:", "Total: \x00", "Date: ᴅᴀᴛᴇ", "Total: " + "9" * 5000, "Date: " + "1/" * 500,
               "Total: ١٢٣", "Product:\nRetailer:\n", "Total: 1e400", "Total: nan", "Total: inf", "Total: -5", "x" * 50000]
    for text in samples:
        result = parse(text)
        assert isinstance(result, dict) and "parser_note" in result
    assert parse(None)["parser_note"]                              # not even a string: still no crash
