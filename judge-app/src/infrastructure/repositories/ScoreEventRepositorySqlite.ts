import type { IScoreEventRepository } from '@/application/ports/repositories';
import type { ScoreEvent } from '@/domain/models/entities';
import { getDb } from '@/infrastructure/db/client';
import { nowIso } from '@/utils/time';

export class ScoreEventRepositorySqlite implements IScoreEventRepository {
  async appendScoreEvent(event: ScoreEvent): Promise<void> {
    const db = await getDb();
    await db.runAsync(
      `INSERT INTO score_event (
        id, idempotency_key, session_id, station_id, device_id, judge_name, match_id, round_number,
        athlete_side, score_target, score_delta, score_before, score_after, occurred_at, sequence, sync_status,
        retry_count, last_error, last_attempt_at, server_ack_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        event.id,
        event.idempotencyKey,
        event.sessionId,
        event.stationId,
        event.deviceId,
        event.judgeName,
        event.matchId,
        event.roundNumber,
        event.athleteSide,
        event.scoreTarget,
        event.scoreDelta,
        event.scoreBefore,
        event.scoreAfter,
        event.occurredAt,
        event.sequence,
        event.syncStatus,
        event.retryCount,
        event.lastError ?? null,
        null,
        event.serverAckAt ?? null
      ]
    );
  }

  async listMatchEvents(matchId: string): Promise<ScoreEvent[]> {
    const db = await getDb();
    const rows = await db.getAllAsync<any>('SELECT * FROM score_event WHERE match_id = ? ORDER BY sequence ASC', [matchId]);
    return rows.map(mapScoreEvent);
  }

  async listPendingEvents(limit: number): Promise<ScoreEvent[]> {
    const db = await getDb();
    const rows = await db.getAllAsync<any>(
      `SELECT * FROM score_event
       WHERE sync_status IN ('pending', 'failed', 'syncing')
         AND station_id <> 'local-offline'
         AND session_id NOT LIKE 'local-%'
         AND match_id NOT LIKE 'local-%'
       ORDER BY occurred_at ASC
       LIMIT ?`,
      [limit]
    );
    return rows.map(mapScoreEvent);
  }

  async markEventAck(eventId: string, ackAt: string): Promise<void> {
    const db = await getDb();
    await db.runAsync(
      `UPDATE score_event
       SET sync_status = 'acknowledged', server_ack_at = ?, last_error = NULL
       WHERE id = ?`,
      [ackAt, eventId]
    );
  }

  async markEventFailed(eventId: string, error: string): Promise<void> {
    const db = await getDb();
    await db.runAsync(
      `UPDATE score_event
       SET sync_status = 'failed', retry_count = retry_count + 1, last_error = ?, last_attempt_at = ?
       WHERE id = ?`,
      [error, nowIso(), eventId]
    );
  }

  async markEventRejected(eventId: string, error: string): Promise<void> {
    const db = await getDb();
    await db.runAsync(
      `UPDATE score_event
       SET sync_status = 'rejected', retry_count = retry_count + 1, last_error = ?, last_attempt_at = ?
       WHERE id = ?`,
      [error, nowIso(), eventId]
    );
  }

  async markEventSyncing(eventId: string): Promise<void> {
    const db = await getDb();
    await db.runAsync(
      `UPDATE score_event
       SET sync_status = 'syncing', last_attempt_at = ?
       WHERE id = ?`,
      [nowIso(), eventId]
    );
  }

  // Events are never deleted by the judge's own corrections (they add compensating events), so MAX + 1 never
  // reuses a sequence the server holds. Only a server-side reset deletes events, the same ones on both sides.
  async getNextSequence(matchId: string): Promise<number> {
    const db = await getDb();
    const row = await db.getFirstAsync<any>('SELECT MAX(sequence) AS maxSequence FROM score_event WHERE match_id = ?', [matchId]);
    return (row?.maxSequence ?? 0) + 1;
  }

  async resetCurrentRound(matchId: string, roundNumber: number): Promise<void> {
    const db = await getDb();
    await db.runAsync('DELETE FROM score_event WHERE match_id = ? AND round_number = ?', [matchId, roundNumber]);
  }
}

function mapScoreEvent(row: any): ScoreEvent {
  return {
    id: row.id,
    idempotencyKey: row.idempotency_key,
    sessionId: row.session_id,
    stationId: row.station_id,
    deviceId: row.device_id,
    judgeName: row.judge_name,
    matchId: row.match_id,
    roundNumber: row.round_number,
    athleteSide: row.athlete_side,
    scoreTarget: row.score_target ?? 'TECHNIQUE',
    scoreDelta: row.score_delta,
    scoreBefore: row.score_before,
    scoreAfter: row.score_after,
    occurredAt: row.occurred_at,
    sequence: row.sequence,
    syncStatus: row.sync_status,
    retryCount: row.retry_count,
    lastError: row.last_error,
    lastAttemptAt: row.last_attempt_at,
    serverAckAt: row.server_ack_at
  };
}
