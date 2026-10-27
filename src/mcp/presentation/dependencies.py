from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator, Optional

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.mcp.application.use_cases import (
    CancelBookingUseCase,
    CheckAvailabilityUseCase,
    CreateBookingRequestUseCase,
    GetBookingStatusUseCase,
    GetBusinessDetailsUseCase,
    GetDimensionOptionsUseCase,
    GetOperationResultUseCase,
    GetServiceContractUseCase,
    ListMyBookingsUseCase,
    SearchBusinessesUseCase,
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
from src.mcp.infrastructure.redis.redis_bus_client import RedisBusClient
from src.mcp.infrastructure.redis.redis_cache_manager import (
    RedisAvailabilityCache,
    RedisDimensionOptionsCache,
)
from src.mcp.infrastructure.redis.redis_hold_manager import RedisHoldManager
from src.mcp.infrastructure.security.slot_token_codec import SlotTokenCodec
from src.shared.config.settings import get_settings
from src.shared.database.session import get_db_session
from src.shared.redis.client import get_redis_client


@dataclass
class MCPUseCases:
    """Contenedor de instancias de los 10 casos de uso del servidor MCP."""
    search_businesses: SearchBusinessesUseCase
    get_business_details: GetBusinessDetailsUseCase
    get_service_contract: GetServiceContractUseCase
    get_dimension_options: GetDimensionOptionsUseCase
    check_availability: CheckAvailabilityUseCase
    get_operation_result: GetOperationResultUseCase
    create_booking_request: CreateBookingRequestUseCase
    get_booking_status: GetBookingStatusUseCase
    list_my_bookings: ListMyBookingsUseCase
    cancel_booking: CancelBookingUseCase


def build_mcp_use_cases(
    session: AsyncSession,
    redis_client: Optional[Redis] = None,
) -> MCPUseCases:
    """Construye y ensambla los casos de uso inyectando repositorios y adaptadores."""
    settings = get_settings()
    redis = redis_client or get_redis_client()

    # Repositorios SQL
    est_repo = SqlEstablishmentRepository(session)
    svc_repo = SqlCatalogServiceRepository(session)
    contract_repo = SqlContractRepository(session)
    booking_repo = SqlBookingRepository(session)
    outbox_repo = SqlOutboxRepository(session)

    # Adaptadores Redis & Seguridad
    avail_cache = RedisAvailabilityCache(redis)
    dim_cache = RedisDimensionOptionsCache(redis)
    hold_manager = RedisHoldManager(redis)
    bus_client = RedisBusClient(redis)
    token_codec = SlotTokenCodec(secret=settings.MCP_TOKEN_SECRET)

    return MCPUseCases(
        search_businesses=SearchBusinessesUseCase(est_repo),
        get_business_details=GetBusinessDetailsUseCase(est_repo, svc_repo, contract_repo),
        get_service_contract=GetServiceContractUseCase(svc_repo, contract_repo),
        get_dimension_options=GetDimensionOptionsUseCase(contract_repo, dim_cache, bus_client, catalog_repo=svc_repo),
        check_availability=CheckAvailabilityUseCase(
            est_repo, svc_repo, contract_repo, avail_cache, hold_manager, bus_client, token_codec
        ),
        get_operation_result=GetOperationResultUseCase(bus_client, hold_manager, token_codec, contract_repo),
        create_booking_request=CreateBookingRequestUseCase(
            booking_repo, contract_repo, hold_manager, outbox_repo, token_codec, catalog_repo=svc_repo
        ),
        get_booking_status=GetBookingStatusUseCase(booking_repo, svc_repo, est_repo),
        list_my_bookings=ListMyBookingsUseCase(booking_repo, svc_repo),
        cancel_booking=CancelBookingUseCase(booking_repo, outbox_repo, catalog_repo=svc_repo),
    )


# Override global para pruebas unitarias
_test_use_cases_override: Optional[MCPUseCases] = None


def set_test_use_cases(override: Optional[MCPUseCases]) -> None:
    """Permite fijar mocks de casos de uso para las pruebas unitarias."""
    global _test_use_cases_override
    _test_use_cases_override = override


@asynccontextmanager
async def get_mcp_use_cases(
    session: Optional[AsyncSession] = None,
    redis_client: Optional[Redis] = None,
) -> AsyncGenerator[MCPUseCases, None]:
    """Generador de contexto que provee los casos de uso con su sesión de base de datos."""
    if _test_use_cases_override is not None:
        yield _test_use_cases_override
        return

    if session is not None:
        yield build_mcp_use_cases(session, redis_client)
    else:
        async with get_db_session() as new_session:
            yield build_mcp_use_cases(new_session, redis_client)
