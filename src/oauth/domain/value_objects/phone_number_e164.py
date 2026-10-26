from __future__ import annotations

import re
from dataclasses import dataclass
from src.shared.domain.base import ValueObject

_E164_REGEX = re.compile(r"^\+[1-9][0-9]{6,14}$")


@dataclass(frozen=True)
class PhoneNumberE164(ValueObject):
    """Número telefónico normalizado bajo estándar internacional ITU E.164 (ej. +18091234567)."""
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("El número telefónico no puede ser vacío.")
        clean_value = self.value.strip()
        if not _E164_REGEX.match(clean_value):
            raise ValueError(
                f"El número telefónico '{self.value}' no cumple con el formato internacional E.164 "
                "(debe iniciar con '+' seguido del código de país y de 7 a 15 dígitos numéricos)."
            )
        object.__setattr__(self, "value", clean_value)

    def __str__(self) -> str:
        return self.value
