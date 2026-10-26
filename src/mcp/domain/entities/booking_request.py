from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from src.mcp.domain.enums.mcp_enums import BookingStatus
from src.mcp.domain.events.booking_events import (
    BookingAcceptedEvent,
    BookingConfirmedEvent,
    BookingExpiredEvent,
    BookingFailedEvent,
    BookingRejectedEvent,
    BookingRequestedEvent,
    CancellationConfirmedEvent,
    CancellationRejectedEvent,
    CancellationRequestedEvent,
)
from src.mcp.domain.exceptions.mcp_exceptions import InvalidStateTransitionException
from src.mcp.domain.value_objects.booking_vo import PriceEstimate
from src.shared.domain.base import AggregateRoot


@dataclass
class BookingRequest(AggregateRoot[UUID]):
    """
    Agregado Raíz BookingRequest.
    Encapsula el ciclo de vida y la máquina de estados estricta de una solicitud de reserva diferida.
    """
    user_uuid: UUID = field(default_factory=uuid4)
    service_id: int = 0
    contract_version_id: UUID = field(default_factory=uuid4)
    status: BookingStatus = BookingStatus.REQUESTED
    status_reason: Optional[str] = None
    idempotency_key: str = ""
    request_fingerprint: str = ""
    token_id: str = ""
    offer_ref: str = ""
    hold_id: Optional[str] = None
    slot_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    slot_end: Optional[datetime] = None
    resource_ref: Optional[str] = None
    applied_filters: dict[str, Any] = field(default_factory=dict)
    fields: dict[str, Any] = field(default_factory=dict)
    price_estimate: Optional[PriceEstimate] = None
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    external_ref: Optional[str] = None
    assigned_details: Optional[dict[str, Any]] = None
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(
        cls,
        user_uuid: UUID,
        service_id: int,
        contract_version_id: UUID,
        idempotency_key: str,
        request_fingerprint: str,
        token_id: str,
        offer_ref: str,
        slot_start: datetime,
        expires_at: datetime,
        hold_id: Optional[str] = None,
        slot_end: Optional[datetime] = None,
        resource_ref: Optional[str] = None,
        applied_filters: Optional[dict[str, Any]] = None,
        fields: Optional[dict[str, Any]] = None,
        price_estimate: Optional[PriceEstimate] = None,
    ) -> BookingRequest:
        booking = cls(
            id=uuid4(),
            user_uuid=user_uuid,
            service_id=service_id,
            contract_version_id=contract_version_id,
            status=BookingStatus.REQUESTED,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            token_id=token_id,
            offer_ref=offer_ref,
            hold_id=hold_id,
            slot_start=slot_start,
            slot_end=slot_end,
            resource_ref=resource_ref,
            applied_filters=applied_filters or {},
            fields=fields or {},
            price_estimate=price_estimate,
            expires_at=expires_at,
        )
        booking.record_event(
            BookingRequestedEvent(
                booking_id=booking.id,
                user_uuid=booking.user_uuid,
                service_id=booking.service_id,
                offer_ref=booking.offer_ref,
                slot_start=booking.slot_start,
                fields=booking.fields,
                expires_at=booking.expires_at,
            )
        )
        return booking

    def accept(self, external_ref: Optional[str] = None, assigned_details: Optional[dict[str, Any]] = None) -> None:
        """
        Marca la solicitud como aceptada en trámite por el ejecutor/establecimiento,
        pendiente de confirmación o rechazo definitivo.
        """
        if self.status != BookingStatus.REQUESTED:
            raise InvalidStateTransitionException(self.status, BookingStatus.ACCEPTED)

        self.status = BookingStatus.ACCEPTED
        if external_ref:
            self.external_ref = external_ref
        if assigned_details:
            self.assigned_details = assigned_details
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
        self.record_event(
            BookingAcceptedEvent(
                booking_id=self.id,
                external_ref=external_ref,
                details=assigned_details,
            )
        )

    def confirm(self, external_ref: str, assigned_details: Optional[dict[str, Any]] = None) -> None:
        """
        Confirma la reserva. Se permite desde REQUESTED, ACCEPTED o desde EXPIRED (confirmación tardía).
        """
        if self.status not in (BookingStatus.REQUESTED, BookingStatus.ACCEPTED, BookingStatus.EXPIRED):
            raise InvalidStateTransitionException(self.status, BookingStatus.CONFIRMED)

        self.status = BookingStatus.CONFIRMED
        self.external_ref = external_ref
        self.assigned_details = assigned_details
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
        self.record_event(
            BookingConfirmedEvent(
                booking_id=self.id,
                external_ref=external_ref,
                assigned_details=assigned_details,
            )
        )

    def reject(self, reason: str) -> None:
        if self.status not in (BookingStatus.REQUESTED, BookingStatus.ACCEPTED):
            raise InvalidStateTransitionException(self.status, BookingStatus.REJECTED)

        self.status = BookingStatus.REJECTED
        self.status_reason = reason
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
        self.record_event(BookingRejectedEvent(booking_id=self.id, reason=reason))

    def fail(self, reason: str) -> None:
        if self.status not in (BookingStatus.REQUESTED, BookingStatus.ACCEPTED):
            raise InvalidStateTransitionException(self.status, BookingStatus.FAILED)

        self.status = BookingStatus.FAILED
        self.status_reason = reason
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
        self.record_event(BookingFailedEvent(booking_id=self.id, reason=reason))

    def expire(self) -> None:
        if self.status not in (BookingStatus.REQUESTED, BookingStatus.ACCEPTED):
            raise InvalidStateTransitionException(self.status, BookingStatus.EXPIRED)

        self.status = BookingStatus.EXPIRED
        self.status_reason = "Vencimiento del tiempo límite de confirmación del establecimiento."
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
        self.record_event(BookingExpiredEvent(booking_id=self.id))

    def request_cancellation(self, reason: Optional[str] = None) -> None:
        if self.status not in (BookingStatus.REQUESTED, BookingStatus.ACCEPTED, BookingStatus.CONFIRMED):
            raise InvalidStateTransitionException(self.status, BookingStatus.CANCEL_REQUESTED)

        self.status = BookingStatus.CANCEL_REQUESTED
        self.status_reason = reason
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
        self.record_event(CancellationRequestedEvent(booking_id=self.id, reason=reason))

    def confirm_cancellation(self) -> None:
        if self.status != BookingStatus.CANCEL_REQUESTED:
            raise InvalidStateTransitionException(self.status, BookingStatus.CANCELLED)

        self.status = BookingStatus.CANCELLED
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
        self.record_event(CancellationConfirmedEvent(booking_id=self.id))

    def reject_cancellation(self, reason: Optional[str] = None) -> None:
        if self.status != BookingStatus.CANCEL_REQUESTED:
            raise InvalidStateTransitionException(self.status, BookingStatus.CONFIRMED)

        self.status = BookingStatus.CONFIRMED
        self.status_reason = reason
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
        self.record_event(CancellationRejectedEvent(booking_id=self.id, reason=reason))
