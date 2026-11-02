from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_commerce_demo_records_are_available() -> None:
    client = TestClient(app)
    assert client.get("/api/v1/orders/ORD-2005").status_code == 200
    assert client.get("/api/v1/products/PROD-1001").status_code == 200
    assert client.get("/api/v1/users/USER-1001").status_code == 200


def test_product_user_and_order_crud() -> None:
    client = TestClient(app)
    suffix = uuid4().hex[:10]
    product_id = f"PROD-{suffix}"
    user_id = f"USER-{suffix}"
    order_number = f"ORD-{suffix}"

    product_response = client.post(
        "/api/v1/products",
        json={
            "id": product_id,
            "sku": f"SKU-{suffix}",
            "name": "Test support plan",
            "description": "Product CRUD test",
            "price": "19.99",
            "inventory_count": 8,
        },
    )
    assert product_response.status_code == 201
    assert client.patch(
        f"/api/v1/products/{product_id}",
        json={"inventory_count": 6},
    ).json()["inventory_count"] == 6

    user_response = client.post(
        "/api/v1/users",
        json={
            "id": user_id,
            "email": f"{suffix}@example.test",
            "role": "support_agent",
            "full_name": "Test Agent",
        },
    )
    assert user_response.status_code == 201
    assert client.get(f"/api/v1/users/{user_id}").json()["full_name"] == "Test Agent"

    order_response = client.post(
        "/api/v1/orders",
        json={
            "order_number": order_number,
            "customer_id": "CUST-1001",
            "items": [{"product_id": product_id, "quantity": 2}],
        },
    )
    assert order_response.status_code == 201
    assert order_response.json()["items"][0]["unit_price"] == "19.99"
    assert client.patch(
        f"/api/v1/orders/{order_number}",
        json={"status": "processing"},
    ).json()["status"] == "processing"

    assert client.delete(f"/api/v1/products/{product_id}").status_code == 204
    assert client.get(f"/api/v1/products/{product_id}").status_code == 404
    assert client.delete(f"/api/v1/users/{user_id}").status_code == 204
