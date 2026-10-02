"""Pure, DB-independent CSV bundle validation.

Per intent.md: provide actionable row/column errors before anything is
staged into the database. This module only reads CSV files from disk and
returns structured errors — it does not touch Postgres, so it can be fully
unit-tested without Docker. The staging/activation transaction (Milestone 2
continuation) wraps this with the durable import-job workflow.
"""

import csv
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from revenueflowai.ingestion.manifest import (
    CURRENCY_COLUMN,
    FOREIGN_KEYS,
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

        ids_by_file[filename] = _collect_id_sets(filename, rows)

    _validate_foreign_keys(rows_by_file, ids_by_file, result)

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
