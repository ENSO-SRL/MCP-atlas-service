from __future__ import annotations

from typing import Optional

from src.mcp.application.dto.reservation_object_dtos import (
    GetUserReservationObjectsQueryDTO,
    ReservationObjectDTO,
    UserReservationObjectsResponseDTO,
)
from src.mcp.domain.exceptions.mcp_exceptions import (
    ContractValidationException,
    EntityNotFoundException,
)
from src.mcp.domain.ports.mcp_ports import IReservationObjectRepository


class GetUserReservationObjectsUseCase:
    """
    Caso de uso: Consultar los objetos de reserva persistentes guardados del usuario autenticado.
    Recibe el 'schema_header' (ej. 'vvautos_taller:vehiculo'), resuelve el número de teléfono del usuario
    y retorna la lista de objetos activos con sus identificadores (object_id) y datos actuales para
    reutilizarlos o modificarlos en una reserva bajo el patrón Resolve or Create.
    """

    def __init__(self, res_obj_repo: IReservationObjectRepository):
        self._repo = res_obj_repo

    async def execute(
        self, query: GetUserReservationObjectsQueryDTO
    ) -> UserReservationObjectsResponseDTO:
        clean_header = (query.schema_header or "").strip()
        if not clean_header:
            raise ContractValidationException(
                "Debe proporcionar 'schema_header' (ej. 'vvautos_taller:vehiculo') para consultar los objetos."
            )

        # 1. Obtener la definición del esquema
        schema = await self._repo.get_schema_by_header(clean_header)
        if not schema:
            raise EntityNotFoundException(
                f"No se encontró el esquema de objeto de reserva '{clean_header}'."
            )

        # 2. Resolver el teléfono del usuario
        user_phone = (query.user_phone or "").strip() or None
        if not user_phone and query.user_uuid:
            user_phone = await self._repo.get_user_phone_by_uuid(query.user_uuid)

        # 3. Si no hay teléfono asociado al usuario, retornar lista vacía
        if not user_phone:
            return UserReservationObjectsResponseDTO(
                schema_header=schema.schema_header,
                section_name=schema.section_name,
                user_phone=None,
                objects=[],
            )

        # 4. Consultar objetos guardados del usuario para ese esquema
        objects = await self._repo.get_objects_by_schema_and_phone(schema.id, user_phone)

        object_dtos = [
            ReservationObjectDTO(
                id=o.id,
                schema_id=o.schema_id,
                object_alias=o.object_alias,
                payload=o.object_payload,
                created_at=o.created_at.isoformat() if o.created_at else None,
                updated_at=o.updated_at.isoformat() if o.updated_at else None,
            )
            for o in objects
        ]

        return UserReservationObjectsResponseDTO(
            schema_header=schema.schema_header,
            section_name=schema.section_name,
            user_phone=user_phone,
            objects=object_dtos,
        )

