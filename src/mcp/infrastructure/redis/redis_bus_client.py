from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from redis.asyncio import Redis

from src.mcp.domain.ports.mcp_ports import IRedisBusClient
from src.shared.config.settings import get_settings
from src.shared.redis.client import get_redis_client


class RedisBusClient(IRedisBusClient):
    """
    Cliente de bus de mensajería y RPC diferido sobre Redis.
    Implementa el puerto IRedisBusClient para:
    - Encolado de peticiones upstream a colas de trabajo (queue:avail:requests, queue:dim:requests).
    - Espera superficial no bloqueante (BLPOP en resp:{operation_id}).
    - Consulta y registro de estado de operaciones diferidas (op:{operation_id}).
    - Publicación y consumo en Redis Streams (stream:booking:events, stream:booking:results).
    """

    def __init__(self, redis_client: Optional[Redis] = None):
        self._redis = redis_client or get_redis_client()
        self._settings = get_settings()

    async def publish_availability_request(
        self, operation_id: str, payload: dict[str, Any]
    ) -> None:
        """
        Publica una solicitud de disponibilidad en la cola 'queue:avail:requests'
        e inicializa el registro op:{operation_id} con status='processing'.
        """
        envelope = {
            "operation_id": operation_id,
            "type": "availability_request",
            "payload": payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.set_operation_result(
            operation_id,
            {
                "status": "processing",
                "operation_id": operation_id,
                "created_at": envelope["created_at"],
            },
            ttl_seconds=self._settings.REDIS_OPERATION_TTL,
        )
        await self._redis.rpush("queue:avail:requests", json.dumps(envelope, ensure_ascii=False))

    async def publish_dimension_request(
        self, operation_id: str, payload: dict[str, Any]
    ) -> None:
        """
        Publica una solicitud de resolución de dimensión en 'queue:dim:requests'
        e inicializa el registro op:{operation_id} con status='processing'.
        """
        envelope = {
            "operation_id": operation_id,
            "type": "dimension_request",
            "payload": payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.set_operation_result(
            operation_id,
            {
                "status": "processing",
                "operation_id": operation_id,
                "created_at": envelope["created_at"],
            },
            ttl_seconds=self._settings.REDIS_OPERATION_TTL,
        )
        await self._redis.rpush("queue:dim:requests", json.dumps(envelope, ensure_ascii=False))

    async def wait_for_response(
        self, response_key: str, timeout_seconds: float
    ) -> Optional[dict[str, Any]]:
        """
        Realiza la espera superficial no bloqueante sobre resp:{operation_id} usando BLPOP.
        Retorna el diccionario de respuesta si el Facade respondió a tiempo; None si expiró.
        """
        timeout = int(timeout_seconds) if timeout_seconds >= 1 else 1
        result = await self._redis.blpop([response_key], timeout=timeout)
        if result is None:
            return None
        _key, raw_val = result
        try:
            return json.loads(raw_val)
        except (json.JSONDecodeError, TypeError):
            return None

    async def get_operation_result(self, operation_id: str) -> Optional[dict[str, Any]]:
        """
        Recupera el resultado o estado actual de una operación diferida (op:{operation_id}).
        Aplica un patrón defensivo (Lazy Sync): si el estado actual es 'processing' o no existe,
        inspecciona de forma no bloqueante (RPOP) la lista efímera resp:{operation_id} por si
        el Facade/ejecutor depositó allí el resultado tras expirar la espera superficial.
        Si encuentra respuesta, la promueve a op:{operation_id} y la retorna.
        """
        key = f"op:{operation_id}"
        raw = await self._redis.get(key)
        data: Optional[dict[str, Any]] = None
        if raw is not None:
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                data = None

        # Si no existe o sigue en trámite ('processing'), revisamos de forma oportunista la lista
        if data is None or data.get("status") == "processing":
            resp_key = f"resp:{operation_id}"
            raw_list_item = await self._redis.rpop(resp_key)
            if raw_list_item is not None:
                try:
                    payload = json.loads(raw_list_item)
                    if isinstance(payload, dict):
                        if "status" not in payload:
                            payload["status"] = "completed"
                        data = payload
                    else:
                        data = {"status": "completed", "data": payload}
                    # Promover inmediatamente a la clave durable op:{operation_id}
                    await self.set_operation_result(operation_id, data)
                except (json.JSONDecodeError, TypeError):
                    pass

        return data

    async def set_operation_result(
        self, operation_id: str, data: dict[str, Any], ttl_seconds: Optional[int] = None
    ) -> None:
        """Guarda o actualiza el estado/resultado de una operación diferida."""
        key = f"op:{operation_id}"
        ttl = ttl_seconds if ttl_seconds is not None else self._settings.REDIS_OPERATION_TTL
        await self._redis.set(key, json.dumps(data, ensure_ascii=False), ex=ttl)

    async def get_cached_availability(self, cache_key: str) -> Optional[dict[str, Any]]:
        """Consulta directa a una clave de caché de disponibilidad."""
        raw = await self._redis.get(cache_key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    async def set_cached_availability(
        self, cache_key: str, data: dict[str, Any], ttl_seconds: int
    ) -> None:
        """Almacena directamente en una clave de caché de disponibilidad."""
        await self._redis.set(
            cache_key, json.dumps(data, ensure_ascii=False), ex=ttl_seconds
        )

    async def publish_stream_event(self, stream_name: str, payload: dict[str, Any]) -> str:
        """
        Publica un evento transaccional en un stream de Redis (XADD).
        Retorna el id generado por Redis (ej. '1729965600000-0').
        """
        fields = {"payload": json.dumps(payload, ensure_ascii=False)}
        msg_id = await self._redis.xadd(stream_name, fields)
        return str(msg_id)
