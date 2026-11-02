from fastapi.testclient import TestClient

from app.main import app


def test_create_approval_request() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/approvals",
        json={
            "tenant_id": "tenant-demo",
            "user_id": "support-agent",
            "action": "create_support_ticket",
            "target_type": "support_ticket",
            "target_id": "TKT-1002",
            "reason": "Requires human approval before ticket creation.",
            "payload": {"customer_id": "CUST-1001", "summary": "Order investigation"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["action"] == "create_support_ticket"


def test_resolve_approval_request() -> None:
    client = TestClient(app)
    create_response = client.post(
        "/api/v1/approvals",
        json={
            "tenant_id": "tenant-demo",
            "user_id": "support-agent",
            "action": "update_ticket_status",
            "target_type": "support_ticket",
            "target_id": "TKT-1002",
            "reason": "Update status after resolution.",
            "payload": {"status": "closed"},
        },
    )
    approval_id = create_response.json()["id"]
    decision_response = client.patch(
        f"/api/v1/approvals/{approval_id}",
        json={"decision": "approved", "approver_id": "supervisor-user", "comment": "Looks valid."},
    )
    assert decision_response.status_code == 200
    assert decision_response.json()["status"] == "approved"
