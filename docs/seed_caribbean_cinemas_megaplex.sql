-- ============================================================================
-- SCRIPT DE MIGRACIÓN / SEED: Contrato MCP, Dimensiones y Precios para Caribbean Cinemas Megaplex 10
-- ============================================================================
-- Servicio existente en el catálogo:
--   - service_id: 87
--   - establecimiento: Caribbean Cinemas
--   - nombre servicio: 'Megaplex 10'
--   - combo_code: 'cc_megaplex_10'
--   - patrón: 'slot_object' (cada función/tanda 'showing_id' es un slot)
--   - regla de antelación (rule_type): NULL (disponibilidad inmediata según cartelera)
--
-- DIMENSIONES DE DISPONIBILIDAD:
--   1. 'movie' (Película en Cartelera): values_source = 'separate_query', resolver_ref = 'cc_movies'.
--      Permite a Claude listar las películas vigentes proyectadas en Megaplex 10.
--   2. 'party_size' (Cantidad de Boletos / Asientos): values_source = 'inline' (1 a 10),
--      permite calcular el precio proyectado exacto durante check_availability.
--
-- ESQUEMA TARIFARIO POR PERSONA (calculation_basis: 'per_person'):
--   - Adulto (Tarifa General):  RD$ 350.00
--   - Adulto CXC:               RD$ 400.00
--   El cálculo proyectado toma la tarifa general (party_size * RD$ 350.00).
--
-- FORMULARIO DE RESERVA:
--   - seat_count: integer (1-10) obligatoria.
--   - seat_mode: 'mejor' (por defecto) o 'seleccion'.
--   - seat_labels: array de strings (requerido solo si seat_mode es 'seleccion').
--   - first_name, last_name: opcionales (toman los datos de la cuenta si no se envían).
-- ============================================================================

BEGIN;

-- 1. Desactivar temporalmente los triggers de inmutabilidad para la migración/seed
ALTER TABLE mcp.service_contract_version DISABLE TRIGGER contract_version_guard;
ALTER TABLE mcp.contract_dimension DISABLE TRIGGER contract_dimension_draft_only;
ALTER TABLE mcp.contract_dimension_value DISABLE TRIGGER contract_value_draft_only;
ALTER TABLE mcp.contract_dimension_dependency DISABLE TRIGGER contract_dependency_draft_only;

DO $$
DECLARE
    v_service_id INT := 87;
    v_contract_id UUID;
    v_dim_movie_id UUID := gen_random_uuid();
    v_dim_party_id UUID := gen_random_uuid();
BEGIN
    -- 2. Validar que el servicio 87 exista en el catálogo
    IF NOT EXISTS (SELECT 1 FROM servicios WHERE id = v_service_id) THEN
        RAISE EXCEPTION 'El servicio con id % no existe en la tabla servicios. Verifique la base de datos.', v_service_id;
    END IF;

    -- 2.1 Asegurar que el establecimiento asociado tenga rule_type = NULL (sin esquema restrictivo)
    UPDATE establishments
    SET rule_type = NULL,
        has_scheduler = false,
        updated_at = NOW()
    WHERE id = (SELECT establishment_id FROM servicios WHERE id = v_service_id);

    -- 3. Contrato de Servicio (mcp.service_contract_version)
    SELECT id INTO v_contract_id 
    FROM mcp.service_contract_version 
    WHERE service_id = v_service_id AND version_no = 1;

    IF v_contract_id IS NULL THEN
        v_contract_id := gen_random_uuid();
        INSERT INTO mcp.service_contract_version (
            id, service_id, version_no, status, pattern, booking_fields_schema,
            payment_policy, cancellation_policy, request_ttl_seconds, meta_schema_version,
            content_hash, published_at, created_at
        )
        VALUES (
            v_contract_id,
            v_service_id,
            1,
            'draft',
            'slot_object',
            '{
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "required": ["seat_count", "seat_mode"],
                "properties": {
                    "seat_count": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "description": "Cantidad de boletos o asientos a reservar."
                    },
                    "seat_mode": {
                        "type": "string",
                        "enum": ["mejor", "seleccion"],
                        "default": "mejor",
                        "description": "Modo de asignación: ''mejor'' (asigna automáticamente las mejores butacas contiguas disponibles) o ''seleccion'' (especifica manualmente las butacas elegidas en ''seat_labels'')."
                    },
                    "seat_labels": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "pattern": "^[A-Za-z][0-9]{1,2}$",
                            "description": "Identificador de butaca (ej. ''F6'', ''F7'')."
                        },
                        "description": "Etiquetas de las butacas elegidas (ej. [\"F6\", \"F7\"]). Requerido únicamente cuando seat_mode es ''seleccion''."
                    },
                    "first_name": {
                        "type": "string",
                        "description": "Nombre de quien recoge las entradas o titular de la reserva (opcional; si se omite, se usa el nombre de la cuenta)."
                    },
                    "last_name": {
                        "type": "string",
                        "description": "Apellido del titular de la reserva (opcional)."
                    }
                }
            }'::jsonb,
            '{
                "policy": "payment_link",
                "currency": "DOP",
                "description": "Al confirmar la reserva, Caribbean Cinemas remite un enlace de pago digital para emitir los boletos electrónicos con código QR."
            }'::jsonb,
            '{"allowed": false, "description": "Las entradas de cine para tandas confirmadas no admiten devolución ni cancelación tras la emisión de boletos."}'::jsonb,
            600,
            1,
            'hash_cc_megaplex_10_v1',
            NOW(),
            NOW()
        );
    ELSE
        UPDATE mcp.service_contract_version
        SET 
            pattern = 'slot_object',
            booking_fields_schema = '{
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "required": ["seat_count", "seat_mode"],
                "properties": {
                    "seat_count": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "description": "Cantidad de boletos o asientos a reservar."
                    },
                    "seat_mode": {
                        "type": "string",
                        "enum": ["mejor", "seleccion"],
                        "default": "mejor",
                        "description": "Modo de asignación: ''mejor'' (asigna automáticamente las mejores butacas contiguas disponibles) o ''seleccion'' (especifica manualmente las butacas elegidas en ''seat_labels'')."
                    },
                    "seat_labels": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "pattern": "^[A-Za-z][0-9]{1,2}$",
                            "description": "Identificador de butaca (ej. ''F6'', ''F7'')."
                        },
                        "description": "Etiquetas de las butacas elegidas (ej. [\"F6\", \"F7\"]). Requerido únicamente cuando seat_mode es ''seleccion''."
                    },
                    "first_name": {
                        "type": "string",
                        "description": "Nombre de quien recoge las entradas o titular de la reserva (opcional; si se omite, se usa el nombre de la cuenta)."
                    },
                    "last_name": {
                        "type": "string",
                        "description": "Apellido del titular de la reserva (opcional)."
                    }
                }
            }'::jsonb,
            payment_policy = '{
                "policy": "payment_link",
                "currency": "DOP",
                "description": "Al confirmar la reserva, Caribbean Cinemas remite un enlace de pago digital para emitir los boletos electrónicos con código QR."
            }'::jsonb,
            cancellation_policy = '{"allowed": false, "description": "Las entradas de cine para tandas confirmadas no admiten devolución ni cancelación tras la emisión de boletos."}'::jsonb,
            request_ttl_seconds = 600
        WHERE id = v_contract_id;
    END IF;

    -- 4. Limpiar dimensiones previas de esta versión de contrato
    DELETE FROM mcp.contract_dimension WHERE contract_version_id = v_contract_id;

    -- 5. Dimensión 1: movie (Película en Cartelera - separate_query)
    INSERT INTO mcp.contract_dimension (
        id, contract_version_id, key, position, label, description,
        values_source, apply_mode, required, allows_any, reports_counts, resolver_ref
    )
    VALUES (
        v_dim_movie_id,
        v_contract_id,
        'movie',
        1,
        'Película en Cartelera',
        'Película proyectada en Caribbean Cinemas Megaplex 10. Consulta la cartelera vigente usando get_dimension_options(service_id=87, dimension_key=''movie''). Requerido para consultar tandas.',
        'separate_query',
        'upstream_param',
        true,
        false,
        false,
        'cc_movies'
    );

    -- 5.1 Dimensión 2: party_size (Cantidad de Asientos / Boletos)
    INSERT INTO mcp.contract_dimension (
        id, contract_version_id, key, position, label, description,
        values_source, apply_mode, required, allows_any, reports_counts
    )
    VALUES (
        v_dim_party_id,
        v_contract_id,
        'party_size',
        2,
        'Cantidad de Boletos',
        'Cantidad de personas o entradas a reservar (permite proyectar el precio total de la tanda en disponibilidad).',
        'inline',
        'upstream_param',
        false,
        true,
        false
    );

    -- Valores inline para party_size (1 a 10 personas)
    INSERT INTO mcp.contract_dimension_value (
        id, contract_version_id, dimension_id, value_key, label, description, position
    )
    VALUES 
        (gen_random_uuid(), v_contract_id, v_dim_party_id, '1', '1 Boleto', '1 entrada individual', 1),
        (gen_random_uuid(), v_contract_id, v_dim_party_id, '2', '2 Boletos', '2 entradas para la tanda', 2),
        (gen_random_uuid(), v_contract_id, v_dim_party_id, '3', '3 Boletos', '3 entradas para la tanda', 3),
        (gen_random_uuid(), v_contract_id, v_dim_party_id, '4', '4 Boletos', '4 entradas para la tanda', 4),
        (gen_random_uuid(), v_contract_id, v_dim_party_id, '5', '5 Boletos', '5 entradas para la tanda', 5),
        (gen_random_uuid(), v_contract_id, v_dim_party_id, '6', '6 Boletos', '6 entradas para la tanda', 6),
        (gen_random_uuid(), v_contract_id, v_dim_party_id, '7', '7 Boletos', '7 entradas para la tanda', 7),
        (gen_random_uuid(), v_contract_id, v_dim_party_id, '8', '8 Boletos', '8 entradas para la tanda', 8),
        (gen_random_uuid(), v_contract_id, v_dim_party_id, '9', '9 Boletos', '9 entradas para la tanda', 9),
        (gen_random_uuid(), v_contract_id, v_dim_party_id, '10', '10 Boletos', '10 entradas para la tanda', 10);

    -- 6. Publicar versión del contrato si estaba en borrador
    UPDATE mcp.service_contract_version 
    SET status = 'published', published_at = NOW()
    WHERE id = v_contract_id;

    -- 7. Política General de Precios (mcp.service_pricing_policy)
    INSERT INTO mcp.service_pricing_policy (
        service_id, pricing_mode, currency, tax_included, info_text, updated_at
    )
    VALUES (
        v_service_id,
        'structured',
        'DOP',
        true,
        'Tarifas oficiales Caribbean Cinemas Megaplex 10: Adulto: RD$ 350.00, Adulto CXC: RD$ 400.00. El precio calculado automático toma la tarifa general de Adulto (RD$ 350.00 por entrada).',
        NOW()
    )
    ON CONFLICT (service_id) DO UPDATE SET 
        pricing_mode = EXCLUDED.pricing_mode,
        currency = EXCLUDED.currency,
        tax_included = EXCLUDED.tax_included,
        info_text = EXCLUDED.info_text,
        updated_at = NOW();

    -- 8. Reglas de Precios por Persona (mcp.service_price_rule)
    DELETE FROM mcp.service_price_rule WHERE service_id = v_service_id;

    -- Regla Principal: Tarifa Adulto (RD$ 350.00 por persona)
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Tarifa Adulto',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        350.00, 'per_person', false, 10, NOW()
    );

    -- Regla Secundaria / Informativa: Tarifa Adulto CXC (RD$ 400.00 por persona)
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Tarifa Adulto CXC',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        400.00, 'per_person', false, 4, NOW()
    );

END $$;

-- 9. Reactivar los triggers de inmutabilidad
ALTER TABLE mcp.service_contract_version ENABLE TRIGGER contract_version_guard;
ALTER TABLE mcp.contract_dimension ENABLE TRIGGER contract_dimension_draft_only;
ALTER TABLE mcp.contract_dimension_value ENABLE TRIGGER contract_value_draft_only;
ALTER TABLE mcp.contract_dimension_dependency ENABLE TRIGGER contract_dependency_draft_only;

COMMIT;

-- ============================================================================
-- VERIFICACIÓN
-- ============================================================================
SELECT 
    v.service_id,
    v.version_no,
    v.status,
    v.pattern,
    jsonb_pretty(v.booking_fields_schema) AS booking_fields,
    (SELECT count(*) FROM mcp.contract_dimension d WHERE d.contract_version_id = v.id) AS total_dimensions,
    (SELECT count(*) FROM mcp.service_price_rule r WHERE r.service_id = v.service_id) AS total_price_rules
FROM mcp.service_contract_version v
WHERE v.service_id = 87;

SELECT 
    d.key,
    d.label,
    d.values_source,
    d.resolver_ref,
    d.required,
    d.allows_any
FROM mcp.contract_dimension d
WHERE d.contract_version_id = (SELECT id FROM mcp.service_contract_version WHERE service_id = 87 AND version_no = 1)
ORDER BY d.position;

SELECT 
    r.label,
    r.amount || ' DOP (' || r.calculation_basis || ')' AS pricing,
    r.priority,
    r.is_starting_price
FROM mcp.service_price_rule r
WHERE r.service_id = 87
ORDER BY r.priority DESC, r.amount ASC;
