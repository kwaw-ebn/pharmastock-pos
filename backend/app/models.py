from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    CheckConstraint,
    JSON,
    UniqueConstraint,
)
from .db import Base


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    token_version = Column(Integer, default=0, nullable=False)
    __table_args__ = (CheckConstraint("role IN ('admin','pharmacist','cashier')"),)


class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    contact = Column(String(150), default="")
    phone = Column(String(50), default="")
    email = Column(String(255), default="")
    address = Column(String(500), default="")


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    code = Column(String(60), unique=True, nullable=False)
    barcode = Column(String(100), unique=True, nullable=True)
    name = Column(String(200), nullable=False, index=True)
    generic_name = Column(String(200), default="")
    strength = Column(String(80), default="")
    form = Column(String(80), default="")
    pack_size = Column(String(80), default="1 unit")
    category = Column(String(100), default="Medicines", index=True)
    manufacturer = Column(String(150), default="")
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    selling_price = Column(Integer, nullable=False)  # minor currency units
    reorder_level = Column(Integer, default=20, nullable=False)
    prescription_required = Column(Boolean, default=False, nullable=False)
    storage_notes = Column(String(500), default="")
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=now, onupdate=now, nullable=False
    )
    __table_args__ = (
        CheckConstraint("selling_price >= 0"),
        CheckConstraint("reorder_level >= 0"),
    )


class Batch(Base):
    __tablename__ = "stock_batches"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    number = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False)
    purchase_price = Column(Integer, nullable=False)
    expiry_date = Column(Date, nullable=False, index=True)
    manufacturing_date = Column(Date, nullable=True)
    received_at = Column(DateTime(timezone=True), default=now, nullable=False)
    __table_args__ = (
        UniqueConstraint("product_id", "number"),
        CheckConstraint("quantity >= 0"),
        CheckConstraint("purchase_price >= 0"),
    )


class StockReceipt(Base):
    __tablename__ = "stock_receipts"
    id = Column(Integer, primary_key=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    reference = Column(String(100), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    notes = Column(String(1000), default="")
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)
    __table_args__ = (UniqueConstraint("supplier_id", "reference"),)


class StockReceiptItem(Base):
    __tablename__ = "stock_receipt_items"
    id = Column(Integer, primary_key=True)
    receipt_id = Column(Integer, ForeignKey("stock_receipts.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("stock_batches.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    purchase_price = Column(Integer, nullable=False)


class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    phone = Column(String(50), default="")
    email = Column(String(255), default="")


class Sale(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True)
    receipt_number = Column(String(100), nullable=False, unique=True, index=True)
    idempotency_key = Column(String(100), nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    subtotal = Column(Integer, nullable=False)
    discount = Column(Integer, nullable=False)
    tax = Column(Integer, nullable=False)
    total = Column(Integer, nullable=False)
    payment_method = Column(String(50), nullable=False)
    amount_paid = Column(Integer, nullable=False)
    change = Column(Integer, nullable=False)
    status = Column(String(30), default="completed", nullable=False)
    pharmacy_snapshot = Column(JSON, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=now, nullable=False, index=True
    )


class SaleItem(Base):
    __tablename__ = "sale_items"
    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("stock_batches.id"), nullable=False)
    product_name = Column(String(250), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Integer, nullable=False)
    unit_cost = Column(Integer, nullable=False)
    __table_args__ = (CheckConstraint("quantity > 0"),)


class Return(Base):
    __tablename__ = "returns"
    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(String(1000), nullable=False)
    restock = Column(Boolean, nullable=False)
    refund_amount = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)


class Movement(Base):
    __tablename__ = "inventory_movements"
    id = Column(Integer, primary_key=True)
    batch_id = Column(
        Integer, ForeignKey("stock_batches.id"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    kind = Column(String(30), nullable=False)
    reference = Column(String(120), nullable=False)
    reason = Column(String(1000), default="")
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)


class Audit(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    record = Column(String(150), nullable=False)
    detail = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)


class Setting(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, default=1)
    values = Column(JSON, nullable=False)


class PasswordReset(Base):
    __tablename__ = "password_resets"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False, nullable=False)


class PaymentIntent(Base):
    __tablename__ = "payment_intents"
    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), unique=True, nullable=False)
    reference = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), nullable=False)
    authorization_url = Column(String(1000), default="")
    external_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now, nullable=False)
