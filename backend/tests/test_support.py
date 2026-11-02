from fastapi.testclient import TestClient

from app.main import app


def test_ticket_create() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/tickets",
        json={
            "customer_id": "CUST-1001",
            "subject": "Issue with order",
            "description": "Payment failed",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["subject"] == "Issue with order"
