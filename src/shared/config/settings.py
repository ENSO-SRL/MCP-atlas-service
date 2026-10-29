from functools import lru_cache
from typing import Optional
from uuid import UUID
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Entorno y servidor
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=True)
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)

    # Modo de desarrollo y pruebas locales (Claude Desktop por stdio sin OAuth)
    DEV_MODE: bool = Field(
        default=False,
        description="Si es True, permite llamadas locales sin token OAuth usando DEV_USER_*",
    )
    DEV_USER_UUID: Optional[UUID] = Field(
        default=None,
        description="UUID de usuario fijo para pruebas locales (ej. 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11')",
    )
    DEV_USER_PHONE: Optional[str] = Field(
        default=None,
        description="Teléfono de prueba fijo en formato E.164 (ej. '+18094251911')",
    )
    DEV_USER_EMAIL: Optional[str] = Field(
        default=None,
        description="Email de prueba fijo (ej. 'juan.perez@example.com')",
    )

    # Base de Datos PostgreSQL (ATLAS-BACKEND)
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/atlas_db",
        description="URL de conexión asíncrona a PostgreSQL con asyncpg",
    )
    DATABASE_POOL_SIZE: int = Field(default=20)
    DATABASE_MAX_OVERFLOW: int = Field(default=10)

    # Redis (Message Bus, Cache y Holds)
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="URL de conexión a Redis",
    )
    REDIS_AVAILABILITY_CACHE_TTL: int = Field(
        default=600,
        description="TTL en segundos para la caché de disponibilidad de slots (5-10 min)",
    )
    REDIS_DIMENSION_CACHE_TTL: int = Field(
        default=600,
        description="TTL en segundos para la caché de opciones de dimensión dependiente (5-10 min)",
    )
    REDIS_SUPERFICIAL_WAIT_SECONDS: float = Field(
        default=2.0,
        description="Tiempo de espera superficial en segundos para consultas diferidas",
    )
    REDIS_OPERATION_TTL: int = Field(
        default=600,
        description="TTL en segundos para el estado y resultado de operaciones diferidas",
    )

    # OAuth 2.0 y JWT
    OAUTH_ISSUER: str = Field(default="https://mcp.atlas.com")
    OAUTH_JWT_SECRET_KEY: str = Field(default="change-this-in-production-super-secret-key-for-oauth")
    OAUTH_JWT_ALGORITHM: str = Field(default="HS256")
    OAUTH_ACCESS_TOKEN_EXPIRE_SECONDS: int = Field(default=3600)  # 1 hora
    OAUTH_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30)
    OAUTH_AUTH_CODE_EXPIRE_SECONDS: int = Field(default=60)  # 60 segundos

    # MCP Slot Token Signing
    MCP_TOKEN_SECRET: str = Field(
        default="change-this-in-production-super-secret-key-for-mcp-slot-tokens",
        description="Clave secreta para firmar criptográficamente los slot_tokens entregados a Claude",
    )


@lru_cache
def get_settings() -> Settings:
    """Retorna una instancia única cacheada de las configuraciones del sistema."""
    return Settings()
