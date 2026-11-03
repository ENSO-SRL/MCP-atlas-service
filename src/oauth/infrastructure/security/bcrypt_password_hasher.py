from __future__ import annotations

import bcrypt

from src.oauth.domain.ports.i_security_ports import IPasswordHasher


class BcryptPasswordHasher(IPasswordHasher):
    """Implementación de hashing y verificación de contraseñas usando Bcrypt."""

    def hash_password(self, plain_password: str) -> str:
        """Genera un hash seguro con salt aleatorio."""
        salt = bcrypt.gensalt(rounds=12)
        hashed_bytes = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
        return hashed_bytes.decode("utf-8")

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verifica si la contraseña coincide con el hash almacenado."""
        if not plain_password or not hashed_password:
            return False
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"), hashed_password.encode("utf-8")
            )
        except (ValueError, TypeError):
            return False

