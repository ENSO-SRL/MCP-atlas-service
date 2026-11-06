from enum import Enum


class BookingStatus(str, Enum):
    """Estados de la máquina de estados de solicitudes de reserva."""
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    REQUIRES_CONFIRMATION = "requires_confirmation"


class NoticeType(str, Enum):
    """Tipos de alertas o avisos de confirmación en una reserva."""
    PRICE_DISCREPANCY = "price_discrepancy"         # Ajuste en la tarifa respecto al estimado
    SCHEDULE_SHIFT = "schedule_shift"               # Desfase sustancial de horario (> 1 hora) propuesto por la sede
    RESOURCE_REASSIGNED = "resource_reassigned"     # Cambio de cancha, pista o recurso asignado
    GENERAL_NOTICE = "general_notice"               # Aviso operativo general que requiere aprobación


class NoticeStatus(str, Enum):
    """Estado de resolución de un aviso de reserva."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class AvailabilityPattern(str, Enum):
    """Patrón de disponibilidad del servicio."""
    SLOT_OBJECT = "slot_object"                 # Cancha, mesa, hoyos (objeto reservable)
    APPOINTMENT_RESOURCE = "appointment_resource" # Taller mecánico (profesional/recurso con hora fija)
    SESSION_SEATS = "session_seats"               # Cine, teatro (butacas o aforo)
    ON_DEMAND_REQUEST = "on_demand_request"       # Veterinaria, presupuestos, urgencias (sin slots fijos)


class RuleType(str, Enum):
    """Reglas de antelación para reservas según el establecimiento en ATLAS-BACKEND."""
    ONLY_TODAY = "only_today"
    TODAY_AND_TOMORROW = "today_and_tomorrow"
    HOURS_RANGE = "hours_range"


class DimensionValuesSource(str, Enum):
    """Origen de las opciones para una dimensión."""
    INLINE = "inline"                   # En el propio contrato
    SLOTS = "slots"                     # Atributo de los slots ya consultados
    SEPARATE_QUERY = "separate_query"   # Consulta aparte a través de Disponibilidad


class DimensionApplyMode(str, Enum):
    """Estrategia de aplicación del filtro de una dimensión."""
    POST_FILTER = "post_filter"         # Filtrado local sin llamada upstream
    UPSTREAM_PARAM = "upstream_param"   # Consulta upstream con parámetro adicional


class PricingMode(str, Enum):
    """Modo de precios informativos del servicio."""
    STRUCTURED = "structured"           # Reglas evaluables por horario y personas
    TEXT_ONLY = "text_only"             # Información en texto libre
    NONE = "none"                       # Sin precio de referencia (cotiza el negocio)


class CalculationBasis(str, Enum):
    """Base de cálculo de una regla de tarifa."""
    PER_BOOKING = "per_booking"
    PER_PERSON = "per_person"


class ContractStatus(str, Enum):
    """Estado del ciclo de vida de un contrato de servicio."""
    DRAFT = "draft"
    PUBLISHED = "published"
    RETIRED = "retired"
