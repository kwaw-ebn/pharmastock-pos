import hashlib, hmac, json
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from app import payments
from app.db import SessionLocal
from app.models import User, Batch
from test_workflows import stock, sale


@pytest.fixture()
def gateway(monkeypatch):
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_test_mock")
    monkeypatch.setenv("PAYMENT_CALLBACK_URL", "https://pharmacy.example")
    result = {
        "status": "success",
        "currency": "GHS",
        "amount": 1000,
        "domain": "test",
        "id": 91,
    }

    def provider(method, path, payload=None):
        if method == "POST":
            return {
                "reference": payload["reference"],
                "authorization_url": "https://checkout.paystack.com/test",
            }
        return {**result, "reference": path.rsplit("/", 1)[-1]}

    monkeypatch.setattr(payments, "provider", provider)
    return result


def initialize(client, headers, product, key=None):
    return client.post(
        "/api/payments/initialize",
        headers=headers["cashier"],
        json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "Card",
            "amount_paid": 10,
            "email": "customer@example.test",
            "idempotency_key": key or uuid4().hex,
        },
    )


def quantities(client, headers):
    return sum(
        b["quantity"]
        for b in client.get("/api/batches", headers=headers["admin"]).json()
    )


def test_verified_once_and_signed_webhook(client, headers, gateway):
    p, _, _ = stock(client, headers)
    key = uuid4().hex
    a = initialize(client, headers, p, key)
    assert a.status_code == 200, a.text
    ref = a.json()["reference"]
    assert initialize(client, headers, p, key).json()["reference"] == ref
    assert quantities(client, headers) == 19
    assert sale(client, headers["cashier"], p, payment_method="Card").status_code == 400
    raw = json.dumps({"event": "charge.success", "data": {"reference": ref}}).encode()
    assert client.post("/api/payments/webhook", content=raw).status_code == 401
    sig = hmac.new(b"sk_test_mock", raw, hashlib.sha512).hexdigest()
    assert (
        client.post(
            "/api/payments/webhook", content=raw, headers={"x-paystack-signature": sig}
        ).status_code
        == 200
    )
    verified = client.post(f"/api/payments/{ref}/verify", headers=headers["cashier"])
    assert verified.json()["sale"]["status"] == "completed"
    assert quantities(client, headers) == 19


@pytest.mark.parametrize(
    "field,value", [("amount", 900), ("currency", "USD"), ("domain", "live")]
)
def test_mismatch_keeps_sale_pending(client, headers, gateway, field, value):
    p, _, _ = stock(client, headers)
    ref = initialize(client, headers, p).json()["reference"]
    gateway[field] = value
    assert (
        client.post(
            f"/api/payments/{ref}/verify", headers=headers["cashier"]
        ).status_code
        == 409
    )
    assert (
        client.get("/api/payments/pending", headers=headers["cashier"]).json()[0][
            "status"
        ]
        == "pending"
    )
    assert quantities(client, headers) == 19


def test_failure_releases_once_and_late_success_requires_review(
    client, headers, gateway
):
    p, _, _ = stock(client, headers)
    ref = initialize(client, headers, p).json()["reference"]
    gateway["status"] = "failed"
    for _ in range(2):
        r = client.post(f"/api/payments/{ref}/verify", headers=headers["cashier"])
        assert r.json()["sale"]["status"] == "cancelled"
    assert quantities(client, headers) == 20
    gateway["status"] = "success"
    r = client.post(f"/api/payments/{ref}/verify", headers=headers["cashier"])
    assert r.json()["sale"]["status"] == "paid_review"
    assert quantities(client, headers) == 20


def test_initial_setup_single_use(client, monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_TOKEN", "setup-test-token")
    with SessionLocal() as db:
        db.execute(delete(User))
        db.commit()
    assert client.get("/api/auth/setup-status").json()["needs_setup"]
    values = {
        "username": "owner",
        "email": "owner@example.test",
        "password": "Secure-test-password!",
        "token": "wrong",
    }
    assert client.post("/api/auth/setup", json=values).status_code == 403
    values["token"] = "setup-test-token"
    assert client.post("/api/auth/setup", json=values).status_code == 200
    assert client.post("/api/auth/setup", json=values).status_code == 409
    assert not client.get("/api/auth/setup-status").json()["needs_setup"]
