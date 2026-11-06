-- ============================================================================
-- MIGRACIÓN: Soporte de Avisos, Discrepancias y Estado 'requires_confirmation'
-- ============================================================================
-- Permite pausar reservas ante discrepancias (ej. ajustes tarifarios no sincronizados
-- o cambios informados por el upstream) y registrar solicitudes de confirmación
-- que el usuario puede resolver mediante la tool 'resolve_booking_notice'.
-- ============================================================================

BEGIN;

-- 1. Actualizar restricción CHECK en mcp.booking_request para admitir 'requires_confirmation'
ALTER TABLE mcp.booking_request DROP CONSTRAINT IF EXISTS booking_request_status_check;

ALTER TABLE mcp.booking_request ADD CONSTRAINT booking_request_status_check
    CHECK (status IN (
        'requested',
        'accepted',
        'confirmed',
        'rejected',
        'failed',
        'expired',
        'cancel_requested',
        'cancelled',
        'requires_confirmation'
    ));

-- 2. Crear tabla de avisos y discrepancias (BookingNotice)
CREATE TABLE IF NOT EXISTS mcp.booking_notice (
    id                  uuid PRIMARY KEY,
    booking_id          uuid NOT NULL REFERENCES mcp.booking_request (id) ON DELETE CASCADE,
    notice_type         text NOT NULL,
    status              text NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'accepted', 'rejected', 'expired')),
    message             text NOT NULL,
    payload             jsonb NOT NULL DEFAULT '{}'::jsonb,
    requires_action     boolean NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now(),
    resolved_at         timestamptz,
    resolution_action   text
);

-- 3. Índices de búsqueda para avisos por reserva y estado
CREATE INDEX IF NOT EXISTS ix_booking_notice_booking
    ON mcp.booking_notice (booking_id, status);

-- 4. Actualizar índice de expiración para contemplar reservas pausadas
DROP INDEX IF EXISTS mcp.ix_booking_expiry;

CREATE INDEX IF NOT EXISTS ix_booking_expiry
    ON mcp.booking_request (expires_at)
    WHERE status IN ('requested', 'accepted', 'requires_confirmation');

COMMIT;

