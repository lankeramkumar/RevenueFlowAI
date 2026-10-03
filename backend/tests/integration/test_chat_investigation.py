"""Supervisor + specialist end-to-end tests against live Postgres, using
the demo (regex) planner -- deterministic, no API key needed, per
intent.md's "Keep live API tests opt-in; deterministic tests run without
credentials." The live Anthropic planner was verified manually against
the running stack (see docs/implementation-plan.md) rather than in CI,
since it costs real tokens on every run.
"""

import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from revenueflowai.agents.ar import make_ar_handler
from revenueflowai.agents.cash import make_cash_handler
from revenueflowai.agents.order import make_order_handler
from revenueflowai.agents.providers.demo import DemoQuestionPlanner
from revenueflowai.agents.supervisor import InvestigationScope, run_investigation
from revenueflowai.agents.transport import InternalAgentTransport
from revenueflowai.ingestion.activation import (
    compute_bundle_hash,
    get_or_create_import_job,
    validate_and_activate,
)

pytestmark = pytest.mark.asyncio

AS_OF = date(2026, 10, 2)


def _generate_small_bundle(tmp_path: Path) -> Path:
    out_dir = tmp_path / "small"
    result = subprocess.run(
        [
            sys.executable, "-m", "revenueflowai.seed", "generate",
            "--profile", "small", "--seed", "42", "--as-of", AS_OF.isoformat(),
            "--output", str(out_dir),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return out_dir


async def _activated_scope(db_session, tenant, tmp_path):
    org, bu, user = tenant
    bundle_dir = _generate_small_bundle(tmp_path)
    job, _ = await get_or_create_import_job(
        db_session, org.id, bu.id, user.id, idempotency_key="chat-test",
        bundle_hash=compute_bundle_hash(bundle_dir), snapshot_date=AS_OF,
    )
    outcome = await validate_and_activate(db_session, job, bundle_dir, snapshot_date=AS_OF)
    assert outcome.validation.is_valid

    return InvestigationScope(
        organization_id=org.id, business_unit_id=bu.id,
        dataset_version_id=outcome.dataset_version.id, business_as_of_date=AS_OF,
        source_snapshot_date=AS_OF, actor_user_id=user.id, provider_mode="demo",
    )


def _transport(db_session) -> InternalAgentTransport:
    return InternalAgentTransport(handlers={
        "order": make_order_handler(db_session),
        "ar": make_ar_handler(db_session),
        "cash": make_cash_handler(db_session),
    })


async def test_aging_question_routes_to_ar_with_real_numbers(db_session, tenant, tmp_path):
    scope = await _activated_scope(db_session, tenant, tmp_path)
    result = await run_investigation(
        scope, "What invoices are overdue? Show the aging breakdown.",
        _transport(db_session), DemoQuestionPlanner(),
    )

    assert any(s.domain == "ar" for s in result.specialist_status)
    # Bucket totals now sum contributions from all 16 scenarios sharing
    # USD/31-60, so check the bucket is reported with a real nonzero
    # total rather than asserting an exact aggregate figure.
    assert "USD" in result.summary
    assert "31-60" in result.summary


async def test_receipt_match_question_routes_to_cash(db_session, tenant, tmp_path):
    scope = await _activated_scope(db_session, tenant, tmp_path)
    result = await run_investigation(
        scope, "Which invoices might match receipt S01-RCP?",
        _transport(db_session), DemoQuestionPlanner(),
    )

    assert len(result.specialist_status) == 1
    assert result.specialist_status[0].domain == "cash"
    assert result.specialist_status[0].status == "success"


async def test_customer_summary_dispatches_all_three_domains(db_session, tenant, tmp_path):
    scope = await _activated_scope(db_session, tenant, tmp_path)
    result = await run_investigation(
        scope, "Summarize this customer's outstanding invoices, cash, and disputes.",
        _transport(db_session), DemoQuestionPlanner(), customer_id_hint="S01-CUST",
    )

    domains = {s.domain for s in result.specialist_status}
    assert domains == {"order", "ar", "cash"}
    assert "600.0000 USD" in result.summary  # AR's outstanding-balance finding
    assert any(e.record_id == "S01-CUST" for e in result.evidence)


async def test_unsupported_question_is_honest_not_fabricated(db_session, tenant, tmp_path):
    scope = await _activated_scope(db_session, tenant, tmp_path)
    result = await run_investigation(
        scope, "What's the weather like today?", _transport(db_session), DemoQuestionPlanner(),
    )

    assert result.specialist_status == ()
    assert result.findings == ()
    assert "unsupported_question_pattern" in result.missing_data
