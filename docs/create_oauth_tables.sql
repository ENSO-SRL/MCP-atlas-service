-- =====================================================================
-- SCRIPT DE MIGRACIÓN DDL: TABLAS DEL SERVIDOR DE AUTORIZACIÓN OAUTH 2.0
-- Base de datos destino: ATLAS-BACKEND (PostgreSQL)
-- Esquema dedicado: 'mcp'
-- Estándares: RFC 6749 (OAuth 2.0), RFC 7636 (PKCE S256), RFC 7009 (Revocation)
-- =====================================================================

-- 1. Asegurar esquema dedicado 'mcp'
CREATE SCHEMA IF NOT EXISTS mcp;

-- =====================================================================
-- 2. TABLA: mcp.oauth_client
-- Clientes OAuth 2.0 registrados (Claude Desktop, Claude Web, etc.)
-- =====================================================================
CREATE TABLE IF NOT EXISTS mcp.oauth_client (
    client_id           VARCHAR(100) PRIMARY KEY,
    client_secret_hash  VARCHAR(255),                                -- Nulo para clientes públicos con PKCE
    client_name         VARCHAR(150) NOT NULL,
    redirect_uris       TEXT[] NOT NULL,                             -- Lista de URIs de callback permitidas
    is_confidential     BOOLEAN NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE mcp.oauth_client IS 'Clientes OAuth 2.0 autorizados para interactuar con el conector Atlas MCP.';
COMMENT ON COLUMN mcp.oauth_client.redirect_uris IS 'URIs de redirección autorizadas para el cliente (validación estricta de callback).';

-- =====================================================================
-- 3. TABLA: mcp.oauth_authorization_code
-- Códigos de autorización efímeros (TTL 60s) con desafío PKCE S256 obligatorio
-- =====================================================================
CREATE TABLE IF NOT EXISTS mcp.oauth_authorization_code (
    code                  VARCHAR(128) PRIMARY KEY,
    client_id             VARCHAR(100) NOT NULL REFERENCES mcp.oauth_client (client_id) ON DELETE CASCADE,
    user_uuid             UUID NOT NULL,                             -- Corresponde al UUID del usuario en public.users
    redirect_uri          TEXT NOT NULL,
    scope                 TEXT NOT NULL DEFAULT 'bookings:read bookings:write profile',
    code_challenge        VARCHAR(128) NOT NULL,
    code_challenge_method VARCHAR(10) NOT NULL DEFAULT 'S256' CHECK (code_challenge_method = 'S256'),
    expires_at            TIMESTAMPTZ NOT NULL,
    used_at               TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE mcp.oauth_authorization_code IS 'Códigos temporales de autorización emitidos tras el consentimiento del usuario (un solo uso).';

-- Índices de consulta rápida y expiración
CREATE INDEX IF NOT EXISTS ix_mcp_auth_code_expiry 
    ON mcp.oauth_authorization_code (expires_at) WHERE used_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_mcp_auth_code_client_user 
    ON mcp.oauth_authorization_code (client_id, user_uuid);

-- =====================================================================
-- 4. TABLA: mcp.oauth_refresh_token
-- Tokens de actualización persistidos por hash SHA-256 para rotación estricta
-- =====================================================================
CREATE TABLE IF NOT EXISTS mcp.oauth_refresh_token (
    token_hash   VARCHAR(128) PRIMARY KEY,                           -- Hash SHA-256 del refresh token
    client_id    VARCHAR(100) NOT NULL REFERENCES mcp.oauth_client (client_id) ON DELETE CASCADE,
    user_uuid    UUID NOT NULL,                                      -- Corresponde al UUID del usuario en public.users
    scope        TEXT NOT NULL DEFAULT 'bookings:read bookings:write profile',
    expires_at   TIMESTAMPTZ NOT NULL,
    revoked_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE mcp.oauth_refresh_token IS 'Tokens de actualización con rotación y revocación para renovación de access tokens JWT.';

-- Índices para búsqueda de tokens vigentes
CREATE INDEX IF NOT EXISTS ix_mcp_refresh_token_lookup 
    ON mcp.oauth_refresh_token (user_uuid, client_id) WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_mcp_refresh_token_expiry 
    ON mcp.oauth_refresh_token (expires_at) WHERE revoked_at IS NULL;

-- =====================================================================
-- 5. SEMILLA INICIAL: Clientes Oficiales de Claude Preconfigurados
-- Permite autorización inmediata sin requerir flujo DCR manual inicial
-- =====================================================================
INSERT INTO mcp.oauth_client (client_id, client_name, redirect_uris, is_confidential)
VALUES 
    (
        'claude-desktop',
        'Claude Desktop Client',
        ARRAY[
            'http://127.0.0.1/callback',
            'http://localhost/callback',
            'https://claude.ai/api/oauth/callback',
            'http://127.0.0.1:8000/oauth/callback'
        ],
        false
    ),
    (
        'claude',
        'Anthropic Claude',
        ARRAY[
            'https://claude.ai/api/oauth/callback',
            'http://127.0.0.1/callback',
            'http://localhost/callback'
        ],
        false
    )
ON CONFLICT (client_id) DO UPDATE SET
    client_name = EXCLUDED.client_name,
    redirect_uris = EXCLUDED.redirect_uris;

