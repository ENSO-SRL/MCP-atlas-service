from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.database.session import Base


class ServiceContractVersionModel(Base):
    """Modelo ORM para mcp.service_contract_version."""
    __tablename__ = "service_contract_version"
    __table_args__ = (
        UniqueConstraint("service_id", "version_no", name="uq_contract_version_service_no"),
        {"schema": "mcp"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    service_id: Mapped[int] = mapped_column(Integer, ForeignKey("servicios.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    pattern: Mapped[str] = mapped_column(String(30), default="slot_object", nullable=False)
    booking_fields_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    payment_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    cancellation_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    request_ttl_seconds: Mapped[int] = mapped_column(Integer, default=900, nullable=False)
    meta_schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    content_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    dimensions: Mapped[list[ContractDimensionModel]] = relationship(
        back_populates="contract_version", cascade="all, delete-orphan"
    )


class ContractDimensionModel(Base):
    """Modelo ORM para mcp.contract_dimension."""
    __tablename__ = "contract_dimension"
    __table_args__ = (
        UniqueConstraint("contract_version_id", "key", name="uq_dimension_version_key"),
        UniqueConstraint("id", "contract_version_id", name="uq_dimension_id_version"),
        {"schema": "mcp"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    contract_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("mcp.service_contract_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    values_source: Mapped[str] = mapped_column(String(30), nullable=False)
    apply_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allows_any: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reports_counts: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolver_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    contract_version: Mapped[ServiceContractVersionModel] = relationship(back_populates="dimensions")
    inline_values: Mapped[list[ContractDimensionValueModel]] = relationship(
        back_populates="dimension", cascade="all, delete-orphan"
    )


class ContractDimensionDependencyModel(Base):
    """Modelo ORM para mcp.contract_dimension_dependency."""
    __tablename__ = "contract_dimension_dependency"
    __table_args__ = (
        ForeignKeyConstraint(
            ["dimension_id", "contract_version_id"],
            ["mcp.contract_dimension.id", "mcp.contract_dimension.contract_version_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["depends_on_dimension_id", "contract_version_id"],
            ["mcp.contract_dimension.id", "mcp.contract_dimension.contract_version_id"],
            ondelete="CASCADE",
        ),
        {"schema": "mcp"},
    )

    contract_version_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    dimension_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    depends_on_dimension_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)


class ContractDimensionValueModel(Base):
    """Modelo ORM para mcp.contract_dimension_value."""
    __tablename__ = "contract_dimension_value"
    __table_args__ = (
        UniqueConstraint("dimension_id", "value_key", name="uq_dimension_value_key"),
        ForeignKeyConstraint(
            ["dimension_id", "contract_version_id"],
            ["mcp.contract_dimension.id", "mcp.contract_dimension.contract_version_id"],
            ondelete="CASCADE",
        ),
        {"schema": "mcp"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    contract_version_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    dimension_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    value_key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)

    dimension: Mapped[ContractDimensionModel] = relationship(back_populates="inline_values")


class ServicePricingPolicyModel(Base):
    """Modelo ORM para mcp.service_pricing_policy."""
    __tablename__ = "service_pricing_policy"
    __table_args__ = {"schema": "mcp"}

    service_id: Mapped[int] = mapped_column(Integer, ForeignKey("servicios.id"), primary_key=True)
    pricing_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    tax_included: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    info_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    disclaimer_override: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    price_rules: Mapped[list[ServicePriceRuleModel]] = relationship(back_populates="policy")


class ServicePriceRuleModel(Base):
    """Modelo ORM para mcp.service_price_rule."""
    __tablename__ = "service_price_rule"
    __table_args__ = {"schema": "mcp"}

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    service_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("mcp.service_pricing_policy.service_id"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    weekdays: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), nullable=False)
    start_minute: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    end_minute: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    min_party_size: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    max_party_size: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    min_duration_min: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    max_duration_min: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    dimension_conditions: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    calculation_basis: Mapped[str] = mapped_column(String(20), nullable=False)
    is_starting_price: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    policy: Mapped[ServicePricingPolicyModel] = relationship(back_populates="price_rules")
