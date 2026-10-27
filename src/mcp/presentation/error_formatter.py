from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Coroutine

from src.mcp.domain.exceptions.mcp_exceptions import (
    BookingRuleViolationException,
    ContractValidationException,
    EntityNotFoundException,
    IdempotencyConflictException,
    InvalidStateTransitionException,
    McpDomainException,
    MissingDimensionDependencyException,
    SlotTokenExpiredException,
    SlotTokenInvalidException,
)
from src.mcp.presentation.auth_context import (
    AuthenticationRequiredException,
    ForbiddenScopeException,
)

logger = logging.getLogger("mcp.presentation.error_formatter")


def handle_mcp_errors(
    fn: Callable[..., Coroutine[Any, Any, Any]]
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """
    Decorador defensivo para herramientas MCP.
    Captura excepciones de dominio y autenticación, transformándolas en respuestas
    estructuradas comprensibles para Claude y los clientes MCP sin interrumpir la sesión.
    """
    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except (AuthenticationRequiredException, ForbiddenScopeException) as exc:
            return {
                "error": True,
                "error_type": exc.__class__.__name__,
                "message": str(exc),
                "resolution": "Verifica tu inicio de sesión OAuth en Claude y que el conector cuente con los permisos necesarios.",
            }
        except EntityNotFoundException as exc:
            return {
                "error": True,
                "error_type": "EntityNotFoundException",
                "message": str(exc),
                "resolution": "Verifica que el identificador suministrado corresponda a un registro existente y pertenezca a tu cuenta.",
            }
        except BookingRuleViolationException as exc:
            return {
                "error": True,
                "error_type": "BookingRuleViolationException",
                "message": str(exc),
                "resolution": "El horario o fecha seleccionada no cumple las reglas del establecimiento o ya fue tomado por otro usuario. Por favor consulta la disponibilidad nuevamente.",
            }
        except ContractValidationException as exc:
            return {
                "error": True,
                "error_type": "ContractValidationException",
                "message": str(exc),
                "resolution": "Los campos enviados no coinciden con el contrato del servicio. Consulta el contrato con get_service_contract.",
            }
        except (SlotTokenExpiredException, SlotTokenInvalidException) as exc:
            return {
                "error": True,
                "error_type": exc.__class__.__name__,
                "message": str(exc),
                "resolution": "El token de slot expiró o no es válido para este usuario. Llama a check_availability para obtener un token nuevo y vigente.",
            }
        except IdempotencyConflictException as exc:
            return {
                "error": True,
                "error_type": "IdempotencyConflictException",
                "message": str(exc),
                "resolution": "Se ha utilizado la misma idempotency_key con un contenido diferente. Utiliza una clave nueva si deseas hacer otra reserva.",
            }
        except InvalidStateTransitionException as exc:
            return {
                "error": True,
                "error_type": "InvalidStateTransitionException",
                "message": str(exc),
                "resolution": "La reserva se encuentra en un estado que no permite ejecutar la acción solicitada.",
            }
        except MissingDimensionDependencyException as exc:
            return {
                "error": True,
                "error_type": "MissingDimensionDependencyException",
                "message": str(exc),
                "missing_dependencies": exc.missing_dependencies,
                "resolution": f"Debes especificar primero las dimensiones precedentes en context: {exc.missing_dependencies}.",
            }
        except McpDomainException as exc:
            return {
                "error": True,
                "error_type": exc.__class__.__name__,
                "message": str(exc),
            }
        except Exception as exc:
            logger.exception("Error inesperado en herramienta MCP: %s", exc)
            return {
                "error": True,
                "error_type": "UnexpectedInternalError",
                "message": f"Ocurrió un error inesperado al procesar la solicitud: {exc}",
            }

    return wrapper
