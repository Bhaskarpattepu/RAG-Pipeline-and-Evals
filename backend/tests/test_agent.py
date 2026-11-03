import asyncio

from fastapi.testclient import TestClient

from app.agents.support_agent import SupportAgent
from app.main import app


def test_agent_requires_approval_for_ticket_creation() -> None:
    agent = SupportAgent()
    result = agent.run("Customer CUST-1001 reports a failed order and wants a support ticket created.")
    assert "conversation_id" in result
    assert result["pending_approval"] is not None
    assert "support ticket" in result["final_answer"].lower()


def test_agent_uses_policy_context() -> None:
    agent = SupportAgent()
    result = agent.run("Check the refund policy for order ORD-2005.")
    assert result["final_answer"]
    assert "refund" in result["final_answer"].lower()


def test_agent_checks_multiple_tools_but_never_creates_ticket_before_approval(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_call_mcp_tool(tool_name, arguments=None):
        calls.append(tool_name)
        return {"tool": tool_name, "result": {"status": "ok"}}

    monkeypatch.setattr("app.agents.support_agent.call_mcp_tool", fake_call_mcp_tool)
    result = SupportAgent().run(
        "Order ORD-2005 payment failed. Check the order and payment and create a support ticket."
    )

    assert calls == ["get_order_status", "get_payment_status"]
    assert result["pending_approval"]["action"] == "create_support_ticket"
    assert not any(
        event["tool"] == "create_support_ticket" and event["executed"]
        for event in result["tool_events"]
    )
    assert any(
        event["tool"] == "create_support_ticket"
        and event["status"] == "approval_required"
        and event["executed"] is False
        for event in result["tool_events"]
    )


def test_agent_routes_payment_status_without_order_lookup(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_call_mcp_tool(tool_name, arguments=None):
        calls.append(tool_name)
        return {"tool": tool_name, "result": {"status": "ok"}}

    monkeypatch.setattr("app.agents.support_agent.call_mcp_tool", fake_call_mcp_tool)
    result = SupportAgent().run("Check the payment status for order ORD-2005.")

    assert calls == ["get_payment_status"]
    assert [event["tool"] for event in result["tool_events"] if event["executed"]] == [
        "get_payment_status"
    ]


def test_agent_does_not_lookup_order_for_payment_failure_policy_question(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_call_mcp_tool(tool_name, arguments=None):
        calls.append(tool_name)
        return {"tool": tool_name, "result": {"status": "ok"}}

    monkeypatch.setattr("app.agents.support_agent.call_mcp_tool", fake_call_mcp_tool)
    SupportAgent().run(
        "Check payment for order ORD-2005 and explain what policy says after a failed retry."
    )

    assert calls == ["get_payment_status"]


def test_agent_supports_order_lookup_wording_variants(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_call_mcp_tool(tool_name, arguments=None):
        calls.append(tool_name)
        return {"tool": tool_name, "result": {"structured_content": {"status": "shipped"}}}

    monkeypatch.setattr("app.agents.support_agent.call_mcp_tool", fake_call_mcp_tool)
    result = SupportAgent().run("Find order ord-2005.")

    assert calls == ["get_order_status"]
    assert result["tool_events"][0]["status"] == "completed"


def test_agent_does_not_call_ticket_search_without_customer_id(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_call_mcp_tool(tool_name, arguments=None):
        calls.append(tool_name)
        return {"tool": tool_name, "result": {"structured_content": []}}

    monkeypatch.setattr("app.agents.support_agent.call_mcp_tool", fake_call_mcp_tool)
    result = SupportAgent().run("Search for existing tickets.")

    assert calls == []
    assert result["tool_events"] == []
    assert "customer ID" in result["final_answer"]


def test_agent_passes_tenant_to_refund_lookup(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_call_mcp_tool(tool_name, arguments=None):
        calls.append((tool_name, arguments or {}))
        return {
            "tool": tool_name,
            "result": {
                "structured_content": {
                    "refund_id": "REF-1005",
                    "status": "pending_review",
                }
            },
        }

    monkeypatch.setattr("app.agents.support_agent.call_mcp_tool", fake_call_mcp_tool)
    result = SupportAgent().run("Check refund status REF-1005.", tenant_id="tenant-test")

    assert calls == [
        (
            "get_refund_status",
            {"refund_id": "REF-1005", "tenant_id": "tenant-test"},
        )
    ]
    assert result["tool_events"][0]["status"] == "completed"


def test_agent_accepts_list_results_from_search_tools(monkeypatch) -> None:
    async def fake_call_mcp_tool(tool_name, arguments=None):
        return {
            "tool": tool_name,
            "result": {
                "structured_content": [
                    {"product_id": "PROD-1001", "name": "Support Plan"}
                ]
            },
        }

    monkeypatch.setattr("app.agents.support_agent.call_mcp_tool", fake_call_mcp_tool)
    result = SupportAgent().run("Search products for support plans.")

    assert result["tool_events"][0]["tool"] == "search_products"
    assert result["tool_events"][0]["status"] == "completed"


def test_agent_endpoint_persists_approval_for_verified_ticket_request() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/agent/run",
        json={
            "message": "Create a support ticket for customer CUST-1001 about order ORD-2005.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    approval = payload["pending_approval"]
    assert approval["id"]
    assert approval["status"] == "pending"
    assert "No ticket was created" in payload["final_answer"]

    approval_response = client.get("/api/v1/approvals")
    assert approval_response.status_code == 200
    assert any(row["id"] == approval["id"] for row in approval_response.json())

    repeated_response = client.post(
        "/api/v1/agent/run",
        json={
            "message": "Create a support ticket for customer CUST-1001 about order ORD-2005.",
        },
    )
    assert repeated_response.json()["pending_approval"]["id"] == approval["id"]


def test_agent_endpoint_does_not_create_approval_for_unknown_customer() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/agent/run",
        json={
            "message": "Create a support ticket for customer CUST-DOES-NOT-EXIST.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pending_approval"] is None
    assert "could not verify" in payload["final_answer"].lower()
    assert any(
        event["tool"] == "create_support_ticket"
        and event["status"] == "clarification_required"
        and event["executed"] is False
        for event in payload["tool_events"]
    )


def test_agent_endpoint_rejects_customer_mismatch_for_order_ticket() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/agent/run",
        json={
            "message": (
                "Create a support ticket for customer CUST-DOES-NOT-EXIST "
                "about order ORD-2005."
            ),
        },
    )

    assert response.status_code == 200
    assert response.json()["pending_approval"] is None
    assert "no approval request" in response.json()["final_answer"].lower()


def test_agent_marks_mcp_error_results_as_failed(monkeypatch) -> None:
    async def fake_call_mcp_tool(tool_name, arguments=None):
        return {
            "tool": tool_name,
            "result": {
                "is_error": True,
                "structured_content": {"error": "backend details must not be exposed"},
            },
        }

    monkeypatch.setattr("app.agents.support_agent.call_mcp_tool", fake_call_mcp_tool)
    result = SupportAgent().run("Check the payment status for order ORD-2005.")

    assert result["tool_events"][0]["status"] == "failed"
    assert "backend details must not be exposed" not in result["final_answer"]
    assert "could not complete" in result["final_answer"].lower()


def test_agent_treats_malformed_mcp_result_as_failed(monkeypatch) -> None:
    async def fake_call_mcp_tool(tool_name, arguments=None):
        return {"tool": tool_name, "result": None}

    monkeypatch.setattr("app.agents.support_agent.call_mcp_tool", fake_call_mcp_tool)
    result = SupportAgent().run("Check the payment status for order ORD-2005.")

    assert result["tool_events"][0]["status"] == "failed"
    assert result["tool_results"][0]["result"] == {
        "error": "Tool failed or returned an error."
    }


def test_agent_times_out_slow_mcp_tool_without_leaking_exception(monkeypatch) -> None:
    async def slow_call_mcp_tool(tool_name, arguments=None):
        await asyncio.sleep(1)
        return {"tool": tool_name, "result": {"structured_content": {"status": "ok"}}}

    monkeypatch.setattr("app.agents.support_agent.call_mcp_tool", slow_call_mcp_tool)
    monkeypatch.setattr("app.agents.support_agent.MCP_TOOL_TIMEOUT_SECONDS", 0.01)
    result = SupportAgent().run("Check the payment status for order ORD-2005.")

    assert result["tool_events"][0]["status"] == "failed"
    assert result["tool_events"][0]["error"] == "TimeoutError"
    assert "Tool execution failed." in result["final_answer"]
    assert "could not complete" in result["final_answer"].lower()


def test_agent_routes_product_and_user_lookups_to_mcp(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_call_mcp_tool(tool_name, arguments=None):
        calls.append((tool_name, arguments or {}))
        return {"tool": tool_name, "result": {"status": "ok"}}

    monkeypatch.setattr("app.agents.support_agent.call_mcp_tool", fake_call_mcp_tool)
    agent = SupportAgent()
    product_result = agent.run("Check product stock and price for SKU-1001.")
    user_result = agent.run("Look up user USER-1001 details and role.")

    assert calls == [
        ("get_product_details", {"product_id": "SKU-1001", "tenant_id": "tenant-demo"}),
        ("get_user_details", {"user_id": "USER-1001", "tenant_id": "tenant-demo"}),
    ]
    assert product_result["tool_events"][0]["status"] == "completed"
    assert user_result["tool_events"][0]["status"] == "completed"
