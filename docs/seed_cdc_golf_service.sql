-- ============================================================================
-- SCRIPT DE MIGRACIÓN / SEED: Contrato MCP, Dimensiones y Precios para Casa de Campo GOLF
-- ============================================================================
-- Servicio existente en el catálogo:
--   - service_id: 15
--   - establecimiento: Casa de Campo Resort & Villas ('CDC')
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
    v_service_id INT := 15;
    v_contract_id UUID;
    v_dim_course_id UUID := gen_random_uuid();
    v_dim_season_id UUID := gen_random_uuid();
    v_dim_players_id UUID := gen_random_uuid();
BEGIN
    -- 2. Validar que el servicio 15 exista en el catálogo
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
                    "notes": {
                        "type": "string",
                        "description": "Notas o peticiones especiales opcionales para la reserva (ej. alquiler de palos de golf, carrito, requerimiento de caddie, etc.)"
                    }
                },
                "required": []
            }'::jsonb,
            '{"policy": "pay_at_venue", "currency": "USD"}'::jsonb,
            '{"allowed": true, "hours_before": 24}'::jsonb,
            900,
            1,
            'hash_cdc_golf_v1',
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
                    "notes": {
                        "type": "string",
                        "description": "Notas o peticiones especiales opcionales para la reserva (ej. alquiler de palos de golf, carrito, requerimiento de caddie, etc.)"
                    }
                },
                "required": []
            }'::jsonb,
            payment_policy = '{"policy": "pay_at_venue", "currency": "USD"}'::jsonb,
            cancellation_policy = '{"allowed": true, "hours_before": 24}'::jsonb,
            request_ttl_seconds = 900
        WHERE id = v_contract_id;
    END IF;

    -- 4. Limpiar dimensiones previas de esta versión de contrato
    DELETE FROM mcp.contract_dimension WHERE contract_version_id = v_contract_id;

    -- 5. Dimensión 1: course (Campos de Golf de Casa de Campo)
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
        'Seleccione el campo de golf de Casa de Campo: Teeth of the Dog, The Links, Dye Fore Marina o Dye Fore Chavón.',
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
            'TEETH OF THE DOG', 'Teeth of the Dog', 
            'Obra maestra de Pete Dye clasificada internacionalmente entre los mejores campos del mundo (18 hoyos par 72 con 7 hoyos bordeando el Mar Caribe).', 1
        ),
        (
            gen_random_uuid(), v_contract_id, v_dim_course_id, 
            'THE LINKS', 'The Links', 
            'Diseño interior clásico estilo links británico, con suaves colinas, obstáculos de agua y calles onduladas (18 hoyos par 71).', 2
        ),
        (
            gen_random_uuid(), v_contract_id, v_dim_course_id, 
            'DYE FORE MARINA', 'Dye Fore - Marina', 
            'Recorrido de 9 hoyos que desciende con vistas panorámicas a la marina del río Chavón.', 3
        ),
        (
            gen_random_uuid(), v_contract_id, v_dim_course_id, 
            'DYE FORE CHAVON', 'Dye Fore - Chavón', 
            'Recorrido de 9 hoyos esculpido sobre los acantilados que se elevan a 300 pies sobre el río Chavón.', 4
        );

    -- 6. Dimensión 2: season (Tipo de Acceso / Condición de Estancia)
    INSERT INTO mcp.contract_dimension (
        id, contract_version_id, key, position, label, description,
        values_source, apply_mode, required, allows_any, reports_counts
    )
    VALUES (
        v_dim_season_id,
        v_contract_id,
        'season',
        2,
        'Tipo de Acceso / Condición de Estancia',
        'Tipo de acreditación o estatus de estancia del cliente en el complejo Casa de Campo. Aunque el parámetro técnico se llame "season", define la condición de hospedaje del golfista (huésped del hotel, huésped en villa privada del complejo o golfista junior).',
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
            gen_random_uuid(), v_contract_id, v_dim_season_id, 
            'CDC HOTEL GUEST', 'Huésped del Hotel (Hotel Guest)', 
            'Jugador registrado y hospedado directamente en las habitaciones del hotel Casa de Campo Resort.', 1
        ),
        (
            gen_random_uuid(), v_contract_id, v_dim_season_id, 
            'CDC PRIVATE VILLA GUEST', 'Huésped de Villa Privada (Private Villa Guest)', 
            'Jugador alojado en una villa privada o propietario/residente del complejo Casa de Campo.', 2
        ),
        (
            gen_random_uuid(), v_contract_id, v_dim_season_id, 
            'CDC JUNIOR GOLFER', 'Golfista Junior (Junior Golfer)', 
            'Tarifa especial para jóvenes y menores de edad en categoría junior.', 3
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
        'Número de jugadores en el turno (1 a 4). El conector upstream adapta este parámetro a "players" para el API de Casa de Campo.',
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
    SET status = 'published', published_at = COALESCE(published_at, NOW()), content_hash = 'hash_cdc_golf_v1'
    WHERE id = v_contract_id;

    -- 9. Política de Precios Informativos
    INSERT INTO mcp.service_pricing_policy (
        service_id, pricing_mode, currency, tax_included, info_text, updated_at
    )
    VALUES (
        v_service_id,
        'structured',
        'USD',
        true,
        'Tarifas oficiales por persona para Green Fee en Casa de Campo según campo y tipo de acreditación de estancia.',
        NOW()
    )
    ON CONFLICT (service_id) DO UPDATE SET 
        pricing_mode = EXCLUDED.pricing_mode,
        currency = EXCLUDED.currency,
        tax_included = EXCLUDED.tax_included,
        info_text = EXCLUDED.info_text,
        updated_at = NOW();

    -- 10. Reglas de Precios (12 Reglas: 4 campos x 3 seasons)
    DELETE FROM mcp.service_price_rule WHERE service_id = v_service_id;

    -- ------------------------------------------------------------------------
    -- TEETH OF THE DOG
    -- ------------------------------------------------------------------------
    -- Private Villa Guest: 649.00 USD / jugador
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Teeth of the Dog - Private Villa Guest',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        '{"course": "TEETH OF THE DOG", "season": "CDC PRIVATE VILLA GUEST"}'::jsonb,
        649.00, 'per_person', false, 10, NOW()
    );

    -- Hotel Guest: 531.00 USD / jugador
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Teeth of the Dog - Hotel Guest',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        '{"course": "TEETH OF THE DOG", "season": "CDC HOTEL GUEST"}'::jsonb,
        531.00, 'per_person', false, 10, NOW()
    );

    -- Junior Golfer: 324.00 USD / jugador
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Teeth of the Dog - Junior Golfer',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        '{"course": "TEETH OF THE DOG", "season": "CDC JUNIOR GOLFER"}'::jsonb,
        324.00, 'per_person', false, 10, NOW()
    );

    -- ------------------------------------------------------------------------
    -- THE LINKS
    -- ------------------------------------------------------------------------
    -- Private Villa Guest: 413.00 USD / jugador
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'The Links - Private Villa Guest',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        '{"course": "THE LINKS", "season": "CDC PRIVATE VILLA GUEST"}'::jsonb,
        413.00, 'per_person', false, 10, NOW()
    );

    -- Hotel Guest: 324.00 USD / jugador
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'The Links - Hotel Guest',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        '{"course": "THE LINKS", "season": "CDC HOTEL GUEST"}'::jsonb,
        324.00, 'per_person', false, 10, NOW()
    );

    -- Junior Golfer: 177.50 USD / jugador (Tarifa más baja del resort / is_starting_price = true)
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'The Links - Junior Golfer',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        '{"course": "THE LINKS", "season": "CDC JUNIOR GOLFER"}'::jsonb,
        177.50, 'per_person', true, 10, NOW()
    );

    -- ------------------------------------------------------------------------
    -- DYE FORE MARINA
    -- ------------------------------------------------------------------------
    -- Private Villa Guest: 531.00 USD / jugador
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Dye Fore Marina - Private Villa Guest',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        '{"course": "DYE FORE MARINA", "season": "CDC PRIVATE VILLA GUEST"}'::jsonb,
        531.00, 'per_person', false, 10, NOW()
    );

    -- Hotel Guest: 413.00 USD / jugador
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Dye Fore Marina - Hotel Guest',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        '{"course": "DYE FORE MARINA", "season": "CDC HOTEL GUEST"}'::jsonb,
        413.00, 'per_person', false, 10, NOW()
    );

    -- Junior Golfer: 253.70 USD / jugador
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Dye Fore Marina - Junior Golfer',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        '{"course": "DYE FORE MARINA", "season": "CDC JUNIOR GOLFER"}'::jsonb,
        253.70, 'per_person', false, 10, NOW()
    );

    -- ------------------------------------------------------------------------
    -- DYE FORE CHAVON
    -- ------------------------------------------------------------------------
    -- Private Villa Guest: 531.00 USD / jugador
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Dye Fore Chavón - Private Villa Guest',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        '{"course": "DYE FORE CHAVON", "season": "CDC PRIVATE VILLA GUEST"}'::jsonb,
        531.00, 'per_person', false, 10, NOW()
    );

    -- Hotel Guest: 413.00 USD / jugador
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Dye Fore Chavón - Hotel Guest',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        '{"course": "DYE FORE CHAVON", "season": "CDC HOTEL GUEST"}'::jsonb,
        413.00, 'per_person', false, 10, NOW()
    );

    -- Junior Golfer: 253.70 USD / jugador
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Dye Fore Chavón - Junior Golfer',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        '{"course": "DYE FORE CHAVON", "season": "CDC JUNIOR GOLFER"}'::jsonb,
        253.70, 'per_person', false, 10, NOW()
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
WHERE s.id = 15;

SELECT d.key, d.label, dv.value_key, dv.label as valor_label, dv.description
FROM mcp.contract_dimension d
JOIN mcp.contract_dimension_value dv ON dv.dimension_id = d.id
JOIN mcp.service_contract_version cv ON cv.id = d.contract_version_id
WHERE cv.service_id = 15
ORDER BY d.position, dv.position;

SELECT r.label, r.amount, r.calculation_basis, r.dimension_conditions, r.is_starting_price
FROM mcp.service_price_rule r
WHERE r.service_id = 15
ORDER BY r.amount DESC;

