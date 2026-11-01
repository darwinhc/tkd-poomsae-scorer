import type { IFinalizationRepository } from '@/application/ports/repositories';
import type { FinalizationEvent } from '@/domain/models/entities';
import { getDb } from '@/infrastructure/db/client';
import { nowIso } from '@/utils/time';

export class FinalizationRepositorySqlite implements IFinalizationRepository {
  async saveFinalization(event: FinalizationEvent): Promise<void> {
    const db = await getDb();
    await db.runAsync(
      `INSERT INTO finalization_event (
        id, match_id, session_id, station_id, checksum, payload_snapshot,
        created_at, sync_status, retry_count, last_error, last_attempt_at, server_ack_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        event.id,
        event.matchId,
        event.sessionId,
        event.stationId,
        event.checksum,
        event.payloadSnapshot,
        event.createdAt,
        event.syncStatus,
        event.retryCount,
        event.lastError ?? null,
        null,
        event.serverAckAt ?? null
      ]
    );
  }

  async listPendingFinalizations(limit: number): Promise<FinalizationEvent[]> {
    const db = await getDb();
    const rows = await db.getAllAsync<any>(
      `SELECT * FROM finalization_event
       WHERE sync_status IN ('pending', 'failed', 'syncing')
       ORDER BY created_at ASC
       LIMIT ?`,
      [limit]
    );
    return rows.map((row) => ({
      id: row.id,
      matchId: row.match_id,
      sessionId: row.session_id,
      stationId: row.station_id,
      checksum: row.checksum,
      payloadSnapshot: row.payload_snapshot,
      createdAt: row.created_at,
      syncStatus: row.sync_status,
      retryCount: row.retry_count,
      lastError: row.last_error,
      lastAttemptAt: row.last_attempt_at,
      serverAckAt: row.server_ack_at
    }));
  }

  async markFinalizationAck(eventId: string, ackAt: string): Promise<void> {
    const db = await getDb();
    await db.runAsync(
      `UPDATE finalization_event
       SET sync_status = 'acknowledged', server_ack_at = ?, last_error = NULL
       WHERE id = ?`,
      [ackAt, eventId]
    );
  }

  async markFinalizationFailed(eventId: string, error: string): Promise<void> {
    const db = await getDb();
    await db.runAsync(
      `UPDATE finalization_event
       SET sync_status = 'failed', retry_count = retry_count + 1, last_error = ?, last_attempt_at = ?
       WHERE id = ?`,
      [error, nowIso(), eventId]
    );
  }

  async markFinalizationSyncing(eventId: string): Promise<void> {
    const db = await getDb();
    await db.runAsync(
      `UPDATE finalization_event
       SET sync_status = 'syncing', last_attempt_at = ?
       WHERE id = ?`,
      [nowIso(), eventId]
    );
  }
}
