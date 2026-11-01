import type { IApiClient, IConnectionRepository, ISettingsRepository, ISessionRepository } from '@/application/ports/repositories';
import { APP_PROTOCOL_VERSION, DEFAULT_STATION_ID, LOCAL_OFFLINE_STATION_NAME } from '@/constants/defaults';
import { validateQrPayload, validateStationConnection } from '@/domain/services/connectionValidation';
import { t } from '@/i18n';
import { LocalizedError } from '@/i18n/LocalizedError';
import { getOrCreateDeviceId } from '@/infrastructure/security/deviceIdentity';
import { createId } from '@/utils/id';
import { nowIso } from '@/utils/time';

export class SessionService {
  constructor(
    private readonly connectionRepo: IConnectionRepository,
    private readonly sessionRepo: ISessionRepository,
    private readonly settingsRepo: ISettingsRepository,
    private readonly apiClient: IApiClient
  ) {}

  async saveFromQr(raw: string) {
    const payload = validateQrPayload(raw);
    await this.sessionRepo.clearSession();
    const backend = await this.connectionRepo.saveBackend(payload);
    await this.settingsRepo.upsertSettings({ defaultStationId: payload.stationId });
    return {
      backend,
      stationId: payload.stationId,
      stationName: payload.stationName ?? null
    };
  }

  async saveManualBackend(baseUrl: string, bootstrapToken?: string) {
    const expiresAt = new Date(Date.now() + 1000 * 60 * 60 * 24 * 365).toISOString();
    const settings = await this.settingsRepo.getSettings();
    await this.sessionRepo.clearSession();
    return this.connectionRepo.saveBackend({
      baseUrl,
      stationId: settings.defaultStationId || DEFAULT_STATION_ID,
      bootstrapToken,
      protocolVersion: APP_PROTOCOL_VERSION,
      expiresAt,
      environment: 'manual',
      tournamentId: 'manual'
    });
  }

  async refreshStations() {
    const backend = await this.connectionRepo.getActiveBackend();
    if (!backend) {
      throw new LocalizedError('errors.saveServerFirst');
    }

    const stations = await this.apiClient.listActiveStations(backend.baseUrl, backend.bootstrapToken ?? undefined);
    await this.connectionRepo.saveStations(stations);
    return stations;
  }

  async connectStation(input: { stationId: string; credential: string; judgeName?: string }) {
    const backend = await this.connectionRepo.getActiveBackend();
    if (!backend) {
      throw new LocalizedError('errors.serverNotConfigured');
    }

    const settings = await this.settingsRepo.getSettings();
    const judgeName = input.judgeName?.trim() || settings.judgeName;
    const deviceId = await getOrCreateDeviceId();

    validateStationConnection({
      stationId: input.stationId,
      credential: input.credential,
      judgeName,
      deviceId
    });

    const connectPayload = {
      stationId: input.stationId,
      credential: input.credential,
      judgeName,
      deviceId
    };

    let response;
    try {
      response = await this.apiClient.connectStation(backend.baseUrl, backend.bootstrapToken ?? undefined, connectPayload);
    } catch (error) {
      if (!shouldReplaceExistingSession(error)) {
        throw error;
      }
      response = await this.apiClient.connectStation(backend.baseUrl, backend.bootstrapToken ?? undefined, {
        ...connectPayload,
        replaceExistingJudgeSession: true
      });
    }

    const now = nowIso();
    const session = {
      id: createId(),
      backendServerId: backend.id,
      stationId: response.station.id,
      stationName: response.station.name,
      judgeName,
      deviceId,
      sessionId: response.sessionId,
      tokenExpiresAt: response.expiresAt,
      lastValidatedAt: now,
      connectionStatus: 'connected' as const,
      createdAt: now,
      updatedAt: now
    };

    await this.sessionRepo.saveSession(session, response.accessToken);
    await this.settingsRepo.upsertSettings({ judgeName });

    return session;
  }

  async refreshActiveMatchSnapshot() {
    const [backend, session, token] = await Promise.all([
      this.connectionRepo.getActiveBackend(),
      this.sessionRepo.getSession(),
      this.sessionRepo.getAccessToken()
    ]);

    if (!backend || !session || session.stationId === 'local-offline') {
      return null;
    }

    const now = nowIso();
    const snapshot = await this.apiClient.fetchActiveMatchSnapshot(backend.baseUrl, session.stationId, token ?? undefined);
    if (!snapshot) {
      await this.settingsRepo.upsertSettings({
        serverHasActiveMatch: false,
        serverActiveMatchId: null,
        serverCompetitorRedName: null,
        serverCompetitorBlueName: null,
        serverMatchUpdatedAt: now
      });
      return {
        hasActiveMatch: false
      };
    }

    const redName = normalizeCompetitorName(snapshot.redName, t('common.red'));
    const blueName = normalizeCompetitorName(snapshot.blueName, t('common.blue'));
    await this.settingsRepo.upsertSettings({
      serverHasActiveMatch: snapshot.hasActiveMatch,
      serverActiveMatchId: snapshot.hasActiveMatch ? snapshot.matchId ?? null : null,
      serverCompetitorRedName: snapshot.hasActiveMatch ? redName : null,
      serverCompetitorBlueName: snapshot.hasActiveMatch ? blueName : null,
      serverMatchUpdatedAt: now
    });

    return snapshot;
  }

  async startLocalSession(input?: { judgeName?: string }) {
    const settings = await this.settingsRepo.getSettings();
    const judgeName = input?.judgeName?.trim() || settings.judgeName;
    if (!judgeName) {
      throw new LocalizedError('errors.judgeNameRequired');
    }

    const deviceId = await getOrCreateDeviceId();
    const now = nowIso();
    const session = {
      id: createId(),
      backendServerId: 'local-offline',
      stationId: 'local-offline',
      stationName: LOCAL_OFFLINE_STATION_NAME,
      judgeName,
      deviceId,
      sessionId: `local-${createId()}`,
      tokenExpiresAt: null,
      lastValidatedAt: now,
      connectionStatus: 'connected' as const,
      createdAt: now,
      updatedAt: now
    };

    await this.sessionRepo.saveSession(session, null);
    await this.settingsRepo.upsertSettings({ judgeName });
    return session;
  }

  async restoreValidatedSession(): Promise<'valid' | 'invalid' | 'missing' | 'offline'> {
    const [session, backend, token] = await Promise.all([
      this.sessionRepo.getSession(),
      this.connectionRepo.getActiveBackend(),
      this.sessionRepo.getAccessToken()
    ]);

    if (!session) {
      return 'missing';
    }

    if (session.connectionStatus === 'revoked' || session.connectionStatus === 'disconnected') {
      await this.sessionRepo.clearSession();
      return 'invalid';
    }

    if (session.stationId === 'local-offline') {
      return 'valid';
    }

    if (!backend || !token) {
      return 'missing';
    }

    try {
      const valid = await this.apiClient.validateSession(backend.baseUrl, token);
      if (!valid) {
        await this.sessionRepo.markRevoked();
        return 'invalid';
      }
      return 'valid';
    } catch {
      return 'offline';
    }
  }
}

function normalizeCompetitorName(value: string | undefined, fallback: string): string {
  const trimmed = (value ?? '').trim();
  return trimmed.length > 0 ? trimmed : fallback;
}

function shouldReplaceExistingSession(error: unknown): boolean {
  if (!error || typeof error !== 'object') {
    return false;
  }
  if ((error as { status?: unknown }).status === 409) {
    return true;
  }
  const message = typeof (error as { message?: unknown }).message === 'string' ? (error as { message: string }).message : '';
  if (!message) {
    return false;
  }
  const normalized = message.toLowerCase();
  return (
    normalized.includes('(409)') ||
    normalized.includes(' 409') ||
    normalized.includes('already connected') ||
    normalized.includes('operator_replaced')
  );
}
