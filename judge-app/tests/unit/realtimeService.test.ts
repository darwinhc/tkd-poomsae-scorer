import { describe, expect, it, vi } from 'vitest';
import { RealtimeService } from '@/application/services/realtimeService';
class FakeRealtimeClient {
  private onMessage?: (event: unknown) => Promise<void> | void;
  sentEvents: Array<{ type: string; payload: Record<string, unknown> }> = [];

  connect(input: {
    onMessage: (event: unknown) => Promise<void> | void;
    onStatus: (status: 'connecting' | 'connected' | 'disconnected') => void;
  }) {
    this.onMessage = input.onMessage;
    input.onStatus('connected');
  }

  disconnect() {}

  sendEvent(type: string, payload: Record<string, unknown>) {
    this.sentEvents.push({ type, payload });
  }

  sendPong(_payload?: Record<string, unknown>) {}

  async emit(event: unknown) {
    if (this.onMessage) {
      await this.onMessage(event);
    }
  }
}

describe('RealtimeService', () => {
  it('maps RED/BLUE names to left/right according to local sides', async () => {
    const realtimeClient = new FakeRealtimeClient();
    const inboundRepo = {
      hasDedupeKey: vi.fn().mockResolvedValue(false),
      appendLog: vi.fn().mockResolvedValue(undefined)
    };
    const matchRepo = {
      getMatchById: vi.fn().mockResolvedValue({
        id: 'm1',
        leftSideColor: 'BLUE',
        rightSideColor: 'RED'
      }),
      updateCompetitors: vi.fn().mockResolvedValue(undefined),
      resetMatch: vi.fn().mockResolvedValue(undefined),
      moveToRound: vi.fn().mockResolvedValue(undefined)
    };
    const scoreRepo = {
      resetCurrentRound: vi.fn().mockResolvedValue(undefined)
    };
    const sessionRepo = {
      clearSession: vi.fn().mockResolvedValue(undefined)
    };
    const settingsRepo = {
      upsertSettings: vi.fn().mockResolvedValue(undefined)
    };

    const service = new RealtimeService(
      realtimeClient as any,
      inboundRepo as any,
      matchRepo as any,
      scoreRepo as any,
      sessionRepo as any,
      settingsRepo as any
    );

    service.connect({
      baseUrl: 'http://localhost:8080',
      sessionId: 's1',
      accessToken: 't1',
      stationId: 'station-01',
      onStatus: () => undefined
    });

    await realtimeClient.emit({
      type: 'new_competitors',
      payload: {
        matchId: 'm1',
        competitorRedName: 'RedName',
        competitorBlueName: 'BlueName'
      }
    });

    expect(matchRepo.updateCompetitors).toHaveBeenCalledWith('m1', 'BlueName', 'RedName');
  });

  it('stores the active match state received over websocket', async () => {
    const realtimeClient = new FakeRealtimeClient();
    const inboundRepo = {
      hasDedupeKey: vi.fn().mockResolvedValue(false),
      appendLog: vi.fn().mockResolvedValue(undefined)
    };
    const matchRepo = {
      getMatchById: vi.fn().mockResolvedValue(null),
      updateCompetitors: vi.fn().mockResolvedValue(undefined),
      resetMatch: vi.fn().mockResolvedValue(undefined),
      moveToRound: vi.fn().mockResolvedValue(undefined)
    };
    const scoreRepo = { resetCurrentRound: vi.fn().mockResolvedValue(undefined) };
    const sessionRepo = {
      clearSession: vi.fn().mockResolvedValue(undefined)
    };
    const settingsRepo = {
      upsertSettings: vi.fn().mockResolvedValue(undefined)
    };

    const service = new RealtimeService(
      realtimeClient as any,
      inboundRepo as any,
      matchRepo as any,
      scoreRepo as any,
      sessionRepo as any,
      settingsRepo as any
    );

    service.connect({
      baseUrl: 'http://localhost:8080',
      sessionId: 's1',
      accessToken: 't1',
      stationId: 'station-01',
      onStatus: () => undefined
    });

    await realtimeClient.emit({
      type: 'active_match_state',
      payload: {
        hasActiveMatch: true,
        matchId: 'mx-1',
        competitorRedName: 'Competitor C',
        competitorBlueName: 'Competitor D'
      }
    });

    expect(settingsRepo.upsertSettings).toHaveBeenCalled();
  });

  it('applies a settings update sent by the backend', async () => {
    const realtimeClient = new FakeRealtimeClient();
    const inboundRepo = {
      hasDedupeKey: vi.fn().mockResolvedValue(false),
      appendLog: vi.fn().mockResolvedValue(undefined)
    };
    const matchRepo = {
      getMatchById: vi.fn().mockResolvedValue(null),
      updateCompetitors: vi.fn().mockResolvedValue(undefined),
      resetMatch: vi.fn().mockResolvedValue(undefined),
      moveToRound: vi.fn().mockResolvedValue(undefined)
    };
    const scoreRepo = { resetCurrentRound: vi.fn().mockResolvedValue(undefined) };
    const sessionRepo = {
      clearSession: vi.fn().mockResolvedValue(undefined)
    };
    const settingsRepo = {
      upsertSettings: vi.fn().mockResolvedValue(undefined)
    };

    const service = new RealtimeService(
      realtimeClient as any,
      inboundRepo as any,
      matchRepo as any,
      scoreRepo as any,
      sessionRepo as any,
      settingsRepo as any
    );

    service.connect({
      baseUrl: 'http://localhost:8080',
      sessionId: 's1',
      accessToken: 't1',
      stationId: 'station-01',
      onStatus: () => undefined
    });

    await realtimeClient.emit({
      type: 'judge_settings_updated',
      payload: {
        defaultRounds: 3,
        defaultStartingScore: 4,
        presentationCategoryStartScore: 2,
        actionValue1: 0.1,
        actionValue2: 0.3
      }
    });

    expect(settingsRepo.upsertSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        defaultRounds: 3,
        defaultStartingScore: 4,
        presentationCategoryStartScore: 2,
        actionValue1: 0.1,
        actionValue2: 0.3
      })
    );
  });

  it('accepts WS messages in event/data format and updates the active match', async () => {
    const realtimeClient = new FakeRealtimeClient();
    const inboundRepo = {
      hasDedupeKey: vi.fn().mockResolvedValue(false),
      appendLog: vi.fn().mockResolvedValue(undefined)
    };
    const matchRepo = {
      getMatchById: vi.fn().mockResolvedValue(null),
      updateCompetitors: vi.fn().mockResolvedValue(undefined),
      resetMatch: vi.fn().mockResolvedValue(undefined),
      moveToRound: vi.fn().mockResolvedValue(undefined)
    };
    const scoreRepo = { resetCurrentRound: vi.fn().mockResolvedValue(undefined) };
    const sessionRepo = {
      clearSession: vi.fn().mockResolvedValue(undefined)
    };
    const settingsRepo = {
      upsertSettings: vi.fn().mockResolvedValue(undefined)
    };

    const service = new RealtimeService(
      realtimeClient as any,
      inboundRepo as any,
      matchRepo as any,
      scoreRepo as any,
      sessionRepo as any,
      settingsRepo as any
    );

    service.connect({
      baseUrl: 'http://localhost:8080',
      sessionId: 's1',
      accessToken: 't1',
      stationId: 'station-01',
      onStatus: () => undefined
    });

    await realtimeClient.emit({
      event: 'match_updated',
      data: {
        match: { id: 'mx-100', status: 'active' },
        competitors: { red: 'Competitor C', blue: 'Competitor D' }
      }
    });

    expect(settingsRepo.upsertSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        serverHasActiveMatch: true,
        serverActiveMatchId: 'mx-100',
        serverCompetitorRedName: 'Competitor C',
        serverCompetitorBlueName: 'Competitor D'
      })
    );
  });

  it('revokes the local session when judge_kicked arrives', async () => {
    const realtimeClient = new FakeRealtimeClient();
    const inboundRepo = {
      hasDedupeKey: vi.fn().mockResolvedValue(false),
      appendLog: vi.fn().mockResolvedValue(undefined)
    };
    const matchRepo = {
      getMatchById: vi.fn().mockResolvedValue(null),
      updateCompetitors: vi.fn().mockResolvedValue(undefined),
      resetMatch: vi.fn().mockResolvedValue(undefined),
      moveToRound: vi.fn().mockResolvedValue(undefined)
    };
    const scoreRepo = { resetCurrentRound: vi.fn().mockResolvedValue(undefined) };
    const sessionRepo = {
      clearSession: vi.fn().mockResolvedValue(undefined)
    };
    const settingsRepo = {
      upsertSettings: vi.fn().mockResolvedValue(undefined)
    };
    const disconnectSpy = vi.spyOn(realtimeClient, 'disconnect');

    const service = new RealtimeService(
      realtimeClient as any,
      inboundRepo as any,
      matchRepo as any,
      scoreRepo as any,
      sessionRepo as any,
      settingsRepo as any
    );

    service.connect({
      baseUrl: 'http://localhost:8080',
      sessionId: 's1',
      accessToken: 't1',
      stationId: 'station-01',
      onStatus: () => undefined
    });

    await realtimeClient.emit({
      type: 'judge_kicked',
      payload: {
        sessionId: 's1',
        stationId: 'station-01'
      }
    });

    expect(sessionRepo.clearSession).toHaveBeenCalledTimes(1);
    expect(disconnectSpy).toHaveBeenCalled();
  });

  it('emits a WS signal when a round and the match are completed', async () => {
    const realtimeClient = new FakeRealtimeClient();
    const service = new RealtimeService(
      realtimeClient as any,
      {
        hasDedupeKey: vi.fn().mockResolvedValue(false),
        appendLog: vi.fn().mockResolvedValue(undefined)
      } as any,
      {} as any,
      {} as any,
      {} as any,
      {} as any
    );

    service.notifyRoundCompleted({
      matchId: 'm1',
      roundNumber: 1,
      sessionId: 's1',
      stationId: 'station-01',
      judgeName: 'Judge 2',
      deviceId: 'dev-1'
    });
    service.notifyMatchCompleted({
      matchId: 'm1',
      finalRound: 2,
      checksum: 'abc',
      sessionId: 's1',
      stationId: 'station-01',
      judgeName: 'Judge 2',
      deviceId: 'dev-1'
    });

    expect(realtimeClient.sentEvents[0]?.type).toBe('judge_round_completed');
    expect(realtimeClient.sentEvents[1]?.type).toBe('judge_match_completed');
  });

  it('answers ping with pong and never answers a pong', async () => {
    const realtimeClient = new FakeRealtimeClient();
    const sendPongSpy = vi.spyOn(realtimeClient, 'sendPong');
    const service = new RealtimeService(
      realtimeClient as any,
      {
        hasDedupeKey: vi.fn().mockResolvedValue(false),
        appendLog: vi.fn().mockResolvedValue(undefined)
      } as any,
      {} as any,
      {} as any,
      {} as any,
      {} as any
    );

    service.connect({
      baseUrl: 'http://localhost:8080',
      sessionId: 's1',
      accessToken: 't1',
      stationId: 'station-01',
      onStatus: () => undefined
    });

    await realtimeClient.emit({
      type: 'ping',
      payload: {
        ts: '2026-03-20T15:00:00.000Z'
      }
    });

    expect(sendPongSpy).toHaveBeenCalledTimes(1);

    await realtimeClient.emit({ type: 'pong', payload: {} });

    expect(sendPongSpy).toHaveBeenCalledTimes(1);
    expect(realtimeClient.sentEvents).toEqual([]);
  });

  it('deletes the round the server reset, not the device current round', async () => {
    const realtimeClient = new FakeRealtimeClient();
    const scoreRepo = { resetCurrentRound: vi.fn().mockResolvedValue(undefined) };
    const service = new RealtimeService(
      realtimeClient as any,
      { hasDedupeKey: vi.fn().mockResolvedValue(false), appendLog: vi.fn().mockResolvedValue(undefined) } as any,
      { getMatchById: vi.fn().mockResolvedValue({ id: 'm1', currentRound: 2 }) } as any,
      scoreRepo as any,
      {} as any,
      {} as any
    );
    service.connect({
      baseUrl: 'http://localhost:8080',
      sessionId: 's1',
      accessToken: 't1',
      stationId: 'station-01',
      onStatus: () => undefined
    });

    await realtimeClient.emit({ type: 'reset_round', payload: { matchId: 'm1', round: 1 } });

    expect(scoreRepo.resetCurrentRound).toHaveBeenCalledWith('m1', 1);
  });

  it('keeps the session when another judge of the station disconnects', async () => {
    const { realtimeClient, sessionRepo, disconnectSpy } = buildConnectedService('s1');

    await realtimeClient.emit({
      type: 'station_disconnected',
      payload: { stationId: 'station-01', sessionId: 's2', reason: 'websocket_disconnected', issuedAt: '2026-10-31T10:00:00Z' }
    });
    await realtimeClient.emit({
      type: 'session_revoked',
      payload: { stationId: 'station-01', sessionId: 's3' }
    });

    expect(sessionRepo.clearSession).not.toHaveBeenCalled();
    expect(disconnectSpy).not.toHaveBeenCalled();
  });

  it('clears the session when its own station_disconnected arrives', async () => {
    const { realtimeClient, sessionRepo, disconnectSpy } = buildConnectedService('s1');

    await realtimeClient.emit({
      type: 'station_disconnected',
      payload: { stationId: 'station-01', sessionId: 's1', reason: 'websocket_disconnected', issuedAt: '2026-10-31T10:00:00Z' }
    });

    expect(sessionRepo.clearSession).toHaveBeenCalledTimes(1);
    expect(disconnectSpy).toHaveBeenCalled();
  });
});

function buildConnectedService(sessionId: string) {
  const realtimeClient = new FakeRealtimeClient();
  const inboundRepo = {
    hasDedupeKey: vi.fn().mockResolvedValue(false),
    appendLog: vi.fn().mockResolvedValue(undefined)
  };
  const matchRepo = {
    getMatchById: vi.fn().mockResolvedValue(null),
    updateCompetitors: vi.fn().mockResolvedValue(undefined),
    resetMatch: vi.fn().mockResolvedValue(undefined),
    moveToRound: vi.fn().mockResolvedValue(undefined)
  };
  const scoreRepo = { resetCurrentRound: vi.fn().mockResolvedValue(undefined) };
  const sessionRepo = { clearSession: vi.fn().mockResolvedValue(undefined) };
  const settingsRepo = { upsertSettings: vi.fn().mockResolvedValue(undefined) };
  const disconnectSpy = vi.spyOn(realtimeClient, 'disconnect');
  const service = new RealtimeService(
    realtimeClient as any,
    inboundRepo as any,
    matchRepo as any,
    scoreRepo as any,
    sessionRepo as any,
    settingsRepo as any
  );
  service.connect({
    baseUrl: 'http://localhost:8080',
    sessionId,
    accessToken: 't1',
    stationId: 'station-01',
    onStatus: () => undefined
  });
  return { realtimeClient, sessionRepo, disconnectSpy };
}
