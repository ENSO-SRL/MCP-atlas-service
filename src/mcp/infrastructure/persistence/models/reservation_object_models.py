from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.database.session import Base


class ReservationObjectSchemaModel(Base):
    """Modelo ORM para la tabla 'reservation_object_schemas' de ATLAS-BACKEND."""
    __tablename__ = "reservation_object_schemas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schema_header: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    schema_fields: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    service_id: Mapped[int] = mapped_column(Integer, ForeignKey("servicios.id"), nullable=False)
    establishment_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("establishments.id"), nullable=True)
    section_name: Mapped[str] = mapped_column(String(100), default="Tus datos", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    objects: Mapped[list[ReservationObjectModel]] = relationship(back_populates="schema")


class ReservationObjectModel(Base):
    """Modelo ORM para la tabla 'reservation_objects' de ATLAS-BACKEND."""
    __tablename__ = "reservation_objects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schema_id: Mapped[int] = mapped_column(Integer, ForeignKey("reservation_object_schemas.id"), nullable=False)
    user_phone: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    object_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    object_alias: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    schema: Mapped[ReservationObjectSchemaModel] = relationship(back_populates="objects")

