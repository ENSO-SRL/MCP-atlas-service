from enum import Enum


class BookingStatus(str, Enum):
    """Estados de la máquina de estados de solicitudes de reserva."""
    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"


class AvailabilityPattern(str, Enum):
    """Patrón de disponibilidad del servicio."""
    SLOT_OBJECT = "slot_object"                 # Cancha, mesa, hoyos (objeto reservable)
    APPOINTMENT_RESOURCE = "appointment_resource" # Taller mecánico, veterinaria (profesional/recurso)
    SESSION_SEATS = "session_seats"               # Cine, teatro (butacas o aforo)


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
