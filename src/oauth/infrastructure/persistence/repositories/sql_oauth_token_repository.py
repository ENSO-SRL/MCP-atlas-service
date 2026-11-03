from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.oauth.domain.entities.authorization_code import AuthorizationCode
from src.oauth.domain.entities.refresh_token import RefreshToken
from src.oauth.domain.ports.i_oauth_token_repository import IOAuthTokenRepository
from src.oauth.domain.value_objects.pkce_challenge import PKCEChallenge
from src.oauth.infrastructure.persistence.models.oauth_models import (
    AuthorizationCodeModel,
    RefreshTokenModel,
)


class SqlOAuthTokenRepository(IOAuthTokenRepository):
    """Implementación de IOAuthTokenRepository para códigos y refresh tokens en PostgreSQL."""

    def __init__(self, session: AsyncSession):
        self._session = session

    @staticmethod
    def _code_to_domain(model: AuthorizationCodeModel) -> AuthorizationCode:
        return AuthorizationCode(
            id=model.code,
            client_id=model.client_id,
            user_uuid=model.user_uuid,
            redirect_uri=model.redirect_uri,
            scope=model.scope,
            challenge=PKCEChallenge(
                code_challenge=model.code_challenge,
                method=model.code_challenge_method,
            ),
            expires_at=model.expires_at,
            used_at=model.used_at,
            created_at=model.created_at,
        )

    @staticmethod
    def _refresh_to_domain(model: RefreshTokenModel) -> RefreshToken:
        return RefreshToken(
            id=model.token_hash,
            client_id=model.client_id,
            user_uuid=model.user_uuid,
            scope=model.scope,
            expires_at=model.expires_at,
            revoked_at=model.revoked_at,
            created_at=model.created_at,
        )

    async def save_code(self, code: AuthorizationCode) -> AuthorizationCode:
        model = AuthorizationCodeModel(
            code=code.id,
            client_id=code.client_id,
            user_uuid=code.user_uuid,
            redirect_uri=code.redirect_uri,
            scope=code.scope,
            code_challenge=code.challenge.code_challenge,
            code_challenge_method=code.challenge.method,
            expires_at=code.expires_at,
            used_at=code.used_at,
            created_at=code.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        return self._code_to_domain(model)

    async def get_code(self, code_str: str) -> Optional[AuthorizationCode]:
        stmt = select(AuthorizationCodeModel).where(AuthorizationCodeModel.code == code_str.strip())
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._code_to_domain(model) if model else None

    async def update_code(self, code: AuthorizationCode) -> None:
        model = await self._session.get(AuthorizationCodeModel, code.id)
        if model:
            model.used_at = code.used_at
            await self._session.flush()

    async def save_refresh_token(self, token: RefreshToken) -> RefreshToken:
        model = RefreshTokenModel(
            token_hash=token.id,
            client_id=token.client_id,
            user_uuid=token.user_uuid,
            scope=token.scope,
            expires_at=token.expires_at,
            revoked_at=token.revoked_at,
            created_at=token.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        return self._refresh_to_domain(model)

    async def get_refresh_token(self, token_hash: str) -> Optional[RefreshToken]:
        stmt = select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash.strip())
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._refresh_to_domain(model) if model else None

    async def update_refresh_token(self, token: RefreshToken) -> None:
        model = await self._session.get(RefreshTokenModel, token.id)
        if model:
            model.revoked_at = token.revoked_at
            await self._session.flush()

