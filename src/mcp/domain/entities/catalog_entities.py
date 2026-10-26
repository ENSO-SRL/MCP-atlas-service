from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time, timedelta
from typing import Optional

from src.mcp.domain.enums.mcp_enums import RuleType
from src.mcp.domain.value_objects.establishment_vo import ContactInfo, LocationAddress
from src.shared.domain.base import Entity


@dataclass
class Establishment(Entity[int]):
    """
    Entidad Establecimiento, mapeada sobre la tabla 'establishments' de ATLAS-BACKEND.
    Representa una sede física o club deportivo con sus reglas operativas.
    """
    name: str = ""
    code: str = ""
    description: Optional[str] = None
    is_active: bool = True
    has_credentials: bool = True
    rule_type: Optional[RuleType] = None
    opening_hour: Optional[time] = None
    closing_hour: Optional[time] = None
    location: LocationAddress = field(default_factory=LocationAddress)
    contact: ContactInfo = field(default_factory=ContactInfo)
    category_name: Optional[str] = None
    configuration: dict = field(default_factory=dict)

    def is_date_allowed(self, target_date: date, reference_date: Optional[date] = None) -> bool:
        """
        Evalúa si la fecha consultada cumple con la regla de antelación del establecimiento (rule_type).
        """
        today = reference_date or date.today()
        if target_date < today:
            return False

        if self.rule_type == RuleType.ONLY_TODAY:
            return target_date == today
        elif self.rule_type == RuleType.TODAY_AND_TOMORROW:
            return target_date in (today, today + timedelta(days=1))
        
        # RuleType.HOURS_RANGE u otros permiten cualquier fecha futura dentro de su rango
        return True

    def is_time_within_hours(self, target_time: time) -> bool:
        """Verifica si un horario se encuentra dentro de las horas de operación del club."""
        if self.opening_hour and target_time < self.opening_hour:
            return False
        if self.closing_hour and target_time > self.closing_hour:
            return False
        return True


@dataclass
class CatalogService(Entity[int]):
    """
    Entidad CatalogService, mapeada sobre la tabla 'servicios' de ATLAS-BACKEND.
    Representa un deporte o servicio específico (ej. Cancha de Pádel 1, Tenis Arcilla).
    """
    establishment_id: int = 0
    name: str = ""
    category_name: str = "GENERAL"
    description: Optional[str] = None
    is_active: bool = True
    has_credentials: bool = True
    combo_code: Optional[str] = None
    sub_endpoint: Optional[str] = None
    configuration: dict = field(default_factory=dict)
