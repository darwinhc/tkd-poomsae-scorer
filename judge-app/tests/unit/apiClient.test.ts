import { afterEach, describe, expect, it, vi } from 'vitest';
import { createApiClient } from '@/infrastructure/network/apiClient';

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body)
  } as unknown as Response;
}

describe('apiClient.fetchActiveMatchSnapshot', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('reads the active match only from the active-match-state JSON endpoint', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, {
        hasActiveMatch: true,
        matchId: 'm-1',
        competitorRedName: 'Competitor A',
        competitorBlueName: 'Competitor B'
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    const snapshot = await createApiClient().fetchActiveMatchSnapshot('http://192.168.1.20:8080', 'station-01', 'token');

    expect(snapshot).toEqual({ hasActiveMatch: true, matchId: 'm-1', redName: 'Competitor A', blueName: 'Competitor B' });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).toContain('/stations/station-01/active-match-state');
  });

  it('returns null on 404 without falling back to any HTML page', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(404, { detail: 'Not found' }));
    vi.stubGlobal('fetch', fetchMock);

    const snapshot = await createApiClient().fetchActiveMatchSnapshot('http://192.168.1.20:8080', 'station-01');

    expect(snapshot).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('throws an English error for other HTTP failures', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(500, {})));

    await expect(createApiClient().fetchActiveMatchSnapshot('http://192.168.1.20:8080', 'station-01')).rejects.toThrow(
      'Could not read the active match (500)'
    );
  });
});

describe('apiClient.postScoreEvent', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('keeps the HTTP status and the server error code on failures', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(409, { detail: 'Match is closed', code: 'match_closed' })));

    const error = await createApiClient()
      .postScoreEvent('http://192.168.1.20:8080', 'token', { idempotencyKey: 'k' } as any)
      .catch((caught) => caught);

    expect(error).toMatchObject({ status: 409, code: 'match_closed' });
  });
});
