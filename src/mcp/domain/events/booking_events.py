from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from src.shared.domain.base import DomainEvent


@dataclass
class BookingRequestedEvent(DomainEvent):
    booking_id: UUID = field(default_factory=uuid4)
    user_uuid: UUID = field(default_factory=uuid4)
    service_id: int = 0
    offer_ref: Optional[str] = None
    slot_start: Optional[datetime] = None
    fields: dict[str, Any] = field(default_factory=dict)
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class BookingAcceptedEvent(DomainEvent):
    booking_id: UUID = field(default_factory=uuid4)
    external_ref: Optional[str] = None
    details: Optional[dict[str, Any]] = None


@dataclass
class BookingConfirmedEvent(DomainEvent):
    booking_id: UUID = field(default_factory=uuid4)
    external_ref: str = ""
    assigned_details: Optional[dict[str, Any]] = None


@dataclass
class BookingRejectedEvent(DomainEvent):
    booking_id: UUID = field(default_factory=uuid4)
    reason: str = ""


@dataclass
class BookingFailedEvent(DomainEvent):
    booking_id: UUID = field(default_factory=uuid4)
    reason: str = ""


@dataclass
class BookingExpiredEvent(DomainEvent):
    booking_id: UUID = field(default_factory=uuid4)


@dataclass
class CancellationRequestedEvent(DomainEvent):
    booking_id: UUID = field(default_factory=uuid4)
    reason: Optional[str] = None


@dataclass
class CancellationConfirmedEvent(DomainEvent):
    booking_id: UUID = field(default_factory=uuid4)


@dataclass
class CancellationRejectedEvent(DomainEvent):
    booking_id: UUID = field(default_factory=uuid4)
    reason: Optional[str] = None
