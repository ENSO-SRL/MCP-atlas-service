from __future__ import annotations

import pytest
from uuid import UUID, uuid4
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport
from starlette.datastructures import Headers

from src.main import create_unified_app
from src.mcp.presentation.auth_context import (
    AuthenticatedUser,
    AuthenticationRequiredException,
    ForbiddenScopeException,
    extract_user_context,
)
from src.oauth.infrastructure.security.jwt_token_issuer import JwtTokenIssuer
from src.shared.config.settings import get_settings


@pytest.mark.asyncio
async def test_unified_app_root_and_discovery():
    """Verifica que la app unificada exponga tanto el root endpoint como los metadatos OAuth RFC 8414."""
    app = create_unified_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Health / Root
        res_root = await client.get("/")
        assert res_root.status_code == 200
        root_data = res_root.json()
        assert root_data["status"] == "online"
        assert "/sse" in root_data["endpoints"]["mcp_sse"]
        assert "/oauth/authorize" in root_data["endpoints"]["oauth_authorize"]

        # 2. Discovery OAuth 2.0
        res_disc = await client.get("/.well-known/oauth-authorization-server")
        assert res_disc.status_code == 200
        disc_data = res_disc.json()
        assert "http://testserver" in disc_data["issuer"]
        assert "/oauth/authorize" in disc_data["authorization_endpoint"]
        assert "/oauth/token" in disc_data["token_endpoint"]
        assert "S256" in disc_data["code_challenge_methods_supported"]


def test_extract_user_context_with_oauth_jwt():
    """Verifica la validación criptográfica del JWT y la extracción de la identidad real del usuario."""
    settings = get_settings()
    issuer = JwtTokenIssuer(
        secret_key=settings.OAUTH_JWT_SECRET_KEY,
        algorithm=settings.OAUTH_JWT_ALGORITHM,
        issuer=settings.OAUTH_ISSUER,
    )

    test_user_uuid = uuid4()
    token = issuer.create_access_token(
        user_uuid=test_user_uuid,
        scope="bookings:read bookings:write profile",
        expires_in_seconds=3600,
        extra_claims={
            "phone_number": "whatsapp:+18098013413",
            "email": "infocriscuervo@gmail.com",
            "name": "Cris Cuervo",
        },
    )

    # 1. Contexto simulando request HTTP
    mock_ctx = MagicMock()
    mock_ctx.headers = {"Authorization": f"Bearer {token}"}

    user = extract_user_context(mock_ctx, required_scope="bookings:read")
    assert isinstance(user, AuthenticatedUser)
    assert user.user_uuid == test_user_uuid
    assert user.email == "infocriscuervo@gmail.com"
    # Verifica que el prefijo whatsapp: se haya limpiado automáticamente
    assert user.phone_number == "+18098013413"
    assert user.name == "Cris Cuervo"
    assert "bookings:read" in user.scopes
    assert "bookings:write" in user.scopes

    # 2. Scope no concedido debe lanzar ForbiddenScopeException
    with pytest.raises(ForbiddenScopeException) as exc_info:
        extract_user_context(mock_ctx, required_scope="admin:superuser")
    assert "Scope insuficiente" in str(exc_info.value)


def test_extract_user_context_starlette_headers_support():
    """Verifica que el extractor de contexto soporte instancias de starlette.datastructures.Headers."""
    settings = get_settings()
    issuer = JwtTokenIssuer(
        secret_key=settings.OAUTH_JWT_SECRET_KEY,
        algorithm=settings.OAUTH_JWT_ALGORITHM,
        issuer=settings.OAUTH_ISSUER,
    )

    test_user_uuid = uuid4()
    token = issuer.create_access_token(
        user_uuid=test_user_uuid,
        scope="bookings:read bookings:write",
        expires_in_seconds=1800,
        extra_claims={
            "phone_number": "+18095551234",
            "email": "usuario.real@atlas.com",
            "name": "Usuario Real",
        },
    )

    # Objeto Headers nativo de Starlette (Mapping, no dict)
    starlette_headers = Headers({"authorization": f"Bearer {token}"})

    mock_ctx = MagicMock()
    mock_ctx.headers = starlette_headers

    user = extract_user_context(mock_ctx, required_scope="bookings:write")
    assert user.user_uuid == test_user_uuid
    assert user.email == "usuario.real@atlas.com"
    assert user.phone_number == "+18095551234"
    assert user.name == "Usuario Real"

