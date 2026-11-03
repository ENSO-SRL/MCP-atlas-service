from __future__ import annotations

import base64
import hashlib
from unittest.mock import AsyncMock
from uuid import UUID
import pytest
from httpx import ASGITransport, AsyncClient

from src.oauth.application.dto.oauth_dtos import (
    AuthorizationCodeResultDTO,
    TokenResponseDTO,
    UserAuthSessionDTO,
    UserInfoDTO,
)
from src.oauth.application.use_cases.authenticate_user import AuthenticateUserUseCase
from src.oauth.application.use_cases.exchange_token import ExchangeTokenUseCase
from src.oauth.application.use_cases.generate_authorization_code import (
    GenerateAuthorizationCodeUseCase,
)
from src.oauth.application.use_cases.get_user_info import GetUserInfoUseCase
from src.oauth.application.use_cases.refresh_token import RefreshTokenUseCase
from src.oauth.application.use_cases.revoke_token import RevokeTokenUseCase
from src.oauth.domain.entities.oauth_client import OAuthClient
from src.oauth.domain.entities.user import User
from src.oauth.domain.exceptions.auth_exceptions import (
    ExpiredAuthorizationCodeException,
    InvalidCredentialsException,
)
from src.oauth.domain.ports.i_oauth_client_repository import IOAuthClientRepository
from src.oauth.domain.value_objects.email_address import EmailAddress
from src.oauth.domain.value_objects.phone_number_e164 import PhoneNumberE164
from src.oauth.presentation.app import app
from src.oauth.presentation.dependencies import (
    get_authenticate_user_use_case,
    get_exchange_token_use_case,
    get_generate_authorization_code_use_case,
    get_oauth_client_repository,
    get_refresh_token_use_case,
    get_revoke_token_use_case,
    get_token_issuer,
    get_user_info_use_case,
)
from src.oauth.presentation.session_manager import create_session_token


@pytest.fixture
def sample_client() -> OAuthClient:
    return OAuthClient(
        id="claude-desktop",
        client_name="Claude Desktop",
        redirect_uris=["http://localhost:8000/callback", "https://claude.ai/oauth/callback"],
        client_secret_hash=None,
        is_confidential=False,
    )


@pytest.fixture
def sample_user() -> User:
    return User(
        id=1,
        uuid=UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
        email=EmailAddress("juan.perez@example.com"),
        hashed_password="$2b$12$eXampleHashedPasswordForTestOnly99999999999999999999999",
        name="Juan Pérez",
        phone=PhoneNumberE164("+18094251911"),
        is_active=True,
        is_confirmed=True,
    )


@pytest.fixture
def mock_client_repo(sample_client: OAuthClient) -> AsyncMock:
    repo = AsyncMock(spec=IOAuthClientRepository)

    async def get_by_client_id(cid: str):
        if cid == sample_client.id:
            return sample_client
        return None

    repo.get_by_client_id.side_effect = get_by_client_id
    return repo


@pytest.fixture
def pkce_pair() -> tuple[str, str]:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


@pytest.mark.asyncio
async def test_oauth_metadata_discovery():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/.well-known/oauth-authorization-server")
        assert res.status_code == 200
        data = res.json()
        assert "issuer" in data
        assert "authorization_endpoint" in data
        assert "token_endpoint" in data
        assert "S256" in data["code_challenge_methods_supported"]
        assert "authorization_code" in data["grant_types_supported"]


@pytest.mark.asyncio
async def test_static_css_and_assets():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/static/auth.css")
        assert res.status_code == 200
        assert "login-wrapper" in res.text
        assert "#DA007C" in res.text

        res_logo = await client.get("/static/atlas.svg")
        assert res_logo.status_code == 200


@pytest.mark.asyncio
async def test_authorize_get_invalid_client(mock_client_repo: AsyncMock):
    app.dependency_overrides[get_oauth_client_repository] = lambda: mock_client_repo
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.get(
                "/oauth/authorize",
                params={
                    "client_id": "non-existent-client",
                    "redirect_uri": "http://localhost:8000/callback",
                    "response_type": "code",
                    "code_challenge": "some-challenge",
                    "code_challenge_method": "S256",
                },
            )
            assert res.status_code == 400
            assert "invalid_client" in res.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_authorize_get_unauthorized_redirect_uri(mock_client_repo: AsyncMock):
    app.dependency_overrides[get_oauth_client_repository] = lambda: mock_client_repo
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.get(
                "/oauth/authorize",
                params={
                    "client_id": "claude-desktop",
                    "redirect_uri": "http://evil-site.com/callback",
                    "response_type": "code",
                    "code_challenge": "some-challenge",
                    "code_challenge_method": "S256",
                },
            )
            assert res.status_code == 400
            assert "invalid_request" in res.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_authorize_get_renders_login_page_when_no_session(
    mock_client_repo: AsyncMock, pkce_pair: tuple[str, str]
):
    _, challenge = pkce_pair
    app.dependency_overrides[get_oauth_client_repository] = lambda: mock_client_repo
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.get(
                "/oauth/authorize",
                params={
                    "client_id": "claude-desktop",
                    "redirect_uri": "http://localhost:8000/callback",
                    "response_type": "code",
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "state": "xyz123",
                },
            )
            assert res.status_code == 200
            assert "¡Bienvenido de nuevo!" in res.text
            assert 'name="email"' in res.text
            assert 'name="password"' in res.text
            assert f'value="{challenge}"' in res.text
            assert 'value="xyz123"' in res.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_login_post_invalid_credentials():
    mock_auth_uc = AsyncMock(spec=AuthenticateUserUseCase)
    mock_auth_uc.execute.side_effect = InvalidCredentialsException("Credenciales incorrectas")

    app.dependency_overrides[get_authenticate_user_use_case] = lambda: mock_auth_uc
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.post(
                "/oauth/login",
                data={
                    "email": "wrong@example.com",
                    "password": "badpassword",
                    "client_id": "claude-desktop",
                    "redirect_uri": "http://localhost:8000/callback",
                    "scope": "bookings:read",
                    "state": "test_state",
                    "code_challenge": "challenge",
                    "code_challenge_method": "S256",
                },
            )
            assert res.status_code == 401
            assert "Correo electrónico o contraseña incorrectos" in res.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_login_post_success_sets_cookie_and_redirects(sample_user: User):
    mock_auth_uc = AsyncMock(spec=AuthenticateUserUseCase)
    mock_auth_uc.execute.return_value = UserAuthSessionDTO(
        user_uuid=sample_user.uuid,
        email=str(sample_user.email),
        name=sample_user.name,
        phone=str(sample_user.phone),
    )

    app.dependency_overrides[get_authenticate_user_use_case] = lambda: mock_auth_uc
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver", follow_redirects=False) as client:
            res = await client.post(
                "/oauth/login",
                data={
                    "email": "juan.perez@example.com",
                    "password": "validpassword",
                    "client_id": "claude-desktop",
                    "redirect_uri": "http://localhost:8000/callback",
                    "scope": "bookings:read",
                    "state": "state123",
                    "code_challenge": "challenge123",
                    "code_challenge_method": "S256",
                },
            )
            assert res.status_code == 303
            assert "atlas_oauth_session" in res.cookies
            location = res.headers["location"]
            assert "/oauth/authorize" in location
            assert "client_id=claude-desktop" in location
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_authorize_get_renders_consent_page_with_active_session(
    mock_client_repo: AsyncMock, sample_user: User, pkce_pair: tuple[str, str]
):
    _, challenge = pkce_pair
    session_token = create_session_token(
        user_uuid=str(sample_user.uuid),
        email=str(sample_user.email),
        name=sample_user.name,
    )

    app.dependency_overrides[get_oauth_client_repository] = lambda: mock_client_repo
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            cookies={"atlas_oauth_session": session_token},
        ) as client:
            res = await client.get(
                "/oauth/authorize",
                params={
                    "client_id": "claude-desktop",
                    "redirect_uri": "http://localhost:8000/callback",
                    "response_type": "code",
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "state": "state_consent",
                    "scope": "bookings:read bookings:write profile",
                },
            )
            assert res.status_code == 200
            assert "Autorizar Conexión" in res.text
            assert "Claude Desktop" in res.text
            assert "juan.perez@example.com" in res.text
            assert "Consultar disponibilidad y reservas" in res.text
            assert "Autorizar acceso" in res.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_consent_post_deny(mock_client_repo: AsyncMock, sample_user: User):
    session_token = create_session_token(
        user_uuid=str(sample_user.uuid),
        email=str(sample_user.email),
        name=sample_user.name,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={"atlas_oauth_session": session_token},
        follow_redirects=False,
    ) as client:
        res = await client.post(
            "/oauth/consent",
            data={
                "action": "deny",
                "client_id": "claude-desktop",
                "redirect_uri": "http://localhost:8000/callback",
                "scope": "bookings:read",
                "state": "mystate",
            },
        )
        assert res.status_code == 302
        location = res.headers["location"]
        assert "error=access_denied" in location
        assert "state=mystate" in location


@pytest.mark.asyncio
async def test_consent_post_allow(sample_user: User):
    session_token = create_session_token(
        user_uuid=str(sample_user.uuid),
        email=str(sample_user.email),
        name=sample_user.name,
    )

    mock_generate_code = AsyncMock(spec=GenerateAuthorizationCodeUseCase)
    mock_generate_code.execute.return_value = AuthorizationCodeResultDTO(
        code="auth_code_xyz",
        redirect_uri="http://localhost:8000/callback",
        state="mystate",
    )

    app.dependency_overrides[get_generate_authorization_code_use_case] = lambda: mock_generate_code
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            cookies={"atlas_oauth_session": session_token},
            follow_redirects=False,
        ) as client:
            res = await client.post(
                "/oauth/consent",
                data={
                    "action": "allow",
                    "client_id": "claude-desktop",
                    "redirect_uri": "http://localhost:8000/callback",
                    "scope": "bookings:read bookings:write profile",
                    "state": "mystate",
                    "code_challenge": "challenge",
                    "code_challenge_method": "S256",
                },
            )
            assert res.status_code == 302
            assert res.headers["location"] == "http://localhost:8000/callback?code=auth_code_xyz&state=mystate"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_token_exchange_authorization_code_success():
    mock_exchange = AsyncMock(spec=ExchangeTokenUseCase)
    mock_exchange.execute.return_value = TokenResponseDTO(
        access_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy_access",
        token_type="Bearer",
        expires_in=3600,
        refresh_token="ref_tok_12345",
        scope="bookings:read profile",
    )

    app.dependency_overrides[get_exchange_token_use_case] = lambda: mock_exchange
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.post(
                "/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": "auth_code_xyz",
                    "redirect_uri": "http://localhost:8000/callback",
                    "client_id": "claude-desktop",
                    "code_verifier": "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
                },
            )
            assert res.status_code == 200
            data = res.json()
            assert data["access_token"] == "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy_access"
            assert data["token_type"] == "Bearer"
            assert data["refresh_token"] == "ref_tok_12345"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_token_exchange_invalid_code():
    mock_exchange = AsyncMock(spec=ExchangeTokenUseCase)
    mock_exchange.execute.side_effect = ExpiredAuthorizationCodeException("Código expirado o inválido")

    app.dependency_overrides[get_exchange_token_use_case] = lambda: mock_exchange
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.post(
                "/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": "invalid_code",
                    "redirect_uri": "http://localhost:8000/callback",
                    "client_id": "claude-desktop",
                    "code_verifier": "verifier",
                },
            )
            assert res.status_code == 400
            data = res.json()
            assert data["error"] == "invalid_grant"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_token_refresh_success():
    mock_refresh = AsyncMock(spec=RefreshTokenUseCase)
    mock_refresh.execute.return_value = TokenResponseDTO(
        access_token="new_access_token_abc",
        token_type="Bearer",
        expires_in=3600,
        refresh_token="new_refresh_token_xyz",
        scope="bookings:read profile",
    )

    app.dependency_overrides[get_refresh_token_use_case] = lambda: mock_refresh
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.post(
                "/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": "claude-desktop",
                    "refresh_token": "valid_refresh_tok",
                },
            )
            assert res.status_code == 200
            data = res.json()
            assert data["access_token"] == "new_access_token_abc"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_revoke_token():
    mock_revoke = AsyncMock(spec=RevokeTokenUseCase)

    app.dependency_overrides[get_revoke_token_use_case] = lambda: mock_revoke
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.post(
                "/oauth/revoke",
                data={"token": "tok_to_revoke"},
            )
            assert res.status_code == 200
            assert res.json() == {"status": "revoked"}
            assert mock_revoke.execute.await_count == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_userinfo_endpoint(sample_user: User):
    token_issuer = get_token_issuer()
    access_token = token_issuer.create_access_token(
        user_uuid=sample_user.uuid,
        scope="bookings:read profile",
        expires_in_seconds=3600,
    )

    mock_user_info = AsyncMock(spec=GetUserInfoUseCase)
    mock_user_info.execute.return_value = UserInfoDTO(
        sub=str(sample_user.uuid),
        email="juan.perez@example.com",
        name="Juan Pérez",
        phone_number="+18094251911",
        is_confirmed=True,
    )

    app.dependency_overrides[get_user_info_use_case] = lambda: mock_user_info
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.get(
                "/oauth/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["email"] == "juan.perez@example.com"
            assert data["name"] == "Juan Pérez"
            assert data["phone_number"] == "+18094251911"
    finally:
        app.dependency_overrides.clear()
