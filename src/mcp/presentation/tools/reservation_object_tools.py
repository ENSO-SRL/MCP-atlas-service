from __future__ import annotations

from typing import Any, Optional

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations

from src.mcp.application.dto.reservation_object_dtos import (
    GetReservationObjectSchemasQueryDTO,
    GetUserReservationObjectsQueryDTO,
)
from src.mcp.presentation.auth_context import extract_user_context
from src.mcp.presentation.dependencies import get_mcp_use_cases
from src.mcp.presentation.error_formatter import handle_mcp_errors


def register_reservation_object_tools(server: MCPServer) -> None:
    """Registra las herramientas para inspección de esquemas y objetos de reserva persistentes."""

    @server.tool(
        name="get_reservation_object_schemas",
        title="Consultar Esquemas de Objetos de Reserva",
        description=(
            "Obtiene los esquemas de objetos de reserva persistentes asociados a un servicio en Atlas "
            "(ej. vehículos para talleres mecánicos, o perfiles clínicos para veterinarias/médicos). "
            "Devuelve la definición de campos requeridos, tipos de datos y banderas de alta variación "
            "(como kilometraje) para saber qué campos solicitar o validar con el usuario antes de reservar."
        ),
        annotations=ToolAnnotations(read_only_hint=True),
    )
    @handle_mcp_errors
    async def get_reservation_object_schemas(
        service_id: int,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        extract_user_context(ctx, required_scope="bookings:read")

        dto_query = GetReservationObjectSchemasQueryDTO(service_id=service_id)

        async with get_mcp_use_cases() as uc:
            res = await uc.get_reservation_object_schemas.execute(dto_query)

        return {
            "service_id": res.service_id,
            "schemas": [
                {
                    "schema_id": s.schema_id,
                    "schema_header": s.schema_header,
                    "section_name": s.section_name,
                    "establishment_id": s.establishment_id,
                    "schema_fields": [
                        {
                            "field_name": f.field_name,
                            "data_type": f.data_type,
                            "is_required": f.is_required,
                            "high_variance_flag": f.high_variance_flag,
                            "description": f.description,
                            "validation_rules": f.validation_rules,
                        }
                        for f in s.schema_fields
                    ],
                }
                for s in res.schemas
            ],
        }

    @server.tool(
        name="get_user_reservation_objects",
        title="Consultar Mis Objetos Guardados",
        description=(
            "Consulta los objetos de reserva persistentes (ej. vehículos guardados) que el usuario autenticado "
            "tiene registrados en Atlas para un esquema específico (ej. 'vvautos_taller:vehiculo'). "
            "Retorna los identificadores (object_id), alias descriptivos y datos actuales de cada objeto "
            "para permitir reutilizarlos o actualizarlos bajo el patrón Resolve or Create al enviar la reserva."
        ),
        annotations=ToolAnnotations(read_only_hint=True),
    )
    @handle_mcp_errors
    async def get_user_reservation_objects(
        schema_header: str,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        user = extract_user_context(ctx, required_scope="bookings:read")

        dto_query = GetUserReservationObjectsQueryDTO(
            schema_header=schema_header,
            user_uuid=user.user_uuid,
            user_phone=user.phone_number,
        )

        async with get_mcp_use_cases() as uc:
            res = await uc.get_user_reservation_objects.execute(dto_query)

        return {
            "schema_header": res.schema_header,
            "section_name": res.section_name,
            "user_phone": res.user_phone,
            "objects": [
                {
                    "id": obj.id,
                    "schema_id": obj.schema_id,
                    "object_alias": obj.object_alias,
                    "payload": obj.payload,
                    "created_at": obj.created_at,
                    "updated_at": obj.updated_at,
                }
                for obj in res.objects
            ],
        }

