"""Simple admin password authentication."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional

from fastapi import Header, HTTPException

from src import config

_TOKEN_TTL_SECONDS = 86400  # 24h
_SECRET = config.ADMIN_PASSWORD or "dev-insecure-change-me"


def _sign_token() -> str:
    expires = int(time.time()) + _TOKEN_TTL_SECONDS
    payload = f"admin:{expires}"
    sig = hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{sig}"


def verify_password(password: str) -> Optional[dict]:
    if not config.ADMIN_PASSWORD:
        if password == "admin":
            return {"token": _sign_token(), "expires_in": _TOKEN_TTL_SECONDS}
        return None
    if hmac.compare_digest(password, config.ADMIN_PASSWORD):
        return {"token": _sign_token(), "expires_in": _TOKEN_TTL_SECONDS}
    return None


def _verify_token(token: str) -> bool:
    try:
        expires_str, sig = token.split(".", 1)
        expires = int(expires_str)
        if time.time() > expires:
            return False
        payload = f"admin:{expires}"
        expected = hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)
    except (ValueError, AttributeError):
        return False


def require_admin(authorization: Optional[str] = Header(None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin authentication required")
    token = authorization[7:].strip()
    if not _verify_token(token):
        raise HTTPException(status_code=401, detail="Invalid or expired admin token")
