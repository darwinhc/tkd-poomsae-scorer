import { describe, expect, it, vi } from 'vitest';

vi.mock('@/infrastructure/security/deviceIdentity', () => ({
  getOrCreateDeviceId: vi.fn(async () => 'dev-1')
}));

describe('sessionService', () => {
  it('persists the judge identity when connecting to a station', async () => {
    const { SessionService } = await import('@/application/services/sessionService');
    let savedJudge = '';
    const service = new SessionService(
      {
        getActiveBackend: async () => ({ id: 'b1', baseUrl: 'http://127.0.0.1:8080', bootstrapToken: 't' }),
        saveBackend: async () => ({}),
        saveStations: async () => undefined,
        listActiveStations: async () => []
      } as any,
      {
        saveSession: async () => undefined,
        getSession: async () => null,
        getAccessToken: async () => null,
        clearSession: async () => undefined,
        markRevoked: async () => undefined
      } as any,
      {
        getSettings: async () => ({ judgeName: 'Judge 1' }),
        upsertSettings: async (input: any) => {
          savedJudge = input.judgeName;
          return input;
        }
      } as any,
      {
        connectStation: async () => ({
          connected: true,
          sessionId: 'sess-1',
          accessToken: 'token',
          station: { id: 'station-01', name: 'Station 1' }
        })
      } as any
    );

    await service.connectStation({ stationId: 'station-01', credential: '1234' });
    expect(savedJudge).toBe('Judge 1');
  });

  it('restores the persisted session and distinguishes invalid vs offline', async () => {
    const { SessionService } = await import('@/application/services/sessionService');
    const revoked = { value: false };
    const service = new SessionService(
      {
        getActiveBackend: async () => ({ baseUrl: 'http://127.0.0.1:8080' })
      } as any,
      {
        getSession: async () => ({ id: 's' }),
        getAccessToken: async () => 'token',
        markRevoked: async () => {
          revoked.value = true;
        }
      } as any,
      {} as any,
      {
        validateSession: async () => false
      } as any
    );

    const status = await service.restoreValidatedSession();
    expect(status).toBe('invalid');
    expect(revoked.value).toBe(true);
  });

  it('retries the connection with replacement when the judge is already connected', async () => {
    const { SessionService } = await import('@/application/services/sessionService');
    const connectStation = vi
      .fn()
      .mockRejectedValueOnce(new Error('Connection rejected (409): Judge already connected'))
      .mockResolvedValueOnce({
        connected: true,
        sessionId: 'sess-2',
        accessToken: 'token-2',
        station: { id: 'station-01', name: 'Station 1' }
      });

    const service = new SessionService(
      {
        getActiveBackend: async () => ({ id: 'b1', baseUrl: 'http://192.168.1.20:8080', bootstrapToken: 't' })
      } as any,
      {
        saveSession: async () => undefined
      } as any,
      {
        getSettings: async () => ({ judgeName: 'Judge 2' }),
        upsertSettings: async (input: any) => input
      } as any,
      {
        connectStation
      } as any
    );

    await service.connectStation({ stationId: 'station-01', credential: '1234' });
    expect(connectStation).toHaveBeenCalledTimes(2);
    expect(connectStation.mock.calls[1][2]).toMatchObject({ replaceExistingJudgeSession: true });
  });

  it('retries with replacement when the connect error carries HTTP status 409', async () => {
    const { SessionService } = await import('@/application/services/sessionService');
    const { LocalizedError } = await import('@/i18n/LocalizedError');
    const connectStation = vi
      .fn()
      .mockRejectedValueOnce(new LocalizedError('errors.connectionRejected', { status: 409 }, { status: 409 }))
      .mockResolvedValueOnce({
        connected: true,
        sessionId: 'sess-3',
        accessToken: 'token-3',
        station: { id: 'station-01', name: 'Station 1' }
      });

    const service = new SessionService(
      {
        getActiveBackend: async () => ({ id: 'b1', baseUrl: 'http://192.168.1.20:8080', bootstrapToken: 't' })
      } as any,
      {
        saveSession: async () => undefined
      } as any,
      {
        getSettings: async () => ({ judgeName: 'Judge 3' }),
        upsertSettings: async (input: any) => input
      } as any,
      {
        connectStation
      } as any
    );

    await service.connectStation({ stationId: 'station-01', credential: '1234' });
    expect(connectStation).toHaveBeenCalledTimes(2);
    expect(connectStation.mock.calls[1][2]).toMatchObject({ replaceExistingJudgeSession: true });
  });

  it('does not retry when the connect error is not a duplicate-session conflict', async () => {
    const { SessionService } = await import('@/application/services/sessionService');
    const connectStation = vi.fn().mockRejectedValueOnce(new Error('Connection rejected (401): Invalid credential'));

    const service = new SessionService(
      {
        getActiveBackend: async () => ({ id: 'b1', baseUrl: 'http://192.168.1.20:8080', bootstrapToken: 't' })
      } as any,
      {} as any,
      {
        getSettings: async () => ({ judgeName: 'Judge 3' })
      } as any,
      {
        connectStation
      } as any
    );

    await expect(service.connectStation({ stationId: 'station-01', credential: '1234' })).rejects.toThrow('(401)');
    expect(connectStation).toHaveBeenCalledTimes(1);
  });

  it('allows a local session without a backend', async () => {
    const { SessionService } = await import('@/application/services/sessionService');
    const service = new SessionService(
      {
        getActiveBackend: async () => null
      } as any,
      {
        saveSession: async () => undefined,
        getSession: async () => ({ stationId: 'local-offline' }),
        getAccessToken: async () => null
      } as any,
      {
        getSettings: async () => ({ judgeName: 'Judge 1' }),
        upsertSettings: async () => ({})
      } as any,
      {} as any
    );

    const state = await service.restoreValidatedSession();
    expect(state).toBe('valid');
  });
});
