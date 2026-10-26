from __future__ import annotations

from typing import Optional
from uuid import UUID
from redis.asyncio import Redis

from src.mcp.domain.ports.mcp_ports import IHoldManager
from src.shared.redis.client import get_redis_client

_RELEASE_HOLD_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class RedisHoldManager(IHoldManager):
    """
    Gestor de holds temporales de slots en memoria (Redis).
    Garantiza atomicidad vía SETNX y evita colisiones concurrentes entre usuarios.
    Clave Redis: hold:slot:{offer_ref}
    """

    def __init__(self, redis_client: Optional[Redis] = None):
        self._redis = redis_client or get_redis_client()

    @staticmethod
    def build_key(offer_ref: str) -> str:
        return f"hold:slot:{offer_ref}"

    async def place_hold(self, offer_ref: str, booking_id: UUID, ttl_seconds: int = 900) -> bool:
        """
        Intenta colocar un hold atómico (SETNX con TTL).
        Retorna True si el slot estaba libre y se concedió el hold; False si ya está tomado.
        """
        key = self.build_key(offer_ref)
        acquired = await self._redis.set(key, str(booking_id), nx=True, ex=ttl_seconds)
        return bool(acquired)

    async def release_hold(self, offer_ref: str, booking_id: Optional[UUID] = None) -> None:
        """
        Libera el hold. Si se especifica booking_id, la liberación es segura y atómica
        (solo quien colocó el hold puede liberarlo vía Lua script).
        """
        key = self.build_key(offer_ref)
        if booking_id is not None:
            await self._redis.eval(_RELEASE_HOLD_LUA, 1, key, str(booking_id))
        else:
            await self._redis.delete(key)

    async def is_held(self, offer_ref: str) -> bool:
        """Verifica si un slot tiene un hold activo y no expirado."""
        key = self.build_key(offer_ref)
        exists = await self._redis.exists(key)
        return bool(exists)

    async def get_held_by(self, offer_ref: str) -> Optional[UUID]:
        """Obtiene el booking_id que posee el hold actual, si existe."""
        key = self.build_key(offer_ref)
        raw = await self._redis.get(key)
        if raw is None:
            return None
        try:
            return UUID(raw)
        except (ValueError, TypeError):
            return None
