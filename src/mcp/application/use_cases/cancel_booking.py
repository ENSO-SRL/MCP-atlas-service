from typing import Optional

from src.mcp.application.dto.booking_dtos import (
    CancelBookingInputDTO,
    CancellationResultDTO,
)
from src.mcp.domain.exceptions.mcp_exceptions import EntityNotFoundException
from src.mcp.domain.ports.mcp_ports import (
    IBookingRepository,
    ICatalogServiceRepository,
    IOutboxRepository,
)


class CancelBookingUseCase:
    """
    Caso de uso: Cancelar reserva activa (cancel_booking).
    Verifica pertenencia al usuario (multi-tenancy), ejecuta la transición de dominio
    (a CANCEL_REQUESTED), persiste la entidad y registra el evento en el Outbox transaccional
    para propagación asíncrona a ATLAS-BACKEND.
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

    async def execute(self, query: CancelBookingInputDTO) -> CancellationResultDTO:
        # 1. Recuperar reserva y verificar que pertenece al usuario autenticado
        booking = await self._booking_repo.get_by_id(query.booking_id)
        if not booking or booking.user_uuid != query.user_uuid:
            raise EntityNotFoundException(
                f"Reserva con id {query.booking_id} no encontrada."
            )

        # 2. Transición de estado en el modelo de dominio
        # (Lanza InvalidStateTransitionException si la reserva ya está cancelada, rechazada o expirada)
        booking.request_cancellation(reason=query.reason)

        # 3. Guardar cambios en el repositorio
        await self._booking_repo.save(booking)

        # 4. Registrar evento en Outbox para propagación asíncrona
        combo_code: Optional[str] = None
        if self._catalog_repo is not None:
            svc = await self._catalog_repo.get_by_id(booking.service_id)
            if svc:
                combo_code = svc.combo_code

        outbox_payload = {
            "booking_id": str(booking.id),
            "user_uuid": str(booking.user_uuid),
            "user_phone": query.user_phone,
            "service_id": booking.service_id,
            "combo_code": combo_code,
            "external_ref": booking.external_ref,
            "reason": query.reason,
        }
        await self._outbox_repo.record_event(
            event_type="CancellationRequested",
            aggregate_id=booking.id,
            payload=outbox_payload,
            correlation_id=str(booking.id),
        )

        return CancellationResultDTO(
            booking_id=booking.id,
            status=booking.status.value,
            message="Solicitud de cancelación registrada exitosamente. Pendiente de confirmación por el establecimiento.",
        )
