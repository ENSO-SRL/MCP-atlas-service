-- ============================================================================
-- SCRIPT DE MIGRACIÓN / SEED: Contratos MCP para VetMetro (Sedes: Paraíso, Arroyo Hondo, Gazcue)
-- ============================================================================
-- Establecimiento:
--   - establishment_id: 94
--   - nombre: 'VetMetro'
--   - código: 'vemt'
--   - regla de antelación (rule_type): NULL (sin agenda fija / citas bajo demanda)
--
-- Sedes / Servicios en el catálogo:
--   - service_id: 101 | VetMetro Ensanche Paraíso (combo_code: 'vemt_paraiso')
--   - service_id: 102 | VetMetro Arroyo Hondo (combo_code: 'vemt_arroyohondo')
--   - service_id: 103 | VetMetro Gazcue (combo_code: 'vemt_gazcue')
--
-- PATRÓN DE DISPONIBILIDAD: 'on_demand_request'
--   - No utiliza slots de agenda ni turnos horarios fijos.
--   - check_availability retorna slots: [] informando que el servicio es bajo demanda.
--   - La reserva se realiza directamente mediante 'create_booking_request' sin 'slot_token'.
--   - Omite el hold atómico en Redis al no haber franja horaria que bloquear.
--   - El conector registra la reserva en Postgres ('requested') y emite 'BookingRequested'
--     en el Outbox transaccional para que el Facade envíe la solicitud al CRM/formulario web.
--
-- FORMULARIO DE RESERVA (booking_fields_schema):
--   - name: string (nombre del propietario / contacto; opcional, toma el de la cuenta si se omite).
--   - pet_type: string enum ["Perro", "Gato", "Ave", "Otro / exótico"].
--   - service: string enum (11 subservicios oficiales de VetMetro).
--   - timeframe: string enum ["Lo antes posible", "Esta semana", "Solo estoy cotizando"].
--   - details: string (síntomas, historial o motivo de consulta).
--   - phone, email: opcionales (toman los datos de la cuenta si se omiten).
--
-- POLÍTICA DE PRECIOS:
--   - pricing_mode: 'text_only'
--   - currency: 'DOP'
--   - Cotización según diagnóstico médico y procedimiento en la veterinaria.
-- ============================================================================

BEGIN;

-- 1. Desactivar temporalmente los triggers de inmutabilidad para la migración/seed
ALTER TABLE mcp.service_contract_version DISABLE TRIGGER contract_version_guard;
ALTER TABLE mcp.contract_dimension DISABLE TRIGGER contract_dimension_draft_only;
ALTER TABLE mcp.contract_dimension_value DISABLE TRIGGER contract_value_draft_only;
ALTER TABLE mcp.contract_dimension_dependency DISABLE TRIGGER contract_dependency_draft_only;

DO $$
DECLARE
    v_establishment_id INT := 94;
    v_services INT[] := ARRAY[101, 102, 103];
    v_service_id INT;
    v_contract_id UUID;
    v_schema JSONB;
BEGIN
    -- 2. Asegurar que el establecimiento VetMetro no tenga regla de antelación restrictiva
    UPDATE establishments
    SET rule_type = NULL,
        has_scheduler = false,
        updated_at = NOW()
    WHERE id = v_establishment_id;

    -- 3. Definición del JSON Schema común para las 3 sedes
    v_schema := '{
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": [
            "pet_type",
            "service",
            "timeframe",
            "details"
        ],
        "properties": {
            "name": {
                "type": "string",
                "description": "Nombre y apellido del propietario o persona de contacto (opcional; si se omite, se usa el de la cuenta)."
            },
            "pet_type": {
                "type": "string",
                "enum": [
                    "Perro",
                    "Gato",
                    "Ave",
                    "Otro / exótico"
                ],
                "description": "Especie o tipo de mascota."
            },
            "service": {
                "type": "string",
                "enum": [
                    "Emergencia 24 horas",
                    "Consulta y medicina general",
                    "Vacunación y prevención",
                    "Laboratorio y diagnóstico",
                    "Hospitalización",
                    "Grooming y spa",
                    "Hotel de mascotas",
                    "Servicio a domicilio",
                    "Tienda y farmacia",
                    "Cirugía",
                    "Negocio - criadero / rescate / pet-friendly"
                ],
                "description": "Tipo de servicio veterinario o atención solicitada."
            },
            "timeframe": {
                "type": "string",
                "enum": [
                    "Lo antes posible",
                    "Esta semana",
                    "Solo estoy cotizando"
                ],
                "description": "Marco de tiempo o urgencia deseada para la atención de la mascota."
            },
            "details": {
                "type": "string",
                "description": "Descripción de los síntomas, condición de la mascota, motivo de la consulta o detalles relevantes."
            },
            "phone": {
                "type": "string",
                "description": "Teléfono de contacto alternativo (opcional; si se omite, se usa el de la cuenta)."
            },
            "email": {
                "type": "string",
                "format": "email",
                "description": "Correo electrónico de contacto alternativo (opcional; si se omite, se usa el de la cuenta)."
            }
        }
    }'::jsonb;

    -- 4. Iterar sobre cada sede de VetMetro para registrar el contrato y su política de precios
    FOREACH v_service_id IN ARRAY v_services LOOP

        -- Validar que el servicio exista en el catálogo
        IF NOT EXISTS (SELECT 1 FROM servicios WHERE id = v_service_id) THEN
            RAISE EXCEPTION 'El servicio con id % no existe en la tabla servicios. Verifique la base de datos.', v_service_id;
        END IF;

        -- Contrato de Servicio (mcp.service_contract_version)
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
                'on_demand_request',
                v_schema,
                '{
                    "policy": "pay_at_venue",
                    "currency": "DOP",
                    "description": "El pago se realiza directamente en la veterinaria o al prestarse el servicio según el procedimiento o diagnóstico clínico."
                }'::jsonb,
                '{
                    "allowed": true,
                    "hours_before": 0,
                    "description": "Puedes cancelar o reprogramar tu solicitud comunicándote directamente con la sede de VetMetro."
                }'::jsonb,
                86400,
                1,
                'hash_vemt_' || v_service_id || '_v1',
                NOW(),
                NOW()
            );
        ELSE
            UPDATE mcp.service_contract_version
            SET 
                pattern = 'on_demand_request',
                booking_fields_schema = v_schema,
                payment_policy = '{
                    "policy": "pay_at_venue",
                    "currency": "DOP",
                    "description": "El pago se realiza directamente en la veterinaria o al prestarse el servicio según el procedimiento o diagnóstico clínico."
                }'::jsonb,
                cancellation_policy = '{
                    "allowed": true,
                    "hours_before": 0,
                    "description": "Puedes cancelar o reprogramar tu solicitud comunicándote directamente con la sede de VetMetro."
                }'::jsonb,
                request_ttl_seconds = 86400
            WHERE id = v_contract_id;
        END IF;

        -- 5. Limpiar dimensiones previas de esta versión de contrato (on_demand_request no requiere dimensiones)
        DELETE FROM mcp.contract_dimension WHERE contract_version_id = v_contract_id;

        -- 6. Publicar versión del contrato si estaba en borrador
        UPDATE mcp.service_contract_version 
        SET status = 'published', published_at = NOW()
        WHERE id = v_contract_id;

        -- 7. Política General de Precios (mcp.service_pricing_policy) -> Modo text_only
        INSERT INTO mcp.service_pricing_policy (
            service_id, pricing_mode, currency, tax_included, info_text, updated_at
        )
        VALUES (
            v_service_id,
            'text_only',
            'DOP',
            true,
            'VetMetro gestiona citas y servicios bajo solicitud previa. Las tarifas se cotizan según el diagnóstico clínico, procedimiento requerido o evaluación presencial de la mascota. Las solicitudes de Emergencia 24 horas reciben atención prioritaria.',
            NOW()
        )
        ON CONFLICT (service_id) DO UPDATE SET 
            pricing_mode = EXCLUDED.pricing_mode,
            currency = EXCLUDED.currency,
            tax_included = EXCLUDED.tax_included,
            info_text = EXCLUDED.info_text,
            updated_at = NOW();

        -- 8. Limpiar reglas de precios estructuradas (no aplican para text_only)
        DELETE FROM mcp.service_price_rule WHERE service_id = v_service_id;

    END LOOP;

END $$;

-- 9. Reactivar los triggers de inmutabilidad
ALTER TABLE mcp.service_contract_version ENABLE TRIGGER contract_version_guard;
ALTER TABLE mcp.contract_dimension ENABLE TRIGGER contract_dimension_draft_only;
ALTER TABLE mcp.contract_dimension_value ENABLE TRIGGER contract_value_draft_only;
ALTER TABLE mcp.contract_dimension_dependency ENABLE TRIGGER contract_dependency_draft_only;

COMMIT;

