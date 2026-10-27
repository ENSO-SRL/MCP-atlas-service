from __future__ import annotations

from typing import Any, Optional

from src.mcp.application.dto.booking_dtos import (
    BookingDetailsDTO,
    GetBookingStatusQueryDTO,
)
from src.mcp.domain.enums.mcp_enums import BookingStatus
from src.mcp.domain.exceptions.mcp_exceptions import EntityNotFoundException
from src.mcp.domain.ports.mcp_ports import (
    IBookingRepository,
    ICatalogServiceRepository,
    IEstablishmentRepository,
)


class GetBookingStatusUseCase:
    """
    Caso de uso: Consultar estado y trazabilidad de una reserva (get_booking_status).
    Garantiza aislamiento estricto por usuario (multi-tenancy) y genera una explicación
    humana clara del estado actual (ej. estado 'accepted' en cola del Queuer).
    """

    def __init__(
        self,
        booking_repo: IBookingRepository,
        catalog_service_repo: ICatalogServiceRepository,
        establishment_repo: IEstablishmentRepository,
    ):
        self._booking_repo = booking_repo
        self._catalog_service_repo = catalog_service_repo
        self._establishment_repo = establishment_repo

    async def execute(self, query: GetBookingStatusQueryDTO) -> BookingDetailsDTO:
        # 1. Recuperar reserva y verificar pertenencia al usuario
        booking = await self._booking_repo.get_by_id(query.booking_id)
        if not booking or booking.user_uuid != query.user_uuid:
            raise EntityNotFoundException(
                f"Reserva con id {query.booking_id} no encontrada."
            )

        # 2. Obtener nombres del servicio y establecimiento
        service_name: Optional[str] = None
        establishment_name: Optional[str] = None

        svc = await self._catalog_service_repo.get_by_id(booking.service_id)
        if svc:
            service_name = svc.name
            est = await self._establishment_repo.get_by_id(svc.establishment_id)
            if est:
                establishment_name = est.name

        # 3. Formatear precio si existe
        price_dict: Optional[dict[str, Any]] = None
        if booking.price_estimate:
            price_dict = {
                "amount": str(booking.price_estimate.amount),
                "currency": booking.price_estimate.currency,
                "basis": booking.price_estimate.basis.value,
                "label": booking.price_estimate.label,
                "informative": booking.price_estimate.informative,
            }

        # 4. Generar explicación contextual del estado
        explanation = "Estado de reserva desconocido."
        if booking.status == BookingStatus.REQUESTED:
            explanation = "La solicitud fue recibida y está en trámite de validación inicial."
        elif booking.status == BookingStatus.ACCEPTED:
            explanation = (
                "La solicitud fue aceptada por la sede o puesta en cola en el sistema Queuer; "
                "está en trámite pendiente de confirmación definitiva."
            )
        elif booking.status == BookingStatus.CONFIRMED:
            ref_str = f" Localizador: {booking.external_ref}." if booking.external_ref else ""
            explanation = f"Reserva confirmada exitosamente.{ref_str}"
        elif booking.status == BookingStatus.REJECTED:
            explanation = (
                f"La reserva fue rechazada por el establecimiento. Motivo: {booking.status_reason or 'No especificado'}."
            )
        elif booking.status == BookingStatus.FAILED:
            explanation = (
                f"No fue posible completar la reserva debido a un fallo técnico. Motivo: {booking.status_reason or 'Fallo interno'}."
            )
        elif booking.status == BookingStatus.EXPIRED:
            explanation = "La solicitud expiró al no recibir confirmación del establecimiento dentro del tiempo límite establecido."
        elif booking.status == BookingStatus.CANCEL_REQUESTED:
            explanation = "Cancelación solicitada por el usuario; pendiente de confirmación por la sede física."
        elif booking.status == BookingStatus.CANCELLED:
            explanation = "La reserva fue cancelada exitosamente."

        return BookingDetailsDTO(
            booking_id=booking.id,
            user_uuid=booking.user_uuid,
            service_id=booking.service_id,
            status=booking.status.value,
            service_name=service_name,
            establishment_name=establishment_name,
            status_reason=booking.status_reason,
            slot_start=booking.slot_start,
            slot_end=booking.slot_end,
            resource_ref=booking.resource_ref,
            applied_filters=booking.applied_filters,
            fields=booking.fields,
            price_estimate=price_dict,
            external_ref=booking.external_ref,
            assigned_details=booking.assigned_details,
            expires_at=booking.expires_at,
            created_at=booking.created_at,
            updated_at=booking.updated_at,
            explanation=explanation,
        )
