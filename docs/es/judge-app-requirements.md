# Requisitos detallados de la app de jueces

Fecha de corte: 2026-03-22  
Proyecto: `tkd-poomsae-scorer`  
Ruta base: `judge-app/`

## 1. Objetivo del documento

Este documento define, en detalle operativo y técnico, **todos los requisitos vigentes del proyecto** para que un tercero pueda recrearlo sin depender de conocimiento tácito.

Incluye:
- requisitos funcionales;
- requisitos de UX/UI;
- requisitos de arquitectura y datos;
- contrato esperado de integración backend;
- requisitos de persistencia offline y sincronización;
- requisitos de pruebas;
- requisitos de build/instalación;
- checklist de aceptación final.

Este documento describe **el estado real esperado** del proyecto en su implementación actual y las reglas que no deben romperse.

---

## 2. Alcance funcional

### 2.1 En alcance

1. App móvil para jueces de Taekwondo Poomsae.
2. Modo offline real (operable sin backend).
3. Conexión remota por QR + PIN de mesa/área.
4. Puntuación de técnica y presentación por rounds.
5. Persistencia local robusta con SQLite.
6. Cola de sincronización HTTP offline-first.
7. Canal WebSocket complementario para eventos en vivo.
8. Finalización de match con checksum.
9. Resumen, históricos, ajustes y recuperación tras reinicio.

### 2.2 Fuera de alcance

1. Implementación del backend dentro de la app (el backend es un componente separado del mismo repositorio, documentado en `backend-technical-reference.md`).
2. mDNS/Bonjour/descubrimiento automático de red.
3. Lógica de combate/kyorugi.
4. Múltiples tipos de competencia en UI.
5. Dependencia obligatoria de internet para puntuar.

---

## 3. Principios del producto

1. **Offline-first real**: puntuar nunca depende de backend.
2. **Local-first**: toda acción crítica se persiste primero localmente.
3. **Resiliencia operativa**: la app continúa aunque haya cortes de red.
4. **Simplicidad de uso**: interfaz de juez, mínima carga cognitiva.
5. **Separación de responsabilidades**: dominio, aplicación, infraestructura, UI.
6. **Extensibilidad controlada**: preparado para crecer sin romper base actual.

---

## 4. Stack y versiones objetivo

### 4.1 Base técnica

1. Expo SDK 55 (`expo ^55.0.8`).
2. React Native `0.83.2`.
3. React `19.2.4`.
4. TypeScript `~5.9.2`.
5. Expo Router `~55.0.7`.

### 4.2 Persistencia y red

1. `expo-sqlite` para datos operativos.
2. `expo-secure-store` para token.
3. `@react-native-community/netinfo` para conectividad.
4. WebSocket nativo (cliente en infraestructura).

### 4.3 Estado y validación

1. Zustand para proyección de estado UI.
2. Zod para validación de configuración y conexión.

### 4.4 Testing

1. Unit/integ: Vitest.
2. E2E móvil nativo: Detox.
3. Playwright no se usa como runner E2E nativo principal en este proyecto.

---

## 5. Arquitectura obligatoria

## 5.1 Capas

1. `app/`:
- Pantallas Expo Router.
- Solo composición UI, navegación y llamadas a `appFacade`.

2. `src/domain/`:
- Reglas puras (score, rounds, checksum, retry, validaciones).
- Sin dependencias de UI/SQLite/fetch.

3. `src/application/`:
- Casos de uso y orquestación.
- Coordina repositorios, servicios y store.

4. `src/infrastructure/`:
- Repositorios SQLite.
- Clientes HTTP/WS.
- Seguridad local (token/device id).

5. `src/components/`:
- UI reutilizable y consistente.

6. `src/store/`:
- Estado UI liviano y derivado.
- Nunca fuente de verdad para acciones críticas.

## 5.2 Reglas de diseño

1. No mezclar lógica de negocio compleja dentro de pantallas.
2. Cada módulo debe tener responsabilidad única razonable.
3. Contratos por interfaces en `application/ports`.
4. Dominios puros testeables.
5. Persistencia desacoplada vía repositorios.

---

## 6. Estructura de carpetas esperada

```txt
/app
  _layout.tsx
  index.tsx
  judge-setup.tsx
  connection.tsx
  match-setup.tsx
  technical-scoring.tsx
  presentation.tsx
  summary.tsx
  history.tsx
  settings.tsx

/src
  /application
    appFacade.ts
    container.ts
    /ports
      repositories.ts
    /services
      sessionService.ts
      matchService.ts
      finalizationService.ts
      syncEngine.ts
      realtimeService.ts
      recoveryService.ts
      retentionService.ts
      historyQueryService.ts

  /domain
    /models
      entities.ts
      contracts.ts
    /services
      scoreCalculator.ts
      roundRules.ts
      retryPolicy.ts
      checksum.ts
      retentionPolicy.ts
      connectionValidation.ts
      settingsValidation.ts
      realtimeHandler.ts
      matchAggregation.ts

  /infrastructure
    /db
      client.ts
      migrations.ts
    /repositories
      SettingsRepositorySqlite.ts
      SessionRepositorySqlite.ts
      MatchRepositorySqlite.ts
      ScoreEventRepositorySqlite.ts
      FinalizationRepositorySqlite.ts
      HistoryRepositorySqlite.ts
      ConnectionRepositorySqlite.ts
      InboundServerEventRepositorySqlite.ts
    /network
      apiClient.ts
      realtimeClient.ts
      connectivityMonitor.ts
    /security
      tokenVault.ts
      deviceIdentity.ts

  /components
    ScreenContainer.tsx
    PrimaryButton.tsx
    StatusBadge.tsx
    ScoreSidePanel.tsx
    PresentationSidePanel.tsx

  /store
    appStore.ts

/tests
  /unit
  /e2e
```

---

## 7. Requisitos funcionales detallados (con IDs)

### 7.1 Arranque y setup de juez

`FR-001` La app debe iniciar con pantalla de carga (`index`) y enrutar automáticamente.  
`FR-002` Si no existe `judgeName`, debe abrir `judge-setup`.  
`FR-003` Si hay match activo recuperado, debe abrir `technical-scoring`.  
`FR-004` Si no hay match activo y ya hay juez, debe abrir `match-setup`.  
`FR-005` El nombre del juez debe persistir localmente y reutilizarse entre reinicios.  
`FR-006` Placeholder recomendado visible en setup: ejemplo `Juez 1`.

Criterios de aceptación:
1. Instalar app limpia -> pide nombre de juez.
2. Guardar nombre -> reiniciar app -> no lo vuelve a pedir.

### 7.2 Conexión con backend por QR y PIN

`FR-010` Debe existir pantalla `connection`.  
`FR-011` Debe soportar escaneo QR con cámara (`expo-camera`).  
`FR-012` Debe soportar pegar JSON de QR manualmente.  
`FR-013` QR válido debe incluir `baseUrl`, `stationId`, `protocolVersion`, `expiresAt`.  
`FR-014` Debe rechazar QR expirado.  
`FR-015` Debe rechazar `localhost`/`127.0.0.1` en QR cuando se usa celular.  
`FR-016` Tras QR válido, debe solicitar PIN/clave de mesa en modal superpuesto.  
`FR-017` Debe conectar por `POST /stations/connect` con `stationId`, `judgeName`, `credential`, `deviceId`.  
`FR-018` Si backend responde conflicto de juez conectado (`409` o equivalente), debe reintentar con `replaceExistingJudgeSession=true`.  
`FR-019` Al conectar exitosamente debe persistir sesión y token.  
`FR-020` Debe existir botón rojo `Desconectar` visible solo si sesión remota está activa.

Criterios de aceptación:
1. Escanear QR válido + PIN correcto -> conexión exitosa.
2. Salir y entrar app -> sesión remota sigue restaurada (si no revocada).
3. Pulsar `Desconectar` -> sesión local queda inactiva.

### 7.3 Modo sin servidor

`FR-030` La app debe operar sin servidor remoto (`local-offline`).  
`FR-031` En modo local se debe crear sesión local válida (sin token remoto).  
`FR-032` En modo local debe permitir crear match, puntuar y finalizar localmente.  
`FR-033` En modo local no debe exigir backend para ninguna acción de scoring.

Criterios de aceptación:
1. Sin red ni backend activo -> se puede puntuar normalmente.
2. Eventos se guardan en SQLite aunque no haya envío remoto.

### 7.4 Pantalla Contienda (configuración operativa del match)

`FR-040` Pantalla `match-setup` debe permitir configurar nombres de competidores.  
`FR-041` Debe soportar intercambio de lados (`Intercambiar lados`).  
`FR-042` Preferencia de lado rojo (`preferredRedSide`) debe persistirse.  
`FR-043` Debe mostrar badge de conexión (`Conectado`, `Reconectando`, `No conectado`).  
`FR-044` Si hay sesión remota, debe permitir sincronizar estado de contienda (`Sincronizar`).  
`FR-045` Badge de `Contienda activa` solo debe mostrarse cuando snapshot confirme `hasActiveMatch=true`.

Criterios de aceptación:
1. Cambiar lado rojo y cerrar app -> al abrir se mantiene.
2. Sin contienda activa backend -> debe mostrar `Sin contienda activa`.

### 7.5 Modelo de rounds

`FR-050` Rounds por defecto = `2`.  
`FR-051` Rounds configurables desde Ajustes (no en cada inicio de ronda).  
`FR-052` Debe existir ronda activa actual (`currentRound`).  
`FR-053` Debe validar transición de ronda con `canMoveToNextRound`.  
`FR-054` No debe avanzar más allá de `totalRounds`.

Criterios de aceptación:
1. En ronda final, siguiente ronda no permitida.
2. `nextRound` actualiza `currentRound` persistido.

### 7.6 Puntuación de técnica

`FR-060` Pantalla `technical-scoring` debe mostrar dos paneles (rojo y azul según lados configurados).  
`FR-061` Técnica inicia en valor configurable (`defaultStartingScore`, default 4).  
`FR-062` Botones por competidor: `-v1`, `-v2`, `+v1`, `+v2` (defaults 0.1 y 0.3).  
`FR-063` Deducción/corrección deben persistirse como eventos con `scoreDelta` firmado.  
`FR-064` Límites técnica: mínimo 0, máximo `startingScore`.  
`FR-065` Botones visibles y grandes en vertical y horizontal con adaptación por pantalla.  
`FR-066` Debe haber botón `Reset` de técnica por ronda con confirmación.  
`FR-067` Debe haber botón `Siguiente` como flecha hacia presentación.  
`FR-068` En técnica no debe aparecer botón `Finalizar`.  
`FR-069` Debe existir botón `X` para cerrar partido con confirmación.

Criterios de aceptación:
1. Tap rápido repetido no debe bloquear UI.
2. Técnica nunca pasa de los límites [0..max].

### 7.7 Puntuación de presentación

`FR-080` Presentación debe estar en pantalla separada (`presentation`).  
`FR-081` Debe mostrar 3 categorías por competidor:
- Velocidad y potencia;
- Ritmo y tempo;
- Expresión de energía.

`FR-082` Cada categoría debe admitir interacción por arrastre y por toque en barra.  
`FR-083` Debe admitir botones `-` y `+` por categoría.  
`FR-084` Límite por categoría: `0..2` (o `PRESENTATION_CATEGORY_MAX_SCORE`).  
`FR-085` Total presentación por competidor = suma de 3 categorías (`0..6`).  
`FR-086` Debe existir botón atrás (flecha) hacia técnica.  
`FR-087` Debe existir botón reset de presentación por ronda con confirmación.  
`FR-088` Si no es última ronda: botón siguiente ronda (flecha).  
`FR-089` Si es última ronda: botón `Finalizar`.

Criterios de aceptación:
1. Arrastrar barra cambia puntaje en pasos válidos.
2. Puntaje por categoría no sale de [0..2].

### 7.8 Reglas de score y cálculo

`FR-100` El evento de score debe usar modelo neutral por delta (`scoreDelta`).  
`FR-101` Negativos = deducciones, positivos = correcciones.  
`FR-102` Cálculo técnica: `startingScore + sum(scoreDelta técnica por lado)` ordenado por `sequence`.  
`FR-103` Cálculo presentación por categoría: `categoryStart + sum(scoreDelta target categoría)` por lado.  
`FR-104` Cálculo presentación total: suma de categorías del lado.  
`FR-105` Clasificación de negativos/positivos para resumen solo aplica a técnica.

Criterios de aceptación:
1. Mismo conjunto de eventos, cualquier recarga, mismo resultado.
2. Orden de `sequence` define resultado determinista.

### 7.9 Persistencia de eventos y no bloqueo

`FR-110` Cada tap de score debe crear `score_event` en SQLite antes de sync remoto.  
`FR-111` UI no debe bloquear por envío remoto.  
`FR-112` Debe existir cola de sync persistida tras reinicio.

Criterios de aceptación:
1. Sin red, se siguen creando eventos.
2. Con red restaurada, eventos pendientes se sincronizan.

### 7.10 Resets y auditoría

`FR-120` Reset de técnica/presentación/ronda/match debe afectar estado local persistido.  
`FR-121` Reset local debe registrar auditoría en `inbound_server_event_log` (eventos `local_reset_*`).  
`FR-122` Si sesión remota activa, reset manual debe emitir señal WS `judge_reset_requested`.

Criterios de aceptación:
1. Tras reset, la proyección de puntaje de la ronda se recalcula sin eventos borrados por target.
2. Queda evidencia en log local.

### 7.11 Finalización de match

`FR-130` Debe existir acción de finalizar con confirmación (en presentación última ronda).  
`FR-131` Debe construir payload consolidado desde SQLite local.  
`FR-132` Debe incluir `matchId` obligatorio y canónico.  
`FR-133` Debe incluir `checksum` SHA-256 determinístico.  
`FR-134` Debe persistir `finalization_event` antes de enviar cuando hay backend.  
`FR-135` Si no hay backend/sesión remota, debe cerrar localmente (`finished_locally`).  
`FR-136` Si hay backend, estado local debe pasar a `finished_locally_pending_finalize_ack`.  
`FR-137` Al ACK de backend debe pasar a `finalized_acknowledged`.  
`FR-138` Si falla envío, estado debe pasar a `finalize_failed_retrying` y reintentar.

Criterios de aceptación:
1. Nunca se pierde intento de finalización.
2. Finalización funciona offline y online.

### 7.12 Resumen

`FR-140` Pantalla `summary` debe priorizar información por ronda.  
`FR-141` Mostrar para cada round y cada color: técnica, presentación y total.  
`FR-142` Mostrar total global pequeño arriba por color (2 decimales).  
`FR-143` Debe mostrar estado de finalización local/remota.  
`FR-144` Debe mostrar metadatos de conexión (mesa/servidor).  
`FR-145` Si sesión remota conectada, puede mostrar estado “esperando nuevo partido”.  
`FR-146` Debe incluir acciones de navegación: reiniciar, historial, volver.

Criterios de aceptación:
1. Resumen visible completo y con scroll funcional en pantallas pequeñas.
2. Totales por round y global consistentes con eventos locales.

### 7.13 Históricos

`FR-150` Debe existir pantalla de históricos (`history`).  
`FR-151` Debe listar matches retenidos localmente por política de retención.  
`FR-152` Debe permitir abrir resumen de match histórico.

Criterios de aceptación:
1. Tras finalizar y crear otro partido, historial muestra registros retenidos.

### 7.14 Ajustes

`FR-160` Debe existir pantalla de ajustes con botón de regreso.  
`FR-161` Debe permitir editar:
- nombre de juez;
- descuentos corto/largo;
- mesa por defecto;
- rondas por partido;
- inicio técnica;
- inicio por categoría de presentación;
- retención de matches.

`FR-162` Guardar debe validar entradas vía Zod.  
`FR-163` Guardar debe mostrar alerta de éxito y regresar a pantalla anterior al confirmar `OK`.

Criterios de aceptación:
1. Valores inválidos deben disparar error de validación.
2. Tras guardar y reabrir, valores persisten.

### 7.15 Estado de juez listo y señales operativas

`FR-170` Al pasar de ronda debe emitir WS `judge_round_completed` si sesión remota.  
`FR-171` Al finalizar match debe emitir WS `judge_match_completed` si sesión remota.  
`FR-172` Estas señales no reemplazan el finalize HTTP.

---

## 8. Requisitos de conexión y sesión persistente

`NFR-010` Debe persistir backend activo, sesión de operador y token.  
`NFR-011` Al reiniciar app, debe restaurar sesión y validar silenciosamente cuando sea posible.  
`NFR-012` Si backend no responde, sesión puede mantenerse en modo `offline` (no reauth forzado inmediato).  
`NFR-013` Si backend revoca sesión, debe marcar `revoked` y desconectar WS.  
`NFR-014` Debe soportar desconexión explícita del área desde UI y por evento WS (`judge_kicked`, `session_revoked`, `station_disconnected`).

---

## 9. Requisitos de backend (contrato esperado)

Fuente oficial del proyecto: [api-contract.md](api-contract.md)

## 9.1 Reglas críticas

1. QR debe incluir `stationId` (mesa/área).
2. `matchId` es obligatorio y canónico en score-events y finalize.
3. WebSocket debe usar query params `sessionId`, `stationId`, `token`.

## 9.2 Endpoints mínimos

1. `GET /health`
2. `GET /stations/active`
3. `POST /stations/connect`
4. `POST /score-events`
5. `POST /matches/finalize`

## 9.3 Eventos WS entrantes soportados

1. `reset_match`
2. `reset_round`
3. `new_competitors` (preferido por color: `competitorRedName`, `competitorBlueName`)
4. `active_match_state`
5. `judge_settings_updated`
6. `round_changed`
7. `match_updated`
8. `station_disconnected`
9. `session_revoked`
10. `judge_kicked`
11. `server_notice`
12. `ping`

## 9.4 Eventos WS salientes desde app

1. `judge_round_completed`
2. `judge_match_completed`
3. `judge_reset_requested`
4. `ping` (eco/control)

---

## 10. Requisitos de persistencia (SQLite)

## 10.1 Fuente de verdad

`NFR-020` SQLite es la fuente de verdad para scoring, estado de match y cola de sync.

## 10.2 Esquema mínimo obligatorio

Tablas:
1. `app_settings`
2. `backend_server`
3. `station`
4. `operator_session`
5. `match`
6. `round`
7. `score_event`
8. `finalization_event`
9. `inbound_server_event_log`

## 10.3 Campos clave

1. `app_settings.preferred_red_side` para persistencia de lados.
2. `app_settings.server_has_active_match` y nombres por color para snapshot de contienda activa.
3. `score_event.idempotency_key` único.
4. `score_event.sequence` para orden determinista.
5. `finalization_event.payload_snapshot` para reintentos.

---

## 11. Requisitos de sincronización offline-first

`NFR-030` Primer intento de sync inmediatamente después de crear evento.  
`NFR-031` Reintentos con backoff + jitter (`retryPolicy`).  
`NFR-032` Reintento automático por timer (`5s`).  
`NFR-033` Reintento al volver online (`NetInfo`).  
`NFR-034` Reintento al volver a foreground (`AppState active`).  
`NFR-035` Reintento manual (`syncNow/resyncNow`).  
`NFR-036` Evitar duplicados por `idempotencyKey`.  
`NFR-037` No reenviar eventos ya ACK.  
`NFR-038` Cola de finalización debe reintentarse hasta ACK.

---

## 12. Requisitos de realtime (WebSocket)

`NFR-040` WebSocket no reemplaza HTTP offline-first.  
`NFR-041` Si WS cae, scoring debe seguir funcionando.  
`NFR-042` Reconexión automática con backoff exponencial + jitter.  
`NFR-043` Dedupe de eventos entrantes con `dedupe_key` persistido.  
`NFR-044` Eventos entrantes relevantes deben persistirse en log local.  
`NFR-045` Debe mapear payloads flexibles (camelCase/snake_case/fallbacks).

---

## 13. Requisitos UX/UI

## 13.1 Idioma y claridad

1. UI en español.
2. Reducir tecnicismos visibles al usuario final.
3. Etiquetas directas y comprensibles.

## 13.2 Ergonomía

1. Portrait-first obligatorio.
2. Landscape permitido sin romper operación.
3. Botones grandes, separados y con feedback inmediato.
4. Diferenciación visual fuerte por color de competidor.

## 13.3 Colores y lados

1. Lógica deportiva se maneja por color (`RED/BLUE`).
2. Presentación de lado izquierdo/derecho depende de `preferredRedSide` local.
3. Intercambio de lados debe persistir para próximas contiendas.

## 13.4 Indicadores

1. Badge conexión en pantallas operativas.
2. Badge contienda activa sólo con confirmación real de backend.
3. Iconografía útil (flechas, wifi/cloud-offline, cerrar, swap).

---

## 14. Requisitos de rendimiento y memoria

`NFR-050` No cargar históricos completos en memoria para todas las pantallas.  
`NFR-051` Proyección en memoria sólo de match activo y datos visibles.  
`NFR-052` Consultas de historial deben ser ligeras y lazy.  
`NFR-053` Evitar trabajos de fondo innecesarios fuera de sync/realtime.

---

## 15. Requisitos de retención, históricos y recuperación

`NFR-060` `retainedMatchesCount` mínimo 2, default 2.  
`NFR-061` Nunca borrar match activo.  
`NFR-062` Mantener los últimos N matches según fecha y estado.  
`NFR-063` Limpieza segura con `RetentionService`.  
`NFR-064` Recuperar match activo tras reinicio y abrir en pantalla correcta.

---

## 16. Requisitos de seguridad

`SEC-001` Access token no se guarda en texto plano SQLite; usar `expo-secure-store`.  
`SEC-002` `deviceId` persistido localmente para trazabilidad de estación.  
`SEC-003` Validación estricta de QR y credenciales antes de conectar.  
`SEC-004` Soporte de revocación remota por WS.

---

## 17. Requisitos de pruebas

## 17.1 Unitarias mínimas

1. cálculo de score y deltas (`scoreCalculator`).
2. agregación de match y tope de 10 (`matchAggregation`).
3. validación de transición de rounds (`roundRules`).
4. retry/backoff elegible (`retryPolicy`).
5. validación de QR/conexión (`connectionValidation`).
6. validación de settings (`settingsValidation`).
7. checksum y finalización (`checksumAndFinalization`).
8. idempotencia del motor de sync (`syncEngine`).
9. reset y auditoría (`matchServiceReset`).
10. mapeo robusto de eventos WS (`realtimeHandler`).
11. aplicación de WS y persistencia (`realtimeService`).
12. retención de matches (`retentionPolicy`).
13. recuperación tras reinicio (`recoveryService`).
14. restauración de sesión y reemplazo de juez (`sessionService`).
15. consulta lazy de historial (`historyQueryService`).

## 17.2 E2E mínimas (Detox)

1. flujo primer uso (setup juez + conexión/local).
2. flujo scoring completo:
- iniciar partido;
- puntuar técnica ambos lados;
- ir a presentación;
- cambiar categorías;
- volver;
- avanzar ronda;
- reset con confirmación;
- finalizar;
- abrir históricos.

## 17.3 Scripts requeridos

1. `npm run test`
2. `npm run test:e2e:build`
3. `npm run test:e2e`
4. `npm run typecheck`

---

## 18. Requisitos de build, ejecución e instalación

## 18.1 Desarrollo

1. `npm install`
2. `npm run start` (Expo Go LAN, con `EXPO_UNSTABLE_HEADLESS=1`).

## 18.2 Dev client

1. `npm run start:dev-client`
2. `npm run android` / `npm run ios`

## 18.3 APK local (Gradle)

1. Entrar a `android/`.
2. `./gradlew assembleRelease` o `assembleDebug`.
3. APK en `android/app/build/outputs/apk/release/app-release.apk`.

## 18.4 APK cloud (EAS)

1. `npx eas login`
2. `npm run build:apk`

## 18.5 Instalación por consola

1. Con dispositivo ADB detectado:
- `adb install -r /ruta/al/apk`

---

## 19. Requisitos nativos Android/iOS

## 19.1 Android

1. SDK Android correctamente configurado (`ANDROID_HOME`/`ANDROID_SDK_ROOT`).
2. JDK 17 o superior para Gradle 9.
3. Permiso de cámara para QR.
4. Soporte para HTTP LAN sin TLS cuando aplique (cleartext policy por configuración nativa).

## 19.2 iOS

1. Permiso de cámara para QR.
2. Configuración de acceso a red local cuando backend está en LAN.

---

## 20. Requisitos de comportamiento ante fallos

`ERR-001` Si backend no disponible, mostrar estado no conectado y seguir operando localmente.  
`ERR-002` Si QR inválido o expirado, bloquear conexión y mostrar alerta clara.  
`ERR-003` Si `/stations/connect` falla, no perder configuración local.  
`ERR-004` Si WS desconecta, reintentar sin romper puntuación.  
`ERR-005` Si finalización remota falla, mantener evento pendiente para reintento.  
`ERR-006` Si snapshot de contienda no confirma activo, no mostrar “Contienda activa”.

---

## 21. Requisitos de consistencia de datos

`DATA-001` `matchId` no puede enviarse vacío a backend.  
`DATA-002` `sequence` de eventos por match debe ser incremental.  
`DATA-003` `scoreBefore/scoreAfter` deben reflejar cálculo local con límites.  
`DATA-004` `idempotencyKey` debe ser estable por evento.  
`DATA-005` Estados de match deben seguir la máquina de estados definida:
- `active`
- `finished_locally`
- `finished_locally_pending_finalize_ack`
- `finalized_acknowledged`
- `finalize_failed_retrying`

---

## 22. Guía de recreación paso a paso (alto nivel)

1. Crear proyecto Expo Router TypeScript SDK 55.
2. Definir capas `domain/application/infrastructure`.
3. Implementar esquema SQLite y migraciones.
4. Implementar repositorios por entidad.
5. Implementar servicios de sesión, match, sync, realtime, finalización, recuperación y retención.
6. Implementar `appFacade` como punto único de orquestación para pantallas.
7. Implementar pantallas:
- judge-setup;
- conexión;
- contienda;
- técnica;
- presentación;
- resumen;
- históricos;
- ajustes.

8. Integrar cola sync + connectivity monitor.
9. Integrar WS con reconexión y dedupe.
10. Integrar cálculo checksum y finalize payload.
11. Implementar tests unitarios y E2E.
12. Validar builds Android/iOS.

---

## 23. Checklist de aceptación final

## 23.1 Operación básica

1. Primer arranque pide juez.
2. Permite trabajar sin backend.
3. Permite conectar por QR + PIN.
4. Reconecta sesión persistida tras reinicio.

## 23.2 Scoring

1. Técnica y presentación separadas en pantallas.
2. Límites correctos técnica [0..4 configurable] y presentación [0..2 por categoría].
3. Botones de acción visibles y ergonómicos en portrait y landscape.
4. Reset por tipo (técnica/presentación) con confirmación.

## 23.3 Integración backend

1. Envía score-events con `matchId` válido.
2. Finaliza con payload completo + checksum.
3. Procesa `active_match_state`, `new_competitors`, `judge_settings_updated`.
4. Soporta `judge_kicked/session_revoked/station_disconnected`.

## 23.4 Resiliencia

1. Sin red, no se pierde puntuación.
2. Al volver red, sincroniza pendientes.
3. Si falla finalize remoto, reintenta.

## 23.5 Calidad

1. Unit tests verdes.
2. E2E crítica verde.
3. Typecheck verde.
4. Build APK release exitoso.

---

## 24. Notas de implementación conocidas

1. El proyecto incluye artefactos APK históricos en raíz para trazabilidad de entregas.
2. Existe documentación previa (`judge-app-technical-reference.md`).
3. El contrato backend vigente debe considerarse fuente de integración y puede evolucionar; cualquier cambio requiere ajuste coordinado app+backend.

---

## 25. Referencias internas obligatorias

1. Contrato backend: [api-contract.md](api-contract.md)
2. README operativo: [README.md](../judge-app/README.md)
3. Migraciones DB: [migrations.ts](../judge-app/src/infrastructure/db/migrations.ts)
4. Fachada principal: [appFacade.ts](../judge-app/src/application/appFacade.ts)
5. Sync engine: [syncEngine.ts](../judge-app/src/application/services/syncEngine.ts)
6. Realtime service: [realtimeService.ts](../judge-app/src/application/services/realtimeService.ts)
7. Finalización: [finalizationService.ts](../judge-app/src/application/services/finalizationService.ts)
8. Pantalla contienda: [match-setup.tsx](../judge-app/app/match-setup.tsx)
9. Pantalla técnica: [technical-scoring.tsx](../judge-app/app/technical-scoring.tsx)
10. Pantalla presentación: [presentation.tsx](../judge-app/app/presentation.tsx)
11. Pantalla resumen: [summary.tsx](../judge-app/app/summary.tsx)
12. Tests unitarios: `/tests/unit/*.test.ts`
13. Tests E2E: `/tests/e2e/*.js`

