from __future__ import annotations

import time
from typing import Any
import jwt
from fastapi import Request, Response

from src.shared.config.settings import get_settings

SESSION_COOKIE_NAME = "atlas_oauth_session"
SESSION_COOKIE_MAX_AGE = 3600  # 1 hora


def create_session_token(user_uuid: str, email: str, name: str) -> str:
    """Genera un JWT firmado para la cookie de sesión del usuario en el flujo OAuth."""
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": str(user_uuid),
        "email": email,
        "name": name,
        "purpose": "oauth_login_session",
        "iat": now,
        "exp": now + SESSION_COOKIE_MAX_AGE,
    }
    return jwt.encode(payload, settings.OAUTH_JWT_SECRET_KEY, algorithm=settings.OAUTH_JWT_ALGORITHM)


def set_session_cookie(response: Response, user_uuid: str, email: str, name: str) -> None:
    """Configura la cookie HttpOnly de sesión en la respuesta HTTP."""
    token = create_session_token(user_uuid, email, name)
    settings = get_settings()
    is_prod = settings.ENVIRONMENT.lower() in ("production", "prod")

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=is_prod,
        path="/",
    )


def get_session_user(request: Request) -> dict[str, Any] | None:
    """Lee y valida la cookie HttpOnly de sesión, retornando los datos del usuario si es válida."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.OAUTH_JWT_SECRET_KEY,
            algorithms=[settings.OAUTH_JWT_ALGORITHM],
        )
        if payload.get("purpose") != "oauth_login_session":
            return None
        return payload
    except (jwt.PyJWTError, Exception):
        return None


def clear_session_cookie(response: Response) -> None:
    """Elimina la cookie de sesión."""
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
