import os, time, hashlib, secrets, smtplib
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import jwt
from pwdlib import PasswordHash
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .db import get_db
from .models import User

SECRET_KEY = os.getenv("SECRET_KEY", "")
if len(SECRET_KEY) < 32 or SECRET_KEY.startswith("replace_"):
    raise RuntimeError("SECRET_KEY must be configured with at least 32 characters")
password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
attempts = defaultdict(deque)


def rate_limit(request: Request, purpose: str, limit=10):
    key = (request.client.host if request.client else "unknown", purpose)
    recent = attempts[key]
    current = time.monotonic()
    while recent and recent[0] < current - 300:
        recent.popleft()
    if len(recent) >= limit:
        raise HTTPException(429, "Too many attempts. Try again in five minutes.")
    recent.append(current)
    if len(attempts) > 10000:
        for old in list(attempts):
            if not attempts[old] or attempts[old][-1] < current - 300:
                del attempts[old]


def token_for(user):
    return jwt.encode(
        {
            "sub": str(user.id),
            "ver": user.token_version,
            "exp": datetime.now(timezone.utc) + timedelta(hours=8),
            "iat": datetime.now(timezone.utc),
        },
        SECRET_KEY,
        algorithm="HS256",
    )


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
):
    try:
        claims = jwt.decode(
            credentials.credentials if credentials else "",
            SECRET_KEY,
            algorithms=["HS256"],
        )
        user = db.get(User, int(claims["sub"]))
        if not user or not user.active or user.token_version != claims["ver"]:
            raise ValueError()
        return user
    except (jwt.InvalidTokenError, ValueError, KeyError, TypeError):
        raise HTTPException(401, "Please sign in again")


def roles(*allowed):
    def check(user=Depends(current_user)):
        if user.role not in allowed:
            raise HTTPException(403, "You do not have permission for this action")
        return user

    return check


def send_reset(email, token):
    host = os.getenv("SMTP_HOST")
    if not host:
        return False
    message = EmailMessage()
    message["Subject"] = "Reset your PharmaStock POS password"
    message["From"] = os.getenv("SMTP_FROM", "noreply@example.com")
    message["To"] = email
    message.set_content(
        f"Use this password reset token within 30 minutes:\n\n{token}\n\nIf you did not request a reset, ignore this email."
    )
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=10) as smtp:
        smtp.starttls()
        if os.getenv("SMTP_USERNAME"):
            smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(message)
    return True
