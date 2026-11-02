from fastapi.testclient import TestClient

from app.main import app


def test_evaluation_summary_endpoint_returns_summary() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/evaluation")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_rows"] >= 2
    assert "status" in payload
    assert "pass_rate" in payload


def test_evaluation_run_endpoint_runs_dataset_checks() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/evaluation/run",
        json={"dataset_path": "evaluation/datasets/golden_dataset.jsonl"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    assert payload["summary"]["dataset_path"].endswith("golden_dataset.jsonl")
    assert "providers" in payload
