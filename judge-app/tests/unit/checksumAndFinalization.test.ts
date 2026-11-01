import { describe, expect, it, vi } from 'vitest';

vi.mock('expo-crypto', () => ({
  CryptoDigestAlgorithm: { SHA256: 'SHA256' },
  digestStringAsync: vi.fn(async () => 'mocked-checksum')
}));

// Shared test vector: backend/tests/unit/test_finalization_checksum.py builds the same payload and must get
// exactly this canonical string and SHA-256.
const SHARED_VECTOR_CANONICAL =
  '{"finalScoreBlue":"9.75","finalScoreRed":"9.30","judgeName":"Judge \u00c9","lastSequence":9,' +
  '"matchId":"match-vector-1","rounds":[{"presentationBlue":"6.00","presentationRed":"5.80","roundNumber":1,' +
  '"techniqueBlue":"3.90","techniqueRed":"3.60"},{"presentationBlue":"5.90","presentationRed":"5.70",' +
  '"roundNumber":2,"techniqueBlue":"3.70","techniqueRed":"3.50"}],"sessionId":"session-vector-1",' +
  '"stationId":"station-01","totalEvents":7}';
const SHARED_VECTOR_SHA256 = '3835fc5400b88b7fdb67a709fbf3d456709fc862247d3fef7a64ec04bf5c4526';

// Real SHA-256 (Web Crypto, available in Node): expo-crypto is mocked in this file.
async function sha256Hex(value: string): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

function sharedVectorInput() {
  return {
    matchId: 'match-vector-1',
    sessionId: 'session-vector-1',
    stationId: 'station-01',
    judgeName: 'Judge \u00c9',
    totalEvents: 7,
    lastSequence: 9,
    finalScoreRed: 9.3,
    finalScoreBlue: 9.75,
    // Unsorted on purpose: the payload sorts rounds by number.
    rounds: [
      { roundNumber: 2, techniqueRed: 3.5, presentationRed: 5.7, techniqueBlue: 3.7, presentationBlue: 5.9 },
      { roundNumber: 1, techniqueRed: 3.6, presentationRed: 5.8, techniqueBlue: 3.9, presentationBlue: 6 }
    ]
  };
}

function roundSummary(roundNumber: number, status: 'pending' | 'active' | 'completed', red: [number, number], blue: [number, number]) {
  return {
    roundNumber,
    status,
    technique: { red: red[0], blue: blue[0] },
    presentationTotal: { red: red[1], blue: blue[1] },
    presentationByCategory: {
      speedPower: { red: 2, blue: 2 },
      rhythmTempo: { red: 2, blue: 2 },
      energyExpression: { red: 2, blue: 2 }
    },
    totalNegative: { red: 0, blue: 0 },
    totalPositive: { red: 0, blue: 0 },
    eventsCount: 1
  };
}

describe('checksum/finalization', () => {
  it('builds the shared test vector canonical string and sha256 like the backend', async () => {
    const { buildFinalizeChecksumPayload, canonicalize } = await import('@/domain/services/checksum');
    const canonical = canonicalize(buildFinalizeChecksumPayload(sharedVectorInput()));

    expect(canonical).toBe(SHARED_VECTOR_CANONICAL);
    expect(await sha256Hex(canonical)).toBe(SHARED_VECTOR_SHA256);
  });

  it('serializes scores as strings with exactly 2 decimals', async () => {
    const { formatScore2 } = await import('@/domain/services/checksum');
    expect(formatScore2(8.85)).toBe('8.85');
    expect(formatScore2(4)).toBe('4.00');
    expect(formatScore2(3.7 + 5.8)).toBe('9.50');
  });

  it('finalizes with 2-decimal scores, per-round parts and the canonical checksum of the scored rounds', async () => {
    const Crypto = await import('expo-crypto');
    const digest = Crypto.digestStringAsync as unknown as ReturnType<typeof vi.fn>;
    digest.mockClear();
    const { FinalizationService } = await import('@/application/services/finalizationService');
    const { canonicalize, buildFinalizeChecksumPayload } = await import('@/domain/services/checksum');
    const saved: any[] = [];
    const service = new FinalizationService(
      {
        getActiveMatch: async () => ({
          id: 'match-1',
          competitorLeftName: 'Red',
          competitorRightName: 'Blue',
          totalRounds: 3,
          currentRound: 2,
          startingScore: 4,
          status: 'active',
          createdAt: '2026-01-01T00:00:00.000Z',
          startedAt: '2026-01-01T00:00:00.000Z',
          retentionPriority: 1
        }),
        finishLocally: async () => undefined
      } as any,
      {
        getSummary: async () => ({
          matchId: 'match-1',
          technique: { red: 3.6, blue: 3.8 },
          presentationTotal: { red: 5.25, blue: 5.25 },
          rounds: [
            // 8.2 and 9.5 average to 8.85 (it was rounded to 8.9 before).
            roundSummary(1, 'completed', [3.4, 4.8], [3.8, 4.9]),
            roundSummary(2, 'active', [3.8, 5.7], [3.8, 5.6]),
            roundSummary(3, 'pending', [4, 6], [4, 6])
          ],
          timeline: [
            { eventId: 'e1', sequence: 1 },
            { eventId: 'e2', sequence: 2 },
            { eventId: 'e3', sequence: 4 }
          ],
          finalizationStatus: 'active'
        })
      } as any,
      { saveFinalization: async (event: any) => saved.push(event) } as any,
      {
        getSession: async () => ({ sessionId: 'sess-1', stationId: 'station-01', judgeName: 'Judge 1' }),
        getAccessToken: async () => 'token-1'
      } as any,
      { getActiveBackend: async () => ({ baseUrl: 'http://192.168.1.20:8080' }) } as any
    );

    const result = await service.finalizeActiveMatch();

    expect(result.payload.finalScoreRed).toBe(8.85);
    expect(result.payload.finalScoreBlue).toBe(9.05);
    expect(result.payload.roundsSummary.map((round) => round.roundNumber)).toEqual([1, 2]);
    expect(result.payload.roundsSummary[0]).toMatchObject({
      techniqueRed: 3.4,
      presentationRed: 4.8,
      techniqueBlue: 3.8,
      presentationBlue: 4.9,
      red: 8.2,
      blue: 8.7
    });
    const expectedCanonical = canonicalize(
      buildFinalizeChecksumPayload({
        matchId: 'match-1',
        sessionId: 'sess-1',
        stationId: 'station-01',
        judgeName: 'Judge 1',
        totalEvents: 3,
        lastSequence: 4,
        finalScoreRed: 8.85,
        finalScoreBlue: 9.05,
        rounds: [
          { roundNumber: 1, techniqueRed: 3.4, presentationRed: 4.8, techniqueBlue: 3.8, presentationBlue: 4.9 },
          { roundNumber: 2, techniqueRed: 3.8, presentationRed: 5.7, techniqueBlue: 3.8, presentationBlue: 5.6 }
        ]
      })
    );
    expect(digest).toHaveBeenCalledWith('SHA256', expectedCanonical);
    expect(expectedCanonical).toContain('"finalScoreRed":"8.85"');
    expect(saved).toHaveLength(1);
  });

  it('builds a deterministic canonical string', async () => {
    const { canonicalize } = await import('@/domain/services/checksum');
    const a = canonicalize({ b: 2, a: 1 } as any);
    const b = canonicalize({ a: 1, b: 2 } as any);
    expect(a).toBe(b);
  });

  it('builds the finalization with checksum and persists the event', async () => {
    const { FinalizationService } = await import('@/application/services/finalizationService');
    const saved: any[] = [];
    const matchRepo: any = {
      getActiveMatch: async () => ({
        id: 'm1',
        competitorLeftName: 'Red',
        competitorRightName: 'Blue',
        totalRounds: 2,
        currentRound: 2,
        startingScore: 10,
        status: 'active',
        createdAt: '2026-01-01T00:00:00.000Z',
        startedAt: '2026-01-01T00:00:00.000Z',
        retentionPriority: 1
      }),
      finishLocally: async () => undefined
    };
    const historyRepo: any = {
      getSummary: async () => ({
        matchId: 'm1',
        technique: { red: 9.8, blue: 9.9 },
        presentationTotal: { red: 6, blue: 6 },
        presentationByCategory: {
          speedPower: { red: 2, blue: 2 },
          rhythmTempo: { red: 2, blue: 2 },
          energyExpression: { red: 2, blue: 2 }
        },
        totalNegative: { red: 0.2, blue: 0.1 },
        totalPositive: { red: 0, blue: 0 },
        rounds: [
          {
            roundNumber: 1,
            technique: { red: 9.9, blue: 9.9 },
            presentationTotal: { red: 6, blue: 6 },
            presentationByCategory: {
              speedPower: { red: 2, blue: 2 },
              rhythmTempo: { red: 2, blue: 2 },
              energyExpression: { red: 2, blue: 2 }
            },
            totalNegative: { red: 0.1, blue: 0.1 },
            totalPositive: { red: 0, blue: 0 },
            eventsCount: 2
          }
        ],
        timeline: [],
        finalizationStatus: 'active'
      })
    };
    const finalRepo: any = {
      saveFinalization: async (event: any) => saved.push(event)
    };
    const sessionRepo: any = {
      getSession: async () => ({
        sessionId: 'sess-1',
        stationId: 'station-01',
        judgeName: 'Judge 1'
      }),
      getAccessToken: async () => 'token-1'
    };
    const connectionRepo: any = {
      getActiveBackend: async () => ({ baseUrl: 'http://192.168.1.20:8080' })
    };

    const service = new FinalizationService(matchRepo, historyRepo, finalRepo, sessionRepo, connectionRepo);
    await service.finalizeActiveMatch();

    expect(saved).toHaveLength(1);
    expect(saved[0].checksum).toBe('mocked-checksum');
  });

  it('finalizes locally without a backend and does not queue a remote finalization', async () => {
    const { FinalizationService } = await import('@/application/services/finalizationService');
    const saved: any[] = [];
    const finishStates: string[] = [];
    const matchRepo: any = {
      getActiveMatch: async () => ({
        id: 'm-local',
        competitorLeftName: 'Red',
        competitorRightName: 'Blue',
        totalRounds: 2,
        currentRound: 2,
        startingScore: 4,
        status: 'active',
        createdAt: '2026-01-01T00:00:00.000Z',
        startedAt: '2026-01-01T00:00:00.000Z',
        retentionPriority: 1
      }),
      finishLocally: async (_id: string, status: string) => finishStates.push(status)
    };
    const historyRepo: any = {
      getSummary: async () => ({
        matchId: 'm-local',
        technique: { red: 3.7, blue: 3.8 },
        presentationTotal: { red: 5.9, blue: 5.7 },
        presentationByCategory: {
          speedPower: { red: 2, blue: 2 },
          rhythmTempo: { red: 2, blue: 1.8 },
          energyExpression: { red: 1.9, blue: 1.9 }
        },
        totalNegative: { red: 0.3, blue: 0.2 },
        totalPositive: { red: 0, blue: 0 },
        rounds: [],
        timeline: [],
        finalizationStatus: 'active'
      })
    };
    const finalRepo: any = {
      saveFinalization: async (event: any) => saved.push(event)
    };
    const sessionRepo: any = {
      getSession: async () => ({
        sessionId: 'local-sess',
        stationId: 'local-offline',
        judgeName: 'Judge 1'
      }),
      getAccessToken: async () => null
    };
    const connectionRepo: any = {
      getActiveBackend: async () => null
    };

    const service = new FinalizationService(matchRepo, historyRepo, finalRepo, sessionRepo, connectionRepo);
    const result = await service.finalizeActiveMatch();

    expect(result.mode).toBe('offline_local');
    expect(saved).toHaveLength(0);
    expect(finishStates).toEqual(['finished_locally']);
  });
});
