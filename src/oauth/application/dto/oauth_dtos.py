from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode
from uuid import UUID


@dataclass(frozen=True)
class UserLoginRequestDTO:
    """Credenciales enviadas en el formulario de inicio de sesión."""
    email: str
    password: str


@dataclass(frozen=True)
class UserAuthSessionDTO:
    """Sesión autenticada del usuario tras login exitoso."""
    user_uuid: UUID
    email: str
    name: str
    phone: Optional[str] = None


@dataclass(frozen=True)
class AuthorizeRequestDTO:
    """Parámetros de la solicitud de autorización OAuth 2.0 (RFC 6749 / RFC 7636)."""
    client_id: str
    redirect_uri: str
    response_type: str
    code_challenge: str
    code_challenge_method: str
    user_uuid: UUID
    scope: str = "bookings:read bookings:write profile"
    state: Optional[str] = None


@dataclass(frozen=True)
class AuthorizationCodeResultDTO:
    """Resultado de la emisión del código de autorización tras el consentimiento."""
    code: str
    redirect_uri: str
    state: Optional[str] = None

    @property
    def callback_url(self) -> str:
        """Construye la URL de redirección con parámetros de consulta estándar."""
        params = {"code": self.code}
        if self.state:
            params["state"] = self.state
        separator = "&" if "?" in self.redirect_uri else "?"
        return f"{self.redirect_uri}{separator}{urlencode(params)}"


@dataclass(frozen=True)
class TokenExchangeRequestDTO:
    """Parámetros para el canje de código por tokens en /oauth/token."""
    grant_type: str
    client_id: str
    code: str
    code_verifier: str
    redirect_uri: str


@dataclass(frozen=True)
class TokenRefreshRequestDTO:
    """Parámetros para la renovación de tokens en /oauth/token."""
    grant_type: str
    client_id: str
    refresh_token: str


@dataclass(frozen=True)
class TokenResponseDTO:
    """Respuesta estándar JSON de emisión de tokens OAuth 2.0."""
    access_token: str
    refresh_token: str
    expires_in: int = 3600
    token_type: str = "Bearer"
    scope: str = "bookings:read bookings:write profile"

    def to_dict(self) -> dict[str, object]:
        return {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            "refresh_token": self.refresh_token,
            "scope": self.scope,
        }


@dataclass(frozen=True)
class RevokeTokenRequestDTO:
    """Parámetros para revocar un token (RFC 7009)."""
    token: str
    client_id: str
    token_type_hint: Optional[str] = None


@dataclass(frozen=True)
class UserInfoDTO:
    """Información del perfil del usuario autenticado (/oauth/userinfo)."""
    sub: str
    email: str
    name: str
    phone_number: Optional[str] = None
    is_confirmed: bool = True

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "sub": self.sub,
            "email": self.email,
            "name": self.name,
            "email_verified": self.is_confirmed,
        }
        if self.phone_number:
            data["phone_number"] = self.phone_number
        return data

