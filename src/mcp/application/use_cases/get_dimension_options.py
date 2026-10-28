from __future__ import annotations

from typing import Optional
from uuid import uuid4

from src.mcp.application.dto.contract_dtos import (
    DimensionOptionDTO,
    DimensionOptionsResponseDTO,
    GetDimensionOptionsQueryDTO,
)
from src.mcp.domain.enums.mcp_enums import DimensionValuesSource
from src.mcp.domain.exceptions.mcp_exceptions import (
    EntityNotFoundException,
    MissingDimensionDependencyException,
)
from src.mcp.domain.ports.mcp_ports import (
    ICatalogServiceRepository,
    IContractRepository,
    IRedisBusClient,
)
from src.mcp.infrastructure.redis.redis_cache_manager import RedisDimensionOptionsCache


class GetDimensionOptionsUseCase:
    """
    Caso de uso: Resolver opciones dinámicas para dimensiones de consulta separada (get_dimension_options).
    Implementa:
    1. Fast-Path: Consulta en RedisDimensionOptionsCache mediante SHA-256 del contexto (< 5ms).
    2. Fallback: RPC asíncrono sobre 'queue:dim:requests' con espera superficial (2s).
       - Si responde a tiempo: puebla la caché y retorna las opciones.
       - Si vence la espera: retorna status='processing' y operation_id para polling posterior.
    """

    def __init__(
        self,
        contract_repo: IContractRepository,
        dim_cache: RedisDimensionOptionsCache,
        bus_client: IRedisBusClient,
        catalog_repo: Optional[ICatalogServiceRepository] = None,
    ):
        self._contract_repo = contract_repo
        self._dim_cache = dim_cache
        self._bus_client = bus_client
        self._catalog_repo = catalog_repo

    async def execute(self, query: GetDimensionOptionsQueryDTO) -> DimensionOptionsResponseDTO:
        # 1. Obtener contrato activo
        contract = await self._contract_repo.get_active_by_service_id(query.service_id)
        if not contract:
            raise EntityNotFoundException(
                f"Contrato no encontrado para el servicio con id {query.service_id}."
            )

        # 2. Localizar la dimensión
        dim = next((d for d in contract.dimensions if d.key == query.dimension_key), None)
        if not dim:
            raise EntityNotFoundException(
                f"La dimensión '{query.dimension_key}' no existe en el contrato del servicio {query.service_id}."
            )

        # 3. Si la dimensión es INLINE, retorna directamente sin llamada externa ni caché
        if dim.values_source == DimensionValuesSource.INLINE:
            options = [
                DimensionOptionDTO(
                    value_key=v.get("key") or v.get("value_key", ""),
                    label=v.get("label", ""),
                    description=v.get("description"),
                    position=v.get("position", 0),
                )
                for v in dim.inline_values
            ]
            return DimensionOptionsResponseDTO(
                status="completed",
                dimension_key=query.dimension_key,
                options=options,
            )

        # 4. Validar dependencias (depends_on)
        missing_dependencies = [dep for dep in dim.depends_on if dep not in query.context]
        if missing_dependencies:
            raise MissingDimensionDependencyException(missing_dependencies)

        context_hash = RedisDimensionOptionsCache.compute_context_hash(query.context)

        # 5. Fast-Path: Consulta en caché de Redis
        cached_options = await self._dim_cache.get(
            query.service_id, query.dimension_key, query.context
        )
        if cached_options is not None:
            options = [
                DimensionOptionDTO(
                    value_key=opt.get("value_key") or opt.get("key", ""),
                    label=opt.get("label", ""),
                    description=opt.get("description"),
                    position=opt.get("position", 0),
                )
                for opt in cached_options
            ]
            return DimensionOptionsResponseDTO(
                status="completed",
                dimension_key=query.dimension_key,
                options=options,
                context_hash=context_hash,
            )

        # 6. Cache MISS: Encolar petición en bus RPC sobre Redis
        operation_id = f"op_dim_{uuid4().hex[:12]}"
        combo_code: Optional[str] = None
        if self._catalog_repo is not None:
            svc = await self._catalog_repo.get_by_id(query.service_id)
            if svc:
                combo_code = svc.combo_code

        envelope_payload = {
            "service_id": query.service_id,
            "combo_code": combo_code,
            "user_uuid": str(query.user_uuid) if query.user_uuid else None,
            "user_phone": query.user_phone,
            "dimension_key": query.dimension_key,
            "context": query.context,
            "context_hash": context_hash,
            "resolver_ref": dim.resolver_ref,
        }

        await self._bus_client.publish_dimension_request(operation_id, envelope_payload)

        # 7. Espera superficial no bloqueante (2 segundos)
        response_key = f"resp:{operation_id}"
        immediate_result = await self._bus_client.wait_for_response(response_key, timeout_seconds=2.0)

        if immediate_result is not None:
            # Llegó respuesta dentro de la ventana de 2 segundos
            raw_options = immediate_result.get("options", [])
            await self._dim_cache.set(
                query.service_id, query.dimension_key, query.context, raw_options
            )
            options = [
                DimensionOptionDTO(
                    value_key=opt.get("value_key") or opt.get("key", ""),
                    label=opt.get("label", ""),
                    description=opt.get("description"),
                    position=opt.get("position", 0),
                )
                for opt in raw_options
            ]
            return DimensionOptionsResponseDTO(
                status="completed",
                dimension_key=query.dimension_key,
                options=options,
                context_hash=context_hash,
            )

        # Superó los 2 segundos: se devuelve status='processing' y operation_id para polling posterior
        return DimensionOptionsResponseDTO(
            status="processing",
            dimension_key=query.dimension_key,
            operation_id=operation_id,
            context_hash=context_hash,
            expires_in_seconds=300,
        )
