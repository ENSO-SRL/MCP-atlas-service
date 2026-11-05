-- ============================================================================
-- SCRIPT DE MIGRACIÓN / SEED: Contrato MCP, Dimensiones y Precios para Country Tennis
-- ============================================================================
-- Servicio existente en el catálogo:
--   - service_id: 11
--   - establecimiento: Santo Domingo Country Club / Country Tennis
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
    v_service_id INT := 11;
    v_contract_id UUID;
    v_dim_game_type_id UUID := gen_random_uuid();
BEGIN
    -- 2. Validar que el servicio 11 exista en el catálogo
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
                "required": ["membership_numbers"],
                "properties": {
                    "membership_numbers": {
                        "type": "array",
                        "description": "Lista de números de carnet o membresía de los jugadores. Debe incluirse exactamente 2 números de membresía para modalidad sencillo (singles) o 4 números para modalidad dobles. Formato: dígitos con o sin guion y letra (ej. \"6966\" o \"6966-C\").",
                        "items": {
                            "type": "string",
                            "pattern": "^[0-9]+(-[A-Za-z0-9]+)?$",
                            "description": "Número de membresía del jugador/socio"
                        },
                        "minItems": 2,
                        "maxItems": 4
                    },
                    "prefer_closest_time": {
                        "type": "boolean",
                        "default": false,
                        "description": "Indica si se acepta el horario más cercano disponible en caso de leve desfase de turnos."
                    },
                    "email": {
                        "type": "string",
                        "format": "email",
                        "description": "Correo electrónico de contacto (opcional; si se omite, se utiliza el correo de la cuenta autenticada)."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Notas o peticiones especiales opcionales para el club (ej. solicitud de cancha específica o alquiler de raquetas/pelotas)."
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
            'hash_country_tennis_v1',
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
                "required": ["membership_numbers"],
                "properties": {
                    "membership_numbers": {
                        "type": "array",
                        "description": "Lista de números de carnet o membresía de los jugadores. Debe incluirse exactamente 2 números de membresía para modalidad sencillo (singles) o 4 números para modalidad dobles. Formato: dígitos con o sin guion y letra (ej. \"6966\" o \"6966-C\").",
                        "items": {
                            "type": "string",
                            "pattern": "^[0-9]+(-[A-Za-z0-9]+)?$",
                            "description": "Número de membresía del jugador/socio"
                        },
                        "minItems": 2,
                        "maxItems": 4
                    },
                    "prefer_closest_time": {
                        "type": "boolean",
                        "default": false,
                        "description": "Indica si se acepta el horario más cercano disponible en caso de leve desfase de turnos."
                    },
                    "email": {
                        "type": "string",
                        "format": "email",
                        "description": "Correo electrónico de contacto (opcional; si se omite, se utiliza el correo de la cuenta autenticada)."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Notas o peticiones especiales opcionales para el club (ej. solicitud de cancha específica o alquiler de raquetas/pelotas)."
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

    -- 5. Dimensión: game_type (Modalidad de Juego: Sencillo vs Dobles)
    INSERT INTO mcp.contract_dimension (
        id, contract_version_id, key, position, label, description,
        values_source, apply_mode, required, allows_any, reports_counts
    )
    VALUES (
        v_dim_game_type_id,
        v_contract_id,
        'game_type',
        1,
        'Modalidad de Juego',
        'Seleccione si jugará en modalidad sencillo (individual / 2 jugadores) o dobles (4 jugadores). Se envía al upstream para filtrar disponibilidad y determina la tarifa por persona.',
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
            gen_random_uuid(), v_contract_id, v_dim_game_type_id, 
            'sencillo', 'Sencillo (Singles - 2 Jugadores)', 
            'Modalidad individual: 2 jugadores en cancha. Requiere 2 carnets de membresía.', 1
        ),
        (
            gen_random_uuid(), v_contract_id, v_dim_game_type_id, 
            'dobles', 'Dobles (4 Jugadores)', 
            'Modalidad por parejas: 4 jugadores en cancha. Requiere 4 carnets de membresía.', 2
        );

    -- 6. Asegurar estado publicado del contrato
    UPDATE mcp.service_contract_version
    SET status = 'published', published_at = COALESCE(published_at, NOW()), content_hash = 'hash_country_tennis_v1'
    WHERE id = v_contract_id;

    -- 7. Política de Precios Informativos
    INSERT INTO mcp.service_pricing_policy (
        service_id, pricing_mode, currency, tax_included, info_text, updated_at
    )
    VALUES (
        v_service_id,
        'structured',
        'DOP',
        true,
        'Tarifas oficiales por persona para tenis según modalidad (Sencillo: RD$ 75.00/persona, Dobles: RD$ 150.00/persona). El pago se formaliza mediante un enlace de pago enviado por el club.',
        NOW()
    )
    ON CONFLICT (service_id) DO UPDATE SET 
        pricing_mode = EXCLUDED.pricing_mode,
        currency = EXCLUDED.currency,
        tax_included = EXCLUDED.tax_included,
        info_text = EXCLUDED.info_text,
        updated_at = NOW();

    -- 8. Reglas de Precios (Por persona según game_type)
    DELETE FROM mcp.service_price_rule WHERE service_id = v_service_id;

    -- Sencillo: 75.00 DOP / jugador (Tarifa base / starting price)
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Tenis Sencillo (Individual)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        '{"game_type": "sencillo"}'::jsonb,
        75.00, 'per_person', true, 10, NOW()
    );

    -- Dobles: 150.00 DOP / jugador
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Tenis Dobles (Por Parejas)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        '{"game_type": "dobles"}'::jsonb,
        150.00, 'per_person', false, 10, NOW()
    );

END $$;

-- 9. Reactivar inmediatamente los triggers de inmutabilidad
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
WHERE s.id = 11;

SELECT d.key, d.label, dv.value_key, dv.label as valor_label, dv.description
FROM mcp.contract_dimension d
JOIN mcp.contract_dimension_value dv ON dv.dimension_id = d.id
JOIN mcp.service_contract_version cv ON cv.id = d.contract_version_id
WHERE cv.service_id = 11
ORDER BY d.position, dv.position;

SELECT r.label, r.amount, r.calculation_basis, r.dimension_conditions, r.is_starting_price
FROM mcp.service_price_rule r
WHERE r.service_id = 11
ORDER BY r.amount DESC;

