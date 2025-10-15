"""Data models for skroutz.gr entities."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class Product(BaseModel):
    """Represents a product from skroutz.gr."""

    id: str = Field(description="Product ID or SKU ID")
    sku_id: Optional[str] = Field(None, description="SKU ID (product catalog ID)")
    product_id: Optional[str] = Field(None, description="Specific product/offer ID")
    shop_id: Optional[int] = Field(None, description="Shop/merchant ID")
    name: str = Field(description="Product name")
    maker: Optional[str] = Field(None, description="Product maker/brand")
    ean: Optional[str] = Field(None, description="EAN/barcode")
    price: Decimal = Field(description="Product price in EUR")
    original_price: Optional[Decimal] = Field(None, description="Original price if discounted")
    available: bool = Field(default=True, description="Product availability")
    image_url: Optional[str] = Field(None, description="Product image URL")
    description: Optional[str] = Field(None, description="Product description")
    url: Optional[str] = Field(None, description="Product URL")


class CartItem(BaseModel):
    """Represents an item in the shopping cart."""

    product: Product
    quantity: int = Field(gt=0, description="Quantity of the product")
    subtotal: Decimal = Field(description="Subtotal for this cart item")


class Cart(BaseModel):
    """Represents the shopping cart."""

    items: list[CartItem] = Field(default_factory=list, description="Cart items")
    total: Decimal = Field(default=Decimal("0"), description="Total cart value")
    item_count: int = Field(default=0, description="Total number of items")


class OrderItem(BaseModel):
    """Represents an item in an order."""

    product_name: str
    quantity: int
    price: Decimal
    subtotal: Decimal


class Order(BaseModel):
    """Represents an order."""

    id: str = Field(description="Order ID")
    order_number: str = Field(description="Human-readable order number")
    status: str = Field(description="Order status (pending, confirmed, delivered, etc.)")
    created_at: datetime = Field(description="Order creation timestamp")
    total: Decimal = Field(description="Order total value")
    items: list[OrderItem] = Field(default_factory=list, description="Order items")
    delivery_address: Optional[str] = Field(None, description="Delivery address")
    delivery_date: Optional[datetime] = Field(None, description="Scheduled delivery date")


class AuthCredentials(BaseModel):
    """Authentication credentials."""

    email: str
    password: str


class SessionData(BaseModel):
    """Session data for authenticated user."""

    cookies: dict[str, str] = Field(default_factory=dict, description="Session cookies")
    user_id: Optional[str] = Field(None, description="User ID")
    user_email: Optional[str] = Field(None, description="User email")
    is_authenticated: bool = Field(default=False, description="Authentication status")
