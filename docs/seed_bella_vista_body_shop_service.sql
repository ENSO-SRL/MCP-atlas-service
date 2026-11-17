-- ============================================================================
-- SCRIPT DE MIGRACIÓN / SEED: Contrato MCP, Dimensiones y Precios para Bella Vista | Body Shop Padel Club
-- ============================================================================
-- Pasarela: PlayByPoint (establishment_id: 13)
-- Servicio en catálogo:
--   - service_id: 23
--   - establecimiento: Bella Vista | Body Shop Padel Club (combo_code: 'bvb', sub_endpoint: 'BODY_SHOP_BELLA_VISTA')
--   - patrón: 'slot_object'
--   - regla de antelación (rule_type): NULL (sin restricciones arbitrarias de antelación)
--
-- DIMENSIÓN DE DISPONIBILIDAD:
--   - type: 'PADEL'
--
-- CAPACIDAD Y PRECALCULO TARIFARIO (calculation_basis: 'per_booking', 90 min):
--   El club exige obligatoriamente 4 jugadores en cancha.
--   Para optimizar la experiencia, se omite la dimensión 'party_size' y se precalcula
--   el costo total de la reserva para los 4 jugadores en turnos de 90 minutos:
--   - Lunes a Viernes:
--       * 05:00 AM – 05:00 PM: RD$ 3,600.00 (4 x RD$ 900.00 / persona)
--       * 05:00 PM – 10:00 PM: RD$ 4,200.00 (4 x RD$ 1,050.00 / persona)
--   - Fines de Semana (Sábado y Domingo):
--       * Todo el día: RD$ 4,200.00 (4 x RD$ 1,050.00 / persona)
--   - Regla Base Fallback: RD$ 3,600.00 (cancha completa)
--
-- REGLA DEL FORMULARIO DE RESERVA:
--   El usuario autenticado que genera la reserva es el 1er jugador.
--   El campo 'users' es obligatorio y exige registrar exactamente a los 3 acompañantes
--   (minItems: 3, maxItems: 3) para cumplir los 4 jugadores requeridos por el club.
-- ============================================================================

BEGIN;

-- 1. Desactivar temporalmente los triggers de inmutabilidad para la migración/seed
ALTER TABLE mcp.service_contract_version DISABLE TRIGGER contract_version_guard;
ALTER TABLE mcp.contract_dimension DISABLE TRIGGER contract_dimension_draft_only;
ALTER TABLE mcp.contract_dimension_value DISABLE TRIGGER contract_value_draft_only;
ALTER TABLE mcp.contract_dimension_dependency DISABLE TRIGGER contract_dependency_draft_only;

DO $$
DECLARE
    v_service_id INT := 23;
    v_contract_id UUID;
    v_dim_type_id UUID := gen_random_uuid();
BEGIN
    -- 2. Validar que el servicio 23 exista en el catálogo
    IF NOT EXISTS (SELECT 1 FROM servicios WHERE id = v_service_id) THEN
        RAISE EXCEPTION 'El servicio con id % no existe en la tabla servicios. Verifique la base de datos.', v_service_id;
    END IF;

    -- 2.1 Asegurar que el establecimiento asociado tenga rule_type = NULL (PlayByPoint)
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
                "required": ["users"],
                "properties": {
                    "users": {
                        "type": "array",
                        "title": "Jugadores Acompañantes",
                        "description": "Bella Vista | Body Shop Padel Club requiere obligatoriamente 4 personas en cancha para turnos de 90 minutos. El titular autenticado de la reserva es el primer jugador, por lo que aquí se deben incluir obligatoriamente los nombres de los 3 jugadores acompañantes.",
                        "minItems": 3,
                        "maxItems": 3,
                        "items": {
                            "type": "object",
                            "required": ["user_name"],
                            "properties": {
                                "user_name": {
                                    "type": "string",
                                    "minLength": 2,
                                    "maxLength": 100,
                                    "description": "Nombre y apellido del jugador acompañante"
                                }
                            }
                        }
                    },
                    "prefer_closest_time": {
                        "type": "boolean",
                        "default": true,
                        "description": "Indica si se acepta el horario más cercano disponible en caso de leve desfase o discrepancia de turnos."
                    }
                }
            }'::jsonb,
            '{
                "policy": "payment_link",
                "currency": "DOP",
                "description": "Al confirmar la reserva, Bella Vista | Body Shop Padel Club remite un enlace de pago digital seguro de PlayByPoint para garantizar el turno."
            }'::jsonb,
            '{"allowed": true, "hours_before": 24}'::jsonb,
            900,
            1,
            'hash_bella_vista_body_shop_v1',
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
                "required": ["users"],
                "properties": {
                    "users": {
                        "type": "array",
                        "title": "Jugadores Acompañantes",
                        "description": "Bella Vista | Body Shop Padel Club requiere obligatoriamente 4 personas en cancha para turnos de 90 minutos. El titular autenticado de la reserva es el primer jugador, por lo que aquí se deben incluir obligatoriamente los nombres de los 3 jugadores acompañantes.",
                        "minItems": 3,
                        "maxItems": 3,
                        "items": {
                            "type": "object",
                            "required": ["user_name"],
                            "properties": {
                                "user_name": {
                                    "type": "string",
                                    "minLength": 2,
                                    "maxLength": 100,
                                    "description": "Nombre y apellido del jugador acompañante"
                                }
                            }
                        }
                    },
                    "prefer_closest_time": {
                        "type": "boolean",
                        "default": true,
                        "description": "Indica si se acepta el horario más cercano disponible en caso de leve desfase o discrepancia de turnos."
                    }
                }
            }'::jsonb,
            payment_policy = '{
                "policy": "payment_link",
                "currency": "DOP",
                "description": "Al confirmar la reserva, Bella Vista | Body Shop Padel Club remite un enlace de pago digital seguro de PlayByPoint para garantizar el turno."
            }'::jsonb,
            cancellation_policy = '{"allowed": true, "hours_before": 24}'::jsonb,
            request_ttl_seconds = 900
        WHERE id = v_contract_id;
    END IF;

    -- 4. Limpiar dimensiones previas de esta versión de contrato
    DELETE FROM mcp.contract_dimension WHERE contract_version_id = v_contract_id;

    -- 5. Dimensión: type (Tipo de Cancha: PADEL)
    INSERT INTO mcp.contract_dimension (
        id, contract_version_id, key, position, label, description,
        values_source, apply_mode, required, allows_any, reports_counts
    )
    VALUES (
        v_dim_type_id,
        v_contract_id,
        'type',
        1,
        'Tipo de Cancha',
        'Tipo de cancha de pádel en Bella Vista | Body Shop Padel Club. Parámetro requerido por PlayByPoint.',
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
            gen_random_uuid(), v_contract_id, v_dim_type_id, 
            'PADEL', 'Cancha de Pádel (Padel Court)', 
            'Pistas reglamentarias de pádel en Body Shop Bella Vista (4 jugadores obligatorios).', 1
        );

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
        'Tarifas oficiales por cancha de 90 minutos para 4 jugadores en Bella Vista | Body Shop Padel Club: Lunes a Viernes 05:00 AM – 05:00 PM RD$ 3,600.00 (RD$ 900/pers); Lunes a Viernes 05:00 PM – 10:00 PM RD$ 4,200.00 (RD$ 1,050/pers); Fines de Semana RD$ 4,200.00 (RD$ 1,050/pers). El pago se formaliza mediante enlace digital seguro de PlayByPoint.',
        NOW()
    )
    ON CONFLICT (service_id) DO UPDATE SET 
        pricing_mode = EXCLUDED.pricing_mode,
        currency = EXCLUDED.currency,
        tax_included = EXCLUDED.tax_included,
        info_text = EXCLUDED.info_text,
        updated_at = NOW();

    -- 8. Reglas de Precios Precalculados por Cancha Completa (mcp.service_price_rule)
    DELETE FROM mcp.service_price_rule WHERE service_id = v_service_id;

    -- ========================================================================
    -- FRANJA 1: Lunes a Viernes, 05:00 AM – 05:00 PM (300 min a 1020 min)
    -- RD$ 900 x 4 jugadores = RD$ 3,600.00
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Lunes a Viernes - Día (05:00 AM – 05:00 PM, 4 jugadores / 90 min)',
        ARRAY[1, 2, 3, 4, 5]::smallint[], 300, 1020, CURRENT_DATE,
        3600.00, 'per_booking', true, 10, NOW()
    );

    -- ========================================================================
    -- FRANJA 2: Lunes a Viernes, 05:00 PM – 10:00 PM (1020 min a 1320 min)
    -- RD$ 1,050 x 4 jugadores = RD$ 4,200.00
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Lunes a Viernes - Noche (05:00 PM – 10:00 PM, 4 jugadores / 90 min)',
        ARRAY[1, 2, 3, 4, 5]::smallint[], 1020, 1320, CURRENT_DATE,
        4200.00, 'per_booking', false, 10, NOW()
    );

    -- ========================================================================
    -- FRANJA 3: Fines de Semana (Sábado y Domingo), Todo el día (0 min a 1440 min)
    -- RD$ 1,050 x 4 jugadores = RD$ 4,200.00
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Fin de Semana - Todo el día (Sábado y Domingo, 4 jugadores / 90 min)',
        ARRAY[6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        4200.00, 'per_booking', false, 10, NOW()
    );

    -- ========================================================================
    -- REGLA FALLBACK BASE (prioridad 1): RD$ 3,600.00 (cancha completa 90 min)
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Tarifa Base Estándar - Body Shop Bella Vista (4 jugadores / 90 min)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        3600.00, 'per_booking', true, 1, NOW()
    );

END $$;

-- 9. Reactivar triggers de inmutabilidad
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
WHERE v.service_id = 23;

SELECT 
    d.key,
    d.label,
    d.required,
    d.allows_any,
    json_agg(v.value_key ORDER BY v.position) AS values
FROM mcp.contract_dimension d
JOIN mcp.contract_dimension_value v ON v.dimension_id = d.id
WHERE d.contract_version_id = (SELECT id FROM mcp.service_contract_version WHERE service_id = 23 AND version_no = 1)
GROUP BY d.key, d.label, d.required, d.allows_any;

SELECT 
    r.label,
    r.weekdays,
    r.start_minute || ' - ' || r.end_minute AS minutes_range,
    r.amount || ' DOP (' || r.calculation_basis || ')' AS pricing,
    r.priority
FROM mcp.service_price_rule r
WHERE r.service_id = 23
ORDER BY r.priority DESC, r.start_minute ASC;
