-- =====================================================================
-- SCRIPT DE MIGRACIÓN DDL: ESQUEMA Y TABLAS DEL CONECTOR MCP DE ATLAS
-- Base de datos destino: ATLAS-BACKEND (PostgreSQL)
-- Esquema dedicado: 'mcp'
-- =====================================================================

-- 1. Crear el esquema dedicado 'mcp'
CREATE SCHEMA IF NOT EXISTS mcp;

-- Comentario explicativo
COMMENT ON SCHEMA mcp IS 'Tablas dedicadas del Conector MCP de Atlas: contratos dinámicos, disponibilidad, precios, reservas y outbox/inbox transaccional.';

-- =====================================================================
-- 2. TABLAS DE CONTRATOS Y DIMENSIONES
-- =====================================================================

CREATE TABLE IF NOT EXISTS mcp.service_contract_version (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    service_id             integer NOT NULL REFERENCES public.servicios (id) ON DELETE RESTRICT,
    version_no             integer NOT NULL DEFAULT 1,
    status                 text NOT NULL DEFAULT 'draft'
                           CHECK (status IN ('draft', 'published', 'retired')),
    booking_fields_schema  jsonb NOT NULL DEFAULT '{}'::jsonb,
    payment_policy         jsonb NOT NULL DEFAULT '{}'::jsonb,
    cancellation_policy    jsonb NOT NULL DEFAULT '{}'::jsonb,
    request_ttl_seconds    integer NOT NULL CHECK (request_ttl_seconds > 0),
    meta_schema_version    integer NOT NULL DEFAULT 1,
    content_hash           text,
    published_at           timestamptz,
    created_at             timestamptz NOT NULL DEFAULT now(),
    UNIQUE (service_id, version_no),
    CHECK (status = 'draft' OR (published_at IS NOT NULL AND content_hash IS NOT NULL))
);

-- Garantiza una sola versión publicada/vigente por servicio
CREATE UNIQUE INDEX IF NOT EXISTS uq_contract_one_published_per_service
    ON mcp.service_contract_version (service_id)
    WHERE status = 'published';

CREATE TABLE IF NOT EXISTS mcp.contract_dimension (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_version_id  uuid NOT NULL REFERENCES mcp.service_contract_version (id) ON DELETE CASCADE,
    key                  text NOT NULL,
    position             smallint NOT NULL DEFAULT 0,
    label                text NOT NULL,
    description          text,
    values_source        text NOT NULL
                         CHECK (values_source IN ('inline', 'slots', 'separate_query')),
    apply_mode           text NOT NULL
                         CHECK (apply_mode IN ('post_filter', 'upstream_param')),
    required             boolean NOT NULL DEFAULT false,
    allows_any           boolean NOT NULL DEFAULT false,
    reports_counts       boolean NOT NULL DEFAULT false,
    resolver_ref         text, -- Clave opaca interna para el Facade/Disponibilidad
    UNIQUE (contract_version_id, key),
    UNIQUE (id, contract_version_id),
    CHECK (values_source <> 'separate_query' OR resolver_ref IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS mcp.contract_dimension_dependency (
    contract_version_id      uuid NOT NULL,
    dimension_id             uuid NOT NULL,
    depends_on_dimension_id  uuid NOT NULL,
    PRIMARY KEY (dimension_id, depends_on_dimension_id),
    CHECK (dimension_id <> depends_on_dimension_id),
    FOREIGN KEY (dimension_id, contract_version_id)
        REFERENCES mcp.contract_dimension (id, contract_version_id) ON DELETE CASCADE,
    FOREIGN KEY (depends_on_dimension_id, contract_version_id)
        REFERENCES mcp.contract_dimension (id, contract_version_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mcp.contract_dimension_value (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_version_id  uuid NOT NULL,
    dimension_id         uuid NOT NULL,
    value_key            text NOT NULL,
    label                text NOT NULL,
    description          text,
    position             smallint NOT NULL DEFAULT 0,
    UNIQUE (dimension_id, value_key),
    FOREIGN KEY (dimension_id, contract_version_id)
        REFERENCES mcp.contract_dimension (id, contract_version_id) ON DELETE CASCADE
);

-- =====================================================================
-- 3. TABLAS DE PRECIOS INFORMATIVOS
-- =====================================================================

CREATE TABLE IF NOT EXISTS mcp.service_pricing_policy (
    service_id           integer PRIMARY KEY REFERENCES public.servicios (id) ON DELETE RESTRICT,
    pricing_mode         text NOT NULL
                         CHECK (pricing_mode IN ('structured', 'text_only', 'none')),
    currency             char(3),
    tax_included         boolean,
    info_text            text,
    disclaimer_override  text,
    updated_at           timestamptz NOT NULL DEFAULT now(),
    CHECK (pricing_mode <> 'structured' OR currency IS NOT NULL),
    CHECK (pricing_mode <> 'text_only' OR info_text IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS mcp.service_price_rule (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    service_id            integer NOT NULL
                          REFERENCES mcp.service_pricing_policy (service_id) ON DELETE RESTRICT,
    label                 text NOT NULL,
    weekdays              smallint[] NOT NULL,
    start_minute          smallint NOT NULL,
    end_minute            smallint NOT NULL,
    valid_from            date NOT NULL,
    valid_to              date,
    min_party_size        smallint,
    max_party_size        smallint,
    min_duration_min      smallint,
    max_duration_min      smallint,
    dimension_conditions  jsonb,
    amount                numeric(12, 2) NOT NULL CHECK (amount >= 0),
    calculation_basis     text NOT NULL
                          CHECK (calculation_basis IN ('per_booking', 'per_person')),
    is_starting_price     boolean NOT NULL DEFAULT false,
    priority              smallint NOT NULL DEFAULT 0,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    CHECK (start_minute >= 0 AND end_minute <= 1440 AND start_minute < end_minute),
    CHECK (cardinality(weekdays) > 0 AND weekdays <@ ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[]),
    CHECK (valid_to IS NULL OR valid_from <= valid_to),
    CHECK (min_party_size IS NULL OR max_party_size IS NULL OR min_party_size <= max_party_size),
    CHECK (min_duration_min IS NULL OR max_duration_min IS NULL OR min_duration_min <= max_duration_min)
);

CREATE INDEX IF NOT EXISTS ix_price_rule_lookup
    ON mcp.service_price_rule (service_id, valid_from, valid_to);

-- =====================================================================
-- 4. TABLAS OPERACIONALES: RESERVAS E HISTÓRICO
-- =====================================================================

CREATE TABLE IF NOT EXISTS mcp.booking_request (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_uuid            uuid NOT NULL, -- Corresponde a public.users.uuid
    service_id           integer NOT NULL REFERENCES public.servicios (id) ON DELETE RESTRICT,
    contract_version_id  uuid NOT NULL REFERENCES mcp.service_contract_version (id) ON DELETE RESTRICT,
    status               text NOT NULL DEFAULT 'requested'
                         CHECK (status IN ('requested', 'confirmed', 'rejected', 'failed',
                                           'expired', 'cancel_requested', 'cancelled')),
    status_reason        text,
    idempotency_key      text NOT NULL,
    request_fingerprint  text NOT NULL,
    token_id             text NOT NULL UNIQUE,
    offer_ref            text NOT NULL,
    hold_id              text,
    slot_start           timestamptz NOT NULL,
    slot_end             timestamptz,
    resource_ref         text,
    applied_filters      jsonb NOT NULL DEFAULT '{}'::jsonb,
    fields               jsonb NOT NULL DEFAULT '{}'::jsonb,
    price_estimate       jsonb,
    expires_at           timestamptz NOT NULL,
    external_ref         text,
    assigned_details     jsonb,
    last_event_at        timestamptz,
    version              integer NOT NULL DEFAULT 1,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_uuid, idempotency_key),
    CHECK (slot_end IS NULL OR slot_end > slot_start)
);

CREATE INDEX IF NOT EXISTS ix_booking_user_created
    ON mcp.booking_request (user_uuid, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS ix_booking_expiry
    ON mcp.booking_request (expires_at)
    WHERE status = 'requested';

CREATE INDEX IF NOT EXISTS ix_booking_service_slot
    ON mcp.booking_request (service_id, slot_start);

CREATE TABLE IF NOT EXISTS mcp.booking_status_history (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    booking_id   uuid NOT NULL REFERENCES mcp.booking_request (id) ON DELETE RESTRICT,
    from_status  text,
    to_status    text NOT NULL,
    cause        text NOT NULL,
    event_id     uuid,
    occurred_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_status_history_booking
    ON mcp.booking_status_history (booking_id, id);

-- =====================================================================
-- 5. TABLAS TRANSACCIONALES: OUTBOX E INBOX PATTERN
-- =====================================================================

CREATE TABLE IF NOT EXISTS mcp.outbox_event (
    id              uuid PRIMARY KEY,     -- Corresponde al event_id
    aggregate_id    uuid NOT NULL,         -- Corresponde al booking_id (clave de partición)
    event_type      text NOT NULL,
    payload         jsonb NOT NULL,
    correlation_id  text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    published_at    timestamptz,
    attempts        integer NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_outbox_pending
    ON mcp.outbox_event (created_at ASC)
    WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS mcp.inbox_event (
    event_id      uuid PRIMARY KEY,
    event_type    text NOT NULL,
    aggregate_id  uuid,
    received_at   timestamptz NOT NULL DEFAULT now(),
    processed_at  timestamptz
);

-- =====================================================================
-- 6. TRIGGERS DE SEGURIDAD PARA INMUTABILIDAD DE CONTRATOS
-- =====================================================================

CREATE OR REPLACE FUNCTION mcp.trg_contract_version_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'draft' THEN
            RAISE EXCEPTION 'No se puede borrar la versión % (no es borrador)', OLD.id;
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.status <> 'draft' THEN
        IF NOT (OLD.status = 'published' AND NEW.status = 'retired'
                AND (to_jsonb(NEW) - 'status') = (to_jsonb(OLD) - 'status')) THEN
            RAISE EXCEPTION 'La versión de contrato % es inmutable y no se puede modificar', OLD.id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS contract_version_guard ON mcp.service_contract_version;
CREATE TRIGGER contract_version_guard
    BEFORE UPDATE OR DELETE ON mcp.service_contract_version
    FOR EACH ROW EXECUTE FUNCTION mcp.trg_contract_version_guard();

CREATE OR REPLACE FUNCTION mcp.trg_contract_children_draft_only() RETURNS trigger AS $$
DECLARE
    v_version uuid;
    v_status  text;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_version := OLD.contract_version_id;
    ELSE
        v_version := NEW.contract_version_id;
    END IF;
    SELECT status INTO v_status FROM mcp.service_contract_version WHERE id = v_version;
    IF v_status IS NOT NULL AND v_status <> 'draft' THEN
        RAISE EXCEPTION 'La versión de contrato % no es borrador y es inmutable', v_version;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS contract_dimension_draft_only ON mcp.contract_dimension;
CREATE TRIGGER contract_dimension_draft_only
    BEFORE INSERT OR UPDATE OR DELETE ON mcp.contract_dimension
    FOR EACH ROW EXECUTE FUNCTION mcp.trg_contract_children_draft_only();

DROP TRIGGER IF EXISTS contract_dependency_draft_only ON mcp.contract_dimension_dependency;
CREATE TRIGGER contract_dependency_draft_only
    BEFORE INSERT OR UPDATE OR DELETE ON mcp.contract_dimension_dependency
    FOR EACH ROW EXECUTE FUNCTION mcp.trg_contract_children_draft_only();

DROP TRIGGER IF EXISTS contract_value_draft_only ON mcp.contract_dimension_value;
CREATE TRIGGER contract_value_draft_only
    BEFORE INSERT OR UPDATE OR DELETE ON mcp.contract_dimension_value
    FOR EACH ROW EXECUTE FUNCTION mcp.trg_contract_children_draft_only();
