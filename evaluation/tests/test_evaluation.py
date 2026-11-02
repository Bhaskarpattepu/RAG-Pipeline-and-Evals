import json
import sys
from types import ModuleType

import pytest
from app.api.routes.evaluation import _resolve_report_path
from fastapi import HTTPException

from evaluation.metrics import evaluator
from evaluation.metrics.evaluator import (
    _check_required_fields,
    evaluate_dataset_quality,
    load_golden_dataset,
    run_agent_tool_suite,
    run_evaluation,
    run_live_evaluation,
)


def test_load_golden_dataset_reads_all_rows() -> None:
    rows = load_golden_dataset("evaluation/datasets/golden_dataset.jsonl")
    assert 30 <= len(rows) <= 50
    assert all("prompt" in row for row in rows)
    assert {row["scenario_type"] for row in rows} == {"normal", "negative", "edge", "multi_step"}


def test_run_evaluation_reports_summary() -> None:
    summary = run_evaluation("evaluation/datasets/golden_dataset.jsonl")
    assert summary.total_rows >= 2
    assert summary.status in {"ready", "needs_attention"}
    assert summary.pass_rate == 100
    assert all(gate["passed"] for gate in summary.metadata["quality_gates"])


def test_required_fields_reject_empty_values() -> None:
    assert not _check_required_fields(
        {"prompt": " ", "expected_behavior": "Expected", "category": "education"}
    )


def test_quality_gates_require_human_approval_without_ticket_tool() -> None:
    rows = load_golden_dataset("evaluation/datasets/golden_dataset.jsonl")
    approval_rows = [row for row in rows if row["requires_approval"]]
    assert approval_rows
    assert all("create_support_ticket" not in row["expected_tool_calls"] for row in approval_rows)
    assert all(gate["passed"] for gate in evaluate_dataset_quality(rows))


def test_agent_tool_suite_reports_approval_and_tool_contract(monkeypatch) -> None:
    class FakeAgent:
        def run(self, message):
            return {
                "tool_events": [
                    {"tool": "get_order_status", "executed": True, "status": "completed"},
                    {"tool": "get_payment_status", "executed": True, "status": "completed"},
                    {
                        "tool": "create_support_ticket",
                        "executed": False,
                        "status": "approval_required",
                    },
                ],
                "pending_approval": {"action": "create_support_ticket"},
                "latency_ms": 12,
            }

    monkeypatch.setattr("app.agents.support_agent.SupportAgent", FakeAgent)
    result = run_agent_tool_suite(
        [
            {
                "id": "multi-step-ticket",
                "prompt": "check order and payment then create ticket",
                "scenario_type": "multi_step",
                "expected_tool_calls": ["get_order_status", "get_payment_status"],
                "requires_approval": True,
            }
        ]
    )

    assert result["status"] == "completed"
    assert result["critical_safety_failures"] == 0
    assert result["cases"][0]["passed"]


def test_all_golden_tool_and_approval_expectations_pass(monkeypatch) -> None:
    async def fake_call_mcp_tool(tool_name, arguments=None):
        return {"tool": tool_name, "result": {"ok": True}}

    monkeypatch.setattr("app.agents.support_agent.call_mcp_tool", fake_call_mcp_tool)
    rows = load_golden_dataset("evaluation/datasets/golden_dataset.jsonl")
    result = run_agent_tool_suite(rows)

    assert result["status"] == "completed", [
        case for case in result["cases"] if not case["passed"]
    ]
    assert result["passed"] == len(rows)
    assert result["critical_safety_failures"] == 0


def test_report_path_is_limited_to_report_directory() -> None:
    report_path = _resolve_report_path("sample.json")
    assert report_path is not None
    assert report_path.parent.name == "reports"

    with pytest.raises(HTTPException) as exc_info:
        _resolve_report_path("../../README.md")
    assert exc_info.value.status_code == 400


def test_live_evaluation_exports_report_without_provider_calls(tmp_path, monkeypatch) -> None:
    report_path = tmp_path / "report.json"
    monkeypatch.setattr(evaluator.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        evaluator,
        "_generate_responses",
        lambda dataset, evaluation_run_id: [
            {
                "id": "sample",
                "category": "education",
                "input": dataset[0]["prompt"],
                "expected_behavior": dataset[0]["expected_behavior"],
                "actual_output": "A test answer.",
                "retrieval_contexts": [],
                "model": "test-model",
                "latency_ms": 1,
                "request_id": "req-test",
            }
        ],
    )
    monkeypatch.setattr(
        evaluator,
        "run_agent_tool_suite",
        lambda _dataset: {
            "provider": "agent_tools",
            "status": "completed",
            "total": 1,
            "passed": 1,
            "failed": 0,
            "critical_safety_failures": 0,
            "mean_latency_ms": 1,
            "cases": [],
        },
    )
    monkeypatch.setattr(
        evaluator,
        "run_deepeval_suite",
        lambda cases: {
            "provider": "deepeval",
            "status": "completed",
            "mean_score": 0.8,
        },
    )

    report = run_live_evaluation(
        "evaluation/datasets/golden_dataset.jsonl",
        provider="deepeval",
        output_path=report_path,
    )

    assert report["status"] == "completed"
    assert report["providers"]["deepeval"]["status"] == "completed"
    assert all(gate["passed"] for gate in report["quality_gates"])
    assert report["langsmith"]["filter"]["evaluation_run_id"] == report["evaluation_run_id"]
    assert report["report_path"] == str(report_path)
    saved_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved_report["cases"][0]["actual_output"] == "A test answer."


def test_live_evaluation_requires_openai_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(evaluator.settings, "openai_api_key", None)
    monkeypatch.setattr(evaluator, "_generate_responses", lambda *_: [])

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        run_live_evaluation(
            "evaluation/datasets/golden_dataset.jsonl",
            provider="deepeval",
            output_path=tmp_path / "report.json",
        )


def test_unavailable_provider_is_exported_as_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(evaluator.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        evaluator,
        "_provider_import_error",
        lambda _provider: "missing test dependency",
    )
    monkeypatch.setattr(
        evaluator,
        "run_agent_tool_suite",
        lambda _dataset: {
            "provider": "agent_tools",
            "status": "completed",
            "total": 1,
            "passed": 1,
            "failed": 0,
            "critical_safety_failures": 0,
            "mean_latency_ms": 1,
            "cases": [],
        },
    )
    report_path = tmp_path / "provider-error.json"

    report = run_live_evaluation(
        "evaluation/datasets/golden_dataset.jsonl",
        provider="ragas",
        output_path=report_path,
    )

    assert report["status"] == "failed"
    assert report["providers"]["ragas"]["status"] == "failed"
    assert report["providers"]["ragas"]["error"] == (
        "Provider dependencies could not be imported: missing test dependency"
    )
    assert report["cases"] == []
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "failed"


def test_live_quality_gate_fails_on_low_score_and_approval_safety_failure(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(evaluator.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(evaluator, "_provider_import_error", lambda _provider: None)
    monkeypatch.setattr(
        evaluator,
        "_generate_responses",
        lambda *_: [
            {
                "id": "sample",
                "category": "education",
                "input": "Question",
                "expected_behavior": "Expected behavior",
                "actual_output": "Answer",
                "retrieval_contexts": [],
                "model": "test-model",
                "latency_ms": 1,
                "request_id": "req-test",
            }
        ],
    )
    monkeypatch.setattr(
        evaluator,
        "run_deepeval_suite",
        lambda _cases: {"provider": "deepeval", "status": "completed", "mean_score": 0.69},
    )
    monkeypatch.setattr(
        evaluator,
        "run_agent_tool_suite",
        lambda _dataset: {
            "provider": "agent_tools",
            "status": "failed",
            "total": 1,
            "passed": 0,
            "failed": 1,
            "critical_safety_failures": 1,
            "mean_latency_ms": 1,
            "cases": [],
        },
    )

    report = run_live_evaluation(
        "evaluation/datasets/golden_dataset.jsonl",
        provider="deepeval",
        output_path=tmp_path / "failed-gates.json",
    )

    assert report["status"] == "failed"
    assert not next(
        gate for gate in report["quality_gates"] if gate["name"] == "agent_tool_and_approval_checks"
    )["passed"]
    assert not next(
        gate for gate in report["quality_gates"] if gate["name"] == "deepeval_minimum_score"
    )["passed"]


def test_deepeval_suite_returns_real_metric_results(monkeypatch) -> None:
    class FakeMetric:
        name = "Expected behavior adherence"
        score = None
        success = False
        reason = ""

        def __init__(self, **_kwargs):
            pass

        def measure(self, _test_case):
            self.score = 0.8
            self.success = True
            self.reason = "The response followed the expected behavior."

    class FakeTestCase:
        def __init__(self, **kwargs):
            self.values = kwargs

    class FakeModel:
        def __init__(self, **_kwargs):
            pass

    metrics_module = ModuleType("deepeval.metrics")
    metrics_module.GEval = FakeMetric
    models_module = ModuleType("deepeval.models")
    models_module.OpenAIModel = FakeModel
    testcase_module = ModuleType("deepeval.test_case")
    testcase_module.LLMTestCase = FakeTestCase
    testcase_module.SingleTurnParams = type(
        "SingleTurnParams",
        (),
        {
            "INPUT": "input",
            "ACTUAL_OUTPUT": "actual_output",
            "EXPECTED_OUTPUT": "expected_output",
            "RETRIEVAL_CONTEXT": "retrieval_context",
        },
    )
    monkeypatch.setitem(sys.modules, "deepeval.metrics", metrics_module)
    monkeypatch.setitem(sys.modules, "deepeval.models", models_module)
    monkeypatch.setitem(sys.modules, "deepeval.test_case", testcase_module)
    monkeypatch.setattr(evaluator.settings, "openai_api_key", "test-key")

    result = evaluator.run_deepeval_suite(
        [
            {
                "id": "case-1",
                "input": "User question",
                "actual_output": "Generated answer",
                "expected_behavior": "Expected answer behavior",
                "retrieval_contexts": ["Relevant context"],
            }
        ]
    )

    assert result["status"] == "completed"
    assert result["mean_score"] == 0.8
    assert result["passed"] == 1
    assert result["cases"][0]["reason"] == "The response followed the expected behavior."


def test_ragas_suite_returns_real_metric_results(monkeypatch) -> None:
    class FakeDataset:
        @classmethod
        def from_list(cls, rows):
            return rows

    class FakeEvaluation:
        def __getitem__(self, metric_name):
            assert metric_name == "answer_relevancy"
            return [0.9, float("nan")]

    def fake_evaluate(**kwargs):
        assert kwargs["metrics"] == ["answer_relevancy"]
        assert kwargs["raise_exceptions"] is True
        return FakeEvaluation()

    ragas_module = ModuleType("ragas")
    ragas_module.EvaluationDataset = FakeDataset
    ragas_module.evaluate = fake_evaluate
    ragas_metrics_module = ModuleType("ragas.metrics")
    ragas_metrics_module.answer_relevancy = "answer_relevancy"
    langchain_openai_module = ModuleType("langchain_openai")
    langchain_openai_module.ChatOpenAI = lambda **_kwargs: object()
    langchain_openai_module.OpenAIEmbeddings = lambda **_kwargs: object()
    monkeypatch.setitem(sys.modules, "ragas", ragas_module)
    monkeypatch.setitem(sys.modules, "ragas.metrics", ragas_metrics_module)
    monkeypatch.setitem(sys.modules, "langchain_openai", langchain_openai_module)
    monkeypatch.setattr(evaluator.settings, "openai_api_key", "test-key")

    result = evaluator.run_ragas_suite(
        [
            {
                "id": "case-1",
                "input": "User question",
                "actual_output": "Generated answer",
                "retrieval_contexts": [],
            },
            {
                "id": "case-2",
                "input": "Another user question",
                "actual_output": "Another generated answer",
                "retrieval_contexts": [],
            },
        ]
    )

    assert result["status"] == "completed"
    assert result["mean_score"] == 0.9
    assert result["cases"] == [
        {"id": "case-1", "score": 0.9},
        {"id": "case-2", "score": None},
    ]


def test_ragas_dependencies_import_with_supported_langchain_community() -> None:
    assert evaluator._provider_import_error("ragas") is None
