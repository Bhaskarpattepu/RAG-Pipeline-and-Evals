import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.llm_service import LLMService


@pytest.mark.live_llm
def test_chat_live_llm() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY required for live LLM tests")

    client = TestClient(app)
    response = client.post("/api/v1/chat", json={"message": "Explain the difference between HTTP 401 and 403."})
    assert response.status_code == 200
    payload = response.json()
    assert "response" in payload
    assert "model" in payload


def test_chat_without_key_returns_503(monkeypatch) -> None:
    monkeypatch.setattr(LLMService, "available", lambda _self: False)
    client = TestClient(app)
    response = client.post("/api/v1/chat", json={"message": "hello"})
    assert response.status_code == 503


def test_chat_grounds_refund_response_in_policy_documents(monkeypatch) -> None:
    prompts: list[str] = []
    monkeypatch.setattr(LLMService, "available", lambda _self: True)
    monkeypatch.setattr(
        LLMService,
        "chat",
        lambda _self, message, trace_metadata=None: (
            prompts.append(message)
            or {
                "response": "You may request a refund within 30 days of purchase.",
                "model": "test-model",
                "request_id": "test-request",
                "latency_ms": 1,
                "usage": None,
            }
        ),
    )

    response = TestClient(app).post(
        "/api/v1/chat",
        json={"message": "When can I request a refund?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "30 days" in prompts[0]
    assert any(source["filename"] == "refund-policy.md" for source in payload["sources"])
    assert payload["response"] == "You may request a refund within 30 days of purchase."


def test_chat_does_not_claim_purchase_is_eligible_only_from_date(monkeypatch) -> None:
    monkeypatch.setattr(LLMService, "available", lambda _self: True)
    monkeypatch.setattr(
        LLMService,
        "chat",
        lambda *_args, **_kwargs: {
            "response": "You are eligible for an approved refund.",
            "model": "test-model",
            "request_id": "test-request",
            "latency_ms": 1,
            "usage": None,
        },
    )
    response = TestClient(app).post(
        "/api/v1/chat",
        json={"message": "Can I request a refund 12 days after purchase?"},
    )

    assert response.status_code == 200
    answer = response.json()["response"].lower()
    assert "within the policy's 30-day request window" in answer
    assert "does not by itself confirm" in answer
    assert "eligible for an approved refund" not in answer


def test_chat_includes_verified_order_product_and_user_records(monkeypatch) -> None:
    prompts: list[str] = []
    monkeypatch.setattr(LLMService, "available", lambda _self: True)
    monkeypatch.setattr(
        LLMService,
        "chat",
        lambda _self, message, trace_metadata=None: (
            prompts.append(message)
            or {
                "response": "I found the matching order, product, and user records.",
                "model": "test-model",
                "request_id": "test-request",
                "latency_ms": 1,
                "usage": None,
            }
        ),
    )

    response = TestClient(app).post(
        "/api/v1/chat",
        json={
            "message": "Check order ORD-2005, product PROD-1001, and user USER-1001 details.",
        },
    )

    assert response.status_code == 200
    assert "'status': 'failed'" in prompts[0]
    assert "Support Plan" in prompts[0]
    assert "Support Agent" in prompts[0]
    assert {source["type"] for source in response.json()["sources"]} >= {
        "order",
        "payment",
        "product",
        "user",
    }


def test_chat_searches_product_catalog_by_name(monkeypatch) -> None:
    prompts: list[str] = []
    monkeypatch.setattr(LLMService, "available", lambda _self: True)
    monkeypatch.setattr(
        LLMService,
        "chat",
        lambda _self, message, trace_metadata=None: (
            prompts.append(message)
            or {
                "response": "I found the support plan.",
                "model": "test-model",
                "request_id": "test-request",
                "latency_ms": 1,
                "usage": None,
            }
        ),
    )
    response = TestClient(app).post(
        "/api/v1/chat",
        json={"message": "Show me products for support plans."},
    )

    assert response.status_code == 200
    assert "Support Plan" in prompts[0]
    assert any(source["type"] == "product" and source["id"] == "SKU-1001" for source in response.json()["sources"])


def test_chat_creates_durable_approval_for_failed_order_ticket(monkeypatch) -> None:
    monkeypatch.setattr(LLMService, "available", lambda _self: True)
    monkeypatch.setattr(
        LLMService,
        "chat",
        lambda *_args, **_kwargs: {
            "response": "A ticket will be created.",
            "model": "test-model",
            "request_id": "test-request",
            "latency_ms": 1,
            "usage": None,
        },
    )
    client = TestClient(app)
    tickets_before = client.get("/api/v1/tickets").json()
    order_tickets_before = [
        ticket for ticket in tickets_before if ticket["order_id"] == "ORD-2005"
    ]
    response = client.post(
        "/api/v1/chat",
        json={
            "message": "Create a support ticket for failed order ORD-2005.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pending_approval"]["status"] == "pending"
    assert "No ticket has been created" in payload["response"]
    assert any(source["type"] == "order" and source["id"] == "ORD-2005" for source in payload["sources"])
    tickets_before_approval = client.get("/api/v1/tickets").json()
    assert len([ticket for ticket in tickets_before_approval if ticket["order_id"] == "ORD-2005"]) == len(
        order_tickets_before
    )

    resolve_response = client.patch(
        f"/api/v1/approvals/{payload['pending_approval']['id']}",
        json={
            "decision": "approved",
            "approver_id": "supervisor-1",
            "comment": "Verified failed payment and order.",
        },
    )
    assert resolve_response.status_code == 200
    created_ticket_id = resolve_response.json()["payload"]["created_ticket_id"]
    tickets = client.get("/api/v1/tickets").json()
    ticket = next(item for item in tickets if item["id"] == created_ticket_id)
    assert ticket["order_id"] == "ORD-2005"
    assert len([item for item in tickets if item["order_id"] == "ORD-2005"]) == len(order_tickets_before) + 1


def test_chat_asks_for_order_or_customer_id_before_ticket_approval(monkeypatch) -> None:
    monkeypatch.setattr(LLMService, "available", lambda _self: True)
    monkeypatch.setattr(
        LLMService,
        "chat",
        lambda *_args, **_kwargs: {
            "response": "I need an order number.",
            "model": "test-model",
            "request_id": "test-request",
            "latency_ms": 1,
            "usage": None,
        },
    )
    response = TestClient(app).post(
        "/api/v1/chat",
        json={"message": "Create a ticket for my failed order."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pending_approval"] is None
    assert "provide a valid order number or customer ID" in payload["response"]
