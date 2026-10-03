"""Evaluates the chat guardrails against labeled cases.

Local run (no AWS calls, exits non-zero on any mismatch):
    python scripts/run_guardrail_eval.py

Bedrock evaluation job (LLM-as-judge over the refusals the app returns):
    python scripts/run_guardrail_eval.py --bedrock --bucket <exports-bucket> --role-arn <eval-role-arn>
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from revenueflowai.agents.guardrails import SCOPE_HELP, check_question
from revenueflowai.agents.providers.demo import DemoQuestionPlanner

CASES = Path(__file__).resolve().parent.parent / "evals" / "guardrails" / "cases.jsonl"
JUDGE_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
APP_MODEL_ID = "revenueflow-app"


def load_cases() -> list[dict]:
    return [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]


def predict(question: str) -> tuple[str, str]:
    """Mirrors the chat endpoint: deterministic guardrails first, then the demo
    planner, which refuses questions no specialist can answer. Live mode may
    route differently, so this measures the deterministic path.
    """
    verdict = check_question(question)
    if verdict is not None:
        return "refuse", verdict.message
    plan = asyncio.run(DemoQuestionPlanner().plan(question, None))
    if not plan.dispatches:
        return "refuse", f"That question is outside what I can answer. {SCOPE_HELP}"
    return "answer", "Routed to specialists for a cited answer."


def run_local(cases: list[dict]) -> int:
    failures = 0
    for case in cases:
        got, _ = predict(case["question"])
        expected = "refuse" if case["expect"] in ("refuse", "refuse_scope") else "answer"
        ok = got == expected
        failures += 0 if ok else 1
        status = "PASS" if ok else "FAIL"
        cat = case["category"]
        print(f"{status}  {case['id']:<8} {cat:<17} expected={expected:<7} got={got}")
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


def run_bedrock(cases: list[dict], bucket: str, role_arn: str, region: str) -> None:
    import boto3

    s3 = boto3.client("s3", region_name=region)
    bedrock = boto3.client("bedrock", region_name=region)

    lines = []
    for case in cases:
        _, response = predict(case["question"])
        lines.append(
            json.dumps(
                {
                    "prompt": case["question"],
                    "referenceResponse": "Refuse the request and explain what can be answered.",
                    "modelResponses": [{"response": response, "modelIdentifier": APP_MODEL_ID}],
                }
            )
        )
    run_id = uuid.uuid4().hex[:8]
    key = f"evals/guardrails/{run_id}/input.jsonl"
    s3.put_object(Bucket=bucket, Key=key, Body="\n".join(lines).encode("utf-8"))

    job = bedrock.create_evaluation_job(
        jobName=f"revenueflow-guardrails-{run_id}",
        roleArn=role_arn,
        applicationType="ModelEvaluation",
        evaluationConfig={
            "automated": {
                "datasetMetricConfigs": [
                    {
                        "taskType": "General",
                        "dataset": {
                            "name": "guardrail-cases",
                            "datasetLocation": {"s3Uri": f"s3://{bucket}/{key}"},
                        },
                        "metricNames": ["Builtin.Helpfulness", "Builtin.Harmfulness"],
                    }
                ],
                "evaluatorModelConfig": {"bedrockEvaluatorModels": [{"modelIdentifier": JUDGE_MODEL}]},
            }
        },
        inferenceConfig={
            "models": [{"precomputedInferenceSource": {"inferenceSourceIdentifier": APP_MODEL_ID}}]
        },
        outputDataConfig={"s3Uri": f"s3://{bucket}/evals/guardrails/{run_id}/output/"},
    )
    print(job["jobArn"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bedrock", action="store_true")
    parser.add_argument("--bucket")
    parser.add_argument("--role-arn")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    cases = load_cases()
    if args.bedrock:
        if not args.bucket or not args.role_arn:
            parser.error("--bedrock needs --bucket and --role-arn")
        run_bedrock(cases, args.bucket, args.role_arn, args.region)
        return 0
    return run_local(cases)


if __name__ == "__main__":
    sys.exit(main())
