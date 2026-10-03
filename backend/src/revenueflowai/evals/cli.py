"""Run the investigation evals against an activated dataset.

    python -m revenueflowai.evals run --organization-id <uuid> --business-unit-id <uuid> \
        --actor-user-id <uuid> --output evals-report.json

Exit status is 1 when the pass rate or citation validity falls below the
thresholds, so this can gate a pipeline. Demo mode is deterministic and needs
no credentials; --live calls the configured Anthropic planner (costs tokens).
"""

import asyncio
import json
from datetime import date
from pathlib import Path
from uuid import UUID

import typer

from revenueflowai.agents.providers.base import QuestionPlanner
from revenueflowai.agents.providers.demo import DemoQuestionPlanner
from revenueflowai.agents.supervisor import InvestigationScope
from revenueflowai.config import get_settings
from revenueflowai.db import AsyncSessionLocal
from revenueflowai.domain.services import get_active_dataset_version
from revenueflowai.evals.cases import SMALL_SUITE
from revenueflowai.evals.runner import SuiteReport, run_suite

app = typer.Typer(add_completion=False)


def _report_dict(report: SuiteReport) -> dict:
    return {
        "provider_mode": report.provider_mode,
        "cases": len(report.scores),
        "pass_rate": round(report.pass_rate, 4),
        "citation_validity": round(report.citation_validity, 4),
        "pass_rate_by_category": {k: round(v, 4) for k, v in report.by_category().items()},
        "latency_ms_p50": _percentile([s.latency_ms for s in report.scores], 50),
        "latency_ms_max": round(max((s.latency_ms for s in report.scores), default=0.0), 2),
        "results": [
            {
                "case_id": s.case_id, "category": s.category, "passed": s.passed,
                "dispatches": sorted(s.actual_dispatches), "failures": list(s.failures),
                "latency_ms": round(s.latency_ms, 2),
            }
            for s in report.scores
        ],
    }


def _percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1)))
    return round(ordered[index], 2)


async def _run(
    organization_id: UUID, business_unit_id: UUID, actor_user_id: UUID, as_of: date, live: bool,
) -> SuiteReport:
    async with AsyncSessionLocal() as session:
        dataset = await get_active_dataset_version(session, organization_id, business_unit_id)
        if dataset is None:
            raise typer.BadParameter("No active dataset for that organization and business unit.")

        planner: QuestionPlanner
        mode = "demo"
        if live:
            from revenueflowai.agents.providers.live import AnthropicQuestionPlanner, BedrockQuestionPlanner

            settings = get_settings()
            if settings.live_planner_provider == "bedrock":
                planner = BedrockQuestionPlanner(settings.aws_region)
            elif settings.anthropic_api_key:
                planner = AnthropicQuestionPlanner(settings.anthropic_api_key)
            else:
                raise typer.BadParameter(
                    "--live requires ANTHROPIC_API_KEY, or LIVE_PLANNER_PROVIDER=bedrock."
                )
            mode = "live"
        else:
            planner = DemoQuestionPlanner()

        scope = InvestigationScope(
            organization_id=organization_id, business_unit_id=business_unit_id,
            dataset_version_id=dataset.id, business_as_of_date=dataset.snapshot_date,
            source_snapshot_date=dataset.snapshot_date, actor_user_id=actor_user_id, provider_mode=mode,
        )
        return await run_suite(session, scope, SMALL_SUITE, planner)


@app.command()
def run(
    organization_id: str = typer.Option(...),
    business_unit_id: str = typer.Option(...),
    actor_user_id: str = typer.Option(...),
    as_of: str = typer.Option(date.today().isoformat(), help="ISO date used as the business as-of date."),
    live: bool = typer.Option(False, help="Use the live Anthropic planner."),
    min_pass_rate: float = typer.Option(1.0),
    min_citation_validity: float = typer.Option(1.0),
    output: Path | None = typer.Option(None, help="Write the JSON report here."),
) -> None:
    report = asyncio.run(_run(
        UUID(organization_id), UUID(business_unit_id), UUID(actor_user_id), date.fromisoformat(as_of), live,
    ))
    payload = _report_dict(report)
    text = json.dumps(payload, indent=2)
    if output:
        output.write_text(text + "\n", encoding="utf-8")
    typer.echo(text)

    ok = payload["pass_rate"] >= min_pass_rate and payload["citation_validity"] >= min_citation_validity
    if not ok:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
