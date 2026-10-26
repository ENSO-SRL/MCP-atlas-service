from __future__ import annotations

from src.mcp.application.dto.contract_dtos import (
    ContractDimensionProjectionDTO,
    DimensionOptionDTO,
    GetServiceContractQueryDTO,
    ServiceContractDTO,
)
from src.mcp.domain.enums.mcp_enums import DimensionValuesSource
from src.mcp.domain.exceptions.mcp_exceptions import EntityNotFoundException
from src.mcp.domain.ports.mcp_ports import (
    ICatalogServiceRepository,
    IContractRepository,
)


class GetServiceContractUseCase:
    """
    Caso de uso: Obtener el contrato dinámico de un servicio (get_service_contract).
    Expone a Claude el patrón de disponibilidad, las dimensiones dinámicas requeridas,
    el JSON Schema de campos de reserva y las políticas de pago/cancelación.
    """

    def __init__(
        self,
        catalog_service_repo: ICatalogServiceRepository,
        contract_repo: IContractRepository,
    ):
        self._catalog_service_repo = catalog_service_repo
        self._contract_repo = contract_repo

    async def execute(self, query: GetServiceContractQueryDTO) -> ServiceContractDTO:
        # 1. Verificar existencia del servicio en catálogo
        svc = await self._catalog_service_repo.get_by_id(query.service_id)
        if not svc:
            raise EntityNotFoundException(
                f"Servicio con id {query.service_id} no encontrado en catálogo."
            )

        # 2. Obtener el contrato activo publicado
        contract = await self._contract_repo.get_active_by_service_id(query.service_id)
        if not contract:
            raise EntityNotFoundException(
                f"El servicio '{svc.name}' (id: {query.service_id}) no tiene un contrato publicado para MCP."
            )

        # 3. Construir proyección pública de dimensiones ordenadas por posición
        dimension_dtos: list[ContractDimensionProjectionDTO] = []
        for dim in sorted(contract.dimensions, key=lambda d: d.position):
            inline_options: list[DimensionOptionDTO] | None = None
            if dim.values_source == DimensionValuesSource.INLINE and dim.inline_values:
                inline_options = [
                    DimensionOptionDTO(
                        value_key=v["key"] if "key" in v else v.get("value_key", ""),
                        label=v.get("label", ""),
                        description=v.get("description"),
                        position=v.get("position", 0),
                    )
                    for v in dim.inline_values
                ]

            dimension_dtos.append(
                ContractDimensionProjectionDTO(
                    key=dim.key,
                    label=dim.label,
                    description=dim.description,
                    values_source=dim.values_source.value,
                    apply_mode=dim.apply_mode.value,
                    required=dim.required,
                    allows_any=dim.allows_any,
                    reports_counts=dim.reports_counts,
                    depends_on=dim.depends_on,
                    values=inline_options,
                )
            )

        published_date_str = (
            contract.published_at.strftime("%Y-%m-%d")
            if contract.published_at
            else "v"
        )
        version_label = f"{published_date_str}.{contract.version_no}"

        return ServiceContractDTO(
            service_id=contract.service_id,
            pattern=contract.pattern.value,
            contract_version=version_label,
            contract_version_id=contract.id,
            availability_dimensions=dimension_dtos,
            booking_fields=contract.booking_fields_schema,
            payment_policy=contract.payment_policy,
            cancellation_policy=contract.cancellation_policy,
            request_expires_in_seconds=contract.request_ttl_seconds,
        )
