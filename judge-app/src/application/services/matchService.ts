import type {
  IHistoryRepository,
  IInboundServerEventRepository,
  IMatchRepository,
  IScoreEventRepository,
  ISessionRepository
} from '@/application/ports/repositories';
import { PRESENTATION_CATEGORY_MAX_SCORE } from '@/constants/defaults';
import type { AthleteSide, Match, OperatorSession, ScoreEvent, ScoreTarget } from '@/domain/models/entities';
import { isLocalOnlyMatchId, isLocalSession } from '@/domain/services/localMode';
import { canMoveToNextRound, nextRoundNumber } from '@/domain/services/roundRules';
import {
  buildSideScore,
  calculatePresentationFromEvents,
  calculateTechniqueFromEvents
} from '@/domain/services/scoreCalculator';
import { LocalizedError } from '@/i18n/LocalizedError';
import { createId } from '@/utils/id';
import { nowIso } from '@/utils/time';

const PRESENTATION_TARGETS: ScoreTarget[] = [
  'PRESENTATION_SPEED_POWER',
  'PRESENTATION_RHYTHM_TEMPO',
  'PRESENTATION_ENERGY_EXPRESSION'
];
const TECHNIQUE_TARGETS: ScoreTarget[] = ['TECHNIQUE'];
const SIDES: AthleteSide[] = ['RED', 'BLUE'];

export class MatchService {
  constructor(
    private readonly matchRepo: IMatchRepository,
    private readonly scoreRepo: IScoreEventRepository,
    private readonly sessionRepo: ISessionRepository,
    private readonly historyRepo: IHistoryRepository,
    private readonly inboundRepo: IInboundServerEventRepository
  ) {}

  async createMatch(input: {
    matchId?: string;
    competitorLeftName: string;
    competitorRightName: string;
    leftSideColor?: AthleteSide;
    rightSideColor?: AthleteSide;
    totalRounds: number;
    startingScore: number;
    presentationCategoryStartScore: number;
  }) {
    return this.matchRepo.createMatch(input);
  }

  async getActiveMatchProjection() {
    const match = await this.matchRepo.getActiveMatch();
    if (!match) {
      return null;
    }

    const events = await this.scoreRepo.listMatchEvents(match.id);
    const currentRoundEvents = events.filter((event) => event.roundNumber === match.currentRound);
    const technique = calculateTechniqueFromEvents(match.startingScore, currentRoundEvents);
    const presentation = calculatePresentationFromEvents(match.presentationCategoryStartScore, currentRoundEvents);

    return {
      match,
      technique,
      presentation,
      events
    };
  }

  async applyScoreDelta(side: AthleteSide, scoreDelta: number, scoreTarget: ScoreTarget = 'TECHNIQUE'): Promise<ScoreEvent | null> {
    const [match, session] = await Promise.all([this.matchRepo.getActiveMatch(), this.sessionRepo.getSession()]);

    if (!match) {
      throw new LocalizedError('errors.noActiveMatch');
    }

    if (!session) {
      throw new LocalizedError('errors.noActiveStationSession');
    }

    if (match.status !== 'active') {
      throw new LocalizedError('errors.matchNotActive');
    }

    const events = (await this.scoreRepo.listMatchEvents(match.id)).filter((event) => event.roundNumber === match.currentRound);
    const beforeStart = scoreTarget === 'TECHNIQUE' ? match.startingScore : match.presentationCategoryStartScore;
    const before = buildSideScore(beforeStart, side, scoreTarget, events);
    const bounds = resolveBounds(match.startingScore, scoreTarget);
    const clampedBefore = clamp(before, bounds.min, bounds.max);
    const clampedAfter = clamp(round1(clampedBefore + scoreDelta), bounds.min, bounds.max);
    const effectiveDelta = round1(clampedAfter - clampedBefore);
    if (Math.abs(effectiveDelta) < 0.05) {
      return null;
    }
    return this.recordEvent(match, session, side, scoreTarget, effectiveDelta, clampedBefore, clampedAfter);
  }

  async moveToNextRound() {
    const match = await this.matchRepo.getActiveMatch();
    if (!match) {
      throw new LocalizedError('errors.noActiveMatch');
    }

    if (!canMoveToNextRound(match.currentRound, match.totalRounds, match.status === 'active')) {
      throw new LocalizedError('errors.cannotAdvance');
    }

    const next = nextRoundNumber(match.currentRound, match.totalRounds);
    await this.matchRepo.moveToRound(match.id, next);
    return next;
  }

  /**
   * Resets the technique of the current round to its start value on this device and on the server.
   *
   * Events are never deleted (some may already be synced): the reset records compensating score events, the
   * inverse of the current value change of each side, with new sequence numbers. The server applies them
   * like any other event, so its scorecard of this judge and the device stay equal and the finalization
   * reconciles. Local-only matches work the same way (their events are simply never sent).
   */
  async resetTechniqueCurrentRound(): Promise<ScoreEvent[]> {
    return this.compensateCurrentRound(TECHNIQUE_TARGETS, 'local_reset_technique_round');
  }

  /** Same as resetTechniqueCurrentRound for the three presentation categories. */
  async resetPresentationCurrentRound(): Promise<ScoreEvent[]> {
    return this.compensateCurrentRound(PRESENTATION_TARGETS, 'local_reset_presentation_round');
  }

  private async compensateCurrentRound(targets: ScoreTarget[], logType: string): Promise<ScoreEvent[]> {
    const [match, session] = await Promise.all([this.matchRepo.getActiveMatch(), this.sessionRepo.getSession()]);
    if (!match) {
      return [];
    }
    if (!session) {
      throw new LocalizedError('errors.noActiveStationSession');
    }

    const roundEvents = (await this.scoreRepo.listMatchEvents(match.id)).filter(
      (event) => event.roundNumber === match.currentRound
    );
    const recorded: ScoreEvent[] = [];
    for (const target of targets) {
      const start = target === 'TECHNIQUE' ? match.startingScore : match.presentationCategoryStartScore;
      for (const side of SIDES) {
        const current = buildSideScore(start, side, target, roundEvents);
        const compensation = round1(start - current);
        if (Math.abs(compensation) < 0.05) {
          continue;
        }
        recorded.push(await this.recordEvent(match, session, side, target, compensation, current, start));
      }
    }

    const now = nowIso();
    await this.inboundRepo.appendLog({
      id: createId(),
      eventType: logType,
      dedupeKey: `${logType}:${match.id}:${match.currentRound}:${now}`,
      payload: JSON.stringify({
        matchId: match.id,
        roundNumber: match.currentRound,
        compensatingEventIds: recorded.map((event) => event.id)
      }),
      receivedAt: now,
      processedAt: now
    });
    return recorded;
  }

  private async recordEvent(
    match: Match,
    session: OperatorSession,
    side: AthleteSide,
    scoreTarget: ScoreTarget,
    scoreDelta: number,
    scoreBefore: number,
    scoreAfter: number
  ): Promise<ScoreEvent> {
    // A new sequence every time: events are never deleted by the judge, so sequences are never reused.
    const sequence = await this.scoreRepo.getNextSequence(match.id);
    const now = nowIso();
    const id = createId();
    // Local mode (local session or local-only match): never synced.
    const localOnly = isLocalOnlyMatchId(match.id) || isLocalSession(session);

    const event: ScoreEvent = {
      id,
      idempotencyKey: id,
      sessionId: session.sessionId,
      stationId: session.stationId,
      deviceId: session.deviceId,
      judgeName: session.judgeName,
      matchId: match.id,
      roundNumber: match.currentRound,
      athleteSide: side,
      scoreTarget,
      scoreDelta,
      scoreBefore,
      scoreAfter,
      occurredAt: now,
      sequence,
      syncStatus: localOnly ? 'acknowledged' : 'pending',
      retryCount: 0,
      lastError: null,
      lastAttemptAt: null,
      serverAckAt: localOnly ? now : null
    };

    await this.scoreRepo.appendScoreEvent(event);
    return event;
  }

  async closeActiveMatch(reason = 'manual_close') {
    const match = await this.matchRepo.getActiveMatch();
    if (!match) {
      return;
    }

    await this.matchRepo.finishLocally(match.id, 'finished_locally');
    const now = nowIso();
    await this.inboundRepo.appendLog({
      id: createId(),
      eventType: 'local_close_match',
      dedupeKey: `local_close_match:${match.id}:${now}`,
      payload: JSON.stringify({ matchId: match.id, reason }),
      receivedAt: now,
      processedAt: now
    });
  }

  async updateCompetitors(matchId: string, left: string, right: string) {
    await this.matchRepo.updateCompetitors(matchId, left, right);
  }

  async getSummary(matchId: string) {
    return this.historyRepo.getSummary(matchId);
  }
}

function resolveBounds(maxTechniqueScore: number, target: ScoreTarget): { min: number; max: number } {
  if (target === 'TECHNIQUE') {
    return { min: 0, max: maxTechniqueScore };
  }
  return { min: 0, max: PRESENTATION_CATEGORY_MAX_SCORE };
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
