from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.mcp.domain.entities.booking_request import BookingRequest
from src.mcp.domain.enums.mcp_enums import BookingStatus
from src.mcp.infrastructure.persistence.models.booking_models import (
    InboxEventModel,
    OutboxEventModel,
)
from src.mcp.infrastructure.workers.inbox_consumer_worker import (
    InboxConsumerWorker,
)
from src.mcp.infrastructure.workers.outbox_relay_worker import (
    OutboxRelayWorker,
)


@pytest.mark.anyio
async def test_outbox_relay_worker_relays_pending_events():
    # 1. Simular evento outbox pendiente
    event_id = uuid4()
    aggregate_id = uuid4()
    pending_event = OutboxEventModel(
        id=event_id,
        aggregate_id=aggregate_id,
        event_type="BookingRequested",
        payload={"booking_id": str(aggregate_id), "status": "requested"},
        correlation_id="corr-999",
        published_at=None,
        attempts=0,
    )

    # Mock de la sesión y session_factory
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [pending_event]
    mock_session.execute.return_value = mock_result

    @asynccontextmanager
    async def mock_begin():
        yield

    mock_session.begin = mock_begin

    @asynccontextmanager
    async def mock_session_ctx():
        yield mock_session

    mock_session_factory = MagicMock(side_effect=mock_session_ctx)

    # Mock de bus_client
    mock_bus_client = AsyncMock()

    worker = OutboxRelayWorker(
        session_factory=mock_session_factory,
        bus_client=mock_bus_client,
        batch_size=10,
        stream_name="stream:booking:events",
    )

    # Ejecutar relay_batch
    count = await worker.relay_batch()

    assert count == 1
    assert pending_event.published_at is not None
    assert pending_event.attempts == 1
    assert mock_bus_client.publish_stream_event.call_count == 1

    call_args = mock_bus_client.publish_stream_event.call_args[0]
    stream_name, envelope = call_args
    assert stream_name == "stream:booking:events"
    assert envelope["event_id"] == str(event_id)
    assert envelope["aggregate_id"] == str(aggregate_id)
    assert envelope["event_type"] == "BookingRequested"


@pytest.mark.anyio
async def test_inbox_consumer_worker_processes_booking_accepted_and_confirmed():
    # 1. Preparar una entidad BookingRequest en estado REQUESTED
    booking = BookingRequest.create(
        user_uuid=uuid4(),
        service_id=10,
        contract_version_id=uuid4(),
        idempotency_key="idemp_inbox",
        request_fingerprint="fp_inbox",
        token_id="tok_inbox",
        offer_ref="off_inbox_123",
        slot_start=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
    )
    assert booking.status == BookingStatus.REQUESTED

    # 2. Configurar mock de sesión y repositorios
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    @asynccontextmanager
    async def mock_begin():
        yield

    mock_session.begin = mock_begin

    @asynccontextmanager
    async def mock_session_ctx():
        yield mock_session

    mock_session_factory = MagicMock(side_effect=mock_session_ctx)

    # Simular que el evento inbox no ha sido procesado aún (get(InboxEventModel) -> None)
    # y que get(BookingRequestModel) retorna los datos correspondientes
    def mock_get(entity_cls, ident):
        if entity_cls == InboxEventModel:
            return None
        return None

    mock_session.get.side_effect = mock_get

    # Mock de Redis y HoldManager
    mock_redis = AsyncMock()
    mock_hold_mgr = AsyncMock()

    worker = InboxConsumerWorker(
        session_factory=mock_session_factory,
        redis_client=mock_redis,
        hold_manager=mock_hold_mgr,
        stream_name="stream:booking:results",
        group_name="mcp_inbox_group",
    )

    # 3. Simular llegada de evento 'BookingAccepted' (trámite en curso)
    accepted_event_id = uuid4()
    accepted_msg = {
        "payload": json.dumps(
            {
                "event_id": str(accepted_event_id),
                "event_type": "BookingAccepted",
                "aggregate_id": str(booking.id),
                "payload": {
                    "external_ref": "TRAMITE-INBOX-101",
                    "details": {"mesa": "VIP"},
                },
            }
        )
    }

    # Inyectar el booking para que SqlBookingRepository lo devuelva al buscar por ID
    from unittest.mock import patch

    with patch(
        "src.mcp.infrastructure.workers.inbox_consumer_worker.SqlBookingRepository"
    ) as mock_repo_cls:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_by_id.return_value = booking
        mock_repo_cls.return_value = mock_repo_instance

        # Procesar BookingAccepted
        ok = await worker.process_message("1001-0", accepted_msg)
        assert ok is True
        assert booking.status == BookingStatus.ACCEPTED
        assert booking.external_ref == "TRAMITE-INBOX-101"
        assert mock_redis.xack.call_count == 1
        # No debe liberar el hold en estado accepted (sigue activo en trámite)
        assert mock_hold_mgr.release_hold.call_count == 0

        # Procesar BookingConfirmed posterior
        mock_redis.xack.reset_mock()
        confirmed_event_id = uuid4()
        confirmed_msg = {
            "payload": json.dumps(
                {
                    "event_id": str(confirmed_event_id),
                    "event_type": "BookingConfirmed",
                    "aggregate_id": str(booking.id),
                    "payload": {
                        "external_ref": "CONFIRM-FINAL-999",
                        "assigned_details": {"pista": "1"},
                    },
                }
            )
        }

        ok_conf = await worker.process_message("1002-0", confirmed_msg)
        assert ok_conf is True
        assert booking.status == BookingStatus.CONFIRMED
        assert booking.external_ref == "CONFIRM-FINAL-999"
        assert mock_redis.xack.call_count == 1
        # Ahora sí debe haber liberado el hold
        assert mock_hold_mgr.release_hold.call_count == 1
        mock_hold_mgr.release_hold.assert_called_with(booking.offer_ref, booking.id)


@pytest.mark.anyio
async def test_inbox_consumer_worker_idempotency_skips_duplicates():
    event_id = uuid4()
    existing_inbox = InboxEventModel(
        event_id=event_id,
        event_type="BookingConfirmed",
        aggregate_id=uuid4(),
        received_at=datetime.now(timezone.utc),
        processed_at=datetime.now(timezone.utc),  # Ya fue procesado previamente
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    @asynccontextmanager
    async def mock_begin():
        yield

    mock_session.begin = mock_begin

    @asynccontextmanager
    async def mock_session_ctx():
        yield mock_session

    mock_session_factory = MagicMock(side_effect=mock_session_ctx)
    mock_session.get.return_value = existing_inbox

    mock_redis = AsyncMock()
    mock_hold_mgr = AsyncMock()

    worker = InboxConsumerWorker(
        session_factory=mock_session_factory,
        redis_client=mock_redis,
        hold_manager=mock_hold_mgr,
    )

    duplicate_msg = {
        "payload": json.dumps(
            {
                "event_id": str(event_id),
                "event_type": "BookingConfirmed",
                "aggregate_id": str(uuid4()),
                "payload": {},
            }
        )
    }

    # Al ser duplicado ya procesado: retorna True y hace XACK directo sin tocar repositorios
    ok = await worker.process_message("2001-0", duplicate_msg)
    assert ok is True
    assert mock_redis.xack.call_count == 1
    assert mock_hold_mgr.release_hold.call_count == 0
