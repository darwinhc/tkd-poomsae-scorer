# TKD Poomsae Scorer Backend

Production-oriented backend scaffold for taekwondo poomsae scoring using Hexagonal Architecture (Ports and Adapters) with Bisslog-style use-case orchestration.

Detailed technical documentation:

- [`docs/backend-technical-reference.md`](../docs/backend-technical-reference.md)
- API contract shared with the judge app: [`docs/api-contract.md`](../docs/api-contract.md)

## Highlights

- Python 3.11+
- Hexagonal architecture with strict layer boundaries
- FastAPI as transport-only entry point
- Framework-agnostic domain and application layers
- SQLAlchemy persistence adapters
- Real-time push model through WebSocket hub and realtime port
- Local admin frontend served by the same FastAPI app (Jinja2 templates + static assets)
- Explicit idempotency for score events and finalization
- Judge/session/station traceability
- Structured logging
- Unit, integration, and API tests

## Architecture

### Layering

- `domain`: entities, value objects, domain services, business exceptions
- `application`: use cases, DTOs, mappers
- `ports`: repository/service/realtime/security abstractions
- `adapters`: SQLAlchemy repositories, JWT/token services, checksum, realtime adapter
- `infra`: config, persistence models, FastAPI DI plumbing, logging, websocket hub
- `entry_points`: FastAPI app bootstrap only

### Bisslog-style conventions applied

- Use cases orchestrate business rules and side effects
- Ports define external dependencies
- Adapters implement ports in infra boundary
- FastAPI routes perform only request parsing, DTO mapping, use-case invocation, response mapping
- Transport and persistence details do not leak into domain logic

## Project Structure

```text
src/tkd_scorer/
  domain/
    entities/
    value_objects/
    services/
    exceptions/
  application/
    use_cases/
    dto/
    mappers/
  ports/
    repositories/
    services/
    realtime/
    security/
    clock/
    id_generator/
  adapters/
    repositories/
    realtime/
    security/
    qr/
    checksum/
  infra/
    templates/
    static/
    fastapi/
    persistence/
    config/
    logging/
    websocket/
  entry_points/
    fastapi/
      api/
      admin_views/
      websocket/

tests/
  unit/
  integration/
  api/
```

## Core Flows

### Station connection and persistent session

1. Client gets stations (`GET /stations/active`)
2. Client posts connection data (`POST /stations/connect`) with:
   - `station_id`
   - `judge_name`
   - `credential`
   - `device_id`
3. Backend verifies credential and judge/device consistency
4. Backend creates (or renews) judge session and returns long-lived access token
5. A station may have multiple active judge sessions at the same time
6. Client can restore silently with `POST /sessions/restore`

### Score ingestion

- `POST /score-events` accepts score actions with `event_id` + `idempotency_key`
- Duplicate keys return consistent idempotent replay response
- Sequence is strictly monotonic per match
- Every score event is auditable and tied to judge/session/station

### Match control

- Create match: `POST /matches`
- Advance round: `POST /matches/{match_id}/next-round`
- Reset round: `POST /matches/{match_id}/reset-round`
- Reset match: `POST /matches/{match_id}/reset-match`
- Summary: `GET /matches/{match_id}/summary`

### Finalization and reconciliation

- `POST /matches/finalize`
- Validates match/session/judge context
- Recomputes canonical checksum payload through checksum service port
- If reconciled: marks match finished and revokes the finalized judge session
- Station is freed only when no active judge sessions remain
- If not reconciled: marks `finalization_pending` and records discrepancy notes
- Finalization is idempotent via `idempotency_key`

### Realtime

- WebSocket endpoint: `/ws`
- Supports bind and ping transport messages
- Server pushes through `RealtimePort` only, never from domain
- Supports targeted station/session notifications
- Emits contract bootstrap events on bind:
  - `judge_settings_updated`
  - `active_match_state`
- Judge expulsion flow emits:
  - `judge_kicked` (recommended by contract)
  - `session_revoked` (compatibility behavior)

### Local admin frontend

- Dashboard: `/admin`
- Login admin: `/admin/login`
- Stations list: `/admin/stations`
- Station detail: `/admin/stations/{station_id}`
- Kick judge session: `POST /admin/stations/{station_id}/sessions/{session_id}/kick`
- Station live scoreboard (public): `/scoreboard/{station_id}`
- Match setup on the station detail page, with separate actions: `Draw poomsaes`
  (`POST /admin/stations/{station_id}/matches/draw-preview`) and `Start match`
  (`POST /admin/stations/{station_id}/matches/start`)
- Save next competitors draft: `POST /admin/stations/{station_id}/matches/save-competitors`
- Active match controls: `POST /admin/stations/{station_id}/active-match/{start-round,stop-round,pause-timer,reset-round,finalize}`
- Station live debug (protected): `/admin/stations/{station_id}/scoreboard/debug`
- Match detail: `/admin/matches/{match_id}`
- Aggregated results: `/admin/results`
- Recent history: `/admin/history`
- Delete one history item: `POST /admin/history/{match_id}/delete`
- Delete history in bulk: `POST /admin/history/delete-all`
- QR image: `/admin/stations/{station_id}/qr.png`

Admin pages are server-rendered and call `AdminViewUseCases` from application layer.

UI language (admin panel and TV scoreboard):

- Set `TKD_UI_LANGUAGE` to `en` (default) or `es`.
- All user-visible strings live in `src/tkd_scorer/infra/i18n/locales/{en,es}.json`
  (flat `key -> text` maps with `{name}` placeholders; both files must have the same keys).
- Templates use the `t('key', **params)` Jinja global and the `status_label` filter.
- The application layer returns translation keys (for example `winner.red`,
  `round_action.start`), never display text.
No scoring/station business rules are implemented directly in templates or admin controllers.
History deletion rule: matches in `in_progress`/`finalization_pending` with active session are protected and skipped.

Admin auth policy:

- If `TKD_ADMIN_PASSWORD` is configured, `/admin/*` requires login cookie.
- Live screens for TV are public:
  - `/scoreboard/{station_id}`
  - `/scoreboard/{station_id}/live`
- Debug live remains protected behind admin auth:
  - `/admin/stations/{station_id}/scoreboard/debug`
  - `/admin/stations/{station_id}/scoreboard/debug/live`
- You can hide admin under a custom path (`TKD_ADMIN_BASE_PATH`), for example `/secret-tkd-panel`.
  - When custom path is enabled, legacy `/admin/*` returns `404`.

### Judge consolidation rules (from the official 3/5/7-judge scoring spreadsheet)

- One shared match per fight; every judge (session) keeps its own scorecard: technique starts at
  `TKD_JUDGE_DEFAULT_STARTING_SCORE` (0..start) and each of the three presentation categories at
  `TKD_JUDGE_PRESENTATION_CATEGORY_START_SCORE` (0..2.0), per round and side
- Technique and presentation are consolidated separately, per round and side:
  - `3` judges (or fewer than 5): plain average
  - `5` or `7` judges (and 6): discard one highest and one lowest, average the rest
  - each part rounded to 2 decimals (half up); round (poomsae) score = technique + presentation
- Final competitor score is the average of the round scores (2 decimals, half up)
- Winner: higher final score, then higher consolidated presentation; otherwise a draw (the remaining
  tie-break steps are applied manually)
- The match closes when every judge session active at the station when it was started has finalized (`FINISHED`, or
  `FINALIZATION_PENDING` if a judge scorecard did not reconcile)
- On station scoreboard screen:
  - one column per judge (J1..Jn, in connection order) with its TEC / PRES per round, plus the consolidated value
  - official consolidation is enabled only for `3`, `5`, or `7` judges
  - red background when RED wins
  - blue background when BLUE wins
  - gray background with `Tie` when tied

## Persistence and migrations approach

Current scaffold uses SQLAlchemy models and startup schema creation (`Base.metadata.create_all`) for fast local operation.
Columns added after the first release (`matches.judges_required`, `score_events.score_target`,
`finalization_records.round_numbers` / `response_payload`) are added to existing SQLite files on startup by an
idempotent "add column if missing" step (`infra/persistence/session_factory.py`).

For production rollout, add Alembic migrations:

1. Initialize Alembic
2. Generate baseline migration from current models
3. Disable runtime `create_all` in production
4. Run migrations during deployment

## Configuration

Environment variables use `TKD_` prefix:

- `TKD_HOST`
- `TKD_PORT`
- `TKD_PUBLIC_BASE_URL` (preferred URL for QR/bootstrap payloads)
- `TKD_DATABASE_URL`
- `TKD_BASE_URL`
- `TKD_QR_USE_SERVER_IP` (`true` by default)
- `TKD_QR_SERVER_IP_OVERRIDE` (optional, recommended in LAN tournaments)
- `TKD_ENVIRONMENT`
- `TKD_JWT_SECRET_KEY`
- `TKD_JWT_ALGORITHM`
- `TKD_BOOTSTRAP_TOKEN_TTL_SECONDS`
- `TKD_OPERATIONAL_TOKEN_TTL_SECONDS`
- `TKD_STATION_CREDENTIAL_TTL_SECONDS`
- `TKD_ADMIN_BASE_PATH` (default: `/admin`)
- `TKD_ADMIN_PASSWORD` (optional, protects `/admin` routes)
- `TKD_ADMIN_AUTH_COOKIE_NAME`
- `TKD_ADMIN_AUTH_COOKIE_TTL_SECONDS`
- `TKD_ADMIN_IP_ALLOWLIST` (optional, comma-separated IP/CIDR list; admin-sensitive routes only)
- `TKD_ADMIN_TRUST_PROXY_HEADERS` (`false` by default; trust `X-Forwarded-For` only if behind trusted proxy)
- `TKD_ADMIN_LOGIN_MAX_ATTEMPTS`
- `TKD_ADMIN_LOGIN_WINDOW_SECONDS`
- `TKD_ADMIN_LOGIN_LOCKOUT_SECONDS`
- `TKD_ADMIN_MIN_PASSWORD_LENGTH`
- `TKD_ADMIN_SECURITY_FAIL_FAST` (`true` by default; blocks startup on insecure admin config)
- `TKD_HISTORY_RETENTION_MATCHES`
- `TKD_JUDGE_DEFAULT_ROUNDS`
- `TKD_JUDGE_DEFAULT_STARTING_SCORE`
- `TKD_JUDGE_PRESENTATION_CATEGORY_START_SCORE`
- `TKD_JUDGE_ACTION_VALUE_1`
- `TKD_JUDGE_ACTION_VALUE_2`
- `TKD_WEBSOCKET_PING_INTERVAL_SECONDS`
- `TKD_DATA_DIR`
- `TKD_LOGS_DIR`
- `TKD_LOG_FILE_NAME`
- `TKD_LOG_LEVEL`
- `TKD_UI_LANGUAGE` (`en` by default, or `es`)
- `TKD_REQUIRE_POOMSAE_CATALOG_FILE`
- `TKD_POOMSAE_CATALOG_PATH`

Defaults are in `src/tkd_scorer/infra/config/settings.py`.

The backend reads `.env` from the runtime root:

- Source/dev mode: repository root
- Packaged mode (PyInstaller): same folder where executable is located

Suggested LAN hardening:

1. Set a strong `TKD_ADMIN_PASSWORD`.
2. Move admin path from `/admin` to a non-obvious value with `TKD_ADMIN_BASE_PATH`.
3. Restrict admin by operator IP(s) using `TKD_ADMIN_IP_ALLOWLIST`.
4. Keep lockout settings enabled (`TKD_ADMIN_LOGIN_*`).
5. Keep fail-fast enabled (`TKD_ADMIN_SECURITY_FAIL_FAST=true`) to prevent insecure startup.

Poomsae catalog behavior:

- Catalog is loaded from `config/poomsae_categories.yaml`.
- In packaged operation, you should keep `TKD_REQUIRE_POOMSAE_CATALOG_FILE=true`.
- Startup fails clearly if required catalog is missing or malformed.
- Reference files:
  - `config/poomsae_categories.yaml`
  - `packaging/runtime/config/poomsae_categories.yaml`

QR bootstrap base URL behavior:

- By default, QR payload uses detected server LAN IP (not browser host/IP).
- You can force a specific server IP with `TKD_QR_SERVER_IP_OVERRIDE`.
- Port and scheme are taken from `TKD_BASE_URL`.

## Run

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
python -m tkd_scorer.entry_points.runtime_server
```

For LAN usage, replace host/port values as needed and use:

- API base: `http://<LAN_IP>:8080`
- Admin frontend: `http://<LAN_IP>:8080<TKD_ADMIN_BASE_PATH>`
- Public live scoreboard: `http://<LAN_IP>:8080/scoreboard/<station_id>`

## Packaging (PyInstaller onedir)

Install tooling:

```bash
. .venv/bin/activate
pip install -e '.[dev,packaging]'
```

Use Makefile targets:

```bash
make help
make package-linux
make package-windows
make package-all
```

Important:

- PyInstaller packaging must run on the target OS.
- Linux target must be built on Linux.
- Windows target must be built on Windows/MSYS.
- `make package-all` only attempts both targets sequentially; it does not cross-compile.

Generated artifacts:

- Linux bundle: `dist/linux/PoomsaeServer`
- Windows bundle: `dist/windows/PoomsaeServer`

Delivery bundle includes:

- Executable folder (`PoomsaeServer/`)
- Editable `.env`
- Editable `config/poomsae_categories.yaml`
- Writable `data/` and `logs/`
- Operator launcher (`Start Admin Panel.bat` or `start_admin_panel.sh`)
- `OPERATIONS.txt`

## Test

```bash
. .venv/bin/activate
pytest -q
```

Admin route tests are included in `tests/api/test_admin_routes.py`.

## Templates and static organization

- Templates: `src/tkd_scorer/infra/templates/admin/*.html`
- Static assets: `src/tkd_scorer/infra/static/admin/*`
- Admin route entry points: `src/tkd_scorer/entry_points/fastapi/admin_views/routes.py`

FastAPI serves static files under `/static` and Jinja2 templates through app state.

## Station bootstrap policy

No default stations are seeded at startup.

Create stations explicitly from:

- Admin frontend: `POST /admin/stations/create` via `/admin/stations`
- API workflows or future setup scripts

## SOLID and maintainability notes

- **S**ingle Responsibility: entities, use cases, adapters, and routes have focused responsibilities
- **O**pen/Closed: new adapters (Redis realtime, different token provider) can be added via ports without modifying use cases
- **L**iskov Substitution: in-memory and SQLAlchemy repos implement the same ports and can replace each other in tests/runtime
- **I**nterface Segregation: small ports per concern (token, checksum, station repo, etc.)
- **D**ependency Inversion: use cases depend on abstract ports, not concrete infrastructure

## Production hardening checklist

- Add Alembic migrations and deployment workflow
- Add token rotation and station credential rotation
- Add authorization policies for admin control endpoints
- Add pagination/filtering for audit queries
- Add optimistic concurrency/versioning for high-contention stations
- Add reconnection replay for websocket missed events
