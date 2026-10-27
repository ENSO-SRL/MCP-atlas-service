from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from src.mcp.application.dto.contract_dtos import DimensionOptionDTO


@dataclass
class CheckAvailabilityQueryDTO:
    """Parámetros para consultar disponibilidad de slots horarias."""
    service_id: int
    date_from: date
    user_uuid: UUID
    date_to: Optional[date] = None
    filters: dict[str, Any] = field(default_factory=dict)
    party_size: int = 1
    user_phone: Optional[str] = None


@dataclass
class SlotPriceEstimateDTO:
    """Estimación informativa de tarifa para un slot."""
    amount: Decimal
    currency: str = "DOP"
    calculation_basis: str = "per_booking"
    is_starting_price: bool = False
    tax_included: bool = True
    rule_label: Optional[str] = None
    formatted: str = ""


@dataclass
class AvailableSlotDTO:
    """Slot horario disponible con token criptográfico de reserva."""
    slot_start: datetime
    offer_ref: str
    slot_token: str
    slot_end: Optional[datetime] = None
    resource_ref: Optional[str] = None
    resource_name: Optional[str] = None
    is_estimated: bool = False  # True para horarios virtuales estimados del sistema Queuer
    slot_type: str = "official"  # "official" | "estimated"
    notice: Optional[str] = None
    price_estimate: Optional[SlotPriceEstimateDTO] = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class AvailabilityResponseDTO:
    """Respuesta consolidada de disponibilidad."""
    status: str  # "completed" | "processing"
    service_id: int
    slots: list[AvailableSlotDTO] = field(default_factory=list)
    operation_id: Optional[str] = None
    applied_filters: dict[str, Any] = field(default_factory=dict)
    filter_hash: Optional[str] = None
    message: Optional[str] = None


@dataclass
class GetOperationResultQueryDTO:
    """Consulta de resultado de una operación asíncrona diferida."""
    operation_id: str
    user_uuid: UUID


@dataclass
class OperationResultResponseDTO:
    """Resultado de una operación diferida (disponibilidad o dimensión)."""
    status: str  # "completed" | "processing" | "failed"
    operation_id: str
    result_type: str = "availability"  # "availability" | "dimension_options"
    slots: list[AvailableSlotDTO] = field(default_factory=list)
    dimension_options: list[DimensionOptionDTO] = field(default_factory=list)
    error_message: Optional[str] = None
    retry_after_seconds: Optional[int] = None
