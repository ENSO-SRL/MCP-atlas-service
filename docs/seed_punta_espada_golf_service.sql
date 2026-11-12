-- ============================================================================
-- SCRIPT DE MIGRACIÓN / SEED: Contrato MCP, Dimensiones y Precios para Punta Espada Golf Club
-- ============================================================================
-- Servicio existente en el catálogo:
--   - service_id: 100
--   - establecimiento: Punta Espada (id: 93, code: 'puesp')
--   - nombre servicio: 'Golf de Punta Espada Golf'
--   - combo_code: 'puesp_golf'
--   - patrón: 'slot_object' (tee times / turnos de salida de golf)
--   - regla de antelación (rule_type): NULL (disponibilidad directa según agenda del club)
--
-- REGLA OPERATIVA DE HOYOS:
--   Punta Espada Golf Club acepta actualmente reservas EXCLUSIVAS de 18 hoyos completos.
--   La dimensión 'holes' refleja esta política con valor único 18.
--
-- ESQUEMA TARIFARIO EN DÓLARES (USD):
--   - Tarifa oficial: US$ 550.00 por jugador (calculation_basis: 'per_person').
--   - Moneda: 'USD' (Dólares estadounidenses).
--   - El precio proyectado calcula automáticamente: players * US$ 550.00.
--
-- DIMENSIONES DE DISPONIBILIDAD:
--   1. 'holes' (Preferencia de Hoyos): values_source = 'inline' (valor fijo: 18).
--   2. 'party_size' (Cantidad de Jugadores): values_source = 'inline' (1 a 4 jugadores).
--      Permite calcular la tarifa proyectada en check_availability y se envía a upstream como 'players'.
--
-- FORMULARIO DE RESERVA (booking_fields_schema):
--   - players: integer (1 a 4 jugadores).
--   - holes: integer (enum [18], default 18).
--   - first_name, last_name: strings opcionales (toman los datos de la cuenta si se omiten).
--   - notes: string opcional (peticiones de caddie, alquiler de palos o carritos).
-- ============================================================================

BEGIN;

-- 1. Desactivar temporalmente los triggers de inmutabilidad para la migración/seed
ALTER TABLE mcp.service_contract_version DISABLE TRIGGER contract_version_guard;
ALTER TABLE mcp.contract_dimension DISABLE TRIGGER contract_dimension_draft_only;
ALTER TABLE mcp.contract_dimension_value DISABLE TRIGGER contract_value_draft_only;
ALTER TABLE mcp.contract_dimension_dependency DISABLE TRIGGER contract_dependency_draft_only;

DO $$
DECLARE
    v_service_id INT := 100;
    v_contract_id UUID;
    v_dim_holes_id UUID := gen_random_uuid();
    v_dim_party_id UUID := gen_random_uuid();
BEGIN
    -- 2. Validar que el servicio 100 exista en el catálogo
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
                "properties": {
                    "players": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 4,
                        "default": 1,
                        "description": "Cantidad de jugadores para la partida de golf (1 a 4 jugadores)."
                    },
                    "holes": {
                        "type": "integer",
                        "enum": [18],
                        "default": 18,
                        "description": "Cantidad de hoyos a jugar. Punta Espada Golf Club solo admite reservas de 18 hoyos completos."
                    },
                    "first_name": {
                        "type": "string",
                        "description": "Nombre de pila del jugador principal o titular de la reserva (opcional; si se omite, se usa el de la cuenta)."
                    },
                    "last_name": {
                        "type": "string",
                        "description": "Apellido del jugador principal o titular de la reserva (opcional)."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Notas o peticiones especiales para el club (ej. solicitud de caddie, alquiler de palos Callaway o carritos adicionales)."
                    }
                }
            }'::jsonb,
            '{
                "policy": "payment_link",
                "currency": "USD",
                "description": "Al registrar la reserva, Punta Espada Golf Club remite un enlace de pago digital seguro en USD para completar y garantizar el tee time."
            }'::jsonb,
            '{"allowed": true, "hours_before": 48, "description": "Cancelación permitida sin penalidad hasta 48 horas antes del tee time reservado."}'::jsonb,
            900,
            1,
            'hash_punta_espada_golf_v1',
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
                    "players": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 4,
                        "default": 1,
                        "description": "Cantidad de jugadores para la partida de golf (1 a 4 jugadores)."
                    },
                    "holes": {
                        "type": "integer",
                        "enum": [18],
                        "default": 18,
                        "description": "Cantidad de hoyos a jugar. Punta Espada Golf Club solo admite reservas de 18 hoyos completos."
                    },
                    "first_name": {
                        "type": "string",
                        "description": "Nombre de pila del jugador principal o titular de la reserva (opcional; si se omite, se usa el de la cuenta)."
                    },
                    "last_name": {
                        "type": "string",
                        "description": "Apellido del jugador principal o titular de la reserva (opcional)."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Notas o peticiones especiales para el club (ej. solicitud de caddie, alquiler de palos Callaway o carritos adicionales)."
                    }
                }
            }'::jsonb,
            payment_policy = '{
                "policy": "payment_link",
                "currency": "USD",
                "description": "Al registrar la reserva, Punta Espada Golf Club remite un enlace de pago digital seguro en USD para completar y garantizar el tee time."
            }'::jsonb,
            cancellation_policy = '{"allowed": true, "hours_before": 48, "description": "Cancelación permitida sin penalidad hasta 48 horas antes del tee time reservado."}'::jsonb,
            request_ttl_seconds = 900
        WHERE id = v_contract_id;
    END IF;

    -- 4. Limpiar dimensiones previas de esta versión de contrato
    DELETE FROM mcp.contract_dimension WHERE contract_version_id = v_contract_id;

    -- 5. Dimensión 1: holes (Preferencia de Hoyos - inline fijo en 18)
    INSERT INTO mcp.contract_dimension (
        id, contract_version_id, key, position, label, description,
        values_source, apply_mode, required, allows_any, reports_counts
    )
    VALUES (
        v_dim_holes_id,
        v_contract_id,
        'holes',
        1,
        'Recorrido de Hoyos',
        'Cantidad de hoyos a jugar. Punta Espada Golf Club opera exclusivamente con recorridos de 18 hoyos.',
        'inline',
        'upstream_param',
        true,
        false,
        false
    );

    INSERT INTO mcp.contract_dimension_value (
        id, contract_version_id, dimension_id, value_key, label, description, position
    )
    VALUES (
        gen_random_uuid(), v_contract_id, v_dim_holes_id,
        '18', '18 Hoyos Completos',
        'Recorrido reglamentario Jack Nicklaus Signature de 18 hoyos frente al mar Caribe.', 1
    );

    -- 5.1 Dimensión 2: party_size (Cantidad de Jugadores / Players - inline)
    INSERT INTO mcp.contract_dimension (
        id, contract_version_id, key, position, label, description,
        values_source, apply_mode, required, allows_any, reports_counts
    )
    VALUES (
        v_dim_party_id,
        v_contract_id,
        'party_size',
        2,
        'Cantidad de Jugadores',
        'Número de golfistas para el tee time (permite calcular el precio total proyectado en USD). Se envía a upstream como players.',
        'inline',
        'upstream_param',
        false,
        true,
        false
    );

    -- Valores inline para party_size (1 a 4 jugadores)
    INSERT INTO mcp.contract_dimension_value (
        id, contract_version_id, dimension_id, value_key, label, description, position
    )
    VALUES 
        (gen_random_uuid(), v_contract_id, v_dim_party_id, '1', '1 Jugador', '1 golfista individual', 1),
        (gen_random_uuid(), v_contract_id, v_dim_party_id, '2', '2 Jugadores', 'Pareja de golfistas', 2),
        (gen_random_uuid(), v_contract_id, v_dim_party_id, '3', '3 Jugadores', 'Trío de golfistas', 3),
        (gen_random_uuid(), v_contract_id, v_dim_party_id, '4', '4 Jugadores', 'Foursome completo (4 jugadores)', 4);

    -- 6. Publicar versión del contrato si estaba en borrador
    UPDATE mcp.service_contract_version 
    SET status = 'published', published_at = NOW()
    WHERE id = v_contract_id;

    -- 7. Política General de Precios (mcp.service_pricing_policy) -> Moneda USD
    INSERT INTO mcp.service_pricing_policy (
        service_id, pricing_mode, currency, tax_included, info_text, updated_at
    )
    VALUES (
        v_service_id,
        'structured',
        'USD',
        true,
        'Tarifa oficial Punta Espada Golf Club: US$ 550.00 por jugador para el recorrido completo de 18 hoyos. El pago se formaliza mediante enlace digital seguro en USD.',
        NOW()
    )
    ON CONFLICT (service_id) DO UPDATE SET 
        pricing_mode = EXCLUDED.pricing_mode,
        currency = EXCLUDED.currency,
        tax_included = EXCLUDED.tax_included,
        info_text = EXCLUDED.info_text,
        updated_at = NOW();

    -- 8. Reglas de Precios en USD (mcp.service_price_rule)
    DELETE FROM mcp.service_price_rule WHERE service_id = v_service_id;

    -- Regla Principal: US$ 550.00 por persona para 18 hoyos
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Green Fee 18 Hoyos (Tarifa por Jugador)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        550.00, 'per_person', false, 10, NOW()
    );

END $$;

-- 9. Reactivar los triggers de inmutabilidad
ALTER TABLE mcp.service_contract_version ENABLE TRIGGER contract_version_guard;
ALTER TABLE mcp.contract_dimension ENABLE TRIGGER contract_dimension_draft_only;
ALTER TABLE mcp.contract_dimension_value ENABLE TRIGGER contract_value_draft_only;
ALTER TABLE mcp.contract_dimension_dependency ENABLE TRIGGER contract_dependency_draft_only;

COMMIT;

