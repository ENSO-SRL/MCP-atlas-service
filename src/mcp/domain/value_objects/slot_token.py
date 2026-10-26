from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from src.shared.domain.base import ValueObject


@dataclass(frozen=True)
class SlotToken(ValueObject):
    """
    Token de oferta opaco y firmado entregado a Claude en check_availability.
    Garantiza que la reserva provenga de un slot real, esté acotada temporalmente
    y no pueda ser reutilizada por otro usuario.
    """
    token_id: str
    user_uuid: UUID
    offer_ref: str
    service_id: int
    slot_start: datetime
    slot_end: Optional[datetime]
    contract_version: str
    expires_at: datetime
    raw_token: str
    applied_filters: dict[str, Any] = field(default_factory=dict)
    is_estimated: bool = False

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        current_time = now or datetime.now(timezone.utc)
        return current_time > self.expires_at

    def is_valid_for_user(self, user_uuid: UUID) -> bool:
        return self.user_uuid == user_uuid
