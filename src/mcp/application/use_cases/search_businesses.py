from __future__ import annotations

from typing import Optional

from src.mcp.application.dto.business_dtos import (
    BusinessSummaryDTO,
    SearchBusinessesQueryDTO,
    SearchBusinessesResponseDTO,
)
from src.mcp.domain.ports.mcp_ports import (
    ICatalogServiceRepository,
    IEstablishmentRepository,
)

GATEWAY_CATEGORY_NAME = "pasarelas"


class SearchBusinessesUseCase:
    """
    Caso de uso: Búsqueda de establecimientos (search_businesses).
    Permite filtrar clubes deportivos, talleres, cines o veterinarias por texto libre,
    categoría o ubicación geográfica.

    Soporta 'Establecimientos Pasarela':
    Si un establecimiento pertenece a la categoría 'Pasarelas', no se expone directamente
    como club físico, sino que se consultan sus servicios activos (que representan sedes reales)
    aplicando el limit restante directamente en la base de datos y marcándolos con is_service=True.
    """

    def __init__(
        self,
        establishment_repo: IEstablishmentRepository,
        catalog_service_repo: Optional[ICatalogServiceRepository] = None,
    ):
        self._establishment_repo = establishment_repo
        self._catalog_service_repo = catalog_service_repo

    async def execute(self, query: SearchBusinessesQueryDTO) -> SearchBusinessesResponseDTO:
        limit = min(max(query.limit, 1), 50)
        offset = max(query.cursor, 0)

        # 1. Consultar establecimientos en repositorio
        establishments = await self._establishment_repo.search(
            query=query.query,
            category=query.category,
            zone=query.zone,
            limit=limit,
            offset=offset,
        )

        items: list[BusinessSummaryDTO] = []
        gateway_establishments = []

        # 2. Filtrar pasarelas y agregar establecimientos estándar
        for est in establishments:
            cat_name = (est.category_name or "").strip().lower()
            if cat_name == GATEWAY_CATEGORY_NAME:
                gateway_establishments.append(est)
                continue

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
                    is_service=False,
                )
            )

        # 3. Completar el límite restante con servicios de las pasarelas detectadas
        if self._catalog_service_repo and gateway_establishments:
            for gateway_est in gateway_establishments:
                remaining_limit = limit - len(items)
                if remaining_limit <= 0:
                    break

                # Aplicar el limit restante directamente a la consulta de base de datos
                services = await self._catalog_service_repo.list_by_establishment(
                    establishment_id=gateway_est.id,
                    limit=remaining_limit,
                )

                hours: dict[str, str] = {}
                if gateway_est.opening_hour and gateway_est.closing_hour:
                    hours = {
                        "opening": gateway_est.opening_hour.strftime("%H:%M"),
                        "closing": gateway_est.closing_hour.strftime("%H:%M"),
                    }

                for svc in services:
                    loc = svc.location
                    addr_line = f"{loc.street or ''} {loc.building_number or ''}".strip() or None if loc else None
                    if not addr_line and gateway_est.location:
                        gloc = gateway_est.location
                        addr_line = f"{gloc.street or ''} {gloc.building_number or ''}".strip() or None

                    city = (loc.city if loc else None) or (gateway_est.location.city if gateway_est.location else None)
                    sector = (loc.sector if loc else None) or (gateway_est.location.sector if gateway_est.location else None)

                    items.append(
                        BusinessSummaryDTO(
                            id=svc.id,
                            name=svc.name,
                            code=svc.combo_code or f"SVC-{svc.id}",
                            category=svc.category_name,
                            city=city,
                            sector=sector,
                            address_line=addr_line,
                            operating_hours=hours,
                            rule_type=gateway_est.rule_type.value if gateway_est.rule_type else "only_today",
                            is_service=True,
                        )
                    )

                    if len(items) >= limit:
                        break

        next_cursor = offset + limit if len(items) == limit else None

        return SearchBusinessesResponseDTO(
            items=items,
            next_cursor=next_cursor,
            total_count=len(items),
        )
