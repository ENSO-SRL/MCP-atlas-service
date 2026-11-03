from __future__ import annotations

import hashlib

from src.oauth.application.dto.oauth_dtos import RevokeTokenRequestDTO
from src.oauth.domain.ports.i_oauth_token_repository import IOAuthTokenRepository


class RevokeTokenUseCase:
    """
    Caso de uso: Revocación de Tokens (RFC 7009).
    Permite invalidar un refresh token activo. Conforme a la especificación,
    si el token no existe o ya fue revocado, la operación concluye con éxito (idempotente).
    """

    def __init__(self, token_repo: IOAuthTokenRepository):
        self._token_repo = token_repo

    async def execute(self, dto: RevokeTokenRequestDTO) -> None:
        if not dto.token or not dto.token.strip():
            return

        token_hash = hashlib.sha256(dto.token.strip().encode("ascii")).hexdigest()
        stored_token = await self._token_repo.get_refresh_token(token_hash)

        if stored_token is not None and stored_token.is_valid():
            stored_token.revoke()
            await self._token_repo.update_refresh_token(stored_token)

