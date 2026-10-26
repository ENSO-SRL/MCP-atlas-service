from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID


class IPasswordHasher(ABC):
    """Puerto para el algoritmo de hashing y verificación de contraseñas (Bcrypt)."""

    @abstractmethod
    def hash_password(self, plain_password: str) -> str:
        """Genera el hash seguro de una contraseña en texto plano."""
        pass

    @abstractmethod
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verifica si la contraseña coincide con el hash almacenado."""
        pass


class ITokenIssuer(ABC):
    """Puerto para la creación, firma y verificación de tokens de acceso JWT (RFC 7519)."""

    @abstractmethod
    def create_access_token(
        self, user_uuid: UUID, scope: str, expires_in_seconds: int = 3600
    ) -> str:
        """Emite y firma un token JWT con los claims requeridos."""
        pass

    @abstractmethod
    def decode_and_validate_access_token(self, token_str: str) -> dict[str, Any]:
        """Decodifica y valida firma, emisor y expiración del JWT."""
        pass
