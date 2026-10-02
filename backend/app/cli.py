from .clock import today as utc_today

"""Administrative commands; no public account registration."""

import argparse, getpass, os
from datetime import date, timedelta
from sqlalchemy import select
from .db import SessionLocal
from .models import User, Product, Supplier, Batch, Movement, Setting, Sale, SaleItem
from .security import password_hash
from .schemas import SettingsIn


def create_admin():
    username = input("Admin username: ").strip()
    email = input("Admin email: ").strip()
    password = getpass.getpass("Password (at least 12 characters): ")
    if len(password) < 12 or not username or "@" not in email:
        raise SystemExit("Valid username, email and 12-character password are required")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == username)):
            raise SystemExit("Username already exists")
        db.add(
            User(
                username=username,
                email=email,
                password_hash=password_hash.hash(password),
                role="admin",
            )
        )
        db.commit()
    print("Administrator created")


def seed():
    if os.getenv("ALLOW_DEMO_SEED") != "true":
        raise SystemExit("Set ALLOW_DEMO_SEED=true only for a demo database")
    with SessionLocal() as db:
        if db.scalar(select(Product)):
            raise SystemExit("Demo seed requires an empty product catalogue")
        user = db.scalar(select(User).where(User.role == "admin"))
        if not user:
            raise SystemExit("Create an administrator first")
        suppliers = [
            Supplier(
                name=f"Fictional Demo Supplier {i + 1}",
                contact="Demo Contact",
                address="Fictional address, Ghana",
            )
            for i in range(5)
        ]
        db.add_all(suppliers)
        db.flush()
        catalogue = [
            ("Paracetamol", "500 mg", "Tablet"),
            ("Oral rehydration salts", "", "Sachet"),
            ("Vitamin C", "100 mg", "Tablet"),
            ("Zinc", "20 mg", "Tablet"),
            ("Amoxicillin", "500 mg", "Capsule"),
            ("Ibuprofen", "200 mg", "Tablet"),
            ("Cetirizine", "10 mg", "Tablet"),
            ("Folic acid", "5 mg", "Tablet"),
            ("Ferrous sulfate", "200 mg", "Tablet"),
            ("Metformin", "500 mg", "Tablet"),
            ("Amlodipine", "5 mg", "Tablet"),
            ("Omeprazole", "20 mg", "Capsule"),
            ("Antacid", "", "Suspension"),
            ("Saline nasal spray", "", "Spray"),
            ("Multivitamin", "", "Tablet"),
            ("Digital thermometer", "", "Device"),
            ("Adhesive plasters", "", "Pack"),
            ("Sterile gauze", "", "Pack"),
            ("Hand sanitizer", "100 ml", "Bottle"),
            ("Sunscreen", "SPF 30", "Tube"),
            ("Baby wipes", "", "Pack"),
            ("Toothpaste", "100 g", "Tube"),
            ("Toothbrush", "", "Unit"),
            ("Petroleum jelly", "100 g", "Jar"),
            ("Soap", "", "Bar"),
            ("Disposable masks", "", "Pack"),
            ("Examination gloves", "", "Box"),
            ("Cotton wool", "", "Pack"),
            ("Blood pressure monitor", "", "Device"),
            ("Glucose test strips", "", "Pack"),
        ]
        for i, (name, strength, form) in enumerate(catalogue):
            p = Product(
                code=f"DEMO-{i + 1:03}",
                barcode=f"99000000{i + 1:05}",
                name=name,
                generic_name=name if i < 15 else "",
                strength=strength,
                form=form,
                category="Medicines" if i < 15 else "Healthcare & toiletries",
                supplier_id=suppliers[i % 5].id,
                selling_price=(i % 8 + 2) * 100,
                reorder_level=20,
                prescription_required=i in (4, 9, 10),
                storage_notes="Fictional demo data. Store according to the actual product label.",
            )
            db.add(p)
            db.flush()
            qty = 0 if i % 10 == 0 else 8 if i % 7 == 0 else 80 + i * 3
            b = Batch(
                product_id=p.id,
                number=f"DEMO-B{i + 1:03}",
                quantity=qty,
                purchase_price=(i % 8 + 1) * 100,
                expiry_date=utc_today()
                + timedelta(days=20 if i % 6 == 0 else 200 + i * 5),
            )
            db.add(b)
            db.flush()
            if qty:
                db.add(
                    Movement(
                        batch_id=b.id,
                        user_id=user.id,
                        quantity=qty,
                        kind="opening",
                        reference="FICTIONAL-DEMO",
                        reason="Fictional demo opening stock",
                    )
                )
            if i < 5:
                old = Batch(
                    product_id=p.id,
                    number=f"DEMO-OLD{i + 1}",
                    quantity=10,
                    purchase_price=100,
                    expiry_date=utc_today() - timedelta(days=5)
                    if i == 0
                    else utc_today() + timedelta(days=10),
                )
                db.add(old)
                db.flush()
                db.add(
                    Movement(
                        batch_id=old.id,
                        user_id=user.id,
                        quantity=10,
                        kind="opening",
                        reference="FICTIONAL-DEMO",
                        reason="Fictional demo opening stock",
                    )
                )
        if not db.get(Setting, 1):
            db.add(
                Setting(
                    id=1,
                    values=SettingsIn(
                        pharmacy_name="DEMO PharmaStock Pharmacy",
                        address="Fictional demo pharmacy, Ghana",
                        receipt_footer="DEMO ONLY — not a real transaction",
                    ).model_dump(mode="json"),
                )
            )
        db.commit()
    from .main import create_sale
    from .schemas import SaleIn
    from uuid import uuid4

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.role == "admin"))
        products = db.scalars(
            select(Product).where(
                Product.prescription_required == False, Product.code != "DEMO-001"
            )
        ).all()
        for i in range(7):
            product = products[i % len(products)]
            result = create_sale(
                SaleIn(
                    items=[{"product_id": product.id, "quantity": 1}],
                    payment_method="Cash",
                    amount_paid=product.selling_price / 100,
                    idempotency_key=uuid4().hex,
                ),
                user=user,
                db=db,
            )
            record = db.get(Sale, result["id"])
            record.created_at = record.created_at - timedelta(days=i)
            db.commit()
    print("30 fictional products, 5 fictional suppliers and 7 fictional sales created")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["create-admin", "seed-demo"])
    args = parser.parse_args()
    create_admin() if args.command == "create-admin" else seed()
