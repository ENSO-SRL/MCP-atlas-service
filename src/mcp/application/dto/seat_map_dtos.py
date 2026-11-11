from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID


@dataclass
class SeatDTO:
    """Información de una butaca o asiento individual."""
    label: str
    status: str = "available"  # "available", "occupied", "reserved", "wheelchair"
    row: Optional[str] = None
    number: Optional[int] = None
    type: Optional[str] = None  # "regular", "vip", "wheelchair"
    recommended: bool = False


@dataclass
class GetSeatMapQueryDTO:
    """Parámetros de entrada para el caso de uso GetSeatMapUseCase."""
    service_id: int
    showing_id: Optional[str] = None
    slot_token: Optional[str] = None
    user_uuid: Optional[UUID] = None
    user_phone: Optional[str] = None


@dataclass
class SeatMapResponseDTO:
    """DTO de respuesta con el plano de sala y butacas disponibles."""
    status: str  # "completed", "processing", "failed"
    service_id: int = 0
    showing_id: Optional[str] = None
    screen_name: Optional[str] = None
    seats_remaining: Optional[int] = None
    seat_mode_options: list[str] = field(default_factory=lambda: ["mejor", "seleccion"])
    recommended_seats: list[str] = field(default_factory=list)
    available_seats: list[str] = field(default_factory=list)
    rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    operation_id: Optional[str] = None
    expires_in_seconds: Optional[int] = None
    error_message: Optional[str] = None
    message: Optional[str] = None

