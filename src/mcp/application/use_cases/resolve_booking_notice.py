from __future__ import annotations

from typing import Optional

from src.mcp.application.dto.booking_dtos import (
    ResolveBookingNoticeInputDTO,
    ResolveBookingNoticeResultDTO,
)
from src.mcp.domain.enums.mcp_enums import BookingStatus
from src.mcp.domain.exceptions.mcp_exceptions import EntityNotFoundException
from src.mcp.domain.ports.mcp_ports import (
    IBookingRepository,
    ICatalogServiceRepository,
    IOutboxRepository,
)


class ResolveBookingNoticeUseCase:
    """
    Caso de uso: Resolver alertas o solicitudes de confirmación sobre una reserva (resolve_booking_notice).
    Permite al usuario aceptar ('accept') o rechazar ('reject') avisos de discrepancia (ej. tarifas).
    Si se aceptan todos los avisos requeridos, la reserva reanuda el trámite hacia el establecimiento
    y emite un evento BookingResumed en el Outbox.
    Si se rechaza, la reserva transiciona a REJECTED y emite BookingRejected.
    """

    def __init__(
        self,
        booking_repo: IBookingRepository,
        outbox_repo: IOutboxRepository,
        catalog_repo: Optional[ICatalogServiceRepository] = None,
    ):
        self._booking_repo = booking_repo
        self._outbox_repo = outbox_repo
        self._catalog_repo = catalog_repo

    async def execute(
        self, query: ResolveBookingNoticeInputDTO
    ) -> ResolveBookingNoticeResultDTO:
        # 1. Recuperar reserva y verificar pertenencia (multi-tenancy)
        booking = await self._booking_repo.get_by_id(query.booking_id)
        if not booking or booking.user_uuid != query.user_uuid:
            raise EntityNotFoundException(
                f"Reserva con id {query.booking_id} no encontrada."
            )

        # 2. Ejecutar resolución en el agregado BookingRequest
        resolved_ids = booking.resolve_notice(
            decision=query.decision,
            notice_id=query.notice_id,
        )

        # 3. Guardar cambios en el repositorio
        await self._booking_repo.save(booking)

        # 4. Registrar evento en Outbox para propagación asíncrona hacia el Facade/upstream
        combo_code: Optional[str] = None
        if self._catalog_repo is not None:
            svc = await self._catalog_repo.get_by_id(booking.service_id)
            if svc:
                combo_code = svc.combo_code

        decision_norm = query.decision.strip().lower()

        if decision_norm == "accept" and booking.status == BookingStatus.ACCEPTED:
            outbox_payload = {
                "booking_id": str(booking.id),
                "user_uuid": str(booking.user_uuid),
                "user_phone": query.user_phone,
                "user_email": query.user_email,
                "service_id": booking.service_id,
                "combo_code": combo_code,
                "status": booking.status.value,
                "action": "accepted",
                "accepted_notice_ids": [str(nid) for nid in resolved_ids],
                "projected_total": float(booking.price_estimate.amount) if booking.price_estimate else None,
            }
            await self._outbox_repo.record_event(
                event_type="BookingResumed",
                aggregate_id=booking.id,
                payload=outbox_payload,
                correlation_id=str(booking.id),
            )
            message = (
                "Avisos confirmados exitosamente. La reserva ha reanudado su trámite hacia el establecimiento."
            )
        elif decision_norm == "reject":
            outbox_payload = {
                "booking_id": str(booking.id),
                "user_uuid": str(booking.user_uuid),
                "user_phone": query.user_phone,
                "user_email": query.user_email,
                "service_id": booking.service_id,
                "combo_code": combo_code,
                "status": booking.status.value,
                "action": "rejected",
                "rejected_notice_ids": [str(nid) for nid in resolved_ids],
                "reason": booking.status_reason,
            }
            await self._outbox_repo.record_event(
                event_type="BookingRejected",
                aggregate_id=booking.id,
                payload=outbox_payload,
                correlation_id=str(booking.id),
            )
            message = (
                "Has rechazado las condiciones o tarifas notificadas. La reserva fue cancelada/rechazada."
            )
        else:
            message = (
                "Aviso resuelto. La reserva aún tiene otros avisos pendientes antes de poder reanudar el trámite."
            )

        return ResolveBookingNoticeResultDTO(
            booking_id=booking.id,
            status=booking.status.value,
            decision=decision_norm,
            resolved_notice_ids=resolved_ids,
            message=message,
        )

