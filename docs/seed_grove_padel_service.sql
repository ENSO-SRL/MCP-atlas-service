-- ============================================================================
-- SCRIPT DE MIGRACIÓN / SEED: Contrato MCP, Dimensiones y Precios para Grove Padel Club
-- ============================================================================
-- Servicio existente en el catálogo:
--   - service_id: 18
--   - establecimiento: Grove Padel Club
--   - patrón: 'slot_object'
--   - regla de antelación (rule_type): NULL (sin esquemas restrictivos de antelación)
--
-- DIMENSIÓN DE DISPONIBILIDAD:
--   - type: 'OUTDOOR COURT' (Cancha al aire libre) vs 'COVERED COURT' (Cancha techada)
--
-- ESQUEMA TARIFARIO POR CANCHA COMPLETA (calculation_basis: 'per_booking'):
--   Grove Padel Club exige estrictamente 4 jugadores por turno. Las tarifas reflejan
--   la cancha completa para los 4 jugadores:
--   - Entre semana (Lunes a Viernes):
--       * Hora Valle (06:00 AM - 04:30 PM): RD$ 1,800.00 (4 x RD$ 450)
--       * Hora Pico  (04:30 PM - 11:00 PM): RD$ 3,200.00 (4 x RD$ 800)
--   - Fin de semana (Sábado y Domingo):
--       * Hora Pico Mañana      (06:00 AM - 10:30 AM): RD$ 3,200.00 (4 x RD$ 800)
--       * Hora Valle            (10:30 AM - 04:30 PM): RD$ 1,800.00 (4 x RD$ 450)
--       * Hora Pico Tarde/Noche (04:30 PM - 11:00 PM): RD$ 3,200.00 (4 x RD$ 800)
--
-- REGLA DEL FORMULARIO DE RESERVA:
--   El campo 'users' exige estrictamente los 3 jugadores acompañantes (invitados),
--   ya que el usuario autenticado que realiza la reserva es el 4to jugador.
-- ============================================================================

BEGIN;

-- 1. Desactivar temporalmente los triggers de inmutabilidad para la migración/seed
ALTER TABLE mcp.service_contract_version DISABLE TRIGGER contract_version_guard;
ALTER TABLE mcp.contract_dimension DISABLE TRIGGER contract_dimension_draft_only;
ALTER TABLE mcp.contract_dimension_value DISABLE TRIGGER contract_value_draft_only;
ALTER TABLE mcp.contract_dimension_dependency DISABLE TRIGGER contract_dependency_draft_only;

DO $$
DECLARE
    v_service_id INT := 18;
    v_contract_id UUID;
    v_dim_type_id UUID := gen_random_uuid();
BEGIN
    -- 2. Validar que el servicio 18 exista en el catálogo
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
                "required": ["users"],
                "properties": {
                    "users": {
                        "type": "array",
                        "title": "Jugadores de la Partida",
                        "description": "Grove Padel Club requiere estrictamente 4 personas obligatorias en cancha. El titular de la reserva es el primer jugador, por lo que aquí se deben incluir obligatoriamente los nombres de los 3 jugadores acompañantes.",
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
                                    "description": "Nombre y apellido del jugador invitado"
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
                "description": "Al confirmar la reserva, Grove Padel Club remite un enlace de pago digital para garantizar el turno."
            }'::jsonb,
            '{"allowed": true, "hours_before": 24}'::jsonb,
            900,
            1,
            'hash_grove_padel_v1',
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
                        "title": "Jugadores de la Partida",
                        "description": "Grove Padel Club requiere estrictamente 4 personas obligatorias en cancha. El titular de la reserva es el primer jugador, por lo que aquí se deben incluir obligatoriamente los nombres de los 3 jugadores acompañantes.",
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
                                    "description": "Nombre y apellido del jugador invitado"
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
                "description": "Al confirmar la reserva, Grove Padel Club remite un enlace de pago digital para garantizar el turno."
            }'::jsonb,
            cancellation_policy = '{"allowed": true, "hours_before": 24}'::jsonb,
            request_ttl_seconds = 900
        WHERE id = v_contract_id;
    END IF;

    -- 4. Limpiar dimensiones previas de esta versión de contrato
    DELETE FROM mcp.contract_dimension WHERE contract_version_id = v_contract_id;

    -- 5. Dimensión: type (Tipo de Cancha: OUTDOOR COURT vs COVERED COURT)
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
        'Seleccione el tipo de cancha: OUTDOOR COURT (Al aire libre) o COVERED COURT (Techada / Cubierta). Requerido por el upstream para consultar disponibilidad.',
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
            'OUTDOOR COURT', 'Cancha al aire libre (Outdoor Court)', 
            'Pistas de pádel reglamentarias al descubierto.', 1
        ),
        (
            gen_random_uuid(), v_contract_id, v_dim_type_id, 
            'COVERED COURT', 'Cancha techada (Covered Court)', 
            'Pistas de pádel techadas protegidas contra el clima y sol.', 2
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
        'Tarifas oficiales por cancha completa (4 jugadores obligatorios) para Grove Padel Club: Hora Valle RD$ 1,800.00 (RD$ 450/persona) y Hora Pico RD$ 3,200.00 (RD$ 800/persona). El pago se formaliza mediante enlace digital.',
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
    -- ENTRE SEMANA: Lunes a Viernes (weekdays: [1, 2, 3, 4, 5])
    -- ========================================================================
    -- Hora Valle: 06:00 AM – 04:30 PM (360 min a 990 min) -> RD$ 1,800.00 (4 jugadores)
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Hora Valle - Entre Semana (Cancha 4 Jugadores)',
        ARRAY[1, 2, 3, 4, 5]::smallint[], 360, 990, CURRENT_DATE,
        1800.00, 'per_booking', true, 10, NOW()
    );

    -- Hora Pico: 04:30 PM – 11:00 PM (990 min a 1380 min) -> RD$ 3,200.00 (4 jugadores)
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Hora Pico - Entre Semana (Cancha 4 Jugadores)',
        ARRAY[1, 2, 3, 4, 5]::smallint[], 990, 1380, CURRENT_DATE,
        3200.00, 'per_booking', false, 10, NOW()
    );

    -- ========================================================================
    -- FIN DE SEMANA: Sábado y Domingo (weekdays: [6, 7])
    -- ========================================================================
    -- Hora Pico Mañana: 06:00 AM – 10:30 AM (360 min a 630 min) -> RD$ 3,200.00 (4 jugadores)
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Hora Pico - Fin de Semana Mañana (Cancha 4 Jugadores)',
        ARRAY[6, 7]::smallint[], 360, 630, CURRENT_DATE,
        3200.00, 'per_booking', false, 10, NOW()
    );

    -- Hora Valle: 10:30 AM – 04:30 PM (630 min a 990 min) -> RD$ 1,800.00 (4 jugadores)
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Hora Valle - Fin de Semana (Cancha 4 Jugadores)',
        ARRAY[6, 7]::smallint[], 630, 990, CURRENT_DATE,
        1800.00, 'per_booking', true, 10, NOW()
    );

    -- Hora Pico Tarde/Noche: 04:30 PM – 11:00 PM (990 min a 1380 min) -> RD$ 3,200.00 (4 jugadores)
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Hora Pico - Fin de Semana Tarde/Noche (Cancha 4 Jugadores)',
        ARRAY[6, 7]::smallint[], 990, 1380, CURRENT_DATE,
        3200.00, 'per_booking', false, 10, NOW()
    );

    -- ========================================================================
    -- REGLA FALLBACK BASE (prioridad 1): RD$ 1,800.00 (cancha completa)
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Tarifa Base Estándar - Grove Padel Club (Cancha 4 Jugadores)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
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
WHERE v.service_id = 18;

SELECT 
    r.label,
    r.weekdays,
    r.start_minute || ' - ' || r.end_minute AS minutes_range,
    r.amount || ' DOP (' || r.calculation_basis || ')' AS pricing,
    r.priority
FROM mcp.service_price_rule r
WHERE r.service_id = 18
ORDER BY r.priority DESC, r.start_minute ASC;
