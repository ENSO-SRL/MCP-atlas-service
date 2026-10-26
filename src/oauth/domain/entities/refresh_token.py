from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4
from src.shared.domain.base import Entity


@dataclass
class RefreshToken(Entity[str]):
    """
    Entidad RefreshToken que representa un token de actualización con rotación.
    'id' corresponde al hash seguro del token (token_hash).
    """
    client_id: str = ""
    user_uuid: UUID = field(default_factory=uuid4)
    scope: str = "bookings:read bookings:write profile"
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    revoked_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        current_time = now or datetime.now(timezone.utc)
        return current_time > self.expires_at

    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_valid(self, now: Optional[datetime] = None) -> bool:
        return not self.is_revoked() and not self.is_expired(now)

    def revoke(self, now: Optional[datetime] = None) -> None:
        self.revoked_at = now or datetime.now(timezone.utc)
