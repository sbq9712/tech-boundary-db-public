from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-before-production")
TOKEN_EXPIRE_SECONDS = 7 * 24 * 3600  # 7 days
_PBKDF2_ITERATIONS = 260_000

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS
    ).hex()
    return f"{salt}:{h}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, expected = stored_hash.split(":", 1)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS
        ).hex()
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def create_token(username: str) -> str:
    now = time.time()
    payload = json.dumps({"sub": username, "iat": now, "exp": now + TOKEN_EXPIRE_SECONDS})
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def _decode_token(token: str) -> dict | None:
    """Verify signature and expiry; return full payload dict or None."""
    parts = token.split(".", 1)
    if len(parts) != 2:
        return None
    payload_b64, sig = parts
    expected_sig = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None
    try:
        padding = "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
    except Exception:
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload


def verify_token(token: str) -> str | None:
    payload = _decode_token(token)
    return payload.get("sub") if payload else None


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> str:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = _decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username: str = payload.get("sub", "")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # If the user changed their password after this token was issued, reject it.
    from app.models.user import User  # local import to avoid circular deps at module level
    user = db.get(User, username)
    if user and user.password_changed_at:
        token_iat: float = payload.get("iat", 0)
        if token_iat < user.password_changed_at.timestamp():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="密码已修改，请重新登录",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return username
