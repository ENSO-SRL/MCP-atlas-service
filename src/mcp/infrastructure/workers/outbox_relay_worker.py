from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.mcp.infrastructure.persistence.models.booking_models import OutboxEventModel
from src.mcp.infrastructure.redis.redis_bus_client import RedisBusClient
from src.shared.database.session import get_session_factory

logger = logging.getLogger(__name__)


class OutboxRelayWorker:
    """
    Worker transaccional en segundo plano para el patrón Transactional Outbox.
    Lee eventos pendientes en 'mcp.outbox_event' (SELECT ... FOR UPDATE SKIP LOCKED)
    y los publica de forma confiable en el Redis Stream 'stream:booking:events'.
    """

    def __init__(
        self,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        bus_client: Optional[RedisBusClient] = None,
        batch_size: int = 50,
        stream_name: str = "stream:booking:events",
    ):
        self._session_factory = session_factory or get_session_factory()
        self._bus_client = bus_client or RedisBusClient()
        self._batch_size = batch_size
        self._stream_name = stream_name

    async def relay_batch(self) -> int:
        """
        Procesa un lote de eventos outbox pendientes dentro de una transacción segura.
        Retorna la cantidad de eventos publicados en este ciclo.
        """
        async with self._session_factory() as session:
            async with session.begin():
                stmt = (
                    select(OutboxEventModel)
                    .where(OutboxEventModel.published_at.is_(None))
                    .order_by(OutboxEventModel.created_at.asc())
                    .limit(self._batch_size)
                    .with_for_update(skip_locked=True)
                )
                result = await session.execute(stmt)
                pending_events = result.scalars().all()

                if not pending_events:
                    return 0

                now_utc = datetime.now(timezone.utc)
                count = 0

                for event in pending_events:
                    envelope = {
                        "event_id": str(event.id),
                        "aggregate_id": str(event.aggregate_id),
                        "event_type": event.event_type,
                        "correlation_id": event.correlation_id,
                        "payload": event.payload,
                        "created_at": event.created_at.isoformat()
                        if event.created_at
                        else now_utc.isoformat(),
                    }

                    try:
                        await self._bus_client.publish_stream_event(
                            self._stream_name, envelope
                        )
                        event.published_at = now_utc
                        event.attempts += 1
                        count += 1
                    except Exception as err:
                        event.attempts += 1
                        logger.error(
                            "Error publicando outbox_event %s al stream %s: %s",
                            event.id,
                            self._stream_name,
                            err,
                        )

                return count

    async def run_forever(
        self,
        interval_seconds: float = 1.0,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        """Bucle continuo de publicación en segundo plano."""
        logger.info("Iniciando OutboxRelayWorker...")
        while stop_event is None or not stop_event.is_set():
            try:
                published = await self.relay_batch()
                if published == 0:
                    await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error en bucle de OutboxRelayWorker: %s", e)
                await asyncio.sleep(interval_seconds)
        logger.info("OutboxRelayWorker detenido.")
