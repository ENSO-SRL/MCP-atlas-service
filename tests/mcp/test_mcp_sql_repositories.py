from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.mcp.domain.entities.booking_request import BookingRequest
from src.mcp.domain.enums.mcp_enums import (
    BookingStatus,
    CalculationBasis,
    ContractStatus,
    DimensionApplyMode,
    DimensionValuesSource,
    RuleType,
)
from src.mcp.domain.value_objects.booking_vo import PriceEstimate
from src.mcp.infrastructure.persistence.models.booking_models import (
    BookingRequestModel,
    BookingStatusHistoryModel,
    OutboxEventModel,
)
from src.mcp.infrastructure.persistence.models.catalog_models import (
    EstablishmentCategoryModel,
    EstablishmentModel,
    ServicioModel,
)
from src.mcp.infrastructure.persistence.models.contract_models import (
    ContractDimensionDependencyModel,
    ContractDimensionModel,
    ContractDimensionValueModel,
    ServiceContractVersionModel,
    ServicePriceRuleModel,
    ServicePricingPolicyModel,
)
from src.mcp.infrastructure.persistence.repositories.sql_booking_repository import (
    SqlBookingRepository,
)
from src.mcp.infrastructure.persistence.repositories.sql_catalog_service_repository import (
    SqlCatalogServiceRepository,
)
from src.mcp.infrastructure.persistence.repositories.sql_contract_repository import (
    SqlContractRepository,
)
from src.mcp.infrastructure.persistence.repositories.sql_establishment_repository import (
    SqlEstablishmentRepository,
)
from src.mcp.infrastructure.persistence.repositories.sql_outbox_repository import (
    SqlOutboxRepository,
)


@pytest.mark.anyio
async def test_sql_establishment_repository_mapping_and_get():
    mock_session = AsyncMock()

    cat_model = EstablishmentCategoryModel(id=1, name="Deportes y Clubes")
    est_model = EstablishmentModel(
        id=10,
        name="Club Pádel Pro",
        code="PADEL-PRO",
        is_active=True,
        has_credentials=True,
        rule_type="only_today",
        opening_hour=time(8, 0),
        closing_hour=time(23, 0),
        city="Santo Domingo",
        sector="Piantini",
        street="Av. Abraham Lincoln",
        phone="+18095550100",
        email="info@padelpro.com",
        category=cat_model,
        configuration={"lights_included": True},
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = est_model
    mock_session.execute.return_value = mock_result

    repo = SqlEstablishmentRepository(session=mock_session)
    establishment = await repo.get_by_id(10)

    assert establishment is not None
    assert establishment.id == 10
    assert establishment.name == "Club Pádel Pro"
    assert establishment.code == "PADEL-PRO"
    assert establishment.rule_type == RuleType.ONLY_TODAY
    assert establishment.category_name == "Deportes y Clubes"
    assert establishment.location.city == "Santo Domingo"
    assert establishment.location.sector == "Piantini"
    assert establishment.contact.phone == "+18095550100"
    assert establishment.configuration == {"lights_included": True}


@pytest.mark.anyio
async def test_sql_catalog_service_repository_mapping_and_list():
    mock_session = AsyncMock()

    svc_model = ServicioModel(
        id=5,
        establishment_id=10,
        nombre="Cancha de Pádel Techada 1",
        activo=True,
        has_credentials=True,
        combo_code="PADEL_INDOOR",
        categoria=None,
        configuration={"court_type": "indoor"},
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [svc_model]
    mock_session.execute.return_value = mock_result

    repo = SqlCatalogServiceRepository(session=mock_session)
    services = await repo.list_by_establishment(10)

    assert len(services) == 1
    assert services[0].id == 5
    assert services[0].establishment_id == 10
    assert services[0].name == "Cancha de Pádel Techada 1"
    assert services[0].category_name == "GENERAL"
    assert services[0].configuration == {"court_type": "indoor"}


@pytest.mark.anyio
async def test_sql_contract_repository_mapping_with_dependencies():
    mock_session = AsyncMock()

    version_id = uuid4()
    dim_surface_id = uuid4()
    dim_court_id = uuid4()

    val_clay = ContractDimensionValueModel(
        id=uuid4(),
        contract_version_id=version_id,
        dimension_id=dim_surface_id,
        value_key="clay",
        label="Tierra Batida",
        position=1,
    )

    dim_surface = ContractDimensionModel(
        id=dim_surface_id,
        contract_version_id=version_id,
        key="surface",
        position=1,
        label="Superficie",
        values_source="inline",
        apply_mode="post_filter",
        required=True,
        inline_values=[val_clay],
    )

    dim_court = ContractDimensionModel(
        id=dim_court_id,
        contract_version_id=version_id,
        key="court",
        position=2,
        label="Pista específica",
        values_source="slots",
        apply_mode="post_filter",
        required=False,
        inline_values=[],
    )

    contract_model = ServiceContractVersionModel(
        id=version_id,
        service_id=10,
        version_no=1,
        status="published",
        booking_fields_schema={"type": "object"},
        dimensions=[dim_surface, dim_court],
        request_ttl_seconds=900,
        content_hash="sha256-abc",
        published_at=datetime.now(timezone.utc),
    )

    # Simular dependencias: 'court' depende de 'surface'
    dep_model = ContractDimensionDependencyModel(
        contract_version_id=version_id,
        dimension_id=dim_court_id,
        depends_on_dimension_id=dim_surface_id,
    )

    # Respuestas de mock
    contract_res = MagicMock()
    contract_res.scalar_one_or_none.return_value = contract_model

    dep_res = MagicMock()
    dep_res.scalars.return_value.all.return_value = [dep_model]

    mock_session.execute.side_effect = [contract_res, dep_res]

    repo = SqlContractRepository(session=mock_session)
    contract = await repo.get_active_by_service_id(10)

    assert contract is not None
    assert contract.id == version_id
    assert contract.service_id == 10
    assert contract.status == ContractStatus.PUBLISHED
    assert len(contract.dimensions) == 2

    surface_dim = next(d for d in contract.dimensions if d.key == "surface")
    assert surface_dim.values_source == DimensionValuesSource.INLINE
    assert len(surface_dim.inline_values) == 1
    assert surface_dim.inline_values[0]["value_key"] == "clay"

    court_dim = next(d for d in contract.dimensions if d.key == "court")
    assert court_dim.depends_on == ["surface"]


@pytest.mark.anyio
async def test_sql_contract_repository_list_price_rules():
    mock_session = AsyncMock()

    pol_res = MagicMock()
    pol_res.scalar_one_or_none.return_value = "USD"

    rule_model = ServicePriceRuleModel(
        id=uuid4(),
        service_id=10,
        label="Tarifa estándar noche",
        weekdays=[1, 2, 3, 4, 5],
        start_minute=1080,
        end_minute=1380,
        valid_from=date(2026, 1, 1),
        valid_to=None,
        amount=Decimal("35.00"),
        calculation_basis="per_booking",
        is_starting_price=True,
        priority=10,
    )

    rule_res = MagicMock()
    rule_res.scalars.return_value.all.return_value = [rule_model]

    mock_session.execute.side_effect = [pol_res, rule_res]

    repo = SqlContractRepository(session=mock_session)
    rules = await repo.list_price_rules_for_service(10)

    assert len(rules) == 1
    assert rules[0].label == "Tarifa estándar noche"
    assert rules[0].currency == "USD"
    assert rules[0].amount == Decimal("35.00")
    assert rules[0].calculation_basis == CalculationBasis.PER_BOOKING


@pytest.mark.anyio
async def test_sql_booking_repository_save_new_and_update():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    # Simula que la primera búsqueda get() retorna None (nueva reserva)
    mock_session.get.return_value = None

    repo = SqlBookingRepository(session=mock_session)
    booking = BookingRequest.create(
        user_uuid=uuid4(),
        service_id=10,
        contract_version_id=uuid4(),
        idempotency_key="idemp_sql_test",
        request_fingerprint="fp_sql_test",
        token_id="tok_sql_test",
        offer_ref="off_sql_test",
        slot_start=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
        price_estimate=PriceEstimate(amount=Decimal("25.00"), currency="DOP"),
    )

    # 1. Guardar nueva reserva
    saved = await repo.save(booking)
    assert saved.status == BookingStatus.REQUESTED
    # Verifica que se hayan agregado a la sesión tanto BookingRequestModel como BookingStatusHistoryModel
    assert mock_session.add.call_count == 2
    assert mock_session.flush.call_count == 1

    # 2. Simular actualización a ACCEPTED (el estado en trámite)
    existing_model = BookingRequestModel(
        id=booking.id,
        user_uuid=booking.user_uuid,
        service_id=booking.service_id,
        contract_version_id=booking.contract_version_id,
        status="requested",
        idempotency_key="idemp_sql_test",
        request_fingerprint="fp_sql_test",
        token_id="tok_sql_test",
        offer_ref="off_sql_test",
        slot_start=booking.slot_start,
        expires_at=booking.expires_at,
    )
    mock_session.get.return_value = existing_model
    mock_session.add.reset_mock()
    mock_session.flush.reset_mock()

    booking.accept(external_ref="TRAMITE-999")
    await repo.save(booking)

    assert existing_model.status == "accepted"
    assert existing_model.external_ref == "TRAMITE-999"
    # Debe haber agregado un nuevo registro en status_history
    assert mock_session.add.call_count == 1
    added_history = mock_session.add.call_args[0][0]
    assert isinstance(added_history, BookingStatusHistoryModel)
    assert added_history.from_status == "requested"
    assert added_history.to_status == "accepted"


@pytest.mark.anyio
async def test_sql_outbox_repository_record_event():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    repo = SqlOutboxRepository(session=mock_session)

    booking_id = uuid4()
    payload = {"booking_id": str(booking_id), "status": "requested"}

    await repo.record_event(
        event_type="BookingRequested",
        aggregate_id=booking_id,
        payload=payload,
        correlation_id="corr-123",
    )

    assert mock_session.add.call_count == 1
    added_event = mock_session.add.call_args[0][0]
    assert isinstance(added_event, OutboxEventModel)
    assert added_event.event_type == "BookingRequested"
    assert added_event.aggregate_id == booking_id
    assert added_event.payload == payload
    assert added_event.published_at is None
    assert mock_session.flush.call_count == 1
