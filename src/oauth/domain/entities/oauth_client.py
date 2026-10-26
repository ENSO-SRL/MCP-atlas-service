from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from src.shared.domain.base import Entity


@dataclass
class OAuthClient(Entity[str]):
    """
    Entidad OAuthClient que representa una aplicación cliente registrada (ej. Claude Desktop, Claude.ai).
    'id' corresponde al 'client_id'.
    """
    client_name: str = ""
    redirect_uris: list[str] = field(default_factory=list)
    client_secret_hash: Optional[str] = None
    is_confidential: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_redirect_uri_allowed(self, uri: str) -> bool:
        """Verifica si la redirect_uri recibida está explícitamente autorizada para este cliente."""
        return uri in self.redirect_uris
