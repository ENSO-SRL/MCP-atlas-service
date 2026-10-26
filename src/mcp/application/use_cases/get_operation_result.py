from __future__ import annotations

from typing import Optional

from src.mcp.application.dto.availability_dtos import (
    AvailableSlotDTO,
    GetOperationResultQueryDTO,
    OperationResultResponseDTO,
)
from src.mcp.application.dto.contract_dtos import DimensionOptionDTO
from src.mcp.application.use_cases.check_availability import process_raw_slots
from src.mcp.domain.ports.mcp_ports import (
    IContractRepository,
    IHoldManager,
    IRedisBusClient,
)
from src.mcp.infrastructure.security.slot_token_codec import SlotTokenCodec


class GetOperationResultUseCase:
    """
    Caso de uso: Consultar resultado de una operación asíncrona diferida (get_operation_result).
    Utilizado por Claude cuando una consulta de disponibilidad o de opciones de dimensión
    superó la espera superficial de 2 segundos.
    
    Aprovecha el mecanismo defensivo de 'Lazy-Sync' implementado en RedisBusClient,
    evalúa holds en tiempo real y acuña los tokens criptográficos de slots para el usuario.
    """

    def __init__(
        self,
        bus_client: IRedisBusClient,
        contract_repo: IContractRepository,
        hold_manager: IHoldManager,
        token_codec: SlotTokenCodec,
    ):
        self._bus_client = bus_client
        self._contract_repo = contract_repo
        self._hold_manager = hold_manager
        self._token_codec = token_codec

    async def execute(self, query: GetOperationResultQueryDTO) -> OperationResultResponseDTO:
        # 1. Consultar resultado con Lazy-Sync
        raw_result = await self._bus_client.get_operation_result(query.operation_id)
        if raw_result is None:
            return OperationResultResponseDTO(
                status="failed",
                operation_id=query.operation_id,
                error_message=f"La operación diferida '{query.operation_id}' no existe o ha expirado.",
            )

        status = raw_result.get("status", "processing")

        # 2. Si sigue en proceso
        if status == "processing":
            return OperationResultResponseDTO(
                status="processing",
                operation_id=query.operation_id,
                retry_after_seconds=2,
            )

        # 3. Si falló upstream
        if status == "failed":
            return OperationResultResponseDTO(
                status="failed",
                operation_id=query.operation_id,
                error_message=raw_result.get(
                    "error", "La operación falló durante el procesamiento en el backend externo."
                ),
            )

        # 4. Operación completada: determinar si fue de dimensión o de disponibilidad
        if "options" in raw_result:
            # Resultado de dimensión dependiente
            raw_options = raw_result.get("options", [])
            options = [
                DimensionOptionDTO(
                    value_key=opt.get("value_key") or opt.get("key", ""),
                    label=opt.get("label", ""),
                    description=opt.get("description"),
                    position=opt.get("position", 0),
                )
                for opt in raw_options
            ]
            return OperationResultResponseDTO(
                status="completed",
                operation_id=query.operation_id,
                result_type="dimension_options",
                dimension_options=options,
            )

        if "slots" in raw_result:
            # Resultado de disponibilidad
            service_id = int(raw_result.get("service_id", 0))
            contract = await self._contract_repo.get_active_by_service_id(service_id)
            if not contract:
                return OperationResultResponseDTO(
                    status="failed",
                    operation_id=query.operation_id,
                    error_message=f"No se encontró un contrato activo para el servicio {service_id}.",
                )

            applied_filters = raw_result.get("filters", {})
            party_size = int(raw_result.get("party_size", 1))
            raw_slots = raw_result.get("slots", [])

            price_rules = await self._contract_repo.list_price_rules_for_service(service_id)
            slots = await process_raw_slots(
                raw_slots=raw_slots,
                service_id=service_id,
                contract=contract,
                user_uuid=query.user_uuid,
                applied_filters=applied_filters,
                party_size=party_size,
                hold_manager=self._hold_manager,
                token_codec=self._token_codec,
                price_rules=price_rules,
            )

            return OperationResultResponseDTO(
                status="completed",
                operation_id=query.operation_id,
                result_type="availability",
                slots=slots,
            )

        # Resultado completado sin formato reconocido
        return OperationResultResponseDTO(
            status="completed",
            operation_id=query.operation_id,
            result_type="unknown",
        )
