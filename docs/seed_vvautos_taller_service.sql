-- ============================================================================
-- SCRIPT DE MIGRACIÓN / SEED: Contrato MCP, Dimensiones y Precios para VVAutos Taller
-- ============================================================================
-- Servicio existente en el catálogo:
--   - service_id: 99
--   - establecimiento: VVAutos (id: 92, code: 'VV')
--   - nombre servicio: 'VVAutos Taller'
--   - combo_code: 'vvautos_taller'
--   - patrón: 'slot_object' (citas y turnos horarios de taller)
--   - regla de antelación (rule_type): NULL (disponibilidad directa según agenda de citas)
--
-- RESTRICCIÓN DE MARCA EXCLUSIVA:
--   VVAutos es un taller especializado que atiende EXCLUSIVAMENTE vehículos de la marca VOLVO.
--   El formulario de reserva y la validación de objetos de reserva exigen que el modelo
--   del vehículo pertenezca a la gama Volvo (ej. Volvo XC60, Volvo S60, Volvo XC90, etc.).
--
-- DIMENSIONES DE DISPONIBILIDAD:
--   1. 'service' (Sub-servicio / Especialidad del Taller): values_source = 'inline'
--      Opciones: 'Mantenimiento General', 'Otros Servicios', 'Cambio de Cristales', 'Desabolladura y Pintura'.
--      Requerido por el upstream para consultar turnos.
--   2. 'staff' (Mecánico / Asesor Técnico): values_source = 'separate_query', resolver_ref = 'vvautos_staff'.
--      Depende de 'service' y fecha. Permite seleccionar técnico o dejar que el taller asigne uno disponible.
--
-- ESQUEMA TARIFARIO (pricing_mode: 'text_only'):
--   Al ser servicios mecánicos y de taller automotriz, el costo final depende de la mano de obra,
--   diagnóstico técnico y piezas/repuestos originales requeridos. Se maneja de forma informativa.
--
-- FORMULARIO DE RESERVA (booking_fields_schema):
--   - wash_vehicle: enum ['Sí', 'No'] (por defecto 'No').
--   - notes: string opcional (síntomas, peticiones o motivo de la visita).
--   - country_code: string (por defecto 'DO').
--   - vehicle: objeto bajo el patrón Resolve or Create (schema_header: 'vvautos_taller:vehiculo').
--     Permite enviar un vehículo existente (object_id), existente con kilometraje actualizado
--     (modifications_payload), o registrar uno nuevo (new_object_alias + new_object_payload).
--     IMPORTANTE: Solo se admiten vehículos marca Volvo.
-- ============================================================================

BEGIN;

-- 1. Desactivar temporalmente los triggers de inmutabilidad para la migración/seed
ALTER TABLE mcp.service_contract_version DISABLE TRIGGER contract_version_guard;
ALTER TABLE mcp.contract_dimension DISABLE TRIGGER contract_dimension_draft_only;
ALTER TABLE mcp.contract_dimension_value DISABLE TRIGGER contract_value_draft_only;
ALTER TABLE mcp.contract_dimension_dependency DISABLE TRIGGER contract_dependency_draft_only;

DO $$
DECLARE
    v_service_id INT := 99;
    v_contract_id UUID;
    v_dim_service_id UUID := gen_random_uuid();
    v_dim_staff_id UUID := gen_random_uuid();
BEGIN
    -- 2. Validar que el servicio 99 exista en el catálogo
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
                "required": ["wash_vehicle", "vehicle"],
                "properties": {
                    "wash_vehicle": {
                        "type": "string",
                        "enum": ["Sí", "No"],
                        "default": "No",
                        "description": "¿Desea incluir el servicio de lavado del vehículo? (Valores permitidos: \"Sí\" o \"No\")."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Notas, síntomas o especificaciones técnicas para el taller (ej. \"Revisión preventiva de frenos y cambio de aceite\")."
                    },
                    "country_code": {
                        "type": "string",
                        "default": "DO",
                        "description": "Código de país telefónico del cliente (por defecto \"DO\")."
                    },
                    "vehicle": {
                        "type": "object",
                        "description": "Información del vehículo bajo el patrón Resolve or Create. VVAutos es un taller especializado que atiende EXCLUSIVAMENTE vehículos de la marca VOLVO. Puedes reutilizar un vehículo guardado (object_id), enviar un vehículo existente con kilometraje actualizado (modifications_payload), o registrar uno nuevo (new_object_alias + new_object_payload).",
                        "required": ["schema_header"],
                        "properties": {
                            "schema_header": {
                                "type": "string",
                                "default": "vvautos_taller:vehiculo",
                                "description": "Identificador del esquema de objeto. Debe ser \"vvautos_taller:vehiculo\"."
                            },
                            "object_id": {
                                "type": ["integer", "null"],
                                "description": "ID del vehículo guardado previamente por el usuario (obtenido con la herramienta get_user_reservation_objects). Nulo si se va a registrar un vehículo nuevo."
                            },
                            "new_object_alias": {
                                "type": ["string", "null"],
                                "description": "Nombre o alias amigable para el vehículo nuevo (ej. \"Mi Volvo XC60 2023\"). Obligatorio cuando se registra un vehículo nuevo (object_id es nulo)."
                            },
                            "new_object_payload": {
                                "type": ["object", "null"],
                                "description": "Datos completos del vehículo nuevo a registrar. Solo se admiten vehículos de la marca VOLVO.",
                                "properties": {
                                    "vehicle_model": {
                                        "type": "string",
                                        "description": "Modelo y año del vehículo Volvo. ATENCIÓN: Este taller solo acepta vehículos marca VOLVO (ej. \"Volvo XC60 2023\", \"Volvo S60 2021\", \"Volvo XC90\")."
                                    },
                                    "vehicle_plate": {
                                        "type": "string",
                                        "description": "Número de placa o matrícula del vehículo (ej. \"C582741\")."
                                    },
                                    "vehicle_chassis": {
                                        "type": "string",
                                        "description": "Número de chasis o VIN del vehículo (ej. \"YV1FS1TK5P1234567\")."
                                    },
                                    "vehicle_mileage": {
                                        "type": "string",
                                        "description": "Kilometraje actual del vehículo en kilómetros (ej. \"35000\"). Campo de alta variación."
                                    }
                                }
                            },
                            "modifications_payload": {
                                "type": ["object", "null"],
                                "description": "Campos a actualizar sobre un vehículo existente (usado típicamente para actualizar vehicle_mileage si cambió desde la última visita).",
                                "properties": {
                                    "vehicle_mileage": {
                                        "type": "string",
                                        "description": "Nuevo kilometraje actualizado del vehículo."
                                    }
                                }
                            }
                        }
                    }
                }
            }'::jsonb,
            '{
                "policy": "on_site",
                "currency": "DOP",
                "description": "El costo de mano de obra y repuestos se cotiza y abona directamente en el taller al recibir o retirar el vehículo tras la inspección y diagnóstico técnico."
            }'::jsonb,
            '{"allowed": true, "hours_before": 2, "description": "Se permite cancelar o reprogramar la cita hasta 2 horas antes del turno seleccionado sin penalidad."}'::jsonb,
            900,
            1,
            'hash_vvautos_taller_v1',
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
                "required": ["wash_vehicle", "vehicle"],
                "properties": {
                    "wash_vehicle": {
                        "type": "string",
                        "enum": ["Sí", "No"],
                        "default": "No",
                        "description": "¿Desea incluir el servicio de lavado del vehículo? (Valores permitidos: \"Sí\" o \"No\")."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Notas, síntomas o especificaciones técnicas para el taller (ej. \"Revisión preventiva de frenos y cambio de aceite\")."
                    },
                    "country_code": {
                        "type": "string",
                        "default": "DO",
                        "description": "Código de país telefónico del cliente (por defecto \"DO\")."
                    },
                    "vehicle": {
                        "type": "object",
                        "description": "Información del vehículo bajo el patrón Resolve or Create. VVAutos es un taller especializado que atiende EXCLUSIVAMENTE vehículos de la marca VOLVO. Puedes reutilizar un vehículo guardado (object_id), enviar un vehículo existente con kilometraje actualizado (modifications_payload), o registrar uno nuevo (new_object_alias + new_object_payload).",
                        "required": ["schema_header"],
                        "properties": {
                            "schema_header": {
                                "type": "string",
                                "default": "vvautos_taller:vehiculo",
                                "description": "Identificador del esquema de objeto. Debe ser \"vvautos_taller:vehiculo\"."
                            },
                            "object_id": {
                                "type": ["integer", "null"],
                                "description": "ID del vehículo guardado previamente por el usuario (obtenido con la herramienta get_user_reservation_objects). Nulo si se va a registrar un vehículo nuevo."
                            },
                            "new_object_alias": {
                                "type": ["string", "null"],
                                "description": "Nombre o alias amigable para el vehículo nuevo (ej. \"Mi Volvo XC60 2023\"). Obligatorio cuando se registra un vehículo nuevo (object_id es nulo)."
                            },
                            "new_object_payload": {
                                "type": ["object", "null"],
                                "description": "Datos completos del vehículo nuevo a registrar. Solo se admiten vehículos de la marca VOLVO.",
                                "properties": {
                                    "vehicle_model": {
                                        "type": "string",
                                        "description": "Modelo y año del vehículo Volvo. ATENCIÓN: Este taller solo acepta vehículos marca VOLVO (ej. \"Volvo XC60 2023\", \"Volvo S60 2021\", \"Volvo XC90\")."
                                    },
                                    "vehicle_plate": {
                                        "type": "string",
                                        "description": "Número de placa o matrícula del vehículo (ej. \"C582741\")."
                                    },
                                    "vehicle_chassis": {
                                        "type": "string",
                                        "description": "Número de chasis o VIN del vehículo (ej. \"YV1FS1TK5P1234567\")."
                                    },
                                    "vehicle_mileage": {
                                        "type": "string",
                                        "description": "Kilometraje actual del vehículo en kilómetros (ej. \"35000\"). Campo de alta variación."
                                    }
                                }
                            },
                            "modifications_payload": {
                                "type": ["object", "null"],
                                "description": "Campos a actualizar sobre un vehículo existente (usado típicamente para actualizar vehicle_mileage si cambió desde la última visita).",
                                "properties": {
                                    "vehicle_mileage": {
                                        "type": "string",
                                        "description": "Nuevo kilometraje actualizado del vehículo."
                                    }
                                }
                            }
                        }
                    }
                }
            }'::jsonb,
            payment_policy = '{
                "policy": "on_site",
                "currency": "DOP",
                "description": "El costo de mano de obra y repuestos se cotiza y abona directamente en el taller al recibir o retirar el vehículo tras la inspección y diagnóstico técnico."
            }'::jsonb,
            cancellation_policy = '{"allowed": true, "hours_before": 2, "description": "Se permite cancelar o reprogramar la cita hasta 2 horas antes del turno seleccionado sin penalidad."}'::jsonb,
            request_ttl_seconds = 900
        WHERE id = v_contract_id;
    END IF;

    -- 4. Limpiar dimensiones previas de esta versión de contrato
    DELETE FROM mcp.contract_dimension WHERE contract_version_id = v_contract_id;

    -- 5. Dimensión 1: service (Sub-servicio / Especialidad del Taller - inline)
    INSERT INTO mcp.contract_dimension (
        id, contract_version_id, key, position, label, description,
        values_source, apply_mode, required, allows_any, reports_counts
    )
    VALUES (
        v_dim_service_id,
        v_contract_id,
        'service',
        1,
        'Tipo de Servicio de Taller',
        'Especialidad o tipo de servicio automotriz requerido para el vehículo Volvo. Requerido por el taller para consultar los turnos disponibles.',
        'inline',
        'upstream_param',
        true,
        false,
        false
    );

    -- Valores inline para la dimensión service
    INSERT INTO mcp.contract_dimension_value (
        id, contract_version_id, dimension_id, value_key, label, description, position
    )
    VALUES 
        (
            gen_random_uuid(), v_contract_id, v_dim_service_id,
            'Mantenimiento General', 'Mantenimiento General',
            'Mantenimiento preventivo periódico, cambio de aceite, fluidos y filtros de rigor para vehículos Volvo.', 1
        ),
        (
            gen_random_uuid(), v_contract_id, v_dim_service_id,
            'Otros Servicios', 'Otros Servicios',
            'Revisión mecánica general, diagnóstico computarizado del sistema Volvo y evaluación de fallas.', 2
        ),
        (
            gen_random_uuid(), v_contract_id, v_dim_service_id,
            'Cambio de Cristales', 'Cambio de Cristales',
            'Sustitución, sellado y calibración de sensores en parabrisas y cristales originales Volvo.', 3
        ),
        (
            gen_random_uuid(), v_contract_id, v_dim_service_id,
            'Desabolladura y Pintura', 'Desabolladura y Pintura',
            'Reparación de carrocería, desabolladura y acabado de pintura automotriz de alta gama.', 4
        );

    -- 5.1 Dimensión 2: staff (Mecánico / Asesor Técnico - separate_query)
    INSERT INTO mcp.contract_dimension (
        id, contract_version_id, key, position, label, description,
        values_source, apply_mode, required, allows_any, reports_counts, resolver_ref
    )
    VALUES (
        v_dim_staff_id,
        v_contract_id,
        'staff',
        2,
        'Mecánico / Asesor Técnico',
        'Mecánico o técnico especializado asignado para el servicio. Puedes consultar los técnicos disponibles con get_dimension_options(service_id=99, dimension_key=''staff'', context={''service'': ''...''}). Si se omite, el taller asigna el técnico disponible según la tanda.',
        'separate_query',
        'upstream_param',
        false,
        true,
        false,
        'vvautos_staff'
    );

    -- Dependencia: staff depende de service
    INSERT INTO mcp.contract_dimension_dependency (
        contract_version_id, dimension_id, depends_on_dimension_id
    )
    VALUES (
        v_contract_id, v_dim_staff_id, v_dim_service_id
    );

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
        NULL,
        true,
        'VVAutos es un taller especializado exclusivo para vehículos Volvo. Los costos de mano de obra y repuestos originales se cotizan y facturan directamente en el taller tras la evaluación y diagnóstico técnico del vehículo.',
        NOW()
    )
    ON CONFLICT (service_id) DO UPDATE SET 
        pricing_mode = EXCLUDED.pricing_mode,
        currency = EXCLUDED.currency,
        tax_included = EXCLUDED.tax_included,
        info_text = EXCLUDED.info_text,
        updated_at = NOW();

    -- 8. Limpiar cualquier regla estructurada previa en service_price_rule (modo text_only no requiere reglas)
    DELETE FROM mcp.service_price_rule WHERE service_id = v_service_id;

END $$;

-- 9. Reactivar los triggers de inmutabilidad
ALTER TABLE mcp.service_contract_version ENABLE TRIGGER contract_version_guard;
ALTER TABLE mcp.contract_dimension ENABLE TRIGGER contract_dimension_draft_only;
ALTER TABLE mcp.contract_dimension_value ENABLE TRIGGER contract_value_draft_only;
ALTER TABLE mcp.contract_dimension_dependency ENABLE TRIGGER contract_dependency_draft_only;

COMMIT;

