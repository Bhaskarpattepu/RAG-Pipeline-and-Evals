from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.product import Product
from app.models.user import User


class CommerceService:
    @staticmethod
    def get_customer(db: Session, customer_id: str, tenant_id: str) -> dict[str, Any] | None:
        customer = (
            db.query(Customer)
            .filter(
                Customer.tenant_id == tenant_id,
                (Customer.id == customer_id) | (Customer.customer_code == customer_id),
            )
            .first()
        )
        if customer is None:
            return None
        return {
            "customer_id": customer.customer_code,
            "name": customer.full_name,
            "status": "active",
        }

    @staticmethod
    def get_user(db: Session, user_id: str, tenant_id: str) -> dict[str, Any] | None:
        user = db.query(User).filter(User.id == user_id, User.tenant_id == tenant_id).first()
        if user is None:
            return None
        return {"user_id": user.id, "name": user.full_name, "role": user.role}

    @staticmethod
    def get_order(db: Session, order_number: str, tenant_id: str) -> dict[str, Any] | None:
        order = (
            db.query(Order)
            .filter(Order.order_number == order_number, Order.tenant_id == tenant_id)
            .first()
        )
        if order is None:
            return None
        items = (
            db.query(OrderItem, Product)
            .join(Product, Product.id == OrderItem.product_id)
            .filter(OrderItem.order_id == order.id)
            .all()
        )
        payments = db.query(Payment).filter(
            Payment.order_id == order.id,
            Payment.tenant_id == tenant_id,
        ).all()
        return {
            "order_id": order.order_number,
            "customer_id": order.customer_id,
            "status": order.status,
            "items": [
                {
                    "product_id": product.id,
                    "sku": product.sku,
                    "name": product.name,
                    "quantity": item.quantity,
                    "unit_price": float(item.unit_price),
                }
                for item, product in items
            ],
            "payments": [
                {
                    "payment_id": payment.id,
                    "status": payment.status,
                    "amount": float(payment.amount),
                }
                for payment in payments
            ],
        }

    @staticmethod
    def get_payment(db: Session, order_number: str, tenant_id: str) -> dict[str, Any] | None:
        order = (
            db.query(Order)
            .filter(Order.order_number == order_number, Order.tenant_id == tenant_id)
            .first()
        )
        if order is None:
            return None
        payments = db.query(Payment).filter(
            Payment.order_id == order.id,
            Payment.tenant_id == tenant_id,
        ).all()
        return {
            "order_id": order.order_number,
            "payments": [
                {
                    "payment_id": payment.id,
                    "status": payment.status,
                    "amount": float(payment.amount),
                    "provider": payment.provider,
                }
                for payment in payments
            ],
        }

    @staticmethod
    def get_product(db: Session, product_id: str, tenant_id: str) -> dict[str, Any] | None:
        product = (
            db.query(Product)
            .filter(
                Product.tenant_id == tenant_id,
                Product.active.is_(True),
                (Product.id == product_id) | (Product.sku == product_id),
            )
            .first()
        )
        if product is None:
            return None
        return {
            "product_id": product.id,
            "sku": product.sku,
            "name": product.name,
            "description": product.description,
            "price": float(product.price),
            "inventory_count": product.inventory_count,
        }

    @staticmethod
    def search_products(db: Session, query: str, tenant_id: str) -> list[dict[str, Any]]:
        products = (
            db.query(Product)
            .filter(Product.tenant_id == tenant_id, Product.active.is_(True))
            .order_by(Product.name)
            .limit(100)
            .all()
        )
        terms = set(re.findall(r"[a-z0-9]+", query.lower()))
        matches = [
            product
            for product in products
            if not terms
            or any(
                term in set(
                    re.findall(
                        r"[a-z0-9]+",
                        f"{product.name} {product.sku} {product.description}".lower(),
                    )
                )
                or (
                    len(term) > 4
                    and any(
                        token.startswith(term.rstrip("s"))
                        for token in re.findall(
                            r"[a-z0-9]+",
                            f"{product.name} {product.sku} {product.description}".lower(),
                        )
                    )
                )
                for term in terms
            )
        ]
        return [
            {
                "product_id": product.id,
                "sku": product.sku,
                "name": product.name,
                "description": product.description,
                "price": float(product.price),
                "inventory_count": product.inventory_count,
            }
            for product in matches[:10]
        ]
