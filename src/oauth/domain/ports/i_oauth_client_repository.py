from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from src.oauth.domain.entities.oauth_client import OAuthClient


class IOAuthClientRepository(ABC):
    """Puerto de repositorio para clientes OAuth autorizados."""

    @abstractmethod
    async def get_by_client_id(self, client_id: str) -> Optional[OAuthClient]:
        """Obtiene un cliente por su client_id."""
        pass

    @abstractmethod
    async def save(self, client: OAuthClient) -> OAuthClient:
        """Registra un nuevo cliente (DCR) o actualiza uno existente."""
        pass
