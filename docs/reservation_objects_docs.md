# Documentación: Reservation Objects y el Patrón "Resolve or Create"

Esta guía explica la arquitectura de los **Reservation Objects**, cómo funcionan sus esquemas de validación, y cómo interactúan con el sistema de reservas principal mediante el patrón *Resolve or Create*.

---

## 1. Conceptos Base

### 1.1 ¿Qué es un Reservation Object?
Un `ReservationObject` es una entidad que guarda información persistente de un usuario que se requiere de manera recurrente para realizar reservas en ciertos establecimientos.

En lugar de pedirle al usuario que llene toda la información de su vehículo cada vez que va al taller, o todo su perfil médico cada vez que va al doctor, guardamos esa información como un `ReservationObject` vinculado a su `user_phone`.

Cada objeto tiene un **`object_alias`** opcional: un nombre amigable que el usuario (o la app) le asigna para identificarlo fácilmente. Ejemplo: `"Mi Toyota Azul"` o `"Carro del trabajo"`. Es puramente descriptivo y no afecta la validación del payload.

### 1.2 Esquemas (`ReservationObjectSchema`)
Los objetos no tienen un formato rígido en la base de datos (se guardan como un payload JSON). Para darle estructura, cada objeto pertenece a un **Schema**.

- **`schema_header`**: Es el identificador único del esquema, usualmente con el formato `combo_code:tipo` (ejemplo: `vvautos_taller:vehiculo`).
- **`section_name`**: Nombre de sección legible para el humano, pensado para ser desplegado en interfaces gráficas (ej: `"Tus Vehículos"`, `"Tu Información Médica"`). El default es `"Tus datos"`.
- **`service_id`**: ID del servicio al que pertenece el schema. Un schema puede estar asociado a un servicio sin estar vinculado a un establecimiento específico.
- **`establishment_id`**: ID del establecimiento al que pertenece el schema (nullable). Si es `null`, el schema es genérico para el servicio.
- **Esquema JSON**: Define qué campos son obligatorios, qué tipo de dato son, etc.
- **Validadores**: En código, usamos subclases de `ReservObjectSchemaValidator` (ej: `VvautosTallerVehiculoValidator`) para garantizar estrictamente que el payload del objeto cumpla con las reglas del esquema antes de guardarlo.

---

## 2. Casos de Uso y Endpoints Directos (CRUD)

El sistema expone endpoints HTTP directos para administrar estos objetos de manera independiente a las reservas. Esto es útil si tienes una pantalla en la app móvil tipo "Mis Vehículos" o "Mis Perfiles".

### Obtener los objetos de un usuario
- **Use Case**: `GetObjectsBySchemaUseCase`
- **Endpoint**: `GET /reservation-objects/{schema_header}/users/{phone}`
- **Para qué sirve**: Devuelve la estructura del esquema (para armar un formulario dinámico en UI o darle contexto al agente de IA) y una lista de todos los objetos asociados a ese número de teléfono.

**Ejemplo de Respuesta:**
```json
{
  "schema": {
    "id": 1,
    "schema_header": "vvautos_taller:vehiculo",
    "service_id": 99,
    "establishment_id": null,
    "section_name": "Tus Vehículos",
    "schema_fields": [
      {
        "field_name": "vehicle_model",
        "is_required": true,
        "data_type": "string",
        "validation_rules": {},
        "high_variance_flag": false,
        "description": "Modelo del vehículo"
      },
      {
        "field_name": "vehicle_plate",
        "is_required": true,
        "data_type": "string",
        "validation_rules": {},
        "high_variance_flag": false,
        "description": "Placa del vehículo"
      },
      {
        "field_name": "vehicle_chassis",
        "is_required": true,
        "data_type": "string",
        "validation_rules": {},
        "high_variance_flag": false,
        "description": "Número de chasis del vehículo"
      },
      {
        "field_name": "vehicle_mileage",
        "is_required": true,
        "data_type": "string",
        "validation_rules": {},
        "high_variance_flag": true,
        "description": "Kilometraje actual del vehículo"
      }
    ]
  },
  "objects": [
    {
      "id": 1,
      "schema_id": 1,
      "user_phone": "+18094251911",
      "object_alias": "Mi Volvo del trabajo",
      "object_payload": {
        "vehicle_model": "Volvo XC60",
        "vehicle_plate": "A123457",
        "vehicle_chassis": "YV1UZ1234K1234567",
        "vehicle_mileage": "85420"
      },
      "created_at": "2026-09-02T16:26:23.887736Z",
      "updated_at": "2026-09-02T16:26:23.887736Z"
    },
    {
      "id": 3,
      "schema_id": 1,
      "user_phone": "+18094251911",
      "object_alias": "Mi Toyota Azul",
      "object_payload": {
        "vehicle_model": "Toyota Tacoma 2026",
        "vehicle_plate": "L123456",
        "vehicle_chassis": "JTEBX9FJ50K123456",
        "vehicle_mileage": "25000"
      },
      "created_at": "2026-09-02T18:35:11.908361Z",
      "updated_at": "2026-09-02T18:35:11.908361Z"
    }
  ]
}
```

> [!TIP]
> **Campos de alta variación (`high_variance_flag`)**:
> Cuando el agente de IA (como ATLAS) o un cliente móvil recibe este esquema, debe prestar especial atención a los campos que tienen `"high_variance_flag": true`. Por ejemplo, el kilometraje (`vehicle_mileage`) cambia constantemente. Es una buena práctica que el agente le pregunte proactivamente al usuario *"Veo que tu último kilometraje registrado era de 25,000, ¿sigue siendo ese o ha cambiado?"* antes de proceder con la reserva.

> [!NOTE]
> **Uso del `section_name` en la UI**:
> El campo `section_name` del schema está pensado para ser el título de sección en pantallas tipo "Mis datos guardados". Por ejemplo, si `section_name = "Tus Vehículos"`, la app puede renderizar una sección con ese título agrupando todos los objetos de ese schema. El `object_alias` de cada objeto funciona como su nombre visible dentro de esa sección.

### Buscar schemas por texto
- **Use Case**: `SearchReservationObjectSchemasUseCase`
- **Endpoint**: `GET /reservation-objects/schemas/search?query={texto}&limit=50&offset=0`
- **Para qué sirve**: Búsqueda paginada por coincidencia parcial (ILIKE) en el `schema_header`.

### Listar schemas por service_id
- **Use Case**: `GetSchemasByServiceIdUseCase`
- **Endpoint**: `GET /reservation-objects/schemas/by-service/{service_id}?limit=50&offset=0`
- **Para qué sirve**: Obtiene todos los schemas asociados a un servicio, paginados. Útil para cargar los tipos de objetos disponibles para un servicio dado.

### Listar schemas por establishment_id
- **Use Case**: `GetSchemasByEstablishmentIdUseCase`
- **Endpoint**: `GET /reservation-objects/schemas/by-establishment/{establishment_id}?limit=50&offset=0`
- **Para qué sirve**: Obtiene todos los schemas vinculados a un establecimiento específico, paginados.

**Todos los endpoints de schemas devuelven la misma estructura `PaginatedSchemasResponse`:**
```json
{
  "total": 1,
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "id": 1,
      "schema_header": "vvautos_taller:vehiculo",
      "service_id": 99,
      "establishment_id": null,
      "section_name": "Tus Vehículos",
      "schema_fields": [ "..." ]
    }
  ]
}
```

### Crear un objeto nuevo manualmente
- **Use Case**: `CreateReservationObjectUseCase`
- **Endpoint**: `POST /reservation-objects/{schema_header}`
- **Para qué sirve**: Crea un objeto nuevo validándolo contra su esquema. El campo `object_alias` es opcional (máx. 40 caracteres).

**Payload:**
```json
POST /reservation-objects/vvautos_taller:vehiculo

{
  "user_phone": "18091234567",
  "object_alias": "Mi Toyota Camry Azul",
  "payload": {
    "vehicle_model": "Toyota Camry 2021",
    "vehicle_plate": "A123456",
    "vehicle_chassis": "4T1BF1FK5MU123456",
    "vehicle_mileage": "45000"
  }
}
```

### Actualizar un objeto
- **Use Case**: `UpdateReservationObjectUseCase`
- **Endpoint**: `PATCH /reservation-objects/{object_id}`
- **Para qué sirve**: Actualiza campos de un objeto existente (merge shallow con el payload original). El caso de uso verifica que el objeto pertenezca al `user_phone` que está haciendo la petición. El `object_alias` se actualiza solo si se envía; si no se envía, se mantiene el existente.

**Payload:**
```json
PATCH /reservation-objects/4

{
  "schema_header": "vvautos_taller:vehiculo",
  "user_phone": "18091234567",
  "object_alias": "Mi Toyota Azul - Actualizado",
  "modifications": {
    "vehicle_mileage": "48500"
  }
}
```

### Eliminar un objeto (Soft Delete)
- **Use Case**: `DeleteReservationObjectUseCase`
- **Endpoint**: `DELETE /reservation-objects/{object_id}`

---

## 3. El Patrón "Resolve or Create" en las Reservas

Obligar al cliente (ATLAS o App) a crear el objeto *antes* de mandar la reserva requeriría dos peticiones HTTP. Para simplificarlo, implementamos el **`ResolveOrCreateReservationObjectUseCase`**.

Este caso de uso es invocado directamente por el **Payload Builder** (ej. `VvautosTallerPayloadBuilder`) cuando entra una petición a `POST /reservations`. Analiza el sub-objeto `vehicle` enviado en el payload y decide si debe **Crear**, **Recuperar** o **Actualizar** el objeto *al vuelo*, justo antes de mandar la petición a automatización.

### Value Object: `ResolveOrCreateReservationObject`

El PayloadBuilder espera recibir este diccionario incrustado en los datos de la reserva:

```json
{
  "schema_header": "vvautos_taller:vehiculo",
  "object_id": null,
  "modifications_payload": null,
  "new_object_payload": { "..." },
  "new_object_alias": "Mi Toyota Camry"
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `schema_header` | `string` | Obligatorio. Header del schema al que pertenece el objeto. |
| `object_id` | `int \| null` | ID del objeto existente. Nulo si se va a crear uno nuevo. |
| `new_object_payload` | `dict \| null` | Payload completo del nuevo objeto. Obligatorio si `object_id` es nulo. |
| `new_object_alias` | `string \| null` | **Obligatorio cuando `new_object_payload` está presente.** Alias descriptivo del objeto nuevo (ej: `"Mi Toyota Azul"`). |
| `modifications_payload` | `dict \| null` | Campos a modificar sobre un objeto existente. Se usa junto con `object_id`. |

> [!IMPORTANT]
> Al enviar `new_object_payload` (crear un vehículo nuevo en el flujo de reserva), **`new_object_alias` es obligatorio**. Si se omite, el sistema retornará un error de validación con código `RM-VVAUTOS-003`.

A continuación, 3 ejemplos de cómo invocar a `POST /reservations` para disparar distintas lógicas internas de este patrón:

### Variante A: Vehículo Nuevo (Creación)
> El cliente **no** tiene el vehículo guardado. Envía `object_id: null` y el payload completo más el `new_object_alias`. El sistema creará el `ReservationObject` en BD y usará esa data para la reserva.

```json
{
  "establishment_code": "vvautos_taller",
  "user_phone": "+18094251911",
  "reservation": {
    "date": "2026-09-04",
    "time": "10:00",
    "service": "Mantenimiento General",
    "customer_name": "Gabriel Guzman",
    "customer_email": "gabriel@gmail.com",
    "customer_phone": "18095551234",
    "country_code": "DO",
    "wash_vehicle": "Sí",
    "headless": true,
    "test_mode": true,
    "vehicle": {
      "schema_header": "vvautos_taller:vehiculo",
      "object_id": null,
      "modifications_payload": null,
      "new_object_alias": "Mi Toyota Nueva",
      "new_object_payload": {
        "vehicle_model": "Toyota Tacoma 2026",
        "vehicle_plate": "L123456",
        "vehicle_chassis": "JTEXXXXXX1234",
        "vehicle_mileage": "15000"
      }
    }
  },
  "webhook_url": "https://webhook.site/..."
}
```

### Variante B: Vehículo Existente (Solo Recuperación)
> El cliente **ya tiene** el vehículo guardado (ID 3) y no hay cambios. Envía solo el `object_id`. El sistema recuperará la info de la BD para armar el payload de automatización.

```json
{
  "establishment_code": "vvautos_taller",
  "user_phone": "+18094251911",
  "reservation": {
    "date": "2026-09-04",
    "time": "10:00",
    "service": "Mantenimiento General",
    "customer_name": "Gabriel Guzman",
    "customer_email": "gabriel@gmail.com",
    "customer_phone": "18095551234",
    "country_code": "DO",
    "wash_vehicle": "Sí",
    "headless": true,
    "test_mode": true,
    "vehicle": {
      "schema_header": "vvautos_taller:vehiculo",
      "object_id": 3,
      "modifications_payload": null,
      "new_object_payload": null,
      "new_object_alias": null
    }
  },
  "webhook_url": "https://webhook.site/..."
}
```

### Variante C: Vehículo Existente + Modificación (Actualización)
> El cliente usa su vehículo existente (ID 3) pero el kilometraje cambió. El sistema usará el `UpdateReservationObjectUseCase` para mezclar la data existente con las modificaciones, validará el nuevo resultado contra el esquema, guardará los cambios en BD y enviará la reserva.

```json
{
  "establishment_code": "vvautos_taller",
  "user_phone": "+18094251911",
  "reservation": {
    "date": "2026-09-04",
    "time": "10:00",
    "service": "Mantenimiento General",
    "customer_name": "Gabriel Guzman",
    "customer_email": "gabriel@gmail.com",
    "customer_phone": "18095551234",
    "country_code": "DO",
    "wash_vehicle": "Sí",
    "headless": true,
    "test_mode": true,
    "vehicle": {
      "schema_header": "vvautos_taller:vehiculo",
      "object_id": 3,
      "new_object_payload": null,
      "new_object_alias": null,
      "modifications_payload": {
        "vehicle_mileage": "18500"
      }
    }
  },
  "webhook_url": "https://webhook.site/..."
}
```

---

> [!NOTE]
> **Resumen del Flujo Interno:**
> 1. Llega HTTP `POST /reservations`
> 2. `CreateReservationUseCase` intercepta el payload y localiza al builder (`VvautosTallerPayloadBuilder`).
> 3. El Builder extrae el diccionario `"vehicle"`, lo convierte al VO `ResolveOrCreateReservationObject` (incluyendo `new_object_alias` si aplica) y llama a `ResolveOrCreateReservationObjectUseCase.execute(vo)`.
> 4. El caso de uso hace la lógica (Crea, Recupera o Actualiza) según qué campos vinieron en el VO. En la ruta de creación, pasa `new_object_alias` al `CreateReservationObjectCommand`.
> 5. El Builder recibe la entidad `ReservationObject` fresca, extrae sus datos (`vehicle_model`, `vehicle_plate`, etc.) y termina de armar el payload plano que el backend de automatización (Selenium/Playwright) necesita.
