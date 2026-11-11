from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from src.mcp.application.dto.seat_map_dtos import (
    GetSeatMapQueryDTO,
    SeatMapResponseDTO,
)
from src.mcp.application.use_cases.operation_helpers import resolve_operation_error
from src.mcp.domain.exceptions.mcp_exceptions import (
    ContractValidationException,
    SlotTokenInvalidException,
)
from src.mcp.domain.ports.mcp_ports import (
    ICatalogServiceRepository,
    IRedisBusClient,
)
from src.mcp.infrastructure.redis.redis_cache_manager import RedisSeatMapCache
from src.mcp.infrastructure.security.slot_token_codec import SlotTokenCodec


class GetSeatMapUseCase:
    """
    Caso de uso: Consultar plano de asientos y butacas disponibles (get_seat_map).
    Implementa:
    1. Resolución y validación del identificador de función/tanda (showing_id):
       - A partir de 'slot_token' (desencripta, valida firma e identidad y extrae offer_ref).
       - O a partir de 'showing_id' directo.
    2. Fast-Path: Consulta en RedisSeatMapCache (clave mcp:seat:cache:{service_id}:{showing_id}, < 5ms).
    3. Fallback: RPC asíncrono sobre 'queue:seatmap:requests' con espera superficial no bloqueante (2.0s).
       - Si responde a tiempo: almacena en caché (TTL 90s) y retorna el plano estructurado.
       - Si vence la espera: retorna status='processing' y operation_id para consulta diferida.
    """

    def __init__(
        self,
        seat_cache: RedisSeatMapCache,
        bus_client: IRedisBusClient,
        token_codec: SlotTokenCodec,
        catalog_repo: Optional[ICatalogServiceRepository] = None,
    ):
        self._seat_cache = seat_cache
        self._bus_client = bus_client
        self._token_codec = token_codec
        self._catalog_repo = catalog_repo

    async def execute(self, query: GetSeatMapQueryDTO) -> SeatMapResponseDTO:
        showing_id: Optional[str] = None

        # 1. Extracción de showing_id desde slot_token o parámetro directo
        if query.slot_token:
            token = self._token_codec.decode(query.slot_token)
            if token.service_id != query.service_id:
                raise ContractValidationException(
                    f"El slot_token suministrado pertenece al servicio {token.service_id}, "
                    f"no al servicio consultado ({query.service_id})."
                )
            if query.user_uuid and token.user_uuid != query.user_uuid:
                raise SlotTokenInvalidException(
                    "El token de horario pertenece a un usuario diferente."
                )
            showing_id = token.offer_ref or str(token.applied_filters.get("showing_id", ""))
        elif query.showing_id:
            showing_id = str(query.showing_id).strip()

        if not showing_id:
            raise ContractValidationException(
                "Debe proporcionar 'showing_id' o 'slot_token' para consultar el mapa de asientos."
            )

        # 2. Información del servicio en catálogo (combo_code para enrutamiento en Facade)
        combo_code: Optional[str] = None
        if self._catalog_repo is not None:
            svc = await self._catalog_repo.get_by_id(query.service_id)
            if svc:
                combo_code = svc.combo_code

        # 3. Fast-Path: Consulta en caché de Redis (mcp:seat:cache:{service_id}:{showing_id})
        cached_data = await self._seat_cache.get(query.service_id, showing_id)
        if cached_data is not None:
            return SeatMapResponseDTO(
                status="completed",
                service_id=query.service_id,
                showing_id=showing_id,
                screen_name=cached_data.get("screen_name") or cached_data.get("screen_id"),
                seats_remaining=cached_data.get("seats_remaining"),
                seat_mode_options=cached_data.get("seat_mode_options", ["mejor", "seleccion"]),
                recommended_seats=cached_data.get("recommended_seats", []),
                available_seats=cached_data.get("available_seats", []),
                rows=cached_data.get("rows", {}),
                message=cached_data.get("message", "Plano de asientos obtenido desde caché."),
            )

        # 4. Cache MISS: Encolar petición en bus RPC sobre Redis
        operation_id = f"op_seat_{uuid4().hex[:12]}"
        envelope_payload = {
            "service_id": query.service_id,
            "combo_code": combo_code,
            "showing_id": showing_id,
            "user_uuid": str(query.user_uuid) if query.user_uuid else None,
            "user_phone": query.user_phone,
        }

        await self._bus_client.publish_seat_map_request(operation_id, envelope_payload)

        # 5. Espera superficial no bloqueante (2 segundos)
        response_key = f"resp:{operation_id}"
        immediate_result = await self._bus_client.wait_for_response(response_key, timeout_seconds=2.0)

        if immediate_result is not None:
            # Comprobar si falló upstream
            if immediate_result.get("status") == "failed":
                error_msg, _ = resolve_operation_error(immediate_result, operation_id)
                return SeatMapResponseDTO(
                    status="failed",
                    service_id=query.service_id,
                    showing_id=showing_id,
                    operation_id=operation_id,
                    error_message=error_msg,
                )

            # Respuesta exitosa dentro de los 2 segundos: guardar en caché (TTL 90s)
            await self._seat_cache.set(query.service_id, showing_id, immediate_result, ttl_seconds=90)

            return SeatMapResponseDTO(
                status="completed",
                service_id=query.service_id,
                showing_id=showing_id,
                screen_name=immediate_result.get("screen_name") or immediate_result.get("screen_id"),
                seats_remaining=immediate_result.get("seats_remaining"),
                seat_mode_options=immediate_result.get("seat_mode_options", ["mejor", "seleccion"]),
                recommended_seats=immediate_result.get("recommended_seats", []),
                available_seats=immediate_result.get("available_seats", []),
                rows=immediate_result.get("rows", {}),
                operation_id=operation_id,
                message=immediate_result.get("message", "Plano de asientos recuperado exitosamente."),
            )

        # 6. Superó los 2 segundos: retorno de status='processing' y operation_id para polling
        return SeatMapResponseDTO(
            status="processing",
            service_id=query.service_id,
            showing_id=showing_id,
            operation_id=operation_id,
            expires_in_seconds=120,
            message="La consulta del plano de butacas está siendo procesada en segundo plano por el cine. Puedes consultar su resultado con 'get_operation_result'.",
        )

