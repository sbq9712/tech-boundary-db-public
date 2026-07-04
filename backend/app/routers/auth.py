from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import (
    create_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User

router = APIRouter(tags=["auth"])

# ---------------------------------------------------------------------------
# Simple in-memory rate limiter for login failures (per client IP)
# ---------------------------------------------------------------------------
_failed_attempts: dict[str, list[float]] = defaultdict(list)
_rate_lock = Lock()
_MAX_FAILURES = 5       # allow 5 failures ...
_WINDOW_SECONDS = 300   # ... within 5 minutes


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_login_rate_limit(ip: str) -> None:
    now = time.time()
    cutoff = now - _WINDOW_SECONDS
    with _rate_lock:
        _failed_attempts[ip] = [t for t in _failed_attempts[ip] if t > cutoff]
        if len(_failed_attempts[ip]) >= _MAX_FAILURES:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"登录失败次数过多，请 {_WINDOW_SECONDS // 60} 分钟后再试",
            )


def _record_login_failure(ip: str) -> None:
    with _rate_lock:
        _failed_attempts[ip].append(time.time())


# ---------------------------------------------------------------------------


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeOut(BaseModel):
    username: str
    display_name: str | None = None
    role: str = "user"


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.post("/auth/login", response_model=TokenOut)
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    ip = _get_client_ip(request)
    _check_login_rate_limit(ip)

    user = db.get(User, payload.username)
    if not user or not verify_password(payload.password, user.password_hash):
        _record_login_failure(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号已禁用",
        )
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return TokenOut(access_token=create_token(payload.username))


@router.get("/auth/me", response_model=MeOut)
def me(current_user: str = Depends(get_current_user), db: Session = Depends(get_db)) -> MeOut:
    user = db.get(User, current_user)
    return MeOut(
        username=current_user,
        display_name=user.display_name if user else None,
        role=user.role if user else "user",
    )


@router.patch("/auth/password")
def change_password(
    payload: ChangePasswordIn,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    user = db.get(User, current_user)
    if not user or not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码错误")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码不能少于6位")
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
