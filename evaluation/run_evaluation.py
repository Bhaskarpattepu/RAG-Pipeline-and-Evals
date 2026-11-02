from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_PATH = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from evaluation.metrics.evaluator import run_evaluation, run_live_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the golden dataset or run live AI evaluation.")
    parser.add_argument(
        "--dataset",
        default="evaluation/datasets/golden_dataset.jsonl",
        help="Path to the JSONL evaluation dataset.",
    )
    parser.add_argument("--live", action="store_true", help="Generate model responses and run provider metrics.")
    parser.add_argument(
        "--provider",
        choices=("deepeval", "ragas", "both"),
        default="both",
        help="Metric provider(s) to run in live mode.",
    )
    parser.add_argument(
        "--output",
        default="evaluation/reports/latest.json",
        help="Path for the JSON report produced in live mode.",
    )
    parser.add_argument(
        "--min-deepeval-score",
        type=float,
        default=0.7,
        help="Minimum mean DeepEval score required for a passing live run.",
    )
    parser.add_argument(
        "--min-ragas-score",
        type=float,
        default=0.7,
        help="Minimum mean RAGAS score required for a passing live run.",
    )
    parser.add_argument(
        "--quality-gate",
        action="store_true",
        help="Exit nonzero when the offline golden-dataset quality gates fail.",
    )
    args = parser.parse_args()

    if args.live:
        report = run_live_evaluation(
            args.dataset,
            provider=args.provider,
            output_path=args.output,
            min_deepeval_score=args.min_deepeval_score,
            min_ragas_score=args.min_ragas_score,
        )
        print(json.dumps(report, indent=2))
        if report["status"] != "completed":
            raise SystemExit(1)
        return

    summary = run_evaluation(args.dataset)
    print(json.dumps(summary.to_dict(), indent=2))
    if args.quality_gate and summary.status != "ready":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
