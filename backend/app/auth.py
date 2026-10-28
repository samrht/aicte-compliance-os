"""Administrator sign-in: a password check and a short-lived signed token.

The token is `<payload>.<HMAC-SHA256>` over a base64 JSON payload, signed with
a key derived from the deployment's audit key, so no session table is needed
and any server instance can check it.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Header, HTTPException

from app import config

DEMO_USER, DEMO_PASSWORD = "admin", "aicte-admin-2026"
ADMIN_USER = os.environ.get("ADMIN_USER", DEMO_USER)
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", DEMO_PASSWORD)
# The login page may show the demo account only while it is the real one.
USING_DEMO_ACCOUNT = "ADMIN_PASSWORD" not in os.environ
TOKEN_TTL = 8 * 3600

_KEY = hashlib.sha256(b"acos-admin-token:" + (config.AUDIT_SIGNING_KEY or "local-dev").encode()
                      + ADMIN_PASSWORD.encode()).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def check_password(username: str, password: str) -> bool:
    ok_user = hmac.compare_digest(username.strip().lower(), ADMIN_USER.lower())
    ok_pass = hmac.compare_digest(password, ADMIN_PASSWORD)
    return ok_user and ok_pass


def issue_token(username: str) -> tuple[str, int]:
    exp = int(time.time()) + TOKEN_TTL
    payload = _b64(json.dumps({"sub": username, "exp": exp}).encode())
    sig = _b64(hmac.new(_KEY, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}", exp


def read_token(token: str) -> str | None:
    try:
        payload, sig = token.split(".", 1)
        good = _b64(hmac.new(_KEY, payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        data = json.loads(_unb64(payload))
        return data["sub"] if data["exp"] > time.time() else None
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def require_admin(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency: the signed-in administrator's name, or 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in as an administrator.")
    who = read_token(authorization.split(" ", 1)[1].strip())
    if who is None:
        raise HTTPException(401, "Your admin session has expired. Sign in again.")
    return who
