import type {
  IConnectionRepository,
  IFinalizationRepository,
  IHistoryRepository,
  IMatchRepository,
  ISessionRepository
} from '@/application/ports/repositories';
import type { FinalizePayload } from '@/domain/models/contracts';
import { buildFinalizeChecksumPayload, buildSha256Checksum } from '@/domain/services/checksum';
import { isLocalOnlyMatchId, isLocalSession } from '@/domain/services/localMode';
import { addScores2, judgeFinalScore } from '@/domain/services/matchAggregation';
import { LocalizedError } from '@/i18n/LocalizedError';
import { createId } from '@/utils/id';
import { nowIso } from '@/utils/time';

export class FinalizationService {
  constructor(
    private readonly matchRepo: IMatchRepository,
    private readonly historyRepo: IHistoryRepository,
    private readonly finalizationRepo: IFinalizationRepository,
    private readonly sessionRepo: ISessionRepository,
    private readonly connectionRepo: IConnectionRepository
  ) {}

  async finalizeActiveMatch() {
    const [match, session, backend, accessToken] = await Promise.all([
      this.matchRepo.getActiveMatch(),
      this.sessionRepo.getSession(),
      this.connectionRepo.getActiveBackend(),
      this.sessionRepo.getAccessToken()
    ]);

    if (!match) {
      throw new LocalizedError('errors.noActiveMatch');
    }

    if (!session) {
      throw new LocalizedError('errors.sessionRequiredToFinalize');
    }

    const summary = await this.historyRepo.getSummary(match.id);
    if (!summary) {
      throw new LocalizedError('errors.summaryBuildFailed');
    }

    const finishedAt = nowIso();
    const finalSequence = summary.timeline.at(-1)?.sequence ?? 0;
    // Same rounds as the summary averages: rounds not reached yet (pending) are not part of the scorecard.
    const scoredRounds = summary.rounds.filter((round) => round.status !== 'pending');
    const finalScoreRed = judgeFinalScore(scoredRounds, 'red');
    const finalScoreBlue = judgeFinalScore(scoredRounds, 'blue');
    const roundsSummary = scoredRounds.map((round) => ({
      roundNumber: round.roundNumber,
      techniqueRed: round.technique.red,
      presentationRed: round.presentationTotal.red,
      techniqueBlue: round.technique.blue,
      presentationBlue: round.presentationTotal.blue,
      red: addScores2(round.technique.red, round.presentationTotal.red),
      blue: addScores2(round.technique.blue, round.presentationTotal.blue),
      negativeRed: round.totalNegative.red,
      negativeBlue: round.totalNegative.blue,
      positiveRed: round.totalPositive.red,
      positiveBlue: round.totalPositive.blue
    }));

    const checksum = await buildSha256Checksum(
      buildFinalizeChecksumPayload({
        matchId: match.id,
        sessionId: session.sessionId,
        stationId: session.stationId,
        judgeName: session.judgeName,
        totalEvents: summary.timeline.length,
        lastSequence: finalSequence,
        finalScoreRed,
        finalScoreBlue,
        rounds: roundsSummary
      })
    );

    const payload: FinalizePayload = {
      sessionId: session.sessionId,
      stationId: session.stationId,
      matchId: match.id,
      judgeName: session.judgeName,
      competitorLeftName: match.competitorLeftName,
      competitorRightName: match.competitorRightName,
      totalRounds: match.totalRounds,
      finalRound: match.currentRound,
      finalScoreRed,
      finalScoreBlue,
      totalEvents: summary.timeline.length,
      finalSequence,
      startedAt: match.startedAt,
      finishedAt,
      checksum,
      roundsSummary
    };

    const canSyncToBackend = Boolean(
      backend &&
      accessToken &&
      !isLocalSession(session) &&
      !isLocalOnlyMatchId(match.id)
    );
    if (!canSyncToBackend) {
      await this.matchRepo.finishLocally(match.id, 'finished_locally');
      return {
        payload,
        backendBaseUrl: backend?.baseUrl ?? null,
        mode: 'offline_local' as const
      };
    }

    await this.finalizationRepo.saveFinalization({
      id: createId(),
      matchId: match.id,
      sessionId: session.sessionId,
      stationId: session.stationId,
      checksum,
      payloadSnapshot: JSON.stringify(payload),
      createdAt: finishedAt,
      syncStatus: 'pending',
      retryCount: 0,
      lastError: null,
      lastAttemptAt: null,
      serverAckAt: null
    });

    await this.matchRepo.finishLocally(match.id, 'finished_locally_pending_finalize_ack');

    return {
      payload,
      backendBaseUrl: backend?.baseUrl ?? null,
      mode: 'pending_remote_ack' as const
    };
  }
}
