from __future__ import annotations

from typing import Optional
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.mcp.domain.entities.catalog_entities import Establishment
from src.mcp.domain.enums.mcp_enums import RuleType
from src.mcp.domain.ports.mcp_ports import IEstablishmentRepository
from src.mcp.domain.value_objects.establishment_vo import ContactInfo, LocationAddress
from src.mcp.infrastructure.persistence.models.catalog_models import (
    EstablishmentCategoryModel,
    EstablishmentModel,
)


class SqlEstablishmentRepository(IEstablishmentRepository):
    """
    Implementación SQL del puerto IEstablishmentRepository.
    Consulta la réplica local de 'establishments' en ATLAS-BACKEND de solo lectura.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    @staticmethod
    def _to_domain(model: EstablishmentModel) -> Establishment:
        rule_type: Optional[RuleType] = None
        if model.rule_type:
            try:
                rule_type = RuleType(model.rule_type)
            except ValueError:
                rule_type = None

        location = LocationAddress(
            country=model.country,
            state_province=model.state_province,
            city=model.city,
            sector=model.sector,
            residential=model.residential,
            street=model.street,
            building_number=model.building_number,
            postal_code=model.postal_code,
            reference=model.reference,
            google_maps_url=model.google_maps_url,
        )

        contact = ContactInfo(
            phone=model.phone,
            email=model.email,
            website=model.website,
        )

        category_name = model.category.name if model.category else None

        return Establishment(
            id=model.id,
            name=model.name,
            code=model.code,
            description=model.description,
            is_active=model.is_active,
            has_credentials=model.has_credentials,
            rule_type=rule_type,
            opening_hour=model.opening_hour,
            closing_hour=model.closing_hour,
            location=location,
            contact=contact,
            category_name=category_name,
            configuration=model.configuration or {},
        )

    async def search(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        zone: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Establishment]:
        stmt = (
            select(EstablishmentModel)
            .options(selectinload(EstablishmentModel.category))
            .where(EstablishmentModel.is_active.is_(True))
        )

        if query:
            clean_query = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    EstablishmentModel.name.ilike(clean_query),
                    EstablishmentModel.description.ilike(clean_query),
                )
            )

        if category:
            stmt = stmt.join(
                EstablishmentCategoryModel,
                EstablishmentModel.category_id == EstablishmentCategoryModel.id,
            ).where(EstablishmentCategoryModel.name.ilike(f"%{category.strip()}%"))

        if zone:
            clean_zone = f"%{zone.strip()}%"
            stmt = stmt.where(
                or_(
                    EstablishmentModel.city.ilike(clean_zone),
                    EstablishmentModel.sector.ilike(clean_zone),
                    EstablishmentModel.state_province.ilike(clean_zone),
                )
            )

        stmt = stmt.order_by(EstablishmentModel.name.asc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def get_by_id(self, establishment_id: int) -> Optional[Establishment]:
        stmt = (
            select(EstablishmentModel)
            .options(selectinload(EstablishmentModel.category))
            .where(EstablishmentModel.id == establishment_id)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def get_by_code(self, code: str) -> Optional[Establishment]:
        stmt = (
            select(EstablishmentModel)
            .options(selectinload(EstablishmentModel.category))
            .where(EstablishmentModel.code == code)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None
