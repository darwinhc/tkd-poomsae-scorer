import type { ISessionRepository } from '@/application/ports/repositories';
import type { OperatorSession } from '@/domain/models/entities';
import { getDb } from '@/infrastructure/db/client';
import { tokenVault } from '@/infrastructure/security/tokenVault';
import { nowIso } from '@/utils/time';

export class SessionRepositorySqlite implements ISessionRepository {
  async saveSession(session: OperatorSession, accessToken?: string | null): Promise<void> {
    const db = await getDb();
    await db.runAsync('UPDATE operator_session SET active = 0');

    await db.runAsync(
      `INSERT OR REPLACE INTO operator_session (
        id, backend_server_id, station_id, station_name, judge_name, device_id, session_id,
        token_expires_at, last_validated_at, connection_status, active, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)`,
      [
        session.id,
        session.backendServerId,
        session.stationId,
        session.stationName,
        session.judgeName,
        session.deviceId,
        session.sessionId,
        session.tokenExpiresAt ?? null,
        session.lastValidatedAt ?? null,
        session.connectionStatus,
        session.createdAt,
        session.updatedAt
      ]
    );

    if (accessToken) {
      await tokenVault.save(accessToken);
    } else {
      await tokenVault.clear();
    }
  }

  async getSession(): Promise<OperatorSession | null> {
    const db = await getDb();
    const row = await db.getFirstAsync<any>('SELECT * FROM operator_session WHERE active = 1 ORDER BY updated_at DESC LIMIT 1');
    if (!row) {
      return null;
    }

    return {
      id: row.id,
      backendServerId: row.backend_server_id,
      stationId: row.station_id,
      stationName: row.station_name,
      judgeName: row.judge_name,
      deviceId: row.device_id,
      sessionId: row.session_id,
      tokenExpiresAt: row.token_expires_at,
      lastValidatedAt: row.last_validated_at,
      connectionStatus: row.connection_status,
      createdAt: row.created_at,
      updatedAt: row.updated_at
    };
  }

  async getAccessToken(): Promise<string | null> {
    return tokenVault.load();
  }

  async clearSession(): Promise<void> {
    const db = await getDb();
    await db.runAsync('UPDATE operator_session SET active = 0, connection_status = ?, updated_at = ?', ['disconnected', nowIso()]);
    await tokenVault.clear();
  }

  async markRevoked(): Promise<void> {
    const db = await getDb();
    await db.runAsync('UPDATE operator_session SET connection_status = ?, updated_at = ? WHERE active = 1', ['revoked', nowIso()]);
  }

  async markDisconnected(): Promise<void> {
    const db = await getDb();
    await db.runAsync('UPDATE operator_session SET connection_status = ?, updated_at = ? WHERE active = 1', ['disconnected', nowIso()]);
  }
}
