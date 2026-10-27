from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations

from src.mcp.application.dto.booking_dtos import (
    CancelBookingInputDTO,
    CreateBookingInputDTO,
    GetBookingStatusQueryDTO,
    ListMyBookingsQueryDTO,
)
from src.mcp.domain.exceptions.mcp_exceptions import ContractValidationException
from src.mcp.presentation.auth_context import extract_user_context
from src.mcp.presentation.dependencies import get_mcp_use_cases
from src.mcp.presentation.error_formatter import handle_mcp_errors


def register_booking_tools(server: MCPServer) -> None:
    """Registra las herramientas del ciclo de vida de reservas en el servidor MCP."""

    @server.tool(
        name="create_booking_request",
        title="Crear Solicitud de Reserva",
        description=(
            "Solicita una reserva en Atlas. Operación asíncrona, no destructiva e idempotente. "
            "Para servicios estándar o con Queuer, exige un 'slot_token' obtenido previamente de check_availability. "
            "Para servicios bajo demanda (patrón on_demand_request como veterinaria o cotizaciones), se omite "
            "'slot_token' y se debe proporcionar 'service_id'. "
            "Los campos del formulario ('fields') deben validar contra el JSON Schema de booking_fields del contrato. "
            "Exige 'idempotency_key' para prevenir reservas duplicadas ante reintentos."
        ),
        annotations=ToolAnnotations(idempotent_hint=True, destructive_hint=False),
    )
    @handle_mcp_errors
    async def create_booking_request(
        idempotency_key: str,
        slot_token: Optional[str] = None,
        service_id: Optional[int] = None,
        fields: Optional[dict[str, Any]] = None,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        user_uuid = extract_user_context(ctx, required_scope="bookings:write")

        dto_input = CreateBookingInputDTO(
            user_uuid=user_uuid,
            idempotency_key=idempotency_key,
            slot_token=slot_token,
            service_id=service_id,
            fields=fields or {},
        )

        async with get_mcp_use_cases() as uc:
            res = await uc.create_booking_request.execute(dto_input)

        return {
            "booking_id": str(res.booking_id),
            "status": res.status,
            "service_id": res.service_id,
            "slot_start": res.slot_start.isoformat() if res.slot_start else None,
            "slot_end": res.slot_end.isoformat() if res.slot_end else None,
            "is_estimated": res.is_estimated,
            "applied_filters": res.applied_filters,
            "status_reason": res.status_reason,
            "external_ref": res.external_ref,
            "expires_at": res.expires_at.isoformat() if res.expires_at else None,
            "message": res.message,
        }

    @server.tool(
        name="get_booking_status",
        title="Consultar Estado de Reserva",
        description=(
            "Consulta el estado y trazabilidad en tiempo real de una reserva en Atlas. "
            "Garantiza aislamiento estricto por usuario y devuelve una explicación humana del estado "
            "(requested: en trámite inicial; accepted: en cola del Queuer; confirmed: con localizador; "
            "rejected/failed: con motivo; cancel_requested: cancelación en trámite)."
        ),
        annotations=ToolAnnotations(read_only_hint=True),
    )
    @handle_mcp_errors
    async def get_booking_status(
        booking_id: str,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        user_uuid = extract_user_context(ctx, required_scope="bookings:read")

        try:
            b_uuid = UUID(booking_id)
        except ValueError:
            raise ContractValidationException(f"El identificador 'booking_id' '{booking_id}' no es un UUID válido.")

        dto_query = GetBookingStatusQueryDTO(booking_id=b_uuid, user_uuid=user_uuid)

        async with get_mcp_use_cases() as uc:
            res = await uc.get_booking_status.execute(dto_query)

        return {
            "booking_id": str(res.booking_id),
            "user_uuid": str(res.user_uuid),
            "service_id": res.service_id,
            "status": res.status,
            "service_name": res.service_name,
            "establishment_name": res.establishment_name,
            "status_reason": res.status_reason,
            "slot_start": res.slot_start.isoformat() if res.slot_start else None,
            "slot_end": res.slot_end.isoformat() if res.slot_end else None,
            "resource_ref": res.resource_ref,
            "applied_filters": res.applied_filters,
            "fields": res.fields,
            "price_estimate": res.price_estimate,
            "external_ref": res.external_ref,
            "assigned_details": res.assigned_details,
            "expires_at": res.expires_at.isoformat() if res.expires_at else None,
            "created_at": res.created_at.isoformat(),
            "updated_at": res.updated_at.isoformat(),
            "explanation": res.explanation,
        }

    @server.tool(
        name="list_my_bookings",
        title="Listar Mis Reservas",
        description=(
            "Lista el historial paginado de solicitudes y reservas del usuario autenticado. "
            "Permite filtrar por estado (requested, accepted, confirmed, rejected, failed, expired, "
            "cancel_requested, cancelled). Preserva los applied_filters y resuelve nombres de servicios."
        ),
        annotations=ToolAnnotations(read_only_hint=True),
    )
    @handle_mcp_errors
    async def list_my_bookings(
        status_filter: Optional[str] = None,
        cursor: int = 0,
        limit: int = 10,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        user_uuid = extract_user_context(ctx, required_scope="bookings:read")

        dto_query = ListMyBookingsQueryDTO(
            user_uuid=user_uuid,
            status_filter=status_filter,
            cursor=cursor,
            limit=limit,
        )

        async with get_mcp_use_cases() as uc:
            res = await uc.list_my_bookings.execute(dto_query)

        return {
            "items": [
                {
                    "booking_id": str(item.booking_id),
                    "service_id": item.service_id,
                    "status": item.status,
                    "service_name": item.service_name,
                    "slot_start": item.slot_start.isoformat() if item.slot_start else None,
                    "slot_end": item.slot_end.isoformat() if item.slot_end else None,
                    "applied_filters": item.applied_filters,
                    "external_ref": item.external_ref,
                    "created_at": item.created_at.isoformat(),
                }
                for item in res.items
            ],
            "next_cursor": res.next_cursor,
            "total_count": res.total_count,
        }

    @server.tool(
        name="cancel_booking",
        title="Cancelar Reserva",
        description=(
            "Solicita la cancelación de una reserva activa en Atlas. Operación destructiva que requiere "
            "confirmación previa del usuario en el chat. Válida únicamente para reservas en estado "
            "requested, accepted o confirmed."
        ),
        annotations=ToolAnnotations(destructive_hint=True),
    )
    @handle_mcp_errors
    async def cancel_booking(
        booking_id: str,
        reason: Optional[str] = None,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        user_uuid = extract_user_context(ctx, required_scope="bookings:write")

        try:
            b_uuid = UUID(booking_id)
        except ValueError:
            raise ContractValidationException(f"El identificador 'booking_id' '{booking_id}' no es un UUID válido.")

        dto_input = CancelBookingInputDTO(
            booking_id=b_uuid,
            user_uuid=user_uuid,
            reason=reason,
        )

        async with get_mcp_use_cases() as uc:
            res = await uc.cancel_booking.execute(dto_input)

        return {
            "booking_id": str(res.booking_id),
            "status": res.status,
            "message": res.message,
        }
