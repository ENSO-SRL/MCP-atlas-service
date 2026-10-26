from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from src.shared.domain.base import DomainEvent


@dataclass
class UserRegisteredEvent(DomainEvent):
    user_uuid: UUID = field(default_factory=uuid4)
    email: str = ""
    phone: Optional[str] = None


@dataclass
class UserPhoneVerifiedEvent(DomainEvent):
    user_uuid: UUID = field(default_factory=uuid4)
    phone: str = ""
    verified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TokenIssuedEvent(DomainEvent):
    user_uuid: UUID = field(default_factory=uuid4)
    client_id: str = ""
    scope: str = ""


@dataclass
class TokenRevokedEvent(DomainEvent):
    user_uuid: UUID = field(default_factory=uuid4)
    client_id: str = ""
    token_hash: str = ""
