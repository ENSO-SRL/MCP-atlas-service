from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from src.oauth.application.dto.oauth_dtos import (
    TokenExchangeRequestDTO,
    TokenResponseDTO,
)
from src.oauth.domain.entities.refresh_token import RefreshToken
from src.oauth.domain.exceptions.auth_exceptions import (
    AuthDomainException,
    ExpiredAuthorizationCodeException,
    InvalidClientException,
    InvalidPKCEException,
    InvalidRedirectUriException,
    UserInactiveException,
)
from src.oauth.domain.ports.i_oauth_client_repository import IOAuthClientRepository
from src.oauth.domain.ports.i_oauth_token_repository import IOAuthTokenRepository
from src.oauth.domain.ports.i_security_ports import ITokenIssuer
from src.oauth.domain.ports.i_user_repository import IUserRepository
from src.shared.config.settings import get_settings


class ExchangeTokenUseCase:
    """
    Caso de uso: Canje de código de autorización por Tokens con PKCE (RFC 6749 / RFC 7636).
    Emite un Access Token (JWT firmado) y un Refresh Token persistido con rotación estricta.
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

    async def execute(self, dto: TokenExchangeRequestDTO) -> TokenResponseDTO:
        # 1. Validar tipo de concesión
        if dto.grant_type != "authorization_code":
            raise AuthDomainException(
                f"grant_type no soportado: '{dto.grant_type}'. Debe ser 'authorization_code'."
            )

        # 2. Validar cliente registrado
        client = await self._client_repo.get_by_client_id(dto.client_id)
        if client is None:
            raise InvalidClientException(f"Cliente '{dto.client_id}' no registrado en el sistema.")

        # 3. Buscar código en la base de datos
        auth_code = await self._token_repo.get_code(dto.code)
        if auth_code is None or auth_code.is_expired():
            raise ExpiredAuthorizationCodeException("El código de autorización ha expirado o no existe.")

        if auth_code.is_used():
            raise ExpiredAuthorizationCodeException("El código de autorización ya fue utilizado previamente.")

        # 4. Validar que el código pertenezca al cliente y redirect_uri
        if auth_code.client_id != dto.client_id:
            raise InvalidClientException("El código de autorización no fue emitido para este client_id.")

        if auth_code.redirect_uri != dto.redirect_uri:
            raise InvalidRedirectUriException("La redirect_uri no coincide con la registrada durante la autorización.")

        # 5. Consumir código con verificación PKCE S256 (un solo uso)
        is_valid = auth_code.consume(dto.code_verifier)
        await self._token_repo.update_code(auth_code)

        if not is_valid:
            raise InvalidPKCEException("El code_verifier no supera el desafío code_challenge de PKCE.")

        # 6. Consultar usuario para adjuntar claims al JWT
        user = await self._user_repo.get_by_uuid(auth_code.user_uuid)
        if user is None or not user.is_active or user.is_cancelled:
            raise UserInactiveException("El usuario asociado al token está inactivo o cancelado.")

        settings = get_settings()
        now = datetime.now(timezone.utc)

        # 7. Emitir Access Token JWT
        extra_claims = {
            "email": str(user.email),
            "phone_number": str(user.phone) if user.phone else None,
            "name": user.full_name or user.name,
        }
        access_token = self._token_issuer.create_access_token(
            user_uuid=user.uuid,
            scope=auth_code.scope,
            expires_in_seconds=settings.OAUTH_ACCESS_TOKEN_EXPIRE_SECONDS,
            extra_claims=extra_claims,
        )

        # 8. Generar y almacenar Refresh Token por Hash SHA-256
        raw_refresh_token = f"rt_{secrets.token_urlsafe(48)}"
        token_hash = hashlib.sha256(raw_refresh_token.encode("ascii")).hexdigest()
        refresh_expires_at = now + timedelta(days=settings.OAUTH_REFRESH_TOKEN_EXPIRE_DAYS)

        refresh_entity = RefreshToken(
            id=token_hash,
            client_id=dto.client_id,
            user_uuid=user.uuid,
            scope=auth_code.scope,
            expires_at=refresh_expires_at,
            created_at=now,
        )
        await self._token_repo.save_refresh_token(refresh_entity)

        return TokenResponseDTO(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            expires_in=settings.OAUTH_ACCESS_TOKEN_EXPIRE_SECONDS,
            scope=auth_code.scope,
        )

