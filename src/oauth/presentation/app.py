from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Form, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

logger = logging.getLogger("oauth.server")

from src.oauth.application.dto.oauth_dtos import (
    AuthorizeRequestDTO,
    RevokeTokenRequestDTO,
    TokenExchangeRequestDTO,
    TokenRefreshRequestDTO,
    UserLoginRequestDTO,
)
from src.oauth.application.use_cases.authenticate_user import AuthenticateUserUseCase
from src.oauth.application.use_cases.exchange_token import ExchangeTokenUseCase
from src.oauth.application.use_cases.generate_authorization_code import (
    GenerateAuthorizationCodeUseCase,
)
from src.oauth.application.use_cases.get_user_info import GetUserInfoUseCase
from src.oauth.application.use_cases.refresh_token import RefreshTokenUseCase
from src.oauth.application.use_cases.revoke_token import RevokeTokenUseCase
from src.oauth.domain.exceptions.auth_exceptions import (
    AuthDomainException,
    ExpiredAuthorizationCodeException,
    InvalidClientException,
    InvalidCredentialsException,
    InvalidPKCEException,
    InvalidRedirectUriException,
    InvalidRefreshTokenException,
    UserInactiveException,
)
from src.oauth.domain.ports.i_oauth_client_repository import IOAuthClientRepository
from src.oauth.domain.ports.i_security_ports import ITokenIssuer
from src.oauth.presentation.dependencies import (
    get_authenticate_user_use_case,
    get_exchange_token_use_case,
    get_generate_authorization_code_use_case,
    get_oauth_client_repository,
    get_refresh_token_use_case,
    get_revoke_token_use_case,
    get_token_issuer,
    get_user_info_use_case,
)
from src.oauth.presentation.session_manager import (
    clear_session_cookie,
    get_session_user,
    set_session_cookie,
)
from src.shared.config.settings import get_settings

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

SCOPE_DESCRIPTIONS = {
    "bookings:read": {
        "title": "Consultar disponibilidad y reservas",
        "description": "Ver horarios disponibles, pistas y el estado de tus reservas de golf en tiempo real.",
    },
    "bookings:write": {
        "title": "Gestionar reservas a tu nombre",
        "description": "Crear, confirmar o cancelar reservas directamente a través del asistente.",
    },
    "profile": {
        "title": "Acceder a tu perfil básico",
        "description": "Ver tu nombre, email y teléfono para asociar las reservas a tu cuenta.",
    },
}


def _get_scopes_info(scope_string: str) -> list[dict[str, str]]:
    scopes = [s for s in scope_string.split() if s]
    info_list = []
    for s in scopes:
        if s in SCOPE_DESCRIPTIONS:
            info_list.append(SCOPE_DESCRIPTIONS[s])
        else:
            info_list.append({
                "title": f"Permiso '{s}'",
                "description": f"Acceso requerido para la operación: {s}",
            })
    return info_list


def _extract_basic_auth(authorization: str | None) -> tuple[str | None, str | None]:
    if not authorization or not authorization.startswith("Basic "):
        return None, None
    try:
        encoded = authorization.split(" ", 1)[1]
        decoded = base64.b64decode(encoded).decode("utf-8")
        client_id, client_secret = decoded.split(":", 1)
        return client_id, client_secret
    except Exception:
        return None, None


oauth_router = APIRouter(tags=["OAuth 2.0"])


# =========================================================================
# RFC 8414 & OpenID Connect Discovery Metadata
# =========================================================================
@oauth_router.get("/.well-known/oauth-authorization-server")
@oauth_router.get("/.well-known/openid-configuration")
async def oauth_authorization_server_metadata():
    """Retorna los metadatos de configuración del servidor de autorización OAuth 2.0."""
    settings = get_settings()
    issuer = settings.OAUTH_ISSUER.rstrip("/")
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/oauth/authorize",
        "token_endpoint": f"{issuer}/oauth/token",
        "revocation_endpoint": f"{issuer}/oauth/revoke",
        "userinfo_endpoint": f"{issuer}/oauth/userinfo",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": ["bookings:read", "bookings:write", "profile"],
    }


# =========================================================================
# RFC 6749 Authorization Endpoint: GET /oauth/authorize
# =========================================================================
@oauth_router.get("/oauth/authorize", response_class=HTMLResponse)
async def authorize(
    request: Request,
    client_id: Annotated[str, Query()],
    redirect_uri: Annotated[str, Query()],
    response_type: Annotated[str, Query()] = "code",
    scope: Annotated[str, Query()] = "bookings:read bookings:write profile",
    state: Annotated[str, Query()] = "",
    code_challenge: Annotated[str, Query()] = "",
    code_challenge_method: Annotated[str, Query()] = "S256",
    client_repo: IOAuthClientRepository = Depends(get_oauth_client_repository),
):
    """Punto de entrada para el flujo de autorización OAuth 2.0 (Login y Consentimiento)."""
    # 1. Validar cliente
    client = await client_repo.get_by_client_id(client_id)
    if not client:
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "error_code": "invalid_client",
                "error_description": "El cliente OAuth especificado no existe o no está registrado.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 2. Validar URI de redirección
    if not client.is_redirect_uri_allowed(redirect_uri):
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "error_code": "invalid_request",
                "error_description": f"La URL de redirección '{redirect_uri}' no está autorizada para este cliente.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 3. Validar response_type
    if response_type != "code":
        sep = "&" if "?" in redirect_uri else "?"
        url = f"{redirect_uri}{sep}error=unsupported_response_type&error_description=Solo+se+admite+response_type=code"
        if state:
            url += f"&state={state}"
        return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)

    # 4. Validar PKCE
    if not code_challenge or code_challenge_method != "S256":
        sep = "&" if "?" in redirect_uri else "?"
        url = f"{redirect_uri}{sep}error=invalid_request&error_description=Se+requiere+PKCE+con+code_challenge_method=S256"
        if state:
            url += f"&state={state}"
        return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)

    # 5. Comprobar si hay sesión activa del usuario
    session_user = get_session_user(request)
    if session_user:
        # El usuario ya inició sesión, mostrar pantalla de consentimiento
        return templates.TemplateResponse(
            request=request,
            name="consent.html",
            context={
                "client_id": client_id,
                "client_name": client.client_name,
                "redirect_uri": redirect_uri,
                "scope": scope,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
                "user_email": session_user.get("email", ""),
                "user_name": session_user.get("name", ""),
                "scopes_info": _get_scopes_info(scope),
            },
        )

    # 6. No hay sesión: mostrar formulario de inicio de sesión con estilo Atlas 100% fiel
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "error_message": None,
        },
    )


# =========================================================================
# Login POST: /oauth/login
# =========================================================================
@oauth_router.post("/oauth/login", response_class=HTMLResponse)
async def login(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    client_id: Annotated[str, Form()],
    redirect_uri: Annotated[str, Form()],
    scope: Annotated[str, Form()] = "bookings:read bookings:write profile",
    state: Annotated[str, Form()] = "",
    code_challenge: Annotated[str, Form()] = "",
    code_challenge_method: Annotated[str, Form()] = "S256",
    auth_use_case: AuthenticateUserUseCase = Depends(get_authenticate_user_use_case),
):
    """Procesa las credenciales del usuario y crea la cookie de sesión."""
    try:
        session_dto = await auth_use_case.execute(UserLoginRequestDTO(email=email, password=password))
    except InvalidCredentialsException:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": scope,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
                "email": email,
                "error_message": "Correo electrónico o contraseña incorrectos.",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    except UserInactiveException:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": scope,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
                "email": email,
                "error_message": "Tu cuenta de usuario no se encuentra activa.",
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )
    except Exception as exc:
        logger.exception("Error inesperado en POST /oauth/login para '%s': %s", email, exc)
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": scope,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
                "email": email,
                "error_message": "Error temporal al iniciar sesión. Intenta más tarde.",
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Redirigir de nuevo a /oauth/authorize preservando los parámetros
    authorize_url = (
        f"/oauth/authorize?client_id={client_id}&redirect_uri={redirect_uri}"
        f"&scope={scope}&state={state}&code_challenge={code_challenge}"
        f"&code_challenge_method={code_challenge_method}"
    )
    response = RedirectResponse(url=authorize_url, status_code=status.HTTP_303_SEE_OTHER)
    set_session_cookie(
        response=response,
        user_uuid=str(session_dto.user_uuid),
        email=session_dto.email,
        name=session_dto.name,
    )
    return response


# =========================================================================
# Consent POST: /oauth/consent
# =========================================================================
@oauth_router.post("/oauth/consent")
async def consent(
    request: Request,
    action: Annotated[str, Form()],
    client_id: Annotated[str, Form()],
    redirect_uri: Annotated[str, Form()],
    scope: Annotated[str, Form()] = "bookings:read bookings:write profile",
    state: Annotated[str, Form()] = "",
    code_challenge: Annotated[str, Form()] = "",
    code_challenge_method: Annotated[str, Form()] = "S256",
    generate_code_use_case: GenerateAuthorizationCodeUseCase = Depends(
        get_generate_authorization_code_use_case
    ),
):
    """Procesa la aprobación o denegación de consentimiento por parte del usuario."""
    # 1. Comprobar sesión
    session_user = get_session_user(request)
    if not session_user:
        authorize_url = (
            f"/oauth/authorize?client_id={client_id}&redirect_uri={redirect_uri}"
            f"&scope={scope}&state={state}&code_challenge={code_challenge}"
            f"&code_challenge_method={code_challenge_method}"
        )
        return RedirectResponse(url=authorize_url, status_code=status.HTTP_303_SEE_OTHER)

    # 2. Si el usuario canceló o denegó el acceso
    if action != "allow":
        sep = "&" if "?" in redirect_uri else "?"
        url = f"{redirect_uri}{sep}error=access_denied&error_description=El+usuario+cancelo+la+autorizacion"
        if state:
            url += f"&state={state}"
        return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)

    # 3. Usuario permitió: generar el código de autorización con PKCE
    user_uuid = UUID(session_user["sub"])
    dto = AuthorizeRequestDTO(
        client_id=client_id,
        redirect_uri=redirect_uri,
        response_type="code",
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        user_uuid=user_uuid,
        scope=scope,
        state=state or None,
    )

    try:
        result = await generate_code_use_case.execute(dto)
        return RedirectResponse(url=result.callback_url, status_code=status.HTTP_302_FOUND)
    except AuthDomainException as exc:
        sep = "&" if "?" in redirect_uri else "?"
        url = f"{redirect_uri}{sep}error=invalid_request&error_description={str(exc)}"
        if state:
            url += f"&state={state}"
        return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


# =========================================================================
# RFC 6749 Token Endpoint: POST /oauth/token
# =========================================================================
@oauth_router.post("/oauth/token")
async def token(
    request: Request,
    grant_type: Annotated[str, Form()] = "",
    code: Annotated[str | None, Form()] = None,
    redirect_uri: Annotated[str | None, Form()] = None,
    client_id: Annotated[str | None, Form()] = None,
    client_secret: Annotated[str | None, Form()] = None,
    code_verifier: Annotated[str | None, Form()] = None,
    refresh_token: Annotated[str | None, Form()] = None,
    scope: Annotated[str | None, Form()] = None,
    authorization: Annotated[str | None, Header()] = None,
    exchange_use_case: ExchangeTokenUseCase = Depends(get_exchange_token_use_case),
    refresh_use_case: RefreshTokenUseCase = Depends(get_refresh_token_use_case),
):
    """Punto de intercambio de tokens OAuth 2.0 (código o refresh token)."""
    # Si viene en cabecera HTTP Basic Auth
    basic_client_id, basic_client_secret = _extract_basic_auth(authorization)
    if basic_client_id:
        client_id = basic_client_id
        client_secret = basic_client_secret

    if not client_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "invalid_client", "error_description": "Falta el parámetro client_id"},
        )

    # 1. Flujo authorization_code
    if grant_type == "authorization_code":
        if not code or not redirect_uri or not code_verifier:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": "invalid_request",
                    "error_description": "Faltan parámetros requeridos: code, redirect_uri o code_verifier",
                },
            )

        dto = TokenExchangeRequestDTO(
            grant_type=grant_type,
            client_id=client_id,
            code=code,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
        )

        try:
            token_response = await exchange_use_case.execute(dto)
            return JSONResponse(status_code=status.HTTP_200_OK, content=token_response.to_dict())
        except (ExpiredAuthorizationCodeException, InvalidPKCEException, InvalidRedirectUriException) as exc:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "invalid_grant", "error_description": str(exc)},
            )
        except InvalidClientException as exc:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "invalid_client", "error_description": str(exc)},
            )
        except AuthDomainException as exc:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "invalid_request", "error_description": str(exc)},
            )

    # 2. Flujo refresh_token
    elif grant_type == "refresh_token":
        if not refresh_token:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": "invalid_request",
                    "error_description": "Falta el parámetro refresh_token",
                },
            )

        dto = TokenRefreshRequestDTO(
            grant_type=grant_type,
            client_id=client_id,
            refresh_token=refresh_token,
        )

        try:
            token_response = await refresh_use_case.execute(dto)
            return JSONResponse(status_code=status.HTTP_200_OK, content=token_response.to_dict())
        except InvalidRefreshTokenException as exc:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "invalid_grant", "error_description": str(exc)},
            )
        except InvalidClientException as exc:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "invalid_client", "error_description": str(exc)},
            )
        except AuthDomainException as exc:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "invalid_request", "error_description": str(exc)},
            )

    else:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "unsupported_grant_type",
                "error_description": f"grant_type '{grant_type}' no soportado",
            },
        )


# =========================================================================
# RFC 7009 Token Revocation: POST /oauth/revoke
# =========================================================================
@oauth_router.post("/oauth/revoke")
async def revoke_token(
    token: Annotated[str, Form()],
    client_id: Annotated[str | None, Form()] = None,
    token_type_hint: Annotated[str | None, Form()] = None,
    revoke_use_case: RevokeTokenUseCase = Depends(get_revoke_token_use_case),
):
    """Revoca un refresh token según RFC 7009."""
    dto = RevokeTokenRequestDTO(
        token=token,
        client_id=client_id or "",
        token_type_hint=token_type_hint,
    )
    await revoke_use_case.execute(dto)
    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "revoked"})


# =========================================================================
# UserInfo Endpoint: GET /oauth/userinfo
# =========================================================================
@oauth_router.get("/oauth/userinfo")
async def user_info(
    authorization: Annotated[str | None, Header()] = None,
    token_issuer: ITokenIssuer = Depends(get_token_issuer),
    user_info_use_case: GetUserInfoUseCase = Depends(get_user_info_use_case),
):
    """Retorna información del usuario autenticado mediante su access token Bearer."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el token de autorización Bearer",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = authorization.split(" ", 1)[1]
    try:
        claims = token_issuer.decode_and_validate_access_token(access_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acceso inválido o expirado",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    if not claims or "sub" not in claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acceso inválido o expirado",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    try:
        user_uuid = UUID(claims["sub"])
        user_dto = await user_info_use_case.execute(user_uuid=user_uuid)
        return user_dto.to_dict()
    except (UserInactiveException, Exception):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado o inactivo",
        )


# =========================================================================
# Logout Endpoint: GET /oauth/logout
# =========================================================================
@oauth_router.get("/oauth/logout")
async def logout(response: Response, redirect_to: str = "/"):
    """Cierra la sesión web del usuario en el flujo OAuth."""
    redirect_res = RedirectResponse(url=redirect_to, status_code=status.HTTP_302_FOUND)
    clear_session_cookie(redirect_res)
    return redirect_res


# =========================================================================
# FastAPI Application Factory
# =========================================================================
def create_oauth_app() -> FastAPI:
    """Crea y configura la aplicación FastAPI para el servidor OAuth 2.0."""
    settings = get_settings()
    app = FastAPI(
        title="Atlas OAuth 2.0 Server",
        description="Servidor de Autorización OAuth 2.0 para Atlas MCP Connector",
        version="1.0.0",
        docs_url="/docs",
        redoc_url=None,
    )

    # Montar archivos estáticos para la UI (CSS, imágenes, SVGs)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Incluir rutas OAuth
    app.include_router(oauth_router)

    return app


app = create_oauth_app()


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run("src.oauth.presentation.app:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
