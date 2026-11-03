from __future__ import annotations

from uuid import UUID

from src.oauth.application.dto.oauth_dtos import UserInfoDTO
from src.oauth.domain.exceptions.auth_exceptions import UserInactiveException
from src.oauth.domain.ports.i_user_repository import IUserRepository


class GetUserInfoUseCase:
    """
    Caso de uso: Obtención de información de perfil del usuario autenticado (/oauth/userinfo).
    Retorna claims básicos del usuario (sub, email, name, phone_number).
    """

    def __init__(self, user_repo: IUserRepository):
        self._user_repo = user_repo

    async def execute(self, user_uuid: UUID) -> UserInfoDTO:
        user = await self._user_repo.get_by_uuid(user_uuid)
        if user is None or not user.is_active or user.is_cancelled:
            raise UserInactiveException("Usuario no encontrado o inactivo.")

        return UserInfoDTO(
            sub=str(user.uuid),
            email=str(user.email),
            name=user.full_name or user.name,
            phone_number=str(user.phone) if user.phone else None,
            is_confirmed=user.is_confirmed,
        )

