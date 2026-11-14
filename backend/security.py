from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

SECRET_KEY = os.getenv("CHURN_SECRET_KEY", "local-churn-defense-secret-change-in-production")
ALGORITHM = "HS256"
ITERATIONS = 180_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip("=")
    return f"{ITERATIONS}${encode(salt)}${encode(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        iterations, salt_text, digest_text = stored.split("$", 2)
        decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), decode(salt_text), int(iterations))
        return hmac.compare_digest(actual, decode(digest_text))
    except (ValueError, TypeError):
        return False


def create_access_token(username: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": username, "role": role, "iat": now, "exp": now + timedelta(hours=12)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
