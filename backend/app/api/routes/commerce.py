from decimal import Decimal
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.user import User
from app.schemas.commerce import (
    OrderCreate,
    OrderItemRead,
    OrderRead,
    OrderUpdate,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    UserCreate,
    UserRead,
    UserUpdate,
)

router = APIRouter(tags=["commerce"])
DEMO_TENANT_ID = "tenant-demo"


def _commit_or_conflict(db: Session, detail: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=detail) from exc


def _get_order_read(db: Session, order: Order) -> OrderRead:
    items = (
        db.query(OrderItem, Product)
        .join(Product, Product.id == OrderItem.product_id)
        .filter(OrderItem.order_id == order.id)
        .all()
    )
    return OrderRead(
        id=order.id,
        tenant_id=order.tenant_id,
        customer_id=order.customer_id,
        order_number=order.order_number,
        status=order.status,
        items=[
            OrderItemRead(
                product_id=product.id,
                sku=product.sku,
                product_name=product.name,
                quantity=item.quantity,
                unit_price=Decimal(item.unit_price),
            )
            for item, product in items
        ],
    )


@router.get("/products", response_model=list[ProductRead])
def list_products(
    db: Annotated[Session, Depends(get_db)],
    tenant_id: Annotated[str, Query()] = DEMO_TENANT_ID,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Product]:
    query = db.query(Product).filter(Product.tenant_id == tenant_id)
    if not include_inactive:
        query = query.filter(Product.active.is_(True))
    return query.order_by(Product.name).limit(limit).all()


@router.get("/products/{product_id}", response_model=ProductRead)
def get_product(
    product_id: str,
    db: Annotated[Session, Depends(get_db)],
    tenant_id: Annotated[str, Query()] = DEMO_TENANT_ID,
    include_inactive: bool = False,
) -> Product:
    query = db.query(Product).filter(Product.id == product_id, Product.tenant_id == tenant_id)
    if not include_inactive:
        query = query.filter(Product.active.is_(True))
    product = query.first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    db: Annotated[Session, Depends(get_db)],
    tenant_id: Annotated[str, Query()] = DEMO_TENANT_ID,
) -> Product:
    product = Product(
        id=payload.id,
        tenant_id=tenant_id,
        sku=payload.sku,
        name=payload.name,
        description=payload.description,
        price=payload.price,
        inventory_count=payload.inventory_count,
        active=payload.active,
    )
    db.add(product)
    _commit_or_conflict(db, "A product with this ID or SKU already exists.")
    db.refresh(product)
    return product


@router.patch("/products/{product_id}", response_model=ProductRead)
def update_product(
    product_id: str,
    payload: ProductUpdate,
    db: Annotated[Session, Depends(get_db)],
    tenant_id: Annotated[str, Query()] = DEMO_TENANT_ID,
) -> Product:
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.tenant_id == tenant_id)
        .first()
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    _commit_or_conflict(db, "A product with this SKU already exists.")
    db.refresh(product)
    return product


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_product(
    product_id: str,
    db: Annotated[Session, Depends(get_db)],
    tenant_id: Annotated[str, Query()] = DEMO_TENANT_ID,
) -> None:
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.tenant_id == tenant_id)
        .first()
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    product.active = False
    db.commit()


@router.get("/users", response_model=list[UserRead])
def list_users(
    db: Annotated[Session, Depends(get_db)],
    tenant_id: Annotated[str, Query()] = DEMO_TENANT_ID,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[User]:
    return (
        db.query(User)
        .filter(User.tenant_id == tenant_id)
        .order_by(User.full_name)
        .limit(limit)
        .all()
    )


@router.get("/users/{user_id}", response_model=UserRead)
def get_user(
    user_id: str,
    db: Annotated[Session, Depends(get_db)],
    tenant_id: Annotated[str, Query()] = DEMO_TENANT_ID,
) -> User:
    user = db.query(User).filter(User.id == user_id, User.tenant_id == tenant_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Annotated[Session, Depends(get_db)],
    tenant_id: Annotated[str, Query()] = DEMO_TENANT_ID,
) -> User:
    user = User(
        id=payload.id,
        tenant_id=tenant_id,
        email=payload.email,
        role=payload.role,
        full_name=payload.full_name,
    )
    db.add(user)
    _commit_or_conflict(db, "A user with this ID or email already exists.")
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: str,
    payload: UserUpdate,
    db: Annotated[Session, Depends(get_db)],
    tenant_id: Annotated[str, Query()] = DEMO_TENANT_ID,
) -> User:
    user = db.query(User).filter(User.id == user_id, User.tenant_id == tenant_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    _commit_or_conflict(db, "A user with this email already exists.")
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str,
    db: Annotated[Session, Depends(get_db)],
    tenant_id: Annotated[str, Query()] = DEMO_TENANT_ID,
) -> None:
    user = db.query(User).filter(User.id == user_id, User.tenant_id == tenant_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()


@router.get("/orders", response_model=list[OrderRead])
def list_orders(
    db: Annotated[Session, Depends(get_db)],
    tenant_id: Annotated[str, Query()] = DEMO_TENANT_ID,
    customer_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[OrderRead]:
    query = db.query(Order).filter(Order.tenant_id == tenant_id)
    if customer_id:
        query = query.filter(Order.customer_id == customer_id)
    return [_get_order_read(db, row) for row in query.order_by(Order.order_number).limit(limit).all()]


@router.get("/orders/{order_number}", response_model=OrderRead)
def get_order(
    order_number: str,
    db: Annotated[Session, Depends(get_db)],
    tenant_id: Annotated[str, Query()] = DEMO_TENANT_ID,
) -> OrderRead:
    order = (
        db.query(Order)
        .filter(Order.order_number == order_number, Order.tenant_id == tenant_id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return _get_order_read(db, order)


@router.post("/orders", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    db: Annotated[Session, Depends(get_db)],
    tenant_id: Annotated[str, Query()] = DEMO_TENANT_ID,
) -> OrderRead:
    customer = (
        db.query(Customer)
        .filter(
            Customer.tenant_id == tenant_id,
            (Customer.id == payload.customer_id) | (Customer.customer_code == payload.customer_id),
        )
        .first()
    )
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    products_by_id: dict[str, Product] = {}
    for requested_item in payload.items:
        product = (
            db.query(Product)
            .filter(
                Product.id == requested_item.product_id,
                Product.tenant_id == tenant_id,
                Product.active.is_(True),
            )
            .first()
        )
        if product is None:
            raise HTTPException(
                status_code=404,
                detail=f"Active product not found: {requested_item.product_id}",
            )
        products_by_id[product.id] = product

    order = Order(
        id=str(uuid4()),
        tenant_id=tenant_id,
        customer_id=customer.id,
        order_number=payload.order_number,
        status=payload.status,
    )
    db.add(order)
    db.flush()
    for requested_item in payload.items:
        product = products_by_id[requested_item.product_id]
        db.add(
            OrderItem(
                id=str(uuid4()),
                order_id=order.id,
                product_id=product.id,
                quantity=requested_item.quantity,
                unit_price=product.price,
            )
        )
    _commit_or_conflict(db, "An order with this order number already exists.")
    db.refresh(order)
    return _get_order_read(db, order)


@router.patch("/orders/{order_number}", response_model=OrderRead)
def update_order_status(
    order_number: str,
    payload: OrderUpdate,
    db: Annotated[Session, Depends(get_db)],
    tenant_id: Annotated[str, Query()] = DEMO_TENANT_ID,
) -> OrderRead:
    order = (
        db.query(Order)
        .filter(Order.order_number == order_number, Order.tenant_id == tenant_id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    order.status = payload.status
    db.commit()
    db.refresh(order)
    return _get_order_read(db, order)
