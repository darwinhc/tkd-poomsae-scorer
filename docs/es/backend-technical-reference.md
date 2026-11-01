# Documentación Ultra Detallada y Trazable - TKD Poomsae Scorer Backend

Fecha de actualización: 2026-03-22

Este documento está diseñado para que una persona pueda reconstruir el producto completo leyendo únicamente este archivo y el código fuente. Incluye decisiones de arquitectura, contrato HTTP/WS, estructura de carpetas, configuración, empaquetado, operación LAN, seguridad, pruebas y trazabilidad requisito-a-implementación.

## 0. Guía de lectura

- Si necesitas ejecutar el sistema ya existente: ve a la sección 17.
- Si necesitas recrearlo desde cero: ve a la sección 20.
- Si necesitas validar cumplimiento de requisitos: ve a la sección 21 (matriz de trazabilidad).
- Si necesitas integrar frontend móvil: ve a la sección 10, 11 y 22.
- Si necesitas empaquetar para operador final: ve a la sección 18 y 19.

## 1. Objetivo del producto

Backend local para competencias de Taekwondo Poomsae con:

- múltiples áreas/mesas (stations),
- múltiples jueces conectados por mesa,
- ingestión de eventos de puntaje idempotentes,
- finalización con reconciliación y checksum,
- señalización realtime por WebSocket,
- panel admin local server-rendered,
- pantallas live para TV (pública y debug).

Alcance intencional:

- Solo Poomsae.
- Red local (LAN).
- Operación por un solo ingeniero mantenedor.
- Claridad y trazabilidad por encima de complejidad.

## 2. Principios arquitectónicos obligatorios (aplicados)

### 2.1 Hexagonal Architecture

Separación aplicada:

- `domain`: reglas puras, entidades, value objects, excepciones.
- `application`: casos de uso y DTOs, orquestación.
- `ports`: contratos de dependencias externas.
- `adapters`: implementaciones concretas de puertos.
- `infra`: configuración, persistencia, logging, wiring FastAPI.
- `entry_points`: exposición de rutas HTTP/WS y vistas admin.

Regla crítica:

- FastAPI no contiene lógica de negocio.
- Las reglas viven en `domain` y `application/use_cases`.

### 2.2 Estilo Bisslog (aplicado)

- Casos de uso como centro de orquestación.
- Adapters detrás de puertos.
- Mapping request/response separado de reglas.
- Infra y entry points como borde de transporte.

## 3. Estructura real del proyecto

```text
src/tkd_scorer/
  domain/
    entities/
    value_objects/
    services/
    exceptions/
  application/
    dto/
    mappers/
    use_cases/
  ports/
    repositories/
    services/
    security/
    realtime/
    clock/
    id_generator/
  adapters/
    repositories/
    security/
    qr/
    checksum/
    realtime/
  infra/
    config/
    fastapi/
    persistence/
    logging/
    websocket/
    templates/admin/
    static/admin/
  entry_points/
    runtime_server.py
    fastapi/
      app.py
      api/
      admin_views/
      websocket/

tests/
  unit/
  integration/
  api/

packaging/
  pyinstaller/
    PoomsaeServer.spec
  runtime/
    .env.example
    config/poomsae_categories.yaml
    Start Admin Panel.bat
    start_admin_panel.sh
    OPERATIONS.txt

config/
  poomsae_categories.yaml
  poomsae_categories.example.yaml

Makefile
docs/api-contract.md
README.md
```

## 4. Modelo de dominio

### 4.1 Entidades y estados

Archivo base de enums: `src/tkd_scorer/domain/entities/common.py`

- `StationStatus`: `active`, `occupied`, `offline`
- `SessionStatus`: `active`, `revoked`, `closed`
- `MatchStatus`: `pending`, `in_progress`, `finalization_pending`, `finished`, `cancelled`
- `RoundStatus`: `pending`, `active`, `finished`
- `AthleteSide`: `red`, `blue`

Entidades principales:

- `Station` (`domain/entities/station.py`): mesa/área, credencial, estado, sesión activa de referencia.
- `DeviceSession` (`domain/entities/device_session.py`): identidad juez+dispositivo+token hash.
- `Match` y `MatchRound` (`domain/entities/match.py`): contienda y rondas.
- `ScoreEvent` (`domain/entities/score_event.py`): evento de delta de puntaje auditable.
- `AuditEvent` (`domain/entities/audit.py`): evento de auditoría transversal.

### 4.2 Value Objects

Archivo: `src/tkd_scorer/domain/value_objects/score.py`

- `ScoreDelta`:
  - acepta decimal finito,
  - normaliza a un decimal (`0.1`) con `ROUND_HALF_UP`,
  - permite deltas acumulados (ej: `-0.8`, `-1.0`, `+0.4`), no solo `±0.1/±0.3`.
- `Score`:
  - normaliza a un decimal,
  - aplica delta de forma inmutable.

### 4.3 Servicios de dominio

- `compute_score` (`domain/services/scoring.py`): suma por `sequence` determinístico.
- `aggregate_competitor_results` (`domain/services/poomsae_aggregation.py`):
  - calcula poomsae 1/2 por lado,
  - final = promedio de poomsae 1 y 2,
  - pondera TEC/PRES por pesos configurables.
- `consolidated_score_for_judges` (`domain/services/judge_consolidation.py`):
  - normaliza conteos: `1/2/3/4 -> regla 3`, `5/6 -> regla 5`, `>=7 -> regla 7`,
  - regla 3: promedio simple,
  - regla 5/7: descarta mínimo y máximo, promedia centro.
- `poomsae_draw` (`domain/services/poomsae_draw.py`):
  - catálogo default,
  - override por YAML,
  - validación de selección,
  - sorteo sin repetición.

## 5. Puertos y adaptadores

### 5.1 Puertos (contratos)

- Repositorios:
  - `StationRepositoryPort`
  - `SessionRepositoryPort`
  - `MatchRepositoryPort`
  - `ScoreEventRepositoryPort`
  - `IdempotencyRepositoryPort`
  - `FinalizationRepositoryPort`
  - `AuditRepositoryPort`
- Servicios:
  - `BootstrapServicePort`
  - `ChecksumServicePort`
  - `CredentialGeneratorPort`
- Seguridad:
  - `TokenServicePort`
  - `StationCredentialServicePort`
- Infra:
  - `RealtimePort`
  - `ClockPort`
  - `IdGeneratorPort`

### 5.2 Adaptadores concretos

- SQLAlchemy repos: `adapters/repositories/sqlalchemy_repositories.py`
- JWT tokens: `adapters/security/system_services.py::JwtTokenService`
- Hash credencial estación: `PasswordStationCredentialService`
- Generador credencial numérica: `NumericCredentialGenerator`
- Bootstrap JWT: `adapters/qr/bootstrap_service.py::JwtBootstrapService`
- Checksum SHA-256: `adapters/checksum/sha256_checksum_service.py`
- Realtime FastAPI: `adapters/realtime/fastapi_realtime_adapter.py`
- Clock/IDs: `adapters/security/system_clock_and_ids.py`

## 6. Persistencia

### 6.1 Stack

- SQLAlchemy 2.x
- DB por defecto: SQLite local
- Esquema creado en startup (`create_all`) para operación local simple

Archivos:

- modelos ORM: `infra/persistence/models.py`
- session factory: `infra/persistence/session_factory.py`
- repositorios: `adapters/repositories/sqlalchemy_repositories.py`

### 6.2 Tablas

- `stations`
- `device_sessions`
- `matches`
- `match_rounds`
- `score_events`
- `idempotency_records`
- `finalization_records`
- `audit_events`

### 6.3 Restricciones clave

- `score_events.idempotency_key` único
- `score_events.event_id` único
- `match_rounds(match_id, round_number)` único
- `idempotency_records.key` único
- `finalization_records.idempotency_key` único

## 7. Casos de uso (núcleo de orquestación)

### 7.1 API móvil

- `GenerateBootstrapUseCase`
- `ValidateBootstrapUseCase`
- `ListActiveStationsUseCase`
- `ConnectStationUseCase`
- `RestoreSessionUseCase`
- `CreateMatchUseCase`
- `IngestScoreEventUseCase`
- `FinalizeMatchUseCase`
- `NextRoundUseCase`
- `ResetRoundUseCase`
- `ResetMatchUseCase`
- `GetMatchSummaryUseCase`
- `GetStationActiveSessionUseCase`
- `KickJudgeSessionUseCase`

### 7.2 Admin local

Caso de uso principal:

- `AdminViewUseCases` (`application/use_cases/admin_view_use_cases.py`)

Responsabilidades:

- Dashboard, estaciones, detalle estación
- Crear/borrar estación
- Rotar credencial
- Guardar participantes (borrador)
- Sortear poomsaes (preview)
- Iniciar contienda
- Control de contienda activa (start/stop/pause/reset/finalize round/contienda)
- Snapshot QR/credencial
- Live scoreboard normal y debug
- Resultados e historial
- Publicación WS de eventos administrativos

## 8. Configuración externa

### 8.1 Carga de settings

Archivo: `infra/config/settings.py`

- `pydantic-settings` con prefijo `TKD_`
- carga desde archivo `.env` de runtime
- si `TKD_REQUIRE_ENV_FILE=true` y no existe `.env`, falla startup con mensaje claro

### 8.2 Resolución de rutas runtime

Archivo: `infra/config/runtime_paths.py`

- Soporta ejecución dev y ejecutable PyInstaller
- `TKD_RUNTIME_ROOT` fuerza raíz de runtime
- `.env`, `config/`, `data/`, `logs/` se resuelven relativo a runtime root

### 8.3 Variables principales

- Red: `TKD_HOST`, `TKD_PORT`, `TKD_BASE_URL`, `TKD_PUBLIC_BASE_URL`
- QR/IP: `TKD_QR_USE_SERVER_IP`, `TKD_QR_SERVER_IP_OVERRIDE`
- Seguridad: `TKD_JWT_SECRET_KEY`, `TKD_JWT_ALGORITHM`
- Tokens: `TKD_BOOTSTRAP_TOKEN_TTL_SECONDS`, `TKD_OPERATIONAL_TOKEN_TTL_SECONDS`
- Estaciones: `TKD_STATION_CREDENTIAL_TTL_SECONDS`, `TKD_STATION_CREDENTIAL_ROTATION_SECONDS`
- Admin auth: `TKD_ADMIN_BASE_PATH`, `TKD_ADMIN_PASSWORD`, `TKD_ADMIN_AUTH_COOKIE_*`
- Admin hardening: `TKD_ADMIN_IP_ALLOWLIST`, `TKD_ADMIN_TRUST_PROXY_HEADERS`, `TKD_ADMIN_LOGIN_*`, `TKD_ADMIN_SECURITY_FAIL_FAST`
- Live UI: `TKD_ADMIN_LIVE_REFRESH_SECONDS`, `TKD_ADMIN_LIVE_WINNER_OVERLAY_SECONDS`
- Negocio: `TKD_JUDGE_DEFAULT_*`, `TKD_POOMSAE_*`, `TKD_HISTORY_RETENTION_MATCHES`
- Catálogo YAML: `TKD_REQUIRE_POOMSAE_CATALOG_FILE`, `TKD_POOMSAE_CATALOG_PATH`
- Runtime dirs: `TKD_DATA_DIR`, `TKD_LOGS_DIR`, `TKD_LOG_FILE_NAME`

## 9. Flujo QR bootstrap

### 9.1 Generación

Endpoint: `POST /bootstrap/generate`

Genera payload con:

- `baseUrl`
- `stationId`
- `stationName`
- `bootstrapToken`
- `environment`
- `tournamentId`
- `protocolVersion`
- `expiresAt` (ISO UTC con `Z`)

### 9.2 Validación

Endpoint: `POST /bootstrap/validate`

- valida JWT bootstrap
- retorna claims

### 9.3 Resolución de base URL

Implementación: `infra/config/runtime_base_url.py`

- Detecta IPv4 del servidor cuando corresponde
- Reemplaza host para QR manteniendo esquema/puerto/path
- Soporta override explícito

## 10. Contrato HTTP (estado actual)

Router real: `infra/fastapi/routes.py`
Schemas: `infra/fastapi/schemas.py`

### 10.1 Endpoints

- `GET /health`
- `POST /bootstrap/generate`
- `POST /bootstrap/validate`
- `GET /stations/active`
- `POST /stations/connect`
- `POST /sessions/restore`
- `POST /matches`
- `POST /score-events`
- `POST /matches/finalize`
- `POST /matches/{match_id}/next-round`
- `POST /matches/{match_id}/reset-round`
- `POST /matches/{match_id}/reset-match`
- `GET /matches/{match_id}/summary`
- `GET /stations/{station_id}/active-session`

### 10.2 Reglas críticas de `/score-events`

- Requiere bearer token válido.
- Valida coherencia token vs body (`sessionId`, `stationId`, `judgeName`).
- `matchId` obligatorio y canónico backend.
- Sin fallback por sesión/estación/juez si `matchId` no existe.
- Si falta o no existe `matchId`: `422`.
- Idempotencia por `idempotencyKey` (body/header).
- Manejo de secuencia:
  - acepta llegada fuera de orden,
  - si llega misma secuencia+mismo payload para la misma sesión: replay idempotente,
  - si llega misma secuencia con payload distinto: `422`.

### 10.3 Reglas críticas de `/matches/finalize`

- Requiere bearer token válido.
- Valida coherencia token vs body.
- `matchId` obligatorio y canónico backend.
- Sin fallback por sesión/estación/juez.
- Si falta o no existe `matchId`: `422`.
- Idempotencia por `idempotencyKey` (o fallback de llave calculada).
- Reconciliación valida:
  - `totalEvents`
  - `lastSequence`
  - score final red/blue
  - `roundsSummary`
  - checksum

## 11. Contrato WebSocket

Endpoint: `WS /ws`
Implementación: `infra/fastapi/websocket_routes.py`

### 11.1 Formas de bind

- Query string: `sessionId`, `stationId`, `token`
- Mensaje `type=bind`

### 11.2 Eventos emitidos por servidor

- `server_notice`
- `judge_settings_updated`
- `active_match_state`
- `match_updated`
- `round_changed`
- `reset_round`
- `reset_match`
- `new_competitors`
- `station_disconnected`
- `judge_kicked`
- `session_revoked`
- `ping` (respuesta pong)

Envelope:

```json
{
  "type": "event_name",
  "eventType": "event_name",
  "payload": {}
}
```

### 11.3 Señales desde app por WS

- `judge_round_completed`
- `judge_match_completed`

Son opcionales de señalización; el flujo principal de puntaje/finalización sigue por HTTP.

## 12. Admin frontend local (mismo backend)

### 12.1 Principio

No hay frontend separado. FastAPI sirve:

- API JSON,
- WS,
- HTML admin Jinja2,
- assets estáticos.

### 12.2 Stack UI

- Jinja2 templates
- Tailwind vía CDN
- Lucide icons vía CDN
- JS liviano in-template para polling/control visual

### 12.3 Rutas admin principales

- Login/logout:
  - `GET /admin/login`
  - `POST /admin/login`
  - `POST /admin/logout`
- Dashboard:
  - `GET /admin`
- Estación:
  - `POST /admin/stations/create`
  - `GET /admin/stations/{station_id}`
  - `POST /admin/stations/{station_id}/rotate-credential`
  - `POST /admin/stations/{station_id}/delete`
  - `POST /admin/stations/{station_id}/sessions/{session_id}/kick`
  - `GET /admin/stations/{station_id}/qr.png`
- Contienda y configuración:
  - `POST /admin/stations/{station_id}/matches/save-competitors`
  - `POST /admin/stations/{station_id}/matches/draw`
  - `POST /admin/stations/{station_id}/matches/draw-preview`
  - `POST /admin/stations/{station_id}/matches/start`
  - `POST /admin/stations/{station_id}/active-match/start-round`
  - `POST /admin/stations/{station_id}/active-match/stop-round`
  - `POST /admin/stations/{station_id}/active-match/pause-timer`
  - `POST /admin/stations/{station_id}/active-match/reset-round`
  - `POST /admin/stations/{station_id}/active-match/finalize`
- Live:
  - público: `GET /scoreboard/{station_id}` y `GET /scoreboard/{station_id}/live`
  - debug (protegido):
    - `GET /admin/stations/{station_id}/scoreboard/debug`
    - `GET /admin/stations/{station_id}/scoreboard/debug/live`
- Reportes:
  - `GET /admin/matches/{match_id}`
  - `GET /admin/results`
  - `GET /admin/history`
  - `POST /admin/history/{match_id}/delete`
  - `POST /admin/history/delete-all`

### 12.4 Comportamientos UI relevantes

- Labels en español (`status_es` filter).
- Pantalla live no-debug:
  - diseño sticky/fullscreen,
  - bloqueo en pantallas pequeñas o verticales,
  - cronómetro renderizado del lado JS con referencia de backend,
  - overlay de ganador auto-cerrable (`TKD_ADMIN_LIVE_WINNER_OVERLAY_SECONDS`).
- Pantalla live debug:
  - incluye deltas por juez.
- Lista de jueces activos muestra estado de conexión real (WS bound vs solo sesión persistida).

## 13. Seguridad y hardening local

### 13.1 Seguridad de API/juez

- JWT access token por sesión de juez.
- hash de token en DB.
- validación de claims en restore/WS.
- credencial de estación hasheada con passlib (`pbkdf2_sha256`).

### 13.2 Seguridad admin

Middleware: `entry_points/fastapi/app.py` + `infra/fastapi/admin_auth.py`

- Password admin por `.env` (`TKD_ADMIN_PASSWORD`).
- Cookie httpOnly para sesión admin.
- Base path admin configurable (`TKD_ADMIN_BASE_PATH`).
- Allowlist IP/CIDR (`TKD_ADMIN_IP_ALLOWLIST`).
- Lockout por intentos fallidos (`TKD_ADMIN_LOGIN_*`).
- `TKD_ADMIN_SECURITY_FAIL_FAST=true` bloquea startup si seguridad mínima no cumple.

### 13.3 Rutas públicas intencionales

- Live no-debug permanece pública para TV:
  - `/scoreboard/{station_id}`
  - `/scoreboard/{station_id}/live`

### 13.4 Rutas protegidas

- Todo `/admin/*` excepto login/logout y aliases públicos específicos.
- Debug live permanece protegido.

## 14. Reglas de negocio clave implementadas

### 14.1 Conectividad de jueces

- Múltiples jueces activos por estación permitidos.
- No permite:
  - mismo juez en dos dispositivos activos,
  - mismo dispositivo con dos jueces activos.
- Sesión persistida puede seguir activa aunque WS se cierre.
- Estado "conectado" en UI depende de conexión WS real (`ConnectionHub`).

### 14.2 Idempotencia y auditoría

- Score events y finalización con idempotencia explícita.
- Auditoría de acciones críticas en `audit_events`.

### 14.3 Consolidación de resultados

- Conteos 1/2/4 usan regla de 3.
- Conteo 6 usa regla de 5.
- 3/5/7 oficiales; otros permitidos en modo prueba.
- Gana quien tenga mayor puntaje (red/blue).

### 14.4 Contienda activa

- Control de rounds con timer persistido en auditoría.
- Al iniciar contienda se publica WS `new_competitors`, `match_updated`, `active_match_state`, `judge_settings_updated`.
- Admin puede finalizar contienda activa manualmente.

### 14.5 Gestión de historial

- Se permite borrar contiendas del historial de forma individual y masiva.
- Una contienda se considera protegida (no borrable) cuando:
  - estado `in_progress` o `finalization_pending`, y
  - la sesión asociada sigue activa.
- Si está en `finalization_pending` pero la sesión ya no está activa, sí se permite borrar.
- En borrado masivo, backend elimina las no protegidas y omite las protegidas.

## 15. Logging y observabilidad

Archivo: `infra/logging/logger.py`

- Formato JSON estructurado.
- Salida a consola + archivo (`logs/tkd_server.log`).
- Logs relevantes:
  - ingestión score recibido/ok/fail,
  - finalize recibido/procesado/fail,
  - eventos WS y desconexión,
  - errores de seguridad/configuración.

## 16. Pruebas y cobertura funcional

### 16.1 Unitarias

Carpeta: `tests/unit/`

Cobertura destacada:

- score calculation y orden por secuencia,
- consolidación 3/5/7 y conteos de prueba,
- conexión de estación y conflictos de identidad,
- restore session y validación token,
- idempotencia score event,
- reglas de round/reset,
- finalización + reconciliación + WS,
- kick de juez,
- draw de poomsaes y YAML override,
- runtime base URL,
- runtime bootstrap,
- settings desde `.env`,
- controles de contienda admin.

### 16.2 Integración

Carpeta: `tests/integration/`

- roundtrip de repositorios SQLAlchemy sobre DB real.

### 16.3 API

Carpeta: `tests/api/`

- flujo bootstrap/connect/restore,
- idempotencia de `/score-events`,
- finalize con `matchId` inválido -> `422`,
- emisión de eventos WS iniciales,
- render/admin auth routes.

## 17. Ejecución local (desarrollo)

### 17.1 Requisitos

- Python 3.11+
- `pip`
- entorno virtual recomendado

### 17.2 Instalación

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev,packaging]'
```

### 17.3 Configuración mínima

1. Copiar `.env.example` a `.env`.
2. Ajustar:

- `TKD_HOST=0.0.0.0`
- `TKD_PORT=8080`
- `TKD_BASE_URL` y `TKD_PUBLIC_BASE_URL`
- `TKD_JWT_SECRET_KEY`
- `TKD_ADMIN_PASSWORD`
- `TKD_ADMIN_BASE_PATH`

3. Validar existencia de `config/poomsae_categories.yaml`.

### 17.4 Arranque

```bash
uvicorn tkd_scorer.entry_points.fastapi.app:app --host 0.0.0.0 --port 8080 --reload
```

### 17.5 URLs típicas

- Health: `http://<IP_LAN>:8080/health`
- Admin: `http://<IP_LAN>:8080<ADMIN_BASE_PATH>`
- Live público: `http://<IP_LAN>:8080/scoreboard/<station_id>`
- WS app: `ws://<IP_LAN>:8080/ws?...`

## 18. Empaquetado ejecutable (operador final)

### 18.1 Estrategia

- PyInstaller `onedir` (no `onefile`)
- razón:
  - más robusto para templates/static,
  - mejor manejo de recursos y debugging,
  - menos problemas de extracción temporal.

### 18.2 Spec file

Archivo: `packaging/pyinstaller/PoomsaeServer.spec`

Incluye:

- entrypoint `src/tkd_scorer/entry_points/runtime_server.py`
- recursos empaquetados:
  - `infra/templates/**/*.html`
  - `infra/static/**/*`
- hidden imports:
  - `tkd_scorer` submódulos
  - `uvicorn` submódulos
  - `passlib.handlers` submódulos

### 18.3 Makefile de automatización

Archivo: `Makefile`

Targets:

- `make help`
- `make clean`
- `make package-linux`
- `make package-windows`
- `make package-all`

Nota crítica:

- PyInstaller no cross-compila oficialmente Linux<->Windows.
- Debes empaquetar en cada OS destino.

### 18.4 Estructura de entrega esperada

```text
PoomsaeServer/
  PoomsaeServer/
    PoomsaeServer(.exe)
    _internal/...
  .env
  config/
    poomsae_categories.yaml
  data/
  logs/
  Start Admin Panel.bat / start_admin_panel.sh
  OPERATIONS.txt
```

## 19. Runtime del ejecutable

### 19.1 Entry point runtime

Archivo: `src/tkd_scorer/entry_points/runtime_server.py`

- carga settings desde `.env` runtime,
- inicia uvicorn,
- errores fatales mostrados con mensaje operador-friendly,
- termina con código no-cero en falla.

### 19.2 Resolución de rutas en modo empaquetado

Archivo: `infra/config/runtime_paths.py`

- detecta modo frozen (`sys.frozen`),
- usa directorio del ejecutable como runtime root,
- soporta override con `TKD_RUNTIME_ROOT`.

### 19.3 Bootstrap de runtime

Archivo: `infra/config/runtime_bootstrap.py`

- crea `data/` y `logs/` si faltan,
- valida YAML de poomsaes si está requerido,
- resuelve SQLite a ruta absoluta writable,
- prepara log file path.

### 19.4 Launchers

- Windows: `packaging/runtime/Start Admin Panel.bat`
- Linux: `packaging/runtime/start_admin_panel.sh`

Ambos:

- exportan/definen `TKD_RUNTIME_ROOT`,
- arrancan ejecutable,
- abren navegador al panel admin local.

## 20. Procedimiento para recrear todo desde cero

1. Crear repositorio Python con `src/` layout y `pyproject.toml`.
2. Definir capas hexagonales (`domain`, `application`, `ports`, `adapters`, `infra`, `entry_points`).
3. Implementar entidades y value objects de dominio.
4. Implementar puertos de repositorio/servicios/realtime/security.
5. Implementar adapters SQLAlchemy/JWT/checksum/realtime/clock/id.
6. Implementar casos de uso uno por flujo principal.
7. Implementar modelos SQLAlchemy y session factory.
8. Implementar wiring DI (`infra/fastapi/dependencies.py`).
9. Implementar rutas API FastAPI sin lógica de negocio.
10. Implementar WS endpoint y `ConnectionHub`.
11. Implementar admin auth middleware y helpers.
12. Implementar vistas admin Jinja2 y static.
13. Implementar live panel público + debug protegido.
14. Implementar settings runtime con `.env` obligatorio.
15. Implementar `prepare_runtime` para dirs/logs/db/yaml.
16. Añadir logging JSON estructurado.
17. Añadir suite de tests unit/integration/api.
18. Añadir packaging:

- `runtime_server.py`
- `.spec` PyInstaller onedir
- launchers `.bat`/`.sh`
- `Makefile`
- README operador

19. Validar contrato backend con app móvil (`docs/api-contract.md`).
20. Congelar release con carpeta de entrega para operador final.

## 21. Matriz de trazabilidad de requisitos (resumen ultra práctico)

Formato: `ID | Requisito | Implementación principal | Prueba | Estado`

- `REQ-001 | FastAPI solo entrada | entry_points + infra/fastapi/routes.py + use_cases | tests/api/test_fastapi_endpoints.py | OK`
- `REQ-002 | Hexagonal/Bisslog | estructura src + ports/adapters/use_cases | revisión estructural + tests | OK`
- `REQ-003 | Judge name obligatorio | ConnectStationUseCase | tests/unit/test_station_connection.py | OK`
- `REQ-004 | Sesión persistente con token | connect + restore session | tests/unit/test_session_restore_and_token.py | OK`
- `REQ-005 | QR bootstrap con metadata | GenerateBootstrapUseCase + routes | tests/api/test_fastapi_endpoints.py | OK`
- `REQ-006 | matchId obligatorio score-events | IngestScoreEventUseCase | tests/unit/test_idempotency_score_event.py | OK`
- `REQ-007 | matchId obligatorio finalize | FinalizeMatchUseCase | tests/api/test_fastapi_endpoints.py | OK`
- `REQ-008 | Idempotencia score-events | idempotency_records + use case | tests/unit/test_idempotency_score_event.py | OK`
- `REQ-009 | Idempotencia finalización | finalization_records + use case | tests/unit/test_finalization_and_websocket.py | OK`
- `REQ-010 | WS realtime por estación/sesión | RealtimePort + ConnectionHub + ws routes | tests/unit/test_websocket_hub.py | OK`
- `REQ-011 | reset round/match auditable | control_match_use_cases + audit | tests/unit/test_round_and_reset_logic.py | OK`
- `REQ-012 | finalización con checksum | FinalizeMatchUseCase + Sha256ChecksumService | tests/unit/test_finalization_and_websocket.py | OK`
- `REQ-013 | admin frontend en mismo proyecto | templates + admin routes | tests/api/test_admin_routes.py | OK`
- `REQ-014 | labels admin en español | templates + labels.py | tests/api/test_admin_routes.py | OK`
- `REQ-015 | live pública y debug protegida | middleware + routes | tests/api/test_admin_routes.py | OK`
- `REQ-016 | estado conectado real de juez | ConnectionHub + AdminViewUseCases filtros | tests/unit/test_websocket_hub.py + admin tests | OK`
- `REQ-017 | expulsar juez de mesa | KickJudgeSessionUseCase + WS judge_kicked | tests/unit/test_kick_judge_session_use_case.py | OK`
- `REQ-018 | sorteo poomsaes por categoría | poomsae_draw + admin use case | tests/unit/test_poomsae_draw.py + test_admin_start_contienda.py | OK`
- `REQ-019 | configuración externa YAML | poomsae_draw + runtime_bootstrap | tests/unit/test_poomsae_draw.py + test_runtime_bootstrap.py | OK`
- `REQ-020 | configuración externa .env | settings + runtime_paths | tests/unit/test_settings_runtime_env.py | OK`
- `REQ-021 | packaging ejecutable onedir | spec + runtime entry + Makefile | validación manual + build targets | OK`
- `REQ-022 | launcher anti-dummy | Start Admin Panel.bat/sh | validación manual | OK`
- `REQ-023 | logging estructurado | infra/logging/logger.py | validación runtime | OK`
- `REQ-024 | contrato backend sincronizado con app | docs/api-contract.md compartido | diff/sha256 | OK`

## 22. Contrato backend-app (sincronización)

Archivos comparados:

- `docs/api-contract.md` (único contrato compartido por backend y app)

Estado actual:

- sincronizados (mismo contenido/hash)

Regla operativa recomendada:

1. Cambiar contrato primero.
2. Aplicar cambios backend + tests.
3. Aplicar cambios app.
4. Verificar diff vacío entre ambos archivos.

## 23. Limitaciones actuales y decisiones explícitas

- Sesión de juez puede permanecer activa en DB aunque WS esté desconectado (diseño deliberado para offline/reintento).
- Estado "conectado" visual se basa en WS activo, no solo sesión persistida.
- `create_all` en startup facilita operación local, pero no sustituye migraciones versionadas (Alembic) para evolución compleja.
- Lockout de login admin es in-memory por proceso.
- Live no-debug pública por requerimiento operativo de TV.

## 24. Checklist de aceptación de release

- `.env` existe y no usa secretos por defecto.
- `config/poomsae_categories.yaml` válido.
- `GET /health` responde 200.
- flujo completo:

1. crear mesa,
2. conectar juez,
3. iniciar contienda,
4. enviar score-events,
5. visualizar live,
6. finalizar,
7. validar reconciliación.

- `/score-events` y `/matches/finalize` rechazan `matchId` inválido con `422`.
- WS entrega `judge_settings_updated` y `active_match_state` al bind.
- Tests pasan (`pytest`).
- Packaging genera carpeta de entrega operable.

## 25. Comandos de operación rápida

### 25.1 Tests

```bash
pytest
```

### 25.2 Lint

```bash
ruff check src tests
```

### 25.3 Packaging

```bash
make clean
make package-linux
# o
make package-windows
```

### 25.4 Ejecutar binario empaquetado (Linux)

```bash
cd dist/linux/PoomsaeServer
./start_admin_panel.sh
```

## 26. Referencias de archivos críticos

- App bootstrap: `src/tkd_scorer/entry_points/fastapi/app.py`
- API routes: `src/tkd_scorer/infra/fastapi/routes.py`
- WS routes: `src/tkd_scorer/infra/fastapi/websocket_routes.py`
- Admin routes: `src/tkd_scorer/entry_points/fastapi/admin_views/routes.py`
- Admin use cases: `src/tkd_scorer/application/use_cases/admin_view_use_cases.py`
- Score ingest: `src/tkd_scorer/application/use_cases/ingest_score_event_use_case.py`
- Finalize: `src/tkd_scorer/application/use_cases/finalize_match_use_case.py`
- Settings: `src/tkd_scorer/infra/config/settings.py`
- Runtime bootstrap: `src/tkd_scorer/infra/config/runtime_bootstrap.py`
- Runtime paths: `src/tkd_scorer/infra/config/runtime_paths.py`
- SQLAlchemy repos: `src/tkd_scorer/adapters/repositories/sqlalchemy_repositories.py`
- ORM models: `src/tkd_scorer/infra/persistence/models.py`
- PyInstaller spec: `packaging/pyinstaller/PoomsaeServer.spec`
- Makefile: `Makefile`
- Contrato backend: `docs/api-contract.md`

---

Si este documento se mantiene actualizado junto con el contrato, permite reconstrucción técnica, operación de torneo y mantenimiento evolutivo sin dependencia tácita de conocimiento oral.
