from __future__ import annotations

from datetime import date as dt_date
from typing import Any, Optional

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations

from src.mcp.application.dto.availability_dtos import (
    CheckAvailabilityQueryDTO,
    GetOperationResultQueryDTO,
)
from src.mcp.domain.exceptions.mcp_exceptions import ContractValidationException
from src.mcp.presentation.auth_context import extract_user_context
from src.mcp.presentation.dependencies import get_mcp_use_cases
from src.mcp.presentation.error_formatter import handle_mcp_errors


def register_availability_tools(server: MCPServer) -> None:
    """Registra las herramientas de disponibilidad y operaciones diferidas en el servidor MCP."""

    @server.tool(
        name="check_availability",
        title="Consultar Disponibilidad de Servicios",
        description=(
            "Consulta los horarios y slots disponibles para un servicio concreto en Atlas en una fecha dada. "
            "Para servicios estándar (pádel, golf, talleres), retorna slots reales con su 'slot_token' "
            "criptográfico firmado e inmutable, necesario para reservar con 'create_booking_request'. "
            "Para servicios con sistema Queuer, entrega slots estimados identificados claramente. "
            "Para servicios bajo demanda (patrón on_demand_request como veterinaria), indica que no requiere "
            "selección de slot y orienta a llamar directamente a 'create_booking_request' con el formulario."
        ),
        annotations=ToolAnnotations(read_only_hint=True),
    )
    @handle_mcp_errors
    async def check_availability(
        service_id: int,
        date: str,
        filters: Optional[dict[str, Any]] = None,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        user = extract_user_context(ctx, required_scope="bookings:read")

        try:
            target_date = dt_date.fromisoformat(date)
        except ValueError:
            raise ContractValidationException(
                f"Formato de fecha inválido en 'date': '{date}'. Formato requerido: YYYY-MM-DD."
            )

        dto_query = CheckAvailabilityQueryDTO(
            service_id=service_id,
            date=target_date,
            filters=filters or {},
            user_uuid=user.user_uuid,
            user_phone=user.phone_number,
        )

        async with get_mcp_use_cases() as uc:
            res = await uc.check_availability.execute(dto_query)

        return {
            "status": res.status,
            "service_id": res.service_id,
            "operation_id": res.operation_id,
            "slots": [
                {
                    "offer_ref": s.offer_ref,
                    "slot_start": s.slot_start.isoformat(),
                    "slot_end": s.slot_end.isoformat() if s.slot_end else None,
                    "slot_token": s.slot_token,
                    "is_estimated": s.is_estimated,
                    "slot_type": s.slot_type,
                    "notice": s.notice,
                    "price_estimate": {
                        "amount": str(s.price_estimate.amount) if s.price_estimate.amount is not None else None,
                        "unit_amount": str(s.price_estimate.unit_amount) if s.price_estimate.unit_amount is not None else None,
                        "total_amount": str(s.price_estimate.total_amount) if s.price_estimate.total_amount is not None else None,
                        "currency": s.price_estimate.currency,
                        "calculation_basis": s.price_estimate.calculation_basis,
                        "rule_label": s.price_estimate.rule_label,
                        "is_starting_price": s.price_estimate.is_starting_price,
                        "tax_included": s.price_estimate.tax_included,
                        "formatted": s.price_estimate.formatted,
                    }
                    if s.price_estimate
                    else None,
                    "attributes": s.attributes,
                }
                for s in res.slots
            ],
            "applied_filters": res.applied_filters,
            "message": res.message,
        }

    @server.tool(
        name="get_operation_result",
        title="Consultar Resultado de Operación Diferida",
        description=(
            "Recupera el resultado de una consulta diferida de disponibilidad o dimensión cuando "
            "la llamada inicial a check_availability o get_dimension_options retornó status 'processing'. "
            "Requiere el 'operation_id' recibido previamente."
        ),
        annotations=ToolAnnotations(read_only_hint=True),
    )
    @handle_mcp_errors
    async def get_operation_result(
        operation_id: str,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        user = extract_user_context(ctx, required_scope="bookings:read")

        dto_query = GetOperationResultQueryDTO(
            operation_id=operation_id,
            user_uuid=user.user_uuid,
        )

        async with get_mcp_use_cases() as uc:
            res = await uc.get_operation_result.execute(dto_query)

        return {
            "operation_id": res.operation_id,
            "status": res.status,
            "result_type": res.result_type,
            "dimension_options": [
                {
                    "value_key": opt.value_key,
                    "label": opt.label,
                    "description": opt.description,
                    "position": opt.position,
                }
                for opt in res.dimension_options
            ]
            if res.dimension_options
            else [],
            "slots": [
                {
                    "offer_ref": s.offer_ref,
                    "slot_start": s.slot_start.isoformat(),
                    "slot_end": s.slot_end.isoformat() if s.slot_end else None,
                    "slot_token": s.slot_token,
                    "is_estimated": s.is_estimated,
                    "slot_type": s.slot_type,
                    "notice": s.notice,
                    "price_estimate": {
                        "amount": str(s.price_estimate.amount) if s.price_estimate.amount is not None else None,
                        "unit_amount": str(s.price_estimate.unit_amount) if s.price_estimate.unit_amount is not None else None,
                        "total_amount": str(s.price_estimate.total_amount) if s.price_estimate.total_amount is not None else None,
                        "currency": s.price_estimate.currency,
                        "calculation_basis": s.price_estimate.calculation_basis,
                        "rule_label": s.price_estimate.rule_label,
                        "is_starting_price": s.price_estimate.is_starting_price,
                        "tax_included": s.price_estimate.tax_included,
                        "formatted": s.price_estimate.formatted,
                    }
                    if s.price_estimate
                    else None,
                    "attributes": s.attributes,
                }
                for s in res.slots
            ]
            if res.slots
            else [],
            "error_message": res.error_message,
            "retry_after_seconds": res.retry_after_seconds,
        }
