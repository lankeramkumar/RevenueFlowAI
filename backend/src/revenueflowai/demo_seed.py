"""Seeds a demo organization with the generated demo dataset, so a fresh
Compose stack shows real data on first login. Runs the same validation and
activation path as an upload. Idempotent: if the admin email already has an
account, nothing is changed.

    python -m revenueflowai.demo_seed --org-slug demo --admin-email demo-admin@revenueflow.test
"""

import asyncio
import csv
import tempfile
from datetime import date
from pathlib import Path

import typer
from sqlalchemy import select

from revenueflowai.bootstrap import _bootstrap
from revenueflowai.db import AsyncSessionLocal
from revenueflowai.ingestion.activation import (
    compute_bundle_hash,
    get_or_create_import_job,
    validate_and_activate,
)
from revenueflowai.models.tenancy import AppUser, BusinessUnit, Organization
from revenueflowai.seed.cli import _generate_small
from revenueflowai.seed.demo import generate_demo_bundle
from revenueflowai.seed.schema import CSV_COLUMNS

app = typer.Typer(add_completion=False)


def _write_bundle(out_dir: Path, seed: int, as_of: date, profile: str) -> None:
    if profile == "small":
        _generate_small(seed, as_of, out_dir)
        return
    bundle = generate_demo_bundle(seed, as_of)
    for filename, columns in CSV_COLUMNS.items():
        with (out_dir / filename).open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            for row in bundle.rows.get(filename, []):
                writer.writerow(row)


async def _seed(org_slug: str, admin_email: str, seed: int, as_of: date, profile: str) -> str:
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(
            select(AppUser).where(AppUser.email == admin_email)
        )).scalar_one_or_none()
    if existing is not None:
        return f"Skipped: '{admin_email}' already has an account."

    await _bootstrap(
        org_name=f"Demo {org_slug}", org_slug=org_slug, bu_code="BU1", bu_name="Business Unit 1",
        admin_subject=f"pending:{admin_email.lower()}", admin_email=admin_email, admin_name="Demo Admin",
    )

    async with AsyncSessionLocal() as session:
        org = (await session.execute(select(Organization).where(Organization.slug == org_slug))).scalar_one()
        bu = (await session.execute(
            select(BusinessUnit).where(BusinessUnit.organization_id == org.id, BusinessUnit.code == "BU1")
        )).scalar_one()
        admin = (await session.execute(select(AppUser).where(AppUser.email == admin_email))).scalar_one()

        with tempfile.TemporaryDirectory() as tmp:
            bundle_dir = Path(tmp)
            _write_bundle(bundle_dir, seed, as_of, profile)
            job, _ = await get_or_create_import_job(
                session, org.id, bu.id, admin.id, idempotency_key=f"demo-seed-{seed}-{as_of.isoformat()}",
                bundle_hash=compute_bundle_hash(bundle_dir), snapshot_date=as_of,
            )
            outcome = await validate_and_activate(session, job, bundle_dir, snapshot_date=as_of)
        await session.commit()

    if not outcome.validation.is_valid:
        raise typer.Exit(code=1)
    rows = sum((outcome.row_counts or {}).values())
    return f"Seeded organization '{org_slug}' with the {profile} dataset ({rows} rows)."


@app.command()
def seed(
    org_slug: str = typer.Option("demo"),
    admin_email: str = typer.Option("demo-admin@revenueflow.test"),
    seed_value: int = typer.Option(42, "--seed"),
    as_of: str = typer.Option("2026-10-02"),
    profile: str = typer.Option("demo", help="demo (realistic mix) or small (scenario fixtures)."),
) -> None:
    typer.echo(asyncio.run(_seed(org_slug, admin_email, seed_value, date.fromisoformat(as_of), profile)))


if __name__ == "__main__":
    app()
