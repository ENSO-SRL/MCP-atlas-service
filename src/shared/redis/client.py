from __future__ import annotations

from typing import Optional
from redis.asyncio import ConnectionPool, Redis

from src.shared.config.settings import get_settings

_redis_pool: Optional[ConnectionPool] = None
_redis_client: Optional[Redis] = None


def get_redis_client() -> Redis:
    """Retorna o inicializa el cliente asíncrono de Redis conectado mediante pool."""
    global _redis_pool, _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=50,
        )
        _redis_client = Redis(connection_pool=_redis_pool)
    return _redis_client


async def close_redis_client() -> None:
    """Cierra las conexiones de Redis al detener el servidor."""
    global _redis_pool, _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None
