from __future__ import annotations

import re
from dataclasses import dataclass
from src.shared.domain.base import ValueObject

_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


@dataclass(frozen=True)
class EmailAddress(ValueObject):
    """Dirección de correo electrónico validada y normalizada a minúsculas."""
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("El correo electrónico no puede ser vacío.")
        clean_value = self.value.strip().lower()
        if not _EMAIL_REGEX.match(clean_value):
            raise ValueError(f"El correo electrónico '{self.value}' no tiene un formato válido.")
        object.__setattr__(self, "value", clean_value)

    def __str__(self) -> str:
        return self.value
