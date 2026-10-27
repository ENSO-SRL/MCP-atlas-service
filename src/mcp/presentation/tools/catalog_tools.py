from __future__ import annotations

from typing import Any, Optional

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations

from src.mcp.application.dto.business_dtos import (
    BusinessDetailsQueryDTO,
    SearchBusinessesQueryDTO,
)
from src.mcp.application.dto.contract_dtos import (
    GetDimensionOptionsQueryDTO,
    GetServiceContractQueryDTO,
)
from src.mcp.presentation.auth_context import extract_user_context
from src.mcp.presentation.dependencies import get_mcp_use_cases
from src.mcp.presentation.error_formatter import handle_mcp_errors


def register_catalog_tools(server: MCPServer) -> None:
    """Registra las herramientas de catálogo e inspección de contratos en el servidor MCP."""

    @server.tool(
        name="search_businesses",
        title="Buscar Establecimientos",
        description=(
            "Busca establecimientos y clubes disponibles en la plataforma Atlas. "
            "Permite filtrar por término de búsqueda (nombre o zona), categoría (Pádel, Golf, Veterinaria, "
            "Taller, Cine) y ciudad. Retorna listado paginado con identificadores de negocio (business_id)."
        ),
        annotations=ToolAnnotations(read_only_hint=True),
    )
    @handle_mcp_errors
    async def search_businesses(
        query: Optional[str] = None,
        category_name: Optional[str] = None,
        city: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        extract_user_context(ctx, required_scope="bookings:read")

        dto_query = SearchBusinessesQueryDTO(
            query=query,
            category=category_name,
            zone=city,
            cursor=offset,
            limit=limit,
        )

        async with get_mcp_use_cases() as uc:
            res = await uc.search_businesses.execute(dto_query)

        return {
            "items": [
                {
                    "business_id": item.id,
                    "name": item.name,
                    "code": item.code,
                    "category": item.category,
                    "city": item.city,
                    "sector": item.sector,
                    "operating_hours": item.operating_hours,
                    "rule_type": item.rule_type,
                }
                for item in res.items
            ],
            "total_count": res.total_count,
            "next_cursor": res.next_cursor,
        }

    @server.tool(
        name="get_business_details",
        title="Obtener Detalles del Negocio",
        description=(
            "Obtiene la ficha informativa completa de un establecimiento en Atlas a partir de su business_id. "
            "Devuelve ubicación física, horarios de apertura y cierre, regla de antelación para reservas, "
            "lista de servicios ofrecidos (service_id, nombre y categoría) y tarifas orientativas."
        ),
        annotations=ToolAnnotations(read_only_hint=True),
    )
    @handle_mcp_errors
    async def get_business_details(
        business_id: int,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        extract_user_context(ctx, required_scope="bookings:read")

        dto_query = BusinessDetailsQueryDTO(business_id=business_id)

        async with get_mcp_use_cases() as uc:
            res = await uc.get_business_details.execute(dto_query)

        return {
            "business_id": res.id,
            "name": res.name,
            "code": res.code,
            "category": res.category,
            "location": {
                "city": res.city,
                "sector": res.sector,
                "address_line": res.address_line,
            },
            "operating_hours": res.operating_hours,
            "rule_type": res.rule_type,
            "advance_booking_rule": res.advance_booking_rule,
            "services": [
                {
                    "service_id": s.id,
                    "name": s.name,
                    "category": s.category,
                    "pattern": s.pattern,
                    "has_active_contract": s.has_active_contract,
                }
                for s in res.services
            ],
            "phone": res.phone,
            "email": res.email,
            "website": res.website,
        }

    @server.tool(
        name="get_service_contract",
        title="Obtener Contrato del Servicio",
        description=(
            "Recupera el contrato dinámico autodescriptivo para un service_id específico. "
            "El contrato define el patrón de disponibilidad (slot_object, on_demand_request, etc.), "
            "las dimensiones de filtrado (availability_dimensions) y el esquema JSON de campos de reserva "
            "(booking_fields). Es la fuente de verdad antes de consultar disponibilidad o reservar."
        ),
        annotations=ToolAnnotations(read_only_hint=True),
    )
    @handle_mcp_errors
    async def get_service_contract(
        service_id: int,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        extract_user_context(ctx, required_scope="bookings:read")

        dto_query = GetServiceContractQueryDTO(service_id=service_id)

        async with get_mcp_use_cases() as uc:
            res = await uc.get_service_contract.execute(dto_query)

        return {
            "service_id": res.service_id,
            "pattern": res.pattern,
            "contract_version": res.contract_version,
            "contract_version_id": str(res.contract_version_id),
            "request_expires_in_seconds": res.request_expires_in_seconds,
            "booking_fields": res.booking_fields,
            "availability_dimensions": [
                {
                    "key": d.key,
                    "label": d.label,
                    "description": d.description,
                    "values_source": d.values_source,
                    "apply_mode": d.apply_mode,
                    "depends_on": d.depends_on,
                    "allows_any": d.allows_any,
                    "required": d.required,
                    "reports_counts": d.reports_counts,
                    "values": [
                        {
                            "value_key": opt.value_key,
                            "label": opt.label,
                            "description": opt.description,
                            "position": opt.position,
                        }
                        for opt in (d.values or [])
                    ],
                }
                for d in res.availability_dimensions
            ],
            "payment_policy": res.payment_policy,
            "cancellation_policy": res.cancellation_policy,
        }

    @server.tool(
        name="get_dimension_options",
        title="Consultar Opciones de Dimensión",
        description=(
            "Explora las opciones disponibles para una dimensión de servicio cuyo values_source es separate_query. "
            "Requiere proporcionar el service_id, la dimension_key (ej. 'mechanic' o 'court_surface') y el contexto "
            "de dimensiones previas fijadas (ej. {'date': '2026-10-28'})."
        ),
        annotations=ToolAnnotations(read_only_hint=True),
    )
    @handle_mcp_errors
    async def get_dimension_options(
        service_id: int,
        dimension_key: str,
        context: Optional[dict[str, Any]] = None,
        ctx: Optional[Context] = None,
    ) -> dict[str, Any]:
        extract_user_context(ctx, required_scope="bookings:read")

        dto_query = GetDimensionOptionsQueryDTO(
            service_id=service_id,
            dimension_key=dimension_key,
            context=context or {},
        )

        async with get_mcp_use_cases() as uc:
            res = await uc.get_dimension_options.execute(dto_query)

        return {
            "status": res.status,
            "dimension_key": res.dimension_key,
            "options": [
                {
                    "value_key": opt.value_key,
                    "label": opt.label,
                    "description": opt.description,
                    "position": opt.position,
                }
                for opt in res.options
            ],
            "operation_id": res.operation_id,
            "context_hash": res.context_hash,
            "expires_in_seconds": res.expires_in_seconds,
        }
