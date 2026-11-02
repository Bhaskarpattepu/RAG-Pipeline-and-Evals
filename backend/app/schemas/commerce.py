from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    sku: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    price: Decimal = Field(..., ge=0)
    inventory_count: int = Field(default=0, ge=0)
    active: bool = True


class ProductUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    price: Decimal | None = Field(default=None, ge=0)
    inventory_count: int | None = Field(default=None, ge=0)
    active: bool | None = None


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    sku: str
    name: str
    description: str
    price: Decimal
    inventory_count: int
    active: bool


class UserCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    email: str = Field(..., min_length=3, max_length=255)
    role: str = Field(default="support_agent", min_length=1, max_length=50)
    full_name: str = Field(..., min_length=1, max_length=255)


class UserUpdate(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=255)
    role: str | None = Field(default=None, min_length=1, max_length=50)
    full_name: str | None = Field(default=None, min_length=1, max_length=255)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    email: str
    role: str
    full_name: str


class OrderItemCreate(BaseModel):
    product_id: str = Field(..., min_length=1, max_length=64)
    quantity: int = Field(..., gt=0, le=1000)


class OrderCreate(BaseModel):
    order_number: str = Field(..., min_length=1, max_length=64)
    customer_id: str = Field(..., min_length=1, max_length=64)
    status: str = Field(default="pending", min_length=1, max_length=50)
    items: list[OrderItemCreate] = Field(..., min_length=1)


class OrderUpdate(BaseModel):
    status: str = Field(..., min_length=1, max_length=50)


class OrderItemRead(BaseModel):
    product_id: str
    sku: str
    product_name: str
    quantity: int
    unit_price: Decimal


class OrderRead(BaseModel):
    id: str
    tenant_id: str
    customer_id: str
    order_number: str
    status: str
    items: list[OrderItemRead] = Field(default_factory=list)
