from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from src.mcp.domain.ports.mcp_ports import IOutboxRepository
from src.mcp.infrastructure.persistence.models.booking_models import OutboxEventModel


class SqlOutboxRepository(IOutboxRepository):
    """
    Implementación SQL del puerto IOutboxRepository (patrón Transactional Outbox).
    Inserta eventos pendientes de publicación dentro de la misma transacción ACID de la reserva.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def record_event(
        self,
        event_type: str,
        aggregate_id: UUID,
        payload: dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> None:
        event_entry = OutboxEventModel(
            id=uuid4(),
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            correlation_id=correlation_id,
            created_at=datetime.now(timezone.utc),
            published_at=None,
            attempts=0,
        )
        self._session.add(event_entry)
        await self._session.flush()
