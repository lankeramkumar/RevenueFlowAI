"""Pure, DB-independent CSV bundle validation.

Per intent.md: provide actionable row/column errors before anything is
staged into the database. This module only reads CSV files from disk and
returns structured errors — it does not touch Postgres, so it can be fully
unit-tested without Docker. The staging/activation transaction (Milestone 2
continuation) wraps this with the durable import-job workflow.
"""

import csv
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from revenueflowai.ingestion.manifest import (
    CURRENCY_COLUMN,
    DATE_COLUMNS,
    FOREIGN_KEYS,
    MAX_DECIMAL_PLACES,
    NONNEGATIVE_AMOUNT_COLUMNS,
    PRIMARY_KEY,
    REQUIRED_COLUMNS,
    STATUS_COLUMN,
    SUPPORTED_CURRENCIES,
    SUPPORTED_STATUSES,
)


@dataclass(frozen=True)
class ValidationError:
    file: str
    row_number: int | None  # 1-based data row number; None for file-level errors
    column: str | None
    code: str
    message: str


@dataclass
class ValidationResult:
    errors: list[ValidationError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add(self, file: str, row_number: int | None, column: str | None, code: str, message: str) -> None:
        self.errors.append(ValidationError(file, row_number, column, code, message))


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def validate_bundle(bundle_dir: Path) -> ValidationResult:
    result = ValidationResult()
    rows_by_file: dict[str, list[dict[str, str]]] = {}
    ids_by_file: dict[str, dict[str, set[str]]] = {}

    for filename, required_columns in REQUIRED_COLUMNS.items():
        path = bundle_dir / filename
        if not path.exists():
            # intent.md: optional files may be omitted where the schema allows;
            # all 13 files here are currently required for a complete bundle.
            result.add(filename, None, None, "missing_file", f"Required file '{filename}' is missing.")
            continue

        rows = _read_rows(path)
        rows_by_file[filename] = rows

        if rows:
            header = set(rows[0].keys())
            missing = [c for c in required_columns if c not in header]
            for col in missing:
                result.add(filename, None, col, "missing_column", f"Required column '{col}' is missing.")

        _validate_primary_key_uniqueness(filename, rows, result)
        _validate_status_vocabulary(filename, rows, result)
        _validate_currency_codes(filename, rows, result)
        _validate_nonnegative_amounts(filename, rows, result)
        _validate_precision(filename, rows, result)
        _validate_dates(filename, rows, result)

        ids_by_file[filename] = _collect_id_sets(filename, rows)

    _validate_foreign_keys(rows_by_file, ids_by_file, result)
    _validate_application_customer_currency_match(rows_by_file, result)

    return result


def _collect_id_sets(filename: str, rows: list[dict[str, str]]) -> dict[str, set[str]]:
    """Index every column referenced as a foreign-key target, by column name."""
    target_columns = {rule.references_column for rule in FOREIGN_KEYS if rule.references_file == filename}
    pk = PRIMARY_KEY.get(filename)
    if pk:
        target_columns.add(pk)
    return {col: {row.get(col, "") for row in rows if row.get(col)} for col in target_columns}


def _validate_primary_key_uniqueness(
    filename: str, rows: list[dict[str, str]], result: ValidationResult
) -> None:
    pk = PRIMARY_KEY.get(filename)
    if pk is None:
        return
    seen: dict[str, int] = {}
    for i, row in enumerate(rows, start=1):
        value = row.get(pk, "")
        if not value:
            result.add(filename, i, pk, "missing_primary_key", f"Row {i} has no value for '{pk}'.")
            continue
        if value in seen:
            result.add(
                filename, i, pk, "duplicate_primary_key",
                f"'{pk}'={value!r} duplicates row {seen[value]}.",
            )
        else:
            seen[value] = i


def _validate_status_vocabulary(filename: str, rows: list[dict[str, str]], result: ValidationResult) -> None:
    status_column = STATUS_COLUMN.get(filename)
    supported = SUPPORTED_STATUSES.get(filename)
    if status_column is None or supported is None:
        return
    for i, row in enumerate(rows, start=1):
        value = row.get(status_column, "")
        if value and value not in supported:
            result.add(
                filename, i, status_column, "unknown_status",
                f"Status {value!r} is not in the supported vocabulary {sorted(supported)}.",
            )


def _validate_currency_codes(filename: str, rows: list[dict[str, str]], result: ValidationResult) -> None:
    currency_column = CURRENCY_COLUMN.get(filename)
    if currency_column is None:
        return
    for i, row in enumerate(rows, start=1):
        value = row.get(currency_column, "")
        if value and value not in SUPPORTED_CURRENCIES:
            result.add(
                filename, i, currency_column, "unsupported_currency",
                f"Currency {value!r} is not supported ({sorted(SUPPORTED_CURRENCIES)}).",
            )


def _validate_nonnegative_amounts(
    filename: str, rows: list[dict[str, str]], result: ValidationResult
) -> None:
    columns = NONNEGATIVE_AMOUNT_COLUMNS.get(filename, [])
    for i, row in enumerate(rows, start=1):
        for column in columns:
            raw = row.get(column, "")
            if raw == "":
                continue
            try:
                value = Decimal(raw)
            except InvalidOperation:
                result.add(filename, i, column, "invalid_decimal", f"{raw!r} is not a valid decimal.")
                continue
            if value < 0:
                result.add(
                    filename, i, column, "negative_amount",
                    f"'{column}'={value} is negative; negative amounts are unsupported in this release.",
                )


def _validate_precision(filename: str, rows: list[dict[str, str]], result: ValidationResult) -> None:
    columns = NONNEGATIVE_AMOUNT_COLUMNS.get(filename, [])
    for i, row in enumerate(rows, start=1):
        for column in columns:
            raw = row.get(column, "")
            if raw == "":
                continue
            try:
                value = Decimal(raw)
            except InvalidOperation:
                continue  # already reported by _validate_nonnegative_amounts
            exponent = value.as_tuple().exponent
            if isinstance(exponent, int) and -exponent > MAX_DECIMAL_PLACES:
                result.add(
                    filename, i, column, "excessive_precision",
                    f"'{column}'={raw!r} has more than {MAX_DECIMAL_PLACES} decimal places; "
                    "rounding would silently change the amount, so this is rejected instead.",
                )


def _validate_dates(filename: str, rows: list[dict[str, str]], result: ValidationResult) -> None:
    columns = DATE_COLUMNS.get(filename, [])
    for i, row in enumerate(rows, start=1):
        for column in columns:
            raw = row.get(column, "")
            if raw == "":
                continue
            try:
                date.fromisoformat(raw)
            except ValueError:
                result.add(
                    filename, i, column, "invalid_date",
                    f"'{column}'={raw!r} is not a valid ISO-8601 date (YYYY-MM-DD).",
                )


def _validate_application_customer_currency_match(
    rows_by_file: dict[str, list[dict[str, str]]], result: ValidationResult
) -> None:
    """intent.md: "Payment and credit applications must connect records for
    the same customer and currency." Checked here, not just left to the
    domain layer, because it's a data-quality defect the uploader should
    see before activation, not a runtime matching nuance.
    """
    invoices = {
        row["invoice_id"]: (row.get("customer_id", ""), row.get("currency", ""))
        for row in rows_by_file.get("invoices.csv", [])
        if row.get("invoice_id")
    }

    receipts = {
        row["receipt_id"]: (row.get("customer_id", ""), row.get("currency", ""))
        for row in rows_by_file.get("receipts.csv", [])
        if row.get("receipt_id")
    }
    for i, row in enumerate(rows_by_file.get("receipt_applications.csv", []), start=1):
        receipt = receipts.get(row.get("receipt_id", ""))
        invoice = invoices.get(row.get("invoice_id", ""))
        if receipt is None or invoice is None:
            continue  # already reported by the foreign-key check
        if receipt != invoice:
            result.add(
                "receipt_applications.csv", i, "invoice_id", "mismatched_application_currency",
                f"Receipt {row.get('receipt_id')!r} (customer/currency {receipt}) applied to invoice "
                f"{row.get('invoice_id')!r} (customer/currency {invoice}) — must match.",
            )

    credit_memos = {
        row["credit_memo_id"]: (row.get("customer_id", ""), row.get("currency", ""))
        for row in rows_by_file.get("credit_memos.csv", [])
        if row.get("credit_memo_id")
    }
    for i, row in enumerate(rows_by_file.get("credit_applications.csv", []), start=1):
        memo = credit_memos.get(row.get("credit_memo_id", ""))
        invoice = invoices.get(row.get("invoice_id", ""))
        if memo is None or invoice is None:
            continue
        if memo != invoice:
            result.add(
                "credit_applications.csv", i, "invoice_id", "mismatched_application_currency",
                f"Credit memo {row.get('credit_memo_id')!r} (customer/currency {memo}) applied to invoice "
                f"{row.get('invoice_id')!r} (customer/currency {invoice}) — must match.",
            )


def _validate_foreign_keys(
    rows_by_file: dict[str, list[dict[str, str]]],
    ids_by_file: dict[str, dict[str, set[str]]],
    result: ValidationResult,
) -> None:
    for rule in FOREIGN_KEYS:
        rows = rows_by_file.get(rule.file)
        if rows is None:
            continue
        target_ids = ids_by_file.get(rule.references_file, {}).get(rule.references_column, set())
        for i, row in enumerate(rows, start=1):
            value = row.get(rule.column, "")
            if not value:
                if rule.required:
                    result.add(
                        rule.file, i, rule.column, "missing_foreign_key",
                        f"Row {i} has no value for required reference '{rule.column}'.",
                    )
                continue
            if value not in target_ids:
                result.add(
                    rule.file, i, rule.column, "broken_foreign_key",
                    f"'{rule.column}'={value!r} does not match any "
                    f"'{rule.references_column}' in {rule.references_file}.",
                )
