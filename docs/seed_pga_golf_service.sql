-- ============================================================================
-- SCRIPT DE MIGRACIÓN / SEED: Servicio PGA_GOLF y Establecimiento PGA
-- ============================================================================
-- Este script es totalmente idempotente y puede ejecutarse repetidas veces.
-- Inserta la jerarquía completa:
-- 1. Categoría de Establecimiento: Golf & Deportes
-- 2. Establecimiento: PGA Ocean's 4 (code: 'PGA')
-- 3. Categoría de Servicio: Golf
-- 4. Servicio de Catálogo: PGA Golf (combo_code: 'PGA_GOLF')
-- 5. Contrato de Servicio (ServiceContractVersion) publicado:
--    - Patrón: slot_object
--    - Schema: guests (firstName, lastName) para acompañantes
-- 6. Dimensiones de Disponibilidad:
--    - course: 'championsship' (18 hoyos), 'par 3 course' (9 hoyos)
--    - party_size: 1, 2, 3, 4 (estándar para cantidad de jugadores)
-- 7. Política y Reglas de Precios:
--    - Championship: 285.00 USD por persona (dimension_conditions: {"course": "championsship"})
--    - Par 3 Course: 55.00 USD por persona (dimension_conditions: {"course": "par 3 course"})
-- ============================================================================

BEGIN;

-- 1. Categoría de Establecimiento
INSERT INTO establishment_categories (name, description, is_active, created_at, updated_at)
VALUES ('Golf & Deportes', 'Clubes de golf, canchas deportivas y academias', true, NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET updated_at = NOW();

-- 2. Establecimiento PGA
INSERT INTO establishments (
    name, code, is_active, has_credentials, has_scheduler, rule_type,
    category_id, country, city, description, created_at, updated_at
)
SELECT 
    'PGA Ocean''s 4', 'PGA', true, true, false, 'days_ahead',
    id, 'DOM', 'La Romana', 'Campo de golf de campeonato PGA en Playa Nueva Romana.', NOW(), NOW()
FROM establishment_categories WHERE name = 'Golf & Deportes'
LIMIT 1
ON CONFLICT DO NOTHING;

-- 3. Categoría de Servicio
INSERT INTO categorias_servicio (nombre, descripcion, activo, created_at, updated_at)
VALUES ('Golf', 'Rondas de golf, green fees y prácticas', true, NOW(), NOW())
ON CONFLICT (nombre) DO UPDATE SET updated_at = NOW();

-- 4. Servicio PGA_GOLF
INSERT INTO servicios (
    nombre, categoria_id, establishment_id, descripcion, activo, combo_code, has_credentials, created_at, updated_at
)
SELECT 
    'PGA Golf',
    cat.id,
    est.id,
    'Reserva de Green Fees para Championship (18 hoyos) y Par 3 (9 hoyos) en PGA Ocean''s 4.',
    true,
    'PGA_GOLF',
    true,
    NOW(),
    NOW()
FROM categorias_servicio cat, establishments est
WHERE cat.nombre = 'Golf' AND est.code = 'PGA'
LIMIT 1
ON CONFLICT DO NOTHING;

-- Bloque transaccional para Contrato, Dimensiones y Precios
DO $$
DECLARE
    v_service_id INT;
    v_contract_id UUID := gen_random_uuid();
    v_dim_course_id UUID := gen_random_uuid();
    v_dim_players_id UUID := gen_random_uuid();
BEGIN
    SELECT id INTO v_service_id FROM servicios WHERE combo_code = 'PGA_GOLF' LIMIT 1;
    
    IF v_service_id IS NOT NULL THEN
        -- 5. Contrato de Servicio publicado
        INSERT INTO mcp.service_contract_version (
            id, service_id, version_no, status, pattern, booking_fields_schema,
            payment_policy, cancellation_policy, request_ttl_seconds, meta_schema_version,
            content_hash, published_at, created_at
        )
        VALUES (
            v_contract_id,
            v_service_id,
            1,
            'published',
            'slot_object',
            '{
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "properties": {
                    "guests": {
                        "type": "array",
                        "description": "Lista de acompañantes (obligatorio si hay más de 1 jugador). Cada acompañante debe indicar firstName y lastName.",
                        "items": {
                            "type": "object",
                            "required": ["firstName", "lastName"],
                            "properties": {
                                "firstName": {"type": "string", "description": "Nombre de pila del acompañante"},
                                "lastName": {"type": "string", "description": "Apellido del acompañante"}
                            }
                        }
                    }
                }
            }'::jsonb,
            '{"policy": "pay_at_venue", "currency": "USD"}'::jsonb,
            '{"allowed": true, "hours_before": 24}'::jsonb,
            900,
            1,
            'hash_pga_golf_v1',
            NOW(),
            NOW()
        )
        ON CONFLICT (service_id, version_no) DO UPDATE SET published_at = NOW()
        RETURNING id INTO v_contract_id;

        -- 6. Dimensión: course
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
            'Seleccione el campo: Championship (18 hoyos) o Par 3 Course (9 hoyos).',
            'inline',
            'upstream_param',
            true,
            false,
            false
        )
        ON CONFLICT (contract_version_id, key) DO NOTHING
        RETURNING id INTO v_dim_course_id;

        IF v_dim_course_id IS NOT NULL THEN
            INSERT INTO mcp.contract_dimension_value (
                contract_version_id, dimension_id, value_key, label, description, position
            )
            VALUES 
                (v_contract_id, v_dim_course_id, 'championsship', 'Championship (18 hoyos)', 'Campo oficial de 18 hoyos par 72.', 1),
                (v_contract_id, v_dim_course_id, 'par 3 course', 'Par 3 Course (9 hoyos)', 'Campo ejecutivo de 9 hoyos par 27.', 2)
            ON CONFLICT (dimension_id, value_key) DO NOTHING;
        END IF;

        -- 7. Dimensión: party_size (estándar para cantidad de personas en filtros)
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
            'Número de jugadores en el turno (1 a 4).',
            'inline',
            'upstream_param',
            true,
            false,
            false
        )
        ON CONFLICT (contract_version_id, key) DO NOTHING
        RETURNING id INTO v_dim_players_id;

        IF v_dim_players_id IS NOT NULL THEN
            INSERT INTO mcp.contract_dimension_value (
                contract_version_id, dimension_id, value_key, label, position
            )
            VALUES 
                (v_contract_id, v_dim_players_id, '1', '1 Jugador', 1),
                (v_contract_id, v_dim_players_id, '2', '2 Jugadores', 2),
                (v_contract_id, v_dim_players_id, '3', '3 Jugadores', 3),
                (v_contract_id, v_dim_players_id, '4', '4 Jugadores', 4)
            ON CONFLICT (dimension_id, value_key) DO NOTHING;
        END IF;

        -- 8. Política de Precios
        INSERT INTO mcp.service_pricing_policy (
            service_id, pricing_mode, currency, tax_included, info_text, updated_at
        )
        VALUES (
            v_service_id,
            'rule_based',
            'USD',
            true,
            'Tarifas oficiales por persona para Green Fee según campo seleccionado.',
            NOW()
        )
        ON CONFLICT (service_id) DO UPDATE SET updated_at = NOW();

        -- 9. Reglas de Precios
        -- Limpiar reglas previas del servicio para garantizar consistencia
        DELETE FROM mcp.service_price_rule WHERE service_id = v_service_id;

        -- Championship: 285.00 USD / persona
        INSERT INTO mcp.service_price_rule (
            service_id, label, weekdays, start_minute, end_minute, valid_from,
            dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
        )
        VALUES (
            v_service_id,
            'Tarifa Championship (18 hoyos)',
            ARRAY[1, 2, 3, 4, 5, 6, 7],
            0,
            1440,
            CURRENT_DATE,
            '{"course": "championsship"}'::jsonb,
            285.00,
            'per_person',
            false,
            10,
            NOW()
        );

        -- Par 3 Course: 55.00 USD / persona
        INSERT INTO mcp.service_price_rule (
            service_id, label, weekdays, start_minute, end_minute, valid_from,
            dimension_conditions, amount, calculation_basis, is_starting_price, priority, updated_at
        )
        VALUES (
            v_service_id,
            'Tarifa Par 3 Course (9 hoyos)',
            ARRAY[1, 2, 3, 4, 5, 6, 7],
            0,
            1440,
            CURRENT_DATE,
            '{"course": "par 3 course"}'::jsonb,
            55.00,
            'per_person',
            false,
            10,
            NOW()
        );

    END IF;
END $$;

COMMIT;
