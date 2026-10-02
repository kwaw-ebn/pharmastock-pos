"""Hosted checkout. Never store card details or trust browser payment success."""

import os, hmac, hashlib, json
from urllib.parse import quote, urlparse
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
import httpx
from pydantic import Field
from starlette.concurrency import run_in_threadpool
from .db import get_db
from .models import PaymentIntent, Sale, SaleItem, Batch, Movement, User
from .schemas import SaleIn
from .security import current_user
from .clock import today

router = APIRouter(prefix="/api/payments", tags=["payments"])


class CheckoutIn(SaleIn):
    email: str = Field(
        min_length=5, max_length=255, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    )


def secret():
    key = os.getenv("PAYSTACK_SECRET_KEY", "")
    if not key.startswith(("sk_test_", "sk_live_")):
        raise HTTPException(
            503,
            "Paystack has not been configured. Add your secret key in the backend environment.",
        )
    return key


def provider(method, path, payload=None):
    try:
        with httpx.Client(timeout=15) as client:
            response = client.request(
                method,
                "https://api.paystack.co" + path,
                headers={"Authorization": "Bearer " + secret()},
                json=payload,
            )
        result = response.json()
        if not response.is_success or not result.get("status"):
            raise HTTPException(
                502,
                "Paystack did not accept this request. Reconcile the pending reference before starting another checkout.",
            )
        return result["data"]
    except (httpx.HTTPError, ValueError):
        raise HTTPException(
            502,
            "Paystack could not be reached. Stock remains reserved; retry verification for this payment.",
        )


@router.get("/config")
def config(user=Depends(current_user)):
    key = os.getenv("PAYSTACK_SECRET_KEY", "")
    return {
        "enabled": key.startswith(("sk_test_", "sk_live_")),
        "mode": "live" if key.startswith("sk_live_") else "test",
    }


@router.post("/initialize")
def initialize(
    data: CheckoutIn, user=Depends(current_user), db: Session = Depends(get_db)
):
    from .main import prepare_sale, settings, required

    secret()
    callback = os.getenv("PAYMENT_CALLBACK_URL", "")
    if not callback.startswith("https://"):
        raise HTTPException(
            503, "The payment callback URL must be configured with HTTPS"
        )
    if (
        data.payment_method not in ("Card", "Mobile Money")
        or settings(db)["currency"] != "GHS"
    ):
        raise HTTPException(
            400, "This gateway configuration supports Card and Mobile Money in GHS"
        )
    result = prepare_sale(data, user, db, pending=True, payment_email=data.email)
    sale = required(db, Sale, result["id"])
    intent = db.scalar(select(PaymentIntent).where(PaymentIntent.sale_id == sale.id))
    if not intent:
        raise HTTPException(
            409, "Checkout reference belongs to a different payment flow"
        )
    if sale.status != "pending":
        return {
            "sale_id": sale.id,
            "reference": intent.reference,
            "status": sale.status,
            "authorization_url": intent.authorization_url,
        }
    if not intent.authorization_url:
        response = provider(
            "POST",
            "/transaction/initialize",
            {
                "email": intent.email,
                "amount": sale.total,
                "currency": "GHS",
                "reference": intent.reference,
                "callback_url": callback,
                "channels": ["card"]
                if sale.payment_method == "Card"
                else ["mobile_money"],
            },
        )
        url = response.get("authorization_url", "")
        if (
            urlparse(url).scheme != "https"
            or urlparse(url).hostname != "checkout.paystack.com"
            or response.get("reference") != intent.reference
        ):
            raise HTTPException(502, "Unexpected payment checkout response")
        intent.authorization_url = url
        db.commit()
    return {
        "sale_id": sale.id,
        "reference": intent.reference,
        "status": sale.status,
        "authorization_url": intent.authorization_url,
    }


def reconcile(db, reference):
    from .main import audit, lock_products, sale_json

    intent = db.scalar(
        select(PaymentIntent).where(PaymentIntent.reference == reference)
    )
    if not intent:
        raise HTTPException(404, "Payment reference not found")
    result = provider("GET", "/transaction/verify/" + quote(reference, safe=""))
    sale = db.get(Sale, intent.sale_id)
    if (
        result.get("reference") != reference
        or result.get("currency") != sale.pharmacy_snapshot["currency"]
        or result.get("amount") != sale.total
    ):
        raise HTTPException(
            409, "Payment amount, currency or reference does not match this sale"
        )
    key = secret()
    expected = "live" if key.startswith("sk_live_") else "test"
    if result.get("domain") != expected:
        raise HTTPException(409, "Payment environment does not match")
    items = db.scalars(select(SaleItem).where(SaleItem.sale_id == sale.id)).all()
    lock_products(db, [i.product_id for i in items])
    sale = db.scalar(select(Sale).where(Sale.id == sale.id).with_for_update())
    db.refresh(sale)
    intent = db.scalar(
        select(PaymentIntent)
        .where(PaymentIntent.reference == reference)
        .with_for_update()
    )
    if result.get("status") == "success" and sale.status in ("pending", "cancelled"):
        # A late success after cancellation or after expiry requires staff review.
        expired = any(db.get(Batch, i.batch_id).expiry_date <= today() for i in items)
        review = sale.status == "cancelled" or expired
        sale.status = "paid_review" if review else "completed"
        sale.amount_paid = sale.total
        intent.external_id = str(result.get("id", ""))
        audit(
            db,
            db.get(User, sale.user_id),
            "gateway_payment_verified",
            sale.id,
            {"reference": reference, "mode": expected, "requires_review": review},
        )
        # Reservation movements already deducted stock; do not deduct it again.
    elif result.get("status") == "failed" and sale.status == "pending":
        for item in items:
            batch = db.get(Batch, item.batch_id)
            batch.quantity += item.quantity
            db.add(
                Movement(
                    batch_id=batch.id,
                    user_id=sale.user_id,
                    quantity=item.quantity,
                    kind="payment_release",
                    reference=reference,
                    reason="Provider verified payment failure",
                )
            )
        sale.status = "cancelled"
        audit(
            db,
            db.get(User, sale.user_id),
            "gateway_payment_failed",
            sale.id,
            {"reference": reference},
        )
    db.commit()
    return {
        "reference": reference,
        "provider_status": result.get("status"),
        "sale": sale_json(db, sale),
    }


@router.post("/{reference}/verify")
def verify(reference: str, user=Depends(current_user), db: Session = Depends(get_db)):
    intent = db.scalar(
        select(PaymentIntent).where(PaymentIntent.reference == reference)
    )
    if not intent:
        raise HTTPException(404, "Payment reference not found")
    sale = db.get(Sale, intent.sale_id)
    if user.role == "cashier" and sale.user_id != user.id:
        raise HTTPException(403, "You can only verify your own sales")
    return reconcile(db, reference)


@router.get("/pending")
def pending(user=Depends(current_user), db: Session = Depends(get_db)):
    query = (
        select(PaymentIntent, Sale)
        .join(Sale)
        .where(Sale.status.in_(["pending", "paid_review"]))
    )
    if user.role == "cashier":
        query = query.where(Sale.user_id == user.id)
    return [
        {
            "reference": p.reference,
            "sale_id": s.id,
            "status": s.status,
            "total": s.total / 100,
            "authorization_url": p.authorization_url,
        }
        for p, s in db.execute(query.order_by(Sale.id.desc()).limit(100))
    ]


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    if len(raw) > 100000:
        raise HTTPException(413, "Payload too large")
    signature = request.headers.get("x-paystack-signature", "")
    expected = hmac.new(secret().encode(), raw, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(401, "Invalid webhook signature")
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Invalid JSON")
    if event.get("event") == "charge.success":
        reference = event.get("data", {}).get("reference")
        if isinstance(reference, str) and db.scalar(
            select(PaymentIntent.id).where(PaymentIntent.reference == reference)
        ):
            await run_in_threadpool(reconcile, db, reference)
    return {"received": True}
