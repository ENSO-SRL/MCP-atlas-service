from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from src.oauth.domain.value_objects.pkce_challenge import PKCEChallenge
from src.shared.domain.base import Entity


@dataclass
class AuthorizationCode(Entity[str]):
    """
    Entidad AuthorizationCode para códigos de autorización efímeros (RFC 6749 / RFC 7636).
    'id' corresponde al string criptográfico del 'code'.
    """
    client_id: str = ""
    user_uuid: UUID = field(default_factory=uuid4)
    redirect_uri: str = ""
    scope: str = "bookings:read bookings:write profile"
    challenge: PKCEChallenge = field(default_factory=lambda: PKCEChallenge("dummy"))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    used_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        current_time = now or datetime.now(timezone.utc)
        return current_time > self.expires_at

    def is_used(self) -> bool:
        return self.used_at is not None

    def consume(self, code_verifier: str, now: Optional[datetime] = None) -> bool:
        """
        Valida que el código esté vigente, no haya sido usado y que el code_verifier
        satisfaga el PKCE S256. Si es válido, lo marca como usado de inmediato.
        """
        current_time = now or datetime.now(timezone.utc)
        if self.is_used() or self.is_expired(current_time):
            return False

        if not self.challenge.verify(code_verifier):
            return False

        self.used_at = current_time
        return True
