from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.mcp.infrastructure.persistence.models.booking_models import InboxEventModel
from src.mcp.infrastructure.persistence.repositories.sql_booking_repository import (
    SqlBookingRepository,
)
from src.mcp.infrastructure.redis.redis_hold_manager import RedisHoldManager
from src.shared.database.session import get_session_factory
from src.shared.redis.client import get_redis_client

logger = logging.getLogger(__name__)


class InboxConsumerWorker:
    """
    Consumidor transaccional de resultados e intermediaciones del Facade.
    Lee de Redis Stream 'stream:booking:results' mediante Consumer Groups,
    aplica deduplicación idempotente en 'mcp.inbox_event', transiciona el agregado
    BookingRequest y libera holds cuando la operación concluye.
    """

    def __init__(
        self,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        redis_client: Optional[Redis] = None,
        hold_manager: Optional[RedisHoldManager] = None,
        stream_name: str = "stream:booking:results",
        group_name: str = "mcp_inbox_group",
        consumer_name: Optional[str] = None,
    ):
        self._session_factory = session_factory or get_session_factory()
        self._redis = redis_client or get_redis_client()
        self._hold_manager = hold_manager or RedisHoldManager(self._redis)
        self._stream_name = stream_name
        self._group_name = group_name
        self._consumer_name = consumer_name or f"mcp_inbox_{uuid4().hex[:8]}"

    async def ensure_group_exists(self) -> None:
        """Crea el Consumer Group en Redis si aún no existe."""
        try:
            await self._redis.xgroup_create(
                self._stream_name, self._group_name, id="0", mkstream=True
            )
        except Exception as e:
            # Si el grupo ya existe (BUSYGROUP), se ignora
            if "BUSYGROUP" not in str(e):
                logger.warning("Aviso creando consumer group %s: %s", self._group_name, e)

    async def process_message(self, msg_id: str, raw_fields: dict[str, Any]) -> bool:
        """
        Procesa un único mensaje de Redis Stream de forma idempotente y transaccional.
        """
        raw_payload = raw_fields.get("payload")
        if not raw_payload:
            await self._redis.xack(self._stream_name, self._group_name, msg_id)
            return True

        try:
            data = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
        except (json.JSONDecodeError, TypeError) as err:
            logger.error("Error decodificando payload de mensaje %s: %s", msg_id, err)
            await self._redis.xack(self._stream_name, self._group_name, msg_id)
            return False

        event_id_str = data.get("event_id")
        event_type = data.get("event_type")
        aggregate_id_str = data.get("aggregate_id") or data.get("booking_id")
        event_payload = data.get("payload") or {}

        if not event_id_str or not event_type:
            await self._redis.xack(self._stream_name, self._group_name, msg_id)
            return True

        try:
            event_id = UUID(event_id_str)
            booking_id = UUID(aggregate_id_str) if aggregate_id_str else None
        except (ValueError, TypeError) as err:
            logger.error("UUID inválido en mensaje %s: %s", msg_id, err)
            await self._redis.xack(self._stream_name, self._group_name, msg_id)
            return False

        now_utc = datetime.now(timezone.utc)

        async with self._session_factory() as session:
            async with session.begin():
                # 1. Comprobación idempotente en inbox_event
                inbox_entry = await session.get(InboxEventModel, event_id)
                if inbox_entry is not None and inbox_entry.processed_at is not None:
                    # Mensaje duplicado ya procesado: confirmar en Redis y salir
                    await self._redis.xack(self._stream_name, self._group_name, msg_id)
                    return True

                if inbox_entry is None:
                    inbox_entry = InboxEventModel(
                        event_id=event_id,
                        event_type=event_type,
                        aggregate_id=booking_id,
                        received_at=now_utc,
                        processed_at=None,
                    )
                    session.add(inbox_entry)

                # 2. Transición del agregado BookingRequest
                if booking_id:
                    repo = SqlBookingRepository(session)
                    booking = await repo.get_by_id(booking_id)

                    if booking:
                        release_hold_needed = False

                        if event_type == "BookingAccepted":
                            # Estado en trámite
                            booking.accept(
                                external_ref=event_payload.get("external_ref"),
                                assigned_details=event_payload.get("assigned_details")
                                or event_payload.get("details"),
                            )
                        elif event_type == "BookingConfirmed":
                            booking.confirm(
                                external_ref=event_payload.get("external_ref", ""),
                                assigned_details=event_payload.get("assigned_details"),
                            )
                            release_hold_needed = True
                        elif event_type == "BookingRejected":
                            booking.reject(
                                reason=event_payload.get(
                                    "reason", "Rechazada por el establecimiento"
                                )
                            )
                            release_hold_needed = True
                        elif event_type == "BookingFailed":
                            booking.fail(
                                reason=event_payload.get("reason", "Fallo técnico en trámite")
                            )
                            release_hold_needed = True
                        elif event_type == "CancellationConfirmed":
                            booking.confirm_cancellation()
                            release_hold_needed = True
                        elif event_type == "CancellationRejected":
                            booking.reject_cancellation(reason=event_payload.get("reason"))

                        await repo.save(booking)

                        if release_hold_needed and booking.offer_ref and self._hold_manager:
                            await self._hold_manager.release_hold(
                                booking.offer_ref, booking.id
                            )

                # 3. Marcar evento como procesado
                inbox_entry.processed_at = datetime.now(timezone.utc)

        # 4. Confirmar recepción en Redis Stream
        await self._redis.xack(self._stream_name, self._group_name, msg_id)
        return True

    async def consume_batch(self, count: int = 10, block_ms: int = 2000) -> int:
        """
        Lee y procesa un lote de mensajes pendientes o nuevos desde el Consumer Group.
        """
        await self.ensure_group_exists()

        try:
            stream_entries = await self._redis.xreadgroup(
                self._group_name,
                self._consumer_name,
                {self._stream_name: ">"},
                count=count,
                block=block_ms,
            )
        except Exception as err:
            logger.error("Error leyendo stream %s: %s", self._stream_name, err)
            return 0

        if not stream_entries:
            return 0

        processed_count = 0
        for _stream, messages in stream_entries:
            for msg_id, raw_fields in messages:
                ok = await self.process_message(msg_id, raw_fields)
                if ok:
                    processed_count += 1

        return processed_count

    async def run_forever(
        self,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        """Bucle continuo de consumo en segundo plano."""
        logger.info("Iniciando InboxConsumerWorker...")
        await self.ensure_group_exists()

        while stop_event is None or not stop_event.is_set():
            try:
                await self.consume_batch()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error en bucle de InboxConsumerWorker: %s", e)
                await asyncio.sleep(1.0)

        logger.info("InboxConsumerWorker detenido.")
