from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID


@dataclass
class SchemaFieldDTO:
    """Metadatos de un campo dentro de un ReservationObjectSchema."""
    field_name: str
    data_type: str = "string"
    is_required: bool = True
    high_variance_flag: bool = False
    description: Optional[str] = None
    validation_rules: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReservationObjectSchemaDTO:
    """Definición de un esquema de objeto de reserva (ej. 'vvautos_taller:vehiculo')."""
    schema_id: int
    schema_header: str
    service_id: int
    establishment_id: Optional[int] = None
    section_name: str = "Tus datos"
    schema_fields: list[SchemaFieldDTO] = field(default_factory=list)


@dataclass
class GetReservationObjectSchemasQueryDTO:
    """Parámetros para consultar esquemas por service_id."""
    service_id: int


@dataclass
class ReservationObjectSchemasResponseDTO:
    """Respuesta con los esquemas de objetos de reserva de un servicio."""
    service_id: int
    schemas: list[ReservationObjectSchemaDTO] = field(default_factory=list)


@dataclass
class ReservationObjectDTO:
    """Instancia de un objeto de reserva guardado por el usuario."""
    id: int
    schema_id: int
    object_alias: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class GetUserReservationObjectsQueryDTO:
    """Parámetros para consultar los objetos del usuario autenticado."""
    schema_header: str
    user_uuid: UUID
    user_phone: Optional[str] = None


@dataclass
class UserReservationObjectsResponseDTO:
    """Respuesta con los objetos guardados del usuario para un esquema dado."""
    schema_header: str
    section_name: str
    user_phone: Optional[str] = None
    objects: list[ReservationObjectDTO] = field(default_factory=list)

