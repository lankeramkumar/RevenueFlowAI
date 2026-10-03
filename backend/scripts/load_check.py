"""Latency check for paginated screens: N concurrent users each issue screen
requests against the live database. Measures the application and database
path in process (no network, no identity provider), so results are a lower
bound on what a deployed system would see.

    python scripts/load_check.py --organization-id <uuid> --business-unit-id <uuid> \
        --actor-user-id <uuid> --users 10 --requests-per-user 30
"""

import asyncio
import statistics
import time
from uuid import UUID

import typer
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from revenueflowai.auth.deps import get_current_app_user
from revenueflowai.db import AsyncSessionLocal, get_session
from revenueflowai.main import app
from revenueflowai.models.tenancy import AppUser

SCREENS = (
    "/api/v1/dashboard/aging-summary?business_unit_id={bu}",
    "/api/v1/dashboard/order-holds?business_unit_id={bu}",
    "/api/v1/dashboard/unbilled-shipments?business_unit_id={bu}",
    "/api/v1/customers/DEMO-CUST-000001?business_unit_id={bu}",
    "/api/v1/tasks?business_unit_id={bu}",
)

cli = typer.Typer(add_completion=False)


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))]


async def _run(organization_id: UUID, business_unit_id: UUID, actor_user_id: UUID,
               users: int, requests_per_user: int) -> None:
    async with AsyncSessionLocal() as setup:
        actor = (await setup.execute(
            select(AppUser).options(selectinload(AppUser.granted_business_units))
            .where(AppUser.id == actor_user_id, AppUser.organization_id == organization_id)
        )).scalar_one()

    async def override_session():
        async with AsyncSessionLocal() as session:
            yield session

    async def override_user() -> AppUser:
        return actor

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_app_user] = override_user

    timings: dict[str, list[float]] = {s: [] for s in SCREENS}
    errors = 0

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://load") as client:
        async def user_session(index: int) -> None:
            nonlocal errors
            for i in range(requests_per_user):
                path = SCREENS[(index + i) % len(SCREENS)].format(bu=business_unit_id)
                started = time.perf_counter()
                response = await client.get(path)
                elapsed = (time.perf_counter() - started) * 1000
                if not 200 <= response.status_code < 300:
                    errors += 1
                if 200 <= response.status_code < 300:
                    timings[SCREENS[(index + i) % len(SCREENS)]].append(elapsed)

        wall = time.perf_counter()
        await asyncio.gather(*(user_session(u) for u in range(users)))
        wall = time.perf_counter() - wall

    app.dependency_overrides.clear()

    all_ms = [t for series in timings.values() for t in series]
    total = len(all_ms) + errors
    typer.echo(f"users={users} requests={total} errors={errors} wall={wall:.2f}s "
               f"throughput={total / wall:.1f} req/s")
    typer.echo(f"overall p50={statistics.median(all_ms):.1f}ms p95={_percentile(all_ms, 95):.1f}ms "
               f"max={max(all_ms):.1f}ms")
    for screen, series in timings.items():
        if series:
            typer.echo(f"  {screen.split('?')[0]:<55} n={len(series):<4} p50={statistics.median(series):7.1f}ms "
                       f"p95={_percentile(series, 95):7.1f}ms")
    target_met = _percentile(all_ms, 95) < 2000 and errors == 0
    typer.echo(f"target (p95 < 2000 ms, no errors): {'MET' if target_met else 'NOT MET'}")


@cli.command()
def run(
    organization_id: str = typer.Option(...),
    business_unit_id: str = typer.Option(...),
    actor_user_id: str = typer.Option(...),
    users: int = typer.Option(10),
    requests_per_user: int = typer.Option(30),
) -> None:
    asyncio.run(_run(UUID(organization_id), UUID(business_unit_id), UUID(actor_user_id), users, requests_per_user))


if __name__ == "__main__":
    cli()
