import type { IHistoryRepository } from '@/application/ports/repositories';
import type { MatchSummary, ScoreEvent } from '@/domain/models/entities';
import { aggregateMatchTotals } from '@/domain/services/matchAggregation';
import { calculatePresentationFromEvents, calculateTechniqueFromEvents, classifyTotals } from '@/domain/services/scoreCalculator';
import { getDb } from '@/infrastructure/db/client';

export class HistoryRepositorySqlite implements IHistoryRepository {
  async getSummary(matchId: string): Promise<MatchSummary | null> {
    const db = await getDb();
    const match = await db.getFirstAsync<any>('SELECT * FROM match WHERE id = ?', [matchId]);
    if (!match) {
      return null;
    }

    const eventsRows = await db.getAllAsync<any>('SELECT * FROM score_event WHERE match_id = ? ORDER BY sequence ASC', [matchId]);
    const events = eventsRows.map(mapEvent);
    const classified = classifyTotals(events);

    const roundsRows = await db.getAllAsync<any>(
      'SELECT round_number, status FROM round WHERE match_id = ? ORDER BY round_number ASC',
      [matchId]
    );
    const rounds = roundsRows.map((r) => {
      const roundEvents = events.filter((e) => e.roundNumber === r.round_number);
      const roundTechnique = calculateTechniqueFromEvents(match.starting_score, roundEvents);
      const roundPresentation = calculatePresentationFromEvents(match.presentation_category_start_score, roundEvents);
      const c = classifyTotals(roundEvents);
      return {
        roundNumber: r.round_number,
        status: r.status,
        technique: roundTechnique,
        presentationTotal: roundPresentation.total,
        presentationByCategory: roundPresentation.byCategory,
        totalNegative: c.totalNegative,
        totalPositive: c.totalPositive,
        eventsCount: roundEvents.length
      };
    });

    const aggregate = aggregateMatchTotals(rounds);

    return {
      matchId,
      technique: aggregate.technique,
      presentationTotal: aggregate.presentationTotal,
      presentationByCategory: aggregate.presentationByCategory,
      totalNegative: classified.totalNegative,
      totalPositive: classified.totalPositive,
      rounds,
      timeline: events.map((event) => ({
        eventId: event.id,
        sequence: event.sequence,
        athleteSide: event.athleteSide,
        scoreTarget: event.scoreTarget,
        scoreDelta: event.scoreDelta,
        roundNumber: event.roundNumber,
        occurredAt: event.occurredAt,
        syncStatus: event.syncStatus
      })),
      finalizationStatus: match.status
    };
  }
}

function mapEvent(row: any): ScoreEvent {
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
