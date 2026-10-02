import os

os.environ.setdefault("SECRET_KEY", "test-only-secret-not-valid-for-production-12345")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test-pharmastock.db")
import pytest
from fastapi.testclient import TestClient
from app.db import Base, engine, SessionLocal
from app.models import User
from app.security import password_hash, attempts
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    attempts.clear()
    with SessionLocal() as db:
        for role in ["admin", "pharmacist", "cashier"]:
            db.add(
                User(
                    username=role,
                    email=role + "@example.test",
                    password_hash=password_hash.hash("Test-password-123!"),
                    role=role,
                )
            )
        db.commit()
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(engine)


@pytest.fixture()
def headers(client):
    return {
        r: {
            "Authorization": "Bearer "
            + client.post(
                "/api/auth/login",
                json={"username": r, "password": "Test-password-123!"},
            ).json()["access_token"]
        }
        for r in ["admin", "pharmacist", "cashier"]
    }
