from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.mcp.infrastructure.persistence.models.booking_models import OutboxEventModel
from src.mcp.infrastructure.redis.redis_bus_client import RedisBusClient
from src.shared.config.settings import get_settings
from src.shared.database.session import get_session_factory

# Configurar logger con salida garantizada a stdout para que nunca quede silenciado
logger = logging.getLogger("mcp.outbox_relay")
logger.setLevel(logging.INFO)

if not logger.handlers:
    _console_handler = logging.StreamHandler(sys.stdout)
    _console_handler.setLevel(logging.INFO)
    _formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [OutboxRelay] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _console_handler.setFormatter(_formatter)
    logger.addHandler(_console_handler)


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

                logger.info(
                    "--> Encontrados %d evento(s) pendientes en 'mcp.outbox_event'. Iniciando retransmisión a Redis Stream '%s'...",
                    len(pending_events),
                    self._stream_name,
                )
                sys.stdout.flush()

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

                    service_id = None
                    offer_ref = None
                    if isinstance(event.payload, dict):
                        service_id = event.payload.get("service_id")
                        offer_ref = event.payload.get("offer_ref")

                    logger.info(
                        "[ENVIANDO A REDIS] stream='%s' | event_id=%s | type=%s | booking_id=%s | service_id=%s | offer_ref=%s | intento=%d",
                        self._stream_name,
                        event.id,
                        event.event_type,
                        event.aggregate_id,
                        service_id,
                        offer_ref,
                        event.attempts + 1,
                    )
                    sys.stdout.flush()

                    try:
                        redis_msg_id = await self._bus_client.publish_stream_event(
                            self._stream_name, envelope
                        )
                        event.published_at = now_utc
                        event.attempts += 1
                        count += 1

                        logger.info(
                            "[EXITO XADD] Evento entregado a Redis Stream! stream='%s' | redis_msg_id=%s | event_id=%s | booking_id=%s",
                            self._stream_name,
                            redis_msg_id,
                            event.id,
                            event.aggregate_id,
                        )
                        sys.stdout.flush()
                    except Exception as err:
                        event.attempts += 1
                        logger.error(
                            "[ERROR XADD] Falló la publicación en Redis Stream '%s': event_id=%s | error=%s",
                            self._stream_name,
                            event.id,
                            err,
                            exc_info=True,
                        )
                        sys.stdout.flush()

                logger.info(
                    "--> Lote outbox completado: %d/%d eventos publicados con éxito en '%s'.",
                    count,
                    len(pending_events),
                    self._stream_name,
                )
                sys.stdout.flush()
                return count

    async def run_forever(
        self,
        interval_seconds: float = 1.0,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        """Bucle continuo de publicación en segundo plano con heartbeat periódico."""
        logger.info(
            "======================================================================\n"
            "  OutboxRelayWorker INICIADO\n"
            "  Stream Redis:    '%s'\n"
            "  Tamaño de Lote:  %d\n"
            "  Intervalo:       %.1f seg\n"
            "======================================================================",
            self._stream_name,
            self._batch_size,
            interval_seconds,
        )
        sys.stdout.flush()

        idle_polls = 0
        while stop_event is None or not stop_event.is_set():
            try:
                published = await self.relay_batch()
                if published == 0:
                    idle_polls += 1
                    # Cada 30 sondeos en vacío (aprox 30s), emitir un heartbeat para confirmar actividad
                    if idle_polls % 30 == 0:
                        logger.info(
                            "[Heartbeat] OutboxRelayWorker activo y sondeando '%s' (0 eventos pendientes en este momento).",
                            self._stream_name,
                        )
                        sys.stdout.flush()
                    await asyncio.sleep(interval_seconds)
                else:
                    idle_polls = 0
                    logger.info(
                        "[Ciclo OK] %d evento(s) confirmados y actualizados en PostgreSQL.",
                        published,
                    )
                    sys.stdout.flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[Excepción Bucle Worker] %s", e, exc_info=True)
                sys.stdout.flush()
                await asyncio.sleep(interval_seconds)

        logger.info("OutboxRelayWorker detenido limpiamente.")
        sys.stdout.flush()


if __name__ == "__main__":
    from pathlib import Path

    # Asegurar sys.path si se invoca directamente con python outbox_relay_worker.py
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))

    import anyio

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    worker = OutboxRelayWorker()
    try:
        anyio.run(worker.run_forever)
    except KeyboardInterrupt:
        logger.info("OutboxRelayWorker interrumpido manualmente por el usuario.")
