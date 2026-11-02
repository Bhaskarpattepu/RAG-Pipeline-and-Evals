from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.observability.langsmith import trace_ai_operation


@dataclass
class EvaluationSummary:
    dataset_path: str
    total_rows: int
    passed_checks: int
    failed_checks: int
    status: str = "ready"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def pass_rate(self) -> float:
        if self.total_rows == 0:
            return 0.0
        return round((self.passed_checks / self.total_rows) * 100, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "total_rows": self.total_rows,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "status": self.status,
            "pass_rate": self.pass_rate,
            "metadata": self.metadata,
        }


def load_golden_dataset(path: str | Path) -> list[dict[str, Any]]:
    dataset_path = Path(path)
    rows: list[dict[str, Any]] = []
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    with dataset_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            rows.append(json.loads(stripped))
    return rows


def _check_required_fields(item: dict[str, Any]) -> bool:
    required = {
        "prompt",
        "expected_behavior",
        "category",
        "scenario_type",
        "expected_tool_calls",
        "requires_approval",
    }
    if not required.issubset(item.keys()):
        return False
    if not isinstance(item["prompt"], str) or not item["prompt"].strip():
        return False
    if not isinstance(item["expected_behavior"], str) or not item["expected_behavior"].strip():
        return False
    if not isinstance(item["category"], str) or not item["category"].strip():
        return False
    if item["scenario_type"] not in {"normal", "negative", "edge", "multi_step"}:
        return False
    if not isinstance(item["expected_tool_calls"], list) or any(
        not isinstance(tool, str) or not tool for tool in item["expected_tool_calls"]
    ):
        return False
    return isinstance(item["requires_approval"], bool)


def summarize_categories(rows: list[dict[str, Any]]) -> dict[str, int]:
    categories: dict[str, int] = {}
    for row in rows:
        category = str(row.get("category", "unknown")).strip() or "unknown"
        categories[category] = categories.get(category, 0) + 1
    return dict(sorted(categories.items()))


def evaluate_dataset_quality(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scenario_types = {row.get("scenario_type") for row in rows}
    safety_rows = [row for row in rows if row.get("requires_approval") is True]
    gates = [
        {
            "name": "dataset_size",
            "passed": 30 <= len(rows) <= 50,
            "critical": True,
            "actual": len(rows),
            "expected": "30 to 50 cases",
        },
        {
            "name": "scenario_coverage",
            "passed": {"normal", "negative", "edge", "multi_step"}.issubset(scenario_types),
            "critical": True,
            "actual": sorted(str(item) for item in scenario_types),
            "expected": ["normal", "negative", "edge", "multi_step"],
        },
        {
            "name": "approval_cases_do_not_expect_ticket_execution",
            "passed": all(
                "create_support_ticket" not in row.get("expected_tool_calls", [])
                for row in safety_rows
            ),
            "critical": True,
            "actual": len(safety_rows),
            "expected": "No ticket-create tool call before human approval",
        },
        {
            "name": "approval_cases_present",
            "passed": bool(safety_rows),
            "critical": True,
            "actual": len(safety_rows),
            "expected": "At least one approval-required scenario",
        },
    ]
    return gates


def run_evaluation(dataset_path: str | Path) -> EvaluationSummary:
    dataset = load_golden_dataset(dataset_path)
    passed = 0
    failed = 0
    for item in dataset:
        if _check_required_fields(item):
            passed += 1
        else:
            failed += 1

    quality_gates = evaluate_dataset_quality(dataset)
    all_gates_passed = all(gate["passed"] for gate in quality_gates)
    summary = EvaluationSummary(
        dataset_path=str(dataset_path),
        total_rows=len(dataset),
        passed_checks=passed,
        failed_checks=failed,
        status="ready" if failed == 0 and all_gates_passed else "needs_attention",
        metadata={
            "dataset_name": Path(dataset_path).name,
            "categories": summarize_categories(dataset),
            "pass_rate": round((passed / len(dataset) * 100), 2) if dataset else 0.0,
            "quality_gates": quality_gates,
        },
    )
    return summary


def export_summary(summary: EvaluationSummary, output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
    return output


def _generate_responses(dataset: list[dict[str, Any]], evaluation_run_id: str) -> list[dict[str, Any]]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for live evaluation.")

    from app.services.llm_service import LLMService

    llm = LLMService()
    cases: list[dict[str, Any]] = []
    for index, row in enumerate(dataset):
        context = row.get("retrieval_contexts", [])
        if not isinstance(context, list) or any(not isinstance(item, str) for item in context):
            raise ValueError(f"Dataset row {index + 1} has invalid retrieval_contexts; expected a list of strings.")

        prompt = row["prompt"]
        if context:
            context_text = "\n".join(context)
            model_input = (
                "Answer the user using the reference context when relevant. Do not invent policy details.\n"
                f"Reference context:\n{context_text}\n\n"
                f"User request:\n{prompt}"
            )
        else:
            model_input = prompt

        case_id = str(row.get("id", f"case-{index + 1}"))
        with trace_ai_operation(
            "support_evaluation_case",
            evaluation_run_id=evaluation_run_id,
            case_id=case_id,
            category=row["category"],
        ):
            response = llm.chat(
                model_input,
                trace_metadata={
                    "evaluation_run_id": evaluation_run_id,
                    "case_id": case_id,
                    "category": row["category"],
                },
            )
        cases.append(
            {
                "id": case_id,
                "category": row["category"],
                "input": prompt,
                "expected_behavior": row["expected_behavior"],
                "actual_output": response["response"],
                "retrieval_contexts": context,
                "model": response["model"],
                "latency_ms": response["latency_ms"],
                "usage": response.get("usage"),
                "request_id": response["request_id"],
            }
        )
    return cases


def _require_evaluation_key() -> None:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required to run model-based evaluation.")


def _mean_score(scores: list[float | None]) -> float | None:
    available = [score for score in scores if score is not None and math.isfinite(score)]
    if not available:
        return None
    return round(sum(available) / len(available), 4)


def run_ragas_suite(cases: list[dict[str, Any]]) -> dict[str, Any]:
    _require_evaluation_key()
    try:
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        from ragas import EvaluationDataset, evaluate
        from ragas.metrics import answer_relevancy
    except ImportError as exc:  # pragma: no cover - depends on optional provider installation
        raise RuntimeError(f"RAGAS dependencies could not be imported: {exc}") from exc

    from importlib.metadata import version

    dataset = EvaluationDataset.from_list(
        [
            {
                "user_input": case["input"],
                "response": case["actual_output"],
            }
            for case in cases
        ]
    )
    evaluator_llm = ChatOpenAI(
        model=settings.openai_evaluation_model,
        api_key=settings.openai_api_key,
    )
    evaluator_embeddings = OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
    )
    result = evaluate(
        dataset=dataset,
        metrics=[answer_relevancy],
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
        raise_exceptions=True,
    )
    scores = []
    for score in result["answer_relevancy"]:
        numeric_score = float(score) if score is not None else None
        scores.append(numeric_score if numeric_score is not None and math.isfinite(numeric_score) else None)
    return {
        "provider": "ragas",
        "version": version("ragas"),
        "status": "completed",
        "metric": "answer_relevancy",
        "mean_score": _mean_score(scores),
        "cases": [
            {"id": case["id"], "score": score}
            for case, score in zip(cases, scores, strict=True)
        ],
    }


def run_deepeval_suite(cases: list[dict[str, Any]]) -> dict[str, Any]:
    _require_evaluation_key()
    try:
        from deepeval.metrics import GEval
        from deepeval.models import OpenAIModel
        from deepeval.test_case import LLMTestCase, SingleTurnParams
    except ImportError as exc:  # pragma: no cover - depends on optional provider installation
        raise RuntimeError(f"DeepEval dependencies could not be imported: {exc}") from exc

    from importlib.metadata import version

    evaluator_model = OpenAIModel(
        model=settings.openai_evaluation_model,
        api_key=settings.openai_api_key,
    )
    metric = GEval(
        name="Expected behavior adherence",
        criteria=(
            "Assess whether the answer follows the expected behavior for the user request. "
            "Reward correctness, completeness, and appropriate policy grounding. "
            "Penalize unsupported claims, missed approval requirements, and irrelevant content."
        ),
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.EXPECTED_OUTPUT,
            SingleTurnParams.RETRIEVAL_CONTEXT,
        ],
        model=evaluator_model,
        threshold=0.5,
        async_mode=False,
    )
    evaluated_cases: list[dict[str, Any]] = []
    scores: list[float | None] = []
    for case in cases:
        test_case = LLMTestCase(
            input=case["input"],
            actual_output=case["actual_output"],
            expected_output=case["expected_behavior"],
            retrieval_context=case["retrieval_contexts"],
        )
        metric.measure(test_case)
        score = float(metric.score) if metric.score is not None else None
        if score is not None and not math.isfinite(score):
            score = None
        scores.append(score)
        evaluated_cases.append(
            {
                "id": case["id"],
                "score": score,
                "passed": bool(metric.success),
                "reason": metric.reason,
            }
        )
    return {
        "provider": "deepeval",
        "version": version("deepeval"),
        "status": "completed",
        "metric": metric.name,
        "mean_score": _mean_score(scores),
        "passed": sum(1 for case in evaluated_cases if case["passed"]),
        "failed": sum(1 for case in evaluated_cases if not case["passed"]),
        "cases": evaluated_cases,
    }


def _provider_import_error(provider: str) -> str | None:
    try:
        if provider == "ragas":
            from langchain_openai import ChatOpenAI, OpenAIEmbeddings  # noqa: F401
            from ragas import EvaluationDataset, evaluate  # noqa: F401
            from ragas.metrics import answer_relevancy  # noqa: F401
        elif provider == "deepeval":
            from deepeval.metrics import GEval  # noqa: F401
            from deepeval.models import OpenAIModel  # noqa: F401
            from deepeval.test_case import LLMTestCase, SingleTurnParams  # noqa: F401
        else:
            raise ValueError(f"Unknown evaluation provider: {provider}")
    except ImportError as exc:  # pragma: no cover - depends on optional provider installation
        return str(exc)
    return None


def run_agent_tool_suite(dataset: list[dict[str, Any]]) -> dict[str, Any]:
    from app.agents.support_agent import SupportAgent

    evaluated_cases: list[dict[str, Any]] = []
    agent = SupportAgent()
    for row in dataset:
        expected_tools = set(row["expected_tool_calls"])
        result = agent.run(row["prompt"])
        events = result["tool_events"]
        actual_tools = {event["tool"] for event in events if event.get("executed") is True}
        failed_tools = {
            event["tool"] for event in events if event.get("status") == "failed"
        }
        approval_required = row["requires_approval"]
        approval_pending = result["pending_approval"] is not None
        ticket_creation_executed = any(
            event.get("tool") == "create_support_ticket" and event.get("executed") is True
            for event in events
        )
        checks = {
            "expected_tools_called": expected_tools == actual_tools,
            "expected_tools_succeeded": not (expected_tools & failed_tools),
            "approval_state_matches": approval_pending == approval_required,
            "ticket_creation_waits_for_approval": not ticket_creation_executed,
        }
        evaluated_cases.append(
            {
                "id": row["id"],
                "scenario_type": row["scenario_type"],
                "expected_tools": sorted(expected_tools),
                "actual_tools": sorted(actual_tools),
                "approval_required": approval_required,
                "approval_pending": approval_pending,
                "ticket_creation_executed": ticket_creation_executed,
                "checks": checks,
                "passed": all(checks.values()),
                "latency_ms": result["latency_ms"],
                "tool_events": events,
            }
        )

    failures = [
        case for case in evaluated_cases if not case["passed"]
    ]
    return {
        "provider": "agent_tools",
        "status": "completed" if not failures else "failed",
        "total": len(evaluated_cases),
        "passed": len(evaluated_cases) - len(failures),
        "failed": len(failures),
        "critical_safety_failures": sum(
            1
            for case in failures
            if case["ticket_creation_executed"]
            or (case["approval_required"] and not case["approval_pending"])
        ),
        "mean_latency_ms": (
            round(sum(case["latency_ms"] for case in evaluated_cases) / len(evaluated_cases), 2)
            if evaluated_cases
            else 0
        ),
        "cases": evaluated_cases,
    }


def run_live_evaluation(
    dataset_path: str | Path,
    provider: str = "both",
    output_path: str | Path | None = None,
    min_deepeval_score: float = 0.7,
    min_ragas_score: float = 0.7,
) -> dict[str, Any]:
    if provider not in {"ragas", "deepeval", "both"}:
        raise ValueError("provider must be one of: ragas, deepeval, both")
    if not 0 <= min_deepeval_score <= 1 or not 0 <= min_ragas_score <= 1:
        raise ValueError("Minimum evaluation scores must be between 0 and 1.")
    _require_evaluation_key()

    dataset = load_golden_dataset(dataset_path)
    if not dataset:
        raise ValueError("Cannot run a live evaluation with an empty dataset.")
    invalid_rows = [index + 1 for index, row in enumerate(dataset) if not _check_required_fields(row)]
    if invalid_rows:
        raise ValueError(f"Invalid required fields in dataset rows: {invalid_rows}")
    offline_summary = run_evaluation(dataset_path)
    if offline_summary.status != "ready":
        raise ValueError(f"Dataset quality gates failed: {offline_summary.metadata['quality_gates']}")

    evaluation_run_id = str(uuid4())
    providers: dict[str, Any] = {}
    requested_providers = ("ragas", "deepeval") if provider == "both" else (provider,)
    available_providers: list[str] = []
    for provider_name in requested_providers:
        import_error = _provider_import_error(provider_name)
        if import_error is not None:
            providers[provider_name] = {
                "provider": provider_name,
                "status": "failed",
                "error": f"Provider dependencies could not be imported: {import_error}",
            }
        else:
            available_providers.append(provider_name)

    cases = _generate_responses(dataset, evaluation_run_id) if available_providers else []
    provider_runners = {"ragas": run_ragas_suite, "deepeval": run_deepeval_suite}
    for provider_name in available_providers:
        try:
            with trace_ai_operation(
                "evaluation_metric",
                evaluation_run_id=evaluation_run_id,
                provider=provider_name,
            ):
                providers[provider_name] = provider_runners[provider_name](cases)
        except RuntimeError as exc:
            providers[provider_name] = {
                "provider": provider_name,
                "status": "failed",
                "error": str(exc),
            }

    with trace_ai_operation(
        "support_agent_tool_evaluation",
        evaluation_run_id=evaluation_run_id,
        dataset_rows=len(dataset),
    ) as trace_run:
        tool_evaluation = run_agent_tool_suite(dataset)
        if trace_run is not None:
            trace_run.outputs = {
                "status": tool_evaluation["status"],
                "passed": tool_evaluation["passed"],
                "failed": tool_evaluation["failed"],
                "critical_safety_failures": tool_evaluation["critical_safety_failures"],
            }

    quality_gates: list[dict[str, Any]] = [
        {
            "name": "agent_tool_and_approval_checks",
            "passed": tool_evaluation["status"] == "completed",
            "critical": True,
            "actual": tool_evaluation["failed"],
            "expected": 0,
        }
    ]
    score_thresholds = {"deepeval": min_deepeval_score, "ragas": min_ragas_score}
    for provider_name in requested_providers:
        result = providers.get(provider_name, {})
        score = result.get("mean_score")
        threshold = score_thresholds[provider_name]
        score_passed = (
            result.get("status") == "completed"
            and isinstance(score, (int, float))
            and math.isfinite(score)
            and score >= threshold
        )
        quality_gates.append(
            {
                "name": f"{provider_name}_minimum_score",
                "passed": score_passed,
                "critical": False,
                "actual": score,
                "expected": threshold,
            }
        )
    all_quality_gates_passed = all(gate["passed"] for gate in quality_gates)
    report = {
        "evaluation_run_id": evaluation_run_id,
        "status": (
            "completed" if all_quality_gates_passed else "failed"
        ),
        "dataset_path": str(dataset_path),
        "dataset_rows": len(dataset),
        "generation_model": settings.openai_model,
        "evaluation_model": settings.openai_evaluation_model,
        "providers": providers,
        "agent_tool_evaluation": tool_evaluation,
        "quality_gates": quality_gates,
        "cases": cases,
        "langsmith": {
            "enabled": settings.langsmith_tracing,
            "project": settings.langsmith_project if settings.langsmith_tracing else None,
            "dashboard_url": "https://smith.langchain.com" if settings.langsmith_tracing else None,
            "filter": {"evaluation_run_id": evaluation_run_id},
        },
    }
    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        report["report_path"] = str(output)
        output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report
