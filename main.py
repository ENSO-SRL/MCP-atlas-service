from __future__ import annotations

import logging
import sys
import anyio

from src.mcp.presentation.server import mcp_server
from src.shared.config.settings import get_settings


async def _run_server() -> None:
    settings = get_settings()

    # Asegurar que los logs vayan a stderr para proteger el canal stdio JSON-RPC de Claude
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO if settings.DEBUG else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if settings.DEV_MODE:
        from src.mcp.infrastructure.workers import InboxConsumerWorker, OutboxRelayWorker

        logger = logging.getLogger("mcp.dev_workers")
        logger.info(
            "DEV_MODE activado: iniciando OutboxRelayWorker e InboxConsumerWorker en segundo plano..."
        )

        outbox_worker = OutboxRelayWorker()
        inbox_worker = InboxConsumerWorker()

        async with anyio.create_task_group() as tg:
            tg.start_soon(outbox_worker.run_forever)
            tg.start_soon(inbox_worker.run_forever)
            try:
                await mcp_server.run_stdio_async()
            finally:
                logger.info("Servidor MCP finalizado. Deteniendo workers de fondo...")
                tg.cancel_scope.cancel()
    else:
        await mcp_server.run_stdio_async()


def main() -> None:
    # 1. Banderas explícitas de línea de comandos
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd in ("--stdio", "stdio"):
            anyio.run(_run_server)
            return
        if cmd in ("--oauth", "oauth", "--web", "web", "--http", "http"):
            import uvicorn
            settings = get_settings()
            uvicorn.run("src.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
            return

    # 2. Sin banderas: detectar si se corre de forma interactiva o como subproceso stdio
    # Si la entrada estándar no es un terminal interactivo (ej. Claude Desktop lanzándolo por tubería stdio):
    if not sys.stdin.isatty():
        anyio.run(_run_server)
    else:
        # En terminal interactiva (ej. 'python main.py'), levantar el servidor HTTP/OAuth/SSE unificado
        import uvicorn
        settings = get_settings()
        uvicorn.run("src.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)


if __name__ == "__main__":
    main()
