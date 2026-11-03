from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import jwt
import pytest

from src.oauth.domain.entities.authorization_code import AuthorizationCode
from src.oauth.domain.entities.oauth_client import OAuthClient
from src.oauth.domain.entities.refresh_token import RefreshToken
from src.oauth.domain.entities.user import User
from src.oauth.domain.enums.user_role import UserRole
from src.oauth.domain.value_objects.email_address import EmailAddress
from src.oauth.domain.value_objects.phone_number_e164 import PhoneNumberE164
from src.oauth.domain.value_objects.pkce_challenge import PKCEChallenge
from src.oauth.infrastructure.persistence.models.oauth_models import (
    AuthorizationCodeModel,
    OAuthClientModel,
    RefreshTokenModel,
)
from src.oauth.infrastructure.persistence.models.user_models import UserModel
from src.oauth.infrastructure.persistence.repositories.sql_oauth_client_repository import (
    SqlOAuthClientRepository,
)
from src.oauth.infrastructure.persistence.repositories.sql_oauth_token_repository import (
    SqlOAuthTokenRepository,
)
from src.oauth.infrastructure.persistence.repositories.sql_user_repository import (
    SqlUserRepository,
)
from src.oauth.infrastructure.security.bcrypt_password_hasher import (
    BcryptPasswordHasher,
)
from src.oauth.infrastructure.security.jwt_token_issuer import JwtTokenIssuer


# =========================================================================
# 1. Pruebas de Adaptadores de Seguridad (Bcrypt & PyJWT)
# =========================================================================

def test_bcrypt_password_hasher():
    hasher = BcryptPasswordHasher()
    plain = "MiClaveSecreta123!"

    hashed = hasher.hash_password(plain)
    assert hashed != plain
    assert hashed.startswith("$2b$")

    assert hasher.verify_password(plain, hashed) is True
    assert hasher.verify_password("PasswordErronea", hashed) is False
    assert hasher.verify_password("", hashed) is False
    assert hasher.verify_password(plain, "") is False


def test_jwt_token_issuer_create_and_validate():
    issuer = JwtTokenIssuer(
        secret_key="test-secret-key-32-bytes-minimum-length!",
        algorithm="HS256",
        issuer="https://mcp.atlas.test",
    )
    user_uuid = uuid4()
    scope = "bookings:read bookings:write"

    token_str = issuer.create_access_token(
        user_uuid=user_uuid,
        scope=scope,
        expires_in_seconds=3600,
        extra_claims={
            "phone_number": "+18094251911",
            "email": "test@example.com",
        },
    )

    assert isinstance(token_str, str)
    assert len(token_str) > 20

    claims = issuer.decode_and_validate_access_token(token_str)
    assert claims["iss"] == "https://mcp.atlas.test"
    assert claims["sub"] == str(user_uuid)
    assert claims["scope"] == scope
    assert claims["phone_number"] == "+18094251911"
    assert claims["email"] == "test@example.com"
    assert claims["exp"] > claims["iat"]


def test_jwt_token_issuer_expired_token():
    issuer = JwtTokenIssuer(
        secret_key="test-secret-key-32-bytes-minimum-length!",
        algorithm="HS256",
        issuer="https://mcp.atlas.test",
    )
    user_uuid = uuid4()

    # Expira de inmediato (-10 segundos)
    expired_token = issuer.create_access_token(
        user_uuid=user_uuid,
        scope="profile",
        expires_in_seconds=-10,
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        issuer.decode_and_validate_access_token(expired_token)


def test_jwt_token_issuer_invalid_signature():
    issuer_a = JwtTokenIssuer(secret_key="secret-key-a-minimum-32-bytes-long!", algorithm="HS256")
    issuer_b = JwtTokenIssuer(secret_key="secret-key-b-minimum-32-bytes-long!", algorithm="HS256")

    token = issuer_a.create_access_token(user_uuid=uuid4(), scope="profile")

    with pytest.raises(jwt.InvalidSignatureError):
        issuer_b.decode_and_validate_access_token(token)


# =========================================================================
# 2. Pruebas de SqlUserRepository
# =========================================================================

async def test_sql_user_repository_get_by_id_and_uuid():
    mock_session = AsyncMock()
    user_id = 42
    u_uuid = uuid4()
    now = datetime.now(timezone.utc)

    model = UserModel(
        id=user_id,
        uuid=str(u_uuid),
        email="carlos@atlas.com",
        hashed_password="$2b$12$somehash",
        name="Carlos",
        last_name="Santana",
        phone="+18095551234",
        gender="M",
        is_active=True,
        is_confirmed=True,
        is_cancelled=False,
        role_id=1,
        created_at=now,
        updated_at=now,
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = model
    mock_session.execute.return_value = mock_result

    repo = SqlUserRepository(mock_session)

    # get_by_id
    user = await repo.get_by_id(user_id)
    assert user is not None
    assert user.id == user_id
    assert user.uuid == u_uuid
    assert str(user.email) == "carlos@atlas.com"
    assert str(user.phone) == "+18095551234"
    assert user.role == UserRole.ADMIN
    assert user.is_confirmed is True

    # get_by_uuid
    user_by_uuid = await repo.get_by_uuid(u_uuid)
    assert user_by_uuid is not None
    assert user_by_uuid.uuid == u_uuid


async def test_sql_user_repository_get_by_email_and_phone():
    mock_session = AsyncMock()
    now = datetime.now(timezone.utc)
    model = UserModel(
        id=10,
        uuid=str(uuid4()),
        email="ana@example.com",
        hashed_password="hash",
        name="Ana",
        last_name="Díaz",
        phone="+18099998888",
        gender="F",
        is_active=True,
        is_confirmed=True,
        role_id=2,
        created_at=now,
        updated_at=now,
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = model
    mock_session.execute.return_value = mock_result

    repo = SqlUserRepository(mock_session)

    user_email = await repo.get_by_email("ana@example.com")
    assert user_email is not None
    assert user_email.name == "Ana"
    assert user_email.role == UserRole.USER

    user_phone = await repo.get_by_phone("+18099998888")
    assert user_phone is not None
    assert str(user_phone.phone) == "+18099998888"


async def test_sql_user_repository_save_new_user():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    repo = SqlUserRepository(mock_session)
    new_user = User(
        id=None,
        uuid=uuid4(),
        email=EmailAddress("nuevo@example.com"),
        hashed_password="hashed_pwd",
        name="Nuevo",
        last_name="Usuario",
        phone=PhoneNumberE164("+18091112222"),
        gender="M",
        role=UserRole.USER,
    )

    # Simular que al hacer flush se le asigna id=100
    def fake_flush():
        added_model = mock_session.add.call_args[0][0]
        added_model.id = 100

    mock_session.flush.side_effect = fake_flush

    saved = await repo.save(new_user)
    assert saved.id == 100
    mock_session.add.assert_called_once()
    mock_session.flush.assert_awaited_once()


# =========================================================================
# 3. Pruebas de SqlOAuthClientRepository
# =========================================================================

async def test_sql_oauth_client_repository():
    mock_session = AsyncMock()
    now = datetime.now(timezone.utc)
    client_model = OAuthClientModel(
        client_id="claude-desktop",
        client_name="Claude Desktop Client",
        redirect_uris=["https://claude.ai/api/oauth/callback"],
        is_confidential=False,
        created_at=now,
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = client_model
    mock_session.execute.return_value = mock_result

    repo = SqlOAuthClientRepository(mock_session)

    client = await repo.get_by_client_id("claude-desktop")
    assert client is not None
    assert client.id == "claude-desktop"
    assert "https://claude.ai/api/oauth/callback" in client.redirect_uris
    assert client.is_redirect_uri_allowed("https://claude.ai/api/oauth/callback") is True
    assert client.is_redirect_uri_allowed("https://malicious.site/cb") is False


# =========================================================================
# 4. Pruebas de SqlOAuthTokenRepository
# =========================================================================

async def test_sql_oauth_token_repository_code_and_refresh():
    mock_session = AsyncMock()
    mock_session.get = AsyncMock()
    mock_session.flush = AsyncMock()

    u_uuid = uuid4()
    now = datetime.now(timezone.utc)
    code_model = AuthorizationCodeModel(
        code="code_xyz_123",
        client_id="claude-desktop",
        user_uuid=u_uuid,
        redirect_uri="https://claude.ai/cb",
        scope="bookings:read bookings:write",
        code_challenge="challenge_str",
        code_challenge_method="S256",
        expires_at=now + timedelta(minutes=5),
        used_at=None,
        created_at=now,
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = code_model
    mock_session.execute.return_value = mock_result

    repo = SqlOAuthTokenRepository(mock_session)

    # 1. get_code
    code = await repo.get_code("code_xyz_123")
    assert code is not None
    assert code.id == "code_xyz_123"
    assert code.client_id == "claude-desktop"
    assert code.challenge.code_challenge == "challenge_str"
    assert not code.is_used()

    # 2. update_code
    mock_session.get.return_value = code_model
    code.used_at = now
    await repo.update_code(code)
    assert code_model.used_at is not None
    mock_session.flush.assert_awaited()

    # 3. save_refresh_token y get_refresh_token
    rt_model = RefreshTokenModel(
        token_hash="hash_rt_999",
        client_id="claude-desktop",
        user_uuid=u_uuid,
        scope="bookings:read",
        expires_at=now + timedelta(days=30),
        revoked_at=None,
        created_at=now,
    )
    mock_result_rt = MagicMock()
    mock_result_rt.scalar_one_or_none.return_value = rt_model
    mock_session.execute.return_value = mock_result_rt

    rt = await repo.get_refresh_token("hash_rt_999")
    assert rt is not None
    assert rt.id == "hash_rt_999"
    assert rt.is_valid()
    assert not rt.is_revoked()

    # 4. update_refresh_token (revocación)
    mock_session.get.return_value = rt_model
    rt.revoke()
    await repo.update_refresh_token(rt)
    assert rt_model.revoked_at is not None
