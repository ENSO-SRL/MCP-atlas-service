from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from src.mcp.domain.enums.mcp_enums import (
    AvailabilityPattern,
    ContractStatus,
    DimensionApplyMode,
    DimensionValuesSource,
)
from src.mcp.domain.exceptions.mcp_exceptions import (
    ContractValidationException,
    MissingDimensionDependencyException,
)
from src.shared.domain.base import AggregateRoot, Entity


@dataclass
class ContractDimension(Entity[UUID]):
    """
    Dimensión de disponibilidad para un contrato de servicio.
    Declara origen de valores (inline, slots, separate_query) y modo de filtro (post_filter, upstream_param).
    """
    key: str = ""
    label: str = ""
    description: Optional[str] = None
    values_source: DimensionValuesSource = DimensionValuesSource.INLINE
    apply_mode: DimensionApplyMode = DimensionApplyMode.POST_FILTER
    required: bool = False
    allows_any: bool = False
    reports_counts: bool = False
    resolver_ref: Optional[str] = None  # Clave opaca interna para Disponibilidad (oculta a Claude)
    depends_on: list[str] = field(default_factory=list)
    inline_values: list[dict[str, Any]] = field(default_factory=list)
    position: int = 0

    def is_upstream(self) -> bool:
        return self.apply_mode == DimensionApplyMode.UPSTREAM_PARAM


@dataclass
class ServiceContractVersion(AggregateRoot[UUID]):
    """
    Agregado Raíz ServiceContractVersion.
    Versión inmutable del contrato de un servicio. Contiene dimensiones de disponibilidad
    y esquema de campos requeridos para la reserva.
    """
    service_id: int = 0
    version_no: int = 1
    status: ContractStatus = ContractStatus.DRAFT
    pattern: AvailabilityPattern = AvailabilityPattern.SLOT_OBJECT
    booking_fields_schema: dict[str, Any] = field(default_factory=dict)
    dimensions: list[ContractDimension] = field(default_factory=list)
    payment_policy: dict[str, Any] = field(default_factory=dict)
    cancellation_policy: dict[str, Any] = field(default_factory=dict)
    request_ttl_seconds: int = 900
    content_hash: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def validate_dependencies(self) -> None:
        """
        Valida que el grafo de dimensiones (depends_on) sea acíclico y que todas las
        dimensiones referenciadas existan.
        """
        dimension_map = {d.key: d for d in self.dimensions}

        # 1. Verificar existencia
        for dim in self.dimensions:
            for dep in dim.depends_on:
                if dep not in dimension_map:
                    raise MissingDimensionDependencyException([dep])
                if dep == dim.key:
                    raise ContractValidationException(f"La dimensión '{dim.key}' no puede depender de sí misma.")

            if dim.values_source == DimensionValuesSource.SEPARATE_QUERY and not dim.resolver_ref:
                raise ContractValidationException(
                    f"La dimensión '{dim.key}' con origen separate_query requiere resolver_ref."
                )

        # 2. Detección de ciclos (algoritmo DFS de 3 colores)
        # 0 = sin visitar, 1 = visitando, 2 = visitado
        visited: dict[str, int] = {k: 0 for k in dimension_map}

        def dfs(node: str) -> None:
            visited[node] = 1
            for neighbor in dimension_map[node].depends_on:
                if visited[neighbor] == 1:
                    raise ContractValidationException(
                        f"Ciclo detectado en las dependencias de dimensiones involucrando a '{node}' y '{neighbor}'."
                    )
                if visited[neighbor] == 0:
                    dfs(neighbor)
            visited[node] = 2

        for key in dimension_map:
            if visited[key] == 0:
                dfs(key)

    def publish(self) -> None:
        """Publica el contrato volviéndolo inmutable."""
        if self.status != ContractStatus.DRAFT:
            raise ContractValidationException("Solo contratos en borrador (DRAFT) pueden ser publicados.")

        self.validate_dependencies()
        self.status = ContractStatus.PUBLISHED
        self.published_at = datetime.now(timezone.utc)
        
        # Generar hash de contenido para verificación de integridad
        raw_content = json.dumps(
            {
                "service_id": self.service_id,
                "version_no": self.version_no,
                "pattern": self.pattern.value,
                "schema": self.booking_fields_schema,
                "dimensions": [d.key for d in self.dimensions],
            },
            sort_keys=True,
        )
        self.content_hash = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()

    def retire(self) -> None:
        """Retira la versión del contrato."""
        if self.status != ContractStatus.PUBLISHED:
            raise ContractValidationException("Solo contratos publicados pueden ser retirados.")
        self.status = ContractStatus.RETIRED

    def get_public_projection(self) -> dict[str, Any]:
        """
        Construye la proyección pública para el tool get_service_contract de Claude,
        omitiendo claves internas del backend (resolver_ref).
        """
        public_dimensions = []
        for d in sorted(self.dimensions, key=lambda x: x.position):
            dim_dict: dict[str, Any] = {
                "key": d.key,
                "label": d.label,
                "description": d.description,
                "values_source": d.values_source.value,
                "apply_mode": d.apply_mode.value,
                "required": d.required,
                "allows_any": d.allows_any,
                "reports_counts": d.reports_counts,
                "depends_on": d.depends_on,
            }
            if d.values_source == DimensionValuesSource.INLINE:
                dim_dict["values"] = d.inline_values
            public_dimensions.append(dim_dict)

        return {
            "service_id": self.service_id,
            "pattern": self.pattern.value,
            "contract_version": f"{self.published_at.strftime('%Y-%m-%d') if self.published_at else 'v'}.{self.version_no}",
            "availability_dimensions": public_dimensions,
            "booking_fields": self.booking_fields_schema,
            "payment_policy": self.payment_policy,
            "cancellation_policy": self.cancellation_policy,
            "request_expires_in_seconds": self.request_ttl_seconds,
        }
