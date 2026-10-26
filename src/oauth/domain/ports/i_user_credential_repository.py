from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from src.oauth.domain.entities.user_credential import UserCredential


class IUserCredentialRepository(ABC):
    """Puerto de repositorio para la tabla 'credentials' de ATLAS-BACKEND."""

    @abstractmethod
    async def get_by_user_and_establishment(
        self, user_id: int, establishment_id: int
    ) -> Optional[UserCredential]:
        """Obtiene la credencial de socio activa de un usuario para un establecimiento."""
        pass

    @abstractmethod
    async def get_by_user_and_service(
        self, user_id: int, service_id: int
    ) -> Optional[UserCredential]:
        """Obtiene la credencial activa de un usuario para un servicio particular."""
        pass

    @abstractmethod
    async def list_by_user(self, user_id: int) -> list[UserCredential]:
        """Lista todas las credenciales activas del usuario."""
        pass
