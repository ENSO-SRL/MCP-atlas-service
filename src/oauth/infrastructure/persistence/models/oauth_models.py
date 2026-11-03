from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.database.session import Base


class OAuthClientModel(Base):
    """Modelo ORM para mcp.oauth_client."""
    __tablename__ = "oauth_client"
    __table_args__ = {"schema": "mcp", "extend_existing": True}

    client_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    client_secret_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    client_name: Mapped[str] = mapped_column(String(150), nullable=False)
    redirect_uris: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    is_confidential: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    codes: Mapped[list[AuthorizationCodeModel]] = relationship(
        "AuthorizationCodeModel", back_populates="client", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list[RefreshTokenModel]] = relationship(
        "RefreshTokenModel", back_populates="client", cascade="all, delete-orphan"
    )


class AuthorizationCodeModel(Base):
    """Modelo ORM para mcp.oauth_authorization_code."""
    __tablename__ = "oauth_authorization_code"
    __table_args__ = {"schema": "mcp", "extend_existing": True}

    code: Mapped[str] = mapped_column(String(128), primary_key=True)
    client_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("mcp.oauth_client.client_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_uuid: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(
        Text, default="bookings:read bookings:write profile", nullable=False
    )
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    code_challenge_method: Mapped[str] = mapped_column(String(10), default="S256", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    client: Mapped[OAuthClientModel] = relationship("OAuthClientModel", back_populates="codes")


class RefreshTokenModel(Base):
    """Modelo ORM para mcp.oauth_refresh_token."""
    __tablename__ = "oauth_refresh_token"
    __table_args__ = {"schema": "mcp", "extend_existing": True}

    token_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    client_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("mcp.oauth_client.client_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_uuid: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    scope: Mapped[str] = mapped_column(
        Text, default="bookings:read bookings:write profile", nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    client: Mapped[OAuthClientModel] = relationship("OAuthClientModel", back_populates="refresh_tokens")

