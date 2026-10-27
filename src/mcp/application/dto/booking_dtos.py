from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID


@dataclass
class CreateBookingInputDTO:
    """Entrada para solicitar una reserva diferida o solicitud bajo demanda."""
    user_uuid: UUID
    idempotency_key: str
    slot_token: Optional[str] = None
    service_id: Optional[int] = None  # Requerido si no hay slot_token (patrón on_demand_request)
    fields: dict[str, Any] = field(default_factory=dict)
    user_phone: Optional[str] = None


@dataclass
class BookingCreationResultDTO:
    """Resultado inicial tras procesar la creación de una solicitud de reserva."""
    booking_id: UUID
    status: str  # "requested", "accepted", "confirmed", "rejected", "failed"
    service_id: int
    slot_start: Optional[datetime] = None
    slot_end: Optional[datetime] = None
    is_estimated: bool = False
    applied_filters: dict[str, Any] = field(default_factory=dict)
    status_reason: Optional[str] = None
    external_ref: Optional[str] = None
    expires_at: Optional[datetime] = None
    message: str = ""


@dataclass
class GetBookingStatusQueryDTO:
    """Consulta de estado y trazabilidad de una reserva."""
    booking_id: UUID
    user_uuid: UUID


@dataclass
class BookingDetailsDTO:
    """Detalle completo de una reserva con trazabilidad contextual."""
    booking_id: UUID
    user_uuid: UUID
    service_id: int
    status: str
    service_name: Optional[str] = None
    establishment_name: Optional[str] = None
    status_reason: Optional[str] = None
    slot_start: Optional[datetime] = None
    slot_end: Optional[datetime] = None
    resource_ref: Optional[str] = None
    applied_filters: dict[str, Any] = field(default_factory=dict)
    fields: dict[str, Any] = field(default_factory=dict)
    price_estimate: Optional[dict[str, Any]] = None
    external_ref: Optional[str] = None
    assigned_details: Optional[dict[str, Any]] = None
    expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    explanation: str = ""


@dataclass
class ListMyBookingsQueryDTO:
    """Consulta paginada del historial de reservas del usuario autenticado."""
    user_uuid: UUID
    status_filter: Optional[str] = None
    cursor: int = 0
    limit: int = 10


@dataclass
class BookingSummaryDTO:
    """Resumen de una reserva para listados."""
    booking_id: UUID
    service_id: int
    status: str
    service_name: Optional[str] = None
    slot_start: Optional[datetime] = None
    slot_end: Optional[datetime] = None
    applied_filters: dict[str, Any] = field(default_factory=dict)
    external_ref: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ListMyBookingsResponseDTO:
    """Respuesta paginada del listado de reservas del usuario."""
    items: list[BookingSummaryDTO] = field(default_factory=list)
    next_cursor: Optional[int] = None
    total_count: int = 0


@dataclass
class CancelBookingInputDTO:
    """Parámetros para solicitar la cancelación de una reserva activa."""
    booking_id: UUID
    user_uuid: UUID
    reason: Optional[str] = None
    user_phone: Optional[str] = None


@dataclass
class CancellationResultDTO:
    """Resultado del proceso de solicitud de cancelación."""
    booking_id: UUID
    status: str  # "cancel_requested", "cancelled"
    message: str
