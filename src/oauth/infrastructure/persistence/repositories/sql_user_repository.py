from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.oauth.domain.entities.user import User
from src.oauth.domain.enums.user_role import UserRole
from src.oauth.domain.ports.i_user_repository import IUserRepository
from src.oauth.domain.value_objects.email_address import EmailAddress
from src.oauth.domain.value_objects.phone_number_e164 import PhoneNumberE164
from src.oauth.infrastructure.persistence.models.user_models import UserModel


class SqlUserRepository(IUserRepository):
    """Implementación de IUserRepository basada en SQLAlchemy Async para 'public.users'."""

    def __init__(self, session: AsyncSession):
        self._session = session

    @staticmethod
    def _to_domain(model: UserModel) -> User:
        user_uuid = UUID(model.uuid) if isinstance(model.uuid, str) else model.uuid
        role = UserRole.ADMIN if getattr(model, "role_id", None) == 1 else UserRole.USER
        phone = getattr(model, "phone", None)
        phone_vo = PhoneNumberE164(phone) if phone else None
        created_at = getattr(model, "created_at", None) or datetime.now(timezone.utc)
        updated_at = getattr(model, "updated_at", None) or datetime.now(timezone.utc)

        return User(
            id=model.id,
            uuid=user_uuid,
            email=EmailAddress(model.email),
            hashed_password=model.hashed_password,
            name=model.name,
            last_name=model.last_name,
            phone=phone_vo,
            national_id=getattr(model, "national_id", None),
            gender=getattr(model, "gender", None),
            is_active=getattr(model, "is_active", True),
            is_confirmed=getattr(model, "is_confirmed", False),
            is_cancelled=getattr(model, "is_cancelled", False),
            role=role,
            parent_id=getattr(model, "parent_id", None),
            created_at=created_at,
            updated_at=updated_at,
        )

    async def get_by_id(self, user_id: int) -> Optional[User]:
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def get_by_uuid(self, user_uuid: UUID) -> Optional[User]:
        stmt = select(UserModel).where(UserModel.uuid == str(user_uuid))
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def get_by_email(self, email: str) -> Optional[User]:
        stmt = select(UserModel).where(UserModel.email == email.strip().lower())
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def get_by_phone(self, phone: str) -> Optional[User]:
        stmt = select(UserModel).where(UserModel.phone == phone.strip())
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def save(self, user: User) -> User:
        model: Optional[UserModel] = None
        if user.id is not None:
            model = await self._session.get(UserModel, user.id)

        if model is None:
            model = UserModel(
                uuid=str(user.uuid),
                email=str(user.email).lower(),
                hashed_password=user.hashed_password,
                name=user.name,
                last_name=user.last_name,
                phone=str(user.phone) if user.phone else None,
                national_id=user.national_id,
                gender=user.gender,
                is_active=user.is_active,
                is_confirmed=user.is_confirmed,
                is_cancelled=user.is_cancelled,
                role_id=1 if user.role == UserRole.ADMIN else 2,
                parent_id=user.parent_id,
            )
            self._session.add(model)
        else:
            model.email = str(user.email).lower()
            model.hashed_password = user.hashed_password
            model.name = user.name
            model.last_name = user.last_name
            model.phone = str(user.phone) if user.phone else None
            model.national_id = user.national_id
            model.gender = user.gender
            model.is_active = user.is_active
            model.is_confirmed = user.is_confirmed
            model.is_cancelled = user.is_cancelled
            model.role_id = 1 if user.role == UserRole.ADMIN else 2
            model.parent_id = user.parent_id

        await self._session.flush()
        user.id = model.id
        return self._to_domain(model)
