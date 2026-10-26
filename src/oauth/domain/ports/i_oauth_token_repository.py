from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from src.oauth.domain.entities.authorization_code import AuthorizationCode
from src.oauth.domain.entities.refresh_token import RefreshToken


class IOAuthTokenRepository(ABC):
    """Puerto de repositorio para la persistencia de códigos de autorización y refresh tokens."""

    @abstractmethod
    async def save_code(self, code: AuthorizationCode) -> AuthorizationCode:
        """Guarda un nuevo código de autorización temporal."""
        pass

    @abstractmethod
    async def get_code(self, code_str: str) -> Optional[AuthorizationCode]:
        """Obtiene un código de autorización por su valor."""
        pass

    @abstractmethod
    async def update_code(self, code: AuthorizationCode) -> None:
        """Actualiza el estado de uso de un código."""
        pass

    @abstractmethod
    async def save_refresh_token(self, token: RefreshToken) -> RefreshToken:
        """Guarda un nuevo refresh token."""
        pass

    @abstractmethod
    async def get_refresh_token(self, token_hash: str) -> Optional[RefreshToken]:
        """Obtiene un refresh token por su hash."""
        pass

    @abstractmethod
    async def update_refresh_token(self, token: RefreshToken) -> None:
        """Actualiza el estado de revocación de un refresh token."""
        pass
