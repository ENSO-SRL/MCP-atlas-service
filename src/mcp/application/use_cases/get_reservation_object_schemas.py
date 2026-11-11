from __future__ import annotations

from src.mcp.application.dto.reservation_object_dtos import (
    GetReservationObjectSchemasQueryDTO,
    ReservationObjectSchemaDTO,
    ReservationObjectSchemasResponseDTO,
    SchemaFieldDTO,
)
from src.mcp.domain.ports.mcp_ports import IReservationObjectRepository


class GetReservationObjectSchemasUseCase:
    """
    Caso de uso: Consultar los esquemas de Reservation Objects asociados a un servicio.
    Permite a Claude o al cliente conocer qué tipo de objetos persistentes (ej. 'vvautos_taller:vehiculo')
    requiere el servicio, qué campos son obligatorios y cuáles son de alta variación (high_variance_flag).
    """

    def __init__(self, res_obj_repo: IReservationObjectRepository):
        self._repo = res_obj_repo

    async def execute(
        self, query: GetReservationObjectSchemasQueryDTO
    ) -> ReservationObjectSchemasResponseDTO:
        schemas = await self._repo.get_schemas_by_service_id(query.service_id)

        schema_dtos: list[ReservationObjectSchemaDTO] = []
        for s in schemas:
            field_dtos = [
                SchemaFieldDTO(
                    field_name=f.field_name,
                    data_type=f.data_type,
                    is_required=f.is_required,
                    high_variance_flag=f.high_variance_flag,
                    description=f.description,
                    validation_rules=f.validation_rules,
                )
                for f in s.schema_fields
            ]
            schema_dtos.append(
                ReservationObjectSchemaDTO(
                    schema_id=s.id,
                    schema_header=s.schema_header,
                    service_id=s.service_id,
                    establishment_id=s.establishment_id,
                    section_name=s.section_name,
                    schema_fields=field_dtos,
                )
            )

        return ReservationObjectSchemasResponseDTO(
            service_id=query.service_id,
            schemas=schema_dtos,
        )

