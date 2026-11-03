from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

import jwt

from src.oauth.domain.ports.i_security_ports import ITokenIssuer
from src.shared.config.settings import get_settings


class JwtTokenIssuer(ITokenIssuer):
    """
    Implementación del emisor y validador de tokens de acceso JWT (RFC 7519).
    Genera tokens firmados con claims estándar ('sub', 'iss', 'iat', 'exp', 'scope')
    y claims de conveniencia ('phone_number', 'email') para el conector MCP.
    """

    def __init__(
        self,
        secret_key: Optional[str] = None,
        algorithm: Optional[str] = None,
        issuer: Optional[str] = None,
    ):
        settings = get_settings()
        self._secret_key = secret_key or settings.OAUTH_JWT_SECRET_KEY
        self._algorithm = algorithm or settings.OAUTH_JWT_ALGORITHM
        self._issuer = issuer or settings.OAUTH_ISSUER

    def create_access_token(
        self,
        user_uuid: UUID,
        scope: str,
        expires_in_seconds: int = 3600,
        extra_claims: Optional[dict[str, Any]] = None,
    ) -> str:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=expires_in_seconds)

        payload: dict[str, Any] = {
            "iss": self._issuer,
            "sub": str(user_uuid),
            "scope": scope,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }

        if extra_claims:
            for key, val in extra_claims.items():
                if key not in payload and val is not None:
                    payload[key] = val

        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def decode_and_validate_access_token(self, token_str: str) -> dict[str, Any]:
        return jwt.decode(
            token_str,
            key=self._secret_key,
            algorithms=[self._algorithm],
            options={"verify_exp": True},
        )

