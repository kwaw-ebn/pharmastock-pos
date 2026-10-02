from .clock import today as utc_today
from datetime import date
from typing import Literal
from decimal import Decimal
from pydantic import BaseModel, Field, model_validator

Money = Decimal


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=12, max_length=200)
    role: Literal["admin", "pharmacist", "cashier"]


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    contact: str = Field(default="", max_length=150)
    phone: str = Field(default="", max_length=50)
    email: str = Field(default="", max_length=255)
    address: str = Field(default="", max_length=500)


class ProductIn(BaseModel):
    code: str = Field(min_length=1, max_length=60)
    barcode: str | None = Field(default=None, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    generic_name: str = Field(default="", max_length=200)
    strength: str = Field(default="", max_length=80)
    form: str = Field(default="", max_length=80)
    pack_size: str = Field(default="1 unit", max_length=80)
    category: str = Field(default="Medicines", max_length=100)
    manufacturer: str = Field(default="", max_length=150)
    supplier_id: int | None = None
    selling_price: Money = Field(ge=0, le=1000000, decimal_places=2)
    reorder_level: int = Field(default=20, ge=0)
    prescription_required: bool = False
    storage_notes: str = Field(default="", max_length=500)


class ReceiveItem(BaseModel):
    product_id: int
    batch_number: str = Field(min_length=1, max_length=100)
    quantity: int = Field(gt=0, le=10000000)
    purchase_price: Money = Field(ge=0, le=1000000, decimal_places=2)
    selling_price: Money | None = Field(
        default=None, ge=0, le=1000000, decimal_places=2
    )
    expiry_date: date
    manufacturing_date: date | None = None

    @model_validator(mode="after")
    def dates(self):
        if self.expiry_date <= utc_today():
            raise ValueError("Receive only stock with a future expiry date")
        if self.manufacturing_date and self.manufacturing_date >= self.expiry_date:
            raise ValueError("Manufacturing date must precede expiry")
        return self


class ReceiveIn(BaseModel):
    supplier_id: int
    reference: str = Field(min_length=1, max_length=100)
    notes: str = Field(default="", max_length=1000)
    items: list[ReceiveItem] = Field(min_length=1, max_length=100)


class CartItem(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=1000000)


class SaleIn(BaseModel):
    items: list[CartItem] = Field(min_length=1, max_length=100)
    discount: Money = Field(default=0, ge=0, decimal_places=2)
    payment_method: str = Field(max_length=50)
    amount_paid: Money = Field(ge=0, le=100000000, decimal_places=2)
    customer_id: int | None = None
    prescription_verified: bool = False
    idempotency_key: str = Field(min_length=10, max_length=100)


class AdjustIn(BaseModel):
    batch_id: int
    quantity: int = Field(ge=-10000000, le=10000000)
    reason: str = Field(min_length=5, max_length=1000)


class ReturnIn(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)
    restock: bool = False


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    phone: str = Field(default="", max_length=50)
    email: str = Field(default="", max_length=255)


class SettingsIn(BaseModel):
    pharmacy_name: str = Field(min_length=1, max_length=150)
    address: str = Field(default="", max_length=500)
    phone: str = Field(default="", max_length=50)
    email: str = Field(default="", max_length=255)
    logo_url: str = Field(default="", max_length=1000)
    currency: str = Field(
        default="GHS", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$"
    )
    receipt_footer: str = Field(default="Thank you for choosing us.", max_length=300)
    tax_percent: Money = Field(default=Decimal("0"), ge=0, le=100, decimal_places=2)
    expiry_warning_days: int = Field(default=90, ge=1, le=365)
    default_reorder_level: int = Field(default=20, ge=0)
    payment_methods: list[str] = Field(
        default=["Cash", "Mobile Money", "Card"], min_length=1, max_length=10
    )


class ResetRequest(BaseModel):
    email: str = Field(max_length=255)


class ResetConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=12, max_length=200)


class UserUpdate(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    role: Literal["admin", "pharmacist", "cashier"]
    password: str | None = Field(default=None, min_length=12, max_length=200)
