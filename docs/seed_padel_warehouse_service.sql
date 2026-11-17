-- ============================================================================
-- SCRIPT DE MIGRACIÓN / SEED: Contrato MCP, Dimensiones y Precios para Padel Warehouse
-- ============================================================================
-- Pasarela: PlayByPoint (establishment_id: 13)
-- Servicio en catálogo:
--   - service_id: 21
--   - establecimiento: Padel Warehouse (combo_code: 'pwh', sub_endpoint: 'PADEL_WAREHOUSE')
--   - patrón: 'slot_object'
--   - regla de antelación (rule_type): NULL (sin restricciones arbitrarias de antelación)
--
-- DIMENSIÓN DE DISPONIBILIDAD:
--   - type: 'OUTDOOR', 'HORARIO B', 'HORARIO A'
--       * HORARIO A y HORARIO B: Exigen obligatoriamente 4 jugadores en cancha.
--       * OUTDOOR: Admite de 1 a 4 jugadores en cancha.
--
-- ESQUEMA TARIFARIO POR CANCHA COMPLETA (calculation_basis: 'per_booking', 90 min):
--   Tarifas escalonadas para el turno completo de 90 minutos:
--   - 06:00 AM – 04:30 PM: RD$ 4,000.00
--   - 04:30 PM – 05:30 PM: RD$ 4,266.67
--   - 05:30 PM – 11:30 PM: RD$ 4,800.00
--   - Regla Base Fallback: RD$ 4,000.00
--
-- REGLA DEL FORMULARIO DE RESERVA:
--   El titular autenticado es siempre el primer jugador en cancha.
--   El campo 'users' admite de 0 a 3 acompañantes para turnos OUTDOOR (1 a 4 jugadores)
--   y exige los 3 acompañantes cuando se selecciona HORARIO A u HORARIO B (4 jugadores).
-- ============================================================================

BEGIN;

-- 1. Desactivar temporalmente los triggers de inmutabilidad para la migración/seed
ALTER TABLE mcp.service_contract_version DISABLE TRIGGER contract_version_guard;
ALTER TABLE mcp.contract_dimension DISABLE TRIGGER contract_dimension_draft_only;
ALTER TABLE mcp.contract_dimension_value DISABLE TRIGGER contract_value_draft_only;
ALTER TABLE mcp.contract_dimension_dependency DISABLE TRIGGER contract_dependency_draft_only;

DO $$
DECLARE
    v_service_id INT := 21;
    v_contract_id UUID;
    v_dim_type_id UUID := gen_random_uuid();
BEGIN
    -- 2. Validar que el servicio 21 exista en el catálogo
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
                "properties": {
                    "users": {
                        "type": "array",
                        "title": "Jugadores Acompañantes",
                        "description": "El titular autenticado es el primer jugador. Para canchas OUTDOOR se admiten de 0 a 3 acompañantes (1 a 4 jugadores). Para turnos de HORARIO A y HORARIO B se requieren obligatoriamente 3 acompañantes (4 jugadores en total).",
                        "minItems": 0,
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
                "description": "Al confirmar la reserva, Padel Warehouse remite un enlace de pago digital seguro de PlayByPoint para garantizar el turno."
            }'::jsonb,
            '{"allowed": true, "hours_before": 24}'::jsonb,
            900,
            1,
            'hash_padel_warehouse_v1',
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
                    "users": {
                        "type": "array",
                        "title": "Jugadores Acompañantes",
                        "description": "El titular autenticado es el primer jugador. Para canchas OUTDOOR se admiten de 0 a 3 acompañantes (1 a 4 jugadores). Para turnos de HORARIO A y HORARIO B se requieren obligatoriamente 3 acompañantes (4 jugadores en total).",
                        "minItems": 0,
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
                "description": "Al confirmar la reserva, Padel Warehouse remite un enlace de pago digital seguro de PlayByPoint para garantizar el turno."
            }'::jsonb,
            cancellation_policy = '{"allowed": true, "hours_before": 24}'::jsonb,
            request_ttl_seconds = 900
        WHERE id = v_contract_id;
    END IF;

    -- 4. Limpiar dimensiones previas de esta versión de contrato
    DELETE FROM mcp.contract_dimension WHERE contract_version_id = v_contract_id;

    -- 5. Dimensión: type (Tipo de Cancha / Horario: OUTDOOR, HORARIO A, HORARIO B)
    INSERT INTO mcp.contract_dimension (
        id, contract_version_id, key, position, label, description,
        values_source, apply_mode, required, allows_any, reports_counts
    )
    VALUES (
        v_dim_type_id,
        v_contract_id,
        'type',
        1,
        'Tipo de Cancha / Horario',
        'Seleccione el tipo de cancha o bloque horario para Padel Warehouse: OUTDOOR (al aire libre, 1-4 jugadores), HORARIO A (4 jugadores) u HORARIO B (4 jugadores). Parámetro requerido por PlayByPoint.',
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
            'OUTDOOR', 'Cancha al Aire Libre (Outdoor - 1 a 4 jugadores)', 
            'Pistas descubiertas con aforo flexible de 1 a 4 personas en cancha.', 1
        ),
        (
            gen_random_uuid(), v_contract_id, v_dim_type_id, 
            'HORARIO A', 'Horario A (4 jugadores obligatorios)', 
            'Franja Horario A que requiere partida formal con 4 jugadores.', 2
        ),
        (
            gen_random_uuid(), v_contract_id, v_dim_type_id, 
            'HORARIO B', 'Horario B (4 jugadores obligatorios)', 
            'Franja Horario B que requiere partida formal con 4 jugadores.', 3
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
        'Tarifas oficiales por cancha de 90 minutos para Padel Warehouse: 06:00 AM – 04:30 PM RD$ 4,000.00; 04:30 PM – 05:30 PM RD$ 4,266.67; 05:30 PM – 11:30 PM RD$ 4,800.00. El pago se formaliza mediante enlace digital de PlayByPoint.',
        NOW()
    )
    ON CONFLICT (service_id) DO UPDATE SET 
        pricing_mode = EXCLUDED.pricing_mode,
        currency = EXCLUDED.currency,
        tax_included = EXCLUDED.tax_included,
        info_text = EXCLUDED.info_text,
        updated_at = NOW();

    -- 8. Reglas de Precios Dinámicos por Cancha Completa (mcp.service_price_rule)
    DELETE FROM mcp.service_price_rule WHERE service_id = v_service_id;

    -- ========================================================================
    -- FRANJA 1: 06:00 AM – 04:30 PM (360 min a 990 min) -> RD$ 4,000.00
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Hora Valle - Mañana y Tarde (06:00 AM – 04:30 PM, 90 mins)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 360, 990, CURRENT_DATE,
        4000.00, 'per_booking', true, 10, NOW()
    );

    -- ========================================================================
    -- FRANJA 2: 04:30 PM – 05:30 PM (990 min a 1050 min) -> RD$ 4,266.67
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Hora Intermedia - Tarde (04:30 PM – 05:30 PM, 90 mins)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 990, 1050, CURRENT_DATE,
        4266.67, 'per_booking', false, 10, NOW()
    );

    -- ========================================================================
    -- FRANJA 3: 05:30 PM – 11:30 PM (1050 min a 1410 min) -> RD$ 4,800.00
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Hora Pico - Noche (05:30 PM – 11:30 PM, 90 mins)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 1050, 1410, CURRENT_DATE,
        4800.00, 'per_booking', false, 10, NOW()
    );

    -- ========================================================================
    -- REGLA FALLBACK BASE (prioridad 1): RD$ 4,000.00 (cancha completa)
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Tarifa Base Estándar - Padel Warehouse (90 mins)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        4000.00, 'per_booking', true, 1, NOW()
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
WHERE v.service_id = 21;

SELECT 
    d.key,
    d.label,
    d.required,
    d.allows_any,
    json_agg(v.value_key ORDER BY v.position) AS values
FROM mcp.contract_dimension d
JOIN mcp.contract_dimension_value v ON v.dimension_id = d.id
WHERE d.contract_version_id = (SELECT id FROM mcp.service_contract_version WHERE service_id = 21 AND version_no = 1)
GROUP BY d.key, d.label, d.required, d.allows_any;

SELECT 
    r.label,
    r.weekdays,
    r.start_minute || ' - ' || r.end_minute AS minutes_range,
    r.amount || ' DOP (' || r.calculation_basis || ')' AS pricing,
    r.priority
FROM mcp.service_price_rule r
WHERE r.service_id = 21
ORDER BY r.priority DESC, r.start_minute ASC;
