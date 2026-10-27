from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from src.mcp.presentation.tools.availability_tools import register_availability_tools
from src.mcp.presentation.tools.booking_tools import register_booking_tools
from src.mcp.presentation.tools.catalog_tools import register_catalog_tools


def create_mcp_server(name: str = "atlas-mcp-connector") -> MCPServer:
    """
    Factoría para inicializar y configurar el servidor MCP de Atlas para Claude.
    Registra formalmente las 10 herramientas del catálogo según las especificaciones de Anthropic.
    """
    server = MCPServer(name)

    # Registrar grupos de herramientas
    register_catalog_tools(server)
    register_availability_tools(server)
    register_booking_tools(server)

    return server


# Instancia por defecto del servidor MCP
mcp_server: MCPServer = create_mcp_server()


if __name__ == "__main__":
    # Ejecución por stdio para clientes locales como Claude Desktop
    mcp_server.run()
