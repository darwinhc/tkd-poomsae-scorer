import type { IConnectionRepository } from '@/application/ports/repositories';
import type { QrBootstrapPayload } from '@/domain/models/contracts';
import type { BackendServer, Station } from '@/domain/models/entities';
import { getDb } from '@/infrastructure/db/client';
import { createId } from '@/utils/id';
import { nowIso } from '@/utils/time';

export class ConnectionRepositorySqlite implements IConnectionRepository {
  async saveBackend(payload: QrBootstrapPayload): Promise<BackendServer> {
    const db = await getDb();
    const now = nowIso();
    const existing = await this.getActiveBackend();
    const id = existing?.id ?? createId();

    await db.runAsync('UPDATE backend_server SET active = 0');
    await db.runAsync(
      `INSERT OR REPLACE INTO backend_server (
        id, base_url, bootstrap_token, environment, tournament_id, protocol_version, expires_at, active, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, COALESCE((SELECT created_at FROM backend_server WHERE id = ?), ?), ?)`,
      [
        id,
        payload.baseUrl,
        payload.bootstrapToken ?? null,
        payload.environment ?? null,
        payload.tournamentId ?? null,
        payload.protocolVersion,
        payload.expiresAt,
        id,
        now,
        now
      ]
    );

    return {
      id,
      baseUrl: payload.baseUrl,
      bootstrapToken: payload.bootstrapToken,
      environment: payload.environment,
      tournamentId: payload.tournamentId,
      protocolVersion: payload.protocolVersion,
      expiresAt: payload.expiresAt,
      createdAt: existing?.createdAt ?? now,
      updatedAt: now
    };
  }

  async getActiveBackend(): Promise<BackendServer | null> {
    const db = await getDb();
    const row = await db.getFirstAsync<any>('SELECT * FROM backend_server WHERE active = 1 ORDER BY updated_at DESC LIMIT 1');
    if (!row) {
      return null;
    }

    return {
      id: row.id,
      baseUrl: row.base_url,
      bootstrapToken: row.bootstrap_token,
      environment: row.environment,
      tournamentId: row.tournament_id,
      protocolVersion: row.protocol_version,
      expiresAt: row.expires_at,
      createdAt: row.created_at,
      updatedAt: row.updated_at
    };
  }

  async saveStations(stations: Station[]): Promise<void> {
    const db = await getDb();
    const now = nowIso();
    await db.runAsync(`UPDATE station SET status = 'inactive'`);

    for (const station of stations) {
      await db.runAsync(
        `INSERT OR REPLACE INTO station (id, name, status, updated_at)
         VALUES (?, ?, ?, ?)`,
        [station.id, station.name, station.status, now]
      );
    }
  }

  async listActiveStations(): Promise<Station[]> {
    const db = await getDb();
    const rows = await db.getAllAsync<any>('SELECT * FROM station WHERE status = ? ORDER BY name ASC', ['active']);
    return rows.map((row) => ({
      id: row.id,
      name: row.name,
      status: row.status,
      updatedAt: row.updated_at
    }));
  }
}
