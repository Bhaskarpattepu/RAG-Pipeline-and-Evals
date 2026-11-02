from typing import Any, Literal

from pydantic import BaseModel, Field


class EvaluationRunRequest(BaseModel):
    dataset_path: str = "evaluation/datasets/golden_dataset.jsonl"
    live: bool = False
    provider: Literal["deepeval", "ragas", "both"] = "both"
    output_path: str | None = None


class EvaluationSummaryResponse(BaseModel):
    dataset_path: str
    total_rows: int
    passed_checks: int
    failed_checks: int
    status: str = "ready"
    pass_rate: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
