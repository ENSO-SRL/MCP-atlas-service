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


def _format_advance_rule_text(rule_type: Optional[RuleType]) -> str:
    if rule_type == RuleType.ONLY_TODAY:
        return "El establecimiento solo permite reservas para el día de hoy."
    elif rule_type == RuleType.TODAY_AND_TOMORROW:
        return "El establecimiento permite reservas únicamente para hoy y mañana."
    elif rule_type == RuleType.HOURS_RANGE:
        return "Reservas sujetas al horario de antelación por horas del establecimiento."
    return "Sin restricción especial de antelación."


class GetBusinessDetailsUseCase:
    """
    Caso de uso: Obtener detalles de un establecimiento (get_business_details).
    Entrega la ficha completa de una sede: ubicación estructurada, contacto,
    reglas de antelación y catálogo de servicios activos.

    Soporta establecimientos físicos modelados como servicios de pasarela (is_service=True):
    - Recupera contacto y dirección física del propio servicio.
    - Recupera reglas técnicas (rule_type, horarios, pasarela) del establecimiento pasarela padre.
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
        # Flujo 1: El negocio solicitado es físicamente un servicio gestionado vía pasarela
        if query.is_service:
            return await self._execute_for_service(query.business_id)

        # Flujo 2: Establecimiento tradicional
        return await self._execute_for_establishment(query.business_id)

    async def _execute_for_service(self, service_id: int) -> BusinessDetailsDTO:
        svc = await self._catalog_service_repo.get_by_id(service_id)
        if not svc:
            raise EntityNotFoundException(f"Servicio físico con id {service_id} no encontrado.")

        est = await self._establishment_repo.get_by_id(svc.establishment_id)
        if not est:
            raise EntityNotFoundException(
                f"Establecimiento pasarela con id {svc.establishment_id} no encontrado para el servicio {svc.id}."
            )

        # Dirección y contacto: del servicio físico (con fallback a la pasarela padre)
        loc = svc.location
        addr_line = f"{loc.street or ''} {loc.building_number or ''}".strip() or None if loc else None
        if not addr_line and est.location:
            gloc = est.location
            addr_line = f"{gloc.street or ''} {gloc.building_number or ''}".strip() or None

        city = (loc.city if loc else None) or (est.location.city if est.location else None)
        sector = (loc.sector if loc else None) or (est.location.sector if est.location else None)
        postal_code = (loc.postal_code if loc else None) or (est.location.postal_code if est.location else None)

        contact = svc.contact
        phone = (contact.phone if contact else None) or (est.contact.phone if est.contact else None)
        email = (contact.email if contact else None) or (est.contact.email if est.contact else None)
        website = (contact.website if contact else None) or (est.contact.website if est.contact else None)

        # Horarios y reglas técnicas operativas provienen de la pasarela padre
        hours: dict[str, str] = {}
        if est.opening_hour and est.closing_hour:
            hours = {
                "opening": est.opening_hour.strftime("%H:%M"),
                "closing": est.closing_hour.strftime("%H:%M"),
            }

        rule_type_val = est.rule_type.value if est.rule_type else "only_today"
        advance_rule_text = _format_advance_rule_text(est.rule_type)

        # Para un servicio físico, su catálogo ofrecido es él mismo
        has_contract = False
        pattern = "slot_object"
        if self._contract_repo:
            active_contract = await self._contract_repo.get_active_by_service_id(svc.id)
            if active_contract:
                has_contract = True
                pattern = active_contract.pattern.value

        service_dtos = [
            BusinessServiceSummaryDTO(
                id=svc.id,
                name=svc.name,
                category=svc.category_name,
                pattern=pattern,
                has_active_contract=has_contract,
            )
        ]

        return BusinessDetailsDTO(
            id=svc.id,
            name=svc.name,
            code=svc.combo_code or f"SVC-{svc.id}",
            category=svc.category_name,
            city=city,
            sector=sector,
            address_line=addr_line,
            postal_code=postal_code,
            latitude=None,
            longitude=None,
            phone=phone,
            email=email,
            website=website,
            operating_hours=hours,
            rule_type=rule_type_val,
            advance_booking_rule=advance_rule_text,
            services=service_dtos,
            is_service=True,
        )

    async def _execute_for_establishment(self, establishment_id: int) -> BusinessDetailsDTO:
        est = await self._establishment_repo.get_by_id(establishment_id)
        if not est:
            raise EntityNotFoundException(f"Establecimiento con id {establishment_id} no encontrado.")

        services = await self._catalog_service_repo.list_by_establishment(establishment_id)

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

        advance_rule_text = _format_advance_rule_text(est.rule_type)

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
            is_service=False,
        )
