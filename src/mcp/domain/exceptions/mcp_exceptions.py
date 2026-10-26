from src.mcp.domain.enums.mcp_enums import BookingStatus


class McpDomainException(Exception):
    """Excepción base para errores de dominio en el módulo MCP."""
    pass


class InvalidStateTransitionException(McpDomainException):
    def __init__(self, current_status: BookingStatus, target_status: BookingStatus):
        super().__init__(
            f"Transición de estado inválida: no es posible pasar de '{current_status.value}' a '{target_status.value}'."
        )
        self.current_status = current_status
        self.target_status = target_status


class SlotTokenExpiredException(McpDomainException):
    def __init__(self, message: str = "El token de oferta del slot ha expirado. Consulta disponibilidad nuevamente."):
        super().__init__(message)


class SlotTokenInvalidException(McpDomainException):
    def __init__(self, message: str = "El token de slot es inválido, manipulado o no pertenece al usuario autenticado."):
        super().__init__(message)


class IdempotencyConflictException(McpDomainException):
    def __init__(self, message: str = "Conflicto de idempotencia: misma idempotency_key enviada con distinto payload."):
        super().__init__(message)


class BookingRuleViolationException(McpDomainException):
    def __init__(self, message: str):
        super().__init__(message)


class ContractValidationException(McpDomainException):
    def __init__(self, message: str):
        super().__init__(message)


class MissingDimensionDependencyException(McpDomainException):
    def __init__(self, missing_dependencies: list[str]):
        super().__init__(f"Faltan dimensiones requeridas por dependencias: {missing_dependencies}")
        self.missing_dependencies = missing_dependencies
