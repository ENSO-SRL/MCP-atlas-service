from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.database.session import Base


class BookingRequestModel(Base):
    """Modelo ORM para mcp.booking_request."""
    __tablename__ = "booking_request"
    __table_args__ = (
        UniqueConstraint("user_uuid", "idempotency_key", name="uq_booking_user_idempotency"),
        {"schema": "mcp"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_uuid: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    service_id: Mapped[int] = mapped_column(Integer, ForeignKey("servicios.id"), nullable=False)
    contract_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("mcp.service_contract_version.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), default="requested", nullable=False)
    status_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    token_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    offer_ref: Mapped[str] = mapped_column(Text, nullable=False)
    hold_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    slot_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resource_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    applied_filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    price_estimate: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    external_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assigned_details: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    last_event_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    history: Mapped[list[BookingStatusHistoryModel]] = relationship(
        back_populates="booking", cascade="all, delete-orphan"
    )


class BookingStatusHistoryModel(Base):
    """Modelo ORM para mcp.booking_status_history."""
    __tablename__ = "booking_status_history"
    __table_args__ = {"schema": "mcp"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    booking_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("mcp.booking_request.id"), nullable=False
    )
    from_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    cause: Mapped[str] = mapped_column(Text, nullable=False)
    event_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    booking: Mapped[BookingRequestModel] = relationship(back_populates="history")


class OutboxEventModel(Base):
    """Modelo ORM para mcp.outbox_event (patrón Transactional Outbox)."""
    __tablename__ = "outbox_event"
    __table_args__ = {"schema": "mcp"}

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    aggregate_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class InboxEventModel(Base):
    """Modelo ORM para mcp.inbox_event (patrón Transactional Inbox idempotente)."""
    __tablename__ = "inbox_event"
    __table_args__ = {"schema": "mcp"}

    event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
