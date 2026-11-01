import { describe, expect, it } from 'vitest';
import { MatchService } from '@/application/services/matchService';
import type { ScoreEvent } from '@/domain/models/entities';
import { calculatePresentationFromEvents, calculateTechniqueFromEvents } from '@/domain/services/scoreCalculator';

// The judge's resets used to delete events on the device only; events already synced stayed on the server and
// the finalization did not reconcile. They now record compensating events (tests below replace the old
// "resetMatch writes an audit log" test: that unused delete-based path was removed).

function setup(options: { matchId?: string; sessionId?: string; stationId?: string; presentationStart?: number } = {}) {
  const match = {
    id: options.matchId ?? 'm1',
    startingScore: 4,
    presentationCategoryStartScore: options.presentationStart ?? 2,
    currentRound: 1,
    status: 'active',
    totalRounds: 2
  };
  const session = {
    sessionId: options.sessionId ?? 'sess-1',
    stationId: options.stationId ?? 'station-01',
    deviceId: 'dev-1',
    judgeName: 'Judge 1'
  };
  const events: ScoreEvent[] = [];
  const logs: any[] = [];
  const scoreRepo = {
    listMatchEvents: async (matchId: string) =>
      events.filter((item) => item.matchId === matchId).sort((a, b) => a.sequence - b.sequence),
    getNextSequence: async (matchId: string) =>
      Math.max(0, ...events.filter((item) => item.matchId === matchId).map((item) => item.sequence)) + 1,
    appendScoreEvent: async (event: ScoreEvent) => {
      events.push(event);
    }
  };
  const service = new MatchService(
    { getActiveMatch: async () => match } as any,
    scoreRepo as any,
    { getSession: async () => session } as any,
    {} as any,
    { appendLog: async (log: any) => logs.push(log) } as any
  );
  return { service, events, logs, match };
}

describe('matchService resets with compensating events', () => {
  it('resets the technique of the round without deleting synced events', async () => {
    const { service, events, logs } = setup();
    await service.applyScoreDelta('RED', -0.3);
    await service.applyScoreDelta('RED', -0.1);
    await service.applyScoreDelta('BLUE', -0.2);
    await service.applyScoreDelta('RED', -0.2, 'PRESENTATION_SPEED_POWER');
    events[0].syncStatus = 'acknowledged';

    const compensations = await service.resetTechniqueCurrentRound();

    expect(events).toHaveLength(6);
    expect(events[0].syncStatus).toBe('acknowledged');
    expect(compensations.map((item) => [item.athleteSide, item.scoreTarget, item.scoreDelta, item.sequence])).toEqual([
      ['RED', 'TECHNIQUE', 0.4, 5],
      ['BLUE', 'TECHNIQUE', 0.2, 6]
    ]);
    expect(compensations.every((item) => item.syncStatus === 'pending')).toBe(true);
    expect(compensations[0]).toMatchObject({ scoreBefore: 3.6, scoreAfter: 4 });
    expect(calculateTechniqueFromEvents(4, events)).toEqual({ red: 4, blue: 4 });
    // Presentation is untouched by a technique reset.
    expect(calculatePresentationFromEvents(2, events).byCategory.speedPower.red).toBe(1.8);
    expect(logs.at(-1).eventType).toBe('local_reset_technique_round');
  });

  it('resets the three presentation categories only', async () => {
    const { service, events } = setup();
    await service.applyScoreDelta('RED', -0.3);
    await service.applyScoreDelta('RED', -0.5, 'PRESENTATION_SPEED_POWER');
    await service.applyScoreDelta('BLUE', -0.1, 'PRESENTATION_ENERGY_EXPRESSION');

    const compensations = await service.resetPresentationCurrentRound();

    expect(compensations.map((item) => [item.athleteSide, item.scoreTarget, item.scoreDelta])).toEqual([
      ['RED', 'PRESENTATION_SPEED_POWER', 0.5],
      ['BLUE', 'PRESENTATION_ENERGY_EXPRESSION', 0.1]
    ]);
    expect(calculatePresentationFromEvents(2, events).total).toEqual({ red: 6, blue: 6 });
    expect(calculateTechniqueFromEvents(4, events).red).toBe(3.7);
  });

  it('never reuses a sequence number after a reset', async () => {
    const { service, events } = setup();
    await service.applyScoreDelta('RED', -0.3);
    await service.resetTechniqueCurrentRound();
    await service.applyScoreDelta('RED', -0.1);
    await service.resetTechniqueCurrentRound();

    const sequences = events.map((item) => item.sequence);
    expect(sequences).toEqual([1, 2, 3, 4]);
    expect(new Set(sequences).size).toBe(sequences.length);
  });

  it('records nothing when the round is already at its start values', async () => {
    const { service, events } = setup();
    await service.applyScoreDelta('RED', -0.2);
    await service.applyScoreDelta('RED', 0.2);

    expect(await service.resetTechniqueCurrentRound()).toEqual([]);
    expect(events).toHaveLength(2);
  });

  it('keeps local-only matches working: compensations are never queued for sync', async () => {
    const local = setup({ matchId: 'local-abc' });
    await local.service.applyScoreDelta('RED', -0.3);
    const [compensation] = await local.service.resetTechniqueCurrentRound();
    expect(compensation.syncStatus).toBe('acknowledged');

    const localSession = setup({ sessionId: 'local-sess', stationId: 'local-offline' });
    const scored = await localSession.service.applyScoreDelta('BLUE', -0.1);
    expect(scored?.syncStatus).toBe('acknowledged');
  });

  it('scores and resets presentation from the configured category start, not from the 2.0 maximum', async () => {
    // With a category start of 1.5 the + buttons must still work up to 2.0 and a reset returns to 1.5.
    const { service, events } = setup({ presentationStart: 1.5 });
    await service.applyScoreDelta('RED', 0.1, 'PRESENTATION_SPEED_POWER');
    await service.applyScoreDelta('RED', 0.1, 'PRESENTATION_SPEED_POWER');
    await service.applyScoreDelta('RED', 0.1, 'PRESENTATION_SPEED_POWER');

    expect(events.map((item) => [item.scoreBefore, item.scoreAfter])).toEqual([
      [1.5, 1.6],
      [1.6, 1.7],
      [1.7, 1.8]
    ]);
    expect(calculatePresentationFromEvents(1.5, events).byCategory.speedPower.red).toBe(1.8);

    await service.resetPresentationCurrentRound();

    expect(calculatePresentationFromEvents(1.5, events).byCategory.speedPower.red).toBe(1.5);
  });
});
