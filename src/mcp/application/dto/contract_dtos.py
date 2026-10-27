from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID


@dataclass
class GetServiceContractQueryDTO:
    """Parámetros para consultar el contrato dinámico de un servicio."""
    service_id: int


@dataclass
class DimensionOptionDTO:
    """Opción individual de una dimensión (ej. tipo de superficie, sede o recurso)."""
    value_key: str
    label: str
    description: Optional[str] = None
    position: int = 0


@dataclass
class ContractDimensionProjectionDTO:
    """Proyección pública de una dimensión de disponibilidad de un contrato."""
    key: str
    label: str
    description: Optional[str] = None
    values_source: str = "inline"
    apply_mode: str = "post_filter"
    required: bool = False
    allows_any: bool = False
    reports_counts: bool = False
    depends_on: list[str] = field(default_factory=list)
    values: Optional[list[DimensionOptionDTO]] = None


@dataclass
class ServiceContractDTO:
    """Proyección de contrato publicada para Claude."""
    service_id: int
    pattern: str  # slot_object, appointment_resource, session_seats, on_demand_request
    contract_version: str
    contract_version_id: UUID
    availability_dimensions: list[ContractDimensionProjectionDTO] = field(default_factory=list)
    booking_fields: dict[str, Any] = field(default_factory=dict)
    payment_policy: dict[str, Any] = field(default_factory=dict)
    cancellation_policy: dict[str, Any] = field(default_factory=dict)
    request_expires_in_seconds: int = 900


@dataclass
class GetDimensionOptionsQueryDTO:
    """Parámetros para resolver opciones dinámicas de una dimensión dependiente."""
    service_id: int
    dimension_key: str
    context: dict[str, Any] = field(default_factory=dict)
    user_uuid: Optional[UUID] = None
    user_phone: Optional[str] = None


@dataclass
class DimensionOptionsResponseDTO:
    """Respuesta a la resolución de opciones de una dimensión."""
    status: str  # "completed" | "processing"
    dimension_key: str
    options: list[DimensionOptionDTO] = field(default_factory=list)
    operation_id: Optional[str] = None
    context_hash: Optional[str] = None
    expires_in_seconds: Optional[int] = None
