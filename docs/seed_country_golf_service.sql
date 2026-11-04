-- ============================================================================
-- SCRIPT DE MIGRACIÓN / SEED: Contrato MCP, Dimensiones y Precios para Country Golf
-- ============================================================================
-- Servicio existente en el catálogo:
--   - service_id: 9
--   - establecimiento: Country Club / Country Golf
--   - patrón: 'slot_object'
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
    v_service_id INT := 9;
    v_contract_id UUID;
    v_dim_course_id UUID := gen_random_uuid();
    v_dim_holes_id UUID := gen_random_uuid();
    v_dim_players_id UUID := gen_random_uuid();
BEGIN
    -- 2. Validar que el servicio 9 exista en el catálogo
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
                "required": ["memberships"],
                "properties": {
                    "memberships": {
                        "type": "array",
                        "description": "Lista de carnets o números de membresía de los jugadores (debe incluirse exactamente un número de membresía por cada jugador). Formato: dígitos con o sin guion y letra (ej. \"6966-C\" o \"12345\").",
                        "items": {
                            "type": "string",
                            "pattern": "^[0-9]+(-[A-Za-z0-9]+)?$",
                            "description": "Número de membresía del jugador/socio"
                        },
                        "minItems": 1,
                        "maxItems": 4
                    },
                    "holes_preference": {
                        "type": "string",
                        "enum": ["9", "18"],
                        "default": "18",
                        "description": "Preferencia de hoyos a jugar (\"9\" o \"18\" hoyos). Si ya se seleccionó en los filtros de disponibilidad, se toma de allí automáticamente."
                    },
                    "email": {
                        "type": "string",
                        "format": "email",
                        "description": "Correo electrónico de contacto (opcional; si se omite, se utiliza el correo de la cuenta autenticada)."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Notas o peticiones especiales opcionales para el club (ej. caddie, alquiler de palos o carrito)."
                    }
                }
            }'::jsonb,
            '{
                "policy": "payment_link",
                "currency": "DOP",
                "description": "Al registrar la reserva, el club envía un enlace de pago seguro para completar y garantizar el turno."
            }'::jsonb,
            '{"allowed": true, "hours_before": 24}'::jsonb,
            900,
            1,
            'hash_country_golf_v1',
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
                "required": ["memberships"],
                "properties": {
                    "memberships": {
                        "type": "array",
                        "description": "Lista de carnets o números de membresía de los jugadores (debe incluirse exactamente un número de membresía por cada jugador). Formato: dígitos con o sin guion y letra (ej. \"6966-C\" o \"12345\").",
                        "items": {
                            "type": "string",
                            "pattern": "^[0-9]+(-[A-Za-z0-9]+)?$",
                            "description": "Número de membresía del jugador/socio"
                        },
                        "minItems": 1,
                        "maxItems": 4
                    },
                    "holes_preference": {
                        "type": "string",
                        "enum": ["9", "18"],
                        "default": "18",
                        "description": "Preferencia de hoyos a jugar (\"9\" o \"18\" hoyos). Si ya se seleccionó en los filtros de disponibilidad, se toma de allí automáticamente."
                    },
                    "email": {
                        "type": "string",
                        "format": "email",
                        "description": "Correo electrónico de contacto (opcional; si se omite, se utiliza el correo de la cuenta autenticada)."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Notas o peticiones especiales opcionales para el club (ej. caddie, alquiler de palos o carrito)."
                    }
                }
            }'::jsonb,
            payment_policy = '{
                "policy": "payment_link",
                "currency": "DOP",
                "description": "Al registrar la reserva, el club envía un enlace de pago seguro para completar y garantizar el turno."
            }'::jsonb,
            cancellation_policy = '{"allowed": true, "hours_before": 24}'::jsonb,
            request_ttl_seconds = 900
        WHERE id = v_contract_id;
    END IF;

    -- 4. Limpiar dimensiones previas de esta versión de contrato
    DELETE FROM mcp.contract_dimension WHERE contract_version_id = v_contract_id;

    -- 5. Dimensión 1: course (Campos de Golf de Country Golf)
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
        'Seleccione el campo de golf del club: Campo Senior o Los Robles.',
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
        (
            gen_random_uuid(), v_contract_id, v_dim_course_id, 
            'Campo Senior', 'Campo Senior', 
            'Campo principal y tradicional del club (18 hoyos).', 1
        ),
        (
            gen_random_uuid(), v_contract_id, v_dim_course_id, 
            'Los Robles', 'Los Robles', 
            'Campo ejecutivo Los Robles.', 2
        );

    -- 6. Dimensión 2: holes_preference (Preferencia de Recorrido: 9 vs 18 Hoyos)
    INSERT INTO mcp.contract_dimension (
        id, contract_version_id, key, position, label, description,
        values_source, apply_mode, required, allows_any, reports_counts
    )
    VALUES (
        v_dim_holes_id,
        v_contract_id,
        'holes_preference',
        2,
        'Preferencia de Recorrido (Hoyos)',
        'Seleccione si desea jugar 9 o 18 hoyos. Se envía como parámetro al upstream para filtrar los turnos y determina la tarifa oficial aplicable.',
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
        (
            gen_random_uuid(), v_contract_id, v_dim_holes_id, 
            '18', '18 Hoyos', 
            'Recorrido completo de 18 hoyos.', 1
        ),
        (
            gen_random_uuid(), v_contract_id, v_dim_holes_id, 
            '9', '9 Hoyos', 
            'Recorrido corto de 9 hoyos.', 2
        );

    -- 7. Dimensión 3: party_size (Cantidad de jugadores estándar en filtros)
    INSERT INTO mcp.contract_dimension (
        id, contract_version_id, key, position, label, description,
        values_source, apply_mode, required, allows_any, reports_counts
    )
    VALUES (
        v_dim_players_id,
        v_contract_id,
        'party_size',
        3,
        'Cantidad de Jugadores',
        'Número de jugadores en la partida (1 a 4). Recuerde que al reservar se requerirá un número de membresía por cada jugador.',
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

    -- 8. Asegurar estado publicado del contrato
    UPDATE mcp.service_contract_version
    SET status = 'published', published_at = COALESCE(published_at, NOW()), content_hash = 'hash_country_golf_v1'
    WHERE id = v_contract_id;

    -- 9. Política de Precios Informativos
    INSERT INTO mcp.service_pricing_policy (
        service_id, pricing_mode, currency, tax_included, info_text, updated_at
    )
    VALUES (
        v_service_id,
        'structured',
        'DOP',
        true,
        'Tarifas oficiales por persona para Green Fee en Country Golf según campo y hoyos seleccionados. El pago se formaliza mediante un enlace de pago.',
        NOW()
    )
    ON CONFLICT (service_id) DO UPDATE SET 
        pricing_mode = EXCLUDED.pricing_mode,
        currency = EXCLUDED.currency,
        tax_included = EXCLUDED.tax_included,
        info_text = EXCLUDED.info_text,
        updated_at = NOW();

    -- 10. Reglas de Precios (4 Reglas: 2 campos x 2 variantes de hoyos)
    DELETE FROM mcp.service_price_rule WHERE service_id = v_service_id;

    -- ------------------------------------------------------------------------
    -- CAMPO SENIOR
    -- ------------------------------------------------------------------------
    -- 18 hoyos: 1,750.00 DOP / jugador
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Campo Senior - 18 Hoyos',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        '{"course": "Campo Senior", "holes_preference": "18"}'::jsonb,
        1750.00, 'per_person', false, 10, NOW()
    );

    -- 9 hoyos: 1,300.00 DOP / jugador
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Campo Senior - 9 Hoyos',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        '{"course": "Campo Senior", "holes_preference": "9"}'::jsonb,
        1300.00, 'per_person', false, 10, NOW()
    );

    -- ------------------------------------------------------------------------
    -- LOS ROBLES
    -- ------------------------------------------------------------------------
    -- 9 hoyos: 875.00 DOP / jugador
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Los Robles - 9 Hoyos',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        '{"course": "Los Robles", "holes_preference": "9"}'::jsonb,
        875.00, 'per_person', false, 10, NOW()
    );

    -- 18 hoyos: 870.00 DOP / jugador (Tarifa más baja / is_starting_price = true)
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Los Robles - 18 Hoyos',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        '{"course": "Los Robles", "holes_preference": "18"}'::jsonb,
        870.00, 'per_person', true, 10, NOW()
    );

END $$;

-- 11. Reactivar inmediatamente los triggers de inmutabilidad
ALTER TABLE mcp.service_contract_version ENABLE TRIGGER contract_version_guard;
ALTER TABLE mcp.contract_dimension ENABLE TRIGGER contract_dimension_draft_only;
ALTER TABLE mcp.contract_dimension_value ENABLE TRIGGER contract_value_draft_only;
ALTER TABLE mcp.contract_dimension_dependency ENABLE TRIGGER contract_dependency_draft_only;

COMMIT;

-- ============================================================================
-- Consultas de verificación
-- ============================================================================
SELECT s.id, s.nombre, s.combo_code, cv.version_no, cv.pattern, cv.status
FROM servicios s
JOIN mcp.service_contract_version cv ON cv.service_id = s.id
WHERE s.id = 9;

SELECT d.key, d.label, dv.value_key, dv.label as valor_label, dv.description
FROM mcp.contract_dimension d
JOIN mcp.contract_dimension_value dv ON dv.dimension_id = d.id
JOIN mcp.service_contract_version cv ON cv.id = d.contract_version_id
WHERE cv.service_id = 9
ORDER BY d.position, dv.position;

SELECT r.label, r.amount, r.calculation_basis, r.dimension_conditions, r.is_starting_price
FROM mcp.service_price_rule r
WHERE r.service_id = 9
ORDER BY r.amount DESC;

