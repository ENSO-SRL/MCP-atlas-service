from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional
from uuid import UUID

from src.mcp.domain.entities.booking_request import BookingRequest
from src.mcp.domain.entities.catalog_entities import CatalogService, Establishment
from src.mcp.domain.entities.contract_entities import ServiceContractVersion
from src.mcp.domain.entities.service_price_rule import ServicePriceRule
from src.mcp.domain.enums.mcp_enums import BookingStatus


class IEstablishmentRepository(ABC):
    """Puerto de lectura sobre la réplica local de establecimientos en ATLAS-BACKEND."""

    @abstractmethod
    async def search(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        zone: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Establishment]:
        """Busca establecimientos activos aplicando filtros opcionales."""
        pass

    @abstractmethod
    async def get_by_id(self, establishment_id: int) -> Optional[Establishment]:
        pass

    @abstractmethod
    async def get_by_code(self, code: str) -> Optional[Establishment]:
        pass


class ICatalogServiceRepository(ABC):
    """Puerto de lectura sobre la tabla 'servicios' de ATLAS-BACKEND."""

    @abstractmethod
    async def get_by_id(self, service_id: int) -> Optional[CatalogService]:
        pass

    @abstractmethod
    async def list_by_establishment(self, establishment_id: int) -> list[CatalogService]:
        pass


class IBookingRepository(ABC):
    """Puerto para persistencia y consulta de solicitudes de reserva (BookingRequest)."""

    @abstractmethod
    async def save(self, booking: BookingRequest) -> BookingRequest:
        pass

    @abstractmethod
    async def get_by_id(self, booking_id: UUID) -> Optional[BookingRequest]:
        pass

    @abstractmethod
    async def get_by_idempotency_key(
        self, user_uuid: UUID, idempotency_key: str
    ) -> Optional[BookingRequest]:
        """Permite recuperar la solicitud previa del usuario para garantizar idempotencia."""
        pass

    @abstractmethod
    async def list_by_user(
        self,
        user_uuid: UUID,
        status: Optional[BookingStatus] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[BookingRequest]:
        pass


class IContractRepository(ABC):
    """Puerto para la gestión de contratos dinámicos de servicios y reglas de precios."""

    @abstractmethod
    async def get_active_by_service_id(self, service_id: int) -> Optional[ServiceContractVersion]:
        """Obtiene la versión actualmente publicada del contrato para un servicio."""
        pass

    @abstractmethod
    async def get_by_version_id(self, version_id: UUID) -> Optional[ServiceContractVersion]:
        pass

    @abstractmethod
    async def list_price_rules_for_service(self, service_id: int) -> list[ServicePriceRule]:
        """Lista las reglas de precios vigentes para el servicio."""
        pass


class IOutboxRepository(ABC):
    """Puerto para registrar eventos en la tabla outbox_event dentro de la misma transacción ACID."""

    @abstractmethod
    async def record_event(
        self,
        event_type: str,
        aggregate_id: UUID,
        payload: dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> None:
        pass


class IHoldManager(ABC):
    """Puerto para gestionar holds temporales de slots en memoria (Redis) y prevenir colisiones."""

    @abstractmethod
    async def place_hold(self, offer_ref: str, booking_id: UUID, ttl_seconds: int) -> bool:
        """Intenta colocar un hold atómico (SETNX). Retorna True si se concedió."""
        pass

    @abstractmethod
    async def release_hold(self, offer_ref: str) -> None:
        pass

    @abstractmethod
    async def is_held(self, offer_ref: str) -> bool:
        pass


class IRedisBusClient(ABC):
    """Puerto para el bus de eventos asíncronos y RPC diferido sobre Redis."""

    @abstractmethod
    async def publish_availability_request(
        self, operation_id: str, payload: dict[str, Any]
    ) -> None:
        pass

    @abstractmethod
    async def wait_for_response(
        self, response_key: str, timeout_seconds: float
    ) -> Optional[dict[str, Any]]:
        """Realiza la espera superficial no bloqueante (ej. BLPOP o Stream read)."""
        pass

    @abstractmethod
    async def get_operation_result(self, operation_id: str) -> Optional[dict[str, Any]]:
        """Recupera el resultado de una operación diferida (Tool get_operation_result)."""
        pass

    @abstractmethod
    async def get_cached_availability(self, cache_key: str) -> Optional[dict[str, Any]]:
        """Consulta la caché determinista de slots (Cache-Aside)."""
        pass

    @abstractmethod
    async def set_cached_availability(
        self, cache_key: str, data: dict[str, Any], ttl_seconds: int
    ) -> None:
        pass
