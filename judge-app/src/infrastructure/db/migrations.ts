import {
  DEFAULT_ACTION_VALUE_1,
  DEFAULT_ACTION_VALUE_2,
  DEFAULT_PRESENTATION_CATEGORY_START,
  DEFAULT_RETAINED_MATCHES,
  DEFAULT_ROUNDS,
  DEFAULT_STATION_ID,
  DEFAULT_STARTING_SCORE
} from '@/constants/defaults';
import { getDb } from './client';

const SCHEMA_SQL = `
CREATE TABLE IF NOT EXISTS app_settings (
  id INTEGER PRIMARY KEY CHECK(id = 1),
  judge_name TEXT NOT NULL DEFAULT '',
  server_has_active_match INTEGER NOT NULL DEFAULT 0,
  server_active_match_id TEXT,
  server_competitor_red_name TEXT,
  server_competitor_blue_name TEXT,
  server_match_updated_at TEXT,
  action_value_1 REAL NOT NULL DEFAULT ${DEFAULT_ACTION_VALUE_1},
  action_value_2 REAL NOT NULL DEFAULT ${DEFAULT_ACTION_VALUE_2},
  remote_base_url TEXT,
  bootstrap_token TEXT,
  default_station_id TEXT NOT NULL DEFAULT '${DEFAULT_STATION_ID}',
  default_rounds INTEGER NOT NULL DEFAULT ${DEFAULT_ROUNDS},
  presentation_category_start_score REAL NOT NULL DEFAULT ${DEFAULT_PRESENTATION_CATEGORY_START},
  default_starting_score REAL NOT NULL DEFAULT ${DEFAULT_STARTING_SCORE},
  retained_matches_count INTEGER NOT NULL DEFAULT ${DEFAULT_RETAINED_MATCHES},
  preferred_red_side TEXT NOT NULL DEFAULT 'LEFT',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backend_server (
  id TEXT PRIMARY KEY,
  base_url TEXT NOT NULL,
  bootstrap_token TEXT,
  environment TEXT,
  tournament_id TEXT,
  protocol_version TEXT NOT NULL,
  expires_at TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS station (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operator_session (
  id TEXT PRIMARY KEY,
  backend_server_id TEXT NOT NULL,
  station_id TEXT NOT NULL,
  station_name TEXT NOT NULL,
  judge_name TEXT NOT NULL,
  device_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  token_expires_at TEXT,
  last_validated_at TEXT,
  connection_status TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(backend_server_id) REFERENCES backend_server(id)
);

CREATE TABLE IF NOT EXISTS match (
  id TEXT PRIMARY KEY,
  competitor_left_name TEXT NOT NULL,
  competitor_right_name TEXT NOT NULL,
  left_side_color TEXT NOT NULL DEFAULT 'RED',
  right_side_color TEXT NOT NULL DEFAULT 'BLUE',
  total_rounds INTEGER NOT NULL,
  current_round INTEGER NOT NULL,
  starting_score REAL NOT NULL,
  presentation_category_start_score REAL NOT NULL DEFAULT ${DEFAULT_PRESENTATION_CATEGORY_START},
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  retention_priority INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS round (
  id TEXT PRIMARY KEY,
  match_id TEXT NOT NULL,
  round_number INTEGER NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  FOREIGN KEY(match_id) REFERENCES match(id)
);

CREATE TABLE IF NOT EXISTS score_event (
  id TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL UNIQUE,
  session_id TEXT NOT NULL,
  station_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  judge_name TEXT NOT NULL,
  match_id TEXT NOT NULL,
  round_number INTEGER NOT NULL,
  athlete_side TEXT NOT NULL,
  score_target TEXT NOT NULL DEFAULT 'TECHNIQUE',
  score_delta REAL NOT NULL,
  score_before REAL NOT NULL,
  score_after REAL NOT NULL,
  occurred_at TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  sync_status TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  last_attempt_at TEXT,
  server_ack_at TEXT,
  FOREIGN KEY(match_id) REFERENCES match(id)
);

CREATE INDEX IF NOT EXISTS idx_score_event_match_sequence ON score_event(match_id, sequence);
CREATE INDEX IF NOT EXISTS idx_score_event_sync ON score_event(sync_status, occurred_at);

CREATE TABLE IF NOT EXISTS finalization_event (
  id TEXT PRIMARY KEY,
  match_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  station_id TEXT NOT NULL,
  checksum TEXT NOT NULL,
  payload_snapshot TEXT NOT NULL,
  created_at TEXT NOT NULL,
  sync_status TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  last_attempt_at TEXT,
  server_ack_at TEXT,
  FOREIGN KEY(match_id) REFERENCES match(id)
);

CREATE INDEX IF NOT EXISTS idx_finalization_sync ON finalization_event(sync_status, created_at);

CREATE TABLE IF NOT EXISTS inbound_server_event_log (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  dedupe_key TEXT NOT NULL UNIQUE,
  payload TEXT NOT NULL,
  received_at TEXT NOT NULL,
  processed_at TEXT
);
`;

export async function runMigrations() {
  const db = await getDb();
  await db.execAsync(SCHEMA_SQL);
  try {
    await db.execAsync('ALTER TABLE match ADD COLUMN updated_at TEXT');
  } catch {
    // Column may already exist.
  }
  try {
    await db.execAsync(`ALTER TABLE match ADD COLUMN presentation_category_start_score REAL NOT NULL DEFAULT ${DEFAULT_PRESENTATION_CATEGORY_START}`);
  } catch {
    // Column may already exist.
  }
  try {
    await db.execAsync(`ALTER TABLE app_settings ADD COLUMN presentation_category_start_score REAL NOT NULL DEFAULT ${DEFAULT_PRESENTATION_CATEGORY_START}`);
  } catch {
    // Column may already exist.
  }
  try {
    await db.execAsync(`ALTER TABLE app_settings ADD COLUMN default_station_id TEXT NOT NULL DEFAULT '${DEFAULT_STATION_ID}'`);
  } catch {
    // Column may already exist.
  }
  try {
    await db.execAsync(`ALTER TABLE score_event ADD COLUMN score_target TEXT NOT NULL DEFAULT 'TECHNIQUE'`);
  } catch {
    // Column may already exist.
  }
  try {
    await db.execAsync(`ALTER TABLE app_settings ADD COLUMN preferred_red_side TEXT NOT NULL DEFAULT 'LEFT'`);
  } catch {
    // Column may already exist.
  }
  try {
    await db.execAsync(`ALTER TABLE app_settings ADD COLUMN server_has_active_match INTEGER NOT NULL DEFAULT 0`);
  } catch {
    // Column may already exist.
  }
  try {
    await db.execAsync(`ALTER TABLE app_settings ADD COLUMN server_active_match_id TEXT`);
  } catch {
    // Column may already exist.
  }
  try {
    await db.execAsync(`ALTER TABLE app_settings ADD COLUMN server_competitor_red_name TEXT`);
  } catch {
    // Column may already exist.
  }
  try {
    await db.execAsync(`ALTER TABLE app_settings ADD COLUMN server_competitor_blue_name TEXT`);
  } catch {
    // Column may already exist.
  }
  try {
    await db.execAsync(`ALTER TABLE app_settings ADD COLUMN server_match_updated_at TEXT`);
  } catch {
    // Column may already exist.
  }

  const now = new Date().toISOString();
  await db.runAsync(
    `INSERT OR IGNORE INTO app_settings (
      id, judge_name, action_value_1, action_value_2, default_station_id, default_rounds, presentation_category_start_score, default_starting_score, retained_matches_count, created_at, updated_at
    ) VALUES (1, '', ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      DEFAULT_ACTION_VALUE_1,
      DEFAULT_ACTION_VALUE_2,
      DEFAULT_STATION_ID,
      DEFAULT_ROUNDS,
      DEFAULT_PRESENTATION_CATEGORY_START,
      DEFAULT_STARTING_SCORE,
      DEFAULT_RETAINED_MATCHES,
      now,
      now
    ]
  );
}
