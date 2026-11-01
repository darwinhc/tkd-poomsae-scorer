import type { RealtimeEvent } from '@/domain/models/contracts';

export interface RealtimeApplyResult {
  shouldPersist: boolean;
  dedupeKey: string;
  action:
    | { type: 'none' }
    | { type: 'reset_match'; matchId: string; reason?: string }
    | { type: 'reset_round'; matchId: string; roundNumber?: number }
    | { type: 'competitors_by_color'; matchId: string; redName?: string; blueName?: string }
    | { type: 'active_match_state'; hasActiveMatch: boolean; matchId?: string; redName?: string; blueName?: string }
    | {
        type: 'judge_settings_updated';
        defaultRounds?: number;
        defaultStartingScore?: number;
        presentationCategoryStartScore?: number;
        actionValue1?: number;
        actionValue2?: number;
      }
    | { type: 'round_changed'; matchId: string; round: number }
    | { type: 'session_revoked'; targetSessionId?: string }
    | { type: 'judge_kicked'; targetSessionId?: string }
    | { type: 'station_disconnected'; targetSessionId?: string }
    | { type: 'server_notice'; message?: string }
    | { type: 'ping' }
    | { type: 'pong' };
}

export function mapRealtimeEvent(event: RealtimeEvent): RealtimeApplyResult {
  const payload = asRecord(event.payload);
  const match = asRecord(payload.match);
  const competitors = asRecord(payload.competitors);
  const matchId = pickRealtimeMatchId(payload, match) ?? 'unknown';
  const payloadKey = JSON.stringify(payload);

  switch (event.type) {
    case 'reset_match':
      return {
        shouldPersist: true,
        dedupeKey: `${event.type}:${matchId}:${payloadKey}`,
        action: {
          type: 'reset_match',
          matchId,
          reason: typeof event.payload.reason === 'string' ? event.payload.reason : undefined
        }
      };
    case 'reset_round':
      return {
        shouldPersist: true,
        dedupeKey: `${event.type}:${matchId}:${payloadKey}`,
        // The server names the round it reset; delete that round's events, not the device's current one.
        action: {
          type: 'reset_round',
          matchId,
          roundNumber: pickNumber(payload.round, payload.roundNumber, payload.round_number)
        }
      };
    case 'new_competitors': {
      // Preferred contract: names by athlete color.
      // Backward compatible fallback for older left/right payloads.
      // Missing names stay undefined; the application layer applies localized defaults.
      const redName = pickRedName(payload, competitors, match);
      const blueName = pickBlueName(payload, competitors, match);
      return {
        shouldPersist: true,
        dedupeKey: `${event.type}:${matchId}:${redName ?? ''}:${blueName ?? ''}`,
        action: { type: 'competitors_by_color', matchId, redName, blueName }
      };
    }
    case 'active_match_state': {
      const hasActiveMatch = pickHasActiveMatch(payload, match, false);
      const activeMatchId = pickRealtimeMatchId(payload, match);
      const redName = pickRedName(payload, competitors, match);
      const blueName = pickBlueName(payload, competitors, match);
      return {
        shouldPersist: true,
        dedupeKey: `${event.type}:${hasActiveMatch ? activeMatchId || 'unknown' : 'none'}:${redName || ''}:${blueName || ''}`,
        action: {
          type: 'active_match_state',
          hasActiveMatch,
          matchId: activeMatchId,
          redName,
          blueName
        }
      };
    }
    case 'match_updated': {
      const active = pickHasActiveMatch(payload, match, true);
      const redName = pickRedName(payload, competitors, match);
      const blueName = pickBlueName(payload, competitors, match);
      const activeMatchId = pickRealtimeMatchId(payload, match);
      return {
        shouldPersist: true,
        dedupeKey: `${event.type}:${active ? activeMatchId || 'unknown' : 'none'}:${redName || ''}:${blueName || ''}`,
        action: {
          type: 'active_match_state',
          hasActiveMatch: active,
          matchId: activeMatchId,
          redName,
          blueName
        }
      };
    }
    case 'judge_settings_updated': {
      const defaultRounds = pickNumber(payload.defaultRounds, payload.default_rounds, payload.totalRounds, payload.total_rounds);
      const defaultStartingScore = pickNumber(payload.defaultStartingScore, payload.default_starting_score);
      const presentationCategoryStartScore = pickNumber(
        payload.presentationCategoryStartScore,
        payload.presentation_category_start_score
      );
      const actionValue1 = pickNumber(payload.actionValue1, payload.action_value_1);
      const actionValue2 = pickNumber(payload.actionValue2, payload.action_value_2);
      return {
        shouldPersist: true,
        dedupeKey: `${event.type}:${payloadKey}`,
        action: {
          type: 'judge_settings_updated',
          defaultRounds,
          defaultStartingScore,
          presentationCategoryStartScore,
          actionValue1,
          actionValue2
        }
      };
    }
    case 'round_changed': {
      const round = pickNumber(payload.currentRound, payload.current_round, payload.roundNumber, payload.round, payload.round_number) ?? 1;
      return {
        shouldPersist: true,
        dedupeKey: `${event.type}:${matchId}:${round}`,
        action: { type: 'round_changed', matchId, round }
      };
    }
    case 'session_revoked':
    case 'judge_kicked':
    case 'station_disconnected': {
      // The server broadcasts these to the whole station and names the affected session;
      // the dedupe key includes it so a later session on this device is not ignored.
      const targetSessionId = pickString(payload.sessionId, payload.session_id) || undefined;
      const issuedAt = pickString(payload.issuedAt, payload.issued_at) ?? '';
      return {
        shouldPersist: true,
        dedupeKey: `${event.type}:${targetSessionId ?? pickString(payload.stationId, payload.station_id, 'station')}:${issuedAt}`,
        action: { type: event.type, targetSessionId }
      };
    }
    case 'server_notice':
      return {
        shouldPersist: true,
        dedupeKey: `${event.type}:${Date.now()}`,
        action: {
          type: 'server_notice',
          message: typeof event.payload.message === 'string' ? event.payload.message : undefined
        }
      };
    case 'ping':
      return {
        shouldPersist: false,
        dedupeKey: `${event.type}:${Date.now()}`,
        action: { type: 'ping' }
      };
    case 'pong':
      // Answer to a keep-alive: nothing to do and never answered (answering would loop).
      return {
        shouldPersist: false,
        dedupeKey: `${event.type}:${Date.now()}`,
        action: { type: 'pong' }
      };
    default:
      return { shouldPersist: false, dedupeKey: `${event.type}:${Date.now()}`, action: { type: 'none' } };
  }
}

function asRecord(input: unknown): Record<string, unknown> {
  if (input && typeof input === 'object' && !Array.isArray(input)) {
    return input as Record<string, unknown>;
  }
  return {};
}

function pickRealtimeMatchId(payload: Record<string, unknown>, match: Record<string, unknown>): string | undefined {
  return pickString(payload.matchId, payload.match_id, payload.activeMatchId, payload.active_match_id, match?.id, match?.matchId, match?.match_id);
}

function pickRedName(
  payload: Record<string, unknown>,
  competitors: Record<string, unknown>,
  match: Record<string, unknown>
): string | undefined {
  return pickString(
    payload.competitorRedName,
    payload.competitor_red_name,
    payload.redName,
    payload.red_name,
    payload.red,
    competitors?.competitorRedName,
    competitors?.competitor_red_name,
    competitors?.redName,
    competitors?.red_name,
    competitors?.red,
    match?.competitorRedName,
    match?.competitor_red_name,
    match?.redName,
    match?.red_name,
    match?.red,
    payload.competitorLeftName,
    payload.competitor_left_name,
    competitors?.competitorLeftName,
    competitors?.competitor_left_name,
    match?.competitorLeftName,
    match?.competitor_left_name
  );
}

function pickBlueName(
  payload: Record<string, unknown>,
  competitors: Record<string, unknown>,
  match: Record<string, unknown>
): string | undefined {
  return pickString(
    payload.competitorBlueName,
    payload.competitor_blue_name,
    payload.blueName,
    payload.blue_name,
    payload.blue,
    competitors?.competitorBlueName,
    competitors?.competitor_blue_name,
    competitors?.blueName,
    competitors?.blue_name,
    competitors?.blue,
    match?.competitorBlueName,
    match?.competitor_blue_name,
    match?.blueName,
    match?.blue_name,
    match?.blue,
    payload.competitorRightName,
    payload.competitor_right_name,
    competitors?.competitorRightName,
    competitors?.competitor_right_name,
    match?.competitorRightName,
    match?.competitor_right_name
  );
}

function pickHasActiveMatch(payload: Record<string, unknown>, match: Record<string, unknown>, fallback: boolean): boolean {
  return (
    pickBoolean(
      payload.hasActiveMatch,
      payload.has_active_match,
      payload.active,
      payload.isActive,
      payload.is_active,
      match?.hasActiveMatch,
      match?.has_active_match,
      match?.active,
      match?.isActive,
      match?.is_active
    ) ??
    statusToActive(payload.status ?? payload.state ?? match?.status ?? match?.state) ??
    fallback
  );
}

function pickString(...values: unknown[]): string | undefined {
  for (const value of values) {
    if (typeof value === 'string') {
      const trimmed = value.trim();
      if (trimmed.length > 0) {
        return trimmed;
      }
    }
  }
  return undefined;
}

function pickBoolean(...values: unknown[]): boolean | undefined {
  for (const value of values) {
    if (typeof value === 'boolean') {
      return value;
    }
    if (typeof value === 'number') {
      if (value === 1) return true;
      if (value === 0) return false;
    }
    if (typeof value === 'string') {
      const normalized = value.trim().toLowerCase();
      if (['true', '1', 'yes', 'active', 'started', 'running', 'in_progress'].includes(normalized)) return true;
      if (['false', '0', 'no', 'inactive', 'finished', 'ended', 'closed'].includes(normalized)) return false;
    }
  }
  return undefined;
}

function statusToActive(status: unknown): boolean | undefined {
  if (typeof status !== 'string') return undefined;
  const normalized = status.trim().toLowerCase();
  if (['active', 'started', 'running', 'in_progress', 'open'].includes(normalized)) return true;
  if (['inactive', 'finished', 'ended', 'closed', 'completed'].includes(normalized)) return false;
  return undefined;
}

function pickNumber(...values: unknown[]): number | undefined {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === 'string') {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }
  return undefined;
}
