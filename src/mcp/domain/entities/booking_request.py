from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from src.mcp.domain.entities.booking_notice import BookingNotice
from src.mcp.domain.enums.mcp_enums import BookingStatus, NoticeStatus, NoticeType
from src.mcp.domain.events.booking_events import (
    BookingAcceptedEvent,
    BookingConfirmedEvent,
    BookingExpiredEvent,
    BookingFailedEvent,
    BookingNoticeRaisedEvent,
    BookingRejectedEvent,
    BookingRequestedEvent,
    BookingResumedEvent,
    CancellationConfirmedEvent,
    CancellationRejectedEvent,
    CancellationRequestedEvent,
)
from src.mcp.domain.exceptions.mcp_exceptions import (
    EntityNotFoundException,
    InvalidStateTransitionException,
)
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
    token_id: Optional[str] = None
    offer_ref: Optional[str] = None
    hold_id: Optional[str] = None
    slot_start: Optional[datetime] = None
    slot_end: Optional[datetime] = None
    resource_ref: Optional[str] = None
    applied_filters: dict[str, Any] = field(default_factory=dict)
    fields: dict[str, Any] = field(default_factory=dict)
    price_estimate: Optional[PriceEstimate] = None
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    external_ref: Optional[str] = None
    assigned_details: Optional[dict[str, Any]] = None
    notices: list[BookingNotice] = field(default_factory=list)
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
        token_id: Optional[str] = None,
        offer_ref: Optional[str] = None,
        slot_start: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
        hold_id: Optional[str] = None,
        slot_end: Optional[datetime] = None,
        resource_ref: Optional[str] = None,
        applied_filters: Optional[dict[str, Any]] = None,
        fields: Optional[dict[str, Any]] = None,
        price_estimate: Optional[PriceEstimate] = None,
    ) -> BookingRequest:
        actual_expires_at = expires_at if expires_at is not None else datetime.now(timezone.utc)
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
            expires_at=actual_expires_at,
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
        if self.status not in (BookingStatus.REQUESTED, BookingStatus.REQUIRES_CONFIRMATION):
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
        Confirma la reserva. Se permite desde REQUESTED, ACCEPTED, EXPIRED (confirmación tardía)
        o REQUIRES_CONFIRMATION.
        """
        if self.status not in (
            BookingStatus.REQUESTED,
            BookingStatus.ACCEPTED,
            BookingStatus.EXPIRED,
            BookingStatus.REQUIRES_CONFIRMATION,
        ):
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
        if self.status not in (
            BookingStatus.REQUESTED,
            BookingStatus.ACCEPTED,
            BookingStatus.REQUIRES_CONFIRMATION,
        ):
            raise InvalidStateTransitionException(self.status, BookingStatus.REJECTED)

        self.status = BookingStatus.REJECTED
        self.status_reason = reason
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
        self.record_event(BookingRejectedEvent(booking_id=self.id, reason=reason))

    def fail(self, reason: str) -> None:
        if self.status not in (
            BookingStatus.REQUESTED,
            BookingStatus.ACCEPTED,
            BookingStatus.REQUIRES_CONFIRMATION,
        ):
            raise InvalidStateTransitionException(self.status, BookingStatus.FAILED)

        self.status = BookingStatus.FAILED
        self.status_reason = reason
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
        self.record_event(BookingFailedEvent(booking_id=self.id, reason=reason))

    def expire(self) -> None:
        if self.status not in (
            BookingStatus.REQUESTED,
            BookingStatus.ACCEPTED,
            BookingStatus.REQUIRES_CONFIRMATION,
        ):
            raise InvalidStateTransitionException(self.status, BookingStatus.EXPIRED)

        self.status = BookingStatus.EXPIRED
        self.status_reason = "Vencimiento del tiempo límite de confirmación del establecimiento."
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
        self.record_event(BookingExpiredEvent(booking_id=self.id))

    def request_cancellation(self, reason: Optional[str] = None) -> None:
        if self.status not in (
            BookingStatus.REQUESTED,
            BookingStatus.ACCEPTED,
            BookingStatus.CONFIRMED,
            BookingStatus.REQUIRES_CONFIRMATION,
        ):
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

    def raise_notice(
        self,
        notice_type: NoticeType | str,
        message: str,
        payload: Optional[dict[str, Any]] = None,
        requires_action: bool = True,
        notice_id: Optional[UUID] = None,
    ) -> BookingNotice:
        """
        Levanta una alerta, discrepancia o solicitud de confirmación sobre la reserva.
        Si requires_action es True, pausa la reserva pasando a REQUIRES_CONFIRMATION.
        """
        if self.status not in (
            BookingStatus.REQUESTED,
            BookingStatus.ACCEPTED,
            BookingStatus.REQUIRES_CONFIRMATION,
        ):
            raise InvalidStateTransitionException(self.status, BookingStatus.REQUIRES_CONFIRMATION)

        parsed_type = NoticeType(notice_type) if isinstance(notice_type, str) else notice_type
        nid = notice_id or uuid4()
        now_utc = datetime.now(timezone.utc)

        # Evitar duplicados por idempotencia de eventos de inbox
        existing = next((n for n in self.notices if n.id == nid), None)
        if existing:
            return existing

        notice = BookingNotice(
            id=nid,
            booking_id=self.id,
            notice_type=parsed_type,
            status=NoticeStatus.PENDING,
            message=message,
            payload=payload or {},
            requires_action=requires_action,
            created_at=now_utc,
        )
        self.notices.append(notice)

        if requires_action:
            self.status = BookingStatus.REQUIRES_CONFIRMATION
            self.status_reason = message

        self.updated_at = now_utc
        self.version += 1
        self.record_event(
            BookingNoticeRaisedEvent(
                booking_id=self.id,
                notice_id=notice.id,
                notice_type=notice.notice_type.value,
                message=message,
                payload=notice.payload,
                requires_action=requires_action,
            )
        )
        return notice

    def resolve_notice(
        self,
        decision: str,
        notice_id: Optional[UUID] = None,
    ) -> list[UUID]:
        """
        Resuelve uno o todos los avisos pendientes en la reserva.
        decision: 'accept' o 'reject'.
        Si se aceptan todos los avisos que requieren acción, la reserva se reanuda a ACCEPTED.
        Si se rechaza, la reserva transiciona a REJECTED.
        """
        if self.status != BookingStatus.REQUIRES_CONFIRMATION:
            raise InvalidStateTransitionException(self.status, BookingStatus.ACCEPTED)

        decision_norm = decision.strip().lower()
        if decision_norm not in ("accept", "reject"):
            raise ValueError(f"Decisión inválida '{decision}'. Debe ser 'accept' o 'reject'.")

        target_notices: list[BookingNotice] = []
        if notice_id is not None:
            target = next((n for n in self.notices if n.id == notice_id), None)
            if not target:
                raise EntityNotFoundException(f"Aviso con id {notice_id} no encontrado en la reserva.")
            target_notices = [target]
        else:
            target_notices = [n for n in self.notices if n.status == NoticeStatus.PENDING]

        if not target_notices:
            return []

        now_utc = datetime.now(timezone.utc)
        resolved_ids: list[UUID] = []

        for n in target_notices:
            if n.status == NoticeStatus.PENDING:
                if decision_norm == "accept":
                    n.status = NoticeStatus.ACCEPTED
                    n.resolution_action = "accepted"
                    # Si el aviso es una discrepancia de precio, actualizar price_estimate
                    if n.notice_type == NoticeType.PRICE_DISCREPANCY:
                        actual_total = n.payload.get("actual_total")
                        if actual_total is not None and self.price_estimate:
                            self.price_estimate = replace(
                                self.price_estimate,
                                amount=Decimal(str(actual_total)),
                            )
                else:
                    n.status = NoticeStatus.REJECTED
                    n.resolution_action = "rejected"

                n.resolved_at = now_utc
                resolved_ids.append(n.id)

        self.updated_at = now_utc
        self.version += 1

        if decision_norm == "reject":
            self.status = BookingStatus.REJECTED
            self.status_reason = (
                "Reserva rechazada por el usuario al no aceptar las condiciones o tarifas notificadas."
            )
            self.record_event(BookingRejectedEvent(booking_id=self.id, reason=self.status_reason))
        else:
            # Si el usuario aceptó, verificar si quedan avisos pendientes con requires_action
            has_pending_action = any(
                n.status == NoticeStatus.PENDING and n.requires_action
                for n in self.notices
            )
            if not has_pending_action:
                self.status = BookingStatus.ACCEPTED
                self.status_reason = "Avisos confirmados por el usuario. Trámite reanudado hacia el establecimiento."
                self.record_event(
                    BookingResumedEvent(
                        booking_id=self.id,
                        accepted_notice_ids=[
                            n.id for n in target_notices if n.resolution_action == "accepted"
                        ],
                    )
                )

        return resolved_ids
