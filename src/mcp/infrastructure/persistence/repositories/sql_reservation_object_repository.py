from __future__ import annotations

import re
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.mcp.domain.entities.reservation_object_entities import (
    ReservationObject,
    ReservationObjectSchema,
    ReservationObjectSchemaField,
)
from src.mcp.domain.ports.mcp_ports import IReservationObjectRepository
from src.mcp.infrastructure.persistence.models.reservation_object_models import (
    ReservationObjectModel,
    ReservationObjectSchemaModel,
)


def _normalize_phone_variants(phone: str) -> list[str]:
    """Genera variantes habituales de formato telefónico (+1809..., 1809..., 809...)."""
    raw = phone.strip()
    digits = re.sub(r"\D", "", raw)
    variants = {raw, digits}
    if digits:
        variants.add(f"+{digits}")
        if len(digits) == 10:  # Ej. 8095551234 -> 18095551234
            variants.add(f"1{digits}")
            variants.add(f"+1{digits}")
        elif len(digits) == 11 and digits.startswith("1"):  # Ej. 18095551234 -> 8095551234
            variants.add(digits[1:])
    return [v for v in variants if v]


def _map_schema_model_to_entity(model: ReservationObjectSchemaModel) -> ReservationObjectSchema:
    fields = []
    raw_fields = model.schema_fields or []
    if isinstance(raw_fields, list):
        for f in raw_fields:
            if isinstance(f, dict):
                fields.append(
                    ReservationObjectSchemaField(
                        field_name=f.get("field_name", ""),
                        data_type=f.get("data_type", "string"),
                        is_required=bool(f.get("is_required", True)),
                        high_variance_flag=bool(f.get("high_variance_flag", False)),
                        description=f.get("description"),
                        validation_rules=f.get("validation_rules", {}),
                    )
                )
    return ReservationObjectSchema(
        id=model.id,
        schema_header=model.schema_header,
        service_id=model.service_id,
        establishment_id=model.establishment_id,
        section_name=model.section_name or "Tus datos",
        schema_fields=fields,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _map_object_model_to_entity(model: ReservationObjectModel) -> ReservationObject:
    return ReservationObject(
        id=model.id,
        schema_id=model.schema_id,
        user_phone=model.user_phone,
        object_alias=model.object_alias,
        object_payload=model.object_payload or {},
        is_deleted=model.is_deleted,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
    )


class SqlReservationObjectRepository(IReservationObjectRepository):
    """Implementación SQLAlchemy para esquemas y objetos de reserva persistentes."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_schemas_by_service_id(self, service_id: int) -> list[ReservationObjectSchema]:
        stmt = (
            select(ReservationObjectSchemaModel)
            .where(ReservationObjectSchemaModel.service_id == service_id)
            .order_by(ReservationObjectSchemaModel.id)
        )
        res = await self._session.execute(stmt)
        models = res.scalars().all()
        return [_map_schema_model_to_entity(m) for m in models]

    async def get_schema_by_header(self, schema_header: str) -> Optional[ReservationObjectSchema]:
        stmt = select(ReservationObjectSchemaModel).where(
            ReservationObjectSchemaModel.schema_header == schema_header.strip()
        )
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            return None
        return _map_schema_model_to_entity(model)

    async def get_objects_by_schema_and_phone(
        self, schema_id: int, user_phone: str
    ) -> list[ReservationObject]:
        phone_variants = _normalize_phone_variants(user_phone)
        stmt = (
            select(ReservationObjectModel)
            .where(
                ReservationObjectModel.schema_id == schema_id,
                ReservationObjectModel.is_deleted.is_(False),
                or_(*(ReservationObjectModel.user_phone == p for p in phone_variants)),
            )
            .order_by(ReservationObjectModel.created_at.desc())
        )
        res = await self._session.execute(stmt)
        models = res.scalars().all()
        return [_map_object_model_to_entity(m) for m in models]

    async def get_user_phone_by_uuid(self, user_uuid: UUID) -> Optional[str]:
        stmt = text("SELECT phone FROM users WHERE uuid = :user_uuid LIMIT 1")
        res = await self._session.execute(stmt, {"user_uuid": str(user_uuid)})
        row = res.scalar_one_or_none()
        return str(row) if row else None

