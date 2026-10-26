from __future__ import annotations

from typing import Optional

from src.mcp.application.dto.business_dtos import (
    BusinessDetailsDTO,
    BusinessDetailsQueryDTO,
    BusinessServiceSummaryDTO,
)
from src.mcp.domain.enums.mcp_enums import RuleType
from src.mcp.domain.exceptions.mcp_exceptions import EntityNotFoundException
from src.mcp.domain.ports.mcp_ports import (
    ICatalogServiceRepository,
    IContractRepository,
    IEstablishmentRepository,
)


class GetBusinessDetailsUseCase:
    """
    Caso de uso: Obtener detalles de un establecimiento (get_business_details).
    Entrega la ficha completa de una sede: ubicación estructurada, contacto,
    reglas de antelación y catálogo de servicios activos.
    """

    def __init__(
        self,
        establishment_repo: IEstablishmentRepository,
        catalog_service_repo: ICatalogServiceRepository,
        contract_repo: Optional[IContractRepository] = None,
    ):
        self._establishment_repo = establishment_repo
        self._catalog_service_repo = catalog_service_repo
        self._contract_repo = contract_repo

    async def execute(self, query: BusinessDetailsQueryDTO) -> BusinessDetailsDTO:
        est = await self._establishment_repo.get_by_id(query.business_id)
        if not est:
            raise EntityNotFoundException(f"Establecimiento con id {query.business_id} no encontrado.")

        services = await self._catalog_service_repo.list_by_establishment(query.business_id)

        service_dtos: list[BusinessServiceSummaryDTO] = []
        for svc in services:
            has_contract = False
            pattern = "slot_object"

            if self._contract_repo:
                active_contract = await self._contract_repo.get_active_by_service_id(svc.id)
                if active_contract:
                    has_contract = True
                    pattern = active_contract.pattern.value

            service_dtos.append(
                BusinessServiceSummaryDTO(
                    id=svc.id,
                    name=svc.name,
                    category=svc.category_name,
                    pattern=pattern,
                    has_active_contract=has_contract,
                )
            )

        # Regla de antelación legible
        advance_rule_text = "Sin restricción especial de antelación."
        if est.rule_type == RuleType.ONLY_TODAY:
            advance_rule_text = "El establecimiento solo permite reservas para el día de hoy."
        elif est.rule_type == RuleType.TODAY_AND_TOMORROW:
            advance_rule_text = "El establecimiento permite reservas únicamente para hoy y mañana."
        elif est.rule_type == RuleType.HOURS_RANGE:
            advance_rule_text = "Reservas sujetas al horario de antelación por horas del establecimiento."

        loc = est.location
        addr_line = f"{loc.street or ''} {loc.building_number or ''}".strip() or None if loc else None
        hours: dict[str, str] = {}
        if est.opening_hour and est.closing_hour:
            hours = {
                "opening": est.opening_hour.strftime("%H:%M"),
                "closing": est.closing_hour.strftime("%H:%M"),
            }

        return BusinessDetailsDTO(
            id=est.id,
            name=est.name,
            code=est.code,
            category=est.category_name,
            city=loc.city if loc else None,
            sector=loc.sector if loc else None,
            address_line=addr_line,
            postal_code=loc.postal_code if loc else None,
            latitude=None,
            longitude=None,
            phone=est.contact.phone if est.contact else None,
            email=est.contact.email if est.contact else None,
            website=est.contact.website if est.contact else None,
            operating_hours=hours,
            rule_type=est.rule_type.value if est.rule_type else "only_today",
            advance_booking_rule=advance_rule_text,
            services=service_dtos,
        )
