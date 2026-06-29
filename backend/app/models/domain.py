from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Domain(Base):
    __tablename__ = "domains"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("domains.id", ondelete="SET NULL"), nullable=True
    )

    parent: Mapped["Domain | None"] = relationship(
        "Domain", remote_side=[id], back_populates="children"
    )
    children: Mapped[list["Domain"]] = relationship(
        "Domain", back_populates="parent", cascade="all, delete-orphan"
    )
