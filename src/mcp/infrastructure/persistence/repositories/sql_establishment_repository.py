from __future__ import annotations

from typing import Optional
from sqlalchemy import String, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.mcp.domain.entities.catalog_entities import Establishment
from src.mcp.domain.enums.mcp_enums import RuleType
from src.mcp.domain.ports.mcp_ports import IEstablishmentRepository
from src.mcp.domain.value_objects.establishment_vo import ContactInfo, LocationAddress
from src.mcp.infrastructure.persistence.models.catalog_models import (
    CategoriaServicioModel,
    EstablishmentCategoryModel,
    EstablishmentModel,
    ServicioModel,
)


class SqlEstablishmentRepository(IEstablishmentRepository):
    """
    Implementación SQL del puerto IEstablishmentRepository.
    Consulta la réplica local de 'establishments' en ATLAS-BACKEND de solo lectura.
    Soporta búsqueda unificada con UNION ALL integrando establecimientos regulares
    y servicios físicos bajo pasarelas con paginación determinista (LIMIT/OFFSET).
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
            has_scheduler=bool(model.has_scheduler) if model.has_scheduler is not None else False,
            rule_type=rule_type,
            opening_hour=model.opening_hour,
            closing_hour=model.closing_hour,
            location=location,
            contact=contact,
            category_name=category_name,
            configuration=model.configuration or {},
            is_service=False,
        )

    async def search(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        zone: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Establishment]:
        """
        Búsqueda unificada paginada:
        1. Establecimientos activos que NO pertenezcan a la categoría 'Pasarelas' (is_service=False).
        2. Servicios activos pertenecientes a pasarelas activas (is_service=True).
        Ambos se combinan mediante UNION ALL para garantizar ordenamiento global alfabético
        y paginación determinista sin saltos entre páginas.
        """
        # =====================================================================
        # BLOQUE 1: Establecimientos regulares (excluyendo 'Pasarelas')
        # =====================================================================
        stmt_est = (
            select(
                EstablishmentModel.id.label("id"),
                EstablishmentModel.name.label("name"),
                EstablishmentModel.code.label("code"),
                EstablishmentCategoryModel.name.label("category_name"),
                EstablishmentModel.city.label("city"),
                EstablishmentModel.sector.label("sector"),
                EstablishmentModel.street.label("street"),
                EstablishmentModel.building_number.label("building_number"),
                EstablishmentModel.postal_code.label("postal_code"),
                EstablishmentModel.opening_hour.label("opening_hour"),
                EstablishmentModel.closing_hour.label("closing_hour"),
                EstablishmentModel.rule_type.label("rule_type"),
                literal(False).label("is_service"),
            )
            .select_from(EstablishmentModel)
            .outerjoin(
                EstablishmentCategoryModel,
                EstablishmentModel.category_id == EstablishmentCategoryModel.id,
            )
            .where(
                EstablishmentModel.is_active.is_(True),
                or_(
                    EstablishmentCategoryModel.name.is_(None),
                    func.lower(EstablishmentCategoryModel.name) != "pasarelas",
                ),
            )
        )

        if query:
            clean_query = f"%{query.strip()}%"
            stmt_est = stmt_est.where(
                or_(
                    EstablishmentModel.name.ilike(clean_query),
                    EstablishmentModel.description.ilike(clean_query),
                )
            )

        if category:
            clean_cat = f"%{category.strip()}%"
            stmt_est = stmt_est.where(EstablishmentCategoryModel.name.ilike(clean_cat))

        if zone:
            clean_zone = f"%{zone.strip()}%"
            stmt_est = stmt_est.where(
                or_(
                    EstablishmentModel.city.ilike(clean_zone),
                    EstablishmentModel.sector.ilike(clean_zone),
                    EstablishmentModel.state_province.ilike(clean_zone),
                )
            )

        # =====================================================================
        # BLOQUE 2: Servicios físicos bajo establecimientos pasarela
        # =====================================================================
        service_code = func.coalesce(
            ServicioModel.combo_code,
            func.concat("SVC-", func.cast(ServicioModel.id, String)),
        )
        service_city = func.coalesce(ServicioModel.city, EstablishmentModel.city)
        service_sector = func.coalesce(ServicioModel.sector, EstablishmentModel.sector)
        service_street = func.coalesce(ServicioModel.street, EstablishmentModel.street)
        service_building_number = func.coalesce(
            ServicioModel.building_number, EstablishmentModel.building_number
        )
        service_postal_code = func.coalesce(
            ServicioModel.postal_code, EstablishmentModel.postal_code
        )

        stmt_svc = (
            select(
                ServicioModel.id.label("id"),
                ServicioModel.nombre.label("name"),
                service_code.label("code"),
                CategoriaServicioModel.nombre.label("category_name"),
                service_city.label("city"),
                service_sector.label("sector"),
                service_street.label("street"),
                service_building_number.label("building_number"),
                service_postal_code.label("postal_code"),
                EstablishmentModel.opening_hour.label("opening_hour"),
                EstablishmentModel.closing_hour.label("closing_hour"),
                EstablishmentModel.rule_type.label("rule_type"),
                literal(True).label("is_service"),
            )
            .select_from(ServicioModel)
            .join(
                EstablishmentModel,
                ServicioModel.establishment_id == EstablishmentModel.id,
            )
            .join(
                EstablishmentCategoryModel,
                EstablishmentModel.category_id == EstablishmentCategoryModel.id,
            )
            .outerjoin(
                CategoriaServicioModel,
                ServicioModel.categoria_id == CategoriaServicioModel.id,
            )
            .where(
                ServicioModel.activo.is_(True),
                EstablishmentModel.is_active.is_(True),
                func.lower(EstablishmentCategoryModel.name) == "pasarelas",
            )
        )

        if query:
            clean_query = f"%{query.strip()}%"
            stmt_svc = stmt_svc.where(
                or_(
                    ServicioModel.nombre.ilike(clean_query),
                    ServicioModel.descripcion.ilike(clean_query),
                )
            )

        if category:
            clean_cat = f"%{category.strip()}%"
            # Si buscan por deporte/categoría, coincide con la categoría del servicio o de la pasarela
            stmt_svc = stmt_svc.where(
                or_(
                    CategoriaServicioModel.nombre.ilike(clean_cat),
                    EstablishmentCategoryModel.name.ilike(clean_cat),
                )
            )

        if zone:
            clean_zone = f"%{zone.strip()}%"
            stmt_svc = stmt_svc.where(
                or_(
                    ServicioModel.city.ilike(clean_zone),
                    ServicioModel.sector.ilike(clean_zone),
                    EstablishmentModel.city.ilike(clean_zone),
                    EstablishmentModel.sector.ilike(clean_zone),
                )
            )

        # =====================================================================
        # UNIÓN Y PAGINACIÓN DETERMINISTA
        # =====================================================================
        unified = union_all(stmt_est, stmt_svc).subquery("unified_catalog")
        final_stmt = (
            select(unified)
            .order_by(unified.c.name.asc())
            .limit(limit)
            .offset(offset)
        )

        result = await self._session.execute(final_stmt)
        rows = result.mappings().all()

        items: list[Establishment] = []
        for row in rows:
            rule_type: Optional[RuleType] = None
            raw_rule = row.get("rule_type")
            if raw_rule:
                try:
                    rule_type = RuleType(raw_rule)
                except ValueError:
                    rule_type = None

            location = LocationAddress(
                city=row.get("city"),
                sector=row.get("sector"),
                street=row.get("street"),
                building_number=row.get("building_number"),
                postal_code=row.get("postal_code"),
            )

            items.append(
                Establishment(
                    id=int(row["id"]),
                    name=str(row["name"]),
                    code=str(row["code"]),
                    rule_type=rule_type,
                    opening_hour=row.get("opening_hour"),
                    closing_hour=row.get("closing_hour"),
                    location=location,
                    category_name=row.get("category_name"),
                    is_service=bool(row.get("is_service", False)),
                )
            )

        return items

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
