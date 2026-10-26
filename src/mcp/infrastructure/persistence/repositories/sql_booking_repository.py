from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.mcp.domain.entities.booking_request import BookingRequest
from src.mcp.domain.enums.mcp_enums import BookingStatus, CalculationBasis
from src.mcp.domain.ports.mcp_ports import IBookingRepository
from src.mcp.domain.value_objects.booking_vo import PriceEstimate
from src.mcp.infrastructure.persistence.models.booking_models import (
    BookingRequestModel,
    BookingStatusHistoryModel,
)


def _dict_to_price_estimate(data: Optional[dict[str, Any]]) -> Optional[PriceEstimate]:
    if not data:
        return None
    return PriceEstimate(
        amount=Decimal(str(data.get("amount", "0.00"))),
        currency=data.get("currency", "DOP"),
        basis=CalculationBasis(data.get("basis", "per_booking")),
        label=data.get("label", "Tarifa estándar"),
        informative=data.get("informative", True),
        note=data.get("note", "Precio informativo"),
    )


class SqlBookingRepository(IBookingRepository):
    """
    Implementación SQL del puerto IBookingRepository.
    Persiste y consulta entidades BookingRequest en el esquema 'mcp' de PostgreSQL,
    registrando cada transición de estado en booking_status_history.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    @staticmethod
    def _to_domain(model: BookingRequestModel) -> BookingRequest:
        return BookingRequest(
            id=model.id,
            user_uuid=model.user_uuid,
            service_id=model.service_id,
            contract_version_id=model.contract_version_id,
            status=BookingStatus(model.status),
            status_reason=model.status_reason,
            idempotency_key=model.idempotency_key,
            request_fingerprint=model.request_fingerprint,
            token_id=model.token_id,
            offer_ref=model.offer_ref,
            hold_id=model.hold_id,
            slot_start=model.slot_start,
            slot_end=model.slot_end,
            resource_ref=model.resource_ref,
            applied_filters=model.applied_filters or {},
            fields=model.fields or {},
            price_estimate=_dict_to_price_estimate(model.price_estimate),
            expires_at=model.expires_at,
            external_ref=model.external_ref,
            assigned_details=model.assigned_details,
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def save(self, booking: BookingRequest) -> BookingRequest:
        model = await self._session.get(BookingRequestModel, booking.id)
        now_utc = datetime.now(timezone.utc)

        price_dict = booking.price_estimate.to_dict() if booking.price_estimate else None

        if model is None:
            # Nueva solicitud
            model = BookingRequestModel(
                id=booking.id,
                user_uuid=booking.user_uuid,
                service_id=booking.service_id,
                contract_version_id=booking.contract_version_id,
                status=booking.status.value,
                status_reason=booking.status_reason,
                idempotency_key=booking.idempotency_key,
                request_fingerprint=booking.request_fingerprint,
                token_id=booking.token_id,
                offer_ref=booking.offer_ref,
                hold_id=booking.hold_id,
                slot_start=booking.slot_start,
                slot_end=booking.slot_end,
                resource_ref=booking.resource_ref,
                applied_filters=booking.applied_filters,
                fields=booking.fields,
                price_estimate=price_dict,
                expires_at=booking.expires_at,
                external_ref=booking.external_ref,
                assigned_details=booking.assigned_details,
                version=booking.version,
                created_at=booking.created_at,
                updated_at=booking.updated_at,
            )
            history = BookingStatusHistoryModel(
                booking_id=booking.id,
                from_status=None,
                to_status=booking.status.value,
                cause="Creación de solicitud de reserva",
                occurred_at=now_utc,
            )
            self._session.add(model)
            self._session.add(history)
        else:
            # Actualización
            if model.status != booking.status.value:
                history = BookingStatusHistoryModel(
                    booking_id=booking.id,
                    from_status=model.status,
                    to_status=booking.status.value,
                    cause=booking.status_reason or "Transición de estado",
                    occurred_at=now_utc,
                )
                self._session.add(history)
                model.status = booking.status.value

            model.status_reason = booking.status_reason
            model.external_ref = booking.external_ref
            model.assigned_details = booking.assigned_details
            model.hold_id = booking.hold_id
            model.price_estimate = price_dict
            model.version = booking.version
            model.updated_at = booking.updated_at or now_utc

        await self._session.flush()
        return booking

    async def get_by_id(self, booking_id: UUID) -> Optional[BookingRequest]:
        model = await self._session.get(BookingRequestModel, booking_id)
        return self._to_domain(model) if model else None

    async def get_by_idempotency_key(
        self, user_uuid: UUID, idempotency_key: str
    ) -> Optional[BookingRequest]:
        stmt = select(BookingRequestModel).where(
            BookingRequestModel.user_uuid == user_uuid,
            BookingRequestModel.idempotency_key == idempotency_key,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def list_by_user(
        self,
        user_uuid: UUID,
        status: Optional[BookingStatus] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[BookingRequest]:
        stmt = select(BookingRequestModel).where(BookingRequestModel.user_uuid == user_uuid)

        if status:
            stmt = stmt.where(BookingRequestModel.status == status.value)

        stmt = (
            stmt.order_by(BookingRequestModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]
