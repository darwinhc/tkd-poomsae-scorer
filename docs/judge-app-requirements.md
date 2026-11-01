# Judge App — Detailed Requirements

Project: `tkd-poomsae-scorer`
Base path: `judge-app/`

## 1. Purpose of this document

This document defines, in operational and technical detail, **all current requirements of the judge app**
so that a third party can rebuild it without relying on unwritten knowledge.

It covers:

- functional requirements;
- UX/UI requirements;
- architecture and data requirements;
- the expected backend integration contract;
- offline persistence and synchronization requirements;
- testing requirements;
- build and installation requirements;
- a final acceptance checklist.

It describes **the expected real state** of the current implementation and the rules that must not be
broken. Product-level requirements for the whole system are in [requirements.md](requirements.md); the
implementation is described in [judge-app.md](judge-app.md); the integration contract is
[api-contract.md](api-contract.md).

---

## 2. Functional scope

### 2.1 In scope

1. Mobile app for taekwondo poomsae judges (Android first).
2. Real offline mode (usable without a backend).
3. Remote connection to a station (competition area) through QR code + PIN.
4. Technique and presentation scoring per round.
5. Robust local persistence with SQLite.
6. Offline-first HTTP synchronization queue.
7. Complementary WebSocket channel for live events.
8. Match finalization with checksum.
9. Summary, history, settings and recovery after restart.

### 2.2 Out of scope

1. Backend implementation inside the app (the backend is a separate component of this repository, see
   [backend.md](backend.md)).
2. mDNS / Bonjour / automatic network discovery.
3. Combat (kyorugi) logic.
4. Several competition types in the UI.
5. Mandatory internet access to score.

---

## 3. Product principles

1. **Real offline-first**: scoring never depends on the backend.
2. **Local-first**: every critical action is persisted locally first.
3. **Operational resilience**: the app keeps working through network outages.
4. **Ease of use**: a judge's interface with minimal cognitive load.
5. **Separation of concerns**: domain, application, infrastructure, UI.
6. **Controlled extensibility**: ready to grow without breaking the current base.

---

## 4. Stack and target versions

### 4.1 Technical base

1. Expo SDK 55 (`expo ^55.0.8`).
2. React Native `0.83.2`.
3. React `19.2.4`.
4. TypeScript `~5.9.2`.
5. Expo Router `~55.0.7`.

### 4.2 Persistence and network

1. `expo-sqlite` for operational data.
2. `expo-secure-store` for the access token.
3. `@react-native-community/netinfo` for connectivity.
4. Native WebSocket (client in the infrastructure layer).

### 4.3 State and validation

1. Zustand for the UI state projection.
2. Zod for settings and connection validation.

### 4.4 Testing

1. Unit/integration: Vitest.
2. Native mobile E2E: Detox.
3. Playwright is not used as the main native E2E runner in this project.

---

## 5. Mandatory architecture

### 5.1 Layers

1. `app/`:
   - Expo Router screens.
   - Only UI composition, navigation and calls to `appFacade`.
2. `src/domain/`:
   - Pure rules (score, rounds, checksum, retry, validation).
   - No dependency on UI, SQLite or `fetch`.
3. `src/application/`:
   - Use cases and orchestration.
   - Coordinates repositories, services and the store.
4. `src/infrastructure/`:
   - SQLite repositories.
   - HTTP/WS clients.
   - Local security (token, device ID).
5. `src/components/`:
   - Reusable, consistent UI.
6. `src/store/`:
   - Lightweight, derived UI state.
   - Never the source of truth for critical actions.
7. `src/i18n/`:
   - UI translations and the `t()` helper; `LocalizedError` for user-facing errors.

### 5.2 Design rules

1. Do not mix complex business logic into screens.
2. Each module has a single, reasonable responsibility.
3. Contracts are interfaces in `application/ports`.
4. Domain modules are pure and testable.
5. Persistence is decoupled through repositories.

---

## 6. Expected folder structure

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

  /i18n
    index.ts
    LocalizedError.ts
    /locales
      en.ts
      es.ts

  /components
    ScreenContainer.tsx
    PrimaryButton.tsx
    StatusBadge.tsx
    ScoreSidePanel.tsx
    PresentationSidePanel.tsx

  /constants
    colors.ts
    defaults.ts

  /store
    appStore.ts

  /shims
    expo-keep-awake.ts

  /utils
    id.ts
    time.ts

/tests
  /unit
  /e2e
```

---

## 7. Detailed functional requirements (with IDs)

### 7.1 Startup and judge setup

`FR-001` The app starts on a loading screen (`index`) and routes automatically.

`FR-002` If there is no `judgeName`, it opens `judge-setup`.

`FR-003` If an active match is recovered, it opens `technical-scoring`.

`FR-004` If there is no active match and a judge is set, it opens `match-setup`.

`FR-005` The judge name is persisted locally and reused across restarts.

`FR-006` Recommended placeholder shown in setup: for example `e.g. Judge 1`.

Acceptance criteria:

1. Fresh install → the app asks for the judge name.
2. Save the name → restart the app → it does not ask again.

### 7.2 Backend connection through QR and PIN

`FR-010` There is a `connection` screen.

`FR-011` It supports QR scanning with the camera (`expo-camera`).

`FR-012` It supports pasting the QR JSON manually.

`FR-013` A valid QR includes `baseUrl`, `stationId`, `protocolVersion` and `expiresAt`.

`FR-014` An expired QR is rejected.

`FR-015` A QR with `localhost` / `127.0.0.1` (or `::1`) is rejected, because a phone cannot reach it.

`FR-016` After a valid QR, the station PIN / password is requested in an overlay modal.

`FR-017` It connects with `POST /stations/connect` sending `stationId`, `judgeName`, `credential`, `deviceId`.

`FR-018` If the backend answers that the judge is already connected (`409` or equivalent), the app retries
once with `replaceExistingJudgeSession=true`.
`FR-019` On a successful connection the session and the token are persisted.

`FR-020` A red `Disconnect` button is visible only when a remote session is active.

> Note on `FR-018`: the current backend ignores `replaceExistingJudgeSession`; it replaces the previous
> session automatically only when the same judge reconnects from the same device (see
> [api-contract.md, section 4.6](api-contract.md#46-post-stationsconnect)).

Acceptance criteria:

1. Scan a valid QR + correct PIN → successful connection.
2. Leave and reopen the app → the remote session is restored (unless revoked).
3. Tap `Disconnect` → the local session becomes inactive.

### 7.3 Serverless mode

`FR-030` The app works without a remote server (`local-offline`).

`FR-031` In local mode a valid local session is created (no remote token).

`FR-032` In local mode the judge can create a match, score and finalize locally.

`FR-033` In local mode no scoring action requires a backend.

Acceptance criteria:

1. With no network and no backend → scoring works normally.
2. Events are stored in SQLite even when nothing is sent remotely.

### 7.4 Match setup screen (operational match configuration)

`FR-040` The `match-setup` screen lets the judge set competitor names.

`FR-041` It supports swapping sides (`Swap sides`).

`FR-042` The red side preference (`preferredRedSide`) is persisted.

`FR-043` It shows a connection badge (`Connected`, `Reconnecting`, `Not connected`).

`FR-044` With a connected remote session it allows syncing the match state (`Sync`).

`FR-045` The `Active match` badge is shown only when the snapshot confirms `hasActiveMatch=true`.

Acceptance criteria:

1. Change the red side and close the app → it is kept on reopening.
2. No active match on the backend → `No active match` is shown.

### 7.5 Round model

`FR-050` Default rounds = `2`.

`FR-051` Rounds are configured in Settings (not at the start of each round).

`FR-052` There is a current active round (`currentRound`).

`FR-053` Round transitions are validated with `canMoveToNextRound`.

`FR-054` The app never moves past `totalRounds`.

Acceptance criteria:

1. In the final round, moving to the next round is not allowed.
2. `nextRound` updates the persisted `currentRound`.

### 7.6 Technique scoring

`FR-060` The `technical-scoring` screen shows two panels (red and blue, by the configured sides).

`FR-061` Technique starts at a configurable value (`defaultStartingScore`, default 4).

`FR-062` Buttons per competitor: `-v1`, `-v2`, `+v1`, `+v2` (defaults 0.1 and 0.3).

`FR-063` Deductions and corrections are persisted as events with a signed `scoreDelta`.

`FR-064` Technique limits: minimum 0, maximum `startingScore`.

`FR-065` Buttons are large and visible in portrait and landscape, adapting to the screen.

`FR-066` There is a `Reset` button for the round's technique, with confirmation.

`FR-067` There is a `Next` arrow button to presentation.

`FR-068` The technique screen does not show a `Finish` button.

`FR-069` There is an `X` button to close the match, with confirmation.

Acceptance criteria:

1. Fast repeated taps do not block the UI.
2. Technique never leaves the limits [0..max].

### 7.7 Presentation scoring

`FR-080` Presentation is on a separate screen (`presentation`).

`FR-081` It shows 3 categories per competitor:
- Speed and power;
- Rhythm and tempo;
- Expression of energy.

`FR-082` Each category supports dragging and tapping on its bar.

`FR-083` Each category has `-` and `+` buttons.

`FR-084` Category limit: `0..2` (`PRESENTATION_CATEGORY_MAX_SCORE`).

`FR-085` Presentation total per competitor = sum of the 3 categories (`0..6`).

`FR-086` There is a back arrow to technique.

`FR-087` There is a reset button for the round's presentation, with confirmation.

`FR-088` If it is not the last round: a next-round arrow button.

`FR-089` If it is the last round: a `Finish` button.

Acceptance criteria:

1. Dragging the bar changes the score in valid steps.
2. A category score never leaves [0..2].

### 7.8 Score rules and calculation

`FR-100` Score events use a neutral delta model (`scoreDelta`).

`FR-101` Negative = deductions, positive = corrections.

`FR-102` Technique: `startingScore + sum(technique scoreDelta for the side)` in `sequence` order.

`FR-103` Presentation per category: `categoryStart + sum(scoreDelta of that category target)` per side.

`FR-104` Presentation total: sum of the side's categories.

`FR-105` The negative/positive breakdown in the summary applies to technique only.

Acceptance criteria:

1. The same set of events gives the same result after any reload.
2. `sequence` order makes the result deterministic.

### 7.9 Event persistence and non-blocking UI

`FR-110` Each score tap creates a `score_event` in SQLite before any remote sync.

`FR-111` The UI never blocks on remote sending.

`FR-112` The sync queue persists across restarts.

Acceptance criteria:

1. Without network, events are still created.
2. When the network returns, pending events are synchronized.

### 7.10 Resets and audit

`FR-120` Technique / presentation / round / match resets change the persisted local state.

`FR-121` A local reset writes an audit entry to `inbound_server_event_log` (`local_reset_*` events).

`FR-122` With an active remote session, a manual reset sends the WebSocket signal `judge_reset_requested`.

Acceptance criteria:

1. After a reset, the round's score projection is recalculated without the events deleted for that target.
2. Evidence remains in the local log.

### 7.11 Match finalization

`FR-130` There is a finish action with confirmation (on presentation, last round).

`FR-131` It builds a consolidated payload from local SQLite.

`FR-132` It includes a mandatory, canonical `matchId`.

`FR-133` It includes a deterministic SHA-256 `checksum`.

`FR-134` It persists a `finalization_event` before sending when there is a backend.

`FR-135` Without a backend or remote session, it closes locally (`finished_locally`).

`FR-136` With a backend, the local status becomes `finished_locally_pending_finalize_ack`.

`FR-137` On backend ACK it becomes `finalized_acknowledged`.

`FR-138` If sending fails, it becomes `finalize_failed_retrying` and is retried.

Acceptance criteria:

1. A finalization attempt is never lost.
2. Finalization works offline and online.

### 7.12 Summary

`FR-140` The `summary` screen puts per-round information first.

`FR-141` For each round and each color it shows technique, presentation and total.

`FR-142` A small overall total per color is shown at the top (2 decimals).

`FR-143` It shows the local/remote finalization status.

`FR-144` It shows connection metadata (station / server).

`FR-145` With a connected remote session it may show a "Waiting for a new match" state.

`FR-146` It includes navigation actions: restart, history, back (plus `Send now` to force a sync).

Acceptance criteria:

1. The summary is fully visible, with working scroll on small screens.
2. Round and overall totals are consistent with the local events.

### 7.13 History

`FR-150` There is a history screen (`history`).

`FR-151` It lists the matches retained locally by the retention policy.

`FR-152` It opens the summary of a historical match.

Acceptance criteria:

1. After finishing a match and creating another, history shows the retained records.

### 7.14 Settings

`FR-160` There is a settings screen with a back button.

`FR-161` It lets the judge edit:
- judge name;
- short / long deduction;
- default station;
- rounds per match;
- technique starting score;
- starting score per presentation category;
- match retention.

`FR-162` Saving validates the input with Zod.

`FR-163` Saving shows a success alert and returns to the previous screen when `OK` is tapped.

Acceptance criteria:

1. Invalid values raise a validation error.
2. After saving and reopening, the values are kept.

### 7.15 Judge-ready state and operational signals

`FR-170` When moving to the next round, the app sends the WebSocket signal `judge_round_completed` if a
remote session is active.
`FR-171` When finishing the match, the app sends the WebSocket signal `judge_match_completed` if a remote
session is active.
`FR-172` These signals do not replace the HTTP finalize request.

---

## 8. Connection and persistent session requirements

`NFR-010` The active backend, the operator session and the token are persisted.

`NFR-011` On restart the app restores the session and silently revalidates it when possible.

`NFR-012` If the backend does not answer, the session can stay in `offline` mode (no forced
re-authentication).
`NFR-013` If the backend revokes the session, the app marks it `revoked` and disconnects the WebSocket.

`NFR-014` The judge can leave the area explicitly from the UI, and the app also leaves on the WebSocket
events `judge_kicked`, `session_revoked` and `station_disconnected`.

---

## 9. Backend requirements (expected contract)

Project source of truth: [api-contract.md](api-contract.md)

### 9.1 Critical rules

1. The QR includes `stationId` (station / area).
2. `matchId` is mandatory and canonical in score events and finalize.
3. The WebSocket uses the query parameters `sessionId`, `stationId`, `token`.

### 9.2 Minimum endpoints

1. `GET /health`
2. `GET /stations/active`
3. `POST /stations/connect`
4. `GET /stations/{stationId}/active-match-state`
5. `POST /score-events`
6. `POST /matches/finalize`

### 9.3 Supported inbound WebSocket events

1. `reset_match`
2. `reset_round`
3. `new_competitors` (preferred by color: `competitorRedName`, `competitorBlueName`)
4. `active_match_state`
5. `judge_settings_updated`
6. `round_changed`
7. `match_updated`
8. `station_disconnected`
9. `session_revoked`
10. `judge_kicked`
11. `server_notice`
12. `ping`

### 9.4 Outbound WebSocket events from the app

1. `judge_round_completed`
2. `judge_match_completed`
3. `judge_reset_requested`
4. `ping` (echo / control)

---

## 10. Persistence requirements (SQLite)

### 10.1 Source of truth

`NFR-020` SQLite is the source of truth for scoring, match state and the sync queue.

### 10.2 Mandatory minimum schema

Tables:

1. `app_settings`
2. `backend_server`
3. `station`
4. `operator_session`
5. `match`
6. `round`
7. `score_event`
8. `finalization_event`
9. `inbound_server_event_log`

### 10.3 Key fields

1. `app_settings.preferred_red_side` to persist the sides.
2. `app_settings.server_has_active_match` and the names by color for the active match snapshot.
3. `score_event.idempotency_key` unique.
4. `score_event.sequence` for deterministic ordering.
5. `finalization_event.payload_snapshot` for retries.

---

## 11. Offline-first synchronization requirements

`NFR-030` First sync attempt right after an event is created.

`NFR-031` Retries with backoff + jitter (`retryPolicy`).

`NFR-032` Automatic retry on a timer (`5 s`).

`NFR-033` Retry when the device comes back online (`NetInfo`).

`NFR-034` Retry when the app returns to the foreground (`AppState active`).

`NFR-035` Manual retry (`syncNow` / `resyncNow`).

`NFR-036` Duplicates are avoided with `idempotencyKey`.

`NFR-037` Events already acknowledged are not resent.

`NFR-038` The finalization queue is retried until ACK.

---

## 12. Realtime requirements (WebSocket)

`NFR-040` The WebSocket does not replace offline-first HTTP.

`NFR-041` If the WebSocket drops, scoring keeps working.

`NFR-042` Automatic reconnection with exponential backoff + jitter.

`NFR-043` Inbound events are de-duplicated with a persisted `dedupe_key`.

`NFR-044` Relevant inbound events are persisted in the local log.

`NFR-045` Payloads are mapped flexibly (camelCase / snake_case / fallbacks).

---

## 13. UX/UI requirements

### 13.1 Language and clarity

1. The UI is in English by default; it switches to Spanish when the device locale is Spanish (`es*`),
   through `src/i18n` (`locales/en.ts`, `locales/es.ts`). Missing keys fall back to English.
2. Keep technical jargon away from the end user.
3. Direct, understandable labels.

### 13.2 Ergonomics

1. Portrait-first is mandatory.
2. Landscape is allowed without breaking operation.
3. Large, well-separated buttons with immediate feedback.
4. Strong visual distinction by competitor color.

### 13.3 Colors and sides

1. Sport logic is handled by color (`RED` / `BLUE`).
2. Showing a color on the left or right depends on the local `preferredRedSide`.
3. Swapping sides persists for the next matches.

### 13.4 Indicators

1. Connection badge on the operational screens.
2. Active match badge only with a real confirmation from the backend.
3. Useful iconography (arrows, wifi / cloud-offline, close, swap).

---

## 14. Performance and memory requirements

`NFR-050` Full history is not loaded into memory for every screen.

`NFR-051` In-memory projection only of the active match and visible data.

`NFR-052` History queries are lightweight and lazy.

`NFR-053` No unnecessary background work outside sync and realtime.

---

## 15. Retention, history and recovery requirements

`NFR-060` `retainedMatchesCount` minimum 2, default 2.

`NFR-061` The active match is never deleted.

`NFR-062` The last N matches are kept by date and status.

`NFR-063` Safe cleanup through `RetentionService`.

`NFR-064` The active match is recovered after a restart and opened on the right screen.

---

## 16. Security requirements

`SEC-001` The access token is not stored in plain SQLite; `expo-secure-store` is used.

`SEC-002` A `deviceId` is persisted locally for station traceability.

`SEC-003` Strict validation of the QR and the credentials before connecting.

`SEC-004` Support for remote revocation through the WebSocket.

---

## 17. Testing requirements

### 17.1 Minimum unit tests

1. Score and delta calculation (`scoreCalculator`).
2. Match aggregation and the 10-point cap (`matchAggregation`).
3. Round transition validation (`roundRules`).
4. Retry / backoff eligibility (`retryPolicy`).
5. QR / connection validation (`connectionValidation`).
6. Settings validation (`settingsValidation`).
7. Checksum and finalization (`checksumAndFinalization`).
8. Sync engine idempotency (`syncEngine`).
9. Reset and audit (`matchServiceReset`).
10. Robust mapping of WebSocket events (`realtimeHandler`).
11. Applying WebSocket events and persistence (`realtimeService`).
12. Match retention (`retentionPolicy`).
13. Recovery after restart (`recoveryService`).
14. Session restore and judge replacement (`sessionService`).
15. Lazy history query (`historyQueryService`).
16. Active match snapshot retrieval (`apiClient`).
17. Locale key parity and English fallback (`i18n`).

### 17.2 Minimum E2E tests (Detox)

1. First-run flow (judge setup + connection / local mode).
2. Full scoring flow:
   - start a match;
   - score technique on both sides;
   - go to presentation;
   - change categories;
   - go back;
   - advance the round;
   - reset with confirmation;
   - finish;
   - open history.

The E2E specs expect the emulator to run with an English device locale.

### 17.3 Required scripts

1. `npm run test`
2. `npm run test:e2e:build`
3. `npm run test:e2e`
4. `npm run typecheck`

---

## 18. Build, run and installation requirements

### 18.1 Development

1. `npm install`
2. `npm run start` (Expo Go on the LAN, with `EXPO_UNSTABLE_HEADLESS=1`).

### 18.2 Development client

1. `npm run start:dev-client`
2. `npm run android` / `npm run ios`

### 18.3 Local APK (Gradle)

1. Generate the native project: `npx expo prebuild` (the `android/` folder is not committed).
2. Go to `android/`.
3. `./gradlew assembleRelease` or `./gradlew assembleDebug`.
4. APK at `android/app/build/outputs/apk/release/app-release.apk` (or `.../debug/app-debug.apk`).

### 18.4 Cloud APK (EAS)

1. `npx eas-cli login`
2. `npm run build:apk` (runs `eas build -p android --profile preview`; needs the `eas` CLI on the `PATH`,
   or run `npx eas-cli build -p android --profile preview`).

### 18.5 Installation from the command line

1. With an ADB device detected:
   - `adb install -r /path/to/app.apk`

---

## 19. Native Android / iOS requirements

### 19.1 Android

1. Android SDK correctly configured (`ANDROID_HOME` / `ANDROID_SDK_ROOT`).
2. JDK 17 or later for Gradle.
3. Camera permission for the QR.
4. Support for LAN HTTP without TLS when needed (`android.usesCleartextTraffic: true` in `app.json`).

### 19.2 iOS

1. Camera permission for the QR (`NSCameraUsageDescription`).
2. Local network access when the backend is on the LAN (`NSLocalNetworkUsageDescription`).

---

## 20. Failure behavior requirements

`ERR-001` If the backend is unavailable, show "not connected" and keep working locally.

`ERR-002` If the QR is invalid or expired, block the connection and show a clear alert.

`ERR-003` If `/stations/connect` fails, the local configuration is not lost.

`ERR-004` If the WebSocket disconnects, retry without breaking scoring.

`ERR-005` If remote finalization fails, keep the event pending for retry.

`ERR-006` If the match snapshot does not confirm an active match, do not show "Active match".

---

## 21. Data consistency requirements

`DATA-001` `matchId` is never sent empty to the backend.

`DATA-002` Event `sequence` per match is incremental.

`DATA-003` `scoreBefore` / `scoreAfter` reflect the local calculation with limits.

`DATA-004` `idempotencyKey` is stable per event.

`DATA-005` Match statuses follow the defined state machine:
- `active`
- `finished_locally`
- `finished_locally_pending_finalize_ack`
- `finalized_acknowledged`
- `finalize_failed_retrying`

---

## 22. Step-by-step rebuild guide (high level)

1. Create an Expo Router TypeScript project on SDK 55.
2. Define the `domain` / `application` / `infrastructure` layers.
3. Implement the SQLite schema and migrations.
4. Implement one repository per entity.
5. Implement the session, match, sync, realtime, finalization, recovery and retention services.
6. Implement `appFacade` as the single orchestration entry point for screens.
7. Implement the screens:
   - judge-setup;
   - connection;
   - match-setup;
   - technical-scoring;
   - presentation;
   - summary;
   - history;
   - settings.
8. Integrate the sync queue and the connectivity monitor.
9. Integrate the WebSocket with reconnection and de-duplication.
10. Integrate the checksum calculation and the finalize payload.
11. Add the English and Spanish translations (`src/i18n`).
12. Implement unit and E2E tests.
13. Validate Android / iOS builds.

---

## 23. Final acceptance checklist

### 23.1 Basic operation

1. First launch asks for the judge.
2. Works without a backend.
3. Connects through QR + PIN.
4. Reconnects the persisted session after a restart.

### 23.2 Scoring

1. Technique and presentation on separate screens.
2. Correct limits: technique [0..4, configurable], presentation [0..2 per category].
3. Action buttons visible and ergonomic in portrait and landscape.
4. Reset per type (technique / presentation) with confirmation.

### 23.3 Backend integration

1. Sends score events with a valid `matchId`.
2. Finalizes with a complete payload + checksum.
3. Handles `active_match_state`, `new_competitors`, `judge_settings_updated`.
4. Supports `judge_kicked` / `session_revoked` / `station_disconnected`.

### 23.4 Resilience

1. Without network, no score is lost.
2. When the network returns, pending items are synchronized.
3. If remote finalize fails, it is retried.

### 23.5 Quality

1. Unit tests green.
2. Critical E2E green.
3. Typecheck green.
4. Release APK build succeeds.

---

## 24. Known implementation notes

1. The technical reference of the app is [judge-app.md](judge-app.md).
2. The backend contract in force is the integration source of truth and may evolve; any change requires a
   coordinated app + backend update.
3. Interoperability gaps verified in the current code (checksum format, WebSocket keep-alive, station
   disconnect broadcast) are listed in [judge-app.md](judge-app.md#known-limitations) and
   [backend.md](backend.md#known-limitations).

---

## 25. Internal references

1. Backend contract: [api-contract.md](api-contract.md)
2. App README: [README.md](../judge-app/README.md)
3. DB migrations: [migrations.ts](../judge-app/src/infrastructure/db/migrations.ts)
4. Main facade: [appFacade.ts](../judge-app/src/application/appFacade.ts)
5. Sync engine: [syncEngine.ts](../judge-app/src/application/services/syncEngine.ts)
6. Realtime service: [realtimeService.ts](../judge-app/src/application/services/realtimeService.ts)
7. Finalization: [finalizationService.ts](../judge-app/src/application/services/finalizationService.ts)
8. Match setup screen: [match-setup.tsx](../judge-app/app/match-setup.tsx)
9. Technique screen: [technical-scoring.tsx](../judge-app/app/technical-scoring.tsx)
10. Presentation screen: [presentation.tsx](../judge-app/app/presentation.tsx)
11. Summary screen: [summary.tsx](../judge-app/app/summary.tsx)
12. Translations: [en.ts](../judge-app/src/i18n/locales/en.ts), [es.ts](../judge-app/src/i18n/locales/es.ts)
13. Unit tests: `judge-app/tests/unit/*.test.ts`
14. E2E tests: `judge-app/tests/e2e/*.e2e.js`
