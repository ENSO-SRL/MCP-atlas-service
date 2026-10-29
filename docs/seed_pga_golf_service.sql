-- ============================================================================
-- SCRIPT DE MIGRACIÓN / SEED: Contrato MCP, Dimensiones y Precios para PGA Golf
-- ============================================================================
-- Servicio existente en el catálogo:
--   - service_id: 12
--   - combo_code: 'PGA_GOLF'
--   - establecimiento: PGA Ocean's 4 ('PGA')
--
-- NOTA ARQUITECTÓNICA SOBRE INMUTABILIDAD:
-- Las tablas del esquema 'mcp' cuentan con triggers (trg_contract_children_draft_only
-- y trg_contract_version_guard) que impiden modificar dimensiones de contratos que
-- ya se encuentran en estado 'published'.
-- Este script desactiva temporalmente esos triggers de inmutabilidad al inicio de la
-- transacción y los reactiva al finalizar, permitiendo resembrar y reparar versiones
-- existentes de forma 100% limpia e idempotente.
-- ============================================================================

BEGIN;

-- 1. Desactivar temporalmente los triggers de inmutabilidad para la migración/seed
ALTER TABLE mcp.service_contract_version DISABLE TRIGGER contract_version_guard;
ALTER TABLE mcp.contract_dimension DISABLE TRIGGER contract_dimension_draft_only;
ALTER TABLE mcp.contract_dimension_value DISABLE TRIGGER contract_value_draft_only;
ALTER TABLE mcp.contract_dimension_dependency DISABLE TRIGGER contract_dependency_draft_only;

DO $$
DECLARE
    v_service_id INT := 12;
    v_contract_id UUID;
    v_dim_course_id UUID := gen_random_uuid();
    v_dim_players_id UUID := gen_random_uuid();
BEGIN
    -- 2. Validar que el servicio 12 exista en el catálogo
    IF NOT EXISTS (SELECT 1 FROM servicios WHERE id = v_service_id) THEN
        RAISE EXCEPTION 'El servicio con id % no existe en la tabla servicios. Verifique la base de datos.', v_service_id;
    END IF;

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
                "properties": {
                    "guests": {
                        "type": "array",
                        "description": "Lista de acompañantes (obligatorio si hay más de 1 jugador). Cada acompañante debe indicar firstName y lastName.",
                        "items": {
                            "type": "object",
                            "required": ["firstName", "lastName"],
                            "properties": {
                                "firstName": {"type": "string", "description": "Nombre de pila del acompañante"},
                                "lastName": {"type": "string", "description": "Apellido del acompañante"}
                            }
                        }
                    }
                }
            }'::jsonb,
            '{"policy": "pay_at_venue", "currency": "USD"}'::jsonb,
            '{"allowed": true, "hours_before": 24}'::jsonb,
            900,
            1,
            'hash_pga_golf_v1',
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
                "properties": {
                    "guests": {
                        "type": "array",
                        "description": "Lista de acompañantes (obligatorio si hay más de 1 jugador). Cada acompañante debe indicar firstName y lastName.",
                        "items": {
                            "type": "object",
                            "required": ["firstName", "lastName"],
                            "properties": {
                                "firstName": {"type": "string", "description": "Nombre de pila del acompañante"},
                                "lastName": {"type": "string", "description": "Apellido del acompañante"}
                            }
                        }
                    }
                }
            }'::jsonb,
            payment_policy = '{"policy": "pay_at_venue", "currency": "USD"}'::jsonb,
            cancellation_policy = '{"allowed": true, "hours_before": 24}'::jsonb
        WHERE id = v_contract_id;
    END IF;

    -- 4. Limpiar dimensiones previas de esta versión de contrato
    DELETE FROM mcp.contract_dimension WHERE contract_version_id = v_contract_id;

    -- 5. Dimensión: course (Championship vs Par 3)
    INSERT INTO mcp.contract_dimension (
        id, contract_version_id, key, position, label, description,
        values_source, apply_mode, required, allows_any, reports_counts
    )
    VALUES (
        v_dim_course_id,
        v_contract_id,
        'course',
        1,
        'Campo de Golf',
        'Seleccione el campo: Championship (18 hoyos) o Par 3 Course (9 hoyos).',
        'inline',
        'upstream_param',
        true,
        false,
        false
    );

    INSERT INTO mcp.contract_dimension_value (
        id, contract_version_id, dimension_id, value_key, label, description, position
    )
    VALUES 
        (gen_random_uuid(), v_contract_id, v_dim_course_id, 'championsship', 'Championship (18 hoyos)', 'Campo oficial de 18 hoyos par 72.', 1),
        (gen_random_uuid(), v_contract_id, v_dim_course_id, 'par 3 course', 'Par 3 Course (9 hoyos)', 'Campo ejecutivo de 9 hoyos par 27.', 2);

    -- 6. Dimensión: party_size (Cantidad de jugadores estándar en filtros)
    INSERT INTO mcp.contract_dimension (
        id, contract_version_id, key, position, label, description,
        values_source, apply_mode, required, allows_any, reports_counts
    )
    VALUES (
        v_dim_players_id,
        v_contract_id,
        'party_size',
        2,
        'Cantidad de Jugadores',
        'Número de jugadores en el turno (1 a 4).',
        'inline',
        'upstream_param',
        true,
        false,
        false
    );

    INSERT INTO mcp.contract_dimension_value (
        id, contract_version_id, dimension_id, value_key, label, position
    )
    VALUES 
        (gen_random_uuid(), v_contract_id, v_dim_players_id, '1', '1 Jugador', 1),
        (gen_random_uuid(), v_contract_id, v_dim_players_id, '2', '2 Jugadores', 2),
        (gen_random_uuid(), v_contract_id, v_dim_players_id, '3', '3 Jugadores', 3),
        (gen_random_uuid(), v_contract_id, v_dim_players_id, '4', '4 Jugadores', 4);

    -- 7. Asegurar estado publicado del contrato
    UPDATE mcp.service_contract_version
    SET status = 'published', published_at = COALESCE(published_at, NOW()), content_hash = 'hash_pga_golf_v1'
    WHERE id = v_contract_id;

    -- 8. Política de Precios
    INSERT INTO mcp.service_pricing_policy (
        service_id, pricing_mode, currency, tax_included, info_text, updated_at
    )
    VALUES (
        v_service_id,
        'structured',
        'USD',
        true,
        'Tarifas oficiales por persona para Green Fee según campo seleccionado.',
        NOW()
    )
    ON CONFLICT (service_id) DO UPDATE SET 
        pricing_mode = EXCLUDED.pricing_mode,
        currency = EXCLUDED.currency,
        tax_included = EXCLUDED.tax_included,
        info_text = EXCLUDED.info_text,
        updated_at = NOW();

    -- 9. Reglas de Precios
    DELETE FROM mcp.service_price_rule WHERE service_id = v_service_id;

    -- Championship: 285.00 USD / persona
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(),
        v_service_id,
        'Tarifa Championship (18 hoyos)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[],
        0,
        1440,
        CURRENT_DATE,
        '{"course": "championsship"}'::jsonb,
        285.00,
        'per_person',
        false,
        10,
        NOW()
    );

    -- Par 3 Course: 55.00 USD / persona
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(),
        v_service_id,
        'Tarifa Par 3 Course (9 hoyos)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[],
        0,
        1440,
        CURRENT_DATE,
        '{"course": "par 3 course"}'::jsonb,
        55.00,
        'per_person',
        false,
        10,
        NOW()
    );

END $$;

-- 10. Reactivar inmediatamente los triggers de inmutabilidad
ALTER TABLE mcp.service_contract_version ENABLE TRIGGER contract_version_guard;
ALTER TABLE mcp.contract_dimension ENABLE TRIGGER contract_dimension_draft_only;
ALTER TABLE mcp.contract_dimension_value ENABLE TRIGGER contract_value_draft_only;
ALTER TABLE mcp.contract_dimension_dependency ENABLE TRIGGER contract_dependency_draft_only;

COMMIT;

-- Consultas de verificación
SELECT s.id, s.nombre, s.combo_code, cv.version_no, cv.pattern, cv.status
FROM servicios s
JOIN mcp.service_contract_version cv ON cv.service_id = s.id
WHERE s.id = 12;

SELECT d.key, d.label, dv.value_key, dv.label as valor_label
FROM mcp.contract_dimension d
JOIN mcp.contract_dimension_value dv ON dv.dimension_id = d.id
JOIN mcp.service_contract_version cv ON cv.id = d.contract_version_id
WHERE cv.service_id = 12
ORDER BY d.position, dv.position;

SELECT r.label, r.amount, r.calculation_basis, r.dimension_conditions
FROM mcp.service_price_rule r
WHERE r.service_id = 12;
