from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from src.mcp.domain.enums.mcp_enums import CalculationBasis
from src.mcp.domain.value_objects.booking_vo import PriceEstimate
from src.shared.domain.base import Entity


@dataclass
class ServicePriceRule(Entity[UUID]):
    """
    Regla de precio estructurada para un servicio.
    Evalúa si aplica para un horario y cantidad de personas, calculando el estimado informativo.
    """
    id: UUID = field(default_factory=uuid4)
    service_id: int = 0
    label: str = "Tarifa estándar"
    weekdays: list[int] = field(default_factory=lambda: [1, 2, 3, 4, 5, 6, 7])
    start_minute: int = 0      # Minutos desde medianoche (ej. 480 = 08:00)
    end_minute: int = 1440     # Minutos desde medianoche (ej. 1320 = 22:00)
    valid_from: date = field(default_factory=date.today)
    valid_to: Optional[date] = None
    min_party_size: Optional[int] = None
    max_party_size: Optional[int] = None
    min_duration_min: Optional[int] = None
    max_duration_min: Optional[int] = None
    dimension_conditions: Optional[dict[str, Any]] = None
    amount: Decimal = Decimal("0.00")
    currency: str = "DOP"
    calculation_basis: CalculationBasis = CalculationBasis.PER_BOOKING
    is_starting_price: bool = False
    priority: int = 0

    def is_applicable(
        self,
        target_datetime: datetime,
        party_size: int = 1,
        duration_minutes: Optional[int] = None,
        applied_filters: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Determina si esta regla aplica según vigencia, día, horario, personas, duración y filtros de dimensión."""
        target_date = target_datetime.date()

        # 1. Vigencia por fechas
        if target_date < self.valid_from:
            return False
        if self.valid_to and target_date > self.valid_to:
            return False

        # 2. Día de la semana (1 = Lunes, 7 = Domingo)
        if target_datetime.isoweekday() not in self.weekdays:
            return False

        # 3. Franja horaria en minutos desde medianoche
        minute_of_day = target_datetime.hour * 60 + target_datetime.minute
        if minute_of_day < self.start_minute or minute_of_day >= self.end_minute:
            return False

        # 4. Cantidad de personas
        if self.min_party_size and party_size < self.min_party_size:
            return False
        if self.max_party_size and party_size > self.max_party_size:
            return False

        # 5. Duración (si aplica)
        if duration_minutes:
            if self.min_duration_min and duration_minutes < self.min_duration_min:
                return False
            if self.max_duration_min and duration_minutes > self.max_duration_min:
                return False

        # 6. Condiciones de dimensión (ej. course="championsship")
        if self.dimension_conditions:
            if not applied_filters:
                return False
            for cond_key, cond_val in self.dimension_conditions.items():
                if applied_filters.get(cond_key) != cond_val:
                    return False

        return True

    def calculate_estimate(self, party_size: int = 1) -> PriceEstimate:
        """Calcula el monto del estimado informativo."""
        if self.calculation_basis == CalculationBasis.PER_PERSON:
            total_amount = self.amount * Decimal(party_size)
        else:
            total_amount = self.amount

        return PriceEstimate(
            amount=total_amount,
            currency=self.currency,
            basis=self.calculation_basis,
            label=self.label,
            rule_id=self.id,
            informative=True,
        )
