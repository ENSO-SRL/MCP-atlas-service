from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse
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
        """
        Verifica si la redirect_uri recibida está autorizada para este cliente.

        Conforme a RFC 8252 Sección 7.3 (Loopback Interface Redirection), los clientes nativos
        pueden solicitar un puerto efímero asignado por el sistema operativo para interfaces de
        loopback (localhost, 127.0.0.1, ::1). Si un cliente tiene registrada una URI de loopback,
        se permite cualquier puerto en el mismo esquema, host de loopback y ruta.
        """
        if uri in self.redirect_uris:
            return True

        try:
            parsed = urlparse(uri)
            loopback_hosts = {"localhost", "127.0.0.1", "::1"}
            if parsed.hostname in loopback_hosts:
                for allowed in self.redirect_uris:
                    parsed_allowed = urlparse(allowed)
                    if (
                        parsed_allowed.hostname in loopback_hosts
                        and parsed.scheme == parsed_allowed.scheme
                        and parsed.path == parsed_allowed.path
                    ):
                        return True
        except Exception:
            return False

        return False
