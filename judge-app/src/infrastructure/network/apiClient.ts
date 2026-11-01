import type { IApiClient } from '@/application/ports/repositories';
import type {
  AckResponse,
  ActiveMatchSnapshot,
  FinalizePayload,
  ScoreEventPayload,
  StationConnectResponse
} from '@/domain/models/contracts';
import type { Station } from '@/domain/models/entities';
import { LocalizedError } from '@/i18n/LocalizedError';

function buildNetworkErrorWithCause(baseUrl: string, cause?: unknown): LocalizedError {
  try {
    const url = new URL(baseUrl);
    const host = url.hostname.toLowerCase();
    if (host === 'localhost' || host === '127.0.0.1' || host === '::1') {
      return new LocalizedError('errors.networkLocalhost', undefined, { cause });
    }
    if (url.protocol === 'https:' && isPrivateHost(host)) {
      return new LocalizedError('errors.networkLocalHttps', undefined, { cause });
    }
  } catch {
    // Invalid URL: fall through to the generic network error.
  }
  const causeText = extractCauseText(cause);
  return causeText
    ? new LocalizedError('errors.networkGenericWithDetail', { baseUrl, detail: causeText }, { cause })
    : new LocalizedError('errors.networkGeneric', { baseUrl }, { cause });
}

class HttpApiClient implements IApiClient {
  async health(baseUrl: string): Promise<boolean> {
    try {
      const response = await fetch(`${baseUrl}/health`);
      return response.ok;
    } catch {
      return false;
    }
  }

  async listActiveStations(baseUrl: string, bootstrapToken?: string): Promise<Station[]> {
    let response: Response;
    try {
      response = await fetch(`${baseUrl}/stations/active`, {
        headers: {
          ...(bootstrapToken ? { Authorization: `Bearer ${bootstrapToken}` } : {})
        }
      });
    } catch (error) {
      throw buildNetworkErrorWithCause(baseUrl, error);
    }

    if (!response.ok) {
      throw new LocalizedError('errors.loadStationsFailed', { status: response.status }, { status: response.status });
    }

    return response.json();
  }

  async fetchActiveMatchSnapshot(baseUrl: string, stationId: string, accessToken?: string): Promise<ActiveMatchSnapshot | null> {
    const url = `${baseUrl}/stations/${encodeURIComponent(stationId)}/active-match-state?_ts=${Date.now()}`;
    let response: Response;
    try {
      response = await fetch(url, {
        cache: 'no-store',
        headers: {
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
          'Cache-Control': 'no-cache, no-store, must-revalidate',
          Pragma: 'no-cache',
          Accept: 'application/json'
        }
      });
    } catch (error) {
      throw buildNetworkErrorWithCause(baseUrl, error);
    }

    if (response.status === 404) {
      return null;
    }

    if (!response.ok) {
      throw new LocalizedError('errors.readActiveMatchFailed', { status: response.status }, { status: response.status });
    }

    const payload = await response.json().catch(() => null);
    return parseActiveMatchStateJson(payload);
  }

  async connectStation(
    baseUrl: string,
    token: string | undefined,
    payload: {
      stationId: string;
      judgeName: string;
      credential: string;
      deviceId: string;
      replaceExistingJudgeSession?: boolean;
    }
  ): Promise<StationConnectResponse> {
    let response: Response;
    try {
      response = await fetch(`${baseUrl}/stations/connect`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: JSON.stringify(payload)
      });
    } catch (error) {
      throw buildNetworkErrorWithCause(baseUrl, error);
    }

    if (!response.ok) {
      let detail = '';
      try {
        const payload = await response.json();
        detail = payload?.detail ? String(payload.detail) : '';
      } catch {
        detail = '';
      }
      throw detail
        ? new LocalizedError('errors.connectionRejectedWithDetail', { status: response.status, detail }, { status: response.status })
        : new LocalizedError('errors.connectionRejected', { status: response.status }, { status: response.status });
    }

    return response.json();
  }

  async postScoreEvent(baseUrl: string, accessToken: string, payload: ScoreEventPayload): Promise<AckResponse> {
    let response: Response;
    try {
      response = await fetch(`${baseUrl}/score-events`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
          'Idempotency-Key': payload.idempotencyKey
        },
        body: JSON.stringify(payload)
      });
    } catch (error) {
      throw buildNetworkErrorWithCause(baseUrl, error);
    }

    if (!response.ok) {
      const code = await readErrorCode(response);
      throw new LocalizedError('errors.scoreEventSyncFailed', { status: response.status }, { status: response.status, code });
    }

    return response.json();
  }

  async finalizeMatch(baseUrl: string, accessToken: string, payload: FinalizePayload): Promise<AckResponse> {
    let response: Response;
    const canonicalMatchId = resolveRequiredMatchId(payload);
    const finalizeBody = {
      ...payload,
      matchId: canonicalMatchId
    };
    try {
      response = await fetch(`${baseUrl}/matches/finalize`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(finalizeBody)
      });
    } catch (error) {
      throw buildNetworkErrorWithCause(baseUrl, error);
    }

    if (!response.ok) {
      const code = await readErrorCode(response);
      throw new LocalizedError('errors.finalizeFailed', { status: response.status }, { status: response.status, code });
    }

    return response.json();
  }

  async validateSession(baseUrl: string, accessToken: string): Promise<boolean> {
    let response: Response;
    try {
      response = await fetch(`${baseUrl}/health`, {
        headers: {
          Authorization: `Bearer ${accessToken}`
        }
      });
    } catch {
      return false;
    }
    if (response.status === 401 || response.status === 403) {
      return false;
    }
    return true;
  }
}

class MockApiClient implements IApiClient {
  async health(): Promise<boolean> {
    return true;
  }

  async listActiveStations(): Promise<Station[]> {
    const now = new Date().toISOString();
    return [
      { id: 'station-01', name: 'Station 1', status: 'active', updatedAt: now },
      { id: 'station-02', name: 'Station 2', status: 'active', updatedAt: now }
    ];
  }

  async fetchActiveMatchSnapshot(): Promise<ActiveMatchSnapshot | null> {
    return {
      hasActiveMatch: false
    };
  }

  async connectStation(
    _baseUrl: string,
    _token: string | undefined,
    payload: {
      stationId: string;
      judgeName: string;
      credential: string;
      deviceId: string;
      replaceExistingJudgeSession?: boolean;
    }
  ): Promise<StationConnectResponse> {
    if (!payload.credential) {
      throw new LocalizedError('errors.credentialRequired');
    }

    return {
      connected: true,
      sessionId: `sess-${payload.stationId}`,
      accessToken: 'mock-long-lived-token',
      expiresAt: new Date(Date.now() + 1000 * 60 * 60 * 24 * 30).toISOString(),
      station: {
        id: payload.stationId,
        name: payload.stationId === 'station-01' ? 'Station 1' : 'Station 2'
      }
    };
  }

  async postScoreEvent(
    _baseUrl: string,
    _accessToken: string,
    payload: ScoreEventPayload
  ): Promise<AckResponse> {
    return {
      acknowledged: true,
      eventId: payload.eventId,
      serverReceivedAt: new Date().toISOString()
    };
  }

  async finalizeMatch(
    _baseUrl: string,
    _accessToken: string,
    payload: FinalizePayload
  ): Promise<AckResponse> {
    return {
      acknowledged: true,
      eventId: payload.matchId,
      serverReceivedAt: new Date().toISOString()
    };
  }

  async validateSession(): Promise<boolean> {
    return true;
  }
}

export function createApiClient(): IApiClient {
  if (process.env.EXPO_PUBLIC_USE_MOCK_BACKEND === '1') {
    return new MockApiClient();
  }

  return new HttpApiClient();
}

function parseActiveMatchStateJson(input: unknown): ActiveMatchSnapshot | null {
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    return null;
  }
  const payload = input as Record<string, unknown>;
  const hasActiveMatch =
    pickBoolean(payload.hasActiveMatch, payload.has_active_match, payload.active, payload.isActive) ?? false;
  const matchId = pickString(payload.matchId, payload.match_id, payload.activeMatchId, payload.active_match_id);
  const redName = pickString(payload.competitorRedName, payload.competitor_red_name, payload.redName, payload.red_name);
  const blueName = pickString(payload.competitorBlueName, payload.competitor_blue_name, payload.blueName, payload.blue_name);

  return {
    hasActiveMatch,
    matchId: hasActiveMatch ? matchId ?? undefined : undefined,
    redName: hasActiveMatch ? redName ?? undefined : undefined,
    blueName: hasActiveMatch ? blueName ?? undefined : undefined
  };
}

/** The `code` field of a backend error body (`{"detail": ..., "code": ...}`), when present. */
async function readErrorCode(response: Response): Promise<string | undefined> {
  try {
    const body = (await response.json()) as { code?: unknown } | null;
    return typeof body?.code === 'string' && body.code.trim().length > 0 ? body.code.trim() : undefined;
  } catch {
    return undefined;
  }
}

function extractCauseText(cause: unknown): string {
  if (!cause) return '';
  if (typeof cause === 'string') return cause;
  if (typeof cause === 'object') {
    const maybeMessage = (cause as { message?: unknown }).message;
    if (typeof maybeMessage === 'string' && maybeMessage.trim().length > 0) {
      return maybeMessage.trim();
    }
  }
  return '';
}

function pickString(...values: unknown[]): string | undefined {
  for (const value of values) {
    if (typeof value === 'string') {
      const trimmed = value.trim();
      if (trimmed.length > 0) {
        return trimmed;
      }
    }
  }
  return undefined;
}

function pickBoolean(...values: unknown[]): boolean | undefined {
  for (const value of values) {
    if (typeof value === 'boolean') {
      return value;
    }
    if (typeof value === 'number') {
      if (value === 1) return true;
      if (value === 0) return false;
    }
    if (typeof value === 'string') {
      const normalized = value.trim().toLowerCase();
      if (['true', '1', 'yes', 'active', 'started', 'running'].includes(normalized)) return true;
      if (['false', '0', 'no', 'inactive', 'finished', 'ended', 'closed'].includes(normalized)) return false;
    }
  }
  return undefined;
}

function isPrivateHost(host: string): boolean {
  if (host === 'localhost' || host === '127.0.0.1' || host === '::1') {
    return true;
  }
  if (/^10\./.test(host)) {
    return true;
  }
  if (/^192\.168\./.test(host)) {
    return true;
  }
  const match = host.match(/^172\.(\d{1,3})\./);
  if (match) {
    const second = Number(match[1]);
    if (second >= 16 && second <= 31) {
      return true;
    }
  }
  return false;
}

function resolveRequiredMatchId(payload: FinalizePayload): string {
  const direct = typeof payload.matchId === 'string' ? payload.matchId.trim() : '';
  if (direct.length > 0) {
    return direct;
  }

  const legacy = typeof (payload as { match_id?: unknown }).match_id === 'string'
    ? (payload as { match_id?: string }).match_id?.trim() ?? ''
    : '';
  if (legacy.length > 0) {
    return legacy;
  }

  throw new LocalizedError('errors.finalizeMatchIdRequired');
}
