from __future__ import annotations

from typing import Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.mcp.domain.entities.contract_entities import (
    ContractDimension,
    ServiceContractVersion,
)
from src.mcp.domain.entities.service_price_rule import ServicePriceRule
from src.mcp.domain.enums.mcp_enums import (
    AvailabilityPattern,
    CalculationBasis,
    ContractStatus,
    DimensionApplyMode,
    DimensionValuesSource,
)
from src.mcp.domain.ports.mcp_ports import IContractRepository
from src.mcp.infrastructure.persistence.models.contract_models import (
    ContractDimensionDependencyModel,
    ContractDimensionModel,
    ServiceContractVersionModel,
    ServicePriceRuleModel,
    ServicePricingPolicyModel,
)


class SqlContractRepository(IContractRepository):
    """
    Implementación SQL del puerto IContractRepository.
    Gestiona versiones de contratos, dimensiones, dependencias y reglas de precios
    en el esquema 'mcp' de PostgreSQL.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def _build_domain_contract(
        self, model: ServiceContractVersionModel
    ) -> ServiceContractVersion:
        # 1. Cargar dependencias de dimensiones para esta versión
        dep_stmt = select(ContractDimensionDependencyModel).where(
            ContractDimensionDependencyModel.contract_version_id == model.id
        )
        dep_result = await self._session.execute(dep_stmt)
        dep_rows = dep_result.scalars().all()

        # Mapeo de dimension_id a key
        dim_key_by_id = {dim.id: dim.key for dim in model.dimensions}
        depends_on_map: dict[UUID, list[str]] = {dim.id: [] for dim in model.dimensions}
        for dep in dep_rows:
            target_key = dim_key_by_id.get(dep.depends_on_dimension_id)
            if target_key and dep.dimension_id in depends_on_map:
                depends_on_map[dep.dimension_id].append(target_key)

        # 2. Mapear dimensiones
        domain_dimensions: list[ContractDimension] = []
        for dim_model in sorted(model.dimensions, key=lambda d: d.position):
            inline_values = [
                {
                    "value_key": val.value_key,
                    "label": val.label,
                    "description": val.description,
                    "position": val.position,
                }
                for val in sorted(dim_model.inline_values, key=lambda v: v.position)
            ]

            dim = ContractDimension(
                id=dim_model.id,
                key=dim_model.key,
                label=dim_model.label,
                description=dim_model.description,
                values_source=DimensionValuesSource(dim_model.values_source),
                apply_mode=DimensionApplyMode(dim_model.apply_mode),
                required=dim_model.required,
                allows_any=dim_model.allows_any,
                reports_counts=dim_model.reports_counts,
                resolver_ref=dim_model.resolver_ref,
                depends_on=depends_on_map.get(dim_model.id, []),
                inline_values=inline_values,
                position=dim_model.position,
            )
            domain_dimensions.append(dim)

        return ServiceContractVersion(
            id=model.id,
            service_id=model.service_id,
            version_no=model.version_no,
            status=ContractStatus(model.status),
            pattern=AvailabilityPattern(model.pattern) if hasattr(model, "pattern") and model.pattern else AvailabilityPattern.SLOT_OBJECT,
            booking_fields_schema=model.booking_fields_schema or {},
            dimensions=domain_dimensions,
            payment_policy=model.payment_policy or {},
            cancellation_policy=model.cancellation_policy or {},
            request_ttl_seconds=model.request_ttl_seconds,
            content_hash=model.content_hash,
            published_at=model.published_at,
            created_at=model.created_at,
        )

    async def get_active_by_service_id(self, service_id: int) -> Optional[ServiceContractVersion]:
        stmt = (
            select(ServiceContractVersionModel)
            .options(
                selectinload(ServiceContractVersionModel.dimensions).selectinload(
                    ContractDimensionModel.inline_values
                )
            )
            .where(
                ServiceContractVersionModel.service_id == service_id,
                ServiceContractVersionModel.status == "published",
            )
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return await self._build_domain_contract(model) if model else None

    async def get_by_version_id(self, version_id: UUID) -> Optional[ServiceContractVersion]:
        stmt = (
            select(ServiceContractVersionModel)
            .options(
                selectinload(ServiceContractVersionModel.dimensions).selectinload(
                    ContractDimensionModel.inline_values
                )
            )
            .where(ServiceContractVersionModel.id == version_id)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return await self._build_domain_contract(model) if model else None

    async def list_price_rules_for_service(self, service_id: int) -> list[ServicePriceRule]:
        # Consultar la moneda en la política de precios del servicio
        pol_stmt = select(ServicePricingPolicyModel.currency).where(
            ServicePricingPolicyModel.service_id == service_id
        )
        pol_res = await self._session.execute(pol_stmt)
        currency = pol_res.scalar_one_or_none() or "DOP"

        rule_stmt = (
            select(ServicePriceRuleModel)
            .where(ServicePriceRuleModel.service_id == service_id)
            .order_by(ServicePriceRuleModel.priority.desc())
        )
        result = await self._session.execute(rule_stmt)
        models = result.scalars().all()

        domain_rules: list[ServicePriceRule] = []
        for m in models:
            domain_rules.append(
                ServicePriceRule(
                    id=m.id,
                    service_id=m.service_id,
                    label=m.label,
                    weekdays=list(m.weekdays),
                    start_minute=m.start_minute,
                    end_minute=m.end_minute,
                    valid_from=m.valid_from,
                    valid_to=m.valid_to,
                    min_party_size=m.min_party_size,
                    max_party_size=m.max_party_size,
                    min_duration_min=m.min_duration_min,
                    max_duration_min=m.max_duration_min,
                    dimension_conditions=m.dimension_conditions,
                    amount=m.amount,
                    currency=currency,
                    calculation_basis=CalculationBasis(m.calculation_basis),
                    is_starting_price=m.is_starting_price,
                    priority=m.priority,
                )
            )
        return domain_rules
