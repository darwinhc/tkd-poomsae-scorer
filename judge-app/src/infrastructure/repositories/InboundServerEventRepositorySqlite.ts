import type { IInboundServerEventRepository } from '@/application/ports/repositories';
import type { InboundServerEventLog } from '@/domain/models/entities';
import { getDb } from '@/infrastructure/db/client';

export class InboundServerEventRepositorySqlite implements IInboundServerEventRepository {
  async hasDedupeKey(dedupeKey: string): Promise<boolean> {
    const db = await getDb();
    const row = await db.getFirstAsync<any>('SELECT 1 FROM inbound_server_event_log WHERE dedupe_key = ? LIMIT 1', [dedupeKey]);
    return Boolean(row);
  }

  async appendLog(log: InboundServerEventLog): Promise<void> {
    const db = await getDb();
    await db.runAsync(
      `INSERT OR IGNORE INTO inbound_server_event_log (
        id, event_type, dedupe_key, payload, received_at, processed_at
      ) VALUES (?, ?, ?, ?, ?, ?)`,
      [log.id, log.eventType, log.dedupeKey, log.payload, log.receivedAt, log.processedAt ?? null]
    );
  }
}
