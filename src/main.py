from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Asegurar que el directorio raíz del proyecto esté en sys.path al invocar python src/main.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Configuración global del logging en consola con flush inmediato
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

import jwt
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mcp.server.sse import TransportSecuritySettings
from starlette.types import ASGIApp, Receive, Scope, Send

from src.mcp.infrastructure.workers import InboxConsumerWorker, OutboxRelayWorker
from src.mcp.presentation.server import mcp_server
from src.oauth.presentation.app import create_oauth_app
from src.shared.config.settings import get_settings

logger = logging.getLogger("atlas.connector")


class MCPAuthMiddleware:
    """
    Middleware ASGI que protege los endpoints MCP (/sse y /messages/).

    1. Para peticiones a /sse o /messages/:
       - Si no cuenta con una cabecera 'Authorization: Bearer <token>' o el token JWT es inválido:
         Devuelve HTTP 401 Unauthorized con la cabecera WWW-Authenticate adecuada (RFC 6750 y RFC 9470).
         Esto notifica a mcp-remote / Claude Desktop que la autenticación es obligatoria y abre el navegador.
       - Si cuenta con un Bearer token válido:
         Valida la firma criptográfica con OAUTH_JWT_SECRET_KEY y permite el paso.
    2. Las demás rutas (root, discovery, oauth UI, static) pasan directamente.
    """
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.settings = get_settings()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path == "/sse" or path.startswith("/messages"):
                method = scope.get("method", "GET")
                if method == "OPTIONS":
                    await self.app(scope, receive, send)
                    return

                headers = dict(scope.get("headers", []))
                auth_header = headers.get(b"authorization", b"").decode("latin1").strip()

                token = None
                if auth_header.lower().startswith("bearer "):
                    token = auth_header[7:].strip()

                authenticated = False
                if token:
                    try:
                        claims = jwt.decode(
                            token,
                            self.settings.OAUTH_JWT_SECRET_KEY,
                            algorithms=[self.settings.OAUTH_JWT_ALGORITHM],
                            options={"verify_aud": False},
                        )
                        if "sub" in claims:
                            authenticated = True
                    except jwt.PyJWTError:
                        authenticated = False

                if not authenticated:
                    host = headers.get(b"host", b"").decode("latin1") or f"localhost:{self.settings.PORT}"
                    base_url = f"http://{host}"
                    www_auth = (
                        f'Bearer realm="Atlas MCP", '
                        f'resource_metadata="{base_url}/.well-known/oauth-protected-resource", '
                        f'scope="bookings:read bookings:write profile"'
                    )
                    res = JSONResponse(
                        status_code=401,
                        content={"detail": "Authentication required. Please authenticate via OAuth 2.0."},
                        headers={"WWW-Authenticate": www_auth},
                    )
                    await res(scope, receive, send)
                    return

        await self.app(scope, receive, send)


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """
    Ciclo de vida ASGI (Lifespan) que gestiona los background workers de Atlas:
    - OutboxRelayWorker: retransmite mcp.outbox_event -> Redis Stream 'stream:booking:events'
    - InboxConsumerWorker: consume Redis Stream 'stream:booking:results' -> actualiza mcp.booking_request
    """
    stop_event = asyncio.Event()
    outbox_worker = OutboxRelayWorker()
    inbox_worker = InboxConsumerWorker()

    logger.info("Iniciando background workers (OutboxRelayWorker e InboxConsumerWorker)...")
    outbox_task = asyncio.create_task(outbox_worker.run_forever(stop_event=stop_event))
    inbox_task = asyncio.create_task(inbox_worker.run_forever(stop_event=stop_event))
    logger.info("Background workers activos en segundo plano.")

    yield

    logger.info("Deteniendo background workers...")
    stop_event.set()
    outbox_task.cancel()
    inbox_task.cancel()
    try:
        await asyncio.gather(outbox_task, inbox_task, return_exceptions=True)
    except Exception:
        pass
    logger.info("Background workers detenidos exitosamente.")


def create_unified_app() -> FastAPI:
    """
    Crea la aplicación ASGI unificada que combina:
      1. Servidor de Autorización OAuth 2.0 (RFC 6749, RFC 7636, RFC 8414, RFC 9470).
      2. Servidor MCP sobre Server-Sent Events (SSE) y HTTP (/sse, /messages/).
      3. Background workers para Outbox / Inbox.
    """
    settings = get_settings()

    # 1. Base FastAPI con todas las rutas OAuth, UI y Lifespan de workers
    app = create_oauth_app(lifespan=app_lifespan)

    # 2. Middleware de autenticación obligatoria para MCP (/sse y /messages/)
    app.add_middleware(MCPAuthMiddleware)

    # 3. Configurar CORS para permitir peticiones locales desde navegadores / Inspector
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 4. Construir la sub-aplicación SSE del servidor MCP
    # Desactivamos la protección estricta de DNS rebinding para desarrollo local en localhost/127.0.0.1
    mcp_sse_subapp = mcp_server.sse_app(
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        )
    )

    # 5. Endpoint de bienvenida / estado general en la raíz
    @app.get("/", tags=["Health"])
    async def root_status():
        return {
            "status": "online",
            "service": "Atlas MCP Connector & OAuth 2.0 Server",
            "environment": settings.ENVIRONMENT,
            "version": "1.0.0",
            "endpoints": {
                "oauth_discovery": "/.well-known/oauth-authorization-server",
                "oauth_protected_resource": "/.well-known/oauth-protected-resource",
                "oauth_register": "/oauth/register",
                "oauth_authorize": "/oauth/authorize",
                "oauth_token": "/oauth/token",
                "mcp_sse": "/sse",
                "mcp_messages": "/messages/",
            },
        }

    # 6. Montar el transporte MCP SSE en la raíz para atender /sse y /messages/
    # Las rutas explícitas de FastAPI (OAuth, static, health) tienen precedencia automática.
    app.mount("/", mcp_sse_subapp)

    return app


# Instancia ASGI principal para uvicorn
app: FastAPI = create_unified_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    logger.info("Iniciando Atlas Unified Server en %s:%s", settings.HOST, settings.PORT)
    uvicorn.run(
        "src.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
