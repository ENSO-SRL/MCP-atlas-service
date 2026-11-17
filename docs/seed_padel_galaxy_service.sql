-- ============================================================================
-- SCRIPT DE MIGRACIÓN / SEED: Contrato MCP, Dimensiones y Precios para Padel Galaxy
-- ============================================================================
-- Pasarela: PlayByPoint (establishment_id: 13)
-- Servicio en catálogo:
--   - service_id: 19
--   - establecimiento: Padel Galaxy (combo_code: 'pgx', sub_endpoint: 'PADEL_GALAXY')
--   - patrón: 'slot_object'
--   - regla de antelación (rule_type): NULL (sin restricciones arbitrarias de antelación)
--
-- DIMENSIONES DE DISPONIBILIDAD:
--   - type: 'HORARIO A', 'HORARIO B' (Franja / Configuración de Horario Upstream)
--   - party_size: '1', '2', '3', '4' (Cantidad de Jugadores en cancha)
--
-- ESQUEMA TARIFARIO POR PERSONA (calculation_basis: 'per_person'):
--   Padel Galaxy opera con turnos de 90 minutos y tolera de 1 a 4 jugadores:
--   - Tarifa única: RD$ 655.00 por jugador por 90 minutos (todos los días)
--   - Regla Base Fallback: RD$ 655.00 por persona
--
-- REGLA DEL FORMULARIO DE RESERVA:
--   El titular autenticado es siempre el primer jugador en cancha.
--   El campo 'users' es opcional y admite de 0 a 3 jugadores acompañantes (invitados),
--   cubriendo capacidades de 1, 2, 3 o 4 jugadores totales.
-- ============================================================================

BEGIN;

-- 1. Desactivar temporalmente los triggers de inmutabilidad para la migración/seed
ALTER TABLE mcp.service_contract_version DISABLE TRIGGER contract_version_guard;
ALTER TABLE mcp.contract_dimension DISABLE TRIGGER contract_dimension_draft_only;
ALTER TABLE mcp.contract_dimension_value DISABLE TRIGGER contract_value_draft_only;
ALTER TABLE mcp.contract_dimension_dependency DISABLE TRIGGER contract_dependency_draft_only;

DO $$
DECLARE
    v_service_id INT := 19;
    v_contract_id UUID;
    v_dim_type_id UUID := gen_random_uuid();
    v_dim_players_id UUID := gen_random_uuid();
BEGIN
    -- 2. Validar que el servicio 19 exista en el catálogo
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
                        "description": "Padel Galaxy admite partidas de 1 a 4 jugadores. El titular autenticado de la cuenta es el primer jugador. Indique aquí de 0 a 3 acompañantes si asisten más personas.",
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
                "description": "Al confirmar la reserva, Padel Galaxy remite un enlace de pago digital seguro de PlayByPoint para garantizar el turno."
            }'::jsonb,
            '{"allowed": true, "hours_before": 24}'::jsonb,
            900,
            1,
            'hash_padel_galaxy_v1',
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
                        "description": "Padel Galaxy admite partidas de 1 a 4 jugadores. El titular autenticado de la cuenta es el primer jugador. Indique aquí de 0 a 3 acompañantes si asisten más personas.",
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
                "description": "Al confirmar la reserva, Padel Galaxy remite un enlace de pago digital seguro de PlayByPoint para garantizar el turno."
            }'::jsonb,
            cancellation_policy = '{"allowed": true, "hours_before": 24}'::jsonb,
            request_ttl_seconds = 900
        WHERE id = v_contract_id;
    END IF;

    -- 4. Limpiar dimensiones previas de esta versión de contrato
    DELETE FROM mcp.contract_dimension WHERE contract_version_id = v_contract_id;

    -- 5. Dimensión 1: type (Configuración de Horario: HORARIO A vs HORARIO B)
    INSERT INTO mcp.contract_dimension (
        id, contract_version_id, key, position, label, description,
        values_source, apply_mode, required, allows_any, reports_counts
    )
    VALUES (
        v_dim_type_id,
        v_contract_id,
        'type',
        1,
        'Tipo de Horario',
        'Seleccione el tipo de horario requerido por la pasarela PlayByPoint para Padel Galaxy: HORARIO A u HORARIO B.',
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
            'HORARIO A', 'Horario A', 
            'Turnos y pistas correspondientes al esquema Horario A de Padel Galaxy.', 1
        ),
        (
            gen_random_uuid(), v_contract_id, v_dim_type_id, 
            'HORARIO B', 'Horario B', 
            'Turnos y pistas correspondientes al esquema Horario B de Padel Galaxy.', 2
        );

    -- 6. Dimensión 2: party_size (Cantidad de Jugadores: 1 a 4)
    INSERT INTO mcp.contract_dimension (
        id, contract_version_id, key, position, label, description,
        values_source, apply_mode, required, allows_any, reports_counts
    )
    VALUES (
        v_dim_players_id,
        v_contract_id,
        'party_size',
        2,
        'Cantidad de Jugadores',
        'Número de jugadores que asistirán a la partida (1 a 4). Permite cotizar y proyectar la tarifa total calculada (RD$ 655 x jugador por 90 min).',
        'inline',
        'upstream_param',
        false,
        true,
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

    -- 7. Publicar versión del contrato si estaba en borrador
    UPDATE mcp.service_contract_version 
    SET status = 'published', published_at = NOW()
    WHERE id = v_contract_id;

    -- 8. Política General de Precios (mcp.service_pricing_policy)
    INSERT INTO mcp.service_pricing_policy (
        service_id, pricing_mode, currency, tax_included, info_text, updated_at
    )
    VALUES (
        v_service_id,
        'structured',
        'DOP',
        true,
        'Tarifas oficiales por persona para Padel Galaxy (admite 1 a 4 jugadores): RD$ 655.00 por jugador por 90 minutos de juego. El pago se formaliza mediante enlace digital.',
        NOW()
    )
    ON CONFLICT (service_id) DO UPDATE SET 
        pricing_mode = EXCLUDED.pricing_mode,
        currency = EXCLUDED.currency,
        tax_included = EXCLUDED.tax_included,
        info_text = EXCLUDED.info_text,
        updated_at = NOW();

    -- 9. Reglas de Precios Dinámicos por Persona (mcp.service_price_rule)
    DELETE FROM mcp.service_price_rule WHERE service_id = v_service_id;

    -- ========================================================================
    -- TARIFA ESTÁNDAR: Todos los días (Lunes a Domingo, weekdays 1 a 7)
    -- ========================================================================
    -- RD$ 655.00 por jugador por 90 minutos
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Tarifa Estándar - Padel Galaxy (RD$ 655/persona por 90 min)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        655.00, 'per_person', true, 10, NOW()
    );

    -- ========================================================================
    -- REGLA FALLBACK BASE (prioridad 1): RD$ 655.00 por persona
    -- ========================================================================
    INSERT INTO mcp.service_price_rule (
        id, service_id, label, weekdays, start_minute, end_minute, valid_from,
        amount, calculation_basis, is_starting_price, priority, updated_at
    )
    VALUES (
        gen_random_uuid(), v_service_id,
        'Tarifa Base Estándar - Padel Galaxy (RD$ 655/persona)',
        ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[], 0, 1440, CURRENT_DATE,
        655.00, 'per_person', true, 1, NOW()
    );

END $$;

-- 10. Reactivar triggers de inmutabilidad
ALTER TABLE mcp.service_contract_version ENABLE TRIGGER contract_version_guard;
ALTER TABLE mcp.contract_dimension DISABLE TRIGGER contract_dimension_draft_only;
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
WHERE v.service_id = 19;

SELECT 
    d.key,
    d.label,
    d.required,
    d.allows_any,
    json_agg(v.value_key ORDER BY v.position) AS values
FROM mcp.contract_dimension d
JOIN mcp.contract_dimension_value v ON v.dimension_id = d.id
WHERE d.contract_version_id = (SELECT id FROM mcp.service_contract_version WHERE service_id = 19 AND version_no = 1)
GROUP BY d.key, d.label, d.required, d.allows_any;

SELECT 
    r.label,
    r.weekdays,
    r.start_minute || ' - ' || r.end_minute AS minutes_range,
    r.amount || ' DOP (' || r.calculation_basis || ')' AS pricing,
    r.priority
FROM mcp.service_price_rule r
WHERE r.service_id = 19
ORDER BY r.priority DESC, r.start_minute ASC;
