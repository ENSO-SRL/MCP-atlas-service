-- ============================================================================
-- SCRIPT DE MIGRACIÓN / SEED: Contrato MCP, Dimensiones y Precios para Cibao Padel Club
-- ============================================================================
-- Pasarela: PlayByPoint (establishment_id: 13)
-- Servicio en catálogo:
--   - service_id: 35
--   - establecimiento: Cibao Padel Club (combo_code: 'cbp', sub_endpoint: 'CIBAO_PADEL_CLUB')
--   - patrón: 'slot_object'
--   - regla de antelación (rule_type): NULL (sin restricciones arbitrarias de antelación)
--
-- DIMENSIÓN DE DISPONIBILIDAD:
--   - type: 'PADEL OUTDOOR', 'PADEL INDOOR'
--
-- CAPACIDAD Y PRECALCULO TARIFARIO (calculation_basis: 'per_booking', 90 min / bloque parcial):
--   El club exige obligatoriamente 4 jugadores en cancha.
--   Se omite la dimensión 'party_size' y se precalcula el costo total de la reserva
--   para los 4 jugadores:
--   - Lunes a Viernes:
--       * 06:00 AM – 06:00 PM: RD$ 2,000.00 (4 x RD$ 500.00 / persona, 90 mins)
--       * 06:00 PM – 11:59 PM: RD$ 3,000.00 (4 x RD$ 750.00 / persona, 90 mins)
--   - Fin de Semana (Sábado y Domingo):
--       * 08:00 AM – 11:00 PM: RD$ 2,000.00 (4 x RD$ 500.00 / persona, 90 mins)
--       * 11:00 PM – 11:59 PM: RD$ 1,333.32 (4 x RD$ 333.33 / persona, bloque parcial)
--   - Regla Base Fallback: RD$ 2,000.00 (cancha completa)
--
-- REGLA DEL FORMULARIO DE RESERVA:
--   El titular autenticado es el primer jugador en cancha.
--   El campo 'users' es obligatorio y exige registrar exactamente a los 3 acompañantes
--   (minItems: 3, maxItems: 3) para completar los 4 jugadores requeridos por el club.
-- ============================================================================

BEGIN;

-- 1. Desactivar temporalmente los triggers de inmutabilidad para la migración/seed
ALTER TABLE mcp.service_contract_version DISABLE TRIGGER contract_version_guard;
ALTER TABLE mcp.contract_dimension DISABLE TRIGGER contract_dimension_draft_only;
ALTER TABLE mcp.contract_dimension_value DISABLE TRIGGER contract_value_draft_only;
ALTER TABLE mcp.contract_dimension_dependency DISABLE TRIGGER contract_dependency_draft_only;

DO $$
DECLARE
    v_service_id INT := 35;
    v_contract_id UUID;
    v_dim_type_id UUID := gen_random_uuid();
BEGIN
    -- 2. Validar que el servicio 35 exista en el catálogo
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
                        "description": "Cibao Padel Club requiere obligatoriamente 4 personas en cancha. El titular autenticado es el primer jugador, por lo que aquí se deben incluir obligatoriamente los nombres de los 3 jugadores acompañantes.",
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
                "description": "Al confirmar la reserva, Cibao Padel Club remite un enlace de pago digital seguro de PlayByPoint para garantizar el turno."
            }'::jsonb,
            '{"allowed": true, "hours_before": 24}'::jsonb,
            900,
            1,
            'hash_cibao_padel_club_v1',
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
                        "description": "Cibao Padel Club requiere obligatoriamente 4 personas en cancha. El titular autenticado es el primer jugador, por lo que aquí se deben incluir obligatoriamente los nombres de los 3 jugadores acompañantes.",
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
                "description": "Al confirmar la reserva, Cibao Padel Club remite un enlace de pago digital seguro de PlayByPoint para garantizar el turno."
            }'::jsonb,
            cancellation_policy = '{"allowed": true, "hours_before": 24}'::jsonb,
            request_ttl_seconds = 900
        WHERE id = v_contract_id;
    END IF;

    -- 4. Limpiar dimensiones previas de esta versión de contrato
    DELETE FROM mcp.contract_dimension WHERE contract_version_id = v_contract_id;

    -- 5. Dimensión: type (Tipo de Cancha)
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
        'Seleccione el tipo de cancha en Cibao Padel Club: PADEL OUTDOOR (al aire libre) o PADEL INDOOR (techada). Parámetro requerido por PlayByPoint.',
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
            'PADEL OUTDOOR', 'Cancha al Aire Libre (Outdoor)', 
            'Pista reglamentaria de pádel descubierta al aire libre (4 jugadores obligatorios).', 1
        ),
        (
            gen_random_uuid(), v_contract_id, v_dim_type_id, 
            'PADEL INDOOR', 'Cancha Techada (Indoor)', 
            'Pista reglamentaria de pádel techada interior (4 jugadores obligatorios).', 2
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
        'Tarifas oficiales por cancha para 4 jugadores en Cibao Padel Club: Lunes a Viernes 06:00 AM – 06:00 PM RD$ 2,000.00 (RD$ 500/pers); Lunes a Viernes 06:00 PM – 11:59 PM RD$ 3,000.00 (RD$ 750/pers); Fines de Semana 08:00 AM – 11:00 PM RD$ 2,000.00 (RD$ 500/pers); Fines de Semana 11:00 PM – 11:59 PM RD$ 1,333.32 (RD$ 333.33/pers bloque parcial). El pago se formaliza mediante enlace digital seguro de PlayByPoint.',
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
    -- FRANJA 1: Lunes a Viernes, 06:00 AM – 06:00 PM (360 min a 1080 min)
    -- RD$ 500 x 4 jugadores = RD$ 2,000.00 (90 mins)
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Lunes a Viernes - Horario Diurno (06:00 AM – 06:00 PM, 4 jugadores / 90 min)',
        ARRAY[1, 2, 3, 4, 5]::smallint[], 360, 1080, CURRENT_DATE,
        2000.00, 'per_booking', true, 10, NOW()
    );

    -- ========================================================================
    -- FRANJA 2: Lunes a Viernes, 06:00 PM – 11:59 PM (1080 min a 1440 min)
    -- RD$ 750 x 4 jugadores = RD$ 3,000.00 (90 mins)
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Lunes a Viernes - Horario Nocturno (06:00 PM – 11:59 PM, 4 jugadores / 90 min)',
        ARRAY[1, 2, 3, 4, 5]::smallint[], 1080, 1440, CURRENT_DATE,
        3000.00, 'per_booking', false, 10, NOW()
    );

    -- ========================================================================
    -- FRANJA 3: Fin de Semana (Sábado y Domingo), 08:00 AM – 11:00 PM (480 min a 1380 min)
    -- RD$ 500 x 4 jugadores = RD$ 2,000.00 (90 mins)
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Fin de Semana - Horario Regular (08:00 AM – 11:00 PM, 4 jugadores / 90 min)',
        ARRAY[6, 7]::smallint[], 480, 1380, CURRENT_DATE,
        2000.00, 'per_booking', false, 10, NOW()
    );

    -- ========================================================================
    -- FRANJA 4: Fin de Semana (Sábado y Domingo), 11:00 PM – 11:59 PM (1380 min a 1440 min)
    -- RD$ 333.33 x 4 jugadores = RD$ 1,333.32 (bloque parcial)
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Fin de Semana - Bloque Parcial Noche (11:00 PM – 11:59 PM, 4 jugadores)',
        ARRAY[6, 7]::smallint[], 1380, 1440, CURRENT_DATE,
        1333.32, 'per_booking', false, 10, NOW()
    );

    -- ========================================================================
    -- REGLA FALLBACK BASE (prioridad 1): RD$ 2,000.00 (cancha completa 90 min)
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Tarifa Base Estándar - Cibao Padel Club (4 jugadores / 90 min)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        2000.00, 'per_booking', true, 1, NOW()
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
WHERE v.service_id = 35;

SELECT 
    d.key,
    d.label,
    d.required,
    d.allows_any,
    json_agg(v.value_key ORDER BY v.position) AS values
FROM mcp.contract_dimension d
JOIN mcp.contract_dimension_value v ON v.dimension_id = d.id
WHERE d.contract_version_id = (SELECT id FROM mcp.service_contract_version WHERE service_id = 35 AND version_no = 1)
GROUP BY d.key, d.label, d.required, d.allows_any;

SELECT 
    r.label,
    r.weekdays,
    r.start_minute || ' - ' || r.end_minute AS minutes_range,
    r.amount || ' DOP (' || r.calculation_basis || ')' AS pricing,
    r.priority
FROM mcp.service_price_rule r
WHERE r.service_id = 35
ORDER BY r.priority DESC, r.start_minute ASC;
