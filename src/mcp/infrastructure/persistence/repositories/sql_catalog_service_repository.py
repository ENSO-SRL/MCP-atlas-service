from __future__ import annotations

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.mcp.domain.entities.catalog_entities import CatalogService
from src.mcp.domain.ports.mcp_ports import ICatalogServiceRepository
from src.mcp.domain.value_objects.establishment_vo import ContactInfo, LocationAddress
from src.mcp.infrastructure.persistence.models.catalog_models import ServicioModel


class SqlCatalogServiceRepository(ICatalogServiceRepository):
    """
    Implementación SQL del puerto ICatalogServiceRepository.
    Consulta la tabla 'servicios' de ATLAS-BACKEND de solo lectura.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    @staticmethod
    def _to_domain(model: ServicioModel) -> CatalogService:
        category_name = model.categoria.nombre if model.categoria else "GENERAL"
        location = LocationAddress(
            country=model.country,
            city=model.city,
            sector=model.sector,
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
        return CatalogService(
            id=model.id,
            establishment_id=model.establishment_id,
            name=model.nombre,
            category_name=category_name,
            description=model.descripcion,
            is_active=model.activo,
            has_credentials=model.has_credentials,
            combo_code=model.combo_code,
            sub_endpoint=model.sub_endpoint,
            configuration=model.configuration or {},
            location=location,
            contact=contact,
        )

    async def get_by_id(self, service_id: int) -> Optional[CatalogService]:
        stmt = (
            select(ServicioModel)
            .options(selectinload(ServicioModel.categoria))
            .where(ServicioModel.id == service_id)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def list_by_establishment(
        self, establishment_id: int, limit: Optional[int] = None
    ) -> list[CatalogService]:
        stmt = (
            select(ServicioModel)
            .options(selectinload(ServicioModel.categoria))
            .where(
                ServicioModel.establishment_id == establishment_id,
                ServicioModel.activo.is_(True),
            )
            .order_by(ServicioModel.nombre.asc())
        )
        if limit is not None and limit > 0:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]
