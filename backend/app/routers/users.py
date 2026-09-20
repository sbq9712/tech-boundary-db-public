from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password, require_admin
from app.db.session import get_db
from app.models.user import User

router = APIRouter(tags=["users"], dependencies=[Depends(require_admin)])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class CreateUserIn(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    role: str = "user"


class UpdateUserIn(BaseModel):
    display_name: str | None = None
    role: str | None = None
    is_active: bool | None = None


class ResetPasswordIn(BaseModel):
    new_password: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_admins(db: Session) -> int:
    """Number of users whose role == 'admin'."""
    return int(db.scalar(select(func.count()).select_from(User).where(User.role == "admin")) or 0)


def _is_admin(user: User | None) -> bool:
    return bool(user) and user.role == "admin"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/users")
def list_users(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(User).order_by(User.created_at.asc())).all()
    return {
        "users": [
            {
                "username": u.username,
                "display_name": u.display_name,
                "role": u.role,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                "password_changed_at": (
                    u.password_changed_at.isoformat() if u.password_changed_at else None
                ),
            }
            for u in rows
        ]
    }


@router.post("/users", status_code=201)
def create_user(
    payload: CreateUserIn,
    db: Session = Depends(get_db),
) -> dict:
    username = payload.username.strip()
    if not username:
        raise HTTPException(400, "用户名不能为空")
    if len(payload.password) < 6:
        raise HTTPException(400, "密码不能少于6位")
    if payload.role not in ("admin", "atsc", "user"):
        raise HTTPException(400, "角色只能是 admin、atsc 或 user")
    if db.get(User, username):
        raise HTTPException(409, "用户名已存在")

    user = User(
        username=username,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
    }


@router.patch("/users/{username}")
def update_user(
    username: str,
    payload: UpdateUserIn,
    current_user: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(User, username)
    if not user:
        raise HTTPException(404, "用户不存在")

    is_self = username == current_user

    if payload.role is not None and payload.role not in ("admin", "atsc", "user"):
        raise HTTPException(400, "角色只能是 admin、atsc 或 user")

    # Demoting from admin -> non-admin: cannot remove the last admin.
    if (
        payload.role in ("atsc", "user")
        and user.role == "admin"
        and _count_admins(db) <= 1
    ):
        raise HTTPException(400, "至少保留一个管理员")

    # Cannot disable yourself.
    if is_self and payload.is_active is False and user.is_active:
        raise HTTPException(400, "不能禁用自己的账号")

    # Apply changes.
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active

    db.commit()
    db.refresh(user)
    return {
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
    }


@router.delete("/users/{username}", status_code=204)
def delete_user(
    username: str,
    current_user: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    if username == current_user:
        raise HTTPException(400, "不能删除自己的账号")
    user = db.get(User, username)
    if not user:
        raise HTTPException(404, "用户不存在")
    if _is_admin(user) and _count_admins(db) <= 1:
        raise HTTPException(400, "不能删除最后一个管理员")
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{username}/reset-password", status_code=204)
def reset_password(
    username: str,
    payload: ResetPasswordIn,
    db: Session = Depends(get_db),
) -> Response:
    if len(payload.new_password) < 6:
        raise HTTPException(400, "密码不能少于6位")
    user = db.get(User, username)
    if not user:
        raise HTTPException(404, "用户不存在")
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
