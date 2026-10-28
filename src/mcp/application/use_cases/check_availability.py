from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from src.mcp.application.dto.availability_dtos import (
    AvailabilityResponseDTO,
    AvailableSlotDTO,
    CheckAvailabilityQueryDTO,
    SlotPriceEstimateDTO,
)
from src.mcp.domain.entities.contract_entities import ServiceContractVersion
from src.mcp.domain.entities.service_price_rule import ServicePriceRule
from src.mcp.domain.enums.mcp_enums import AvailabilityPattern
from src.mcp.domain.exceptions.mcp_exceptions import (
    BookingRuleViolationException,
    EntityNotFoundException,
)
from src.mcp.domain.ports.mcp_ports import (
    ICatalogServiceRepository,
    IContractRepository,
    IEstablishmentRepository,
    IHoldManager,
    IRedisBusClient,
)
from src.mcp.domain.value_objects.canonical_filter_hash import CanonicalFilterHash
from src.mcp.infrastructure.redis.redis_cache_manager import RedisAvailabilityCache
from src.mcp.infrastructure.security.slot_token_codec import SlotTokenCodec


async def process_raw_slots(
    raw_slots: list[dict[str, Any]],
    service_id: int,
    contract: ServiceContractVersion,
    user_uuid: UUID,
    applied_filters: dict[str, Any],
    party_size: int,
    hold_manager: IHoldManager,
    token_codec: SlotTokenCodec,
    price_rules: list[ServicePriceRule],
) -> list[AvailableSlotDTO]:
    """
    Procesa slots crudos:
    1. Descarta o filtra slots bloqueados con hold atómico activo en Redis.
    2. Evalúa reglas de tarifas aplicables para el horario y personas.
    3. Acuña tokens criptográficos firmados (SlotToken) vinculados estrictamente al user_uuid.
    4. Detecta y marca slots estimados del sistema Queuer.
    """
    contract_version_label = (
        f"{contract.published_at.strftime('%Y-%m-%d') if contract.published_at else 'v'}.{contract.version_no}"
    )
    available_slots: list[AvailableSlotDTO] = []

    for item in raw_slots:
        offer_ref = item["offer_ref"]

        # 1. Filtrado de holds en Redis
        if await hold_manager.is_held(offer_ref):
            continue

        # 2. Fechas de inicio y fin
        raw_start = item["slot_start"]
        slot_start = (
            datetime.fromisoformat(raw_start)
            if isinstance(raw_start, str)
            else raw_start
        )
        raw_end = item.get("slot_end")
        slot_end = (
            datetime.fromisoformat(raw_end)
            if isinstance(raw_end, str)
            else raw_end
        )

        is_estimated = bool(item.get("is_estimated", False))
        slot_type = "estimated" if is_estimated else "official"
        notice = item.get("notice")
        if is_estimated and not notice:
            notice = (
                "Horario estimado no oficial. Al reservar, el sistema Queuer capturará "
                "automáticamente el horario cuando el club lo publique el día previo."
            )

        # 3. Estimación de precio
        price_dto: Optional[SlotPriceEstimateDTO] = None
        for rule in sorted(price_rules, key=lambda r: r.priority, reverse=True):
            if rule.is_applicable(slot_start, party_size=party_size):
                estimate = rule.calculate_estimate(party_size=party_size)
                price_dto = SlotPriceEstimateDTO(
                    amount=estimate.amount,
                    currency=estimate.currency,
                    calculation_basis=estimate.basis.value,
                    is_starting_price=rule.is_starting_price,
                    rule_label=rule.label,
                    formatted=f"{estimate.amount:.2f} {estimate.currency}",
                )
                break

        # 4. Acuñación del SlotToken criptográfico
        token_id = f"tok_{uuid4().hex[:12]}"
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=contract.request_ttl_seconds)

        slot_token = token_codec.encode(
            token_id=token_id,
            user_uuid=user_uuid,
            offer_ref=offer_ref,
            service_id=service_id,
            slot_start=slot_start,
            slot_end=slot_end,
            contract_version=contract_version_label,
            expires_at=expires_at,
            applied_filters=applied_filters,
            is_estimated=is_estimated,
        )

        available_slots.append(
            AvailableSlotDTO(
                slot_start=slot_start,
                slot_end=slot_end,
                resource_ref=item.get("resource_ref"),
                resource_name=item.get("resource_name"),
                offer_ref=offer_ref,
                slot_token=slot_token.raw_token,
                is_estimated=is_estimated,
                slot_type=slot_type,
                notice=notice,
                price_estimate=price_dto,
                attributes=item.get("attributes", {}),
            )
        )

    return available_slots


class CheckAvailabilityUseCase:
    """
    Caso de uso: Consultar disponibilidad de slots (check_availability).
    Implementa:
    1. Verificación de reglas de antelación del club (rule_type).
    2. Identificación de patrones ON_DEMAND_REQUEST (veterinarias/formularios sin slots).
    3. Caché canónica determinista (CanonicalFilterHash en Redis).
    4. Fallback RPC asíncrono con espera superficial (2s).
    5. Exclusión de holds atómicos tomados en tiempo real.
    6. Estimación dinámica de tarifas y acuñación de tokens criptográficos sellados para Claude.
    """

    def __init__(
        self,
        establishment_repo: IEstablishmentRepository,
        catalog_service_repo: ICatalogServiceRepository,
        contract_repo: IContractRepository,
        avail_cache: RedisAvailabilityCache,
        hold_manager: IHoldManager,
        bus_client: IRedisBusClient,
        token_codec: SlotTokenCodec,
    ):
        self._establishment_repo = establishment_repo
        self._catalog_service_repo = catalog_service_repo
        self._contract_repo = contract_repo
        self._avail_cache = avail_cache
        self._hold_manager = hold_manager
        self._bus_client = bus_client
        self._token_codec = token_codec

    async def execute(self, query: CheckAvailabilityQueryDTO) -> AvailabilityResponseDTO:
        # 1. Obtener servicio y contrato activo
        svc = await self._catalog_service_repo.get_by_id(query.service_id)
        if not svc:
            raise EntityNotFoundException(f"Servicio con id {query.service_id} no encontrado.")

        contract = await self._contract_repo.get_active_by_service_id(query.service_id)
        if not contract:
            raise EntityNotFoundException(
                f"El servicio '{svc.name}' (id: {query.service_id}) no tiene contrato activo publicado."
            )

        # 2. Servicios ON_DEMAND (Veterinaria / Citas sin slots)
        if contract.pattern == AvailabilityPattern.ON_DEMAND_REQUEST:
            return AvailabilityResponseDTO(
                status="completed",
                service_id=query.service_id,
                slots=[],
                applied_filters=query.filters,
                message=(
                    f"El servicio '{svc.name}' funciona bajo demanda mediante solicitud/formulario (sin slots fijos). "
                    "Puedes proceder directamente a reservar con 'create_booking_request' enviando los campos requeridos."
                ),
            )

        # 3. Validación de antelación según políticas del establecimiento
        est = await self._establishment_repo.get_by_id(svc.establishment_id)
        if est and not est.is_date_allowed(query.date):
            rule_name = est.rule_type.value if est.rule_type else "política de antelación"
            raise BookingRuleViolationException(
                f"La fecha consultada ({query.date}) no está permitida por el establecimiento "
                f"según su regla operativa ({rule_name})."
            )

        # 4. Cálculo de hash determinista canónico
        contract_version_label = (
            f"{contract.published_at.strftime('%Y-%m-%d') if contract.published_at else 'v'}.{contract.version_no}"
        )
        search_context = {
            "date": query.date.isoformat(),
            "party_size": query.party_size,
            **query.filters,
        }
        filter_hash = CanonicalFilterHash.from_filters(search_context).hash_value

        # 5. Fast-Path: Consulta en RedisAvailabilityCache
        cached_data = await self._avail_cache.get(
            query.service_id, contract_version_label, filter_hash
        )
        raw_slots: Optional[list[dict[str, Any]]] = None

        if cached_data is not None:
            raw_slots = cached_data.get("slots", [])
        else:
            # 6. Cache MISS: Publicar petición en bus RPC sobre Redis
            operation_id = f"op_avail_{uuid4().hex[:12]}"
            bus_payload = {
                "service_id": query.service_id,
                "combo_code": svc.combo_code if svc else None,
                "user_uuid": str(query.user_uuid),
                "user_phone": query.user_phone,
                "date": query.date.isoformat(),
                "filters": query.filters,
                "party_size": query.party_size,
                "contract_version": contract_version_label,
                "filter_hash": filter_hash,
            }
            await self._bus_client.publish_availability_request(operation_id, bus_payload)

            # Espera superficial no bloqueante (2 segundos)
            response_key = f"resp:{operation_id}"
            immediate_result = await self._bus_client.wait_for_response(response_key, timeout_seconds=2.0)

            if immediate_result is not None:
                raw_slots = immediate_result.get("slots", [])
                await self._avail_cache.set(
                    query.service_id,
                    contract_version_label,
                    filter_hash,
                    {"slots": raw_slots},
                )
            else:
                # Superó los 2 segundos: polling diferido
                return AvailabilityResponseDTO(
                    status="processing",
                    service_id=query.service_id,
                    slots=[],
                    operation_id=operation_id,
                    applied_filters=query.filters,
                    filter_hash=filter_hash,
                    message=(
                        "La consulta de disponibilidad está tardando más de lo habitual y continúa procesándose en segundo plano. "
                        "Usa la herramienta 'get_operation_result' con el operation_id para consultar el resultado."
                    ),
                )

        # 7. Procesamiento de slots: filtrado de holds, precios y tokens criptográficos
        price_rules = await self._contract_repo.list_price_rules_for_service(query.service_id)
        slots = await process_raw_slots(
            raw_slots=raw_slots or [],
            service_id=query.service_id,
            contract=contract,
            user_uuid=query.user_uuid,
            applied_filters=query.filters,
            party_size=query.party_size,
            hold_manager=self._hold_manager,
            token_codec=self._token_codec,
            price_rules=price_rules,
        )

        return AvailabilityResponseDTO(
            status="completed",
            service_id=query.service_id,
            slots=slots,
            applied_filters=query.filters,
            filter_hash=filter_hash,
        )
