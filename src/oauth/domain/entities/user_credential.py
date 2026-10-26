from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from src.shared.domain.base import Entity


@dataclass
class UserCredential(Entity[int]):
    """
    Entidad UserCredential, mapeada sobre la tabla 'credentials' de ATLAS-BACKEND.
    Almacena credenciales o membresías de socio externas de un usuario en un club o servicio.
    """
    user_id: int = 0
    establishment_id: Optional[int] = None
    servicio_id: Optional[int] = None
    encrypted_data: str = ""
    description: Optional[str] = None
    membership_number: Optional[str] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        # Validación de la restricción Check chk_credentials_establishment_or_servicio
        has_establishment = self.establishment_id is not None
        has_servicio = self.servicio_id is not None
        if not (has_establishment ^ has_servicio):
            raise ValueError(
                "Una credencial debe estar vinculada exclusivamente a un establecimiento "
                "O a un servicio, nunca a ambos ni a ninguno."
            )

    def is_valid_for_establishment(self, establishment_id: int) -> bool:
        return self.is_active and self.establishment_id == establishment_id

    def is_valid_for_service(self, servicio_id: int) -> bool:
        return self.is_active and self.servicio_id == servicio_id
