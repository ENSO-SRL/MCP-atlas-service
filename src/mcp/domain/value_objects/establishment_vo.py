from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from src.shared.domain.base import ValueObject


@dataclass(frozen=True)
class LocationAddress(ValueObject):
    """Dirección física estructurada de un establecimiento o servicio."""
    country: Optional[str] = None
    state_province: Optional[str] = None
    city: Optional[str] = None
    sector: Optional[str] = None
    residential: Optional[str] = None
    street: Optional[str] = None
    building_number: Optional[str] = None
    postal_code: Optional[str] = None
    reference: Optional[str] = None
    google_maps_url: Optional[str] = None

    @property
    def formatted_summary(self) -> str:
        parts = [p for p in [self.street, self.building_number, self.sector, self.city, self.country] if p]
        return ", ".join(parts) if parts else "Ubicación no especificada"


@dataclass(frozen=True)
class ContactInfo(ValueObject):
    """Datos de contacto oficiales de un establecimiento o servicio."""
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
