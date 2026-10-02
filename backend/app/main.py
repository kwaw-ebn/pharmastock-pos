from .clock import today as utc_today
import csv, io, logging, secrets, hashlib, os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import (
    User,
    Supplier,
    Product,
    Batch,
    StockReceipt,
    StockReceiptItem,
    Customer,
    Sale,
    SaleItem,
    Return,
    Movement,
    Audit,
    Setting,
    PasswordReset,
    now,
)
from .schemas import (
    LoginIn,
    UserIn,
    SupplierIn,
    ProductIn,
    ReceiveIn,
    SaleIn,
    AdjustIn,
    ReturnIn,
    CustomerIn,
    SettingsIn,
    ResetRequest,
    ResetConfirm,
    UserUpdate,
)
from .security import (
    password_hash,
    token_for,
    current_user,
    roles,
    rate_limit,
    send_reset,
)

app = FastAPI(title="PharmaStock POS API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(IntegrityError)
async def integrity_error(request, error):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=409,
        content={
            "detail": "A record with these unique details already exists, or a referenced record is invalid."
        },
    )


def cents(value):
    return int(
        (Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def money(value):
    return round(value / 100, 2)


def obj(row, exclude=()):
    return {
        c.name: getattr(row, c.name)
        for c in row.__table__.columns
        if c.name not in exclude
    }


def audit(db, user, action, record, detail=None):
    db.add(
        Audit(
            user_id=user.id if user else None,
            action=action,
            record=str(record),
            detail=detail or {},
        )
    )


def required(db, cls, identifier):
    row = db.get(cls, identifier)
    if not row:
        raise HTTPException(404, "Record not found")
    return row


def settings(db):
    row = db.get(Setting, 1)
    return (
        row.values
        if row
        else SettingsIn(pharmacy_name="PharmaStock Pharmacy").model_dump(mode="json")
    )


def product_json(db, product):
    batches = db.scalars(select(Batch).where(Batch.product_id == product.id)).all()
    result = obj(product)
    result["selling_price"] = money(product.selling_price)
    result["quantity"] = sum(b.quantity for b in batches if b.expiry_date > utc_today())
    result["expired_quantity"] = sum(
        b.quantity for b in batches if b.expiry_date <= utc_today()
    )
    result["next_expiry"] = min(
        (
            b.expiry_date
            for b in batches
            if b.quantity > 0 and b.expiry_date > utc_today()
        ),
        default=None,
    )
    return result


def lock_products(db, ids):
    # Serialize every stock write on the product rows, always in ascending order.
    # For SQLite acquire the write reservation before reading any stock values.
    if db.bind.dialect.name == "sqlite":
        db.rollback()
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    return db.scalars(
        select(Product)
        .where(Product.id.in_(sorted(set(ids))))
        .order_by(Product.id)
        .with_for_update()
    ).all()


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    rate_limit(request, "login")
    user = db.scalar(
        select(User).where(
            or_(User.username == data.username, User.email == data.username)
        )
    )
    valid = False
    if user:
        try:
            valid = password_hash.verify(data.password, user.password_hash)
        except Exception:
            valid = False
    else:
        # A real hash verification keeps missing-account timing similar.
        password_hash.verify(data.password, DUMMY_HASH)
    if not user or not user.active or not valid:
        audit(db, None, "login_failed", "authentication")
        db.commit()
        raise HTTPException(401, "Incorrect username or password")
    audit(db, user, "login", user.id)
    db.commit()
    return {
        "access_token": token_for(user),
        "token_type": "bearer",
        "user": obj(user, ("password_hash", "token_version")),
    }


DUMMY_HASH = password_hash.hash(secrets.token_urlsafe(32))


@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return obj(user, ("password_hash", "token_version"))


@app.post("/api/auth/logout")
def logout(user=Depends(current_user), db: Session = Depends(get_db)):
    user.token_version += 1
    audit(db, user, "logout", user.id)
    db.commit()
    return {"message": "Signed out"}


@app.post("/api/auth/reset-request")
def reset_request(data: ResetRequest, request: Request, db: Session = Depends(get_db)):
    rate_limit(request, "reset", 5)
    user = db.scalar(select(User).where(User.email == data.email, User.active == True))
    if user and os.getenv("SMTP_HOST"):
        token = secrets.token_urlsafe(36)
        db.add(
            PasswordReset(
                user_id=user.id,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=now() + timedelta(minutes=30),
            )
        )
        db.commit()
        try:
            send_reset(user.email, token)
        except Exception:
            logging.exception("Password reset email delivery failed")
    return {
        "message": "If the account exists and email delivery is configured, a reset token will be sent. Otherwise contact your administrator."
    }


@app.post("/api/auth/reset-confirm")
def reset_confirm(data: ResetConfirm, request: Request, db: Session = Depends(get_db)):
    rate_limit(request, "reset-confirm", 5)
    reset = db.scalar(
        select(PasswordReset)
        .where(
            PasswordReset.token_hash == hashlib.sha256(data.token.encode()).hexdigest()
        )
        .with_for_update()
    )
    if not reset or reset.used or reset.expires_at.replace(tzinfo=timezone.utc) < now():
        raise HTTPException(400, "Invalid or expired reset token")
    user = required(db, User, reset.user_id)
    user.password_hash = password_hash.hash(data.password)
    user.token_version += 1
    reset.used = True
    audit(db, user, "password_reset", user.id)
    db.commit()
    return {"message": "Password updated. Please sign in."}


@app.get("/api/users")
def users(user=Depends(roles("admin")), db: Session = Depends(get_db)):
    return [
        obj(u, ("password_hash", "token_version"))
        for u in db.scalars(select(User).order_by(User.id))
    ]


@app.post("/api/users", status_code=201)
def create_user(
    data: UserIn, user=Depends(roles("admin")), db: Session = Depends(get_db)
):
    record = User(
        **data.model_dump(exclude={"password"}),
        password_hash=password_hash.hash(data.password),
    )
    db.add(record)
    db.flush()
    audit(db, user, "user_created", record.id, {"role": record.role})
    db.commit()
    return obj(record, ("password_hash", "token_version"))


@app.patch("/api/users/{identifier}/active")
def toggle_user(
    identifier: int, user=Depends(roles("admin")), db: Session = Depends(get_db)
):
    if identifier == user.id:
        raise HTTPException(400, "You cannot disable your own account")
    record = required(db, User, identifier)
    record.active = not record.active
    record.token_version += 1
    audit(db, user, "user_status_changed", identifier, {"active": record.active})
    db.commit()
    return {"active": record.active}


@app.get("/api/products")
def products(
    q: str = Query(default="", max_length=200),
    category: str = "",
    status: str = "",
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(current_user),
    db: Session = Depends(get_db),
):
    query = select(Product).where(Product.active == True)
    if q:
        term = "%" + q.replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(
            or_(
                *[
                    field.ilike(term, escape="\\")
                    for field in [
                        Product.name,
                        Product.generic_name,
                        Product.code,
                        Product.barcode,
                        Product.category,
                    ]
                ]
            )
        )
    if category:
        query = query.where(Product.category == category)
    if status:
        qty = (
            select(func.coalesce(func.sum(Batch.quantity), 0))
            .where(Batch.product_id == Product.id, Batch.expiry_date > utc_today())
            .scalar_subquery()
        )
        if status == "low":
            query = query.where(qty > 0, qty <= Product.reorder_level)
        elif status == "out":
            query = query.where(qty == 0)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(Product.name).offset((page - 1) * limit).limit(limit)
    ).all()
    return {"items": [product_json(db, p) for p in rows], "total": total, "page": page}


@app.post("/api/products", status_code=201)
def create_product(
    data: ProductIn, user=Depends(roles("admin")), db: Session = Depends(get_db)
):
    values = data.model_dump()
    values["selling_price"] = cents(data.selling_price)
    values["barcode"] = values["barcode"] or None
    if values["supplier_id"]:
        required(db, Supplier, values["supplier_id"])
    record = Product(**values)
    db.add(record)
    db.flush()
    audit(db, user, "product_created", record.id)
    db.commit()
    return product_json(db, record)


@app.put("/api/products/{identifier}")
def update_product(
    identifier: int,
    data: ProductIn,
    user=Depends(roles("admin")),
    db: Session = Depends(get_db),
):
    lock_products(db, [identifier])
    record = required(db, Product, identifier)
    before = obj(record, ("created_at", "updated_at"))
    values = data.model_dump()
    values["selling_price"] = cents(data.selling_price)
    values["barcode"] = values["barcode"] or None
    if values["supplier_id"]:
        required(db, Supplier, values["supplier_id"])
    for key, value in values.items():
        setattr(record, key, value)
    audit(db, user, "product_updated", identifier, {"before": before, "after": values})
    db.commit()
    return product_json(db, record)


@app.get("/api/batches")
def batches(
    product_id: int | None = None,
    expiry: str = "",
    user=Depends(roles("admin", "pharmacist")),
    db: Session = Depends(get_db),
):
    query = select(Batch, Product.name).join(Product, Batch.product_id == Product.id)
    if product_id:
        query = query.where(Batch.product_id == product_id)
    if expiry == "expired":
        query = query.where(Batch.expiry_date <= utc_today(), Batch.quantity > 0)
    elif expiry in ("30", "60", "90"):
        query = query.where(
            Batch.expiry_date > utc_today(),
            Batch.expiry_date <= utc_today() + timedelta(days=int(expiry)),
            Batch.quantity > 0,
        )
    return [
        {
            **obj(b),
            "product_name": name,
            "purchase_price": money(b.purchase_price),
            "expired": b.expiry_date <= utc_today(),
        }
        for b, name in db.execute(query.order_by(Batch.expiry_date).limit(2000))
    ]


@app.get("/api/suppliers")
def suppliers(
    user=Depends(roles("admin", "pharmacist")), db: Session = Depends(get_db)
):
    result = []
    for supplier in db.scalars(select(Supplier).order_by(Supplier.name)):
        receipts = db.scalars(
            select(StockReceipt).where(StockReceipt.supplier_id == supplier.id)
        ).all()
        receipt_ids = [r.id for r in receipts]
        value = db.scalar(
            select(
                func.coalesce(
                    func.sum(
                        StockReceiptItem.quantity * StockReceiptItem.purchase_price
                    ),
                    0,
                )
            ).where(StockReceiptItem.receipt_id.in_(receipt_ids))
        )
        result.append(
            {
                **obj(supplier),
                "purchased_value": money(value),
                "deliveries": len(receipts),
                "last_delivery": max((r.created_at for r in receipts), default=None),
            }
        )
    return result


@app.post("/api/suppliers", status_code=201)
def create_supplier(
    data: SupplierIn, user=Depends(roles("admin")), db: Session = Depends(get_db)
):
    record = Supplier(**data.model_dump())
    db.add(record)
    db.flush()
    audit(db, user, "supplier_created", record.id)
    db.commit()
    return obj(record)


@app.post("/api/stock/receive", status_code=201)
def receive(
    data: ReceiveIn,
    user=Depends(roles("admin", "pharmacist")),
    db: Session = Depends(get_db),
):
    products = lock_products(db, [i.product_id for i in data.items])
    product_map = {p.id: p for p in products}
    required(db, Supplier, data.supplier_id)
    record = StockReceipt(
        supplier_id=data.supplier_id,
        reference=data.reference,
        user_id=user.id,
        notes=data.notes,
    )
    db.add(record)
    db.flush()
    for item in data.items:
        if item.product_id not in product_map:
            raise HTTPException(404, "Product not found")
        batch = db.scalar(
            select(Batch)
            .where(
                Batch.product_id == item.product_id, Batch.number == item.batch_number
            )
            .with_for_update()
        )
        if batch:
            if batch.expiry_date != item.expiry_date or batch.purchase_price != cents(
                item.purchase_price
            ):
                raise HTTPException(
                    409,
                    "Existing batch has different expiry or purchase cost. Use a separate batch reference.",
                )
            batch.quantity += item.quantity
        else:
            batch = Batch(
                product_id=item.product_id,
                number=item.batch_number,
                quantity=item.quantity,
                purchase_price=cents(item.purchase_price),
                expiry_date=item.expiry_date,
                manufacturing_date=item.manufacturing_date,
            )
            db.add(batch)
            db.flush()
        if item.selling_price is not None:
            product = product_map[item.product_id]
            audit(
                db,
                user,
                "price_changed",
                product.id,
                {"before": product.selling_price, "after": cents(item.selling_price)},
            )
            product.selling_price = cents(item.selling_price)
        db.add(
            StockReceiptItem(
                receipt_id=record.id,
                batch_id=batch.id,
                quantity=item.quantity,
                purchase_price=cents(item.purchase_price),
            )
        )
        db.add(
            Movement(
                batch_id=batch.id,
                user_id=user.id,
                quantity=item.quantity,
                kind="received",
                reference=f"STOCK-{record.id}",
                reason=data.notes,
            )
        )
    audit(db, user, "stock_received", record.id, {"reference": record.reference})
    db.commit()
    return {"id": record.id, "message": "Stock received successfully"}


@app.get("/api/stock/receipts")
def stock_receipts(
    user=Depends(roles("admin", "pharmacist")), db: Session = Depends(get_db)
):
    return [
        {**obj(r), "supplier_name": s}
        for r, s in db.execute(
            select(StockReceipt, Supplier.name)
            .join(Supplier)
            .order_by(StockReceipt.id.desc())
            .limit(500)
        )
    ]


@app.post("/api/stock/adjust")
def adjust(data: AdjustIn, user=Depends(roles("admin")), db: Session = Depends(get_db)):
    batch = required(db, Batch, data.batch_id)
    product_id = batch.product_id
    lock_products(db, [product_id])
    batch = db.scalar(select(Batch).where(Batch.id == data.batch_id).with_for_update())
    if data.quantity == 0 or batch.quantity + data.quantity < 0:
        raise HTTPException(
            400, "Adjustment must be nonzero and cannot make stock negative"
        )
    before = batch.quantity
    batch.quantity += data.quantity
    db.add(
        Movement(
            batch_id=batch.id,
            user_id=user.id,
            quantity=data.quantity,
            kind="adjustment",
            reference=f"ADJ-{uuid4().hex[:12]}",
            reason=data.reason,
        )
    )
    audit(
        db,
        user,
        "stock_adjusted",
        batch.id,
        {"before": before, "after": batch.quantity, "reason": data.reason},
    )
    db.commit()
    return {"quantity": batch.quantity}


@app.get("/api/stock/movements")
def movements(
    user=Depends(roles("admin", "pharmacist")), db: Session = Depends(get_db)
):
    return [
        {**obj(m), "product_name": name, "batch_number": batch}
        for m, name, batch in db.execute(
            select(Movement, Product.name, Batch.number)
            .join(Batch, Movement.batch_id == Batch.id)
            .join(Product, Batch.product_id == Product.id)
            .order_by(Movement.id.desc())
            .limit(1000)
        )
    ]


@app.get("/api/customers")
def customers(
    q: str = "",
    user=Depends(roles("admin", "pharmacist")),
    db: Session = Depends(get_db),
):
    query = select(Customer)
    if q:
        query = query.where(Customer.name.ilike("%" + q + "%"))
    return [obj(c) for c in db.scalars(query.order_by(Customer.name).limit(500))]


@app.post("/api/customers", status_code=201)
def create_customer(
    data: CustomerIn,
    user=Depends(roles("admin", "pharmacist")),
    db: Session = Depends(get_db),
):
    record = Customer(**data.model_dump())
    db.add(record)
    db.flush()
    audit(db, user, "customer_created", record.id)
    db.commit()
    return obj(record)


@app.get("/api/customers/{identifier}/sales")
def customer_history(
    identifier: int,
    user=Depends(roles("admin", "pharmacist")),
    db: Session = Depends(get_db),
):
    required(db, Customer, identifier)
    return [
        sale_json(db, s, False)
        for s in db.scalars(
            select(Sale)
            .where(Sale.customer_id == identifier)
            .order_by(Sale.id.desc())
            .limit(500)
        )
    ]


def sale_json(db, sale, detailed=True):
    result = obj(sale, ("idempotency_key",))
    for field in ("subtotal", "discount", "tax", "total", "amount_paid", "change"):
        result[field] = money(result[field])
    result["cashier"] = required(db, User, sale.user_id).username
    if detailed:
        result["items"] = [
            {
                **obj(i, ("unit_cost",)),
                "unit_price": money(i.unit_price),
                "total": money(i.unit_price * i.quantity),
            }
            for i in db.scalars(select(SaleItem).where(SaleItem.sale_id == sale.id))
        ]
        result["return"] = (
            obj(db.scalar(select(Return).where(Return.sale_id == sale.id)))
            if sale.status == "refunded"
            else None
        )
    return result


@app.post("/api/sales", status_code=201)
def create_sale(
    data: SaleIn, user=Depends(current_user), db: Session = Depends(get_db)
):
    lock_products(db, [i.product_id for i in data.items])
    existing = db.scalar(
        select(Sale).where(Sale.idempotency_key == data.idempotency_key)
    )
    if existing:
        if existing.user_id != user.id:
            raise HTTPException(409, "Checkout reference already used")
        return sale_json(db, existing)
    config = settings(db)
    if data.payment_method not in config["payment_methods"]:
        raise HTTPException(400, "Unsupported payment method")
    if data.customer_id:
        if user.role == "cashier":
            raise HTTPException(403, "Customer records require pharmacist access")
        required(db, Customer, data.customer_id)
    quantities = {}
    for item in data.items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
    allocation = []
    subtotal = 0
    for identifier, quantity in sorted(quantities.items()):
        product = required(db, Product, identifier)
        if not product.active:
            raise HTTPException(400, "Product is inactive")
        if product.prescription_required and (
            user.role == "cashier" or not data.prescription_verified
        ):
            raise HTTPException(
                403, "A pharmacist must verify the prescription before sale"
            )
        batches = db.scalars(
            select(Batch)
            .where(
                Batch.product_id == identifier,
                Batch.quantity > 0,
                Batch.expiry_date > utc_today(),
            )
            .order_by(Batch.expiry_date, Batch.id)
            .with_for_update()
        ).all()
        if sum(b.quantity for b in batches) < quantity:
            raise HTTPException(409, f"Insufficient sellable stock for {product.name}")
        subtotal += quantity * product.selling_price
        remaining = quantity
        for batch in batches:
            taken = min(remaining, batch.quantity)
            if taken:
                allocation.append((product, batch, taken))
                remaining -= taken
            if remaining == 0:
                break
    discount = cents(data.discount)
    if discount > subtotal:
        raise HTTPException(400, "Discount cannot exceed subtotal")
    if discount and user.role == "cashier":
        raise HTTPException(
            403, "Discounts require pharmacist or administrator approval"
        )
    tax = int(
        (
            Decimal(subtotal - discount) * Decimal(str(config["tax_percent"])) / 100
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    total = subtotal - discount + tax
    paid = cents(data.amount_paid)
    if paid < total:
        raise HTTPException(400, "Amount paid is below the total")
    if data.payment_method != "Cash" and paid != total:
        raise HTTPException(400, "Non-cash payment must match the total exactly")
    sale = Sale(
        receipt_number=f"PS-{utc_today():%Y%m%d}-{uuid4().hex[:12].upper()}",
        idempotency_key=data.idempotency_key,
        user_id=user.id,
        customer_id=data.customer_id,
        subtotal=subtotal,
        discount=discount,
        tax=tax,
        total=total,
        payment_method=data.payment_method,
        amount_paid=paid,
        change=paid - total,
        pharmacy_snapshot=config,
    )
    db.add(sale)
    db.flush()
    for product, batch, quantity in allocation:
        batch.quantity -= quantity
        db.add(
            SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                batch_id=batch.id,
                product_name=f"{product.name} {product.strength}".strip(),
                quantity=quantity,
                unit_price=product.selling_price,
                unit_cost=batch.purchase_price,
            )
        )
        db.add(
            Movement(
                batch_id=batch.id,
                user_id=user.id,
                quantity=-quantity,
                kind="sale",
                reference=sale.receipt_number,
            )
        )
    audit(
        db,
        user,
        "sale_completed",
        sale.id,
        {
            "receipt": sale.receipt_number,
            "prescription_verified": data.prescription_verified,
        },
    )
    db.commit()
    return sale_json(db, sale)


@app.get("/api/sales")
def sales(
    start: date | None = None,
    end: date | None = None,
    q: str = "",
    payment_method: str = "",
    user_id: int | None = None,
    product_id: int | None = None,
    page: int = Query(1, ge=1),
    user=Depends(current_user),
    db: Session = Depends(get_db),
):
    query = select(Sale)
    if user.role == "cashier":
        query = query.where(Sale.user_id == user.id)
    elif user_id:
        query = query.where(Sale.user_id == user_id)
    if product_id:
        query = query.where(
            Sale.id.in_(
                select(SaleItem.sale_id).where(SaleItem.product_id == product_id)
            )
        )
    if start:
        query = query.where(
            Sale.created_at
            >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
        )
    if end:
        query = query.where(
            Sale.created_at
            < datetime.combine(
                end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
            )
        )
    if q:
        query = query.where(Sale.receipt_number.ilike("%" + q + "%"))
    if payment_method:
        query = query.where(Sale.payment_method == payment_method)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    return {
        "items": [
            sale_json(db, s, False)
            for s in db.scalars(
                query.order_by(Sale.id.desc()).offset((page - 1) * 50).limit(50)
            )
        ],
        "total": total,
    }


@app.get("/api/sales/{identifier}")
def get_sale(
    identifier: int, user=Depends(current_user), db: Session = Depends(get_db)
):
    sale = required(db, Sale, identifier)
    if user.role == "cashier" and sale.user_id != user.id:
        raise HTTPException(403, "You can only view your own sales")
    return sale_json(db, sale)


@app.post("/api/sales/{identifier}/refund")
def refund(
    identifier: int,
    data: ReturnIn,
    user=Depends(roles("admin")),
    db: Session = Depends(get_db),
):
    sale = required(db, Sale, identifier)
    items = db.scalars(select(SaleItem).where(SaleItem.sale_id == identifier)).all()
    lock_products(db, [i.product_id for i in items])
    sale = db.scalar(select(Sale).where(Sale.id == identifier).with_for_update())
    db.refresh(sale)
    if sale.status != "completed":
        raise HTTPException(409, "This sale has already been refunded")
    if data.restock:
        for item in items:
            batch = db.scalar(
                select(Batch).where(Batch.id == item.batch_id).with_for_update()
            )
            if batch.expiry_date <= utc_today():
                raise HTTPException(
                    400, "Expired stock cannot be returned to sellable inventory"
                )
            batch.quantity += item.quantity
            db.add(
                Movement(
                    batch_id=batch.id,
                    user_id=user.id,
                    quantity=item.quantity,
                    kind="return",
                    reference=sale.receipt_number,
                    reason=data.reason,
                )
            )
    sale.status = "refunded"
    db.add(
        Return(
            sale_id=sale.id,
            user_id=user.id,
            reason=data.reason,
            restock=data.restock,
            refund_amount=sale.total,
        )
    )
    audit(
        db,
        user,
        "sale_refunded",
        sale.id,
        {"reason": data.reason, "restock": data.restock},
    )
    db.commit()
    return sale_json(db, sale)


@app.get("/api/settings")
def get_settings(user=Depends(current_user), db: Session = Depends(get_db)):
    return settings(db)


@app.put("/api/settings")
def put_settings(
    data: SettingsIn, user=Depends(roles("admin")), db: Session = Depends(get_db)
):
    before = settings(db)
    values = data.model_dump(mode="json")
    if data.logo_url and not data.logo_url.startswith("https://"):
        raise HTTPException(400, "Logo URL must use HTTPS")
    record = db.get(Setting, 1)
    if record:
        record.values = values
    else:
        db.add(Setting(id=1, values=values))
    audit(db, user, "settings_updated", 1, {"before": before, "after": values})
    db.commit()
    return values


@app.get("/api/audit")
def audit_logs(user=Depends(roles("admin")), db: Session = Depends(get_db)):
    return [
        {**obj(a), "username": name or "Unknown"}
        for a, name in db.execute(
            select(Audit, User.username)
            .outerjoin(User, Audit.user_id == User.id)
            .order_by(Audit.id.desc())
            .limit(1000)
        )
    ]


@app.get("/api/dashboard")
def dashboard(user=Depends(current_user), db: Session = Depends(get_db)):
    inventory = [
        product_json(db, p)
        for p in db.scalars(select(Product).where(Product.active == True))
    ]
    today = datetime.combine(utc_today(), datetime.min.time(), tzinfo=timezone.utc)
    query = select(Sale).where(Sale.created_at >= today - timedelta(days=30))
    if user.role == "cashier":
        query = query.where(Sale.user_id == user.id)
    rows = db.scalars(query).all()
    completed = [s for s in rows if s.status == "completed"]
    daily = {}
    category = {}
    best = {}
    for sale in completed:
        day = sale.created_at.date().isoformat()
        daily[day] = daily.get(day, 0) + sale.total
        for item in db.scalars(select(SaleItem).where(SaleItem.sale_id == sale.id)):
            product = db.get(Product, item.product_id)
            category[product.category] = (
                category.get(product.category, 0) + item.unit_price * item.quantity
            )
            best[item.product_name] = best.get(item.product_name, 0) + item.quantity
    warning = int(settings(db)["expiry_warning_days"])
    return {
        "today_sales": money(
            sum(s.total for s in completed if s.created_at.date() == utc_today())
        ),
        "today_transactions": sum(
            1 for s in completed if s.created_at.date() == utc_today()
        ),
        "total_products": len(inventory),
        "in_stock": sum(p["quantity"] > 0 for p in inventory),
        "low_stock": sum(0 < p["quantity"] <= p["reorder_level"] for p in inventory),
        "out_of_stock": sum(p["quantity"] == 0 for p in inventory),
        "expiring": sum(
            bool(
                p["next_expiry"]
                and p["next_expiry"] <= utc_today() + timedelta(days=warning)
            )
            for p in inventory
        ),
        "expired": sum(p["expired_quantity"] > 0 for p in inventory),
        "trend": [
            {
                "date": (utc_today() - timedelta(days=i)).isoformat(),
                "sales": money(
                    daily.get((utc_today() - timedelta(days=i)).isoformat(), 0)
                ),
            }
            for i in range(29, -1, -1)
        ],
        "best_sellers": [
            {"name": name, "quantity": qty}
            for name, qty in sorted(best.items(), key=lambda x: x[1], reverse=True)[:5]
        ],
        "categories": [
            {"name": name, "sales": money(amount)} for name, amount in category.items()
        ],
        "alerts": [
            p
            for p in inventory
            if p["quantity"] <= p["reorder_level"]
            or p["expired_quantity"]
            or (
                p["next_expiry"]
                and p["next_expiry"] <= utc_today() + timedelta(days=warning)
            )
        ][:12],
    }


@app.get("/api/reports")
def reports(
    start: date | None = None,
    end: date | None = None,
    user=Depends(roles("admin")),
    db: Session = Depends(get_db),
):
    query = select(Sale)
    if start:
        query = query.where(
            Sale.created_at
            >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
        )
    if end:
        query = query.where(
            Sale.created_at
            < datetime.combine(
                end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
            )
        )
    all_sales = db.scalars(query).all()
    completed = [s for s in all_sales if s.status == "completed"]
    ids = [s.id for s in completed]
    cost = db.scalar(
        select(
            func.coalesce(func.sum(SaleItem.unit_cost * SaleItem.quantity), 0)
        ).where(SaleItem.sale_id.in_(ids))
    )
    net = sum(s.subtotal - s.discount for s in completed)
    groups = {}
    for sale in completed:
        for dimension, label in [
            ("payment", sale.payment_method),
            ("staff", required(db, User, sale.user_id).username),
            ("day", sale.created_at.date().isoformat()),
            ("month", sale.created_at.strftime("%Y-%m")),
            ("week", sale.created_at.strftime("%G-W%V")),
        ]:
            key = (dimension, label)
            groups[key] = groups.get(key, 0) + sale.total
    products = {}
    for item in db.scalars(select(SaleItem).where(SaleItem.sale_id.in_(ids))):
        entry = products.setdefault(
            item.product_id, {"name": item.product_name, "quantity": 0, "sales": 0}
        )
        entry["quantity"] += item.quantity
        entry["sales"] += item.unit_price * item.quantity
        product = required(db, Product, item.product_id)
        key = ("category", product.category)
        groups[key] = groups.get(key, 0) + item.unit_price * item.quantity
    valuation = db.scalar(
        select(func.coalesce(func.sum(Batch.quantity * Batch.purchase_price), 0)).where(
            Batch.expiry_date > utc_today()
        )
    )
    return {
        "transactions": len(completed),
        "gross_sales": money(sum(s.total for s in completed)),
        "discounts": money(sum(s.discount for s in completed)),
        "tax": money(sum(s.tax for s in completed)),
        "net_sales": money(net),
        "cost_of_goods": money(cost),
        "gross_profit": money(net - cost),
        "refunds": money(sum(s.total for s in all_sales if s.status == "refunded")),
        "stock_valuation": money(valuation),
        "groups": [
            {"dimension": key[0], "name": key[1], "sales": money(amount)}
            for key, amount in groups.items()
        ],
        "products": [
            {**p, "sales": money(p["sales"])}
            for p in sorted(
                products.values(), key=lambda x: x["quantity"], reverse=True
            )
        ],
        "slow_moving": [
            p.name
            for p in db.scalars(select(Product).where(Product.active == True))
            if p.id not in products
        ],
    }


@app.get("/api/reports/export")
def export(
    kind: str = "sales",
    start: date | None = None,
    end: date | None = None,
    user=Depends(roles("admin")),
    db: Session = Depends(get_db),
):
    if kind == "sales":
        query = select(Sale)
        if start:
            query = query.where(
                Sale.created_at
                >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
            )
        if end:
            query = query.where(
                Sale.created_at
                < datetime.combine(
                    end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
                )
            )
        fields = [
            "receipt_number",
            "created_at",
            "cashier",
            "status",
            "subtotal",
            "discount",
            "tax",
            "total",
            "payment_method",
        ]
        rows = [
            sale_json(db, s, False) for s in db.scalars(query.order_by(Sale.id.desc()))
        ]
    elif kind == "inventory":
        fields = [
            "code",
            "name",
            "category",
            "quantity",
            "expired_quantity",
            "selling_price",
            "reorder_level",
            "next_expiry",
        ]
        rows = [product_json(db, p) for p in db.scalars(select(Product))]
    elif kind == "movements":
        fields = [
            "id",
            "batch_id",
            "quantity",
            "kind",
            "reference",
            "reason",
            "created_at",
        ]
        rows = [obj(m) for m in db.scalars(select(Movement))]
    elif kind == "expiry":
        fields = ["product_id", "number", "quantity", "expiry_date", "purchase_price"]
        rows = [
            {**obj(b), "purchase_price": money(b.purchase_price)}
            for b in db.scalars(
                select(Batch).where(Batch.quantity > 0).order_by(Batch.expiry_date)
            )
        ]
    else:
        raise HTTPException(400, "Unknown report type")
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        clean = {
            k: (
                "'" + v
                if isinstance(v, str)
                and v.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
                else v
            )
            for k, v in row.items()
        }
        writer.writerow(clean)
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="pharmastock-{kind}.csv"'
        },
    )


@app.put("/api/suppliers/{identifier}")
def update_supplier(
    identifier: int,
    data: SupplierIn,
    user=Depends(roles("admin")),
    db: Session = Depends(get_db),
):
    record = required(db, Supplier, identifier)
    before = obj(record)
    for key, value in data.model_dump().items():
        setattr(record, key, value)
    audit(
        db,
        user,
        "supplier_updated",
        identifier,
        {"before": before, "after": data.model_dump()},
    )
    db.commit()
    return obj(record)


@app.put("/api/customers/{identifier}")
def update_customer(
    identifier: int,
    data: CustomerIn,
    user=Depends(roles("admin", "pharmacist")),
    db: Session = Depends(get_db),
):
    record = required(db, Customer, identifier)
    for key, value in data.model_dump().items():
        setattr(record, key, value)
    audit(db, user, "customer_updated", identifier)
    db.commit()
    return obj(record)


@app.put("/api/users/{identifier}")
def update_user(
    identifier: int,
    data: UserUpdate,
    user=Depends(roles("admin")),
    db: Session = Depends(get_db),
):
    record = required(db, User, identifier)
    if identifier == user.id and data.role != "admin":
        raise HTTPException(400, "You cannot remove your own administrator role")
    before = {"email": record.email, "role": record.role}
    record.email = data.email
    record.role = data.role
    record.token_version += 1
    if data.password:
        record.password_hash = password_hash.hash(data.password)
    audit(
        db,
        user,
        "user_permissions_updated",
        identifier,
        {
            "before": before,
            "after": {"email": record.email, "role": record.role},
            "password_reset": bool(data.password),
        },
    )
    db.commit()
    return obj(record, ("password_hash", "token_version"))
