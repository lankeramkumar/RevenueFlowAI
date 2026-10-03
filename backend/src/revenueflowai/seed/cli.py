"""Synthetic data generator CLI.

    python -m revenueflowai.seed generate --profile small --seed 42 --as-of 2026-10-02 \
        --output ./sample-data/small

Same seed + arguments must produce byte-identical CSVs and a stable
manifest (no wall-clock timestamps in the generated artifacts) — see
synthetic_data_requirements.md.
"""

import csv
import hashlib
import json
from datetime import date
from pathlib import Path

import typer

from revenueflowai.seed.demo import generate_demo_bundle
from revenueflowai.seed.invalid import generate_invalid_bundles
from revenueflowai.seed.scenarios import IMPLEMENTED_SCENARIOS
from revenueflowai.seed.schema import CSV_COLUMNS

app = typer.Typer(add_completion=False)

GENERATOR_VERSION = "0.1.0"
STATUS_VOCABULARY = {
    "invoices": ["draft", "posted", "void"],
    "receipts": ["posted", "cancelled"],
    "receipt_applications": ["posted", "reversed"],
    "credit_memos": ["posted", "void"],
    "credit_applications": ["posted", "reversed"],
    "disputes": ["open", "closed"],
    "order_holds": ["active", "released"],
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@app.command()
def version() -> None:
    """Print the generator version (also keeps this a multi-command Typer app
    so `generate` must be named explicitly, matching the documented CLI)."""
    typer.echo(GENERATOR_VERSION)


def _generate_small(seed: int, as_of_date: date, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    rows_by_file: dict[str, list[dict]] = {name: [] for name in CSV_COLUMNS}
    scenario_manifest = []

    for builder in IMPLEMENTED_SCENARIOS:
        bundle = builder(as_of_date)
        for filename, rows in bundle.rows.items():
            rows_by_file[filename].extend(rows)
        scenario_manifest.append({
            "scenario_id": bundle.scenario_id,
            "description": bundle.description,
            "expected": bundle.expected,
        })

    file_hashes = {}
    file_row_counts = {}
    for filename, columns in CSV_COLUMNS.items():
        path = out_dir / filename
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            for row in rows_by_file[filename]:
                writer.writerow(row)
        file_hashes[filename] = _sha256(path)
        file_row_counts[filename] = len(rows_by_file[filename])

    manifest = {
        "generator_version": GENERATOR_VERSION,
        "profile": "small",
        "seed": seed,
        "as_of_date": as_of_date.isoformat(),
        "snapshot_date": as_of_date.isoformat(),
        "status_vocabulary": STATUS_VOCABULARY,
        "scenario_ids": [s["scenario_id"] for s in scenario_manifest],
        "file_row_counts": file_row_counts,
        "file_sha256": file_hashes,
    }
    (out_dir / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (out_dir / "scenario_manifest.json").write_text(
        json.dumps(scenario_manifest, indent=2, sort_keys=True) + "\n"
    )

    typer.echo(
        f"Wrote {len(CSV_COLUMNS)} CSV files + manifests to {out_dir} "
        f"({len(scenario_manifest)} scenarios)."
    )


def _generate_demo(seed: int, as_of_date: date, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = generate_demo_bundle(seed, as_of_date)

    file_hashes = {}
    file_row_counts = {}
    for filename, columns in CSV_COLUMNS.items():
        path = out_dir / filename
        rows = bundle.rows.get(filename, [])
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        file_hashes[filename] = _sha256(path)
        file_row_counts[filename] = len(rows)

    manifest = {
        "generator_version": GENERATOR_VERSION,
        "profile": "demo",
        "seed": seed,
        "as_of_date": as_of_date.isoformat(),
        "snapshot_date": as_of_date.isoformat(),
        "status_vocabulary": STATUS_VOCABULARY,
        "file_row_counts": file_row_counts,
        "file_sha256": file_hashes,
    }
    (out_dir / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    typer.echo(
        f"Wrote {len(CSV_COLUMNS)} CSV files to {out_dir}: "
        f"{file_row_counts.get('customers.csv', 0)} customers, {file_row_counts.get('orders.csv', 0)} orders."
    )


def _generate_invalid(seed: int, as_of_date: date, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fixture_manifest = generate_invalid_bundles(seed, as_of_date, out_dir)

    manifest = {
        "generator_version": GENERATOR_VERSION,
        "profile": "invalid",
        "seed": seed,
        "as_of_date": as_of_date.isoformat(),
        "fixtures": fixture_manifest,
    }
    (out_dir / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    typer.echo(f"Wrote {len(fixture_manifest)} invalid fixture bundles to {out_dir}.")


@app.command()
def generate(
    profile: str = typer.Option(..., help="small|demo|load|invalid"),
    seed: int = typer.Option(42),
    as_of: str = typer.Option(..., help="ISO date, e.g. 2026-10-02. Never the machine clock."),
    output: str = typer.Option(...),
    total_rows: int = typer.Option(100_000, help="Only used by the load profile."),
) -> None:
    as_of_date = date.fromisoformat(as_of)
    out_dir = Path(output)

    if profile == "small":
        _generate_small(seed, as_of_date, out_dir)
    elif profile == "invalid":
        _generate_invalid(seed, as_of_date, out_dir)
    elif profile == "demo":
        _generate_demo(seed, as_of_date, out_dir)
    else:
        typer.echo(
            f"Profile '{profile}' is not yet implemented ('small', 'invalid', and 'demo' are done; "
            "'load' is tracked in docs/implementation-plan.md).",
            err=True,
        )
        raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
