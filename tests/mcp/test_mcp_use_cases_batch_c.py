from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.mcp.application.dto.booking_dtos import (
    CancelBookingInputDTO,
    CreateBookingInputDTO,
    GetBookingStatusQueryDTO,
    ListMyBookingsQueryDTO,
)
from src.mcp.application.use_cases.cancel_booking import CancelBookingUseCase
from src.mcp.application.use_cases.create_booking_request import (
    CreateBookingRequestUseCase,
    compute_request_fingerprint,
)
from src.mcp.application.use_cases.get_booking_status import GetBookingStatusUseCase
from src.mcp.application.use_cases.list_my_bookings import ListMyBookingsUseCase
from src.mcp.domain.entities.booking_request import BookingRequest
from src.mcp.domain.entities.catalog_entities import CatalogService, Establishment
from src.mcp.domain.entities.contract_entities import ServiceContractVersion
from src.mcp.domain.enums.mcp_enums import (
    AvailabilityPattern,
    BookingStatus,
    CalculationBasis,
    ContractStatus,
    RuleType,
)
from src.mcp.domain.exceptions.mcp_exceptions import (
    BookingRuleViolationException,
    ContractValidationException,
    EntityNotFoundException,
    IdempotencyConflictException,
    InvalidStateTransitionException,
    SlotTokenInvalidException,
)
from src.mcp.domain.value_objects.booking_vo import PriceEstimate
from src.mcp.domain.value_objects.slot_token import SlotToken
from src.mcp.infrastructure.security.slot_token_codec import SlotTokenCodec


@pytest.fixture
def mock_token_codec():
    return SlotTokenCodec(secret="test-secret-key-12345678901234567890")


@pytest.fixture
def sample_user_uuid():
    return uuid4()


@pytest.fixture
def sample_contract():
    return ServiceContractVersion(
        id=uuid4(),
        service_id=20,
        version_no=1,
        status=ContractStatus.PUBLISHED,
        pattern=AvailabilityPattern.SLOT_OBJECT,
        request_ttl_seconds=900,
        booking_fields_schema={
            "type": "object",
            "properties": {
                "player_count": {"type": "integer", "minimum": 1, "maximum": 4},
                "notes": {"type": "string"},
            },
            "required": ["player_count"],
        },
    )


@pytest.fixture
def on_demand_contract():
    return ServiceContractVersion(
        id=uuid4(),
        service_id=30,
        version_no=1,
        status=ContractStatus.PUBLISHED,
        pattern=AvailabilityPattern.ON_DEMAND_REQUEST,
        request_ttl_seconds=3600,
        booking_fields_schema={
            "type": "object",
            "properties": {
                "pet_name": {"type": "string"},
                "symptoms": {"type": "string"},
            },
            "required": ["pet_name", "symptoms"],
        },
    )


@pytest.fixture
def sample_slot_token_str(mock_token_codec, sample_user_uuid):
    token = mock_token_codec.encode(
        token_id="tok-test-123",
        user_uuid=sample_user_uuid,
        offer_ref="off-court-4",
        service_id=20,
        slot_start=datetime(2026, 10, 27, 18, 0, tzinfo=timezone.utc),
        slot_end=datetime(2026, 10, 27, 19, 30, tzinfo=timezone.utc),
        contract_version="1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        applied_filters={"court_surface": "cristal", "indoor": True},
        is_estimated=False,
    )
    return token.raw_token


@pytest.fixture
def sample_estimated_slot_token_str(mock_token_codec, sample_user_uuid):
    token = mock_token_codec.encode(
        token_id="tok-est-999",
        user_uuid=sample_user_uuid,
        offer_ref="est-court-v1",
        service_id=20,
        slot_start=datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc),
        slot_end=datetime(2026, 10, 28, 11, 30, tzinfo=timezone.utc),
        contract_version="1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        applied_filters={"court_surface": "cristal"},
        is_estimated=True,
    )
    return token.raw_token


# =========================================================================
# 1. Pruebas de CreateBookingRequestUseCase
# =========================================================================

@pytest.mark.asyncio
async def test_create_booking_happy_path_slot_based(
    mock_token_codec, sample_user_uuid, sample_contract, sample_slot_token_str
):
    """Prueba flujo exitoso con slot_token: adquisición de hold atómico, registro ACID en Outbox y retorno requested."""
    mock_booking_repo = MagicMock()
    mock_booking_repo.get_by_idempotency_key = AsyncMock(return_value=None)
    saved_bookings: list[BookingRequest] = []

    async def mock_save(b: BookingRequest):
        saved_bookings.append(b)
        return b

    mock_booking_repo.save = AsyncMock(side_effect=mock_save)

    mock_contract_repo = MagicMock()
    mock_contract_repo.get_active_by_service_id = AsyncMock(return_value=sample_contract)

    mock_hold_manager = MagicMock()
    mock_hold_manager.place_hold = AsyncMock(return_value=True)

    mock_outbox_repo = MagicMock()
    mock_outbox_repo.record_event = AsyncMock()

    use_case = CreateBookingRequestUseCase(
        booking_repo=mock_booking_repo,
        contract_repo=mock_contract_repo,
        hold_manager=mock_hold_manager,
        outbox_repo=mock_outbox_repo,
        token_codec=mock_token_codec,
    )

    query = CreateBookingInputDTO(
        user_uuid=sample_user_uuid,
        idempotency_key="idemp-key-101",
        slot_token=sample_slot_token_str,
        fields={"player_count": 4, "notes": "Traeremos pelotas nuevas"},
    )

    result = await use_case.execute(query)

    assert result.status == "requested"
    assert result.service_id == 20
    assert result.applied_filters == {"court_surface": "cristal", "indoor": True}
    assert result.is_estimated is False
    assert "segundo plano" in result.message

    # Verificar hold colocado con TTL del contrato (900s)
    mock_hold_manager.place_hold.assert_awaited_once_with(
        offer_ref="off-court-4",
        booking_id=result.booking_id,
        ttl_seconds=900,
    )

    # Verificar Outbox event registrado
    mock_outbox_repo.record_event.assert_awaited_once()
    event_args = mock_outbox_repo.record_event.call_args[1]
    assert event_args["event_type"] == "BookingRequested"
    assert event_args["correlation_id"] == "idemp-key-101"
    assert event_args["payload"]["token_id"] == "tok-test-123"
    assert event_args["payload"]["applied_filters"] == {"court_surface": "cristal", "indoor": True}


@pytest.mark.asyncio
async def test_create_booking_queuer_virtual_slot(
    mock_token_codec, sample_user_uuid, sample_contract, sample_estimated_slot_token_str
):
    """Prueba que un slot virtual del Queuer (is_estimated=True) no adquiere hold físico y emite evento con is_estimated."""
    mock_booking_repo = MagicMock()
    mock_booking_repo.get_by_idempotency_key = AsyncMock(return_value=None)
    mock_booking_repo.save = AsyncMock(side_effect=lambda b: b)

    mock_contract_repo = MagicMock()
    mock_contract_repo.get_active_by_service_id = AsyncMock(return_value=sample_contract)

    mock_hold_manager = MagicMock()
    mock_hold_manager.place_hold = AsyncMock()

    mock_outbox_repo = MagicMock()
    mock_outbox_repo.record_event = AsyncMock()

    use_case = CreateBookingRequestUseCase(
        booking_repo=mock_booking_repo,
        contract_repo=mock_contract_repo,
        hold_manager=mock_hold_manager,
        outbox_repo=mock_outbox_repo,
        token_codec=mock_token_codec,
    )

    query = CreateBookingInputDTO(
        user_uuid=sample_user_uuid,
        idempotency_key="idemp-key-queuer",
        slot_token=sample_estimated_slot_token_str,
        fields={"player_count": 4},
    )

    result = await use_case.execute(query)

    assert result.status == "requested"
    assert result.is_estimated is True
    assert "segundo plano" in result.message

    # Verificar que NUNCA se intentó adquirir hold en Redis para slots virtuales
    mock_hold_manager.place_hold.assert_not_called()

    # Verificar que el evento en Outbox lleva is_estimated=True
    event_args = mock_outbox_repo.record_event.call_args[1]
    assert event_args["payload"]["is_estimated"] is True


@pytest.mark.asyncio
async def test_create_booking_on_demand_happy_path(
    mock_token_codec, sample_user_uuid, on_demand_contract
):
    """Prueba creación exitosa bajo demanda (veterinaria/formulario sin slot)."""
    mock_booking_repo = MagicMock()
    mock_booking_repo.get_by_idempotency_key = AsyncMock(return_value=None)
    mock_booking_repo.save = AsyncMock(side_effect=lambda b: b)

    mock_contract_repo = MagicMock()
    mock_contract_repo.get_active_by_service_id = AsyncMock(return_value=on_demand_contract)

    mock_hold_manager = MagicMock()
    mock_hold_manager.place_hold = AsyncMock()

    mock_outbox_repo = MagicMock()
    mock_outbox_repo.record_event = AsyncMock()

    use_case = CreateBookingRequestUseCase(
        booking_repo=mock_booking_repo,
        contract_repo=mock_contract_repo,
        hold_manager=mock_hold_manager,
        outbox_repo=mock_outbox_repo,
        token_codec=mock_token_codec,
    )

    query = CreateBookingInputDTO(
        user_uuid=sample_user_uuid,
        idempotency_key="idemp-vet-1",
        slot_token=None,
        service_id=30,
        fields={"pet_name": "Max", "symptoms": "Fiebre y letargo"},
    )

    result = await use_case.execute(query)

    assert result.status == "requested"
    assert result.service_id == 30
    assert result.slot_start is None
    assert result.slot_end is None
    mock_hold_manager.place_hold.assert_not_called()
    mock_outbox_repo.record_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_booking_on_demand_schema_validation_error(
    mock_token_codec, sample_user_uuid, on_demand_contract
):
    """Prueba que campos inválidos según el schema del contrato levantan ContractValidationException."""
    mock_booking_repo = MagicMock()
    mock_booking_repo.get_by_idempotency_key = AsyncMock(return_value=None)

    mock_contract_repo = MagicMock()
    mock_contract_repo.get_active_by_service_id = AsyncMock(return_value=on_demand_contract)

    use_case = CreateBookingRequestUseCase(
        booking_repo=mock_booking_repo,
        contract_repo=mock_contract_repo,
        hold_manager=MagicMock(),
        outbox_repo=MagicMock(),
        token_codec=mock_token_codec,
    )

    query = CreateBookingInputDTO(
        user_uuid=sample_user_uuid,
        idempotency_key="idemp-vet-err",
        slot_token=None,
        service_id=30,
        fields={"pet_name": "Max"},  # Falta 'symptoms' que es requerido
    )

    with pytest.raises(ContractValidationException) as exc_info:
        await use_case.execute(query)

    assert "Error de validación en campos de reserva" in str(exc_info.value)


@pytest.mark.asyncio
async def test_create_booking_hold_collision_raises_rule_violation(
    mock_token_codec, sample_user_uuid, sample_contract, sample_slot_token_str
):
    """Prueba que si el slot ya fue bloqueado (hold fallido), levanta BookingRuleViolationException."""
    mock_booking_repo = MagicMock()
    mock_booking_repo.get_by_idempotency_key = AsyncMock(return_value=None)

    mock_contract_repo = MagicMock()
    mock_contract_repo.get_active_by_service_id = AsyncMock(return_value=sample_contract)

    mock_hold_manager = MagicMock()
    mock_hold_manager.place_hold = AsyncMock(return_value=False)  # Colisión de concurrencia

    use_case = CreateBookingRequestUseCase(
        booking_repo=mock_booking_repo,
        contract_repo=mock_contract_repo,
        hold_manager=mock_hold_manager,
        outbox_repo=MagicMock(),
        token_codec=mock_token_codec,
    )

    query = CreateBookingInputDTO(
        user_uuid=sample_user_uuid,
        idempotency_key="idemp-collision",
        slot_token=sample_slot_token_str,
        fields={"player_count": 2},
    )

    with pytest.raises(BookingRuleViolationException) as exc_info:
        await use_case.execute(query)

    assert "ya no está disponible o ha sido bloqueado" in str(exc_info.value)


@pytest.mark.asyncio
async def test_create_booking_idempotent_replay(
    mock_token_codec, sample_user_uuid, sample_contract, sample_slot_token_str
):
    """Prueba que reintentar exactamente la misma solicitud retorna la reserva existente sin duplicar."""
    fingerprint = compute_request_fingerprint(
        user_uuid=sample_user_uuid,
        service_id=20,
        slot_token=sample_slot_token_str,
        fields={"player_count": 4},
    )

    existing_booking = BookingRequest(
        id=uuid4(),
        user_uuid=sample_user_uuid,
        service_id=20,
        contract_version_id=sample_contract.id,
        status=BookingStatus.REQUESTED,
        idempotency_key="idemp-replay-1",
        request_fingerprint=fingerprint,
        slot_start=datetime(2026, 10, 27, 18, 0, tzinfo=timezone.utc),
        slot_end=datetime(2026, 10, 27, 19, 30, tzinfo=timezone.utc),
        applied_filters={"court_surface": "cristal"},
    )

    mock_booking_repo = MagicMock()
    mock_booking_repo.get_by_idempotency_key = AsyncMock(return_value=existing_booking)

    use_case = CreateBookingRequestUseCase(
        booking_repo=mock_booking_repo,
        contract_repo=MagicMock(),
        hold_manager=MagicMock(),
        outbox_repo=MagicMock(),
        token_codec=mock_token_codec,
    )

    query = CreateBookingInputDTO(
        user_uuid=sample_user_uuid,
        idempotency_key="idemp-replay-1",
        slot_token=sample_slot_token_str,
        fields={"player_count": 4},
    )

    result = await use_case.execute(query)

    assert result.booking_id == existing_booking.id
    assert "repetición idempotente" in result.message


@pytest.mark.asyncio
async def test_create_booking_idempotency_conflict_different_payload(
    mock_token_codec, sample_user_uuid, sample_contract, sample_slot_token_str
):
    """Prueba que misma idempotency_key con contenido diferente levanta IdempotencyConflictException."""
    existing_booking = BookingRequest(
        id=uuid4(),
        user_uuid=sample_user_uuid,
        service_id=20,
        contract_version_id=sample_contract.id,
        status=BookingStatus.REQUESTED,
        idempotency_key="idemp-conflict-1",
        request_fingerprint="fingerprint_anterior_distinto",
    )

    mock_booking_repo = MagicMock()
    mock_booking_repo.get_by_idempotency_key = AsyncMock(return_value=existing_booking)

    use_case = CreateBookingRequestUseCase(
        booking_repo=mock_booking_repo,
        contract_repo=MagicMock(),
        hold_manager=MagicMock(),
        outbox_repo=MagicMock(),
        token_codec=mock_token_codec,
    )

    query = CreateBookingInputDTO(
        user_uuid=sample_user_uuid,
        idempotency_key="idemp-conflict-1",
        slot_token=sample_slot_token_str,
        fields={"player_count": 4},
    )

    with pytest.raises(IdempotencyConflictException):
        await use_case.execute(query)


@pytest.mark.asyncio
async def test_create_booking_token_user_mismatch_raises_slot_invalid(
    mock_token_codec, sample_contract, sample_slot_token_str
):
    """Prueba que un usuario intentando canjear el token de slot de otro usuario es rechazado."""
    different_user_uuid = uuid4()

    use_case = CreateBookingRequestUseCase(
        booking_repo=MagicMock(),
        contract_repo=MagicMock(),
        hold_manager=MagicMock(),
        outbox_repo=MagicMock(),
        token_codec=mock_token_codec,
    )

    query = CreateBookingInputDTO(
        user_uuid=different_user_uuid,  # No coincide con el user_uuid del token firmado
        idempotency_key="idemp-mismatch",
        slot_token=sample_slot_token_str,
        fields={"player_count": 2},
    )

    with pytest.raises(SlotTokenInvalidException):
        await use_case.execute(query)


# =========================================================================
# 2. Pruebas de GetBookingStatusUseCase
# =========================================================================

@pytest.mark.asyncio
async def test_get_booking_status_happy_path(sample_user_uuid):
    """Prueba consulta exitosa de estado, nombres de catálogo, precio y explicación contextual."""
    booking_id = uuid4()
    booking = BookingRequest(
        id=booking_id,
        user_uuid=sample_user_uuid,
        service_id=20,
        contract_version_id=uuid4(),
        status=BookingStatus.CONFIRMED,
        external_ref="EXT-PADEL-10",
        applied_filters={"surface": "panoramica"},
        fields={"notes": "Favor dejar encendidas las luces"},
        price_estimate=PriceEstimate(
            amount=Decimal("1800.00"),
            currency="DOP",
            basis=CalculationBasis.PER_BOOKING,
            label="Tarifa estándar",
            informative=False,
        ),
    )

    mock_booking_repo = MagicMock()
    mock_booking_repo.get_by_id = AsyncMock(return_value=booking)

    mock_cat_repo = MagicMock()
    mock_cat_repo.get_by_id = AsyncMock(
        return_value=CatalogService(
            id=20,
            establishment_id=5,
            name="Pista Central",
            category_name="Deportes",
        )
    )

    mock_est_repo = MagicMock()
    mock_est_repo.get_by_id = AsyncMock(
        return_value=Establishment(
            id=5,
            name="Club Pádel Santo Domingo",
            code="CPSD",
            rule_type=RuleType.ONLY_TODAY,
        )
    )

    use_case = GetBookingStatusUseCase(
        booking_repo=mock_booking_repo,
        catalog_service_repo=mock_cat_repo,
        establishment_repo=mock_est_repo,
    )

    query = GetBookingStatusQueryDTO(booking_id=booking_id, user_uuid=sample_user_uuid)
    result = await use_case.execute(query)

    assert result.booking_id == booking_id
    assert result.status == "confirmed"
    assert result.service_name == "Pista Central"
    assert result.establishment_name == "Club Pádel Santo Domingo"
    assert result.external_ref == "EXT-PADEL-10"
    assert result.applied_filters == {"surface": "panoramica"}
    assert result.price_estimate is not None
    assert result.price_estimate["amount"] == "1800.00"
    assert "Reserva confirmada exitosamente" in result.explanation


@pytest.mark.asyncio
async def test_get_booking_status_isolation_wrong_user_raises_not_found(sample_user_uuid):
    """Prueba de seguridad multi-inquilino: consultar reserva de otro usuario levanta EntityNotFoundException."""
    booking_id = uuid4()
    other_user_uuid = uuid4()

    booking = BookingRequest(
        id=booking_id,
        user_uuid=other_user_uuid,  # Pertenece a otro usuario
        service_id=20,
        contract_version_id=uuid4(),
        status=BookingStatus.REQUESTED,
    )

    mock_booking_repo = MagicMock()
    mock_booking_repo.get_by_id = AsyncMock(return_value=booking)

    use_case = GetBookingStatusUseCase(
        booking_repo=mock_booking_repo,
        catalog_service_repo=MagicMock(),
        establishment_repo=MagicMock(),
    )

    query = GetBookingStatusQueryDTO(booking_id=booking_id, user_uuid=sample_user_uuid)

    with pytest.raises(EntityNotFoundException):
        await use_case.execute(query)


# =========================================================================
# 3. Pruebas de ListMyBookingsUseCase
# =========================================================================

@pytest.mark.asyncio
async def test_list_my_bookings_pagination_and_enrichment(sample_user_uuid):
    """Prueba listado paginado, resolución de nombres y cálculo de next_cursor."""
    b1 = BookingRequest(
        id=uuid4(),
        user_uuid=sample_user_uuid,
        service_id=20,
        contract_version_id=uuid4(),
        status=BookingStatus.CONFIRMED,
        applied_filters={"court": "P1"},
    )
    b2 = BookingRequest(
        id=uuid4(),
        user_uuid=sample_user_uuid,
        service_id=20,
        contract_version_id=uuid4(),
        status=BookingStatus.REQUESTED,
        applied_filters={"court": "P2"},
    )
    b3 = BookingRequest(
        id=uuid4(),
        user_uuid=sample_user_uuid,
        service_id=20,
        contract_version_id=uuid4(),
        status=BookingStatus.CANCELLED,
    )

    mock_booking_repo = MagicMock()
    # Solicitamos limit=2; el repo retorna 3 elementos (simulando que hay más páginas)
    mock_booking_repo.list_by_user = AsyncMock(return_value=[b1, b2, b3])

    mock_cat_repo = MagicMock()
    mock_cat_repo.get_by_id = AsyncMock(
        return_value=CatalogService(
            id=20,
            establishment_id=5,
            name="Cancha Principal",
            category_name="Deportes",
        )
    )

    use_case = ListMyBookingsUseCase(
        booking_repo=mock_booking_repo,
        catalog_service_repo=mock_cat_repo,
    )

    query = ListMyBookingsQueryDTO(
        user_uuid=sample_user_uuid,
        status_filter="confirmed",
        cursor=0,
        limit=2,
    )

    result = await use_case.execute(query)

    assert len(result.items) == 2
    assert result.next_cursor == 2
    assert result.items[0].booking_id == b1.id
    assert result.items[0].service_name == "Cancha Principal"
    assert result.items[0].applied_filters == {"court": "P1"}
    assert result.items[1].applied_filters == {"court": "P2"}


@pytest.mark.asyncio
async def test_list_my_bookings_invalid_status_filter_raises_error(sample_user_uuid):
    """Prueba que un status_filter no reconocido genera ContractValidationException."""
    use_case = ListMyBookingsUseCase(
        booking_repo=MagicMock(),
        catalog_service_repo=MagicMock(),
    )

    query = ListMyBookingsQueryDTO(
        user_uuid=sample_user_uuid,
        status_filter="status_invalido_xyz",
    )

    with pytest.raises(ContractValidationException):
        await use_case.execute(query)


# =========================================================================
# 4. Pruebas de CancelBookingUseCase
# =========================================================================

@pytest.mark.asyncio
async def test_cancel_booking_happy_path(sample_user_uuid):
    """Prueba cancelación exitosa: transición a cancel_requested y registro en Outbox."""
    booking_id = uuid4()
    booking = BookingRequest(
        id=booking_id,
        user_uuid=sample_user_uuid,
        service_id=20,
        contract_version_id=uuid4(),
        status=BookingStatus.CONFIRMED,
        external_ref="EXT-CANCEL-ME",
    )

    mock_booking_repo = MagicMock()
    mock_booking_repo.get_by_id = AsyncMock(return_value=booking)
    mock_booking_repo.save = AsyncMock(side_effect=lambda b: b)

    mock_outbox_repo = MagicMock()
    mock_outbox_repo.record_event = AsyncMock()

    use_case = CancelBookingUseCase(
        booking_repo=mock_booking_repo,
        outbox_repo=mock_outbox_repo,
    )

    query = CancelBookingInputDTO(
        booking_id=booking_id,
        user_uuid=sample_user_uuid,
        reason="Imprevisto laboral, no podré asistir.",
    )

    result = await use_case.execute(query)

    assert result.booking_id == booking_id
    assert result.status == "cancel_requested"
    assert "cancelación registrada exitosamente" in result.message

    assert booking.status == BookingStatus.CANCEL_REQUESTED
    assert booking.status_reason == "Imprevisto laboral, no podré asistir."

    mock_outbox_repo.record_event.assert_awaited_once()
    event_args = mock_outbox_repo.record_event.call_args[1]
    assert event_args["event_type"] == "CancellationRequested"
    assert event_args["payload"]["reason"] == "Imprevisto laboral, no podré asistir."


@pytest.mark.asyncio
async def test_cancel_booking_isolation_wrong_user(sample_user_uuid):
    """Prueba que un usuario no puede cancelar la reserva de otro."""
    booking_id = uuid4()
    booking = BookingRequest(
        id=booking_id,
        user_uuid=uuid4(),  # Otro usuario
        service_id=20,
        contract_version_id=uuid4(),
        status=BookingStatus.CONFIRMED,
    )

    mock_booking_repo = MagicMock()
    mock_booking_repo.get_by_id = AsyncMock(return_value=booking)

    use_case = CancelBookingUseCase(
        booking_repo=mock_booking_repo,
        outbox_repo=MagicMock(),
    )

    query = CancelBookingInputDTO(
        booking_id=booking_id,
        user_uuid=sample_user_uuid,
        reason="Intento cancelar ajeno",
    )

    with pytest.raises(EntityNotFoundException):
        await use_case.execute(query)


@pytest.mark.asyncio
async def test_cancel_booking_invalid_transition_when_already_cancelled(sample_user_uuid):
    """Prueba que intentar cancelar una reserva ya cancelada levanta InvalidStateTransitionException."""
    booking_id = uuid4()
    booking = BookingRequest(
        id=booking_id,
        user_uuid=sample_user_uuid,
        service_id=20,
        contract_version_id=uuid4(),
        status=BookingStatus.CANCELLED,  # Ya cancelada
    )

    mock_booking_repo = MagicMock()
    mock_booking_repo.get_by_id = AsyncMock(return_value=booking)

    use_case = CancelBookingUseCase(
        booking_repo=mock_booking_repo,
        outbox_repo=MagicMock(),
    )

    query = CancelBookingInputDTO(
        booking_id=booking_id,
        user_uuid=sample_user_uuid,
        reason="Cancelar de nuevo",
    )

    with pytest.raises(InvalidStateTransitionException):
        await use_case.execute(query)
