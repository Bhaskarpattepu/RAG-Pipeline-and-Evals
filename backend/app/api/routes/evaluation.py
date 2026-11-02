from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.metrics.evaluator import run_evaluation, run_live_evaluation

from app.schemas.evaluation import EvaluationRunRequest, EvaluationSummaryResponse

router = APIRouter(tags=["evaluation"])
DEFAULT_DATASET_PATH = "evaluation/datasets/golden_dataset.jsonl"


@router.get("/evaluation", response_model=EvaluationSummaryResponse)
def get_evaluation_summary() -> EvaluationSummaryResponse:
    try:
        summary = run_evaluation(DEFAULT_DATASET_PATH)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return EvaluationSummaryResponse(**summary.to_dict())


def _resolve_report_path(output_path: str | None) -> Path | None:
    if output_path is None:
        return None

    report_root = (REPO_ROOT / "evaluation" / "reports").resolve()
    requested_path = Path(output_path)
    if not requested_path.is_absolute():
        requested_path = report_root / requested_path
    resolved_path = requested_path.resolve()
    if resolved_path == report_root or report_root not in resolved_path.parents:
        raise HTTPException(status_code=400, detail="output_path must be inside evaluation/reports.")
    return resolved_path


@router.post("/evaluation/run", response_model=dict[str, Any])
def run_evaluation_route(payload: EvaluationRunRequest) -> dict[str, Any]:
    if payload.live:
        try:
            return run_live_evaluation(
                payload.dataset_path,
                provider=payload.provider,
                output_path=_resolve_report_path(payload.output_path),
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        summary = run_evaluation(payload.dataset_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "summary": summary.to_dict(),
        "providers": {
            "status": "not_run",
            "message": "Set live=true to generate model outputs and run provider metrics.",
        },
    }
