from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

import jsonschema

from src.mcp.application.dto.booking_dtos import (
    BookingCreationResultDTO,
    CreateBookingInputDTO,
)
from src.mcp.domain.entities.booking_request import BookingRequest
from src.mcp.domain.enums.mcp_enums import AvailabilityPattern, BookingStatus
from src.mcp.domain.exceptions.mcp_exceptions import (
    BookingRuleViolationException,
    ContractValidationException,
    EntityNotFoundException,
    IdempotencyConflictException,
)
from src.mcp.domain.ports.mcp_ports import (
    IBookingRepository,
    ICatalogServiceRepository,
    IContractRepository,
    IHoldManager,
    IOutboxRepository,
)
from src.mcp.infrastructure.security.slot_token_codec import SlotTokenCodec


def compute_request_fingerprint(
    user_uuid: UUID,
    service_id: int,
    slot_token: Optional[str],
    fields: dict[str, Any],
) -> str:
    """Calcula el hash SHA-256 canónico del payload de solicitud para verificación de idempotencia."""
    payload = {
        "user_uuid": str(user_uuid),
        "service_id": service_id,
        "slot_token": slot_token or "",
        "fields": fields,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class CreateBookingRequestUseCase:
    """
    Caso de uso: Crear solicitud de reserva diferida (create_booking_request).
    Implementa:
    1. Verificación estricta de idempotencia por user_uuid + idempotency_key.
    2. Bifurcación:
       - Con slot_token (canchas, cines, o slots estimados Queuer): decodifica, valida expiración y adquiere hold atómico.
       - Sin slot_token (patrón ON_DEMAND_REQUEST / veterinaria): omite slot y hold, valida contra schema.
    3. Validación de campos de reserva con jsonschema contra el contrato dinámico.
    4. Transacción ACID: guarda BookingRequest en PostgreSQL y registra evento BookingRequested en Outbox.
    5. Retorno inmediato del estado 'requested' conforme al diseño event-driven asíncrono (Outbox/Inbox).
    """

    def __init__(
        self,
        booking_repo: IBookingRepository,
        contract_repo: IContractRepository,
        hold_manager: IHoldManager,
        outbox_repo: IOutboxRepository,
        token_codec: SlotTokenCodec,
        catalog_repo: Optional[ICatalogServiceRepository] = None,
    ):
        self._booking_repo = booking_repo
        self._contract_repo = contract_repo
        self._hold_manager = hold_manager
        self._outbox_repo = outbox_repo
        self._token_codec = token_codec
        self._catalog_repo = catalog_repo

    async def execute(self, query: CreateBookingInputDTO) -> BookingCreationResultDTO:
        # 1. Determinación preliminar de service_id y extracción de slot_token
        is_on_demand = query.slot_token is None

        if is_on_demand:
            if query.service_id is None:
                raise ContractValidationException(
                    "Para solicitudes sin 'slot_token' (patrón bajo demanda) se requiere especificar 'service_id'."
                )
            service_id = query.service_id
            slot_token_obj = None
        else:
            # Decodificar y validar token criptográfico
            slot_token_obj = self._token_codec.decode(query.slot_token)
            self._token_codec.verify_for_user(slot_token_obj, query.user_uuid)
            service_id = slot_token_obj.service_id

        # 2. Verificación de Idempotencia
        fingerprint = compute_request_fingerprint(
            user_uuid=query.user_uuid,
            service_id=service_id,
            slot_token=query.slot_token,
            fields=query.fields,
        )
        existing_booking = await self._booking_repo.get_by_idempotency_key(
            user_uuid=query.user_uuid,
            idempotency_key=query.idempotency_key,
        )
        if existing_booking:
            if existing_booking.request_fingerprint == fingerprint:
                return BookingCreationResultDTO(
                    booking_id=existing_booking.id,
                    status=existing_booking.status.value,
                    service_id=existing_booking.service_id,
                    slot_start=existing_booking.slot_start,
                    slot_end=existing_booking.slot_end,
                    applied_filters=existing_booking.applied_filters,
                    status_reason=existing_booking.status_reason,
                    external_ref=existing_booking.external_ref,
                    expires_at=existing_booking.expires_at,
                    message="Solicitud de reserva ya procesada previamente (repetición idempotente segura).",
                )
            raise IdempotencyConflictException(
                "Conflicto de idempotencia: se ha enviado la misma idempotency_key con un contenido de solicitud diferente."
            )

        # 3. Obtener y validar contrato de servicio
        contract = await self._contract_repo.get_active_by_service_id(service_id)
        if not contract:
            raise EntityNotFoundException(
                f"No se encontró un contrato activo publicado para el servicio con id {service_id}."
            )

        # 4. Validar consistencia de patrón de disponibilidad
        if is_on_demand and contract.pattern != AvailabilityPattern.ON_DEMAND_REQUEST:
            raise ContractValidationException(
                f"El servicio {service_id} no admite solicitudes sin slot_token (patrón actual: {contract.pattern.value})."
            )

        # 5. Validación de Campos de Reserva (JSON Schema)
        if contract.booking_fields_schema and contract.booking_fields_schema.get("properties"):
            try:
                jsonschema.validate(instance=query.fields, schema=contract.booking_fields_schema)
            except jsonschema.ValidationError as err:
                raise ContractValidationException(
                    f"Error de validación en campos de reserva: {err.message}"
                )

        # 6. Adquisición de Hold Atómico en Redis (solo si no es on_demand ni estimado Queuer)
        booking_id = uuid4()
        hold_id: Optional[str] = None
        offer_ref: Optional[str] = None
        slot_start: Optional[datetime] = None
        slot_end: Optional[datetime] = None
        token_id: Optional[str] = None
        applied_filters: dict[str, Any] = {}
        is_estimated: bool = False

        if slot_token_obj is not None:
            token_id = slot_token_obj.token_id
            offer_ref = slot_token_obj.offer_ref
            slot_start = slot_token_obj.slot_start
            slot_end = slot_token_obj.slot_end
            applied_filters = slot_token_obj.applied_filters
            is_estimated = slot_token_obj.is_estimated

            if not is_estimated:
                # Slot real: adquirir hold atómico con TTL de seguridad (request_ttl_seconds)
                hold_acquired = await self._hold_manager.place_hold(
                    offer_ref=offer_ref,
                    booking_id=booking_id,
                    ttl_seconds=contract.request_ttl_seconds,
                )
                if not hold_acquired:
                    raise BookingRuleViolationException(
                        "El horario seleccionado ya no está disponible o ha sido bloqueado por otro usuario."
                    )
                hold_id = f"hold:{offer_ref}"

        # 7. Persistencia de la Reserva e Historial (Transacción ACID)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=contract.request_ttl_seconds)
        booking = BookingRequest(
            id=booking_id,
            user_uuid=query.user_uuid,
            service_id=service_id,
            contract_version_id=contract.id,
            status=BookingStatus.REQUESTED,
            idempotency_key=query.idempotency_key,
            request_fingerprint=fingerprint,
            token_id=token_id,
            offer_ref=offer_ref,
            hold_id=hold_id,
            slot_start=slot_start,
            slot_end=slot_end,
            applied_filters=applied_filters,
            fields=query.fields,
            expires_at=expires_at,
        )
        await self._booking_repo.save(booking)

        # 8. Registro de Evento en Outbox
        combo_code: Optional[str] = None
        if self._catalog_repo is not None:
            svc = await self._catalog_repo.get_by_id(service_id)
            if svc:
                combo_code = svc.combo_code

        outbox_payload = {
            "booking_id": str(booking.id),
            "user_uuid": str(booking.user_uuid),
            "user_phone": query.user_phone,
            "service_id": booking.service_id,
            "combo_code": combo_code,
            "contract_version_id": str(booking.contract_version_id),
            "token_id": booking.token_id,
            "offer_ref": booking.offer_ref,
            "slot_start": booking.slot_start.isoformat() if booking.slot_start else None,
            "slot_end": booking.slot_end.isoformat() if booking.slot_end else None,
            "is_estimated": is_estimated,
            "applied_filters": booking.applied_filters,
            "fields": booking.fields,
            "expires_at": booking.expires_at.isoformat(),
        }
        await self._outbox_repo.record_event(
            event_type="BookingRequested",
            aggregate_id=booking.id,
            payload=outbox_payload,
            correlation_id=query.idempotency_key,
        )

        # 9. Retorno inmediato del estado 'requested' conforme al diseño event-driven asíncrono
        # La reserva será procesada por OutboxRelayWorker -> Redis Stream -> Ejecutor -> InboxConsumerWorker
        return BookingCreationResultDTO(
            booking_id=booking.id,
            status=booking.status.value,
            service_id=service_id,
            slot_start=slot_start,
            slot_end=slot_end,
            is_estimated=is_estimated,
            applied_filters=applied_filters,
            expires_at=booking.expires_at,
            message=(
                "Solicitud de reserva registrada exitosamente. Está siendo procesada en segundo plano por el establecimiento. "
                "Puedes consultar su estado con la herramienta 'get_booking_status'."
            ),
        )
