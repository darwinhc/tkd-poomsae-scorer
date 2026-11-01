# Contrato Backend Esperado (Actualizado)

Fecha: 2026-03-22  
Protocolo: `v1`

## 1) Regla clave nueva

El **QR debe incluir la mesa** (`stationId`).  
La app conecta usando esa mesa, no una seleccionada manualmente en UI.

Además:
- si el backend quiere sacar a un juez del área, debe enviar evento WS de revocación/desconexión;
- después de eso, el juez debe volver a escanear QR + PIN para reconectar.

## 2) QR bootstrap (obligatorio)

```json
{
  "baseUrl": "http://192.168.1.20:8080",
  "stationId": "mesa-01",
  "stationName": "Mesa 1",
  "bootstrapToken": "short-lived-token",
  "environment": "tournament-local",
  "tournamentId": "tkd-poomsae-2026-01",
  "protocolVersion": "v1",
  "expiresAt": "2026-12-31T23:59:59.000Z"
}
```

Validaciones app:
- `baseUrl`: URL válida
- `stationId`: requerido
- `expiresAt`: no expirado

## 3) Endpoints HTTP esperados

- `GET /health`
- `GET /stations/active`
- `POST /stations/connect`
- `POST /score-events`
- `POST /matches/finalize`
- `GET /stations/{stationId}/active-match-state` (**nuevo, JSON, requerido para app móvil**)

### Endpoints de administración de contienda (panel local)

> Estos endpoints son para operación local (admin), no para flujo normal de scoring móvil.
> Si el backend usa ruta admin personalizada (`TKD_ADMIN_BASE_PATH`), reemplazar prefijo `/admin` por la ruta configurada.

- `POST /admin/stations/{station_id}/matches/save-competitors`
  - Guarda borrador de nombres (`competitor_left_name`, `competitor_right_name`) para la próxima contienda.
- `POST /admin/stations/{station_id}/matches/draw-preview`
  - Genera preview de sorteo con:
    - `category_id`
    - `selected_poomsaes[]`
    - `total_rounds`
    - `competitor_left_name`
    - `competitor_right_name`
- `POST /admin/stations/{station_id}/matches/start`
  - Inicia contienda usando configuración enviada:
    - `competitor_left_name`
    - `competitor_right_name`
    - `category_id`
    - `selected_poomsaes[]`
    - `drawn_poomsaes[]` (opcional)
    - `total_rounds`
- `POST /admin/stations/{station_id}/active-match/start-round`
- `POST /admin/stations/{station_id}/active-match/stop-round`
- `POST /admin/stations/{station_id}/active-match/pause-timer`
- `POST /admin/stations/{station_id}/active-match/reset-round`
- `POST /admin/stations/{station_id}/active-match/finalize`

Reglas operativas:
- `total_rounds` define cuántos rounds tendrá esa contienda.
- Nombres de competidores se fijan al iniciar la contienda activa y no deben mutarse durante la misma.
- El admin puede guardar/borrador de la siguiente contienda sin alterar la activa.

### Endpoints de administración de historial (panel local)

- `POST /admin/history/{match_id}/delete`
  - Borra una contienda específica del historial.
- `POST /admin/history/delete-all`
  - Borra en bloque todas las contiendas del historial que no estén protegidas.

Reglas de borrado de historial:
- Una contienda está protegida y no debe borrarse si:
  - su estado es `in_progress` o `finalization_pending`, y
  - su sesión asociada sigue activa en backend.
- Si una contienda quedó pendiente pero ya no tiene sesión activa asociada, sí puede borrarse.
- En borrado masivo, backend elimina las no protegidas y omite las protegidas.

### `POST /stations/connect`

Request:

```json
{
  "stationId": "mesa-01",
  "judgeName": "Juez 2",
  "credential": "1234",
  "deviceId": "device-abc"
}
```

Response:

```json
{
  "connected": true,
  "sessionId": "sess-xyz",
  "accessToken": "long-lived-operation-token",
  "expiresAt": "2026-06-01T00:00:00.000Z",
  "station": {
    "id": "mesa-01",
    "name": "Mesa 1"
  }
}
```

Nota:
- Si la mesa no existe, backend puede responder `404` con detalle, por ejemplo: `{"detail":"Station not found"}`.

### `POST /score-events`

Headers:
- `Authorization: Bearer <accessToken>`
- `Content-Type: application/json`
- `Idempotency-Key: <idempotencyKey>`

Body incluye:
- `eventId`, `idempotencyKey`
- `sessionId`, `stationId`, `deviceId`, `judgeName`
- `matchId`, `roundNumber`, `athleteSide`
- `scoreTarget`, `scoreDelta`, `scoreBefore`, `scoreAfter`
- `occurredAt`, `sequence`

Urgente para frontend:
- `matchId` es **obligatorio** y debe ser el identificador canónico emitido por backend.
- Backend **no** hace fallback por `sessionId`/`stationId`/`judgeName` cuando `matchId` no corresponde.
- Si `matchId` falta, viene vacío o no existe en backend, responde `422`.

ACK:

```json
{
  "acknowledged": true,
  "eventId": "uuid",
  "serverReceivedAt": "2026-03-18T14:30:00.250Z"
}
```

### `POST /matches/finalize`

Headers:
- `Authorization: Bearer <accessToken>`
- `Content-Type: application/json`

Body incluye:
- `sessionId`, `stationId`, `matchId`, `judgeName`
- `competitorLeftName`, `competitorRightName`
- `totalRounds`, `finalRound`
- `finalScoreRed`, `finalScoreBlue`
- `totalEvents`, `finalSequence`
- `startedAt`, `finishedAt`
- `checksum`
- `roundsSummary[]`

Urgente para frontend:
- `matchId` es **obligatorio** y debe ser el identificador canónico emitido por backend.
- Backend **no** hace fallback por `sessionId`/`stationId`/`judgeName` para finalizar.
- Si `matchId` falta, viene vacío o no existe en backend, responde `422`.

### `GET /stations/{stationId}/active-match-state` (nuevo)

Objetivo:
- Entregar a la app del juez el estado de contienda activa en **JSON** (sin parseo HTML).
- Debe ser la fuente para botón `Sincronizar` y carga inicial de `Contienda`.

Headers:
- `Authorization: Bearer <accessToken>` (si aplica seguridad por sesión)
- `Accept: application/json`

Path params:
- `stationId`: mesa/área operativa del juez

Response 200:

```json
{
  "hasActiveMatch": true,
  "matchId": "match-2026-031",
  "competitorRedName": "Competidor C",
  "competitorBlueName": "Competidor D",
  "updatedAt": "2026-03-22T14:22:00.000Z"
}
```

Response 200 (sin contienda activa):

```json
{
  "hasActiveMatch": false,
  "matchId": null,
  "competitorRedName": null,
  "competitorBlueName": null,
  "updatedAt": "2026-03-22T14:22:00.000Z"
}
```

Reglas:
- `hasActiveMatch=true` exige `matchId` no vacío.
- Nombres deben venir por color (`competitorRedName`, `competitorBlueName`), nunca por left/right.
- Si nombres no existen aún, backend puede devolver `null`; frontend aplicará fallback local (`Rojo`/`Azul`).
- Este endpoint reemplaza para móvil el scraping de `/scoreboard/{stationId}/live`.

Errores recomendados:
- `401/403` sesión inválida o revocada.
- `404` estación no existe.
- `422` payload interno inválido para estación solicitada.

## 4) WebSocket esperado

URL:

`ws://<host>/ws?sessionId=<...>&stationId=<...>&token=<accessToken>`

Tipos soportados:
- `reset_match`
- `reset_round`
- `new_competitors`
- `active_match_state`
- `judge_settings_updated`
- `round_changed`
- `match_updated`
- `station_disconnected`
- `session_revoked`
- `judge_kicked` (recomendado para expulsión explícita)
- `server_notice`
- `ping`

### Evento de competidores (recomendado)

El backend debe enviar nombres por color fijo, no por izquierda/derecha.

```json
{
  "type": "new_competitors",
  "payload": {
    "matchId": "uuid",
    "competitorRedName": "Competidor C",
    "competitorBlueName": "Competidor D"
  }
}
```

Regla:
- `RED/BLUE` los define backend.
- `LEFT/RIGHT` lo define la app según configuración local del juez.

### Evento de estado de contienda activa (nuevo)

Se usa para mostrar en pantalla de `Contienda` si hay contienda activa del área.

```json
{
  "type": "active_match_state",
  "payload": {
    "hasActiveMatch": true,
    "matchId": "match-2026-031",
    "competitorRedName": "Competidor C",
    "competitorBlueName": "Competidor D",
    "issuedAt": "2026-03-20T14:22:00.000Z"
  }
}
```

Reglas:
- si `hasActiveMatch=false`, la app limpia indicador activo de contienda;
- nombres por color (`competitorRedName`, `competitorBlueName`);
- la app decide qué color va a izquierda/derecha según preferencia local del juez.

### Evento de actualización de configuración del juez (nuevo)

Se usa para empujar configuración operativa desde backend a la app del juez.

```json
{
  "type": "judge_settings_updated",
  "payload": {
    "defaultRounds": 2,
    "defaultStartingScore": 4,
    "presentationCategoryStartScore": 2,
    "actionValue1": 0.1,
    "actionValue2": 0.3,
    "issuedAt": "2026-03-20T14:22:10.000Z"
  }
}
```

Campos esperados:
- `defaultRounds` (`1..10`)
- `defaultStartingScore` (`0..20`)
- `presentationCategoryStartScore` (`0..2`)
- `actionValue1` (`0.1..1`)
- `actionValue2` (`0.1..2`)

### Evento recomendado para expulsar juez del área

```json
{
  "type": "judge_kicked",
  "payload": {
    "sessionId": "sess-xyz",
    "stationId": "mesa-01",
    "reason": "operator_replaced",
    "issuedAt": "2026-03-20T01:00:00.000Z"
  }
}
```

Comportamiento esperado en app:
- cerrar socket;
- invalidar sesión local de área;
- obligar reconexión (QR + PIN).

Compatibilidad:
- si backend no implementa `judge_kicked`, puede usar `session_revoked` o `station_disconnected` con mismo efecto operativo.

### Mensajes WS salientes (app -> backend)

Además de recibir comandos, la app envía señales operativas del juez por el mismo canal WS cuando hay sesión remota:

#### `judge_round_completed`

Se envía al terminar de calificar una ronda (cuando el juez pasa de presentación al siguiente round).

```json
{
  "type": "judge_round_completed",
  "payload": {
    "matchId": "match-2026-031",
    "roundNumber": 1,
    "sessionId": "sess-xyz",
    "stationId": "mesa-01",
    "judgeName": "Juez 2",
    "deviceId": "device-abc",
    "finishedAt": "2026-03-20T15:00:00.000Z"
  }
}
```

#### `judge_match_completed`

Se envía cuando el juez finaliza la contienda desde la app.

```json
{
  "type": "judge_match_completed",
  "payload": {
    "matchId": "match-2026-031",
    "finalRound": 2,
    "checksum": "sha256-hex",
    "sessionId": "sess-xyz",
    "stationId": "mesa-01",
    "judgeName": "Juez 2",
    "deviceId": "device-abc",
    "finishedAt": "2026-03-20T15:05:00.000Z"
  }
}
```

Regla:
- Estas señales no reemplazan `POST /matches/finalize`; son complementarias para estado en tiempo real del backend.

## 5) Flujo de conexión por mesa (resumen)

1. Escanear QR de la mesa (`stationId` incluido).
2. Ingresar PIN/clave.
3. `POST /stations/connect` con ese `stationId`.
4. Guardar `sessionId` + `accessToken`.
5. Abrir WS con `sessionId`, `stationId`, `token`.
