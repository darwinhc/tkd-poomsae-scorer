import type { IMatchRepository } from '@/application/ports/repositories';
import type { AthleteSide, Match } from '@/domain/models/entities';
import { getDb } from '@/infrastructure/db/client';
import { createId } from '@/utils/id';
import { nowIso } from '@/utils/time';

export class MatchRepositorySqlite implements IMatchRepository {
  async createMatch(input: {
    matchId?: string;
    competitorLeftName: string;
    competitorRightName: string;
    leftSideColor?: AthleteSide;
    rightSideColor?: AthleteSide;
    totalRounds: number;
    startingScore: number;
    presentationCategoryStartScore: number;
  }): Promise<Match> {
    const db = await getDb();
    const requestedId = typeof input.matchId === 'string' ? input.matchId.trim() : '';
    const id = requestedId || createId();
    const now = nowIso();
    const retentionPriority = Date.now();
    const leftSideColor = input.leftSideColor ?? 'RED';
    const rightSideColor = input.rightSideColor ?? 'BLUE';

    await db.runAsync(
      `INSERT INTO match (
        id, competitor_left_name, competitor_right_name, left_side_color, right_side_color,
        total_rounds, current_round, starting_score, presentation_category_start_score, status, created_at, updated_at, started_at, finished_at, retention_priority
      ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, 'active', ?, ?, ?, NULL, ?)`,
      [
        id,
        input.competitorLeftName,
        input.competitorRightName,
        leftSideColor,
        rightSideColor,
        input.totalRounds,
        input.startingScore,
        input.presentationCategoryStartScore,
        now,
        now,
        now,
        retentionPriority
      ]
    );

    for (let round = 1; round <= input.totalRounds; round += 1) {
      await db.runAsync(
        `INSERT INTO round (id, match_id, round_number, status, started_at, ended_at)
         VALUES (?, ?, ?, ?, ?, ?)`,
        [createId(), id, round, round === 1 ? 'active' : 'pending', now, null]
      );
    }

    return {
      id,
      competitorLeftName: input.competitorLeftName,
      competitorRightName: input.competitorRightName,
      leftSideColor,
      rightSideColor,
      totalRounds: input.totalRounds,
      currentRound: 1,
      startingScore: input.startingScore,
      presentationCategoryStartScore: input.presentationCategoryStartScore,
      status: 'active',
      createdAt: now,
      startedAt: now,
      finishedAt: null,
      retentionPriority
    };
  }

  async getActiveMatch(): Promise<Match | null> {
    const db = await getDb();
    const row = await db.getFirstAsync<any>("SELECT * FROM match WHERE status = 'active' ORDER BY created_at DESC LIMIT 1");
    return row ? mapMatch(row) : null;
  }

  async getMatchById(matchId: string): Promise<Match | null> {
    const db = await getDb();
    const row = await db.getFirstAsync<any>('SELECT * FROM match WHERE id = ?', [matchId]);
    return row ? mapMatch(row) : null;
  }

  async listAllMatches(): Promise<Match[]> {
    const db = await getDb();
    const rows = await db.getAllAsync<any>('SELECT * FROM match ORDER BY created_at DESC');
    return rows.map(mapMatch);
  }

  async listRetainedMatches(limit: number): Promise<Match[]> {
    const db = await getDb();
    const rows = await db.getAllAsync<any>('SELECT * FROM match ORDER BY created_at DESC LIMIT ?', [limit]);
    return rows.map(mapMatch);
  }

  async updateCompetitors(matchId: string, left: string, right: string): Promise<void> {
    const db = await getDb();
    await db.runAsync(
      `UPDATE match SET competitor_left_name = ?, competitor_right_name = ?, updated_at = ? WHERE id = ?`,
      [left, right, nowIso(), matchId]
    );
  }

  async moveToRound(matchId: string, roundNumber: number): Promise<void> {
    const db = await getDb();
    const now = nowIso();

    await db.runAsync('UPDATE round SET status = ?, ended_at = ? WHERE match_id = ? AND status = ?', ['completed', now, matchId, 'active']);
    await db.runAsync('UPDATE round SET status = ?, started_at = ?, ended_at = NULL WHERE match_id = ? AND round_number = ?', [
      'active',
      now,
      matchId,
      roundNumber
    ]);
    await db.runAsync('UPDATE match SET current_round = ? WHERE id = ?', [roundNumber, matchId]);
    await db.runAsync('UPDATE match SET updated_at = ? WHERE id = ?', [now, matchId]);
  }

  async finishLocally(matchId: string, status: Match['status']): Promise<void> {
    const db = await getDb();
    const now = nowIso();
    await db.runAsync('UPDATE match SET status = ?, finished_at = ?, updated_at = ? WHERE id = ?', [status, now, now, matchId]);
    await db.runAsync('UPDATE round SET status = ?, ended_at = ? WHERE match_id = ? AND status = ?', ['completed', now, matchId, 'active']);
  }

  async markFinalizedAck(matchId: string): Promise<void> {
    const db = await getDb();
    await db.runAsync("UPDATE match SET status = 'finalized_acknowledged' WHERE id = ?", [matchId]);
    await db.runAsync('UPDATE match SET updated_at = ? WHERE id = ?', [nowIso(), matchId]);
  }

  async resetMatch(matchId: string): Promise<void> {
    const db = await getDb();
    const now = nowIso();
    await db.runAsync('DELETE FROM score_event WHERE match_id = ?', [matchId]);
    await db.runAsync('UPDATE match SET current_round = 1, status = ?, finished_at = NULL WHERE id = ?', ['active', matchId]);
    await db.runAsync('UPDATE match SET updated_at = ? WHERE id = ?', [now, matchId]);
    await db.runAsync('UPDATE round SET status = ?, ended_at = ? WHERE match_id = ?', ['pending', null, matchId]);
    await db.runAsync('UPDATE round SET status = ?, ended_at = NULL, started_at = ? WHERE match_id = ? AND round_number = 1', [
      'active',
      now,
      matchId
    ]);
  }

  async deleteMatches(matchIds: string[]): Promise<void> {
    if (!matchIds.length) {
      return;
    }

    const db = await getDb();
    for (const id of matchIds) {
      await db.runAsync('DELETE FROM finalization_event WHERE match_id = ?', [id]);
      await db.runAsync('DELETE FROM score_event WHERE match_id = ?', [id]);
      await db.runAsync('DELETE FROM round WHERE match_id = ?', [id]);
      await db.runAsync('DELETE FROM match WHERE id = ?', [id]);
    }
  }
}

function mapMatch(row: any): Match {
  return {
    id: row.id,
    competitorLeftName: row.competitor_left_name,
    competitorRightName: row.competitor_right_name,
    leftSideColor: row.left_side_color,
    rightSideColor: row.right_side_color,
    totalRounds: row.total_rounds,
    currentRound: row.current_round,
    startingScore: row.starting_score,
    presentationCategoryStartScore: row.presentation_category_start_score,
    status: row.status,
    createdAt: row.created_at,
    startedAt: row.started_at,
    finishedAt: row.finished_at,
    retentionPriority: row.retention_priority
  };
}
