from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.product import Product
from app.models.tenant import Tenant
from app.models.user import User

DEMO_TENANT_ID = "tenant-demo"


def seed_demo_data(db: Session) -> None:
    tenant = db.query(Tenant).filter(Tenant.id == DEMO_TENANT_ID).first()
    if tenant is None:
        tenant = Tenant(id=DEMO_TENANT_ID, name="Demo Support", slug="demo-support")
        db.add(tenant)
        db.flush()

    customer = (
        db.query(Customer)
        .filter(Customer.tenant_id == DEMO_TENANT_ID, Customer.customer_code == "CUST-1001")
        .first()
    )
    if customer is None:
        customer = Customer(
            id="CUST-1001",
            tenant_id=DEMO_TENANT_ID,
            customer_code="CUST-1001",
            email="ada.customer@example.com",
            full_name="Ada Brooks",
        )
        db.add(customer)
        db.flush()

    if db.query(User).filter(User.id == "USER-1001").first() is None:
        db.add(
            User(
                id="USER-1001",
                tenant_id=DEMO_TENANT_ID,
                email="support@example.com",
                role="support_agent",
                full_name="Support Agent",
            )
        )

    product = db.query(Product).filter(Product.id == "PROD-1001").first()
    if product is None:
        product = Product(
            id="PROD-1001",
            tenant_id=DEMO_TENANT_ID,
            sku="SKU-1001",
            name="Support Plan",
            description="Sample annual support subscription.",
            price=Decimal("249.99"),
            inventory_count=100,
            active=True,
        )
        db.add(product)
        db.flush()

    order = db.query(Order).filter(Order.order_number == "ORD-2005").first()
    if order is None:
        order = Order(
            id="ORD-2005",
            tenant_id=DEMO_TENANT_ID,
            customer_id=customer.id,
            order_number="ORD-2005",
            status="failed",
        )
        db.add(order)
        db.flush()
        db.add(
            OrderItem(
                id="ORDITEM-2005-1",
                order_id=order.id,
                product_id=product.id,
                quantity=1,
                unit_price=product.price,
            )
        )
        db.add(
            Payment(
                id="PAY-2005",
                tenant_id=DEMO_TENANT_ID,
                order_id=order.id,
                amount=product.price,
                status="failed",
                provider="demo",
            )
        )

    db.commit()
