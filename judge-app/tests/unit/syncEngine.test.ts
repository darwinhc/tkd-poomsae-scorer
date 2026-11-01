import { describe, expect, it, vi } from 'vitest';
import { SyncEngine, resolveSessionOwner } from '@/application/services/syncEngine';
import { LocalizedError } from '@/i18n/LocalizedError';

vi.mock('expo-crypto', () => ({
  CryptoDigestAlgorithm: { SHA256: 'SHA256' },
  // Deterministic stand-in for SHA-256: returns the canonical string it was given.
  digestStringAsync: vi.fn(async (_algorithm: string, value: string) => `sha256(${value})`)
}));

describe('syncEngine', () => {
  it('does not resend an already acknowledged event (idempotency)', async () => {
    const events: any[] = [
      {
        id: 'e1',
        idempotencyKey: 'e1',
        sessionId: 'sess',
        stationId: 'station-01',
        deviceId: 'dev-1',
        judgeName: 'Judge 1',
        matchId: 'm1',
        roundNumber: 1,
        athleteSide: 'RED',
        scoreDelta: -0.1,
        scoreBefore: 10,
        scoreAfter: 9.9,
        occurredAt: '2026-03-18T00:00:00.000Z',
        sequence: 1,
        retryCount: 0,
        lastAttemptAt: null
      }
    ];

    let calls = 0;
    const scoreRepo: any = {
      listPendingEvents: async () => events,
      markEventSyncing: async () => undefined,
      markEventAck: async () => {
        events.length = 0;
      },
      markEventFailed: async () => undefined
    };

    const engine = new SyncEngine(
      scoreRepo,
      {
        listPendingFinalizations: async () => [],
        markFinalizationSyncing: async () => undefined,
        markFinalizationAck: async () => undefined,
        markFinalizationFailed: async () => undefined
      } as any,
      { getAccessToken: async () => 'token', getSession: async () => null } as any,
      { getActiveBackend: async () => ({ baseUrl: 'http://127.0.0.1:8080' }) } as any,
      { markFinalizedAck: async () => undefined } as any,
      {
        postScoreEvent: async () => {
          calls += 1;
          return { acknowledged: true, eventId: 'e1', serverReceivedAt: new Date().toISOString() };
        },
        finalizeMatch: async () => ({ acknowledged: true, eventId: '', serverReceivedAt: '' })
      } as any
    );

    await engine.triggerSync();
    await engine.triggerSync();

    expect(calls).toBe(1);
  });

  it('queues an extra cycle when triggerSync arrives during a run', async () => {
    let listCalls = 0;
    const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

    const scoreRepo: any = {
      listPendingEvents: async () => {
        listCalls += 1;
        await sleep(25);
        return [];
      },
      markEventSyncing: async () => undefined,
      markEventAck: async () => undefined,
      markEventFailed: async () => undefined
    };

    const engine = new SyncEngine(
      scoreRepo,
      {
        listPendingFinalizations: async () => [],
        markFinalizationSyncing: async () => undefined,
        markFinalizationAck: async () => undefined,
        markFinalizationFailed: async () => undefined
      } as any,
      { getAccessToken: async () => 'token', getSession: async () => null } as any,
      { getActiveBackend: async () => ({ baseUrl: 'http://127.0.0.1:8080' }) } as any,
      { markFinalizedAck: async () => undefined, finishLocally: async () => undefined } as any,
      {
        postScoreEvent: async () => ({ acknowledged: true, eventId: '', serverReceivedAt: new Date().toISOString() }),
        finalizeMatch: async () => ({ acknowledged: true, eventId: '', serverReceivedAt: new Date().toISOString() })
      } as any
    );

    const first = engine.triggerSync();
    const second = engine.triggerSync();
    await Promise.all([first, second]);

    expect(listCalls).toBeGreaterThanOrEqual(2);
  });

  it('holds a finalization until every score event of that match is acknowledged', async () => {
    const pending: any[] = [
      {
        id: 'e1',
        idempotencyKey: 'e1',
        sessionId: 'sess',
        stationId: 'station-01',
        deviceId: 'dev-1',
        judgeName: 'Judge 1',
        matchId: 'm1',
        roundNumber: 1,
        athleteSide: 'RED',
        scoreTarget: 'TECHNIQUE',
        scoreDelta: -0.1,
        scoreBefore: 4,
        scoreAfter: 3.9,
        occurredAt: '2026-03-18T00:00:00.000Z',
        sequence: 1,
        retryCount: 0,
        lastAttemptAt: null
      }
    ];
    let failEvents = true;
    const finalizeCalls: string[] = [];
    const engine = new SyncEngine(
      {
        listPendingEvents: async () => [...pending],
        markEventSyncing: async () => undefined,
        markEventAck: async () => {
          pending.length = 0;
        },
        markEventFailed: async () => undefined
      } as any,
      {
        listPendingFinalizations: async () =>
          finalizeCalls.length
            ? []
            : [{ id: 'f1', matchId: 'm1', payloadSnapshot: JSON.stringify({ matchId: 'm1' }), retryCount: 0, lastAttemptAt: null }],
        markFinalizationSyncing: async () => undefined,
        markFinalizationAck: async () => undefined,
        markFinalizationFailed: async () => undefined
      } as any,
      { getAccessToken: async () => 'token', getSession: async () => null } as any,
      { getActiveBackend: async () => ({ baseUrl: 'http://127.0.0.1:8080' }) } as any,
      { markFinalizedAck: async () => undefined, finishLocally: async () => undefined } as any,
      {
        postScoreEvent: async () => {
          if (failEvents) throw new Error('network down');
          return { acknowledged: true, eventId: 'e1', serverReceivedAt: new Date().toISOString() };
        },
        finalizeMatch: async (_baseUrl: string, _token: string, payload: any) => {
          finalizeCalls.push(payload.matchId);
          return { acknowledged: true, eventId: 'f1', serverReceivedAt: new Date().toISOString() };
        }
      } as any
    );

    const blocked = await engine.triggerSync();
    expect(blocked.failed).toBe(1);
    expect(finalizeCalls).toEqual([]);

    failEvents = false;
    pending[0].retryCount = 0;
    const sent = await engine.triggerSync();
    expect(sent.sent).toBe(1);
    expect(finalizeCalls).toEqual(['m1']);
  });

  it('stops holding the finalization once an event keeps failing', async () => {
    const finalizeCalls: string[] = [];
    const engine = new SyncEngine(
      {
        listPendingEvents: async () => [
          { id: 'e1', idempotencyKey: 'e1', matchId: 'm1', retryCount: 5, lastAttemptAt: null, sequence: 1 }
        ],
        markEventSyncing: async () => undefined,
        markEventAck: async () => undefined,
        markEventFailed: async () => undefined
      } as any,
      {
        listPendingFinalizations: async () => [
          { id: 'f1', matchId: 'm1', payloadSnapshot: JSON.stringify({ matchId: 'm1' }), retryCount: 0, lastAttemptAt: null }
        ],
        markFinalizationSyncing: async () => undefined,
        markFinalizationAck: async () => undefined,
        markFinalizationFailed: async () => undefined
      } as any,
      { getAccessToken: async () => 'token', getSession: async () => null } as any,
      { getActiveBackend: async () => ({ baseUrl: 'http://127.0.0.1:8080' }) } as any,
      { markFinalizedAck: async () => undefined, finishLocally: async () => undefined } as any,
      {
        postScoreEvent: async () => {
          throw new Error('rejected');
        },
        finalizeMatch: async (_baseUrl: string, _token: string, payload: any) => {
          finalizeCalls.push(payload.matchId);
          return { acknowledged: true, eventId: 'f1', serverReceivedAt: new Date().toISOString() };
        }
      } as any
    );

    await engine.triggerSync();

    expect(finalizeCalls).toEqual(['m1']);
  });

  it('rejects an event the server refuses definitively and does not hold the finalization for it', async () => {
    const calls: string[] = [];
    const rejected: string[] = [];
    const finalizeCalls: string[] = [];
    let pending: any[] = [
      { id: 'e1', idempotencyKey: 'e1', matchId: 'm1', sessionId: 'sess', stationId: 'station-01', retryCount: 0, lastAttemptAt: null, sequence: 1 }
    ];
    const engine = new SyncEngine(
      {
        listPendingEvents: async () => [...pending],
        markEventSyncing: async () => undefined,
        markEventAck: async () => undefined,
        markEventFailed: async () => {
          throw new Error('a terminal error must not be retried');
        },
        markEventRejected: async (id: string) => {
          rejected.push(id);
          pending = pending.filter((item) => item.id !== id);
        }
      } as any,
      {
        listPendingFinalizations: async () =>
          finalizeCalls.length
            ? []
            : [{ id: 'f1', matchId: 'm1', payloadSnapshot: JSON.stringify({ matchId: 'm1' }), retryCount: 0, lastAttemptAt: null }],
        markFinalizationSyncing: async () => undefined,
        markFinalizationAck: async () => undefined,
        markFinalizationFailed: async () => undefined
      } as any,
      { getAccessToken: async () => 'token', getSession: async () => null } as any,
      { getActiveBackend: async () => ({ baseUrl: 'http://127.0.0.1:8080' }) } as any,
      { markFinalizedAck: async () => undefined, finishLocally: async () => undefined } as any,
      {
        postScoreEvent: async (_baseUrl: string, _token: string, payload: any) => {
          calls.push(payload.eventId);
          throw new LocalizedError('errors.scoreEventSyncFailed', { status: 409 }, { status: 409, code: 'match_closed' });
        },
        finalizeMatch: async (_baseUrl: string, _token: string, payload: any) => {
          finalizeCalls.push(payload.matchId);
          return { acknowledged: true, eventId: 'f1', serverReceivedAt: new Date().toISOString() };
        }
      } as any
    );

    const first = await engine.triggerSync();
    await engine.triggerSync();

    expect(first.rejected).toBe(1);
    expect(rejected).toEqual(['e1']);
    expect(calls).toEqual(['e1']);
    expect(finalizeCalls).toEqual(['m1']);
  });

  it('never sends local-mode events and they do not hold server finalizations', async () => {
    const sent: string[] = [];
    const finalizeCalls: string[] = [];
    const engine = new SyncEngine(
      {
        listPendingEvents: async () => [
          { id: 'l1', matchId: 'm-local', sessionId: 'local-abc', stationId: 'local-offline', retryCount: 0, lastAttemptAt: null, sequence: 1 },
          { id: 'l2', matchId: 'local-xyz', sessionId: 'sess', stationId: 'station-01', retryCount: 0, lastAttemptAt: null, sequence: 1 }
        ],
        markEventSyncing: async () => undefined,
        markEventAck: async () => undefined,
        markEventFailed: async () => undefined,
        markEventRejected: async () => undefined
      } as any,
      {
        listPendingFinalizations: async () => [
          { id: 'f1', matchId: 'm1', payloadSnapshot: JSON.stringify({ matchId: 'm1' }), retryCount: 0, lastAttemptAt: null }
        ],
        markFinalizationSyncing: async () => undefined,
        markFinalizationAck: async () => undefined,
        markFinalizationFailed: async () => undefined
      } as any,
      { getAccessToken: async () => 'token', getSession: async () => null } as any,
      { getActiveBackend: async () => ({ baseUrl: 'http://127.0.0.1:8080' }) } as any,
      { markFinalizedAck: async () => undefined, finishLocally: async () => undefined } as any,
      {
        postScoreEvent: async (_baseUrl: string, _token: string, payload: any) => {
          sent.push(payload.eventId);
          return { acknowledged: true, eventId: payload.eventId, serverReceivedAt: new Date().toISOString() };
        },
        finalizeMatch: async (_baseUrl: string, _token: string, payload: any) => {
          finalizeCalls.push(payload.matchId);
          return { acknowledged: true, eventId: 'f1', serverReceivedAt: new Date().toISOString() };
        }
      } as any
    );

    const stats = await engine.triggerSync();

    expect(sent).toEqual([]);
    expect(stats.pendingBefore).toBe(0);
    expect(finalizeCalls).toEqual(['m1']);
  });

  it('classifies queued items by the session that queued them', () => {
    const session = { sessionId: 'new', stationId: 'station-01', judgeName: 'Judge 1' };
    expect(resolveSessionOwner({ sessionId: 'new', stationId: 'station-01', judgeName: 'Judge 1' }, session)).toBe('current-session');
    expect(resolveSessionOwner({ sessionId: 'old', stationId: 'station-01', judgeName: 'Judge 1' }, session)).toBe('previous-session');
    expect(resolveSessionOwner({ sessionId: 'old', stationId: 'station-01', judgeName: 'Judge 2' }, session)).toBe('other-judge');
    expect(resolveSessionOwner({ sessionId: 'old', stationId: 'station-02', judgeName: 'Judge 1' }, session)).toBe('other-judge');
    expect(resolveSessionOwner({ sessionId: 'old', stationId: 'station-01', judgeName: 'Judge 1' }, null)).toBe('current-session');
  });

  it('sends events and the finalization of a previous session with the current session', async () => {
    const sent: any[] = [];
    const finalized: any[] = [];
    const events: any[] = [
      {
        id: 'e1', idempotencyKey: 'e1', sessionId: 'old', stationId: 'station-01', deviceId: 'dev-1',
        judgeName: 'Judge 1', matchId: 'm1', roundNumber: 1, athleteSide: 'RED', scoreTarget: 'TECHNIQUE',
        scoreDelta: -0.3, scoreBefore: 4, scoreAfter: 3.7, occurredAt: '2026-03-18T00:00:00.000Z',
        sequence: 1, retryCount: 0, lastAttemptAt: null
      }
    ];
    const finalizePayload = {
      sessionId: 'old', stationId: 'station-01', matchId: 'm1', judgeName: 'Judge 1',
      totalEvents: 1, finalSequence: 1, finalScoreRed: 9.7, finalScoreBlue: 10, checksum: 'old-checksum',
      roundsSummary: [{ roundNumber: 1, techniqueRed: 3.7, presentationRed: 6, techniqueBlue: 4, presentationBlue: 6 }]
    };
    const finalizations: any[] = [
      { id: 'f1', matchId: 'm1', payloadSnapshot: JSON.stringify(finalizePayload), retryCount: 0, lastAttemptAt: null }
    ];
    const engine = new SyncEngine(
      {
        listPendingEvents: async () => events,
        markEventSyncing: async () => undefined,
        markEventAck: async () => { events.length = 0; },
        markEventFailed: async () => undefined,
        markEventRejected: async () => undefined
      } as any,
      {
        listPendingFinalizations: async () => finalizations,
        markFinalizationSyncing: async () => undefined,
        markFinalizationAck: async () => { finalizations.length = 0; },
        markFinalizationFailed: async () => undefined
      } as any,
      {
        getAccessToken: async () => 'token-new',
        getSession: async () => ({ sessionId: 'new', stationId: 'station-01', judgeName: 'Judge 1' })
      } as any,
      { getActiveBackend: async () => ({ baseUrl: 'http://127.0.0.1:8080' }) } as any,
      { markFinalizedAck: async () => undefined, finishLocally: async () => undefined } as any,
      {
        postScoreEvent: async (_url: string, _token: string, body: any) => {
          sent.push(body);
          return { acknowledged: true, eventId: body.eventId, serverReceivedAt: '2026-03-18T00:00:01.000Z' };
        },
        finalizeMatch: async (_url: string, _token: string, body: any) => {
          finalized.push(body);
          return { acknowledged: true, eventId: 'f1', serverReceivedAt: '2026-03-18T00:00:02.000Z' };
        }
      } as any
    );

    await engine.triggerSync();

    expect(sent).toHaveLength(1);
    expect(sent[0].sessionId).toBe('new');
    expect(finalized).toHaveLength(1);
    expect(finalized[0].sessionId).toBe('new');
    // The checksum covers the session id, so it is rebuilt for the new session.
    const canonical =
      '{"finalScoreBlue":"10.00","finalScoreRed":"9.70","judgeName":"Judge 1","lastSequence":1,"matchId":"m1",' +
      '"rounds":[{"presentationBlue":"6.00","presentationRed":"6.00","roundNumber":1,"techniqueBlue":"4.00",' +
      '"techniqueRed":"3.70"}],"sessionId":"new","stationId":"station-01","totalEvents":1}';
    expect(finalized[0].checksum).toBe(`sha256(${canonical})`);
  });

  it('never sends items queued by another judge on the same phone', async () => {
    const rejected: string[] = [];
    let posts = 0;
    const engine = new SyncEngine(
      {
        listPendingEvents: async () => [
          {
            id: 'e1', idempotencyKey: 'e1', sessionId: 'old', stationId: 'station-01', deviceId: 'dev-1',
            judgeName: 'Judge 2', matchId: 'm1', roundNumber: 1, athleteSide: 'RED', scoreTarget: 'TECHNIQUE',
            scoreDelta: -0.1, scoreBefore: 4, scoreAfter: 3.9, occurredAt: '2026-03-18T00:00:00.000Z',
            sequence: 1, retryCount: 0, lastAttemptAt: null
          }
        ],
        markEventSyncing: async () => undefined,
        markEventAck: async () => undefined,
        markEventFailed: async () => undefined,
        markEventRejected: async (id: string) => { rejected.push(id); }
      } as any,
      {
        listPendingFinalizations: async () => [],
        markFinalizationSyncing: async () => undefined,
        markFinalizationAck: async () => undefined,
        markFinalizationFailed: async () => undefined
      } as any,
      {
        getAccessToken: async () => 'token-new',
        getSession: async () => ({ sessionId: 'new', stationId: 'station-01', judgeName: 'Judge 1' })
      } as any,
      { getActiveBackend: async () => ({ baseUrl: 'http://127.0.0.1:8080' }) } as any,
      { markFinalizedAck: async () => undefined } as any,
      {
        postScoreEvent: async () => { posts += 1; return { acknowledged: true, eventId: 'e1', serverReceivedAt: '' }; },
        finalizeMatch: async () => ({ acknowledged: true, eventId: '', serverReceivedAt: '' })
      } as any
    );

    await engine.triggerSync();

    expect(posts).toBe(0);
    expect(rejected).toEqual(['e1']);
  });
});
