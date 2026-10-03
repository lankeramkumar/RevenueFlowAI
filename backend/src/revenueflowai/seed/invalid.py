"""Deliberately invalid CSV bundles — one per defect class, per
synthetic_data_requirements.md's "Invalid bundles and warnings" section.
Each starts from the real small-profile valid bundle and applies exactly
one mutation, so a passing validator run proves the defect itself is what
gets caught, not some unrelated issue in the base data.
"""

import csv
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from revenueflowai.seed.scenarios import IMPLEMENTED_SCENARIOS
from revenueflowai.seed.schema import CSV_COLUMNS


@dataclass(frozen=True)
class InvalidFixture:
    name: str
    description: str
    # None means "expected to pass ingestion" -- used for fixtures proving
    # safe-as-data handling rather than rejection (e.g. formula-bearing text).
    expected_error_code: str | None
    mutate: Callable[[Path], None]  # applied after the valid base is written


def _write_valid_base(out_dir: Path, as_of: date) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows_by_file: dict[str, list[dict]] = {name: [] for name in CSV_COLUMNS}
    for builder in IMPLEMENTED_SCENARIOS:
        bundle = builder(as_of)
        for filename, rows in bundle.rows.items():
            rows_by_file[filename].extend(rows)

    for filename, columns in CSV_COLUMNS.items():
        path = out_dir / filename
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            for row in rows_by_file[filename]:
                writer.writerow(row)


def _append_row(out_dir: Path, filename: str, row: dict) -> None:
    columns = CSV_COLUMNS[filename]
    with (out_dir / filename).open("a", newline="", encoding="utf-8") as fh:
        csv.DictWriter(fh, fieldnames=columns, restval="").writerow(row)


def _rewrite_file(out_dir: Path, filename: str, rows: list[dict]) -> None:
    columns = CSV_COLUMNS[filename]
    with (out_dir / filename).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _read_rows(out_dir: Path, filename: str) -> list[dict]:
    with (out_dir / filename).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _mutate_duplicate_primary_key(out_dir: Path) -> None:
    rows = _read_rows(out_dir, "customers.csv")
    duplicate = dict(rows[0])
    rows.append(duplicate)
    _rewrite_file(out_dir, "customers.csv", rows)


def _mutate_missing_required_column(out_dir: Path) -> None:
    rows = _read_rows(out_dir, "invoices.csv")
    for row in rows:
        row.pop("due_date", None)
    with (out_dir / "invoices.csv").open("w", newline="", encoding="utf-8") as fh:
        columns = [c for c in CSV_COLUMNS["invoices.csv"] if c != "due_date"]
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: v for k, v in row.items() if k != "due_date"})


def _mutate_broken_foreign_key(out_dir: Path) -> None:
    _append_row(out_dir, "orders.csv", {
        "order_id": "INVALID-ORD-1", "customer_id": "NO-SUCH-CUSTOMER",
        "order_date": "2026-01-01", "currency": "USD", "status": "open",
    })


def _mutate_unknown_status(out_dir: Path) -> None:
    rows = _read_rows(out_dir, "invoices.csv")
    rows[0]["status"] = "not-a-real-status"
    _rewrite_file(out_dir, "invoices.csv", rows)


def _mutate_invalid_date(out_dir: Path) -> None:
    rows = _read_rows(out_dir, "invoices.csv")
    rows[0]["invoice_date"] = "13/45/2026"
    _rewrite_file(out_dir, "invoices.csv", rows)


def _mutate_excessive_precision(out_dir: Path) -> None:
    rows = _read_rows(out_dir, "invoices.csv")
    rows[0]["invoice_amount"] = "100.123456"
    _rewrite_file(out_dir, "invoices.csv", rows)


def _mutate_negative_amount(out_dir: Path) -> None:
    rows = _read_rows(out_dir, "invoices.csv")
    rows[0]["invoice_amount"] = "-500.00"
    _rewrite_file(out_dir, "invoices.csv", rows)


def _mutate_mismatched_currency(out_dir: Path) -> None:
    """A receipt application linking a USD receipt to a EUR invoice --
    same-customer/currency is required for a valid application.
    """
    _append_row(out_dir, "receipts.csv", {
        "receipt_id": "INVALID-RCP-1", "customer_id": "S09-CUST", "receipt_date": "2026-01-01",
        "currency": "USD", "receipt_amount": "200.00", "status": "posted", "remittance_reference": "",
    })
    _append_row(out_dir, "receipt_applications.csv", {
        "application_id": "INVALID-APP-1", "receipt_id": "INVALID-RCP-1", "invoice_id": "S09-INV-EUR",
        "applied_amount": "200.00", "application_date": "2026-01-01", "status": "posted",
    })


def _mutate_formula_bearing_text(out_dir: Path) -> None:
    """Narrative text starting with a spreadsheet-formula trigger character
    -- must be safely escaped on export, never executed, per intent.md's
    "spreadsheet formula injection" requirement.
    """
    rows = _read_rows(out_dir, "disputes.csv")
    injected = dict(rows[0])
    injected["dispute_id"] = "INVALID-DISP-FORMULA"
    injected["reason"] = "=cmd|' /C calc'!A1"
    rows.append(injected)
    _rewrite_file(out_dir, "disputes.csv", rows)


FIXTURES: tuple[InvalidFixture, ...] = (
    InvalidFixture("duplicate_primary_key", "Two customers.csv rows share a customer_id.",
                   "duplicate_primary_key", _mutate_duplicate_primary_key),
    InvalidFixture("missing_required_column", "invoices.csv is missing the required due_date column.",
                   "missing_column", _mutate_missing_required_column),
    InvalidFixture("broken_foreign_key", "An order references a customer_id that doesn't exist.",
                   "broken_foreign_key", _mutate_broken_foreign_key),
    InvalidFixture("unknown_status", "An invoice has a status outside the supported vocabulary.",
                   "unknown_status", _mutate_unknown_status),
    InvalidFixture("invalid_date", "An invoice_date is not valid ISO-8601.",
                   "invalid_date", _mutate_invalid_date),
    InvalidFixture("excessive_precision", "An invoice_amount has more than 4 decimal places.",
                   "excessive_precision", _mutate_excessive_precision),
    InvalidFixture("negative_amount", "An invoice_amount is negative.",
                   "negative_amount", _mutate_negative_amount),
    InvalidFixture(
        "mismatched_application_currency",
        "A receipt application links a USD receipt to a EUR invoice for the same customer.",
        "mismatched_application_currency", _mutate_mismatched_currency,
    ),
    InvalidFixture(
        "formula_bearing_narrative_text",
        "A dispute reason begins with '=', a spreadsheet formula trigger character. Accepted as plain "
        "data at ingestion (intentionally) -- intent.md's requirement is safe *export* escaping, which "
        "is a separate, not-yet-built export feature (tracked in docs/implementation-plan.md), not an "
        "ingestion rejection.",
        None,
        _mutate_formula_bearing_text,
    ),
)


def generate_invalid_bundles(seed: int, as_of: date, output_dir: Path) -> dict[str, dict]:
    """Writes one subdirectory per fixture under output_dir. Returns a
    manifest dict: {fixture_name: {description, expected_error_code}}.
    `seed` is accepted for interface symmetry with the other profiles;
    these fixtures are hand-specified, not randomized.
    """
    del seed
    manifest: dict[str, dict] = {}
    for fixture in FIXTURES:
        fixture_dir = output_dir / fixture.name
        if fixture_dir.exists():
            shutil.rmtree(fixture_dir)
        _write_valid_base(fixture_dir, as_of)
        fixture.mutate(fixture_dir)
        manifest[fixture.name] = {
            "description": fixture.description,
            "expected_error_code": fixture.expected_error_code,
        }
    return manifest
