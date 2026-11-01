import { buildFinalizeChecksumPayload, buildSha256Checksum } from '@/domain/services/checksum';
import type {
  IApiClient,
  IConnectionRepository,
  IFinalizationRepository,
  IMatchRepository,
  IScoreEventRepository,
  ISessionRepository
} from '@/application/ports/repositories';
import { isLocalOnlyMatchId, isLocalOnlyScoreEvent } from '@/domain/services/localMode';
import { isRetryEligible, isTerminalSyncError } from '@/domain/services/retryPolicy';

const PENDING_EVENTS_BATCH = 100;
// After this many failed attempts of one event (e.g. rejected because the match was closed by the operator)
// the finalization is sent anyway; the backend then records it as pending reconciliation.
const FINALIZE_HOLD_MAX_EVENT_RETRIES = 5;

export interface SyncCycleStats {
  pendingBefore: number;
  sent: number;
  failed: number;
  // Events the server refused definitively (e.g. 409 match_closed): marked rejected, never retried.
  rejected: number;
  finalizedSent: number;
  finalizedFailed: number;
  lastSyncAt?: string;
}

export class SyncEngine {
  private timer: ReturnType<typeof setInterval> | null = null;

  private running = false;
  private shouldRunAgain = false;
  private runningPromise: Promise<SyncCycleStats> | null = null;

  constructor(
    private readonly scoreRepo: IScoreEventRepository,
    private readonly finalizationRepo: IFinalizationRepository,
    private readonly sessionRepo: ISessionRepository,
    private readonly connectionRepo: IConnectionRepository,
    private readonly matchRepo: IMatchRepository,
    private readonly apiClient: IApiClient
  ) {}

  start(onCycle?: (stats: SyncCycleStats) => void) {
    if (this.timer) {
      return;
    }

    this.timer = setInterval(async () => {
      const stats = await this.triggerSync();
      onCycle?.(stats);
    }, 5000);
  }

  stop() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  async triggerSync(): Promise<SyncCycleStats> {
    if (this.running) {
      this.shouldRunAgain = true;
      return (
        this.runningPromise ?? {
          pendingBefore: 0,
          sent: 0,
          failed: 0,
          rejected: 0,
          finalizedSent: 0,
          finalizedFailed: 0
        }
      );
    }

    this.running = true;
    this.runningPromise = (async () => {
      const aggregate = createEmptyStats();
      do {
        this.shouldRunAgain = false;
        const cycle = await this.runOneCycle();
        aggregate.pendingBefore = Math.max(aggregate.pendingBefore, cycle.pendingBefore);
        aggregate.sent += cycle.sent;
        aggregate.failed += cycle.failed;
        aggregate.rejected += cycle.rejected;
        aggregate.finalizedSent += cycle.finalizedSent;
        aggregate.finalizedFailed += cycle.finalizedFailed;
        aggregate.lastSyncAt = cycle.lastSyncAt ?? aggregate.lastSyncAt;
      } while (this.shouldRunAgain);
      return aggregate;
    })();

    try {
      return await this.runningPromise;
    } finally {
      this.running = false;
      this.runningPromise = null;
    }
  }

  private async runOneCycle(): Promise<SyncCycleStats> {
    const stats = createEmptyStats();
    const [backend, token, session] = await Promise.all([
      this.connectionRepo.getActiveBackend(),
      this.sessionRepo.getAccessToken(),
      this.sessionRepo.getSession()
    ]);
    if (!backend || !token) {
      return stats;
    }

    // Local-mode events are never sent (the repository already leaves them out; older rows are skipped here).
    const pendingEvents = (await this.scoreRepo.listPendingEvents(PENDING_EVENTS_BATCH)).filter(
      (event) => !isLocalOnlyScoreEvent(event)
    );
    stats.pendingBefore = pendingEvents.length;
    // Matches with score events the backend has not acknowledged yet. Their finalization waits: the
    // backend rebuilds this judge's scorecard from the received events, so finalizing first would not reconcile.
    const unsyncedMatchIds = new Set<string>();
    const holdFinalization = (event: { matchId: string; retryCount: number }) => {
      if (event.retryCount < FINALIZE_HOLD_MAX_EVENT_RETRIES) {
        unsyncedMatchIds.add(event.matchId);
      }
    };

    for (const event of pendingEvents) {
      if (!isRetryEligible({ retryCount: event.retryCount, lastAttemptAt: event.lastAttemptAt ?? null }, new Date().toISOString())) {
        holdFinalization(event);
        continue;
      }

      const owner = resolveSessionOwner(event, session);
      if (owner === 'other-judge') {
        // Queued by another judge or station on this phone: the current token can never send it.
        await this.scoreRepo.markEventRejected(event.id, 'Queued under another judge session');
        stats.rejected += 1;
        continue;
      }

      try {
        await this.scoreRepo.markEventSyncing(event.id);
        const ack = await this.apiClient.postScoreEvent(backend.baseUrl, token, {
          eventId: event.id,
          idempotencyKey: event.idempotencyKey,
          // Same judge reconnected with a new session: the server keeps one scorecard across both sessions.
          sessionId: owner === 'previous-session' && session ? session.sessionId : event.sessionId,
          stationId: event.stationId,
          deviceId: event.deviceId,
          judgeName: event.judgeName,
          matchId: event.matchId,
          roundNumber: event.roundNumber,
          athleteSide: event.athleteSide,
          scoreTarget: event.scoreTarget,
          scoreDelta: event.scoreDelta,
          scoreBefore: event.scoreBefore,
          scoreAfter: event.scoreAfter,
          occurredAt: event.occurredAt,
          sequence: event.sequence
        });

        await this.scoreRepo.markEventAck(event.id, ack.serverReceivedAt);
        stats.sent += 1;
      } catch (error: any) {
        if (isTerminalSyncError(error)) {
          // Cannot succeed on retry (e.g. the operator closed the match): stop retrying and stop holding
          // this match's finalization for it.
          await this.scoreRepo.markEventRejected(event.id, String(error?.message ?? error));
          stats.rejected += 1;
          continue;
        }
        await this.scoreRepo.markEventFailed(event.id, String(error?.message ?? error));
        stats.failed += 1;
        holdFinalization(event);
      }
    }
    // A full batch may hide more pending events of any match: send finalizations in a later cycle.
    const moreEventsPending = pendingEvents.length >= PENDING_EVENTS_BATCH;

    const pendingFinalizations = await this.finalizationRepo.listPendingFinalizations(20);
    for (const event of pendingFinalizations) {
      if (isLocalOnlyMatchId(event.matchId)) {
        continue;
      }
      if (moreEventsPending || unsyncedMatchIds.has(event.matchId)) {
        continue;
      }
      if (!isRetryEligible({ retryCount: event.retryCount, lastAttemptAt: event.lastAttemptAt ?? null }, new Date().toISOString())) {
        continue;
      }

      try {
        await this.finalizationRepo.markFinalizationSyncing(event.id);
        const payload = JSON.parse(event.payloadSnapshot) as Record<string, unknown>;
        const parsedMatchId = typeof payload.matchId === 'string' ? payload.matchId.trim() : '';
        const resolvedMatchId = parsedMatchId || event.matchId;
        payload.matchId = resolvedMatchId;
        const owner = resolveSessionOwner(
          {
            sessionId: String(payload.sessionId ?? ''),
            stationId: String(payload.stationId ?? ''),
            judgeName: String(payload.judgeName ?? '')
          },
          session
        );
        if (owner === 'other-judge') {
          // Another judge's finalization: never sent with this phone's current token.
          await this.finalizationRepo.markFinalizationFailed(event.id, 'Queued under another judge session');
          continue;
        }
        if (owner === 'previous-session' && session) {
          await resignFinalizePayload(payload, session.sessionId);
        }
        const ack = await this.apiClient.finalizeMatch(backend.baseUrl, token, payload as any);
        await this.finalizationRepo.markFinalizationAck(event.id, ack.serverReceivedAt);
        await this.matchRepo.markFinalizedAck(event.matchId);
        stats.finalizedSent += 1;
      } catch (error: any) {
        await this.finalizationRepo.markFinalizationFailed(event.id, String(error?.message ?? error));
        await this.matchRepo.finishLocally(event.matchId, 'finalize_failed_retrying');
        stats.finalizedFailed += 1;
      }
    }

    stats.lastSyncAt = new Date().toISOString();
    return stats;
  }
}

type SessionOwner = 'current-session' | 'previous-session' | 'other-judge';

/** Who queued an item, compared with the session now signed in on this phone. */
export function resolveSessionOwner(
  item: { sessionId: string; stationId: string; judgeName: string },
  session: { sessionId: string; stationId: string; judgeName: string } | null
): SessionOwner {
  if (!session || item.sessionId === session.sessionId) {
    return 'current-session';
  }
  if (item.stationId === session.stationId && item.judgeName === session.judgeName) {
    return 'previous-session';
  }
  return 'other-judge';
}

/** Moves a queued finalization to the current session; the checksum covers the session id, so it is rebuilt. */
async function resignFinalizePayload(payload: Record<string, unknown>, sessionId: string): Promise<void> {
  payload.sessionId = sessionId;
  const rounds = Array.isArray(payload.roundsSummary) ? (payload.roundsSummary as Record<string, unknown>[]) : [];
  payload.checksum = await buildSha256Checksum(
    buildFinalizeChecksumPayload({
      matchId: String(payload.matchId),
      sessionId,
      stationId: String(payload.stationId),
      judgeName: String(payload.judgeName),
      totalEvents: Number(payload.totalEvents),
      lastSequence: Number(payload.finalSequence ?? payload.lastSequence),
      finalScoreRed: Number(payload.finalScoreRed),
      finalScoreBlue: Number(payload.finalScoreBlue),
      rounds: rounds.map((round) => ({
        roundNumber: Number(round.roundNumber),
        techniqueRed: Number(round.techniqueRed),
        presentationRed: Number(round.presentationRed),
        techniqueBlue: Number(round.techniqueBlue),
        presentationBlue: Number(round.presentationBlue)
      }))
    })
  );
}

function createEmptyStats(): SyncCycleStats {
  return {
    pendingBefore: 0,
    sent: 0,
    failed: 0,
    rejected: 0,
    finalizedSent: 0,
    finalizedFailed: 0
  };
}
