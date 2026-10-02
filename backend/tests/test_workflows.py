from app.clock import today as utc_today
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from uuid import uuid4
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Batch


def stock(c, h, qty=10, rx=False):
    supplier = c.post(
        "/api/suppliers", headers=h["admin"], json={"name": "Test Supplier"}
    ).json()
    p = c.post(
        "/api/products",
        headers=h["admin"],
        json={
            "name": "Test medicine",
            "code": uuid4().hex,
            "selling_price": 10,
            "prescription_required": rx,
        },
    ).json()

    def receive(number, quantity, days):
        return c.post(
            "/api/stock/receive",
            headers=h["admin"],
            json={
                "supplier_id": supplier["id"],
                "reference": uuid4().hex,
                "items": [
                    {
                        "product_id": p["id"],
                        "batch_number": number,
                        "quantity": quantity,
                        "purchase_price": 4,
                        "expiry_date": (utc_today() + timedelta(days=days)).isoformat(),
                    }
                ],
            },
        )

    assert receive("EARLY", qty, 10).status_code == 201
    assert receive("LATER", qty, 100).status_code == 201
    return p, supplier, receive


def sale(c, h, p, qty=1, **kw):
    return c.post(
        "/api/sales",
        headers=h,
        json={
            "items": [{"product_id": p["id"], "quantity": qty}],
            "payment_method": "Cash",
            "amount_paid": qty * 10,
            "idempotency_key": uuid4().hex,
            **kw,
        },
    )


def test_fefo_and_movement_balance(client, headers):
    p, _, _ = stock(client, headers, 3)
    r = sale(client, headers["cashier"], p, 4)
    assert r.status_code == 201, r.text
    assert [i["quantity"] for i in r.json()["items"]] == [3, 1]
    assert [
        b["quantity"]
        for b in client.get("/api/batches", headers=headers["admin"]).json()
    ] == [0, 2]
    assert (
        sum(
            m["quantity"]
            for m in client.get("/api/stock/movements", headers=headers["admin"]).json()
        )
        == 2
    )
    assert any(
        a["action"] == "sale_completed"
        for a in client.get("/api/audit", headers=headers["admin"]).json()
    )


def test_oversell_rollback(client, headers):
    p, _, _ = stock(client, headers, 2)
    assert sale(client, headers["cashier"], p, 5).status_code == 409
    assert (
        client.get("/api/products", headers=headers["admin"]).json()["items"][0][
            "quantity"
        ]
        == 4
    )
    assert client.get("/api/sales", headers=headers["admin"]).json()["total"] == 0


def test_expired_stock_blocked(client, headers):
    p, _, _ = stock(client, headers, 2)
    with SessionLocal() as db:
        for b in db.scalars(select(Batch)):
            b.expiry_date = utc_today()
        db.commit()
    assert sale(client, headers["admin"], p).status_code == 409
    assert (
        client.get("/api/products", headers=headers["admin"]).json()["items"][0][
            "expired_quantity"
        ]
        == 4
    )


def test_idempotency(client, headers):
    p, _, _ = stock(client, headers)
    key = uuid4().hex
    a = sale(client, headers["admin"], p, idempotency_key=key)
    b = sale(client, headers["admin"], p, idempotency_key=key)
    assert a.json()["id"] == b.json()["id"]
    assert (
        client.get("/api/products", headers=headers["admin"]).json()["items"][0][
            "quantity"
        ]
        == 19
    )


def test_cashier_permissions(client, headers):
    for path in ["users", "audit", "reports", "customers", "suppliers", "batches"]:
        assert client.get("/api/" + path, headers=headers["cashier"]).status_code == 403
    assert client.get("/api/products").status_code == 401
    assert (
        client.post(
            "/api/products",
            headers=headers["cashier"],
            json={"name": "X", "code": "X", "selling_price": 1},
        ).status_code
        == 403
    )


def test_prescription_gate(client, headers):
    p, _, _ = stock(client, headers, rx=True)
    assert (
        sale(client, headers["cashier"], p, prescription_verified=True).status_code
        == 403
    )
    assert sale(client, headers["pharmacist"], p).status_code == 403
    assert (
        sale(client, headers["pharmacist"], p, prescription_verified=True).status_code
        == 201
    )


def test_full_refund_once(client, headers):
    p, _, _ = stock(client, headers)
    s = sale(client, headers["cashier"], p, 2).json()
    path = f"/api/sales/{s['id']}/refund"
    data = {"reason": "Approved unopened return", "restock": True}
    assert client.post(path, headers=headers["cashier"], json=data).status_code == 403
    r = client.post(path, headers=headers["admin"], json=data)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "refunded"
    assert client.post(path, headers=headers["admin"], json=data).status_code == 409
    assert (
        client.get("/api/products", headers=headers["admin"]).json()["items"][0][
            "quantity"
        ]
        == 20
    )
    report = client.get("/api/reports", headers=headers["admin"]).json()
    assert report["gross_sales"] == 0 and report["refunds"] == 20


def test_receive_atomicity(client, headers):
    p, s, _ = stock(client, headers)
    item = {
        "product_id": p["id"],
        "batch_number": "NEW",
        "quantity": 5,
        "purchase_price": 4,
        "expiry_date": (utc_today() + timedelta(days=10)).isoformat(),
    }
    r = client.post(
        "/api/stock/receive",
        headers=headers["admin"],
        json={
            "supplier_id": s["id"],
            "reference": "bad-delivery",
            "items": [item, {**item, "product_id": 99999}],
        },
    )
    assert r.status_code == 404
    assert (
        client.get("/api/products", headers=headers["admin"]).json()["items"][0][
            "quantity"
        ]
        == 20
    )
    assert len(client.get("/api/stock/receipts", headers=headers["admin"]).json()) == 2


def test_negative_adjustment(client, headers):
    stock(client, headers)
    b = client.get("/api/batches", headers=headers["admin"]).json()[0]
    assert (
        client.post(
            "/api/stock/adjust",
            headers=headers["admin"],
            json={"batch_id": b["id"], "quantity": -11, "reason": "Stock correction"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/stock/adjust",
            headers=headers["admin"],
            json={"batch_id": b["id"], "quantity": -2, "reason": "Damaged packages"},
        ).json()["quantity"]
        == 8
    )


def test_cashier_own_sales(client, headers):
    p, _, _ = stock(client, headers)
    s = sale(client, headers["admin"], p).json()
    assert (
        client.get(f"/api/sales/{s['id']}", headers=headers["cashier"]).status_code
        == 403
    )
    assert client.get("/api/sales", headers=headers["cashier"]).json()["total"] == 0


def test_tax_and_payment(client, headers):
    p, _, _ = stock(client, headers)
    config = client.get("/api/settings", headers=headers["admin"]).json()
    config["tax_percent"] = "2.50"
    assert (
        client.put("/api/settings", headers=headers["admin"], json=config).status_code
        == 200
    )
    r = sale(client, headers["admin"], p, discount="1.11", amount_paid="10.00").json()
    assert r["tax"] == 0.22 and r["total"] == 9.11 and r["change"] == 0.89
    assert sale(client, headers["cashier"], p, discount=1).status_code == 403
    assert (
        sale(
            client, headers["admin"], p, payment_method="Card", amount_paid=12
        ).status_code
        == 400
    )


def test_concurrent_checkout(client, headers):
    p, _, _ = stock(client, headers, qty=1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: sale(client, headers["cashier"], p, qty=2), range(2))
        )
    assert sorted(r.status_code for r in results) == [201, 409]
    assert (
        client.get("/api/products", headers=headers["admin"]).json()["items"][0][
            "quantity"
        ]
        == 0
    )


def test_logout_revokes(client, headers):
    assert (
        client.post("/api/auth/logout", headers=headers["cashier"]).status_code == 200
    )
    assert client.get("/api/auth/me", headers=headers["cashier"]).status_code == 401


def test_login_rate_limit(client):
    for _ in range(10):
        assert (
            client.post(
                "/api/auth/login", json={"username": "missing", "password": "bad"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login", json={"username": "missing", "password": "bad"}
        ).status_code
        == 429
    )


def test_csv_escape(client, headers):
    client.post(
        "/api/products",
        headers=headers["admin"],
        json={"name": "=UNSAFE()", "code": "ESCAPE", "selling_price": 1},
    )
    r = client.get("/api/reports/export?kind=inventory", headers=headers["admin"])
    assert r.status_code == 200 and "'=UNSAFE()" in r.text


def test_batch_metadata_validation(client, headers):
    _, _, receive = stock(client, headers)
    assert receive("EARLY", 3, 11).status_code == 409
    assert receive("EXPIRED", 3, -2).status_code == 422


def test_multi_product_rollback(client, headers):
    p, _, _ = stock(client, headers)
    r = sale(
        client,
        headers["admin"],
        p,
        items=[
            {"product_id": p["id"], "quantity": 1},
            {"product_id": 99999, "quantity": 1},
        ],
    )
    assert r.status_code == 404
    assert (
        client.get("/api/products", headers=headers["admin"]).json()["items"][0][
            "quantity"
        ]
        == 20
    )


def test_user_permission_change_revokes_session(client, headers):
    user = client.get("/api/auth/me", headers=headers["cashier"]).json()
    result = client.put(
        "/api/users/" + str(user["id"]),
        headers=headers["admin"],
        json={"email": user["email"], "role": "pharmacist"},
    )
    assert result.status_code == 200, result.text
    assert client.get("/api/auth/me", headers=headers["cashier"]).status_code == 401
    fresh = client.post(
        "/api/auth/login",
        json={"username": "cashier", "password": "Test-password-123!"},
    ).json()
    assert fresh["user"]["role"] == "pharmacist"


def test_admin_password_reset(client, headers):
    user = client.get("/api/auth/me", headers=headers["cashier"]).json()
    assert (
        client.put(
            "/api/users/" + str(user["id"]),
            headers=headers["admin"],
            json={
                "email": user["email"],
                "role": "cashier",
                "password": "New-password-123!",
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"username": "cashier", "password": "Test-password-123!"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"username": "cashier", "password": "New-password-123!"},
        ).status_code
        == 200
    )


def test_reset_token_is_single_use_and_revokes_session(client, headers):
    import hashlib
    from app.models import PasswordReset, User, now

    token = "reset-token-for-test-only-123456789"
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "cashier"))
        db.add(
            PasswordReset(
                user_id=user.id,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=now() + timedelta(minutes=10),
            )
        )
        db.commit()
    body = {"token": token, "password": "Updated-password-123!"}
    assert client.post("/api/auth/reset-confirm", json=body).status_code == 200
    assert client.post("/api/auth/reset-confirm", json=body).status_code == 400
    assert client.get("/api/auth/me", headers=headers["cashier"]).status_code == 401


def test_demo_seed_complete(client, headers, monkeypatch):
    from app.cli import seed

    monkeypatch.setenv("ALLOW_DEMO_SEED", "true")
    seed()
    assert client.get("/api/products", headers=headers["admin"]).json()["total"] == 30
    assert client.get("/api/sales", headers=headers["admin"]).json()["total"] == 7
    assert len(client.get("/api/suppliers", headers=headers["admin"]).json()) == 5


def test_dashboard_uses_ghana_business_date(client, headers):
    p, _, _ = stock(client, headers)
    result = sale(client, headers["admin"], p)
    assert result.status_code == 201
    dashboard = client.get("/api/dashboard", headers=headers["admin"]).json()
    assert dashboard["today_sales"] == 10 and dashboard["today_transactions"] == 1
    assert dashboard["trend"][-1]["sales"] == 10
