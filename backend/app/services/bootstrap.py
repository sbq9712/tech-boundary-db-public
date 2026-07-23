from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.domain import Domain
from app.models.user import User
from app.services.data_loader import load_json


def seed_domains_if_empty(db: Session) -> None:
    raw_domains = load_json("domains.json")
    if not isinstance(raw_domains, list):
        return

    existing_rows = db.scalars(select(Domain)).all()
    existing_by_id = {row.id: row for row in existing_rows}

    for row in raw_domains:
        if not isinstance(row, dict):
            continue
        if not row.get("id") or not row.get("name"):
            continue
        existing = existing_by_id.get(row["id"])
        if existing:
            existing.name = row["name"]
            existing.parent_id = row.get("parent_id")
            continue

        db.add(
            Domain(
                id=row["id"],
                name=row["name"],
                parent_id=row.get("parent_id"),
            )
        )
    db.commit()


def seed_users_if_empty(db: Session) -> None:
    """Create one explicit bootstrap administrator, never predictable bulk accounts."""
    username = os.getenv("TECHDB_INITIAL_ADMIN_USERNAME", "").strip()
    password = os.getenv("TECHDB_INITIAL_ADMIN_PASSWORD", "")
    if not username or not password:
        return
    if db.scalar(select(User.username).where(User.username == username)):
        return
    db.add(
        User(
            username=username,
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
        )
    )
    db.commit()
