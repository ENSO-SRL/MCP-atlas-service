from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.mcp.application.dto.reservation_object_dtos import (
    GetReservationObjectSchemasQueryDTO,
    GetUserReservationObjectsQueryDTO,
)
from src.mcp.application.use_cases.get_reservation_object_schemas import (
    GetReservationObjectSchemasUseCase,
)
from src.mcp.application.use_cases.get_user_reservation_objects import (
    GetUserReservationObjectsUseCase,
)
from src.mcp.domain.entities.reservation_object_entities import (
    ReservationObject,
    ReservationObjectSchema,
    ReservationObjectSchemaField,
)
from src.mcp.domain.exceptions.mcp_exceptions import (
    ContractValidationException,
    EntityNotFoundException,
)
from src.mcp.infrastructure.persistence.repositories.sql_reservation_object_repository import (
    _normalize_phone_variants,
)


@pytest.fixture
def sample_user_uuid():
    return uuid4()


@pytest.fixture
def sample_schema():
    return ReservationObjectSchema(
        id=1,
        schema_header="vvautos_taller:vehiculo",
        service_id=99,
        establishment_id=92,
        section_name="Tus vehículos",
        schema_fields=[
            ReservationObjectSchemaField(
                field_name="vehicle_model",
                data_type="string",
                is_required=True,
                high_variance_flag=False,
                description="Modelo del vehículo",
            ),
            ReservationObjectSchemaField(
                field_name="vehicle_plate",
                data_type="string",
                is_required=True,
                high_variance_flag=False,
                description="Placa del vehículo",
            ),
            ReservationObjectSchemaField(
                field_name="vehicle_chassis",
                data_type="string",
                is_required=True,
                high_variance_flag=False,
                description="Número de chasis",
            ),
            ReservationObjectSchemaField(
                field_name="vehicle_mileage",
                data_type="string",
                is_required=True,
                high_variance_flag=True,
                description="Kilometraje actual",
            ),
        ],
    )


@pytest.fixture
def sample_object():
    return ReservationObject(
        id=19,
        schema_id=1,
        user_phone="+18094251911",
        object_alias="Mi Toyota Tacoma 2024",
        object_payload={
            "vehicle_model": "Toyota Tacoma 2024",
            "vehicle_plate": "L123456",
            "vehicle_chassis": "JTEXXXXXX12345678",
            "vehicle_mileage": "15000",
        },
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_get_reservation_object_schemas_happy_path(sample_schema):
    """Verifica que se recuperen los esquemas de un servicio con sus campos y banderas de alta variación."""
    mock_repo = MagicMock()
    mock_repo.get_schemas_by_service_id = AsyncMock(return_value=[sample_schema])

    use_case = GetReservationObjectSchemasUseCase(res_obj_repo=mock_repo)

    query = GetReservationObjectSchemasQueryDTO(service_id=99)
    res = await use_case.execute(query)

    assert res.service_id == 99
    assert len(res.schemas) == 1
    schema_dto = res.schemas[0]
    assert schema_dto.schema_header == "vvautos_taller:vehiculo"
    assert schema_dto.section_name == "Tus vehículos"
    assert len(schema_dto.schema_fields) == 4

    mileage_field = next(f for f in schema_dto.schema_fields if f.field_name == "vehicle_mileage")
    assert mileage_field.high_variance_flag is True
    assert mileage_field.is_required is True


@pytest.mark.asyncio
async def test_get_reservation_object_schemas_empty():
    """Verifica respuesta limpia cuando un servicio no tiene schemas de objetos."""
    mock_repo = MagicMock()
    mock_repo.get_schemas_by_service_id = AsyncMock(return_value=[])

    use_case = GetReservationObjectSchemasUseCase(res_obj_repo=mock_repo)

    query = GetReservationObjectSchemasQueryDTO(service_id=18)
    res = await use_case.execute(query)

    assert res.service_id == 18
    assert len(res.schemas) == 0


@pytest.mark.asyncio
async def test_get_user_reservation_objects_happy_path(sample_schema, sample_object, sample_user_uuid):
    """Verifica que se recuperen los objetos guardados del usuario filtrando por schema_header y teléfono."""
    mock_repo = MagicMock()
    mock_repo.get_schema_by_header = AsyncMock(return_value=sample_schema)
    mock_repo.get_objects_by_schema_and_phone = AsyncMock(return_value=[sample_object])

    use_case = GetUserReservationObjectsUseCase(res_obj_repo=mock_repo)

    query = GetUserReservationObjectsQueryDTO(
        schema_header="vvautos_taller:vehiculo",
        user_uuid=sample_user_uuid,
        user_phone="+18094251911",
    )
    res = await use_case.execute(query)

    assert res.schema_header == "vvautos_taller:vehiculo"
    assert res.section_name == "Tus vehículos"
    assert res.user_phone == "+18094251911"
    assert len(res.objects) == 1

    obj_dto = res.objects[0]
    assert obj_dto.id == 19
    assert obj_dto.object_alias == "Mi Toyota Tacoma 2024"
    assert obj_dto.payload["vehicle_plate"] == "L123456"
    assert obj_dto.payload["vehicle_mileage"] == "15000"


@pytest.mark.asyncio
async def test_get_user_reservation_objects_resolves_phone_from_uuid_fallback(
    sample_schema, sample_object, sample_user_uuid
):
    """Verifica que si no viene user_phone en la query, se resuelva mediante el user_uuid en BD."""
    mock_repo = MagicMock()
    mock_repo.get_schema_by_header = AsyncMock(return_value=sample_schema)
    mock_repo.get_user_phone_by_uuid = AsyncMock(return_value="+18094251911")
    mock_repo.get_objects_by_schema_and_phone = AsyncMock(return_value=[sample_object])

    use_case = GetUserReservationObjectsUseCase(res_obj_repo=mock_repo)

    query = GetUserReservationObjectsQueryDTO(
        schema_header="vvautos_taller:vehiculo",
        user_uuid=sample_user_uuid,
        user_phone=None,
    )
    res = await use_case.execute(query)

    mock_repo.get_user_phone_by_uuid.assert_awaited_once_with(sample_user_uuid)
    assert res.user_phone == "+18094251911"
    assert len(res.objects) == 1


@pytest.mark.asyncio
async def test_get_user_reservation_objects_schema_not_found_raises(sample_user_uuid):
    """Verifica que si el schema_header no existe, lance EntityNotFoundException."""
    mock_repo = MagicMock()
    mock_repo.get_schema_by_header = AsyncMock(return_value=None)

    use_case = GetUserReservationObjectsUseCase(res_obj_repo=mock_repo)

    query = GetUserReservationObjectsQueryDTO(
        schema_header="esquema:inexistente",
        user_uuid=sample_user_uuid,
        user_phone="+18095551234",
    )

    with pytest.raises(EntityNotFoundException, match="No se encontró el esquema"):
        await use_case.execute(query)


@pytest.mark.asyncio
async def test_get_user_reservation_objects_empty_header_raises(sample_user_uuid):
    """Verifica que un schema_header vacío lance ContractValidationException."""
    use_case = GetUserReservationObjectsUseCase(res_obj_repo=MagicMock())

    query = GetUserReservationObjectsQueryDTO(
        schema_header="   ",
        user_uuid=sample_user_uuid,
        user_phone="+18095551234",
    )

    with pytest.raises(ContractValidationException, match="Debe proporcionar 'schema_header'"):
        await use_case.execute(query)


@pytest.mark.asyncio
async def test_get_user_reservation_objects_no_phone_returns_empty_list(
    sample_schema, sample_user_uuid
):
    """Verifica que si el usuario no tiene teléfono registrado, devuelva lista vacía sin error."""
    mock_repo = MagicMock()
    mock_repo.get_schema_by_header = AsyncMock(return_value=sample_schema)
    mock_repo.get_user_phone_by_uuid = AsyncMock(return_value=None)

    use_case = GetUserReservationObjectsUseCase(res_obj_repo=mock_repo)

    query = GetUserReservationObjectsQueryDTO(
        schema_header="vvautos_taller:vehiculo",
        user_uuid=sample_user_uuid,
        user_phone=None,
    )
    res = await use_case.execute(query)

    assert res.objects == []
    assert res.user_phone is None


def test_normalize_phone_variants():
    """Verifica la generación de variantes de teléfonos para búsquedas flexibles en BD."""
    variants = _normalize_phone_variants("+18094251911")
    assert "+18094251911" in variants
    assert "18094251911" in variants
    assert "8094251911" in variants

