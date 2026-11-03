from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.oauth.application.dto import (
    AuthorizeRequestDTO,
    RevokeTokenRequestDTO,
    TokenExchangeRequestDTO,
    TokenRefreshRequestDTO,
    UserLoginRequestDTO,
)
from src.oauth.application.use_cases import (
    AuthenticateUserUseCase,
    ExchangeTokenUseCase,
    GenerateAuthorizationCodeUseCase,
    GetUserInfoUseCase,
    RefreshTokenUseCase,
    RevokeTokenUseCase,
)
from src.oauth.domain.entities.authorization_code import AuthorizationCode
from src.oauth.domain.entities.oauth_client import OAuthClient
from src.oauth.domain.entities.refresh_token import RefreshToken
from src.oauth.domain.entities.user import User
from src.oauth.domain.enums.user_role import UserRole
from src.oauth.domain.exceptions.auth_exceptions import (
    AuthDomainException,
    ExpiredAuthorizationCodeException,
    InvalidClientException,
    InvalidCredentialsException,
    InvalidPKCEException,
    InvalidRedirectUriException,
    InvalidRefreshTokenException,
    UserInactiveException,
)
from src.oauth.domain.value_objects.email_address import EmailAddress
from src.oauth.domain.value_objects.phone_number_e164 import PhoneNumberE164
from src.oauth.domain.value_objects.pkce_challenge import PKCEChallenge


def _create_pkce_pair(verifier: str = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


# =========================================================================
# 1. Pruebas de AuthenticateUserUseCase
# =========================================================================

async def test_authenticate_user_success():
    user_repo = AsyncMock()
    hasher = MagicMock()
    u_uuid = uuid4()

    mock_user = User(
        id=1,
        uuid=u_uuid,
        email=EmailAddress("socio@atlas.com"),
        hashed_password="$2b$12$hashed",
        name="Socio",
        last_name="Activo",
        phone=PhoneNumberE164("+18095551234"),
        is_active=True,
        is_confirmed=True,
    )
    user_repo.get_by_email.return_value = mock_user
    hasher.verify_password.return_value = True

    use_case = AuthenticateUserUseCase(user_repo, hasher)
    session = await use_case.execute(UserLoginRequestDTO(email="socio@atlas.com", password="Password123!"))

    assert session.user_uuid == u_uuid
    assert session.email == "socio@atlas.com"
    assert session.name == "Socio Activo"
    assert session.phone == "+18095551234"
    hasher.verify_password.assert_called_once_with("Password123!", "$2b$12$hashed")


async def test_authenticate_user_wrong_password():
    user_repo = AsyncMock()
    hasher = MagicMock()

    mock_user = User(
        id=1,
        uuid=uuid4(),
        email=EmailAddress("socio@atlas.com"),
        hashed_password="$2b$12$hashed",
        name="Socio",
        last_name="Activo",
        is_active=True,
    )
    user_repo.get_by_email.return_value = mock_user
    hasher.verify_password.return_value = False

    use_case = AuthenticateUserUseCase(user_repo, hasher)
    with pytest.raises(InvalidCredentialsException):
        await use_case.execute(UserLoginRequestDTO(email="socio@atlas.com", password="WrongPassword"))


async def test_authenticate_user_not_found():
    user_repo = AsyncMock()
    hasher = MagicMock()
    user_repo.get_by_email.return_value = None

    use_case = AuthenticateUserUseCase(user_repo, hasher)
    with pytest.raises(InvalidCredentialsException):
        await use_case.execute(UserLoginRequestDTO(email="inexistente@atlas.com", password="Password123!"))


async def test_authenticate_user_inactive_or_cancelled():
    user_repo = AsyncMock()
    hasher = MagicMock()

    mock_user = User(
        id=1,
        uuid=uuid4(),
        email=EmailAddress("socio@atlas.com"),
        hashed_password="$2b$12$hashed",
        name="Socio",
        last_name="Inactivo",
        is_active=False,
    )
    user_repo.get_by_email.return_value = mock_user
    hasher.verify_password.return_value = True

    use_case = AuthenticateUserUseCase(user_repo, hasher)
    with pytest.raises(UserInactiveException):
        await use_case.execute(UserLoginRequestDTO(email="socio@atlas.com", password="Password123!"))


# =========================================================================
# 2. Pruebas de GenerateAuthorizationCodeUseCase
# =========================================================================

async def test_generate_authorization_code_success():
    client_repo = AsyncMock()
    token_repo = AsyncMock()
    user_repo = AsyncMock()

    client = OAuthClient(
        id="claude-desktop",
        client_name="Claude Desktop",
        redirect_uris=["https://claude.ai/api/oauth/callback"],
    )
    client_repo.get_by_client_id.return_value = client

    u_uuid = uuid4()
    mock_user = User(id=1, uuid=u_uuid, email=EmailAddress("u@a.com"), is_active=True)
    user_repo.get_by_uuid.return_value = mock_user

    verifier, challenge = _create_pkce_pair()
    req = AuthorizeRequestDTO(
        client_id="claude-desktop",
        redirect_uri="https://claude.ai/api/oauth/callback",
        response_type="code",
        code_challenge=challenge,
        code_challenge_method="S256",
        user_uuid=u_uuid,
        state="state-123",
    )

    use_case = GenerateAuthorizationCodeUseCase(client_repo, token_repo, user_repo)
    result = await use_case.execute(req)

    assert result.code.startswith("auth_code_")
    assert result.redirect_uri == "https://claude.ai/api/oauth/callback"
    assert result.state == "state-123"
    assert "code=" in result.callback_url
    assert "state=state-123" in result.callback_url
    token_repo.save_code.assert_awaited_once()


async def test_generate_authorization_code_invalid_client_or_uri():
    client_repo = AsyncMock()
    token_repo = AsyncMock()
    user_repo = AsyncMock()

    client = OAuthClient(
        id="claude-desktop",
        client_name="Claude Desktop",
        redirect_uris=["https://claude.ai/api/oauth/callback"],
    )
    client_repo.get_by_client_id.return_value = client

    verifier, challenge = _create_pkce_pair()
    req_bad_uri = AuthorizeRequestDTO(
        client_id="claude-desktop",
        redirect_uri="https://evil.attacker.com/cb",
        response_type="code",
        code_challenge=challenge,
        code_challenge_method="S256",
        user_uuid=uuid4(),
    )

    use_case = GenerateAuthorizationCodeUseCase(client_repo, token_repo, user_repo)
    with pytest.raises(InvalidRedirectUriException):
        await use_case.execute(req_bad_uri)

    # Cliente no existe
    client_repo.get_by_client_id.return_value = None
    with pytest.raises(InvalidClientException):
        await use_case.execute(req_bad_uri)


# =========================================================================
# 3. Pruebas de ExchangeTokenUseCase
# =========================================================================

async def test_exchange_token_success():
    client_repo = AsyncMock()
    token_repo = AsyncMock()
    user_repo = AsyncMock()
    token_issuer = MagicMock()

    client = OAuthClient(
        id="claude-desktop",
        client_name="Claude Desktop",
        redirect_uris=["https://claude.ai/cb"],
    )
    client_repo.get_by_client_id.return_value = client

    verifier, challenge = _create_pkce_pair()
    u_uuid = uuid4()
    now = datetime.now(timezone.utc)

    auth_code = AuthorizationCode(
        id="auth_code_xyz",
        client_id="claude-desktop",
        user_uuid=u_uuid,
        redirect_uri="https://claude.ai/cb",
        scope="bookings:read bookings:write",
        challenge=PKCEChallenge(challenge, "S256"),
        expires_at=now + timedelta(minutes=5),
        created_at=now,
    )
    token_repo.get_code.return_value = auth_code

    mock_user = User(
        id=1,
        uuid=u_uuid,
        email=EmailAddress("user@atlas.com"),
        name="User",
        last_name="Test",
        phone=PhoneNumberE164("+18091112222"),
        is_active=True,
    )
    user_repo.get_by_uuid.return_value = mock_user
    token_issuer.create_access_token.return_value = "jwt_access_token_123"

    req = TokenExchangeRequestDTO(
        grant_type="authorization_code",
        client_id="claude-desktop",
        code="auth_code_xyz",
        code_verifier=verifier,
        redirect_uri="https://claude.ai/cb",
    )

    use_case = ExchangeTokenUseCase(client_repo, token_repo, user_repo, token_issuer)
    res = await use_case.execute(req)

    assert res.access_token == "jwt_access_token_123"
    assert res.refresh_token.startswith("rt_")
    assert res.token_type == "Bearer"
    assert res.scope == "bookings:read bookings:write"
    assert auth_code.is_used() is True
    token_repo.update_code.assert_awaited_once_with(auth_code)
    token_repo.save_refresh_token.assert_awaited_once()


async def test_exchange_token_invalid_pkce_verifier():
    client_repo = AsyncMock()
    token_repo = AsyncMock()
    user_repo = AsyncMock()
    token_issuer = MagicMock()

    client_repo.get_by_client_id.return_value = OAuthClient(id="claude", redirect_uris=["https://cb.com"])
    verifier, challenge = _create_pkce_pair()
    u_uuid = uuid4()
    now = datetime.now(timezone.utc)

    auth_code = AuthorizationCode(
        id="auth_code_xyz",
        client_id="claude",
        user_uuid=u_uuid,
        redirect_uri="https://cb.com",
        challenge=PKCEChallenge(challenge, "S256"),
        expires_at=now + timedelta(minutes=5),
        created_at=now,
    )
    token_repo.get_code.return_value = auth_code

    req = TokenExchangeRequestDTO(
        grant_type="authorization_code",
        client_id="claude",
        code="auth_code_xyz",
        code_verifier="wrong-verifier-123456789012345678901234567890",
        redirect_uri="https://cb.com",
    )

    use_case = ExchangeTokenUseCase(client_repo, token_repo, user_repo, token_issuer)
    with pytest.raises(InvalidPKCEException):
        await use_case.execute(req)


async def test_exchange_token_code_expired_or_already_used():
    client_repo = AsyncMock()
    token_repo = AsyncMock()
    user_repo = AsyncMock()
    token_issuer = MagicMock()

    client_repo.get_by_client_id.return_value = OAuthClient(id="claude", redirect_uris=["https://cb.com"])
    verifier, challenge = _create_pkce_pair()
    now = datetime.now(timezone.utc)

    # 1. Ya usado
    used_code = AuthorizationCode(
        id="code_used",
        client_id="claude",
        redirect_uri="https://cb.com",
        challenge=PKCEChallenge(challenge, "S256"),
        expires_at=now + timedelta(minutes=5),
        used_at=now,
    )
    token_repo.get_code.return_value = used_code

    req = TokenExchangeRequestDTO(
        grant_type="authorization_code",
        client_id="claude",
        code="code_used",
        code_verifier=verifier,
        redirect_uri="https://cb.com",
    )
    use_case = ExchangeTokenUseCase(client_repo, token_repo, user_repo, token_issuer)
    with pytest.raises(ExpiredAuthorizationCodeException):
        await use_case.execute(req)

    # 2. Expirado
    expired_code = AuthorizationCode(
        id="code_exp",
        client_id="claude",
        redirect_uri="https://cb.com",
        challenge=PKCEChallenge(challenge, "S256"),
        expires_at=now - timedelta(seconds=10),
    )
    token_repo.get_code.return_value = expired_code
    with pytest.raises(ExpiredAuthorizationCodeException):
        await use_case.execute(req)


# =========================================================================
# 4. Pruebas de RefreshTokenUseCase
# =========================================================================

async def test_refresh_token_rotation_success():
    client_repo = AsyncMock()
    token_repo = AsyncMock()
    user_repo = AsyncMock()
    token_issuer = MagicMock()

    client_repo.get_by_client_id.return_value = OAuthClient(id="claude")

    u_uuid = uuid4()
    now = datetime.now(timezone.utc)
    raw_rt = "rt_original_token_string_12345"
    token_hash = hashlib.sha256(raw_rt.encode("ascii")).hexdigest()

    stored_rt = RefreshToken(
        id=token_hash,
        client_id="claude",
        user_uuid=u_uuid,
        scope="bookings:read",
        expires_at=now + timedelta(days=30),
        revoked_at=None,
    )
    token_repo.get_refresh_token.return_value = stored_rt

    mock_user = User(id=1, uuid=u_uuid, email=EmailAddress("u@a.com"), is_active=True)
    user_repo.get_by_uuid.return_value = mock_user
    token_issuer.create_access_token.return_value = "new_jwt_access_token"

    req = TokenRefreshRequestDTO(
        grant_type="refresh_token",
        client_id="claude",
        refresh_token=raw_rt,
    )

    use_case = RefreshTokenUseCase(client_repo, token_repo, user_repo, token_issuer)
    res = await use_case.execute(req)

    assert res.access_token == "new_jwt_access_token"
    assert res.refresh_token.startswith("rt_")
    assert res.refresh_token != raw_rt
    assert stored_rt.is_revoked() is True
    token_repo.update_refresh_token.assert_awaited_once_with(stored_rt)
    token_repo.save_refresh_token.assert_awaited_once()


async def test_refresh_token_already_revoked():
    client_repo = AsyncMock()
    token_repo = AsyncMock()
    user_repo = AsyncMock()
    token_issuer = MagicMock()

    client_repo.get_by_client_id.return_value = OAuthClient(id="claude")
    now = datetime.now(timezone.utc)

    stored_rt = RefreshToken(
        id="hash",
        client_id="claude",
        user_uuid=uuid4(),
        expires_at=now + timedelta(days=30),
        revoked_at=now,
    )
    token_repo.get_refresh_token.return_value = stored_rt

    req = TokenRefreshRequestDTO(grant_type="refresh_token", client_id="claude", refresh_token="rt_revoked")
    use_case = RefreshTokenUseCase(client_repo, token_repo, user_repo, token_issuer)

    with pytest.raises(InvalidRefreshTokenException):
        await use_case.execute(req)


# =========================================================================
# 5. Pruebas de RevokeTokenUseCase y GetUserInfoUseCase
# =========================================================================

async def test_revoke_token():
    token_repo = AsyncMock()
    raw_rt = "rt_to_revoke"
    token_hash = hashlib.sha256(raw_rt.encode("ascii")).hexdigest()

    stored_rt = RefreshToken(
        id=token_hash,
        client_id="claude",
        user_uuid=uuid4(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    token_repo.get_refresh_token.return_value = stored_rt

    use_case = RevokeTokenUseCase(token_repo)
    await use_case.execute(RevokeTokenRequestDTO(token=raw_rt, client_id="claude"))

    assert stored_rt.is_revoked() is True
    token_repo.update_refresh_token.assert_awaited_once_with(stored_rt)


async def test_get_user_info():
    user_repo = AsyncMock()
    u_uuid = uuid4()

    mock_user = User(
        id=1,
        uuid=u_uuid,
        email=EmailAddress("socio@atlas.com"),
        name="María",
        last_name="González",
        phone=PhoneNumberE164("+18095554321"),
        is_active=True,
        is_confirmed=True,
    )
    user_repo.get_by_uuid.return_value = mock_user

    use_case = GetUserInfoUseCase(user_repo)
    info = await use_case.execute(u_uuid)

    assert info.sub == str(u_uuid)
    assert info.email == "socio@atlas.com"
    assert info.name == "María González"
    assert info.phone_number == "+18095554321"
    assert info.is_confirmed is True

