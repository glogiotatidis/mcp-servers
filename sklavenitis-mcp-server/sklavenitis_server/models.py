"""Data models."""

from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class Product(BaseModel):
    """Product model."""
    id: str
    name: str
    price: Decimal = Decimal("0")
    description: Optional[str] = None


class CartItem(BaseModel):
    """Cart item model."""
    sku: str
    name: str
    quantity: str
    price: str


class Cart(BaseModel):
    """Cart model."""
    items: dict[str, CartItem] = {}
    summary_text: str = "0"
    grand_total: str = "€0"
    slot_info: Optional[str] = None

