from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse
from uuid import uuid4

from src.oauth.application.dto.oauth_dtos import (
    ClientRegistrationRequestDTO,
    ClientRegistrationResponseDTO,
)
from src.oauth.domain.entities.oauth_client import OAuthClient
from src.oauth.domain.exceptions.auth_exceptions import InvalidRedirectUriException
from src.oauth.domain.ports.i_oauth_client_repository import IOAuthClientRepository

logger = logging.getLogger("oauth.dcr")


class RegisterClientUseCase:
    """
    Caso de Uso: Registro Dinámico de Clientes (Dynamic Client Registration - RFC 7591).
    Permite a clientes nativos como Claude Desktop y mcp-remote registrarse automáticamente
    al iniciar sesión, recibiendo un client_id válido y registrando sus URIs de retorno efímeras.
    """

    def __init__(self, client_repo: IOAuthClientRepository) -> None:
        self._client_repo = client_repo

    async def execute(self, dto: ClientRegistrationRequestDTO) -> ClientRegistrationResponseDTO:
        if not dto.redirect_uris or not isinstance(dto.redirect_uris, list):
            raise InvalidRedirectUriException("El registro dinámico requiere al menos una redirect_uri.")

        # Validar formato básico de las URIs de redirección
        validated_uris: list[str] = []
        for uri in dto.redirect_uris:
            if not isinstance(uri, str) or not uri.strip():
                continue
            parsed = urlparse(uri)
            if not parsed.scheme or not parsed.netloc:
                raise InvalidRedirectUriException(f"URI de redirección malformada: '{uri}'")
            validated_uris.append(uri.strip())

        if not validated_uris:
            raise InvalidRedirectUriException("No se proporcionaron URIs de redirección válidas.")

        # Generar un identificador de cliente único
        client_id = f"mcp-client-{uuid4().hex[:12]}"
        client_name = dto.client_name.strip() if dto.client_name else "Claude Desktop MCP Client"
        token_auth_method = dto.token_endpoint_auth_method or "none"
        is_confidential = token_auth_method != "none"

        grant_types = dto.grant_types or ["authorization_code", "refresh_token"]
        response_types = dto.response_types or ["code"]

        now = datetime.now(timezone.utc)
        client = OAuthClient(
            id=client_id,
            client_name=client_name,
            redirect_uris=validated_uris,
            client_secret_hash=None,
            is_confidential=is_confidential,
            created_at=now,
        )

        saved_client = await self._client_repo.save(client)
        logger.info(
            "Cliente OAuth dinámico registrado exitosamente: id=%s, name='%s', uris=%s",
            saved_client.id,
            saved_client.client_name,
            saved_client.redirect_uris,
        )

        return ClientRegistrationResponseDTO(
            client_id=saved_client.id,
            client_name=saved_client.client_name,
            redirect_uris=saved_client.redirect_uris,
            token_endpoint_auth_method=token_auth_method,
            grant_types=grant_types,
            response_types=response_types,
            client_id_issued_at=int(saved_client.created_at.timestamp()),
            client_secret=None,
        )

