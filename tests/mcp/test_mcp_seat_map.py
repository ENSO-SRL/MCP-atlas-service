from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.mcp.application.dto.availability_dtos import GetOperationResultQueryDTO
from src.mcp.application.dto.seat_map_dtos import GetSeatMapQueryDTO
from src.mcp.application.use_cases.get_operation_result import GetOperationResultUseCase
from src.mcp.application.use_cases.get_seat_map import GetSeatMapUseCase
from src.mcp.domain.entities.catalog_entities import CatalogService
from src.mcp.domain.exceptions.mcp_exceptions import (
    ContractValidationException,
    SlotTokenInvalidException,
)
from src.mcp.infrastructure.redis.redis_cache_manager import (
    RedisAvailabilityCache,
    RedisDimensionOptionsCache,
    RedisSeatMapCache,
)
from src.mcp.infrastructure.security.slot_token_codec import SlotTokenCodec


@pytest.fixture
def mock_token_codec():
    return SlotTokenCodec(secret="test-secret-key-12345678901234567890")


@pytest.fixture
def sample_user_uuid():
    return uuid4()


@pytest.fixture
def mock_redis():
    """Simulador de cliente Redis en memoria para pruebas unitarias."""
    storage = {}

    client = MagicMock()

    async def _get(key):
        return storage.get(key)

    async def _set(key, val, ex=None):
        storage[key] = val

    async def _delete(key):
        storage.pop(key, None)

    client.get = AsyncMock(side_effect=_get)
    client.set = AsyncMock(side_effect=_set)
    client.delete = AsyncMock(side_effect=_delete)
    client._storage = storage
    return client


@pytest.mark.asyncio
async def test_seat_map_cache_hit_returns_immediately(mock_redis, mock_token_codec):
    """Verifica que si el plano de sala ya está en caché Redis, retorna en Fast-Path sin llamar al bus."""
    seat_cache = RedisSeatMapCache(redis_client=mock_redis)

    # Pre-popular la caché con la clave acordada mcp:seat:cache:{service_id}:{showing_id}
    cached_payload = {
        "service_id": 90,
        "showing_id": "1093912",
        "screen_name": "Sala 4",
        "seats_remaining": 101,
        "seat_mode_options": ["mejor", "seleccion"],
        "recommended_seats": ["F6", "F7"],
        "available_seats": ["F6", "F7", "F8"],
        "rows": {
            "F": [
                {"label": "F1", "status": "occupied"},
                {"label": "F6", "status": "available", "recommended": True},
            ]
        },
    }
    await seat_cache.set(service_id=90, showing_id="1093912", data=cached_payload)

    mock_bus = MagicMock()
    mock_bus.publish_seat_map_request = AsyncMock()

    use_case = GetSeatMapUseCase(
        seat_cache=seat_cache,
        bus_client=mock_bus,
        token_codec=mock_token_codec,
    )

    query = GetSeatMapQueryDTO(service_id=90, showing_id="1093912")
    res = await use_case.execute(query)

    assert res.status == "completed"
    assert res.showing_id == "1093912"
    assert res.screen_name == "Sala 4"
    assert res.seats_remaining == 101
    assert res.recommended_seats == ["F6", "F7"]
    mock_bus.publish_seat_map_request.assert_not_called()


@pytest.mark.asyncio
async def test_seat_map_cache_miss_rpc_hit_returns_completed_and_populates_cache(
    mock_redis, mock_token_codec
):
    """Verifica que ante un Cache Miss, el conector despacha la petición al bus y cachea la respuesta exitosa."""
    seat_cache = RedisSeatMapCache(redis_client=mock_redis)

    mock_bus = MagicMock()
    mock_bus.publish_seat_map_request = AsyncMock()
    mock_bus.wait_for_response = AsyncMock(
        return_value={
            "status": "completed",
            "service_id": 90,
            "showing_id": "1093912",
            "screen_name": "Sala 4",
            "seats_remaining": 95,
            "seat_mode_options": ["mejor", "seleccion"],
            "recommended_seats": ["G5", "G6"],
            "available_seats": ["G5", "G6", "G7"],
            "rows": {
                "G": [
                    {"label": "G5", "status": "available", "recommended": True},
                    {"label": "G6", "status": "available", "recommended": True},
                ]
            },
        }
    )

    mock_catalog_repo = MagicMock()
    mock_catalog_repo.get_by_id = AsyncMock(
        return_value=CatalogService(
            id=90, establishment_id=91, name="Multiplaza La Romana", combo_code="cc_multiplaza_la_romana"
        )
    )

    use_case = GetSeatMapUseCase(
        seat_cache=seat_cache,
        bus_client=mock_bus,
        token_codec=mock_token_codec,
        catalog_repo=mock_catalog_repo,
    )

    query = GetSeatMapQueryDTO(service_id=90, showing_id="1093912")
    res = await use_case.execute(query)

    assert res.status == "completed"
    assert res.showing_id == "1093912"
    assert res.seats_remaining == 95
    assert res.recommended_seats == ["G5", "G6"]
    mock_bus.publish_seat_map_request.assert_awaited_once()

    # Comprobar que se guardó en caché con la clave correcta mcp:seat:cache:90:1093912
    cached = await seat_cache.get(90, "1093912")
    assert cached is not None
    assert cached["screen_name"] == "Sala 4"


@pytest.mark.asyncio
async def test_seat_map_cache_miss_rpc_timeout_returns_processing(
    mock_redis, mock_token_codec
):
    """Verifica que si la espera de 2s vence, se devuelve status='processing' y un operation_id."""
    seat_cache = RedisSeatMapCache(redis_client=mock_redis)

    mock_bus = MagicMock()
    mock_bus.publish_seat_map_request = AsyncMock()
    mock_bus.wait_for_response = AsyncMock(return_value=None)  # Simula timeout de 2s

    use_case = GetSeatMapUseCase(
        seat_cache=seat_cache,
        bus_client=mock_bus,
        token_codec=mock_token_codec,
    )

    query = GetSeatMapQueryDTO(service_id=90, showing_id="1093912")
    res = await use_case.execute(query)

    assert res.status == "processing"
    assert res.operation_id.startswith("op_seat_")
    assert "segundo plano" in res.message


@pytest.mark.asyncio
async def test_seat_map_cache_miss_rpc_failed_returns_failed(
    mock_redis, mock_token_codec
):
    """Verifica que si el upstream devuelve fallo, el use case retorna status='failed' con el mensaje de error."""
    seat_cache = RedisSeatMapCache(redis_client=mock_redis)

    mock_bus = MagicMock()
    mock_bus.publish_seat_map_request = AsyncMock()
    mock_bus.wait_for_response = AsyncMock(
        return_value={"status": "failed", "error_message": "Función inexistente en Caribbean Cinemas"}
    )

    use_case = GetSeatMapUseCase(
        seat_cache=seat_cache,
        bus_client=mock_bus,
        token_codec=mock_token_codec,
    )

    query = GetSeatMapQueryDTO(service_id=90, showing_id="1093912")
    res = await use_case.execute(query)

    assert res.status == "failed"
    assert "Función inexistente" in res.error_message


@pytest.mark.asyncio
async def test_seat_map_resolves_showing_id_from_slot_token(
    mock_redis, mock_token_codec, sample_user_uuid
):
    """Verifica que se pueda consultar enviando el slot_token de check_availability."""
    seat_cache = RedisSeatMapCache(redis_client=mock_redis)

    # Acuñar token con offer_ref='1093912'
    token = mock_token_codec.encode(
        token_id="tok_cinema_1093912",
        user_uuid=sample_user_uuid,
        offer_ref="1093912",
        service_id=90,
        slot_start=datetime.now(timezone.utc) + timedelta(hours=2),
        slot_end=datetime.now(timezone.utc) + timedelta(hours=4),
        contract_version="2026-11-10.1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        applied_filters={"movie": "Wildwood"},
    )

    mock_bus = MagicMock()
    mock_bus.publish_seat_map_request = AsyncMock()
    mock_bus.wait_for_response = AsyncMock(
        return_value={
            "status": "completed",
            "service_id": 90,
            "showing_id": "1093912",
            "screen_name": "Sala 4",
            "seats_remaining": 80,
            "available_seats": ["F6", "F7"],
        }
    )

    use_case = GetSeatMapUseCase(
        seat_cache=seat_cache,
        bus_client=mock_bus,
        token_codec=mock_token_codec,
    )

    query = GetSeatMapQueryDTO(
        service_id=90,
        slot_token=token.raw_token,
        user_uuid=sample_user_uuid,
    )
    res = await use_case.execute(query)

    assert res.status == "completed"
    assert res.showing_id == "1093912"


@pytest.mark.asyncio
async def test_seat_map_slot_token_service_mismatch_raises_contract_validation(
    mock_redis, mock_token_codec, sample_user_uuid
):
    """Verifica que si el token pertenece a otro servicio (ej: 18 en vez de 90), se rechace."""
    seat_cache = RedisSeatMapCache(redis_client=mock_redis)

    token = mock_token_codec.encode(
        token_id="tok_wrong_svc",
        user_uuid=sample_user_uuid,
        offer_ref="1093912",
        service_id=18,
        slot_start=datetime.now(timezone.utc) + timedelta(hours=2),
        slot_end=datetime.now(timezone.utc) + timedelta(hours=4),
        contract_version="1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )

    use_case = GetSeatMapUseCase(
        seat_cache=seat_cache,
        bus_client=MagicMock(),
        token_codec=mock_token_codec,
    )

    query = GetSeatMapQueryDTO(
        service_id=90,
        slot_token=token.raw_token,
        user_uuid=sample_user_uuid,
    )

    with pytest.raises(ContractValidationException, match="no al servicio consultado"):
        await use_case.execute(query)


@pytest.mark.asyncio
async def test_seat_map_slot_token_user_mismatch_raises_invalid_token(
    mock_redis, mock_token_codec, sample_user_uuid
):
    """Verifica que si el token pertenece a otro usuario, se rechace."""
    seat_cache = RedisSeatMapCache(redis_client=mock_redis)

    token = mock_token_codec.encode(
        token_id="tok_other_user",
        user_uuid=uuid4(),  # Otro usuario
        offer_ref="1093912",
        service_id=90,
        slot_start=datetime.now(timezone.utc) + timedelta(hours=2),
        slot_end=datetime.now(timezone.utc) + timedelta(hours=4),
        contract_version="1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )

    use_case = GetSeatMapUseCase(
        seat_cache=seat_cache,
        bus_client=MagicMock(),
        token_codec=mock_token_codec,
    )

    query = GetSeatMapQueryDTO(
        service_id=90,
        slot_token=token.raw_token,
        user_uuid=sample_user_uuid,
    )

    with pytest.raises(SlotTokenInvalidException, match="usuario diferente"):
        await use_case.execute(query)


@pytest.mark.asyncio
async def test_seat_map_missing_both_showing_id_and_token_raises_validation(
    mock_redis, mock_token_codec
):
    """Verifica que si no se envía showing_id ni slot_token, lance ContractValidationException."""
    use_case = GetSeatMapUseCase(
        seat_cache=RedisSeatMapCache(redis_client=mock_redis),
        bus_client=MagicMock(),
        token_codec=mock_token_codec,
    )

    query = GetSeatMapQueryDTO(service_id=90)
    with pytest.raises(ContractValidationException, match="Debe proporcionar 'showing_id' o 'slot_token'"):
        await use_case.execute(query)


@pytest.mark.asyncio
async def test_get_operation_result_handles_seat_map(mock_redis):
    """Verifica que get_operation_result procese resultados de mapa de asientos y pueble la caché."""
    seat_cache = RedisSeatMapCache(redis_client=mock_redis)

    mock_bus = MagicMock()
    mock_bus.get_operation_result = AsyncMock(
        return_value={
            "status": "completed",
            "service_id": 90,
            "showing_id": "1093912",
            "result_type": "seat_map",
            "screen_name": "Sala 4",
            "available_seats": ["F6", "F7"],
            "rows": {"F": [{"label": "F6", "status": "available"}]},
        }
    )

    use_case = GetOperationResultUseCase(
        bus_client=mock_bus,
        contract_repo=MagicMock(),
        hold_manager=MagicMock(),
        token_codec=MagicMock(),
        avail_cache=MagicMock(),
        dim_cache=MagicMock(),
        seat_cache=seat_cache,
    )

    query = GetOperationResultQueryDTO(operation_id="op_seat_123456", user_uuid=uuid4())
    res = await use_case.execute(query)

    assert res.status == "completed"
    assert res.result_type == "seat_map"
    assert res.seat_map is not None
    assert res.seat_map["showing_id"] == "1093912"

    # Verificar que se pobló la caché con la clave mcp:seat:cache:90:1093912
    cached = await seat_cache.get(90, "1093912")
    assert cached is not None
    assert cached["screen_name"] == "Sala 4"

