from __future__ import annotations

from src.oauth.application.dto.oauth_dtos import (
    UserAuthSessionDTO,
    UserLoginRequestDTO,
)
from src.oauth.domain.exceptions.auth_exceptions import (
    InvalidCredentialsException,
    UserInactiveException,
)
from src.oauth.domain.ports.i_security_ports import IPasswordHasher
from src.oauth.domain.ports.i_user_repository import IUserRepository


class AuthenticateUserUseCase:
    """
    Caso de uso: Autenticación de usuarios de ATLAS-BACKEND.
    Verifica las credenciales del usuario (email y contraseña hash Bcrypt)
    y valida el estado de la cuenta para iniciar sesión en el servidor OAuth.
    """

    def __init__(self, user_repo: IUserRepository, password_hasher: IPasswordHasher):
        self._user_repo = user_repo
        self._hasher = password_hasher

    async def execute(self, dto: UserLoginRequestDTO) -> UserAuthSessionDTO:
        clean_email = dto.email.strip().lower()
        user = await self._user_repo.get_by_email(clean_email)

        if user is None:
            raise InvalidCredentialsException()

        if not self._hasher.verify_password(dto.password, user.hashed_password):
            raise InvalidCredentialsException()

        if not user.is_active or user.is_cancelled:
            raise UserInactiveException("La cuenta de usuario está desactivada o cancelada.")

        return UserAuthSessionDTO(
            user_uuid=user.uuid,
            email=str(user.email),
            name=user.full_name or user.name,
            phone=str(user.phone) if user.phone else None,
        )

