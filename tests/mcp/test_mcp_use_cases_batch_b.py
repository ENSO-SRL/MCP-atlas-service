from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.mcp.application.dto.availability_dtos import (
    CheckAvailabilityQueryDTO,
    GetOperationResultQueryDTO,
)
from src.mcp.application.use_cases.check_availability import CheckAvailabilityUseCase
from src.mcp.application.use_cases.get_operation_result import GetOperationResultUseCase
from src.mcp.domain.entities.catalog_entities import CatalogService, Establishment
from src.mcp.domain.entities.contract_entities import ServiceContractVersion
from src.mcp.domain.entities.service_price_rule import ServicePriceRule
from src.mcp.domain.enums.mcp_enums import (
    AvailabilityPattern,
    CalculationBasis,
    ContractStatus,
    RuleType,
)
from src.mcp.domain.exceptions.mcp_exceptions import (
    BookingRuleViolationException,
    EntityNotFoundException,
)
from src.mcp.infrastructure.security.slot_token_codec import SlotTokenCodec


@pytest.fixture
def mock_token_codec():
    return SlotTokenCodec(secret="test-secret-key-12345678901234567890")


@pytest.fixture
def sample_service():
    return CatalogService(
        id=20,
        establishment_id=5,
        name="Pista Central de Pádel",
        category_name="Deportes",
    )


@pytest.fixture
def sample_establishment():
    return Establishment(
        id=5,
        name="Club Pádel Santo Domingo",
        code="CPSD",
        rule_type=RuleType.ONLY_TODAY,
    )


@pytest.fixture
def sample_contract():
    return ServiceContractVersion(
        id=uuid4(),
        service_id=20,
        version_no=1,
        status=ContractStatus.PUBLISHED,
        pattern=AvailabilityPattern.SLOT_OBJECT,
        request_ttl_seconds=900,
        published_at=datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_price_rule():
    return ServicePriceRule(
        id=uuid4(),
        service_id=20,
        label="Tarifa Tarde",
        weekdays=[1, 2, 3, 4, 5, 6, 7],
        start_minute=480,  # 08:00
        end_minute=1320,  # 22:00
        valid_from=date(2026, 1, 1),
        amount=Decimal("1500.00"),
        currency="DOP",
        calculation_basis=CalculationBasis.PER_BOOKING,
        priority=10,
    )


@pytest.mark.asyncio
async def test_check_availability_on_demand_returns_guidance(
    sample_service, sample_establishment, mock_token_codec
):
    """Prueba que un servicio ON_DEMAND (veterinaria/formulario) devuelve mensaje explicativo sin slots."""
    on_demand_contract = ServiceContractVersion(
        id=uuid4(),
        service_id=20,
        pattern=AvailabilityPattern.ON_DEMAND_REQUEST,
        status=ContractStatus.PUBLISHED,
    )

    mock_catalog = MagicMock()
    mock_catalog.get_by_id = AsyncMock(return_value=sample_service)
    mock_contract = MagicMock()
    mock_contract.get_active_by_service_id = AsyncMock(return_value=on_demand_contract)
    mock_est = MagicMock()
    mock_cache = MagicMock()
    mock_hold = MagicMock()
    mock_bus = MagicMock()

    use_case = CheckAvailabilityUseCase(
        establishment_repo=mock_est,
        catalog_service_repo=mock_catalog,
        contract_repo=mock_contract,
        avail_cache=mock_cache,
        hold_manager=mock_hold,
        bus_client=mock_bus,
        token_codec=mock_token_codec,
    )

    res = await use_case.execute(
        CheckAvailabilityQueryDTO(
            service_id=20,
            date_from=date.today(),
            user_uuid=uuid4(),
        )
    )

    assert res.status == "completed"
    assert len(res.slots) == 0
    assert "funciona bajo demanda" in res.message
    assert "create_booking_request" in res.message


@pytest.mark.asyncio
async def test_check_availability_anticipation_rule_violated_raises(
    sample_service, sample_establishment, sample_contract, mock_token_codec
):
    """Prueba que si el club solo permite reservas para hoy y se consulta mañana, lanza excepción de regla."""
    sample_establishment.rule_type = RuleType.ONLY_TODAY

    mock_catalog = MagicMock()
    mock_catalog.get_by_id = AsyncMock(return_value=sample_service)
    mock_contract = MagicMock()
    mock_contract.get_active_by_service_id = AsyncMock(return_value=sample_contract)
    mock_est = MagicMock()
    mock_est.get_by_id = AsyncMock(return_value=sample_establishment)
    mock_cache = MagicMock()
    mock_hold = MagicMock()
    mock_bus = MagicMock()

    use_case = CheckAvailabilityUseCase(
        establishment_repo=mock_est,
        catalog_service_repo=mock_catalog,
        contract_repo=mock_contract,
        avail_cache=mock_cache,
        hold_manager=mock_hold,
        bus_client=mock_bus,
        token_codec=mock_token_codec,
    )

    # Consultar para mañana cuando la regla es ONLY_TODAY
    tomorrow = date.today() + timedelta(days=1)
    with pytest.raises(BookingRuleViolationException) as exc_info:
        await use_case.execute(
            CheckAvailabilityQueryDTO(
                service_id=20,
                date_from=tomorrow,
                user_uuid=uuid4(),
            )
        )
    assert "only_today" in str(exc_info.value)


@pytest.mark.asyncio
async def test_check_availability_fast_path_cache_hit_with_holds_and_estimated_queuer(
    sample_service, sample_establishment, sample_contract, sample_price_rule, mock_token_codec
):
    """
    Prueba Fast-Path:
    1. Recupera slots de la caché.
    2. Excluye el slot que tiene un hold activo en Redis.
    3. Conserva el slot estimado del Queuer y el slot oficial.
    4. Acuña tokens válidos y cotiza el precio.
    """
    sample_establishment.rule_type = RuleType.HOURS_RANGE
    user_uuid = uuid4()
    today = date.today()
    slot_dt_1 = datetime(today.year, today.month, today.day, 10, 0, tzinfo=timezone.utc)
    slot_dt_2 = datetime(today.year, today.month, today.day, 11, 30, tzinfo=timezone.utc)
    slot_dt_3 = datetime(today.year, today.month, today.day, 14, 0, tzinfo=timezone.utc)

    raw_cached_slots = [
        {
            "offer_ref": "off_court_1_10am",
            "slot_start": slot_dt_1.isoformat(),
            "slot_end": (slot_dt_1 + timedelta(hours=1, minutes=30)).isoformat(),
            "resource_ref": "court_1",
            "resource_name": "Pista 1",
            "is_estimated": False,
        },
        {
            "offer_ref": "off_court_1_1130am",  # Este slot estará tomado con Hold
            "slot_start": slot_dt_2.isoformat(),
            "slot_end": (slot_dt_2 + timedelta(hours=1, minutes=30)).isoformat(),
            "resource_ref": "court_1",
            "resource_name": "Pista 1",
            "is_estimated": False,
        },
        {
            "offer_ref": "off_queuer_virtual_2pm",  # Slot virtual estimado del Queuer
            "slot_start": slot_dt_3.isoformat(),
            "slot_end": (slot_dt_3 + timedelta(hours=1, minutes=30)).isoformat(),
            "resource_ref": "queuer_pool",
            "resource_name": "Horario Sugerido Queuer",
            "is_estimated": True,
            "notice": "Horario estimado Queuer.",
        },
    ]

    mock_catalog = MagicMock()
    mock_catalog.get_by_id = AsyncMock(return_value=sample_service)
    mock_contract = MagicMock()
    mock_contract.get_active_by_service_id = AsyncMock(return_value=sample_contract)
    mock_contract.list_price_rules_for_service = AsyncMock(return_value=[sample_price_rule])
    mock_est = MagicMock()
    mock_est.get_by_id = AsyncMock(return_value=sample_establishment)

    # Simular HIT en caché
    mock_cache = MagicMock()
    mock_cache.get = AsyncMock(return_value={"slots": raw_cached_slots})

    # Simular que el segundo slot tiene hold activo en Redis
    mock_hold = MagicMock()
    mock_hold.is_held = AsyncMock(side_effect=lambda ref: ref == "off_court_1_1130am")

    mock_bus = MagicMock()
    mock_bus.publish_availability_request = AsyncMock()

    use_case = CheckAvailabilityUseCase(
        establishment_repo=mock_est,
        catalog_service_repo=mock_catalog,
        contract_repo=mock_contract,
        avail_cache=mock_cache,
        hold_manager=mock_hold,
        bus_client=mock_bus,
        token_codec=mock_token_codec,
    )

    res = await use_case.execute(
        CheckAvailabilityQueryDTO(
            service_id=20,
            date_from=today,
            filters={"surface": "clay"},
            party_size=2,
            user_uuid=user_uuid,
        )
    )

    assert res.status == "completed"
    # El slot con hold fue descartado, quedan 2
    assert len(res.slots) == 2

    # Slot 1: oficial
    slot_1 = res.slots[0]
    assert slot_1.offer_ref == "off_court_1_10am"
    assert slot_1.is_estimated is False
    assert slot_1.slot_type == "official"
    assert slot_1.price_estimate is not None
    assert slot_1.price_estimate.amount == Decimal("1500.00")
    assert slot_1.price_estimate.currency == "DOP"
    assert slot_1.slot_token is not None

    # Verificar que el token decodifica correctamente para este usuario
    decoded_token = mock_token_codec.decode(slot_1.slot_token)
    assert decoded_token.user_uuid == user_uuid
    assert decoded_token.offer_ref == "off_court_1_10am"
    assert decoded_token.applied_filters == {"surface": "clay"}

    # Slot 2: estimado del Queuer
    slot_2 = res.slots[1]
    assert slot_2.offer_ref == "off_queuer_virtual_2pm"
    assert slot_2.is_estimated is True
    assert slot_2.slot_type == "estimated"
    assert slot_2.notice == "Horario estimado Queuer."

    # No debió publicar al bus por haber tenido HIT en caché
    mock_bus.publish_availability_request.assert_not_called()


@pytest.mark.asyncio
async def test_check_availability_cache_miss_with_immediate_response(
    sample_service, sample_establishment, sample_contract, sample_price_rule, mock_token_codec
):
    """Prueba Cache MISS con respuesta dentro de la espera superficial (2s)."""
    sample_establishment.rule_type = RuleType.HOURS_RANGE
    today = date.today()
    slot_dt = datetime(today.year, today.month, today.day, 16, 0, tzinfo=timezone.utc)

    mock_catalog = MagicMock()
    mock_catalog.get_by_id = AsyncMock(return_value=sample_service)
    mock_contract = MagicMock()
    mock_contract.get_active_by_service_id = AsyncMock(return_value=sample_contract)
    mock_contract.list_price_rules_for_service = AsyncMock(return_value=[sample_price_rule])
    mock_est = MagicMock()
    mock_est.get_by_id = AsyncMock(return_value=sample_establishment)

    # Cache miss
    mock_cache = MagicMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()

    mock_hold = MagicMock()
    mock_hold.is_held = AsyncMock(return_value=False)

    mock_bus = MagicMock()
    mock_bus.publish_availability_request = AsyncMock()
    mock_bus.wait_for_response = AsyncMock(
        return_value={
            "slots": [
                {
                    "offer_ref": "off_live_4pm",
                    "slot_start": slot_dt.isoformat(),
                    "slot_end": (slot_dt + timedelta(hours=1)).isoformat(),
                    "resource_ref": "cancha_2",
                    "is_estimated": False,
                }
            ]
        }
    )

    use_case = CheckAvailabilityUseCase(
        establishment_repo=mock_est,
        catalog_service_repo=mock_catalog,
        contract_repo=mock_contract,
        avail_cache=mock_cache,
        hold_manager=mock_hold,
        bus_client=mock_bus,
        token_codec=mock_token_codec,
    )

    res = await use_case.execute(
        CheckAvailabilityQueryDTO(
            service_id=20,
            date_from=today,
            user_uuid=uuid4(),
        )
    )

    assert res.status == "completed"
    assert len(res.slots) == 1
    assert res.slots[0].offer_ref == "off_live_4pm"
    mock_bus.publish_availability_request.assert_called_once()
    mock_cache.set.assert_called_once()


@pytest.mark.asyncio
async def test_check_availability_cache_miss_timeout_returns_processing(
    sample_service, sample_establishment, sample_contract, mock_token_codec
):
    """Prueba Cache MISS cuando la espera superficial vence (> 2s), retornando status processing."""
    sample_establishment.rule_type = RuleType.HOURS_RANGE
    today = date.today()

    mock_catalog = MagicMock()
    mock_catalog.get_by_id = AsyncMock(return_value=sample_service)
    mock_contract = MagicMock()
    mock_contract.get_active_by_service_id = AsyncMock(return_value=sample_contract)
    mock_est = MagicMock()
    mock_est.get_by_id = AsyncMock(return_value=sample_establishment)

    mock_cache = MagicMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_hold = MagicMock()

    mock_bus = MagicMock()
    mock_bus.publish_availability_request = AsyncMock()
    mock_bus.wait_for_response = AsyncMock(return_value=None)  # Timeout > 2s

    use_case = CheckAvailabilityUseCase(
        establishment_repo=mock_est,
        catalog_service_repo=mock_catalog,
        contract_repo=mock_contract,
        avail_cache=mock_cache,
        hold_manager=mock_hold,
        bus_client=mock_bus,
        token_codec=mock_token_codec,
    )

    res = await use_case.execute(
        CheckAvailabilityQueryDTO(
            service_id=20,
            date_from=today,
            user_uuid=uuid4(),
        )
    )

    assert res.status == "processing"
    assert res.operation_id is not None
    assert res.operation_id.startswith("op_avail_")
    assert len(res.slots) == 0


@pytest.mark.asyncio
async def test_get_operation_result_not_found(mock_token_codec):
    mock_bus = MagicMock()
    mock_bus.get_operation_result = AsyncMock(return_value=None)
    mock_contract = MagicMock()
    mock_hold = MagicMock()

    use_case = GetOperationResultUseCase(
        bus_client=mock_bus,
        contract_repo=mock_contract,
        hold_manager=mock_hold,
        token_codec=mock_token_codec,
    )

    res = await use_case.execute(
        GetOperationResultQueryDTO(operation_id="op_missing_123", user_uuid=uuid4())
    )

    assert res.status == "failed"
    assert "no existe o ha expirado" in res.error_message


@pytest.mark.asyncio
async def test_get_operation_result_still_processing(mock_token_codec):
    mock_bus = MagicMock()
    mock_bus.get_operation_result = AsyncMock(return_value={"status": "processing"})
    mock_contract = MagicMock()
    mock_hold = MagicMock()

    use_case = GetOperationResultUseCase(
        bus_client=mock_bus,
        contract_repo=mock_contract,
        hold_manager=mock_hold,
        token_codec=mock_token_codec,
    )

    res = await use_case.execute(
        GetOperationResultQueryDTO(operation_id="op_pending_123", user_uuid=uuid4())
    )

    assert res.status == "processing"
    assert res.retry_after_seconds == 2


@pytest.mark.asyncio
async def test_get_operation_result_completed_dimension_options(mock_token_codec):
    mock_bus = MagicMock()
    mock_bus.get_operation_result = AsyncMock(
        return_value={
            "status": "completed",
            "options": [
                {"value_key": "clay", "label": "Arcilla"},
                {"value_key": "grass", "label": "Hierba"},
            ],
        }
    )
    mock_contract = MagicMock()
    mock_hold = MagicMock()

    use_case = GetOperationResultUseCase(
        bus_client=mock_bus,
        contract_repo=mock_contract,
        hold_manager=mock_hold,
        token_codec=mock_token_codec,
    )

    res = await use_case.execute(
        GetOperationResultQueryDTO(operation_id="op_dim_done", user_uuid=uuid4())
    )

    assert res.status == "completed"
    assert res.result_type == "dimension_options"
    assert len(res.dimension_options) == 2
    assert res.dimension_options[0].value_key == "clay"


@pytest.mark.asyncio
async def test_get_operation_result_completed_availability_with_tokens(
    sample_contract, sample_price_rule, mock_token_codec
):
    user_uuid = uuid4()
    today = date.today()
    slot_dt = datetime(today.year, today.month, today.day, 18, 0, tzinfo=timezone.utc)

    mock_bus = MagicMock()
    mock_bus.get_operation_result = AsyncMock(
        return_value={
            "status": "completed",
            "service_id": 20,
            "filters": {"indoor": True},
            "party_size": 4,
            "slots": [
                {
                    "offer_ref": "off_deferred_slot_1",
                    "slot_start": slot_dt.isoformat(),
                    "slot_end": (slot_dt + timedelta(hours=1, minutes=30)).isoformat(),
                    "resource_ref": "court_indoor",
                    "resource_name": "Pista Techada",
                    "is_estimated": False,
                }
            ],
        }
    )

    mock_contract = MagicMock()
    mock_contract.get_active_by_service_id = AsyncMock(return_value=sample_contract)
    mock_contract.list_price_rules_for_service = AsyncMock(return_value=[sample_price_rule])

    mock_hold = MagicMock()
    mock_hold.is_held = AsyncMock(return_value=False)

    use_case = GetOperationResultUseCase(
        bus_client=mock_bus,
        contract_repo=mock_contract,
        hold_manager=mock_hold,
        token_codec=mock_token_codec,
    )

    res = await use_case.execute(
        GetOperationResultQueryDTO(operation_id="op_avail_done", user_uuid=user_uuid)
    )

    assert res.status == "completed"
    assert res.result_type == "availability"
    assert len(res.slots) == 1

    slot = res.slots[0]
    assert slot.offer_ref == "off_deferred_slot_1"
    assert slot.slot_token is not None

    # Validar que el token acuñado esté ligado al user_uuid del query
    decoded = mock_token_codec.decode(slot.slot_token)
    assert decoded.user_uuid == user_uuid
    assert decoded.offer_ref == "off_deferred_slot_1"
    assert decoded.applied_filters == {"indoor": True}
