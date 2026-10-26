from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from src.oauth.domain.enums.user_role import UserRole
from src.oauth.domain.value_objects.email_address import EmailAddress
from src.oauth.domain.value_objects.phone_number_e164 import PhoneNumberE164
from src.shared.domain.base import AggregateRoot


@dataclass
class User(AggregateRoot[int]):
    """
    Entidad de Dominio User, mapeada sobre la tabla 'users' de ATLAS-BACKEND.
    Representa un usuario, socio o invitado en el sistema.
    """
    uuid: UUID = field(default_factory=uuid4)
    email: EmailAddress = field(default_factory=lambda: EmailAddress("user@example.com"))
    hashed_password: str = ""
    name: str = ""
    last_name: str = ""
    phone: Optional[PhoneNumberE164] = None
    national_id: Optional[str] = None
    gender: Optional[str] = None
    is_active: bool = True
    is_confirmed: bool = False
    is_cancelled: bool = False
    role: UserRole = UserRole.USER
    parent_id: Optional[int] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def full_name(self) -> str:
        return f"{self.name} {self.last_name}".strip()

    def is_profile_complete(self) -> bool:
        """
        Regla de Negocio ATLAS-BACKEND:
        Un usuario tiene su perfil completo si posee teléfono y género registrados.
        """
        return self.phone is not None and bool(self.gender and self.gender.strip())

    def can_book(self) -> bool:
        """
        Regla de Negocio ATLAS-BACKEND:
        Para realizar una reserva se requiere:
        - Cuenta activa y no cancelada.
        - Correo confirmado (is_confirmed == True).
        - Perfil completo (teléfono verificado y género).
        """
        return (
            self.is_active
            and not self.is_cancelled
            and self.is_confirmed
            and self.is_profile_complete()
        )

    def confirm_email(self) -> None:
        self.is_confirmed = True
        self.updated_at = datetime.now(timezone.utc)

    def deactivate(self) -> None:
        self.is_active = False
        self.updated_at = datetime.now(timezone.utc)
