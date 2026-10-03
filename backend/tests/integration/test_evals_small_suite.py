"""The investigation eval suite against live Postgres and the activated small
bundle. Demo mode is deterministic, so the bar is 100% pass rate and 100%
citation validity; any regression fails the build.
"""

import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path

import pytest

from revenueflowai.agents.providers.demo import DemoQuestionPlanner
from revenueflowai.agents.supervisor import InvestigationScope
from revenueflowai.domain.services import get_active_dataset_version
from revenueflowai.evals.cases import SMALL_SUITE
from revenueflowai.evals.runner import run_suite
from revenueflowai.ingestion.activation import (
    compute_bundle_hash,
    get_or_create_import_job,
    validate_and_activate,
)

pytestmark = pytest.mark.asyncio

AS_OF = date(2026, 10, 2)


async def test_small_suite_passes_in_demo_mode(db_session, tenant, tmp_path: Path):
    org, bu, user = tenant
    out_dir = tmp_path / "small"
    result = subprocess.run(
        [sys.executable, "-m", "revenueflowai.seed", "generate", "--profile", "small",
         "--seed", "42", "--as-of", AS_OF.isoformat(), "--output", str(out_dir)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    job, _ = await get_or_create_import_job(
        db_session, org.id, bu.id, user.id, idempotency_key=f"evals-{uuid.uuid4().hex[:8]}",
        bundle_hash=compute_bundle_hash(out_dir), snapshot_date=AS_OF,
    )
    outcome = await validate_and_activate(db_session, job, out_dir, snapshot_date=AS_OF)
    assert outcome.validation.is_valid

    dv = await get_active_dataset_version(db_session, org.id, bu.id)
    scope = InvestigationScope(
        organization_id=org.id, business_unit_id=bu.id, dataset_version_id=dv.id,
        business_as_of_date=dv.snapshot_date, source_snapshot_date=dv.snapshot_date,
        actor_user_id=user.id, provider_mode="demo",
    )
    report = await run_suite(db_session, scope, SMALL_SUITE, DemoQuestionPlanner())

    failures = [(s.case_id, s.failures) for s in report.scores if not s.passed]
    assert failures == [], failures
    assert report.pass_rate == 1.0
    assert report.citation_validity == 1.0
    assert len(report.scores) == len(SMALL_SUITE)
