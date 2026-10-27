from __future__ import annotations

from typing import Optional

from src.mcp.application.dto.booking_dtos import (
    BookingSummaryDTO,
    ListMyBookingsQueryDTO,
    ListMyBookingsResponseDTO,
)
from src.mcp.domain.enums.mcp_enums import BookingStatus
from src.mcp.domain.exceptions.mcp_exceptions import ContractValidationException
from src.mcp.domain.ports.mcp_ports import (
    IBookingRepository,
    ICatalogServiceRepository,
)


class ListMyBookingsUseCase:
    """
    Caso de uso: Listar historial paginado de reservas del usuario autenticado (list_my_bookings).
    Permite filtrar por estado, resuelve nombres de servicios e incluye los applied_filters
    para preservar el contexto de dimensiones del slot reservado.
    """

    def __init__(
        self,
        booking_repo: IBookingRepository,
        catalog_service_repo: ICatalogServiceRepository,
    ):
        self._booking_repo = booking_repo
        self._catalog_service_repo = catalog_service_repo

    async def execute(self, query: ListMyBookingsQueryDTO) -> ListMyBookingsResponseDTO:
        # 1. Validar y convertir filtro de estado si fue especificado
        status_enum: Optional[BookingStatus] = None
        if query.status_filter:
            try:
                status_enum = BookingStatus(query.status_filter.lower())
            except ValueError:
                valid_statuses = [s.value for s in BookingStatus]
                raise ContractValidationException(
                    f"Filtro de estado '{query.status_filter}' no válido. Valores permitidos: {valid_statuses}."
                )

        # 2. Consultar registros con cursor/offset solicitando 1 adicional para determinar next_cursor
        limit = max(1, min(query.limit, 50))  # Asegurar límite entre 1 y 50
        offset = max(0, query.cursor)

        records = await self._booking_repo.list_by_user(
            user_uuid=query.user_uuid,
            status=status_enum,
            limit=limit + 1,
            offset=offset,
        )

        has_next = len(records) > limit
        items = records[:limit]
        next_cursor = offset + limit if has_next else None

        # 3. Resolver nombres de servicios (optimizando duplicados en memoria)
        service_names: dict[int, str] = {}
        for b in items:
            if b.service_id not in service_names:
                svc = await self._catalog_service_repo.get_by_id(b.service_id)
                service_names[b.service_id] = svc.name if svc else "Servicio no disponible"

        # 4. Mapear a DTOs de resumen
        summary_dtos = [
            BookingSummaryDTO(
                booking_id=b.id,
                service_id=b.service_id,
                status=b.status.value,
                service_name=service_names.get(b.service_id),
                slot_start=b.slot_start,
                slot_end=b.slot_end,
                applied_filters=b.applied_filters,
                external_ref=b.external_ref,
                created_at=b.created_at,
            )
            for b in items
        ]

        return ListMyBookingsResponseDTO(
            items=summary_dtos,
            next_cursor=next_cursor,
            total_count=len(summary_dtos),
        )
