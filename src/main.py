from __future__ import annotations

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mcp.server.sse import TransportSecuritySettings

from src.mcp.presentation.server import mcp_server
from src.oauth.presentation.app import create_oauth_app
from src.shared.config.settings import get_settings

logger = logging.getLogger("atlas.connector")


def create_unified_app() -> FastAPI:
    """
    Crea la aplicación ASGI unificada que combina:
      1. Servidor de Autorización OAuth 2.0 (RFC 6749, RFC 7636, RFC 8414).
      2. Servidor MCP sobre Server-Sent Events (SSE) y HTTP (/sse, /messages/).
    """
    settings = get_settings()

    # 1. Base FastAPI con todas las rutas OAuth y páginas Jinja2
    app = create_oauth_app()

    # 2. Configurar CORS para permitir peticiones locales desde navegadores / Inspector
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 3. Construir la sub-aplicación SSE del servidor MCP
    # Desactivamos la protección estricta de DNS rebinding para desarrollo local en localhost/127.0.0.1
    mcp_sse_subapp = mcp_server.sse_app(
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        )
    )

    # 4. Endpoint de bienvenida / estado general en la raíz
    @app.get("/", tags=["Health"])
    async def root_status():
        return {
            "status": "online",
            "service": "Atlas MCP Connector & OAuth 2.0 Server",
            "environment": settings.ENVIRONMENT,
            "version": "1.0.0",
            "endpoints": {
                "oauth_discovery": "/.well-known/oauth-authorization-server",
                "oauth_authorize": "/oauth/authorize",
                "oauth_token": "/oauth/token",
                "mcp_sse": "/sse",
                "mcp_messages": "/messages/",
            },
        }

    # 5. Montar el transporte MCP SSE en la raíz para atender /sse y /messages/
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

