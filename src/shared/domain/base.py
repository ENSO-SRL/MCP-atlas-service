from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar
from uuid import UUID, uuid4

EntityId = TypeVar("EntityId")


@dataclass(frozen=True)
class ValueObject(ABC):
    """Clase base inmutable para todos los Value Objects del sistema."""
    pass


@dataclass
class DomainEvent(ABC):
    """Clase base para todos los eventos de dominio."""
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Entity(Generic[EntityId], ABC):
    """Clase base para entidades con identidad propia."""
    id: EntityId

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, type(self)):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash((type(self), self.id))


@dataclass
class AggregateRoot(Entity[EntityId], ABC):
    """Entidad raíz de agregado capaz de recolectar y emitir eventos de dominio."""
    _domain_events: list[DomainEvent] = field(default_factory=list, init=False, repr=False)

    def record_event(self, event: DomainEvent) -> None:
        self._domain_events.append(event)

    def pull_domain_events(self) -> list[DomainEvent]:
        events = list(self._domain_events)
        self._domain_events.clear()
        return events
