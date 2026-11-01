# TKD Poomsae Scorer — Judge App (React Native / Expo)

Offline-first mobile app for poomsae judges. SQLite is the source of truth, score events are synced to the
tournament server over an HTTP event queue, and a complementary WebSocket channel delivers live commands.

## Stack

- Expo SDK 55
- React Native + TypeScript
- Expo Router
- SQLite (`expo-sqlite`) for durable persistence
- Secure token storage with `expo-secure-store`
- Lightweight UI state with Zustand (a projection of SQLite)
- Unit tests with Vitest
- E2E tests with Detox (a better fit for native mobile than Playwright)

## Architecture

Separate layers:

- `src/domain`: pure rules (score, rounds, retry, checksum, validation)
- `src/application`: use cases and orchestration (`AppFacade`, `SyncEngine`, `SessionService`, `MatchService`, ...)
- `src/infrastructure`: SQLite repositories, HTTP/WS clients, connectivity, security
- `src/i18n`: UI translations (`locales/en.ts`, `locales/es.ts`) and the `t()` helper
- `app`: Expo Router screens (UI and interaction only)

## Operating flow

1. First launch: the judge name is captured (`judge-setup`).
2. The app opens `match-setup`. Without a server session it starts a local session automatically (full local mode).
3. Optional connection to the tournament server from `connection`: scan the QR code (or paste its JSON),
   then enter the station password.
4. While connected, the active match and competitor names come from the server
   (`GET /stations/{station_id}/active-match-state` plus WebSocket events).
5. Technique scoring (`technical-scoring`) and presentation scoring (`presentation`), round by round.
6. Every action is written to SQLite first (`score_event`) and then sent asynchronously.
7. Finalization builds a deterministic SHA-256 checksum, persists a `finalization_event` and retries until ACK.

## Local database

Main tables:

- `app_settings`
- `backend_server`
- `station`
- `operator_session`
- `match`
- `round`
- `score_event`
- `finalization_event`
- `inbound_server_event_log`

See `src/infrastructure/db/migrations.ts`.

## Offline-first sync

`SyncEngine`:

- first attempt immediately after each action
- retry with exponential backoff + jitter
- periodic retry timer
- retry when the device comes back online
- retry when the app returns to the foreground
- manual sync from `match-setup` (**Sync**) and `summary` (**Send now**)
- idempotency through `idempotencyKey = event.id`
- never resends events that were already acknowledged

## Realtime WebSocket

`RealtimeService` / `RealtimeClient`:

- connects after an authenticated session is established
- automatic reconnection with backoff
- scoring is never blocked when the WebSocket drops
- inbound events are de-duplicated (`inbound_server_event_log`)
- supported events: `new_competitors`, `active_match_state`, `match_updated`, `judge_settings_updated`,
  `round_changed`, `reset_match`, `reset_round`, `session_revoked`, `judge_kicked`, `station_disconnected`,
  `server_notice`, `ping`

## Retention and history

- `retainedMatchesCount` is configurable (minimum 2, default 2)
- the active match is always preserved
- safe cleanup through `RetentionService`
- lightweight history list with lazy detail loading (`HistoryQueryService`)

## Persistent session restore

- backend, session and token are restored on startup
- silent revalidation
- if the backend is offline the session is kept (`offline`) and no re-authentication is forced
- the session is only invalidated when the server reports it as revoked or invalid

## Screens

| Route | Purpose |
|---|---|
| `judge-setup` | First-run judge name |
| `connection` | QR / station password, connect and disconnect |
| `match-setup` | Competitor names, sides, server match state, start |
| `technical-scoring` | Technique deductions per round |
| `presentation` | Presentation categories per round, next round, finish |
| `summary` | Per-round and overall totals, sync status |
| `history` | Retained matches (active, pending, finalized) |
| `settings` | Judge name, deduction values, rounds, starting scores, retention |

Portrait-first layout with large touch targets.

## Languages

The UI language follows the device locale (read through `Intl`): Spanish (`es*`) shows Spanish, anything else
shows English, which is also the fallback for missing keys. All user-visible text lives in
`src/i18n/locales/en.ts` and `src/i18n/locales/es.ts`; both files must define the same keys (checked by
`tests/unit/i18n.test.ts`). Use `t('key', { param })` in screens and components, and throw `LocalizedError`
from services for errors that are shown to the user.

## Scripts

| Script | Description |
|---|---|
| `npm run start` | Expo Go, LAN, clean cache (headless) |
| `npm run start:go` | Same as `start` |
| `npm run start:go:tunnel` | Expo Go through a tunnel |
| `npm run start:dev-client` | Development client, LAN, clean cache |
| `npm run start:mock` | Development client with the mock backend (`EXPO_PUBLIC_USE_MOCK_BACKEND=1`) |
| `npm run start:tunnel` | Development client through a tunnel |
| `npm run start:phone` | Kills any process on port 8081, then starts Expo Go on the LAN IP of this machine |
| `npm run android` / `npm run ios` | Native build and run (`expo run:*`) |
| `npm run web` | Web target |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | ESLint |
| `npm run test` / `npm run test:watch` | Vitest unit tests (single run / watch) |
| `npm run test:e2e:build` | Detox Android debug build |
| `npm run test:e2e` | Detox Android E2E tests |
| `npm run test:e2e:mock` | Detox E2E tests against the mock backend |
| `npm run build:apk` | EAS build of an Android APK (`preview` profile) |

## Tests

### Unit

```bash
npm run test
```

Covers:

- score calculation and aggregation
- round transitions
- retry eligibility and backoff
- settings and connection validation
- checksum and finalization
- sync idempotency
- reset and audit log
- realtime event handling
- active match snapshot retrieval
- retention policy
- recovery on restart
- session restore
- lazy history queries
- locale key parity and English fallback

### E2E (Detox)

> Playwright is not a good fit for native React Native E2E tests, so Detox is used.
> The specs expect the emulator to use an English device locale.

1. Native prebuild:

```bash
npx expo prebuild
```

2. Detox Android build:

```bash
npm run test:e2e:build
```

3. Run:

```bash
npm run test:e2e
```

Specs:

- `tests/e2e/first-run.e2e.js`
- `tests/e2e/scoring.e2e.js`

## Development

```bash
npm install
npm run start
```

`npm run start` opens in Expo Go mode (LAN) and avoids the DevTools issue on Linux.

### Using it without a server (fully offline)

1. Enter the judge name on first launch.
2. Set up the match on `match-setup` (a local session is created automatically).
3. Score normally. Everything is stored locally in SQLite.
4. If you connect to a server later, pending events are sent by the sync engine.

### Temporary Android APK

Local option (requires the Android SDK and `adb`):

```bash
npm run android
```

Cloud option (no local SDK, recommended):

```bash
npx eas login
npm run build:apk
```

Download the generated `.apk` and install it on the phone.

### Error: `Failed to download remote update`

Most common cause: the phone cannot reach the Metro server (IP, port, firewall or a different network).

Quick steps:

1. Put the computer and the phone on the same Wi-Fi network.
2. Stop any old Metro process:

```bash
lsof -ti tcp:8081 | xargs -r kill -9
```

3. Start clean:

```bash
npm run start:phone
```

4. Open Expo Go and scan the new QR code.
5. If it still fails, use a tunnel:

```bash
npm run start:go:tunnel
```

## Native notes

- QR camera: camera permission is required.
- iOS LAN: `NSLocalNetworkUsageDescription` is configured.
- Android LAN HTTP: `usesCleartextTraffic` is enabled in `app.json` for local servers without TLS.
- Tokens are never stored in plain SQLite; they are persisted in `expo-secure-store`.

## Structure

- `app/`
- `src/application/`
- `src/components/`
- `src/domain/`
- `src/i18n/`
- `src/infrastructure/`
- `src/store/`
- `tests/unit/`
- `tests/e2e/`
