from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.oauth.domain.entities.oauth_client import OAuthClient
from src.oauth.domain.ports.i_oauth_client_repository import IOAuthClientRepository
from src.oauth.infrastructure.persistence.models.oauth_models import OAuthClientModel


class SqlOAuthClientRepository(IOAuthClientRepository):
    """Implementación de IOAuthClientRepository basada en SQLAlchemy Async."""

    def __init__(self, session: AsyncSession):
        self._session = session

    @staticmethod
    def _to_domain(model: OAuthClientModel) -> OAuthClient:
        return OAuthClient(
            id=model.client_id,
            client_name=model.client_name,
            redirect_uris=list(model.redirect_uris or []),
            client_secret_hash=model.client_secret_hash,
            is_confidential=model.is_confidential,
            created_at=model.created_at,
        )

    async def get_by_client_id(self, client_id: str) -> Optional[OAuthClient]:
        stmt = select(OAuthClientModel).where(OAuthClientModel.client_id == client_id.strip())
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def save(self, client: OAuthClient) -> OAuthClient:
        model = await self._session.get(OAuthClientModel, client.id)
        if model is None:
            model = OAuthClientModel(
                client_id=client.id,
                client_name=client.client_name,
                redirect_uris=client.redirect_uris,
                client_secret_hash=client.client_secret_hash,
                is_confidential=client.is_confidential,
                created_at=client.created_at,
            )
            self._session.add(model)
        else:
            model.client_name = client.client_name
            model.redirect_uris = client.redirect_uris
            model.client_secret_hash = client.client_secret_hash
            model.is_confidential = client.is_confidential

        await self._session.flush()
        return self._to_domain(model)

