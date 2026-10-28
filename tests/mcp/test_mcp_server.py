from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import jwt
import pytest

from src.mcp.application.dto.availability_dtos import (
    AvailabilityResponseDTO,
    AvailableSlotDTO,
    OperationResultResponseDTO,
    SlotPriceEstimateDTO,
)
from src.mcp.application.dto.booking_dtos import (
    BookingCreationResultDTO,
    BookingDetailsDTO,
    BookingSummaryDTO,
    CancellationResultDTO,
    ListMyBookingsResponseDTO,
)
from src.mcp.application.dto.business_dtos import (
    BusinessDetailsDTO,
    BusinessServiceSummaryDTO,
    BusinessSummaryDTO,
    SearchBusinessesResponseDTO,
)
from src.mcp.application.dto.contract_dtos import (
    ContractDimensionProjectionDTO,
    DimensionOptionDTO,
    DimensionOptionsResponseDTO,
    ServiceContractDTO,
)
from src.mcp.domain.entities.catalog_entities import LocationAddress
from src.mcp.domain.exceptions.mcp_exceptions import (
    BookingRuleViolationException,
    EntityNotFoundException,
)
from src.mcp.presentation.auth_context import current_user_context
from src.mcp.presentation.dependencies import MCPUseCases, set_test_use_cases
from src.mcp.presentation.server import create_mcp_server
from src.shared.config.settings import get_settings


@pytest.fixture
def sample_user_uuid():
    return uuid4()


@pytest.fixture
def mock_use_cases():
    return MCPUseCases(
        search_businesses=MagicMock(),
        get_business_details=MagicMock(),
        get_service_contract=MagicMock(),
        get_dimension_options=MagicMock(),
        check_availability=MagicMock(),
        get_operation_result=MagicMock(),
        create_booking_request=MagicMock(),
        get_booking_status=MagicMock(),
        list_my_bookings=MagicMock(),
        cancel_booking=MagicMock(),
    )


@pytest.fixture(autouse=True)
def setup_test_container(mock_use_cases, sample_user_uuid):
    """Configura los mocks de casos de uso y fija el usuario de contexto para las pruebas."""
    set_test_use_cases(mock_use_cases)
    token = current_user_context.set(sample_user_uuid)
    yield
    current_user_context.reset(token)
    set_test_use_cases(None)


@pytest.fixture
def server():
    return create_mcp_server("test-atlas-server")


# =========================================================================
# 1. Metadatos y Registro de las 10 Tools
# =========================================================================

@pytest.mark.asyncio
async def test_server_registers_all_10_tools(server):
    """Verifica que el servidor MCP expone exactamente las 10 tools acordadas."""
    tools = await server.list_tools()
    tool_names = {t.name for t in tools}

    expected_tools = {
        "search_businesses",
        "get_business_details",
        "get_service_contract",
        "get_dimension_options",
        "check_availability",
        "get_operation_result",
        "create_booking_request",
        "get_booking_status",
        "list_my_bookings",
        "cancel_booking",
    }

    assert tool_names == expected_tools
    assert len(tools) == 10


@pytest.mark.asyncio
async def test_server_tool_annotations_match_spec(server):
    """Verifica que las anotaciones (read_only, destructive, idempotent) coincidan con el diseño."""
    tools = {t.name: t for t in await server.list_tools()}

    # Tools de solo lectura
    read_only_tools = [
        "search_businesses",
        "get_business_details",
        "get_service_contract",
        "get_dimension_options",
        "check_availability",
        "get_operation_result",
        "get_booking_status",
        "list_my_bookings",
    ]
    for name in read_only_tools:
        ann = tools[name].annotations
        assert ann is not None, f"Tool {name} debe tener anotaciones"
        assert ann.read_only_hint is True, f"Tool {name} debe tener read_only_hint=True"

    # Tool de creación: idempotent=True, destructive!=True
    create_ann = tools["create_booking_request"].annotations
    assert create_ann.idempotent_hint is True
    assert create_ann.destructive_hint is not True

    # Tool de cancelación: destructive=True
    cancel_ann = tools["cancel_booking"].annotations
    assert cancel_ann.destructive_hint is True


@pytest.mark.asyncio
async def test_server_ctx_hidden_from_tool_input_schemas(server):
    """Verifica que el parámetro 'ctx' de Context de MCP no figure en el input_schema de Claude."""
    tools = await server.list_tools()
    for t in tools:
        props = t.input_schema.get("properties", {})
        assert "ctx" not in props, f"El parámetro 'ctx' no debe ser expuesto en {t.name}"


# =========================================================================
# 2. Pruebas de Autenticación y Contexto
# =========================================================================

@pytest.mark.asyncio
async def test_tool_call_without_auth_returns_error(server):
    """Prueba que si no hay usuario autenticado en contexto ni cabecera, se devuelva error estructurado."""
    # Reset temporal del usuario en contexto
    current_user_context.set(None)

    result = await server.call_tool("search_businesses", {"query": "Pádel"})
    text_content = result.content[0].text
    payload = json.loads(text_content)

    assert payload.get("error") is True
    assert payload.get("error_type") == "AuthenticationRequiredException"
    assert "Autenticación requerida" in payload.get("message")


def test_auth_context_extracts_phone_number_from_jwt():
    """Prueba que extract_user_context extrae correctamente el claim phone_number del JWT."""
    from src.mcp.presentation.auth_context import extract_user_context

    current_user_context.set(None)
    settings = get_settings()
    user_id = uuid4()
    token = jwt.encode(
        {
            "sub": str(user_id),
            "phone_number": "+18095551234",
            "scope": "bookings:read bookings:write",
            "exp": int(datetime.now(timezone.utc).timestamp()) + 3600,
        },
        key=settings.OAUTH_JWT_SECRET_KEY,
        algorithm=settings.OAUTH_JWT_ALGORITHM,
    )

    mock_ctx = MagicMock()
    mock_ctx.headers = {"Authorization": f"Bearer {token}"}

    user = extract_user_context(mock_ctx, required_scope="bookings:read")
    assert user.user_uuid == user_id
    assert user.phone_number == "+18095551234"


def test_auth_context_extracts_phone_number_from_dev_headers():
    """Prueba que extract_user_context extrae X-User-UUID y X-User-Phone."""
    from src.mcp.presentation.auth_context import extract_user_context

    current_user_context.set(None)
    user_id = uuid4()
    mock_ctx = MagicMock()
    mock_ctx.headers = {
        "x-user-uuid": str(user_id),
        "x-user-phone": "+34912345678",
    }

    user = extract_user_context(mock_ctx)
    assert user.user_uuid == user_id
    assert user.phone_number == "+34912345678"


# =========================================================================
# 3. Invocación de Tools de Catálogo y Contratos
# =========================================================================

@pytest.mark.asyncio
async def test_search_businesses_tool_execution(server, mock_use_cases):
    """Prueba la ejecución exitosa de search_businesses vía protocolo MCP."""
    mock_use_cases.search_businesses.execute = AsyncMock(
        return_value=SearchBusinessesResponseDTO(
            items=[
                BusinessSummaryDTO(
                    id=1,
                    name="Club Pádel Santo Domingo",
                    code="CPSD",
                    category="Pádel",
                    city="Santo Domingo",
                    sector="Piantini",
                    operating_hours={"open": "07:00", "close": "23:00"},
                    rule_type="only_today",
                )
            ],
            total_count=1,
            next_cursor=None,
        )
    )

    result = await server.call_tool("search_businesses", {"query": "Pádel", "city": "Santo Domingo"})
    data = json.loads(result.content[0].text)

    assert data["total_count"] == 1
    assert data["items"][0]["name"] == "Club Pádel Santo Domingo"
    assert data["items"][0]["business_id"] == 1
    mock_use_cases.search_businesses.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_business_details_tool_execution(server, mock_use_cases):
    """Prueba la ejecución exitosa de get_business_details."""
    mock_use_cases.get_business_details.execute = AsyncMock(
        return_value=BusinessDetailsDTO(
            id=5,
            name="Club Pádel Bella Vista",
            code="CPBV",
            category="Deportes",
            city="Santo Domingo",
            sector="Bella Vista",
            address_line="Av. Sarasota 40",
            operating_hours={"open": "07:00", "close": "23:00"},
            rule_type="only_today",
            advance_booking_rule="Reservas permitidas únicamente para el día de hoy",
            services=[
                BusinessServiceSummaryDTO(
                    id=20,
                    name="Pista Panorámica 1",
                    category="Pádel",
                    pattern="slot_object",
                    has_active_contract=True,
                )
            ],
            phone="+18095551234",
            email="info@cpbv.do",
        )
    )

    result = await server.call_tool("get_business_details", {"business_id": 5})
    data = json.loads(result.content[0].text)

    assert data["business_id"] == 5
    assert data["name"] == "Club Pádel Bella Vista"
    assert len(data["services"]) == 1
    assert data["services"][0]["service_id"] == 20
    assert data["location"]["city"] == "Santo Domingo"


@pytest.mark.asyncio
async def test_get_service_contract_tool_execution(server, mock_use_cases):
    """Prueba la ejecución exitosa de get_service_contract."""
    mock_use_cases.get_service_contract.execute = AsyncMock(
        return_value=ServiceContractDTO(
            service_id=20,
            pattern="slot_object",
            contract_version="v1.0",
            contract_version_id=uuid4(),
            request_expires_in_seconds=900,
            booking_fields={"type": "object", "properties": {"players": {"type": "integer"}}},
            availability_dimensions=[
                ContractDimensionProjectionDTO(
                    key="surface",
                    label="Superficie",
                    values_source="inline",
                    apply_mode="post_filter",
                    values=[DimensionOptionDTO(value_key="cristal", label="Cristal")],
                )
            ],
        )
    )

    result = await server.call_tool("get_service_contract", {"service_id": 20})
    data = json.loads(result.content[0].text)

    assert data["service_id"] == 20
    assert data["pattern"] == "slot_object"
    assert data["availability_dimensions"][0]["key"] == "surface"


# =========================================================================
# 4. Invocación de Tools de Disponibilidad
# =========================================================================

@pytest.mark.asyncio
async def test_check_availability_tool_execution(server, mock_use_cases):
    """Prueba la ejecución exitosa de check_availability."""
    mock_use_cases.check_availability.execute = AsyncMock(
        return_value=AvailabilityResponseDTO(
            status="completed",
            service_id=20,
            slots=[
                AvailableSlotDTO(
                    offer_ref="off-padel-1",
                    slot_start=datetime(2026, 10, 28, 16, 0, tzinfo=timezone.utc),
                    slot_end=datetime(2026, 10, 28, 17, 30, tzinfo=timezone.utc),
                    slot_token="signed-crypto-slot-token-xyz",
                    is_estimated=False,
                    slot_type="confirmed_schedule",
                    price_estimate=SlotPriceEstimateDTO(
                        amount=Decimal("1500.00"),
                        currency="DOP",
                        calculation_basis="per_booking",
                        rule_label="Tarifa Tarde",
                    ),
                    attributes={"court_name": "Pista 1"},
                )
            ],
            applied_filters={"surface": "cristal"},
        )
    )

    result = await server.call_tool(
        "check_availability",
        {"service_id": 20, "date": "2026-10-28", "filters": {"surface": "cristal"}},
    )
    data = json.loads(result.content[0].text)

    assert data["status"] == "completed"
    assert len(data["slots"]) == 1
    assert data["slots"][0]["slot_token"] == "signed-crypto-slot-token-xyz"
    assert data["slots"][0]["price_estimate"]["amount"] == "1500.00"


# =========================================================================
# 5. Invocación de Tools de Reservas
# =========================================================================

@pytest.mark.asyncio
async def test_create_booking_request_tool_execution(server, mock_use_cases, sample_user_uuid):
    """Prueba la ejecución de create_booking_request retornando estado requested."""
    booking_id = uuid4()
    mock_use_cases.create_booking_request.execute = AsyncMock(
        return_value=BookingCreationResultDTO(
            booking_id=booking_id,
            status="requested",
            service_id=20,
            slot_start=datetime(2026, 10, 28, 16, 0, tzinfo=timezone.utc),
            slot_end=datetime(2026, 10, 28, 17, 30, tzinfo=timezone.utc),
            applied_filters={"surface": "cristal"},
            expires_at=datetime.now(timezone.utc),
            message="Solicitud de reserva registrada exitosamente.",
        )
    )

    result = await server.call_tool(
        "create_booking_request",
        {
            "idempotency_key": "idemp-req-1",
            "slot_token": "signed-crypto-slot-token-xyz",
            "fields": {"players": 4},
        },
    )
    data = json.loads(result.content[0].text)

    assert data["booking_id"] == str(booking_id)
    assert data["status"] == "requested"
    assert data["applied_filters"] == {"surface": "cristal"}


@pytest.mark.asyncio
async def test_get_booking_status_tool_execution(server, mock_use_cases, sample_user_uuid):
    """Prueba la consulta de estado de una reserva."""
    booking_id = uuid4()
    mock_use_cases.get_booking_status.execute = AsyncMock(
        return_value=BookingDetailsDTO(
            booking_id=booking_id,
            user_uuid=sample_user_uuid,
            service_id=20,
            status="confirmed",
            service_name="Pista Central",
            establishment_name="Club Pádel Santo Domingo",
            external_ref="CONF-PADEL-99",
            explanation="Reserva confirmada exitosamente. Localizador: CONF-PADEL-99.",
        )
    )

    result = await server.call_tool("get_booking_status", {"booking_id": str(booking_id)})
    data = json.loads(result.content[0].text)

    assert data["booking_id"] == str(booking_id)
    assert data["status"] == "confirmed"
    assert data["external_ref"] == "CONF-PADEL-99"


@pytest.mark.asyncio
async def test_cancel_booking_tool_execution(server, mock_use_cases):
    """Prueba la solicitud de cancelación de una reserva."""
    booking_id = uuid4()
    mock_use_cases.cancel_booking.execute = AsyncMock(
        return_value=CancellationResultDTO(
            booking_id=booking_id,
            status="cancel_requested",
            message="Solicitud de cancelación registrada exitosamente.",
        )
    )

    result = await server.call_tool(
        "cancel_booking",
        {"booking_id": str(booking_id), "reason": "Motivos personales"},
    )
    data = json.loads(result.content[0].text)

    assert data["booking_id"] == str(booking_id)
    assert data["status"] == "cancel_requested"


# =========================================================================
# 6. Manejo Resiliente de Excepciones de Dominio
# =========================================================================

@pytest.mark.asyncio
async def test_booking_rule_violation_caught_and_formatted(server, mock_use_cases):
    """Prueba que BookingRuleViolationException se formatee limpiamente sin generar fallo 500."""
    mock_use_cases.check_availability.execute = AsyncMock(
        side_effect=BookingRuleViolationException("El establecimiento solo permite reservar para hoy.")
    )

    result = await server.call_tool("check_availability", {"service_id": 20, "date": "2026-11-01"})
    data = json.loads(result.content[0].text)

    assert data["error"] is True
    assert data["error_type"] == "BookingRuleViolationException"
    assert "solo permite reservar para hoy" in data["message"]
    assert "resolution" in data


@pytest.mark.asyncio
async def test_entity_not_found_caught_and_formatted(server, mock_use_cases):
    """Prueba que EntityNotFoundException se formatee limpiamente."""
    mock_use_cases.get_business_details.execute = AsyncMock(
        side_effect=EntityNotFoundException("Establecimiento con id 9999 no encontrado.")
    )

    result = await server.call_tool("get_business_details", {"business_id": 9999})
    data = json.loads(result.content[0].text)

    assert data["error"] is True
    assert data["error_type"] == "EntityNotFoundException"
    assert "no encontrado" in data["message"]


def test_build_mcp_use_cases_factory():
    """Verifica que build_mcp_use_cases instancie los 10 use cases con sus repositorios y adaptadores."""
    from src.mcp.presentation.dependencies import build_mcp_use_cases
    mock_session = MagicMock()
    mock_redis = MagicMock()
    container = build_mcp_use_cases(mock_session, mock_redis)
    assert container.search_businesses is not None
    assert container.get_business_details is not None
    assert container.get_service_contract is not None
    assert container.get_dimension_options is not None
    assert container.check_availability is not None
    assert container.get_operation_result is not None
    assert container.create_booking_request is not None
    assert container.get_booking_status is not None
    assert container.list_my_bookings is not None
    assert container.cancel_booking is not None
