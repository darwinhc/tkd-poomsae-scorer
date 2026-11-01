import type {
  IInboundServerEventRepository,
  IMatchRepository,
  IRealtimeClient,
  IScoreEventRepository,
  ISettingsRepository,
  ISessionRepository
} from '@/application/ports/repositories';
import type { RealtimeEvent } from '@/domain/models/contracts';
import { mapRealtimeEvent } from '@/domain/services/realtimeHandler';
import { t } from '@/i18n';
import { useAppStore } from '@/store/appStore';
import { createId } from '@/utils/id';
import { nowIso } from '@/utils/time';

export class RealtimeService {
  constructor(
    private readonly realtimeClient: IRealtimeClient,
    private readonly inboundRepo: IInboundServerEventRepository,
    private readonly matchRepo: IMatchRepository,
    private readonly scoreRepo: IScoreEventRepository,
    private readonly sessionRepo: ISessionRepository,
    private readonly settingsRepo: ISettingsRepository
  ) {}

  private boundSessionId: string | null = null;

  connect(input: {
    baseUrl: string;
    sessionId: string;
    accessToken: string;
    stationId: string;
    onStatus: (status: 'connecting' | 'connected' | 'disconnected') => void;
  }) {
    this.boundSessionId = input.sessionId;
    this.realtimeClient.connect({
      ...input,
      onMessage: async (message) => {
        const event = normalizeRealtimeEvent(message);
        if (!event) {
          return;
        }
        try {
          await this.handleEvent(event);
        } catch {
          // Ignore malformed inbound event processing to keep websocket channel alive.
        }
      }
    });
  }

  disconnect() {
    this.realtimeClient.disconnect();
  }

  notifyRoundCompleted(input: {
    matchId: string;
    roundNumber: number;
    sessionId: string;
    stationId: string;
    judgeName: string;
    deviceId: string;
  }) {
    this.realtimeClient.sendEvent('judge_round_completed', {
      matchId: input.matchId,
      roundNumber: input.roundNumber,
      sessionId: input.sessionId,
      stationId: input.stationId,
      judgeName: input.judgeName,
      deviceId: input.deviceId,
      finishedAt: nowIso()
    });
  }

  notifyMatchCompleted(input: {
    matchId: string;
    finalRound: number;
    checksum: string;
    sessionId: string;
    stationId: string;
    judgeName: string;
    deviceId: string;
  }) {
    this.realtimeClient.sendEvent('judge_match_completed', {
      matchId: input.matchId,
      finalRound: input.finalRound,
      checksum: input.checksum,
      sessionId: input.sessionId,
      stationId: input.stationId,
      judgeName: input.judgeName,
      deviceId: input.deviceId,
      finishedAt: nowIso()
    });
  }

  notifyResetRequested(input: {
    matchId: string;
    roundNumber: number;
    resetTarget: 'TECHNIQUE' | 'PRESENTATION' | 'ROUND' | 'MATCH';
    sessionId: string;
    stationId: string;
    judgeName: string;
    deviceId: string;
    reason?: string;
  }) {
    this.realtimeClient.sendEvent('judge_reset_requested', {
      matchId: input.matchId,
      roundNumber: input.roundNumber,
      resetTarget: input.resetTarget,
      sessionId: input.sessionId,
      stationId: input.stationId,
      judgeName: input.judgeName,
      deviceId: input.deviceId,
      reason: input.reason ?? 'manual_reset',
      requestedAt: nowIso()
    });
  }

  private async handleEvent(event: RealtimeEvent) {
    const mapped = mapRealtimeEvent(event);
    if (mapped.action.type === 'ping') {
      // Keep-alive: answered once with `pong`; a `pong` (mapped to `pong`) is never answered.
      this.realtimeClient.sendPong({
        echo: event.payload,
        serverTime: pickString((event.payload as Record<string, unknown>)?.ts, (event.payload as Record<string, unknown>)?.timestamp),
        clientTime: nowIso()
      });
      return;
    }

    if (mapped.action.type === 'none' || mapped.action.type === 'pong') {
      return;
    }

    if (isAddressedToAnotherSession(mapped.action, this.boundSessionId)) {
      // Another judge of the station disconnected or was revoked: this session stays active.
      return;
    }

    if (!mapped.shouldPersist) {
      return;
    }

    const exists = await this.inboundRepo.hasDedupeKey(mapped.dedupeKey);
    if (exists) {
      return;
    }

    const now = nowIso();
    await this.inboundRepo.appendLog({
      id: createId(),
      eventType: event.type,
      dedupeKey: mapped.dedupeKey,
      payload: JSON.stringify(event.payload),
      receivedAt: now,
      processedAt: now
    });

    switch (mapped.action.type) {
      case 'reset_match':
        await this.matchRepo.resetMatch(mapped.action.matchId);
        break;
      case 'reset_round': {
        // Server-side reset: the server deleted these events, so the device deletes the same ones.
        const match = await this.matchRepo.getMatchById(mapped.action.matchId);
        if (match) {
          await this.scoreRepo.resetCurrentRound(match.id, mapped.action.roundNumber ?? match.currentRound);
        }
        break;
      }
      case 'competitors_by_color': {
        const redName = normalizeCompetitorName(mapped.action.redName, t('common.red'));
        const blueName = normalizeCompetitorName(mapped.action.blueName, t('common.blue'));
        await this.settingsRepo.upsertSettings({
          serverHasActiveMatch: true,
          serverActiveMatchId: mapped.action.matchId,
          serverCompetitorRedName: redName,
          serverCompetitorBlueName: blueName,
          serverMatchUpdatedAt: nowIso()
        });
        useAppStore.getState().bumpSettingsVersion();

        const match = await this.matchRepo.getMatchById(mapped.action.matchId);
        if (!match) {
          break;
        }
        const left = match.leftSideColor === 'RED' ? redName : blueName;
        const right = match.rightSideColor === 'RED' ? redName : blueName;
        await this.matchRepo.updateCompetitors(mapped.action.matchId, left, right);
        break;
      }
      case 'active_match_state': {
        const redName = normalizeCompetitorName(mapped.action.redName, t('common.red'));
        const blueName = normalizeCompetitorName(mapped.action.blueName, t('common.blue'));
        await this.settingsRepo.upsertSettings({
          serverHasActiveMatch: mapped.action.hasActiveMatch,
          serverActiveMatchId: mapped.action.hasActiveMatch ? mapped.action.matchId ?? null : null,
          serverCompetitorRedName: mapped.action.hasActiveMatch ? redName : null,
          serverCompetitorBlueName: mapped.action.hasActiveMatch ? blueName : null,
          serverMatchUpdatedAt: nowIso()
        });
        useAppStore.getState().bumpSettingsVersion();

        if (mapped.action.hasActiveMatch && mapped.action.matchId) {
          const match = await this.matchRepo.getMatchById(mapped.action.matchId);
          if (match) {
            const left = match.leftSideColor === 'RED' ? redName : blueName;
            const right = match.rightSideColor === 'RED' ? redName : blueName;
            await this.matchRepo.updateCompetitors(match.id, left, right);
          }
        }
        break;
      }
      case 'judge_settings_updated': {
        const update: Record<string, number> = {};
        if (mapped.action.defaultRounds !== undefined && Number.isFinite(mapped.action.defaultRounds)) {
          update.defaultRounds = clampInt(mapped.action.defaultRounds, 1, 10);
        }
        if (mapped.action.defaultStartingScore !== undefined && Number.isFinite(mapped.action.defaultStartingScore)) {
          update.defaultStartingScore = clamp(mapped.action.defaultStartingScore, 0, 20);
        }
        if (
          mapped.action.presentationCategoryStartScore !== undefined &&
          Number.isFinite(mapped.action.presentationCategoryStartScore)
        ) {
          update.presentationCategoryStartScore = clamp(mapped.action.presentationCategoryStartScore, 0, 2);
        }
        if (mapped.action.actionValue1 !== undefined && Number.isFinite(mapped.action.actionValue1)) {
          update.actionValue1 = clamp(mapped.action.actionValue1, 0.1, 1);
        }
        if (mapped.action.actionValue2 !== undefined && Number.isFinite(mapped.action.actionValue2)) {
          update.actionValue2 = clamp(mapped.action.actionValue2, 0.1, 2);
        }

        if (Object.keys(update).length > 0) {
          await this.settingsRepo.upsertSettings(update);
          useAppStore.getState().bumpSettingsVersion();
        }
        break;
      }
      case 'round_changed':
        await this.matchRepo.moveToRound(mapped.action.matchId, mapped.action.round);
        break;
      case 'station_disconnected':
        await this.sessionRepo.clearSession();
        this.realtimeClient.disconnect();
        break;
      case 'session_revoked':
      case 'judge_kicked':
        await this.sessionRepo.clearSession();
        this.realtimeClient.disconnect();
        break;
      default:
        break;
    }
  }
}

function isAddressedToAnotherSession(action: { type: string; targetSessionId?: string }, boundSessionId: string | null): boolean {
  if (action.type !== 'session_revoked' && action.type !== 'judge_kicked' && action.type !== 'station_disconnected') {
    return false;
  }
  return Boolean(action.targetSessionId && boundSessionId && action.targetSessionId !== boundSessionId);
}

function normalizeCompetitorName(value: string | undefined, fallback: string): string {
  const trimmed = (value ?? '').trim();
  return trimmed.length > 0 ? trimmed : fallback;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function clampInt(value: number, min: number, max: number): number {
  return Math.round(clamp(value, min, max));
}

function normalizeRealtimeEvent(raw: unknown): RealtimeEvent | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return null;
  }

  const message = raw as Record<string, unknown>;
  const type = pickString(message.type, message.event, message.name);
  if (!type) {
    return null;
  }

  const payload = asRecord(message.payload ?? message.data ?? message.body);
  return {
    type: type as RealtimeEvent['type'],
    payload
  };
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

function asRecord(input: unknown): Record<string, unknown> {
  if (input && typeof input === 'object' && !Array.isArray(input)) {
    return input as Record<string, unknown>;
  }
  return {};
}
