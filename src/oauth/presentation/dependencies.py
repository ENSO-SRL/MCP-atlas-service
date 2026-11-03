from __future__ import annotations

from collections.abc import AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.oauth.application.use_cases.authenticate_user import AuthenticateUserUseCase
from src.oauth.application.use_cases.exchange_token import ExchangeTokenUseCase
from src.oauth.application.use_cases.generate_authorization_code import (
    GenerateAuthorizationCodeUseCase,
)
from src.oauth.application.use_cases.get_user_info import GetUserInfoUseCase
from src.oauth.application.use_cases.refresh_token import RefreshTokenUseCase
from src.oauth.application.use_cases.revoke_token import RevokeTokenUseCase
from src.oauth.domain.ports.i_oauth_client_repository import IOAuthClientRepository
from src.oauth.domain.ports.i_oauth_token_repository import IOAuthTokenRepository
from src.oauth.domain.ports.i_security_ports import IPasswordHasher, ITokenIssuer
from src.oauth.domain.ports.i_user_repository import IUserRepository
from src.oauth.infrastructure.persistence.repositories.sql_oauth_client_repository import (
    SqlOAuthClientRepository,
)
from src.oauth.infrastructure.persistence.repositories.sql_oauth_token_repository import (
    SqlOAuthTokenRepository,
)
from src.oauth.infrastructure.persistence.repositories.sql_user_repository import (
    SqlUserRepository,
)
from src.oauth.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher
from src.oauth.infrastructure.security.jwt_token_issuer import JwtTokenIssuer
from src.shared.config.settings import get_settings
from src.shared.database.session import get_db_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provee una sesión de base de datos asíncrona por petición."""
    async with get_db_session() as session:
        yield session


def get_user_repository(session: AsyncSession = Depends(get_db)) -> IUserRepository:
    return SqlUserRepository(session)


def get_oauth_client_repository(session: AsyncSession = Depends(get_db)) -> IOAuthClientRepository:
    return SqlOAuthClientRepository(session)


def get_oauth_token_repository(session: AsyncSession = Depends(get_db)) -> IOAuthTokenRepository:
    return SqlOAuthTokenRepository(session)


def get_password_hasher() -> IPasswordHasher:
    return BcryptPasswordHasher()


def get_token_issuer() -> ITokenIssuer:
    settings = get_settings()
    return JwtTokenIssuer(
        secret_key=settings.OAUTH_JWT_SECRET_KEY,
        algorithm=settings.OAUTH_JWT_ALGORITHM,
        issuer=settings.OAUTH_ISSUER,
    )


def get_authenticate_user_use_case(
    user_repo: IUserRepository = Depends(get_user_repository),
    hasher: IPasswordHasher = Depends(get_password_hasher),
) -> AuthenticateUserUseCase:
    return AuthenticateUserUseCase(user_repo=user_repo, password_hasher=hasher)


def get_generate_authorization_code_use_case(
    client_repo: IOAuthClientRepository = Depends(get_oauth_client_repository),
    token_repo: IOAuthTokenRepository = Depends(get_oauth_token_repository),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> GenerateAuthorizationCodeUseCase:
    return GenerateAuthorizationCodeUseCase(
        client_repo=client_repo,
        token_repo=token_repo,
        user_repo=user_repo,
    )


def get_exchange_token_use_case(
    client_repo: IOAuthClientRepository = Depends(get_oauth_client_repository),
    token_repo: IOAuthTokenRepository = Depends(get_oauth_token_repository),
    user_repo: IUserRepository = Depends(get_user_repository),
    token_issuer: ITokenIssuer = Depends(get_token_issuer),
) -> ExchangeTokenUseCase:
    return ExchangeTokenUseCase(
        client_repo=client_repo,
        token_repo=token_repo,
        user_repo=user_repo,
        token_issuer=token_issuer,
    )


def get_refresh_token_use_case(
    client_repo: IOAuthClientRepository = Depends(get_oauth_client_repository),
    token_repo: IOAuthTokenRepository = Depends(get_oauth_token_repository),
    user_repo: IUserRepository = Depends(get_user_repository),
    token_issuer: ITokenIssuer = Depends(get_token_issuer),
) -> RefreshTokenUseCase:
    return RefreshTokenUseCase(
        client_repo=client_repo,
        token_repo=token_repo,
        user_repo=user_repo,
        token_issuer=token_issuer,
    )


def get_revoke_token_use_case(
    token_repo: IOAuthTokenRepository = Depends(get_oauth_token_repository),
) -> RevokeTokenUseCase:
    return RevokeTokenUseCase(token_repo=token_repo)


def get_user_info_use_case(
    user_repo: IUserRepository = Depends(get_user_repository),
) -> GetUserInfoUseCase:
    return GetUserInfoUseCase(user_repo=user_repo)
