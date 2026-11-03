from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from src.oauth.application.dto.oauth_dtos import (
    AuthorizationCodeResultDTO,
    AuthorizeRequestDTO,
)
from src.oauth.domain.entities.authorization_code import AuthorizationCode
from src.oauth.domain.exceptions.auth_exceptions import (
    AuthDomainException,
    InvalidClientException,
    InvalidPKCEException,
    InvalidRedirectUriException,
    UserInactiveException,
)
from src.oauth.domain.ports.i_oauth_client_repository import IOAuthClientRepository
from src.oauth.domain.ports.i_oauth_token_repository import IOAuthTokenRepository
from src.oauth.domain.ports.i_user_repository import IUserRepository
from src.oauth.domain.value_objects.pkce_challenge import PKCEChallenge
from src.shared.config.settings import get_settings


class GenerateAuthorizationCodeUseCase:
    """
    Caso de uso: Generación de código de autorización efímero con PKCE (RFC 7636).
    Se ejecuta tras el consentimiento explícito del usuario en /oauth/authorize.
    """

    def __init__(
        self,
        client_repo: IOAuthClientRepository,
        token_repo: IOAuthTokenRepository,
        user_repo: IUserRepository,
    ):
        self._client_repo = client_repo
        self._token_repo = token_repo
        self._user_repo = user_repo

    async def execute(self, dto: AuthorizeRequestDTO) -> AuthorizationCodeResultDTO:
        # 1. Validaciones de protocolo OAuth 2.0
        if dto.response_type != "code":
            raise AuthDomainException(f"response_type no soportado: '{dto.response_type}'. Solo se admite 'code'.")

        if dto.code_challenge_method != "S256":
            raise InvalidPKCEException("Solo se soporta code_challenge_method='S256'.")

        if not dto.code_challenge or len(dto.code_challenge.strip()) < 43:
            raise InvalidPKCEException("El code_challenge proporcionado es inválido o demasiado corto.")

        # 2. Validar cliente registrado
        client = await self._client_repo.get_by_client_id(dto.client_id)
        if client is None:
            raise InvalidClientException(f"Cliente '{dto.client_id}' no registrado en el sistema.")

        # 3. Validar redirect_uri autorizada
        if not client.is_redirect_uri_allowed(dto.redirect_uri):
            raise InvalidRedirectUriException(
                f"La redirect_uri '{dto.redirect_uri}' no está autorizada para el cliente '{dto.client_id}'."
            )

        # 4. Validar usuario activo
        user = await self._user_repo.get_by_uuid(dto.user_uuid)
        if user is None or not user.is_active or user.is_cancelled:
            raise UserInactiveException("El usuario asociado a la autorización no existe o está inactivo.")

        # 5. Generar código criptográfico y expiración (TTL corto, ej. 60s)
        settings = get_settings()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=settings.OAUTH_AUTH_CODE_EXPIRE_SECONDS)

        code_value = f"auth_code_{secrets.token_urlsafe(32)}"
        challenge = PKCEChallenge(code_challenge=dto.code_challenge.strip(), method="S256")

        auth_code = AuthorizationCode(
            id=code_value,
            client_id=dto.client_id,
            user_uuid=dto.user_uuid,
            redirect_uri=dto.redirect_uri,
            scope=dto.scope,
            challenge=challenge,
            expires_at=expires_at,
            created_at=now,
        )

        await self._token_repo.save_code(auth_code)

        return AuthorizationCodeResultDTO(
            code=auth_code.id,
            redirect_uri=dto.redirect_uri,
            state=dto.state,
        )

