from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from src.oauth.domain.entities.user import User


class IUserRepository(ABC):
    """Puerto de repositorio para la entidad User (tabla 'users' de ATLAS-BACKEND)."""

    @abstractmethod
    async def get_by_id(self, user_id: int) -> Optional[User]:
        """Obtiene un usuario por su ID interno autoincremental."""
        pass

    @abstractmethod
    async def get_by_uuid(self, user_uuid: UUID) -> Optional[User]:
        """Obtiene un usuario por su identificador público UUID."""
        pass

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[User]:
        """Obtiene un usuario por su correo electrónico."""
        pass

    @abstractmethod
    async def get_by_phone(self, phone: str) -> Optional[User]:
        """Obtiene un usuario por su número de teléfono."""
        pass

    @abstractmethod
    async def save(self, user: User) -> User:
        """Crea o actualiza un usuario en la base de datos."""
        pass
