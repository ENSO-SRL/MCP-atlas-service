-- ============================================================================
-- SCRIPT DE MIGRACIÓN / SEED: Contrato MCP, Dimensiones y Precios para Padel House
-- ============================================================================
-- Pasarela: PlayByPoint (establishment_id: 13)
-- Servicio en catálogo:
--   - service_id: 16
--   - establecimiento: Padel House (combo_code: 'pho', sub_endpoint: 'PADEL_HOUSE')
--   - patrón: 'slot_object'
--   - regla de antelación (rule_type): NULL (sin restricciones arbitrarias de antelación)
--
-- DIMENSIÓN DE DISPONIBILIDAD:
--   - type: 'PADEL COURT OUTDOOR' (Al aire libre) vs 'PADEL COURT INDOOR' (Techada / Interior)
--
-- ESQUEMA TARIFARIO POR CANCHA COMPLETA (calculation_basis: 'per_booking', 90 min):
--   Partidos estándar de 90 minutos (4 jugadores obligatorios en cancha):
--   - Entre semana (Lunes a Viernes):
--       * Hora Pico Mañana      (06:00 AM - 10:30 AM): RD$ 4,400.00 (4 x RD$ 1,100 / persona)
--       * Hora Valle Mediodía   (10:30 AM - 04:30 PM): RD$ 3,200.00 (4 x RD$ 800 / persona)
--       * Hora Pico Tarde/Noche (04:30 PM - 10:30 PM): RD$ 4,400.00 (4 x RD$ 1,100 / persona)
--   - Fin de semana (Sábado y Domingo):
--       * Todo el día: RD$ 3,200.00 (4 x RD$ 800 / persona)
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
    v_service_id INT := 16;
    v_contract_id UUID;
    v_dim_type_id UUID := gen_random_uuid();
BEGIN
    -- 2. Validar que el servicio 16 exista en el catálogo
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
                        "title": "Jugadores de la Partida",
                        "description": "Padel House requiere 4 personas en cancha para turnos de 90 minutos. El titular de la reserva es el primer jugador, por lo que aquí se deben incluir obligatoriamente los nombres de los 3 jugadores acompañantes.",
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
                "description": "Al confirmar la reserva en PlayByPoint, Padel House remite un enlace de pago digital para formalizar el turno de la cancha."
            }'::jsonb,
            '{"allowed": true, "hours_before": 24}'::jsonb,
            900,
            1,
            'hash_padel_house_v1',
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
                        "description": "Padel House requiere 4 personas en cancha para turnos de 90 minutos. El titular de la reserva es el primer jugador, por lo que aquí se deben incluir obligatoriamente los nombres de los 3 jugadores acompañantes.",
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
                "description": "Al confirmar la reserva en PlayByPoint, Padel House remite un enlace de pago digital para formalizar el turno de la cancha."
            }'::jsonb,
            cancellation_policy = '{"allowed": true, "hours_before": 24}'::jsonb,
            request_ttl_seconds = 900
        WHERE id = v_contract_id;
    END IF;

    -- 4. Limpiar dimensiones previas de esta versión de contrato
    DELETE FROM mcp.contract_dimension WHERE contract_version_id = v_contract_id;

    -- 5. Dimensión: type (Tipo de Cancha: PADEL COURT OUTDOOR vs PADEL COURT INDOOR)
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
        'Seleccione el tipo de cancha: PADEL COURT OUTDOOR (Al aire libre) o PADEL COURT INDOOR (Techada / Interior). Requerido por el conector PlayByPoint para consultar disponibilidad.',
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
            'PADEL COURT OUTDOOR', 'Cancha al aire libre (Outdoor Court)', 
            'Pistas de pádel reglamentarias al descubierto en Padel House.', 1
        ),
        (
            gen_random_uuid(), v_contract_id, v_dim_type_id, 
            'PADEL COURT INDOOR', 'Cancha techada / interior (Indoor Court)', 
            'Pistas de pádel techadas e interiores protegidas contra el clima y sol en Padel House.', 2
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
        'Tarifas oficiales por cancha completa para 4 jugadores (turnos de 90 minutos) en Padel House: Hora Valle RD$ 3,200.00 (RD$ 800/persona) y Hora Pico RD$ 4,400.00 (RD$ 1,100/persona). Pistas Outdoor e Indoor disponibles. El pago se formaliza mediante enlace digital de PlayByPoint.',
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
    -- Hora Pico Mañana: 06:00 AM – 10:30 AM (360 min a 630 min) -> RD$ 4,400.00 (4 x RD$ 1,100)
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Hora Pico Mañana - Entre Semana (Cancha 4 Jugadores, RD$ 1,100/persona)',
        ARRAY[1, 2, 3, 4, 5]::smallint[], 360, 630, CURRENT_DATE,
        4400.00, 'per_booking', false, 10, NOW()
    );

    -- Hora Valle Mediodía/Tarde: 10:30 AM – 04:30 PM (630 min a 990 min) -> RD$ 3,200.00 (4 x RD$ 800)
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Hora Valle - Entre Semana (Cancha 4 Jugadores, RD$ 800/persona)',
        ARRAY[1, 2, 3, 4, 5]::smallint[], 630, 990, CURRENT_DATE,
        3200.00, 'per_booking', true, 10, NOW()
    );

    -- Hora Pico Tarde/Noche: 04:30 PM – 10:30 PM (990 min a 1350 min) -> RD$ 4,400.00 (4 x RD$ 1,100)
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Hora Pico Tarde/Noche - Entre Semana (Cancha 4 Jugadores, RD$ 1,100/persona)',
        ARRAY[1, 2, 3, 4, 5]::smallint[], 990, 1350, CURRENT_DATE,
        4400.00, 'per_booking', false, 10, NOW()
    );

    -- ========================================================================
    -- FIN DE SEMANA: Sábado y Domingo (weekdays: [6, 7])
    -- ========================================================================
    -- Todo el día: RD$ 3,200.00 (4 x RD$ 800)
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Tarifa Fin de Semana - Todo el Día (Cancha 4 Jugadores, RD$ 800/persona)',
        ARRAY[6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        3200.00, 'per_booking', true, 10, NOW()
    );

    -- ========================================================================
    -- REGLA FALLBACK BASE (prioridad 1): RD$ 3,200.00 (cancha completa)
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Tarifa Base Estándar - Padel House (Cancha 4 Jugadores)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        3200.00, 'per_booking', true, 1, NOW()
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
WHERE v.service_id = 16;

SELECT 
    r.label,
    r.weekdays,
    r.start_minute || ' - ' || r.end_minute AS minutes_range,
    r.amount || ' DOP (' || r.calculation_basis || ')' AS pricing,
    r.priority
FROM mcp.service_price_rule r
WHERE r.service_id = 16
ORDER BY r.priority DESC, r.start_minute ASC;

