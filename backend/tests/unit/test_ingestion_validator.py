"""Validator tests: the real generated 'small' bundle must be valid, and each
deliberately broken fixture must surface the specific error code intent.md /
synthetic_data_requirements.md calls for (duplicate PK, broken FK, unknown
status, unsupported currency, negative amount).
"""

import csv
import subprocess
import sys
from pathlib import Path

import pytest

from revenueflowai.ingestion.manifest import REQUIRED_COLUMNS
from revenueflowai.ingestion.validator import validate_bundle


@pytest.fixture
def generated_small_bundle(tmp_path) -> Path:
    out_dir = tmp_path / "small"
    result = subprocess.run(
        [
            sys.executable, "-m", "revenueflowai.seed", "generate",
            "--profile", "small", "--seed", "42", "--as-of", "2026-10-02",
            "--output", str(out_dir),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return out_dir


def _write_empty_bundle(bundle_dir: Path) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    for filename, columns in REQUIRED_COLUMNS.items():
        with (bundle_dir / filename).open("w", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=columns).writeheader()


def _append_row(bundle_dir: Path, filename: str, row: dict[str, str]) -> None:
    columns = REQUIRED_COLUMNS[filename]
    with (bundle_dir / filename).open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, restval="")
        writer.writerow(row)


def test_generated_small_bundle_is_valid(generated_small_bundle):
    result = validate_bundle(generated_small_bundle)
    assert result.is_valid, [e.message for e in result.errors]


def test_missing_required_file_is_reported(tmp_path):
    bundle_dir = tmp_path / "bundle"
    _write_empty_bundle(bundle_dir)
    (bundle_dir / "customers.csv").unlink()

    result = validate_bundle(bundle_dir)

    assert not result.is_valid
    assert any(e.code == "missing_file" and e.file == "customers.csv" for e in result.errors)


def test_duplicate_primary_key_is_reported(tmp_path):
    bundle_dir = tmp_path / "bundle"
    _write_empty_bundle(bundle_dir)
    _append_row(bundle_dir, "customers.csv", {"customer_id": "CUST-1", "customer_name": "Alpha Co"})
    _append_row(bundle_dir, "customers.csv", {"customer_id": "CUST-1", "customer_name": "Beta Co"})

    result = validate_bundle(bundle_dir)

    assert any(e.code == "duplicate_primary_key" and e.file == "customers.csv" for e in result.errors)


def test_broken_foreign_key_is_reported(tmp_path):
    bundle_dir = tmp_path / "bundle"
    _write_empty_bundle(bundle_dir)
    _append_row(bundle_dir, "orders.csv", {
        "order_id": "ORD-1", "customer_id": "NO-SUCH-CUSTOMER",
        "order_date": "2026-01-01", "currency": "USD", "status": "open",
    })

    result = validate_bundle(bundle_dir)

    assert any(e.code == "broken_foreign_key" and e.file == "orders.csv" for e in result.errors)


def test_unknown_status_is_reported(tmp_path):
    bundle_dir = tmp_path / "bundle"
    _write_empty_bundle(bundle_dir)
    _append_row(bundle_dir, "customers.csv", {"customer_id": "CUST-1", "customer_name": "Alpha Co"})
    _append_row(bundle_dir, "orders.csv", {
        "order_id": "ORD-1", "customer_id": "CUST-1",
        "order_date": "2026-01-01", "currency": "USD", "status": "not-a-real-status",
    })

    result = validate_bundle(bundle_dir)

    assert any(e.code == "unknown_status" and e.file == "orders.csv" for e in result.errors)


def test_unsupported_currency_is_reported(tmp_path):
    bundle_dir = tmp_path / "bundle"
    _write_empty_bundle(bundle_dir)
    _append_row(bundle_dir, "customers.csv", {"customer_id": "CUST-1", "customer_name": "Alpha Co"})
    _append_row(bundle_dir, "orders.csv", {
        "order_id": "ORD-1", "customer_id": "CUST-1",
        "order_date": "2026-01-01", "currency": "JPY", "status": "open",
    })

    result = validate_bundle(bundle_dir)

    assert any(e.code == "unsupported_currency" and e.file == "orders.csv" for e in result.errors)


def test_negative_amount_is_reported(tmp_path):
    bundle_dir = tmp_path / "bundle"
    _write_empty_bundle(bundle_dir)
    _append_row(bundle_dir, "customers.csv", {"customer_id": "CUST-1", "customer_name": "Alpha Co"})
    _append_row(bundle_dir, "invoices.csv", {
        "invoice_id": "INV-1", "customer_id": "CUST-1",
        "invoice_date": "2026-01-01", "due_date": "2026-02-01",
        "currency": "USD", "invoice_amount": "-100.00", "status": "posted",
    })

    result = validate_bundle(bundle_dir)

    assert any(e.code == "negative_amount" and e.file == "invoices.csv" for e in result.errors)


def test_excessive_precision_is_reported(tmp_path):
    bundle_dir = tmp_path / "bundle"
    _write_empty_bundle(bundle_dir)
    _append_row(bundle_dir, "customers.csv", {"customer_id": "CUST-1", "customer_name": "Alpha Co"})
    _append_row(bundle_dir, "invoices.csv", {
        "invoice_id": "INV-1", "customer_id": "CUST-1",
        "invoice_date": "2026-01-01", "due_date": "2026-02-01",
        "currency": "USD", "invoice_amount": "100.123456", "status": "posted",
    })

    result = validate_bundle(bundle_dir)

    assert any(e.code == "excessive_precision" and e.file == "invoices.csv" for e in result.errors)


def test_invalid_date_is_reported(tmp_path):
    bundle_dir = tmp_path / "bundle"
    _write_empty_bundle(bundle_dir)
    _append_row(bundle_dir, "customers.csv", {"customer_id": "CUST-1", "customer_name": "Alpha Co"})
    _append_row(bundle_dir, "invoices.csv", {
        "invoice_id": "INV-1", "customer_id": "CUST-1",
        "invoice_date": "01/01/2026", "due_date": "2026-02-01",
        "currency": "USD", "invoice_amount": "100.00", "status": "posted",
    })

    result = validate_bundle(bundle_dir)

    assert any(e.code == "invalid_date" and e.file == "invoices.csv" for e in result.errors)
