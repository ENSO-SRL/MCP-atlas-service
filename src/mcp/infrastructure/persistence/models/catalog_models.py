from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Time
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.database.session import Base


class EstablishmentCategoryModel(Base):
    """Modelo ORM para la tabla 'establishment_categories' de ATLAS-BACKEND."""
    __tablename__ = "establishment_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    establishments: Mapped[list[EstablishmentModel]] = relationship(back_populates="category")


class EstablishmentModel(Base):
    """Modelo ORM para la tabla 'establishments' de ATLAS-BACKEND."""
    __tablename__ = "establishments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    has_credentials: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    has_scheduler: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, nullable=True)
    rule_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    opening_hour: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    closing_hour: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    endpoint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("establishment_categories.id"), nullable=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    services: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state_province: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sector: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    residential: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    street: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    building_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    google_maps_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    category: Mapped[Optional[EstablishmentCategoryModel]] = relationship(back_populates="establishments")
    servicios: Mapped[list[ServicioModel]] = relationship(back_populates="establishment")


class CategoriaServicioModel(Base):
    """Modelo ORM para la tabla 'categorias_servicio' de ATLAS-BACKEND."""
    __tablename__ = "categorias_servicio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    servicios: Mapped[list[ServicioModel]] = relationship(back_populates="categoria")


class ServicioModel(Base):
    """Modelo ORM para la tabla 'servicios' de ATLAS-BACKEND."""
    __tablename__ = "servicios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    categoria_id: Mapped[int] = mapped_column(Integer, ForeignKey("categorias_servicio.id"), nullable=False)
    establishment_id: Mapped[int] = mapped_column(Integer, ForeignKey("establishments.id"), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    combo_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sub_endpoint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    has_credentials: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    configuration: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    services: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sector: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    street: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    building_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    google_maps_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    establishment: Mapped[EstablishmentModel] = relationship(back_populates="servicios")
    categoria: Mapped[CategoriaServicioModel] = relationship(back_populates="servicios")
