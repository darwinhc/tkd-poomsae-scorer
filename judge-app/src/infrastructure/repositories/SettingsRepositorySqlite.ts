import type { ISettingsRepository } from '@/application/ports/repositories';
import {
  DEFAULT_ACTION_VALUE_1,
  DEFAULT_ACTION_VALUE_2,
  DEFAULT_PRESENTATION_CATEGORY_START,
  DEFAULT_PREFERRED_RED_SIDE,
  DEFAULT_RETAINED_MATCHES,
  DEFAULT_ROUNDS,
  DEFAULT_STATION_ID,
  DEFAULT_STARTING_SCORE
} from '@/constants/defaults';
import type { AppSettings } from '@/domain/models/entities';
import { getDb } from '@/infrastructure/db/client';
import { nowIso } from '@/utils/time';

export class SettingsRepositorySqlite implements ISettingsRepository {
  async getSettings(): Promise<AppSettings> {
    const db = await getDb();
    const row = await db.getFirstAsync<any>('SELECT * FROM app_settings WHERE id = 1');
    if (!row) {
      const created = nowIso();
      return {
        id: 1,
        judgeName: '',
        preferredRedSide: DEFAULT_PREFERRED_RED_SIDE,
        serverHasActiveMatch: false,
        serverActiveMatchId: null,
        serverCompetitorRedName: null,
        serverCompetitorBlueName: null,
        serverMatchUpdatedAt: null,
        actionValue1: DEFAULT_ACTION_VALUE_1,
        actionValue2: DEFAULT_ACTION_VALUE_2,
        defaultStationId: DEFAULT_STATION_ID,
        defaultRounds: DEFAULT_ROUNDS,
        presentationCategoryStartScore: DEFAULT_PRESENTATION_CATEGORY_START,
        defaultStartingScore: DEFAULT_STARTING_SCORE,
        retainedMatchesCount: DEFAULT_RETAINED_MATCHES,
        createdAt: created,
        updatedAt: created
      };
    }

    return mapSettings(row);
  }

  async upsertSettings(input: Partial<AppSettings>): Promise<AppSettings> {
    const db = await getDb();
    const current = await this.getSettings();
    const merged = {
      ...current,
      ...input,
      updatedAt: nowIso()
    };

    await db.runAsync(
      `UPDATE app_settings
      SET judge_name = ?, server_has_active_match = ?, server_active_match_id = ?, server_competitor_red_name = ?, server_competitor_blue_name = ?, server_match_updated_at = ?,
          action_value_1 = ?, action_value_2 = ?, remote_base_url = ?, bootstrap_token = ?,
          default_station_id = ?, default_rounds = ?, presentation_category_start_score = ?, default_starting_score = ?, retained_matches_count = ?,
          preferred_red_side = ?, updated_at = ?
      WHERE id = 1`,
      [
        merged.judgeName,
        merged.serverHasActiveMatch ? 1 : 0,
        merged.serverActiveMatchId ?? null,
        merged.serverCompetitorRedName ?? null,
        merged.serverCompetitorBlueName ?? null,
        merged.serverMatchUpdatedAt ?? null,
        merged.actionValue1,
        merged.actionValue2,
        merged.remoteBaseUrl ?? null,
        merged.bootstrapToken ?? null,
        merged.defaultStationId,
        merged.defaultRounds,
        merged.presentationCategoryStartScore,
        merged.defaultStartingScore,
        merged.retainedMatchesCount,
        merged.preferredRedSide ?? DEFAULT_PREFERRED_RED_SIDE,
        merged.updatedAt
      ]
    );

    return merged;
  }
}

function mapSettings(row: any): AppSettings {
  return {
    id: 1,
    judgeName: row.judge_name,
    preferredRedSide: row.preferred_red_side ?? DEFAULT_PREFERRED_RED_SIDE,
    serverHasActiveMatch: Boolean(row.server_has_active_match),
    serverActiveMatchId: row.server_active_match_id ?? null,
    serverCompetitorRedName: row.server_competitor_red_name ?? null,
    serverCompetitorBlueName: row.server_competitor_blue_name ?? null,
    serverMatchUpdatedAt: row.server_match_updated_at ?? null,
    actionValue1: row.action_value_1,
    actionValue2: row.action_value_2,
    remoteBaseUrl: row.remote_base_url,
    bootstrapToken: row.bootstrap_token,
    defaultStationId: row.default_station_id ?? DEFAULT_STATION_ID,
    defaultRounds: row.default_rounds,
    presentationCategoryStartScore: row.presentation_category_start_score ?? DEFAULT_PRESENTATION_CATEGORY_START,
    defaultStartingScore: row.default_starting_score,
    retainedMatchesCount: row.retained_matches_count,
    createdAt: row.created_at,
    updatedAt: row.updated_at
  };
}
