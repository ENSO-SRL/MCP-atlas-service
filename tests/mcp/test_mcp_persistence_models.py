from src.mcp.infrastructure.persistence.models import (
    BookingRequestModel,
    BookingStatusHistoryModel,
    CategoriaServicioModel,
    ContractDimensionDependencyModel,
    ContractDimensionModel,
    ContractDimensionValueModel,
    EstablishmentCategoryModel,
    EstablishmentModel,
    InboxEventModel,
    OutboxEventModel,
    ServiceContractVersionModel,
    ServicePriceRuleModel,
    ServicePricingPolicyModel,
    ServicioModel,
)
from src.shared.database.session import Base


def test_sqlalchemy_models_registration():
    # Verificar que todos los modelos están en Base.metadata
    table_names = set(Base.metadata.tables.keys())

    # Tablas del catálogo (sin esquema o en default)
    assert "establishments" in table_names
    assert "establishment_categories" in table_names
    assert "servicios" in table_names
    assert "categorias_servicio" in table_names

    # Tablas dedicadas en el esquema 'mcp'
    assert "mcp.service_contract_version" in table_names
    assert "mcp.contract_dimension" in table_names
    assert "mcp.contract_dimension_dependency" in table_names
    assert "mcp.contract_dimension_value" in table_names
    assert "mcp.service_pricing_policy" in table_names
    assert "mcp.service_price_rule" in table_names
    assert "mcp.booking_request" in table_names
    assert "mcp.booking_status_history" in table_names
    assert "mcp.outbox_event" in table_names
    assert "mcp.inbox_event" in table_names


def test_mcp_models_schema_and_columns():
    booking_table = Base.metadata.tables["mcp.booking_request"]
    assert booking_table.schema == "mcp"
    assert "idempotency_key" in booking_table.c
    assert "token_id" in booking_table.c
    assert "user_uuid" in booking_table.c

    contract_table = Base.metadata.tables["mcp.service_contract_version"]
    assert contract_table.schema == "mcp"
    assert "booking_fields_schema" in contract_table.c
    assert "status" in contract_table.c
