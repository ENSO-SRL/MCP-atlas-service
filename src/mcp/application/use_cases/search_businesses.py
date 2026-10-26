from __future__ import annotations

from src.mcp.application.dto.business_dtos import (
    BusinessSummaryDTO,
    SearchBusinessesQueryDTO,
    SearchBusinessesResponseDTO,
)
from src.mcp.domain.ports.mcp_ports import IEstablishmentRepository


class SearchBusinessesUseCase:
    """
    Caso de uso: Búsqueda de establecimientos (search_businesses).
    Permite filtrar clubes deportivos, talleres, cines o veterinarias por texto libre,
    categoría o ubicación geográfica.
    """

    def __init__(self, establishment_repo: IEstablishmentRepository):
        self._establishment_repo = establishment_repo

    async def execute(self, query: SearchBusinessesQueryDTO) -> SearchBusinessesResponseDTO:
        limit = min(max(query.limit, 1), 50)
        offset = max(query.cursor, 0)

        # Consultar repositorio
        establishments = await self._establishment_repo.search(
            query=query.query,
            category=query.category,
            zone=query.zone,
            limit=limit,
            offset=offset,
        )

        items: list[BusinessSummaryDTO] = []
        for est in establishments:
            loc = est.location
            addr_line = f"{loc.street or ''} {loc.building_number or ''}".strip() or None if loc else None
            hours: dict[str, str] = {}
            if est.opening_hour and est.closing_hour:
                hours = {
                    "opening": est.opening_hour.strftime("%H:%M"),
                    "closing": est.closing_hour.strftime("%H:%M"),
                }

            items.append(
                BusinessSummaryDTO(
                    id=est.id,
                    name=est.name,
                    code=est.code,
                    category=est.category_name,
                    city=loc.city if loc else None,
                    sector=loc.sector if loc else None,
                    address_line=addr_line,
                    operating_hours=hours,
                    rule_type=est.rule_type.value if est.rule_type else "only_today",
                )
            )

        next_cursor = offset + limit if len(items) == limit else None

        return SearchBusinessesResponseDTO(
            items=items,
            next_cursor=next_cursor,
            total_count=len(items),
        )
