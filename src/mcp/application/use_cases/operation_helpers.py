from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("mcp.application.operations")

GENERIC_INTERNAL_ERROR_MESSAGE = (
    "El servicio que está solicitando actualmente se encuentra inaccesible debido a dificultades técnicas."
)


def resolve_operation_error(
    payload: dict[str, Any],
    operation_id: str,
) -> tuple[str, str]:
    """
    Interpreta el payload de error proveniente del backend/facade upstream:
    - Si result_type == "internal_error": Logea el error técnico real y devuelve un mensaje genérico al usuario.
    - Si result_type == "error_to_user": Devuelve el mensaje descriptivo en 'detail' (o 'error').
    - Fallback: Si no coincide con ninguno, devuelve 'detail'/'error' si existe o el mensaje genérico.

    Retorna una tupla: (mensaje_para_usuario, result_type_normalizado).
    """
    result_type = str(payload.get("result_type") or "").strip()
    detail = payload.get("detail") or payload.get("error")

    if result_type == "internal_error":
        logger.error(
            "Operación asíncrona '%s' falló en backend upstream con internal_error: %s",
            operation_id,
            detail or "Detalle no proporcionado",
        )
        return GENERIC_INTERNAL_ERROR_MESSAGE, "internal_error"

    if result_type == "error_to_user":
        user_msg = (
            str(detail).strip()
            if detail
            else "La operación no pudo completarse debido a un error en el servicio."
        )
        return user_msg, "error_to_user"

    # Fallback para respuestas de error sin result_type explícito o con valores personalizados
    if detail:
        return str(detail).strip(), result_type or "failed"

    return GENERIC_INTERNAL_ERROR_MESSAGE, result_type or "internal_error"

