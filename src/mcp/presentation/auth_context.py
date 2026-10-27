from dataclasses import dataclass, field
from contextvars import ContextVar
from typing import Any, Optional, Union
from uuid import UUID

import jwt

from mcp.server.mcpserver import Context
from src.mcp.domain.exceptions.mcp_exceptions import McpDomainException
from src.shared.config.settings import get_settings


class AuthenticationRequiredException(McpDomainException):
    """Lanzada cuando una solicitud a una herramienta MCP carece de credenciales válidas."""
    def __init__(self, message: str = "Autenticación requerida: se requiere token OAuth Bearer válido."):
        super().__init__(message)


class ForbiddenScopeException(McpDomainException):
    """Lanzada cuando el token carece del scope necesario para la operación solicitada."""
    def __init__(self, message: str = "Permisos insuficientes para invocar la herramienta solicitada."):
        super().__init__(message)


@dataclass(frozen=True)
class AuthenticatedUser:
    """Información del usuario autenticado resuelto desde el JWT OAuth o el contexto de ejecución."""
    user_uuid: UUID
    phone_number: Optional[str] = None
    email: Optional[str] = None
    scopes: list[str] = field(default_factory=list)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, UUID):
            return self.user_uuid == other
        if isinstance(other, AuthenticatedUser):
            return (
                self.user_uuid == other.user_uuid
                and self.phone_number == other.phone_number
            )
        return False


# Variable de contexto para inyección explícita en pruebas o middleware
current_user_context: ContextVar[Optional[Union[UUID, AuthenticatedUser]]] = ContextVar(
    "current_user_context", default=None
)


def extract_user_context(
    ctx: Optional[Context] = None,
    required_scope: Optional[str] = None,
) -> AuthenticatedUser:
    """
    Resuelve el usuario autenticado (UUID y teléfono) a partir del Context de MCP o la variable de contexto.
    Valida la firma criptográfica JWT, expiración y scopes requeridos (RFC 6749 / RFC 7519).
    """
    # 1. Verificar si hay un usuario fijado explícitamente en ContextVar (útil para tests y scripts)
    explicit_user = current_user_context.get()
    if explicit_user is not None:
        if isinstance(explicit_user, UUID):
            return AuthenticatedUser(user_uuid=explicit_user, phone_number=None)
        return explicit_user

    # 2. Extraer cabeceras HTTP desde el objeto Context de MCP (protegido contra ejecuciones fuera de request)
    headers: dict[str, str] = {}
    if ctx is not None:
        try:
            raw_headers = ctx.headers
            if raw_headers and isinstance(raw_headers, dict):
                headers = {k.lower(): str(v) for k, v in raw_headers.items()}
        except (ValueError, AttributeError):
            headers = {}

    # 3. Comprobar cabecera Authorization (Bearer JWT)
    auth_header = headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        raw_token = auth_header[7:].strip()
        settings = get_settings()
        try:
            claims = jwt.decode(
                raw_token,
                key=settings.OAUTH_JWT_SECRET_KEY,
                algorithms=[settings.OAUTH_JWT_ALGORITHM],
                options={"verify_exp": True},
            )
            sub = claims.get("sub")
            if not sub:
                raise AuthenticationRequiredException("El token JWT no contiene claim 'sub' válido.")

            token_scopes = (claims.get("scope") or "").split()
            if required_scope:
                if required_scope not in token_scopes:
                    raise ForbiddenScopeException(
                        f"Scope insuficiente: se requiere '{required_scope}' (scopes otorgados: {token_scopes})."
                    )

            phone = (
                claims.get("phone_number")
                or claims.get("phone")
                or claims.get("user_phone")
            )
            email = claims.get("email")

            return AuthenticatedUser(
                user_uuid=UUID(sub),
                phone_number=str(phone) if phone else None,
                email=str(email) if email else None,
                scopes=token_scopes,
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationRequiredException("El token de acceso OAuth ha expirado. Por favor renuévalo.")
        except jwt.PyJWTError as err:
            raise AuthenticationRequiredException(f"Token de acceso OAuth inválido: {err}")

    # 4. Comprobar cabeceras de conveniencia para pruebas / desarrollo (X-User-UUID, X-User-Phone)
    x_user = headers.get("x-user-uuid")
    if x_user:
        try:
            x_phone = headers.get("x-user-phone")
            return AuthenticatedUser(
                user_uuid=UUID(x_user),
                phone_number=x_phone,
            )
        except ValueError:
            raise AuthenticationRequiredException("Cabecera X-User-UUID inválida (no es un UUID válido).")

    # 5. Si no se proporcionaron credenciales
    raise AuthenticationRequiredException(
        "Autenticación requerida: debes suministrar un token OAuth 2.0 válido mediante 'Authorization: Bearer <jwt>'."
    )
