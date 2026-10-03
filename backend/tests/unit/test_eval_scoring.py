from datetime import date
from uuid import uuid4

from revenueflowai.agents.contracts import FinalInvestigation, Finding
from revenueflowai.evals.cases import EvalCase
from revenueflowai.evals.runner import score_case


def _result(**overrides) -> FinalInvestigation:
    base = dict(
        summary="", findings=(), specialist_status=(), evidence=(), recommended_actions=(),
        missing_data=(), dataset_version_id=uuid4(), as_of_date=date(2026, 10, 2).isoformat(),
    )
    base.update(overrides)
    return FinalInvestigation(**base)


CASE = EvalCase(
    case_id="c", category="grounding", question="q",
    expected_dispatches=frozenset({"ar:invoice_overdue_dispute"}),
    expected_entities={"invoice_id": "S01-INV-1000"},
    expected_finding_substrings=("600.00 USD",),
)


def _finding(text: str) -> Finding:
    return Finding(key=text, statement=text, evidence=())


def test_correct_result_passes():
    result = _result(
        findings=(_finding("Invoice S01-INV-1000 has an open balance of 600.00 USD."),),
        dispatches=("ar:invoice_overdue_dispute",), entities={"invoice_id": "S01-INV-1000"},
    )
    score = score_case(CASE, result, citations_total=0, citations_resolved=0, latency_ms=1.0)
    assert score.passed, score.failures


def test_wrong_routing_fails():
    result = _result(
        findings=(_finding("600.00 USD"),), dispatches=("order:order_hold",),
        entities={"invoice_id": "S01-INV-1000"},
    )
    score = score_case(CASE, result, 0, 0, 1.0)
    assert not score.passed
    assert not score.routing_ok


def test_missing_finding_fails():
    result = _result(dispatches=("ar:invoice_overdue_dispute",), entities={"invoice_id": "S01-INV-1000"})
    score = score_case(CASE, result, 0, 0, 1.0)
    assert not score.findings_ok


def test_unresolved_citation_fails_even_when_answer_is_right():
    result = _result(
        findings=(_finding("600.00 USD"),), dispatches=("ar:invoice_overdue_dispute",),
        entities={"invoice_id": "S01-INV-1000"},
    )
    score = score_case(CASE, result, citations_total=2, citations_resolved=1, latency_ms=1.0)
    assert not score.passed
    assert any("unresolved" in f for f in score.failures)


def test_fabricated_findings_on_an_abstention_case_fail():
    abstain = EvalCase(
        case_id="a", category="injection", question="q", expect_no_findings=True,
        expected_missing_substring="unsupported_question_pattern",
    )
    result = _result(
        findings=(_finding("All invoices are paid."),),
        missing_data=("unsupported_question_pattern",),
    )
    score = score_case(abstain, result, 0, 0, 1.0)
    assert not score.abstention_ok
