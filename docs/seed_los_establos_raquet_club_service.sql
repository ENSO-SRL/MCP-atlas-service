-- ============================================================================
-- SCRIPT DE MIGRACIÓN / SEED: Contrato MCP, Dimensiones y Precios para Los Establos Raquet Club
-- ============================================================================
-- Pasarela: PlayByPoint (establishment_id: 13)
-- Servicio en catálogo:
--   - service_id: 39
--   - establecimiento: Los Establos Raquet Club (combo_code: 'ler', sub_endpoint: 'LOS_ESTABLOS_RAQUET_CLUB')
--   - patrón: 'slot_object'
--   - regla de antelación (rule_type): NULL (sin restricciones arbitrarias de antelación)
--
-- DIMENSIÓN DE DISPONIBILIDAD:
--   - type: 'PADEL', 'COVERED COURT', 'BALL MACHINE'
--
-- CAPACIDAD Y ESQUEMA TARIFARIO POR CANCHA (calculation_basis: 'per_booking'):
--   - PADEL (90 minutos, 4 jugadores obligatorio):
--       * 06:00 AM – 05:00 PM: RD$ 2,000.00 por reserva (RD$ 500.00 / jugador)
--       * 05:00 PM – 11:00 PM: RD$ 2,600.00 por reserva (RD$ 650.00 / jugador)
--   - COVERED COURT (Cancha techada, 90 minutos, 4 jugadores obligatorio):
--       * 06:00 AM – 05:00 PM: RD$ 2,600.00 por reserva (RD$ 650.00 / jugador)
--       * 05:00 PM – 11:00 PM: RD$ 3,600.00 por reserva (RD$ 900.00 / jugador)
--   - BALL MACHINE (Máquina lanzapelotas, 60 minutos):
--       * Todo el día: RD$ 1,800.00 por reserva por hora
--   - Regla Base Fallback: RD$ 1,800.00 por reserva
--
-- REGLA DEL FORMULARIO DE RESERVA:
--   El titular autenticado es el 1er jugador.
--   El campo 'users' admite de 0 a 3 acompañantes:
--   - Para PADEL y COVERED COURT: se deben suministrar obligatoriamente los 3 acompañantes (4 jugadores en cancha).
--   - Para BALL MACHINE: uso individual o acompañantes opcionales.
-- ============================================================================

BEGIN;

-- 1. Desactivar temporalmente los triggers de inmutabilidad para la migración/seed
ALTER TABLE mcp.service_contract_version DISABLE TRIGGER contract_version_guard;
ALTER TABLE mcp.contract_dimension DISABLE TRIGGER contract_dimension_draft_only;
ALTER TABLE mcp.contract_dimension_value DISABLE TRIGGER contract_value_draft_only;
ALTER TABLE mcp.contract_dimension_dependency DISABLE TRIGGER contract_dependency_draft_only;

DO $$
DECLARE
    v_service_id INT := 39;
    v_contract_id UUID;
    v_dim_type_id UUID := gen_random_uuid();
BEGIN
    -- 2. Validar que el servicio 39 exista en el catálogo
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
                        "description": "El titular autenticado es el primer jugador. Para PADEL y COVERED COURT se requieren obligatoriamente 3 acompañantes (4 jugadores en total en cancha). Para BALL MACHINE los acompañantes son opcionales.",
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
                "description": "Al confirmar la reserva, Los Establos Raquet Club remite un enlace de pago digital seguro de PlayByPoint para garantizar el turno."
            }'::jsonb,
            '{"allowed": true, "hours_before": 24}'::jsonb,
            900,
            1,
            'hash_los_establos_raquet_club_v1',
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
                        "description": "El titular autenticado es el primer jugador. Para PADEL y COVERED COURT se requieren obligatoriamente 3 acompañantes (4 jugadores en total en cancha). Para BALL MACHINE los acompañantes son opcionales.",
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
                "description": "Al confirmar la reserva, Los Establos Raquet Club remite un enlace de pago digital seguro de PlayByPoint para garantizar el turno."
            }'::jsonb,
            cancellation_policy = '{"allowed": true, "hours_before": 24}'::jsonb,
            request_ttl_seconds = 900
        WHERE id = v_contract_id;
    END IF;

    -- 4. Limpiar dimensiones previas de esta versión de contrato
    DELETE FROM mcp.contract_dimension WHERE contract_version_id = v_contract_id;

    -- 5. Dimensión: type (Tipo de Cancha / Servicio)
    INSERT INTO mcp.contract_dimension (
        id, contract_version_id, key, position, label, description,
        values_source, apply_mode, required, allows_any, reports_counts
    )
    VALUES (
        v_dim_type_id,
        v_contract_id,
        'type',
        1,
        'Tipo de Cancha / Servicio',
        'Seleccione el tipo de cancha o servicio en Los Establos Raquet Club: PADEL (al aire libre, 4 jugadores), COVERED COURT (techada, 4 jugadores) o BALL MACHINE (máquina lanzapelotas). Parámetro requerido por PlayByPoint.',
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
            'PADEL', 'Pádel al Aire Libre (4 jugadores obligatorio)', 
            'Pista reglamentaria de pádel descubierta (90 minutos, 4 jugadores obligatorios).', 1
        ),
        (
            gen_random_uuid(), v_contract_id, v_dim_type_id, 
            'COVERED COURT', 'Cancha Techada (Covered Court - 4 jugadores)', 
            'Pista reglamentaria de pádel techada/cubierta (90 minutos, 4 jugadores obligatorios).', 2
        ),
        (
            gen_random_uuid(), v_contract_id, v_dim_type_id, 
            'BALL MACHINE', 'Máquina Lanzapelotas (Ball Machine)', 
            'Pista con máquina automática lanzapelotas para entrenamiento (turnos de 60 minutos).', 3
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
        'Tarifas oficiales por cancha en Los Establos Raquet Club: Pádel: 06:00 AM – 05:00 PM RD$ 2,000.00; 05:00 PM – 11:00 PM RD$ 2,600.00 (4 jugadores / 90 min); Covered Court: 06:00 AM – 05:00 PM RD$ 2,600.00; 05:00 PM – 11:00 PM RD$ 3,600.00 (4 jugadores / 90 min); Ball Machine: RD$ 1,800.00/hora. El pago se formaliza mediante enlace digital seguro de PlayByPoint.',
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
    -- PÁDEL: Franja Diurna (06:00 AM – 05:00 PM, 360 min a 1020 min)
    -- RD$ 2,000.00 por reserva (4 x RD$ 500.00 / jugador, 90 mins)
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Pádel - Horario Diurno (06:00 AM – 05:00 PM, 4 jugadores / 90 min)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 360, 1020, CURRENT_DATE,
        '{"type": "PADEL"}'::jsonb,
        2000.00, 'per_booking', false, 10, NOW()
    );

    -- ========================================================================
    -- PÁDEL: Franja Nocturna (05:00 PM – 11:00 PM, 1020 min a 1380 min)
    -- RD$ 2,600.00 por reserva (4 x RD$ 650.00 / jugador, 90 mins)
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Pádel - Horario Nocturno (05:00 PM – 11:00 PM, 4 jugadores / 90 min)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 1020, 1380, CURRENT_DATE,
        '{"type": "PADEL"}'::jsonb,
        2600.00, 'per_booking', false, 10, NOW()
    );

    -- ========================================================================
    -- COVERED COURT: Franja Diurna (06:00 AM – 05:00 PM, 360 min a 1020 min)
    -- RD$ 2,600.00 por reserva (4 x RD$ 650.00 / jugador, 90 mins)
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Covered Court - Horario Diurno (06:00 AM – 05:00 PM, 4 jugadores / 90 min)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 360, 1020, CURRENT_DATE,
        '{"type": "COVERED COURT"}'::jsonb,
        2600.00, 'per_booking', false, 10, NOW()
    );

    -- ========================================================================
    -- COVERED COURT: Franja Nocturna (05:00 PM – 11:00 PM, 1020 min a 1380 min)
    -- RD$ 3,600.00 por reserva (4 x RD$ 900.00 / jugador, 90 mins)
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Covered Court - Horario Nocturno (05:00 PM – 11:00 PM, 4 jugadores / 90 min)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 1020, 1380, CURRENT_DATE,
        '{"type": "COVERED COURT"}'::jsonb,
        3600.00, 'per_booking', false, 10, NOW()
    );

    -- ========================================================================
    -- BALL MACHINE: Todo el día (0 min a 1440 min)
    -- RD$ 1,800.00 por reserva por hora (60 mins)
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Ball Machine - Tarifa por Hora (60 min)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        '{"type": "BALL MACHINE"}'::jsonb,
        1800.00, 'per_booking', true, 10, NOW()
    );

    -- ========================================================================
    -- REGLA FALLBACK BASE (prioridad 1): RD$ 1,800.00 por reserva
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Tarifa Base Estándar - Los Establos Raquet Club',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        NULL,
        1800.00, 'per_booking', true, 1, NOW()
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
WHERE v.service_id = 39;

SELECT 
    d.key,
    d.label,
    d.required,
    d.allows_any,
    json_agg(v.value_key ORDER BY v.position) AS values
FROM mcp.contract_dimension d
JOIN mcp.contract_dimension_value v ON v.dimension_id = d.id
WHERE d.contract_version_id = (SELECT id FROM mcp.service_contract_version WHERE service_id = 39 AND version_no = 1)
GROUP BY d.key, d.label, d.required, d.allows_any;

SELECT 
    r.label,
    r.dimension_conditions,
    r.weekdays,
    r.start_minute || ' - ' || r.end_minute AS minutes_range,
    r.amount || ' DOP (' || r.calculation_basis || ')' AS pricing,
    r.priority
FROM mcp.service_price_rule r
WHERE r.service_id = 39
ORDER BY r.priority DESC, r.start_minute ASC;
