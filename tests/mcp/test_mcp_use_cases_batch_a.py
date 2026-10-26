from __future__ import annotations

from datetime import datetime, time, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.mcp.application.dto.business_dtos import (
    BusinessDetailsQueryDTO,
    SearchBusinessesQueryDTO,
)
from src.mcp.application.dto.contract_dtos import (
    GetDimensionOptionsQueryDTO,
    GetServiceContractQueryDTO,
)
from src.mcp.application.use_cases.get_business_details import GetBusinessDetailsUseCase
from src.mcp.application.use_cases.get_dimension_options import GetDimensionOptionsUseCase
from src.mcp.application.use_cases.get_service_contract import GetServiceContractUseCase
from src.mcp.application.use_cases.search_businesses import SearchBusinessesUseCase
from src.mcp.domain.entities.catalog_entities import CatalogService, Establishment
from src.mcp.domain.entities.contract_entities import (
    ContractDimension,
    ServiceContractVersion,
)
from src.mcp.domain.enums.mcp_enums import (
    AvailabilityPattern,
    ContractStatus,
    DimensionApplyMode,
    DimensionValuesSource,
    RuleType,
)
from src.mcp.domain.exceptions.mcp_exceptions import (
    EntityNotFoundException,
    MissingDimensionDependencyException,
)
from src.mcp.domain.value_objects.establishment_vo import ContactInfo, LocationAddress


@pytest.mark.asyncio
async def test_search_businesses_use_case():
    mock_repo = MagicMock()
    mock_repo.search = AsyncMock(
        return_value=[
            Establishment(
                id=1,
                name="Club Pádel Pro",
                code="CPP",
                category_name="Deportes",
                location=LocationAddress(city="Santo Domingo", sector="Piantini", street="Av. Lincoln 100"),
                opening_hour=time(8, 0),
                closing_hour=time(22, 0),
                rule_type=RuleType.ONLY_TODAY,
            ),
            Establishment(
                id=2,
                name="Club Tenis Central",
                code="CTC",
                category_name="Deportes",
                location=LocationAddress(city="Santo Domingo", sector="Naco"),
                opening_hour=time(7, 0),
                closing_hour=time(21, 0),
                rule_type=RuleType.TODAY_AND_TOMORROW,
            ),
        ]
    )

    use_case = SearchBusinessesUseCase(establishment_repo=mock_repo)
    result = await use_case.execute(
        SearchBusinessesQueryDTO(query="pádel", category="Deportes", zone="Santo Domingo", limit=2, cursor=0)
    )

    assert len(result.items) == 2
    assert result.items[0].name == "Club Pádel Pro"
    assert result.items[0].city == "Santo Domingo"
    assert result.items[0].rule_type == "only_today"
    assert result.next_cursor == 2  # len(items) == limit -> hay siguiente página


@pytest.mark.asyncio
async def test_get_business_details_use_case_success():
    mock_est_repo = MagicMock()
    mock_est_repo.get_by_id = AsyncMock(
        return_value=Establishment(
            id=10,
            name="Clínica Veterinaria PetCare",
            code="PET",
            category_name="Veterinaria",
            location=LocationAddress(
                city="Santiago",
                sector="Los Jardines",
                street="Calle 5",
                postal_code="51000",
            ),
            contact=ContactInfo(phone="+18095551234", email="info@petcare.do", website="https://petcare.do"),
            opening_hour=time(8, 0),
            closing_hour=time(18, 0),
            rule_type=RuleType.ONLY_TODAY,
        )
    )

    mock_catalog_repo = MagicMock()
    mock_catalog_repo.list_by_establishment = AsyncMock(
        return_value=[
            CatalogService(
                id=101,
                establishment_id=10,
                name="Consulta General Canina",
                category_name="Salud",
            )
        ]
    )

    mock_contract_repo = MagicMock()
    mock_contract_repo.get_active_by_service_id = AsyncMock(
        return_value=ServiceContractVersion(
            id=uuid4(),
            service_id=101,
            pattern=AvailabilityPattern.ON_DEMAND_REQUEST,
            status=ContractStatus.PUBLISHED,
        )
    )

    use_case = GetBusinessDetailsUseCase(
        establishment_repo=mock_est_repo,
        catalog_service_repo=mock_catalog_repo,
        contract_repo=mock_contract_repo,
    )

    details = await use_case.execute(BusinessDetailsQueryDTO(business_id=10))

    assert details.id == 10
    assert details.name == "Clínica Veterinaria PetCare"
    assert details.phone == "+18095551234"
    assert "solo permite reservas para el día de hoy" in details.advance_booking_rule
    assert len(details.services) == 1
    assert details.services[0].name == "Consulta General Canina"
    assert details.services[0].pattern == "on_demand_request"
    assert details.services[0].has_active_contract is True


@pytest.mark.asyncio
async def test_get_business_details_not_found_raises():
    mock_est_repo = MagicMock()
    mock_est_repo.get_by_id = AsyncMock(return_value=None)
    mock_catalog_repo = MagicMock()

    use_case = GetBusinessDetailsUseCase(
        establishment_repo=mock_est_repo,
        catalog_service_repo=mock_catalog_repo,
    )

    with pytest.raises(EntityNotFoundException):
        await use_case.execute(BusinessDetailsQueryDTO(business_id=999))


@pytest.mark.asyncio
async def test_get_service_contract_use_case_success():
    mock_catalog_repo = MagicMock()
    mock_catalog_repo.get_by_id = AsyncMock(
        return_value=CatalogService(
            id=50,
            establishment_id=1,
            name="Cancha de Pádel Techada",
            category_name="Deportes",
        )
    )

    contract = ServiceContractVersion(
        id=uuid4(),
        service_id=50,
        version_no=2,
        status=ContractStatus.PUBLISHED,
        pattern=AvailabilityPattern.SLOT_OBJECT,
        booking_fields_schema={"type": "object", "required": ["player_names"]},
        dimensions=[
            ContractDimension(
                id=uuid4(),
                key="surface",
                label="Superficie",
                values_source=DimensionValuesSource.INLINE,
                apply_mode=DimensionApplyMode.POST_FILTER,
                position=1,
                inline_values=[{"key": "clay", "label": "Tierra Batida"}, {"key": "glass", "label": "Cristal"}],
            ),
            ContractDimension(
                id=uuid4(),
                key="court_id",
                label="Cancha Específica",
                values_source=DimensionValuesSource.SEPARATE_QUERY,
                apply_mode=DimensionApplyMode.UPSTREAM_PARAM,
                resolver_ref="resolver_court_padel",
                position=2,
            ),
        ],
        payment_policy={"accepted_methods": ["credit_card"]},
        cancellation_policy={"allowed_until_hours_before": 24},
        published_at=datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc),
    )

    mock_contract_repo = MagicMock()
    mock_contract_repo.get_active_by_service_id = AsyncMock(return_value=contract)

    use_case = GetServiceContractUseCase(
        catalog_service_repo=mock_catalog_repo,
        contract_repo=mock_contract_repo,
    )

    res = await use_case.execute(GetServiceContractQueryDTO(service_id=50))

    assert res.service_id == 50
    assert res.pattern == "slot_object"
    assert res.contract_version == "2026-10-26.2"
    assert len(res.availability_dimensions) == 2
    # La primera dimensión debe ser surface y tener inline values
    dim_surface = res.availability_dimensions[0]
    assert dim_surface.key == "surface"
    assert dim_surface.values is not None
    assert len(dim_surface.values) == 2
    assert dim_surface.values[0].value_key == "clay"
    # La segunda dimensión court_id no tiene inline values y su resolver_ref está oculto a Claude
    dim_court = res.availability_dimensions[1]
    assert dim_court.key == "court_id"
    assert dim_court.values_source == "separate_query"
    assert not hasattr(dim_court, "resolver_ref")


@pytest.mark.asyncio
async def test_get_service_contract_missing_contract_raises():
    mock_catalog_repo = MagicMock()
    mock_catalog_repo.get_by_id = AsyncMock(
        return_value=CatalogService(id=50, establishment_id=1, name="Servicio Sin Contrato")
    )
    mock_contract_repo = MagicMock()
    mock_contract_repo.get_active_by_service_id = AsyncMock(return_value=None)

    use_case = GetServiceContractUseCase(
        catalog_service_repo=mock_catalog_repo,
        contract_repo=mock_contract_repo,
    )

    with pytest.raises(EntityNotFoundException):
        await use_case.execute(GetServiceContractQueryDTO(service_id=50))


@pytest.mark.asyncio
async def test_get_dimension_options_fast_path_cache_hit():
    contract = ServiceContractVersion(
        id=uuid4(),
        service_id=50,
        status=ContractStatus.PUBLISHED,
        dimensions=[
            ContractDimension(
                id=uuid4(),
                key="instructor",
                label="Instructor",
                values_source=DimensionValuesSource.SEPARATE_QUERY,
                resolver_ref="res_instructor",
                depends_on=["date"],
            )
        ],
    )
    mock_contract_repo = MagicMock()
    mock_contract_repo.get_active_by_service_id = AsyncMock(return_value=contract)

    # Simular HIT en caché
    mock_dim_cache = MagicMock()
    mock_dim_cache.get = AsyncMock(
        return_value=[
            {"value_key": "inst_1", "label": "Carlos Gómez", "description": "Nivel avanzado"},
            {"value_key": "inst_2", "label": "María Pérez", "description": "Iniciación"},
        ]
    )

    mock_bus_client = MagicMock()
    mock_bus_client.publish_dimension_request = AsyncMock()

    use_case = GetDimensionOptionsUseCase(
        contract_repo=mock_contract_repo,
        dim_cache=mock_dim_cache,
        bus_client=mock_bus_client,
    )

    res = await use_case.execute(
        GetDimensionOptionsQueryDTO(
            service_id=50,
            dimension_key="instructor",
            context={"date": "2026-10-30"},
        )
    )

    assert res.status == "completed"
    assert len(res.options) == 2
    assert res.options[0].value_key == "inst_1"
    assert res.options[0].label == "Carlos Gómez"
    assert res.context_hash is not None
    # No se debió publicar en el bus gracias al Fast-Path
    mock_bus_client.publish_dimension_request.assert_not_called()


@pytest.mark.asyncio
async def test_get_dimension_options_missing_dependency_raises():
    contract = ServiceContractVersion(
        id=uuid4(),
        service_id=50,
        status=ContractStatus.PUBLISHED,
        dimensions=[
            ContractDimension(
                id=uuid4(),
                key="mechanic",
                label="Mecánico",
                values_source=DimensionValuesSource.SEPARATE_QUERY,
                resolver_ref="res_mechanic",
                depends_on=["branch_id", "date"],
            )
        ],
    )
    mock_contract_repo = MagicMock()
    mock_contract_repo.get_active_by_service_id = AsyncMock(return_value=contract)
    mock_dim_cache = MagicMock()
    mock_bus_client = MagicMock()

    use_case = GetDimensionOptionsUseCase(
        contract_repo=mock_contract_repo,
        dim_cache=mock_dim_cache,
        bus_client=mock_bus_client,
    )

    # Solo enviamos branch_id, falta 'date'
    with pytest.raises(MissingDimensionDependencyException) as exc_info:
        await use_case.execute(
            GetDimensionOptionsQueryDTO(
                service_id=50,
                dimension_key="mechanic",
                context={"branch_id": "central"},
            )
        )
    assert "date" in exc_info.value.missing_dependencies


@pytest.mark.asyncio
async def test_get_dimension_options_cache_miss_with_immediate_response():
    contract = ServiceContractVersion(
        id=uuid4(),
        service_id=50,
        status=ContractStatus.PUBLISHED,
        dimensions=[
            ContractDimension(
                id=uuid4(),
                key="instructor",
                label="Instructor",
                values_source=DimensionValuesSource.SEPARATE_QUERY,
                resolver_ref="res_instructor",
                depends_on=[],
            )
        ],
    )
    mock_contract_repo = MagicMock()
    mock_contract_repo.get_active_by_service_id = AsyncMock(return_value=contract)

    # Cache miss
    mock_dim_cache = MagicMock()
    mock_dim_cache.get = AsyncMock(return_value=None)
    mock_dim_cache.set = AsyncMock()

    mock_bus_client = MagicMock()
    mock_bus_client.publish_dimension_request = AsyncMock()
    # Responde a tiempo en la espera superficial
    mock_bus_client.wait_for_response = AsyncMock(
        return_value={
            "options": [
                {"value_key": "inst_10", "label": "Pedro Santana"},
            ]
        }
    )

    use_case = GetDimensionOptionsUseCase(
        contract_repo=mock_contract_repo,
        dim_cache=mock_dim_cache,
        bus_client=mock_bus_client,
    )

    res = await use_case.execute(
        GetDimensionOptionsQueryDTO(
            service_id=50,
            dimension_key="instructor",
            context={},
        )
    )

    assert res.status == "completed"
    assert len(res.options) == 1
    assert res.options[0].value_key == "inst_10"
    mock_bus_client.publish_dimension_request.assert_called_once()
    mock_dim_cache.set.assert_called_once()


@pytest.mark.asyncio
async def test_get_dimension_options_cache_miss_timeout_processing():
    contract = ServiceContractVersion(
        id=uuid4(),
        service_id=50,
        status=ContractStatus.PUBLISHED,
        dimensions=[
            ContractDimension(
                id=uuid4(),
                key="instructor",
                label="Instructor",
                values_source=DimensionValuesSource.SEPARATE_QUERY,
                resolver_ref="res_instructor",
                depends_on=[],
            )
        ],
    )
    mock_contract_repo = MagicMock()
    mock_contract_repo.get_active_by_service_id = AsyncMock(return_value=contract)

    # Cache miss
    mock_dim_cache = MagicMock()
    mock_dim_cache.get = AsyncMock(return_value=None)
    mock_dim_cache.set = AsyncMock()

    mock_bus_client = MagicMock()
    mock_bus_client.publish_dimension_request = AsyncMock()
    # Agota los 2 segundos de espera superficial (retorna None)
    mock_bus_client.wait_for_response = AsyncMock(return_value=None)

    use_case = GetDimensionOptionsUseCase(
        contract_repo=mock_contract_repo,
        dim_cache=mock_dim_cache,
        bus_client=mock_bus_client,
    )

    res = await use_case.execute(
        GetDimensionOptionsQueryDTO(
            service_id=50,
            dimension_key="instructor",
            context={},
        )
    )

    assert res.status == "processing"
    assert res.operation_id is not None
    assert res.operation_id.startswith("op_dim_")
    assert len(res.options) == 0
    mock_dim_cache.set.assert_not_called()
