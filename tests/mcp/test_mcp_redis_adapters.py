from __future__ import annotations

import json
from typing import Any, Optional
from uuid import uuid4

import pytest

from src.mcp.infrastructure.redis.redis_bus_client import RedisBusClient
from src.mcp.infrastructure.redis.redis_cache_manager import (
    RedisAvailabilityCache,
    RedisDimensionOptionsCache,
    compute_context_hash,
)
from src.mcp.infrastructure.redis.redis_hold_manager import RedisHoldManager


class FakeAsyncRedis:
    """Simulador en memoria del cliente async de Redis para pruebas unitarias sin dependencias externas."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}
        self.streams: dict[str, list[dict[str, Any]]] = {}

    async def get(self, key: str) -> Optional[str]:
        return self.store.get(key)

    async def set(
        self,
        key: str,
        value: str,
        ex: Optional[int] = None,
        nx: bool = False,
    ) -> bool:
        if nx and key in self.store:
            return False
        self.store[key] = str(value)
        return True

    async def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                count += 1
            if k in self.lists:
                del self.lists[k]
                count += 1
        return count

    async def exists(self, key: str) -> int:
        return 1 if (key in self.store or key in self.lists) else 0

    async def rpush(self, key: str, *values: str) -> int:
        if key not in self.lists:
            self.lists[key] = []
        for v in values:
            self.lists[key].append(str(v))
        return len(self.lists[key])

    async def blpop(self, keys: list[str], timeout: int = 0) -> Optional[tuple[str, str]]:
        for k in keys:
            if k in self.lists and len(self.lists[k]) > 0:
                val = self.lists[k].pop(0)
                return (k, val)
        return None

    async def rpop(self, key: str) -> Optional[str]:
        if key in self.lists and len(self.lists[key]) > 0:
            return self.lists[key].pop()
        return None

    async def xadd(self, stream_name: str, fields: dict[str, Any]) -> str:
        if stream_name not in self.streams:
            self.streams[stream_name] = []
        msg_id = f"1729965600000-{len(self.streams[stream_name])}"
        self.streams[stream_name].append({"id": msg_id, "fields": fields})
        return msg_id

    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> Any:
        # Simulación del script Lua de liberación segura de hold
        if "if redis.call(\"get\", KEYS[1]) == ARGV[1]" in script:
            key = keys_and_args[0]
            expected_val = keys_and_args[1]
            if self.store.get(key) == expected_val:
                del self.store[key]
                return 1
            return 0
        return None


def test_compute_context_hash_determinism():
    ctx_a = {"date": "2026-10-26", "specialty": "brakes", "mechanic_id": 4}
    ctx_b = {"mechanic_id": 4, "date": "2026-10-26", "specialty": "brakes"}

    hash_a = compute_context_hash(ctx_a)
    hash_b = compute_context_hash(ctx_b)

    assert hash_a == hash_b
    assert len(hash_a) == 64  # SHA-256 hex digest


@pytest.mark.anyio
async def test_redis_availability_cache():
    fake_redis = FakeAsyncRedis()
    cache = RedisAvailabilityCache(redis_client=fake_redis)

    # Cache miss inicial
    miss = await cache.get(service_id=1, contract_version="v1", filter_hash="hash123")
    assert miss is None

    # Cache set y hit
    slot_data = {"slots": [{"start": "10:00", "end": "11:00", "available": True}]}
    await cache.set(
        service_id=1, contract_version="v1", filter_hash="hash123", data=slot_data
    )

    hit = await cache.get(service_id=1, contract_version="v1", filter_hash="hash123")
    assert hit == slot_data

    # Delete
    await cache.delete(service_id=1, contract_version="v1", filter_hash="hash123")
    assert (
        await cache.get(service_id=1, contract_version="v1", filter_hash="hash123") is None
    )


@pytest.mark.anyio
async def test_redis_dimension_options_cache():
    fake_redis = FakeAsyncRedis()
    cache = RedisDimensionOptionsCache(redis_client=fake_redis)

    context = {"date": "2026-10-26", "shift": "morning"}
    miss = await cache.get(service_id=5, dimension_key="mechanic", context=context)
    assert miss is None

    options = [
        {"value_key": "mech_1", "label": "Carlos Gómez"},
        {"value_key": "mech_2", "label": "Ana Martínez"},
    ]
    await cache.set(
        service_id=5, dimension_key="mechanic", context=context, options=options
    )

    hit = await cache.get(service_id=5, dimension_key="mechanic", context=context)
    assert hit == options

    # Probar que con claves desordenadas también da hit por el hash canónico
    shuffled_context = {"shift": "morning", "date": "2026-10-26"}
    hit_shuffled = await cache.get(
        service_id=5, dimension_key="mechanic", context=shuffled_context
    )
    assert hit_shuffled == options


@pytest.mark.anyio
async def test_redis_hold_manager():
    fake_redis = FakeAsyncRedis()
    hold_mgr = RedisHoldManager(redis_client=fake_redis)

    offer_ref = "offer_padel_court_4_1800"
    booking_id_1 = uuid4()
    booking_id_2 = uuid4()

    # Primer hold se concede
    acquired = await hold_mgr.place_hold(offer_ref, booking_id_1, ttl_seconds=600)
    assert acquired is True
    assert await hold_mgr.is_held(offer_ref) is True
    assert await hold_mgr.get_held_by(offer_ref) == booking_id_1

    # Segundo hold concurrentemente sobre el mismo slot es rechazado
    second_attempt = await hold_mgr.place_hold(offer_ref, booking_id_2, ttl_seconds=600)
    assert second_attempt is False

    # Intento de liberar con booking_id incorrecto falla (no lo libera)
    await hold_mgr.release_hold(offer_ref, booking_id=booking_id_2)
    assert await hold_mgr.is_held(offer_ref) is True

    # Liberación con el booking_id dueño sí lo libera
    await hold_mgr.release_hold(offer_ref, booking_id=booking_id_1)
    assert await hold_mgr.is_held(offer_ref) is False
    assert await hold_mgr.get_held_by(offer_ref) is None


@pytest.mark.anyio
async def test_redis_bus_client():
    fake_redis = FakeAsyncRedis()
    bus = RedisBusClient(redis_client=fake_redis)

    # 1. Publicar solicitud de disponibilidad
    op_id = "op_test_123"
    await bus.publish_availability_request(op_id, {"service_id": 1, "date": "2026-10-27"})

    # Verificar que el estado inicial en op:op_test_123 es processing
    op_status = await bus.get_operation_result(op_id)
    assert op_status is not None
    assert op_status["status"] == "processing"
    assert op_status["operation_id"] == op_id

    # Verificar que la solicitud entró en la cola queue:avail:requests
    assert len(fake_redis.lists["queue:avail:requests"]) == 1
    envelope = json.loads(fake_redis.lists["queue:avail:requests"][0])
    assert envelope["operation_id"] == op_id

    # 2. Simular respuesta del Facade en resp:op_test_123
    resp_payload = {"status": "completed", "slots": [{"id": 101}]}
    await fake_redis.rpush(f"resp:{op_id}", json.dumps(resp_payload))

    # Espera superficial debe recuperar la respuesta
    received = await bus.wait_for_response(f"resp:{op_id}", timeout_seconds=1.0)
    assert received == resp_payload

    # 3. Publicación en Redis Streams
    stream_id = await bus.publish_stream_event(
        "stream:booking:events", {"event": "BookingRequested", "id": 999}
    )
    assert "stream:booking:events" in fake_redis.streams
    assert stream_id.startswith("1729965600000-")


@pytest.mark.anyio
async def test_redis_bus_client_lazy_sync_fallback():
    """
    Verifica que si la espera superficial expiró y el estado en op:{id} quedó en 'processing',
    pero el Facade depositó la respuesta tardía en resp:{id}, get_operation_result extrae
    el resultado de resp:{id} vía RPOP, lo promueve a op:{id} como 'completed' y lo entrega.
    """
    fake_redis = FakeAsyncRedis()
    bus = RedisBusClient(redis_client=fake_redis)

    op_id = "op_delayed_789"

    # 1. Simular inicio de operación: queda registrada en 'processing'
    await bus.set_operation_result(op_id, {"status": "processing", "operation_id": op_id})
    assert (await bus.get_operation_result(op_id))["status"] == "processing"

    # 2. Simular que el Facade responde tardíamente en la lista efímera resp:{op_id}
    delayed_response = {
        "status": "completed",
        "slots": [{"slot_id": "slot_late_1", "start": "19:00"}],
    }
    await fake_redis.rpush(f"resp:{op_id}", json.dumps(delayed_response))

    # 3. Claude o el cliente consulta el resultado con get_operation_result
    result = await bus.get_operation_result(op_id)
    assert result is not None
    assert result["status"] == "completed"
    assert result["slots"][0]["slot_id"] == "slot_late_1"

    # 4. Verificar que la lista efímera quedó vacía (fue consumida por RPOP)
    assert len(fake_redis.lists[f"resp:{op_id}"]) == 0

    # 5. Verificar que la clave durable op:{op_id} ahora tiene guardado el resultado
    persisted_op = json.loads(fake_redis.store[f"op:{op_id}"])
    assert persisted_op["status"] == "completed"
    assert persisted_op["slots"][0]["slot_id"] == "slot_late_1"

