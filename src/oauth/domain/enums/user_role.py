from enum import Enum


class UserRole(str, Enum):
    """Roles de usuario en el sistema ATLAS-BACKEND."""
    ADMIN = "ADMIN"
    USER = "USER"
    GUEST = "GUEST"
