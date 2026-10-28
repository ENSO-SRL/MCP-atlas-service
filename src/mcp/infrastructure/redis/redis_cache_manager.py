from __future__ import annotations

import hashlib
import json
from typing import Any, Optional
from redis.asyncio import Redis

from src.shared.config.settings import get_settings
from src.shared.redis.client import get_redis_client


def compute_context_hash(context: dict[str, Any]) -> str:
    """
    Calcula el digest SHA-256 canónico y determinista para un contexto de dimensión.
    Garantiza que el orden de las claves no altere el valor del hash.
    """
    canonical_json = json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class RedisAvailabilityCache:
    """
    Caché determinista de disponibilidad de slots (Cache-Aside).
    Clave Redis: avail:cache:{service_id}:{contract_version}:{filter_hash}
    TTL por defecto: 600 segundos (10 minutos).
    """

    def __init__(self, redis_client: Optional[Redis] = None):
        self._redis = redis_client or get_redis_client()
        self._default_ttl = get_settings().REDIS_AVAILABILITY_CACHE_TTL

    @staticmethod
    def build_key(service_id: int, contract_version: str, filter_hash: str) -> str:
        return f"avail:cache:{service_id}:{contract_version}:{filter_hash}"

    async def get(
        self, service_id: int, contract_version: str, filter_hash: str
    ) -> Optional[dict[str, Any]]:
        key = self.build_key(service_id, contract_version, filter_hash)
        raw = await self._redis.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set(
        self,
        service_id: int,
        contract_version: str,
        filter_hash: str,
        data: dict[str, Any],
        ttl_seconds: Optional[int] = None,
    ) -> None:
        key = self.build_key(service_id, contract_version, filter_hash)
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        serialized = json.dumps(data, ensure_ascii=False)
        await self._redis.set(key, serialized, ex=ttl)

    async def delete(self, service_id: int, contract_version: str, filter_hash: str) -> None:
        key = self.build_key(service_id, contract_version, filter_hash)
        await self._redis.delete(key)


class RedisDimensionOptionsCache:
    """
    Caché determinista de opciones para dimensiones calculadas upstream (separate_query).
    Clave Redis: dim:cache:{service_id}:{dimension_key}:{context_hash}
    TTL por defecto: 600 segundos (10 minutos).
    """

    def __init__(self, redis_client: Optional[Redis] = None):
        self._redis = redis_client or get_redis_client()
        self._default_ttl = get_settings().REDIS_DIMENSION_CACHE_TTL

    @staticmethod
    def compute_context_hash(context: dict[str, Any]) -> str:
        return compute_context_hash(context)

    @staticmethod
    def build_key_from_hash(service_id: int, dimension_key: str, context_hash: str) -> str:
        return f"dim:cache:{service_id}:{dimension_key}:{context_hash}"

    @staticmethod
    def build_key(service_id: int, dimension_key: str, context: dict[str, Any]) -> str:
        context_hash = compute_context_hash(context)
        return RedisDimensionOptionsCache.build_key_from_hash(service_id, dimension_key, context_hash)

    async def get_by_hash(
        self, service_id: int, dimension_key: str, context_hash: str
    ) -> Optional[list[dict[str, Any]]]:
        key = self.build_key_from_hash(service_id, dimension_key, context_hash)
        raw = await self._redis.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def get(
        self, service_id: int, dimension_key: str, context: dict[str, Any]
    ) -> Optional[list[dict[str, Any]]]:
        context_hash = self.compute_context_hash(context)
        return await self.get_by_hash(service_id, dimension_key, context_hash)

    async def set_by_hash(
        self,
        service_id: int,
        dimension_key: str,
        context_hash: str,
        options: list[dict[str, Any]],
        ttl_seconds: Optional[int] = None,
    ) -> None:
        key = self.build_key_from_hash(service_id, dimension_key, context_hash)
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        serialized = json.dumps(options, ensure_ascii=False)
        await self._redis.set(key, serialized, ex=ttl)

    async def set(
        self,
        service_id: int,
        dimension_key: str,
        context: dict[str, Any],
        options: list[dict[str, Any]],
        ttl_seconds: Optional[int] = None,
    ) -> None:
        context_hash = self.compute_context_hash(context)
        await self.set_by_hash(
            service_id=service_id,
            dimension_key=dimension_key,
            context_hash=context_hash,
            options=options,
            ttl_seconds=ttl_seconds,
        )

    async def delete(self, service_id: int, dimension_key: str, context: dict[str, Any]) -> None:
        key = self.build_key(service_id, dimension_key, context)
        await self._redis.delete(key)
