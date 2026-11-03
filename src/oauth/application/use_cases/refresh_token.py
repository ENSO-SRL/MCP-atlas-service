from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from src.oauth.application.dto.oauth_dtos import (
    TokenRefreshRequestDTO,
    TokenResponseDTO,
)
from src.oauth.domain.entities.refresh_token import RefreshToken
from src.oauth.domain.exceptions.auth_exceptions import (
    AuthDomainException,
    InvalidClientException,
    InvalidRefreshTokenException,
    UserInactiveException,
)
from src.oauth.domain.ports.i_oauth_client_repository import IOAuthClientRepository
from src.oauth.domain.ports.i_oauth_token_repository import IOAuthTokenRepository
from src.oauth.domain.ports.i_security_ports import ITokenIssuer
from src.oauth.domain.ports.i_user_repository import IUserRepository
from src.shared.config.settings import get_settings


class RefreshTokenUseCase:
    """
    Caso de uso: Renovación y Rotación Estricta de Refresh Tokens (RFC 6749).
    Invalida el refresh token utilizado y emite un nuevo par (Access Token + Refresh Token).
    """

    def __init__(
        self,
        client_repo: IOAuthClientRepository,
        token_repo: IOAuthTokenRepository,
        user_repo: IUserRepository,
        token_issuer: ITokenIssuer,
    ):
        self._client_repo = client_repo
        self._token_repo = token_repo
        self._user_repo = user_repo
        self._token_issuer = token_issuer

    async def execute(self, dto: TokenRefreshRequestDTO) -> TokenResponseDTO:
        # 1. Validar grant_type
        if dto.grant_type != "refresh_token":
            raise AuthDomainException(
                f"grant_type no soportado: '{dto.grant_type}'. Debe ser 'refresh_token'."
            )

        if not dto.refresh_token or not dto.refresh_token.strip():
            raise InvalidRefreshTokenException("No se proporcionó el refresh_token.")

        # 2. Validar cliente registrado
        client = await self._client_repo.get_by_client_id(dto.client_id)
        if client is None:
            raise InvalidClientException(f"Cliente '{dto.client_id}' no registrado en el sistema.")

        # 3. Buscar token por su hash SHA-256
        token_hash = hashlib.sha256(dto.refresh_token.strip().encode("ascii")).hexdigest()
        stored_token = await self._token_repo.get_refresh_token(token_hash)

        if stored_token is None or not stored_token.is_valid():
            raise InvalidRefreshTokenException("El refresh token es inválido, ha expirado o ya fue revocado.")

        if stored_token.client_id != dto.client_id:
            raise InvalidClientException("El refresh token no corresponde al client_id proporcionado.")

        # 4. Rotación: Revocar inmediatamente el refresh token anterior
        stored_token.revoke()
        await self._token_repo.update_refresh_token(stored_token)

        # 5. Consultar usuario para adjuntar claims actualizados
        user = await self._user_repo.get_by_uuid(stored_token.user_uuid)
        if user is None or not user.is_active or user.is_cancelled:
            raise UserInactiveException("El usuario asociado al token está inactivo o cancelado.")

        settings = get_settings()
        now = datetime.now(timezone.utc)

        # 6. Emitir nuevo Access Token JWT
        extra_claims = {
            "email": str(user.email),
            "phone_number": str(user.phone) if user.phone else None,
            "name": user.full_name or user.name,
        }
        new_access_token = self._token_issuer.create_access_token(
            user_uuid=user.uuid,
            scope=stored_token.scope,
            expires_in_seconds=settings.OAUTH_ACCESS_TOKEN_EXPIRE_SECONDS,
            extra_claims=extra_claims,
        )

        # 7. Emitir y persistir nuevo Refresh Token
        new_raw_refresh_token = f"rt_{secrets.token_urlsafe(48)}"
        new_token_hash = hashlib.sha256(new_raw_refresh_token.encode("ascii")).hexdigest()
        new_expires_at = now + timedelta(days=settings.OAUTH_REFRESH_TOKEN_EXPIRE_DAYS)

        new_refresh_entity = RefreshToken(
            id=new_token_hash,
            client_id=dto.client_id,
            user_uuid=user.uuid,
            scope=stored_token.scope,
            expires_at=new_expires_at,
            created_at=now,
        )
        await self._token_repo.save_refresh_token(new_refresh_entity)

        return TokenResponseDTO(
            access_token=new_access_token,
            refresh_token=new_raw_refresh_token,
            expires_in=settings.OAUTH_ACCESS_TOKEN_EXPIRE_SECONDS,
            scope=stored_token.scope,
        )

