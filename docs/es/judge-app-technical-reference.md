# Documentación Ultradetallada - TKD Poomsae Scorer App

Fecha de corte: 2026-03-20
Proyecto: `tkd-poomsae-scorer`
Ruta local: `judge-app/`

---

## 1. Propósito real de esta app

Aplicación móvil para juez de poomsae con estas prioridades:

- funcionar aunque el backend no esté disponible;
- guardar cada acción de puntuación localmente primero;
- sincronizar después sin bloquear al juez;
- usar WebSocket para complementar operación en vivo (no reemplaza el offline-first);
- UI optimizada para operación rápida con botones grandes y mínimo texto.

La app no implementa backend. Solo consume contrato HTTP/WS esperado.

---

## 2. Estado funcional actual (lo que ya está implementado)

### 2.1 Flujo de entrada

1. `app/index.tsx` decide ruta de arranque:
   - si falta nombre de juez -> `judge-setup`;
   - si hay match activo -> `technical-scoring`;
   - de lo contrario -> `match-setup`.

2. No existe pantalla “Inicio” como hub principal (se removió).

### 2.2 Setup inicial de juez

- Pantalla `judge-setup` pide nombre del juez.
- Persistencia local en `app_settings.judge_name`.
- Placeholder actual: `Ej. Juez 1`.

### 2.3 Conexión backend

Pantalla `connection`:

- escaneo QR por cámara (principal);
- pegar JSON de QR (fallback);
- ingreso de PIN/clave;
- conexión por mesa (`stationId`) y juez;
- badge de estado `Conectado` / `No conectado`;
- botón rojo `Desconectar` solo si hay sesión remota activa;
- modal de clave de mesa tras aceptar QR.

No hay container de “Servidor” manual en esta pantalla (fue removido del UI actual).

### 2.4 Pantalla Contienda

Pantalla `match-setup`:

- nombres por color (Rojo/Azul);
- intercambio de lados (persistido con `preferredRedSide`);
- badge de conexión;
- badge de contienda activa backend cuando hay WS conectado;
- autorefresco de datos de contienda/config cuando llegan eventos WS;
- botón `Iniciar` para crear partido local y abrir `technical-scoring`.

### 2.5 Puntuación técnica

Pantalla `technical-scoring`:

- dos paneles (izquierda/derecha según configuración local);
- cada panel muestra nombre y score técnico actual;
- botones de deducción hacia afuera y corrección hacia adentro (por lado);
- botones disponibles: `-0.1`, `-0.3`, `+0.1`, `+0.3` (valores configurables);
- botón `Reset` (gris);
- botón siguiente como flecha verde a presentación;
- botón `X` para cerrar partido con confirmación;
- badge de conexión con icono.

### 2.6 Puntuación de presentación

Pantalla `presentation`:

- tres categorías por competidor:
  - Velocidad y potencia
  - Ritmo y tempo
  - Expresión de energía
- cada categoría usa barra interactiva:
  - permite click/tap sobre la barra;
  - permite arrastre;
  - también botones `-` y `+`;
- límites por categoría: `0..2`;
- total presentación por lado: suma de 3 categorías (`0..6`);
- controles inferiores:
  - flecha atrás a técnica,
  - reset de presentación de ronda,
  - siguiente/finalizar.

### 2.7 Finalización

- en última ronda, en `presentation`, botón `Finalizar`.
- flujo:
  - genera payload consolidado;
  - calcula checksum SHA-256 determinístico;
  - si no hay backend/sesión remota: cierra localmente y muestra resumen;
  - si hay backend: guarda `finalization_event` en cola y queda pendiente de ACK.

### 2.8 Resumen

Pantalla `summary`:

- protagonismo por ronda (`Round 1`, `Round 2`, ...);
- para cada ronda:
  - sección ROJO (Técnica, Presentación, Total)
  - sección AZUL (Técnica, Presentación, Total)
- estado de match;
- metadatos de mesa/servidor;
- si hay conexión remota activa: muestra estado de espera de nuevo partido;
- acciones: `Reiniciar` o espera, `Enviar ahora`, `Historial`, `Volver`.

### 2.9 Históricos

Pantalla `history`:

- secciones por estado:
  - Activo
  - Pendiente
  - Finalizados
- apertura de resumen por match seleccionado.

### 2.10 Ajustes

Pantalla `settings`:

- nombre juez;
- descuentos cortos/largos;
- mesa por defecto;
- rondas por defecto;
- inicio técnica;
- inicio por barra presentación;
- retención de matches;
- botón `Guardar` con alerta y retorno automático a pantalla anterior.

Campos de servidor y reset activo fueron retirados de esta pantalla.

---

## 3. Requisitos de UX que quedaron aplicados

- idioma español en pantallas operativas;
- tipografía grande y botones amplios;
- enfoque portrait-first, con adaptación a landscape;
- separación visual fuerte por color (ROJO/AZUL);
- minimización de texto técnico para usuarios no técnicos;
- controles críticos con confirmación (reset/finalizar/cerrar/desconectar);
- iconografía aplicada en acciones de navegación y estados clave.

---

## 4. Stack actual (real del `package.json`)

### 4.1 Runtime

- `expo` `^55.0.8`
- `react-native` `0.83.2`
- `react` `19.2.4`
- `expo-router` `~55.0.7`
- `expo-sqlite` `~55.0.11`
- `expo-secure-store` `~55.0.9`
- `expo-camera` `~55.0.10`
- `@react-native-community/netinfo` `11.5.2`
- `zustand` `^5.0.8`

### 4.2 Testing

- Unit: `vitest` `^4.0.3`
- E2E: `detox` `^20.47.0`

### 4.3 Nota sobre Expo Go

Se usa `EXPO_UNSTABLE_HEADLESS=1` en scripts para evitar problemas de React Native DevTools en Linux (sandbox chrome-sandbox).

---

## 5. Arquitectura y separación de responsabilidades

## 5.1 Estructura

- `app/` -> pantallas Expo Router
- `src/domain/` -> reglas puras
- `src/application/` -> casos de uso/orquestación
- `src/infrastructure/` -> SQLite, red, seguridad
- `src/components/` -> UI reutilizable
- `src/store/` -> estado UI liviano (proyección)

## 5.2 Domain

- `scoreCalculator.ts`: cálculo por eventos y targets.
- `roundRules.ts`: validación transición de rondas.
- `retryPolicy.ts`: elegibilidad y backoff.
- `checksum.ts`: serialización canónica + SHA-256.
- `connectionValidation.ts`: validación QR/conexión.
- `settingsValidation.ts`: validación zod de ajustes.
- `realtimeHandler.ts`: mapeo evento WS -> acción aplicable.

## 5.3 Application

- `AppFacade`: API de alto nivel para pantallas.
- `SessionService`: QR, conexión estación, sesión local/remota, restore.
- `MatchService`: scoring, reseteos, rounds, cierre local.
- `FinalizationService`: consolidación y finalización robusta.
- `SyncEngine`: envío HTTP con cola/retry/idempotencia.
- `RealtimeService`: consumo WS + aplicación idempotente + persistencia.
- `RetentionService`: limpieza segura según retención.
- `RecoveryService`: bootstrap + migraciones.

## 5.4 Infrastructure

- Repos SQLite por entidad (`Settings`, `Session`, `Match`, `ScoreEvent`, `Finalization`, `History`, etc.).
- `apiClient.ts` para HTTP backend.
- `realtimeClient.ts` para WS con reconexión.
- `connectivityMonitor.ts` para disparar sync en online/resume.
- `tokenVault.ts` para token seguro en `expo-secure-store`.

---

## 6. Modelo de datos local (SQLite)

Fuente de verdad persistente: `expo-sqlite`.

Tablas principales (`src/infrastructure/db/migrations.ts`):

- `app_settings`
- `backend_server`
- `station`
- `operator_session`
- `match`
- `round`
- `score_event`
- `finalization_event`
- `inbound_server_event_log`

## 6.1 Campos importantes agregados en `app_settings`

- `preferred_red_side`
- `server_has_active_match`
- `server_active_match_id`
- `server_competitor_red_name`
- `server_competitor_blue_name`
- `server_match_updated_at`

Estos campos permiten que `Contienda` muestre indicador backend y prellene nombres por color.

---

## 7. Reglas de puntuación implementadas

## 7.1 Técnica

- inicio configurable (`defaultStartingScore`, por defecto 4);
- eventos por delta firmado (`scoreDelta`): deducciones negativas, correcciones positivas;
- límites aplicados en app: `0..startingScore`;
- valores de acción configurables (`actionValue1`, `actionValue2`).

## 7.2 Presentación

- 3 categorías por lado;
- inicio por categoría configurable (`presentationCategoryStartScore`, por defecto 2);
- límites por categoría: `0..2`;
- total de presentación por lado: suma de categorías (`0..6`).

## 7.3 Total por ronda / final

- total por lado y ronda en resumen = técnica + presentación;
- puntaje perfecto esperado por ronda (con defaults): `4 + 6 = 10`;
- agregación revisada para no duplicar ni inflar resultados.

---

## 8. Flujo offline-first y sincronización

## 8.1 Principio operativo

Cada tap de scoring:

1. aplica feedback local inmediato (optimista);
2. se persiste en SQLite (`score_event`) con `sync_status='pending'`;
3. se dispara intento async de sync HTTP;
4. UI nunca se bloquea por red.

## 8.2 SyncEngine

- timer de 5s;
- retry con backoff+jitter (`retryPolicy`);
- retries adicionales al volver online y al volver foreground;
- idempotencia con `Idempotency-Key` (ID local del evento);
- no reenvía ACKed;
- también sincroniza `finalization_event`.

## 8.3 Estados de finalización de match

- `finished_locally`
- `finished_locally_pending_finalize_ack`
- `finalized_acknowledged`
- `finalize_failed_retrying`

---

## 9. Tiempo real (WebSocket) actual

## 9.1 Tipos soportados en app

- `reset_match`
- `reset_round`
- `new_competitors`
- `active_match_state` (nuevo)
- `judge_settings_updated` (nuevo)
- `round_changed`
- `match_updated` (reservado)
- `station_disconnected`
- `session_revoked`
- `server_notice`
- `ping`

## 9.2 Política de nombres por color

Se migró para que backend mande por color fijo:

- `competitorRedName`
- `competitorBlueName`

La app convierte a izquierda/derecha según configuración local del juez (`preferredRedSide` y colores del match).

Hay fallback de compatibilidad temporal para payload antiguo `competitorLeftName`/`competitorRightName`.

## 9.3 Evento nuevo: contienda activa

`active_match_state` permite que en `Contienda` salga badge de “Contienda activa” y autocompletar nombres.

## 9.4 Evento nuevo: actualización de configuración

`judge_settings_updated` actualiza en caliente settings del juez:

- `defaultRounds`
- `defaultStartingScore`
- `presentationCategoryStartScore`
- `actionValue1`
- `actionValue2`

Se aplican clamps de seguridad en la app.

---

## 10. Contrato backend esperado

Archivo oficial del contrato actualizado:

- `docs/api-contract.md`

Incluye:

- QR con `stationId` obligatorio;
- conexión por `POST /stations/connect`;
- payload de score-event con idempotencia;
- payload de finalize con checksum;
- WS con `new_competitors`, `active_match_state`, `judge_settings_updated`, etc.

---

## 11. Persistencia de sesión y seguridad

## 11.1 Sesión

Se persiste:

- backend activo,
- stationId/stationName,
- judgeName,
- sessionId,
- token metadata,
- estado conexión.

Restore al inicio:

- si token válido: recupera sesión;
- si backend offline: estado `offline` permitido;
- si inválido/revocado: marca sesión y fuerza reconexión.

## 11.2 Token

- access token en `expo-secure-store` (`tokenVault`), no en SQLite plano.

## 11.3 Device ID

- se genera/persiste identidad de dispositivo para requests de estación.

---

## 12. Decisiones UX/ergonomía aplicadas

- controles de score con `onPressIn` para respuesta inmediata;
- guard anti-double-tap (`lockRef` ~180ms) para comandos críticos;
- cola de taps en scoring (`scoreQueueRef`) para no perder acciones seguidas;
- barra de presentación manipulable por arrastre y click;
- acciones peligrosas con confirmación;
- botón `X` para cierre rápido de partido con confirmación.

Nota sobre multitap simultáneo:

- se mejoró latencia y serialización de taps;
- no hay garantía de multi-touch paralelo perfecto en todos los dispositivos por limitaciones de dispatch de eventos táctiles y diseño de Pressable.

---

## 13. Scripts y ejecución

## 13.1 Scripts npm

- `npm run start` -> Expo Go LAN (headless)
- `npm run start:dev-client`
- `npm run start:go`
- `npm run start:go:tunnel`
- `npm run android`
- `npm run ios`
- `npm run typecheck`
- `npm run test`
- `npm run test:e2e` / `test:e2e:build`
- `npm run build:apk` (EAS)

## 13.2 Probar sin Expo Go (recomendado para estabilidad)

### Opción A: APK local en PC

Requisitos:

- JDK 17
- Android SDK + `adb`
- `JAVA_HOME`, `ANDROID_HOME` configurados

Comandos:

```bash
cd android
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

### Opción B: EAS cloud

```bash
npx eas-cli login
npx eas-cli build -p android --profile preview
```

`eas.json` ya tiene `preview.android.buildType = apk`.

---

## 14. Testing actual

## 14.1 Unit tests

Se ejecutan con `vitest`:

```bash
npm run test
```

Cobertura en lógica de:

- score calculator;
- rules de ronda;
- retry policy;
- checksum/finalization;
- validaciones conexión/settings;
- retención y recuperación;
- sync engine;
- realtime handler/service.

## 14.2 E2E (Detox)

Hay base de E2E (`tests/e2e/*`), pero **algunos specs están desalineados con UI actual** por cambios de flujo/IDs (ej. referencias viejas a controles removidos).

Esto está documentado como deuda técnica de pruebas E2E a ajustar.

---

## 15. Errores y fixes históricos importantes

1. `expo-router/babel` deprecado:
- se dejó `babel-preset-expo` sin plugin deprecado.

2. Error Linux DevTools sandbox (`chrome-sandbox`):
- scripts con `EXPO_UNSTABLE_HEADLESS=1` para evitar bloqueo.

3. Error `ExpoKeepAwake.activate rejected`:
- shim `src/shims/expo-keep-awake.ts` + alias en `metro.config.js`.

4. `SafeAreaView` deprecado:
- `ScreenContainer` usa `react-native-safe-area-context`.

5. Cálculo total incorrecto (inflado):
- se ajustó agregación en `HistoryRepositorySqlite` usando `aggregateMatchTotals`.

6. `getSnapshot should be cached` (zustand selector objeto):
- se migró a selects por campo para evitar loop infinito.

7. Conexión 404 por estación:
- API client muestra detalle backend en mensaje (`payload.detail`).

---

## 16. Checklist de regeneración total (mañana desde cero)

1. Clonar repo.
2. `npm install`.
3. Verificar Expo/Node/npm:
   - Node recomendado LTS estable para ecosistema Expo;
   - evitar usar comandos `npx eas` sin `eas-cli`.
4. Confirmar `app.json`, `babel.config.js`, `metro.config.js`.
5. Ejecutar:
   - `npm run typecheck`
   - `npm run test`
6. Levantar app:
   - preferible APK local o dev-client.
7. Verificar flujos manuales críticos:
   - setup juez
   - conexión QR + PIN
   - desconexión
   - contienda con intercambio de lados
   - scoring técnica/presentación
   - reset/finalizar
   - resumen/históricos
   - restauración tras reinicio
8. Verificar WS con backend:
   - `new_competitors`
   - `active_match_state`
   - `judge_settings_updated`
   - `session_revoked`/`station_disconnected`.
9. Si se cambia contrato backend, actualizar:
   - `docs/api-contract.md`
   - `src/domain/models/contracts.ts`
   - `src/domain/services/realtimeHandler.ts`
   - `src/application/services/realtimeService.ts`
   - tests unitarios asociados.

---

## 17. Payloads de ejemplo listos para backend

## 17.1 `new_competitors`

```json
{
  "type": "new_competitors",
  "payload": {
    "matchId": "match-001",
    "competitorRedName": "Competidor C",
    "competitorBlueName": "Competidor D"
  }
}
```

## 17.2 `active_match_state`

```json
{
  "type": "active_match_state",
  "payload": {
    "hasActiveMatch": true,
    "matchId": "match-001",
    "competitorRedName": "Competidor C",
    "competitorBlueName": "Competidor D",
    "issuedAt": "2026-03-20T14:22:00.000Z"
  }
}
```

## 17.3 `judge_settings_updated`

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

---

## 18. Notas de límites actuales / deuda técnica explícita

1. `app.json` tiene `orientation: "default"`.
   - la UX está diseñada portrait-first, pero no se fuerza lock de orientación.

2. E2E Detox necesita actualización de selectores/flujo para reflejar UI vigente.

3. Persistencia de contienda activa backend está en `app_settings`; funciona bien para el caso actual, pero puede evolucionar a entidad separada si crece complejidad de estados remotos.

4. `build:apk` en `package.json` usa `eas build` (requiere binario `eas` global o ajuste a `npx eas-cli`).

---

## 19. Archivos clave de referencia rápida

- UI:
  - `app/match-setup.tsx`
  - `app/connection.tsx`
  - `app/technical-scoring.tsx`
  - `app/presentation.tsx`
  - `app/summary.tsx`
  - `app/settings.tsx`

- Orquestación:
  - `src/application/appFacade.ts`
  - `src/application/services/matchService.ts`
  - `src/application/services/sessionService.ts`
  - `src/application/services/syncEngine.ts`
  - `src/application/services/realtimeService.ts`
  - `src/application/services/finalizationService.ts`

- Dominio:
  - `src/domain/services/scoreCalculator.ts`
  - `src/domain/services/realtimeHandler.ts`
  - `src/domain/services/retryPolicy.ts`
  - `src/domain/services/checksum.ts`
  - `src/domain/services/settingsValidation.ts`

- Persistencia y red:
  - `src/infrastructure/db/migrations.ts`
  - `src/infrastructure/repositories/*.ts`
  - `src/infrastructure/network/apiClient.ts`
  - `src/infrastructure/network/realtimeClient.ts`

- Contrato backend:
  - `docs/api-contract.md`

---

## 20. Cierre

Este documento refleja el estado funcional y técnico actual de la app con las últimas decisiones aplicadas durante el ciclo de cambios.

Si mañana quieres regenerar o reimplementar, este archivo + `docs/api-contract.md` te da el mapa completo de:

- qué existe,
- por qué existe,
- cómo se conecta,
- cómo se prueba,
- y qué puntos hay que ajustar primero.

