from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class ReservationObjectSchemaField:
    """Campo individual dentro de un esquema de objeto de reserva."""
    field_name: str
    data_type: str = "string"
    is_required: bool = True
    high_variance_flag: bool = False
    description: Optional[str] = None
    validation_rules: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReservationObjectSchema:
    """Entidad de dominio para un esquema de objeto de reserva."""
    id: int
    schema_header: str
    service_id: int
    establishment_id: Optional[int] = None
    section_name: str = "Tus datos"
    schema_fields: list[ReservationObjectSchemaField] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class ReservationObject:
    """Entidad de dominio para un objeto guardado de un usuario."""
    id: int
    schema_id: int
    user_phone: str
    object_payload: dict[str, Any]
    object_alias: Optional[str] = None
    is_deleted: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

