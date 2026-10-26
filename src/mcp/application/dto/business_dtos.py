from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SearchBusinessesQueryDTO:
    """Parámetros de búsqueda de negocios en el catálogo."""
    query: Optional[str] = None
    category: Optional[str] = None
    zone: Optional[str] = None
    cursor: int = 0
    limit: int = 10


@dataclass
class BusinessSummaryDTO:
    """Resumen de un establecimiento para listados de búsqueda."""
    id: int
    name: str
    code: str
    category: Optional[str] = None
    city: Optional[str] = None
    sector: Optional[str] = None
    address_line: Optional[str] = None
    operating_hours: dict[str, Any] = field(default_factory=dict)
    rule_type: str = "only_today"


@dataclass
class SearchBusinessesResponseDTO:
    """Resultado paginado de búsqueda de establecimientos."""
    items: list[BusinessSummaryDTO] = field(default_factory=list)
    next_cursor: Optional[int] = None
    total_count: int = 0


@dataclass
class BusinessDetailsQueryDTO:
    """Consulta de detalle de un establecimiento específico."""
    business_id: int


@dataclass
class BusinessServiceSummaryDTO:
    """Resumen de un servicio perteneciente a un establecimiento."""
    id: int
    name: str
    category: Optional[str] = None
    pattern: str = "slot_object"
    has_active_contract: bool = False


@dataclass
class BusinessDetailsDTO:
    """Ficha técnica y operativa completa de un establecimiento físico."""
    id: int
    name: str
    code: str
    category: Optional[str] = None
    city: Optional[str] = None
    sector: Optional[str] = None
    address_line: Optional[str] = None
    postal_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    operating_hours: dict[str, Any] = field(default_factory=dict)
    rule_type: str = "only_today"
    advance_booking_rule: str = ""
    services: list[BusinessServiceSummaryDTO] = field(default_factory=list)
