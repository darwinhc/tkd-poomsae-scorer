import { container } from '@/application/container';
import { startConnectivityMonitor } from '@/infrastructure/network/connectivityMonitor';
import { useAppStore } from '@/store/appStore';
import { validateSettings } from '@/domain/services/settingsValidation';
import type { AthleteSide, ScoreTarget } from '@/domain/models/entities';
import { LocalizedError } from '@/i18n/LocalizedError';
import { createId } from '@/utils/id';

let stopMonitor: (() => void) | null = null;

export class AppFacade {
  async init() {
    const { recoveryService, sessionService, syncEngine, realtimeService, retentionService } = container.services;
    const { sessionRepo, connectionRepo } = container.repos;
    const setBoot = useAppStore.getState().setBoot;
    const setWsStatus = useAppStore.getState().setWsStatus;

    const { settings, activeMatch } = await recoveryService.bootstrap();
    const sessionState = await sessionService.restoreValidatedSession();
    let hasSession = false;

    if (sessionState === 'valid' || sessionState === 'offline') {
      const [session, token, backend] = await Promise.all([
        sessionRepo.getSession(),
        sessionRepo.getAccessToken(),
        connectionRepo.getActiveBackend()
      ]);
      if (session?.stationId === 'local-offline') {
        hasSession = true;
        setWsStatus('disconnected');
      } else if (session && token && backend) {
        hasSession = true;
        realtimeService.connect({
          baseUrl: backend.baseUrl,
          sessionId: session.sessionId,
          stationId: session.stationId,
          accessToken: token,
          onStatus: setWsStatus
        });
      }
    } else {
      setWsStatus('disconnected');
    }

    syncEngine.start((stats) => {
      useAppStore.getState().setSync({
        pending: stats.pendingBefore,
        sent: stats.sent,
        failed: stats.failed + stats.finalizedFailed,
        lastSyncAt: stats.lastSyncAt
      });
    });

    if (!stopMonitor) {
      stopMonitor = startConnectivityMonitor({
        onOnline: () => {
          syncEngine.triggerSync().catch(() => undefined);
        },
        onResume: () => {
          syncEngine.triggerSync().catch(() => undefined);
        }
      });
    }

    setBoot({
      bootstrapped: true,
      needsJudgeSetup: !settings.judgeName,
      hasSession,
      activeMatch
    });

    await retentionService.enforce();
  }

  shutdown() {
    container.services.syncEngine.stop();
    container.services.realtimeService.disconnect();
    if (stopMonitor) {
      stopMonitor();
      stopMonitor = null;
    }
  }

  async getSettings() {
    return container.repos.settingsRepo.getSettings();
  }

  async saveSettings(input: {
    judgeName: string;
    actionValue1: number;
    actionValue2: number;
    remoteBaseUrl?: string;
    bootstrapToken?: string;
    defaultStationId: string;
    defaultRounds: number;
    presentationCategoryStartScore: number;
    defaultStartingScore: number;
    retainedMatchesCount: number;
  }) {
    const validated = validateSettings(input);
    return container.repos.settingsRepo.upsertSettings({
      judgeName: validated.judgeName,
      actionValue1: validated.actionValue1,
      actionValue2: validated.actionValue2,
      remoteBaseUrl: validated.remoteBaseUrl || null,
      bootstrapToken: validated.bootstrapToken || null,
      defaultStationId: validated.defaultStationId,
      defaultRounds: validated.defaultRounds,
      presentationCategoryStartScore: validated.presentationCategoryStartScore,
      defaultStartingScore: validated.defaultStartingScore,
      retainedMatchesCount: validated.retainedMatchesCount
    });
  }

  async saveJudgeName(judgeName: string) {
    const settings = await container.repos.settingsRepo.getSettings();
    const updated = await this.saveSettings({
      judgeName,
      actionValue1: settings.actionValue1,
      actionValue2: settings.actionValue2,
      remoteBaseUrl: settings.remoteBaseUrl ?? undefined,
      bootstrapToken: settings.bootstrapToken ?? undefined,
      defaultStationId: settings.defaultStationId,
      defaultRounds: settings.defaultRounds,
      presentationCategoryStartScore: settings.presentationCategoryStartScore,
      defaultStartingScore: settings.defaultStartingScore,
      retainedMatchesCount: settings.retainedMatchesCount
    });
    useAppStore.getState().setBoot({
      bootstrapped: true,
      needsJudgeSetup: !updated.judgeName,
      hasSession: useAppStore.getState().hasSession,
      activeMatch: await container.repos.matchRepo.getActiveMatch()
    });
    return updated;
  }

  async savePreferredRedSide(side: 'LEFT' | 'RIGHT') {
    return container.repos.settingsRepo.upsertSettings({ preferredRedSide: side });
  }

  async saveQr(rawQr: string) {
    const result = await container.services.sessionService.saveFromQr(rawQr);
    await container.repos.settingsRepo.upsertSettings({
      serverHasActiveMatch: false,
      serverActiveMatchId: null,
      serverCompetitorRedName: null,
      serverCompetitorBlueName: null,
      serverMatchUpdatedAt: null
    });
    useAppStore.getState().bumpSettingsVersion();
    useAppStore.setState({ hasSession: false });
    return result;
  }

  async saveManualBackend(baseUrl: string, token?: string) {
    const result = await container.services.sessionService.saveManualBackend(baseUrl, token);
    await container.repos.settingsRepo.upsertSettings({
      serverHasActiveMatch: false,
      serverActiveMatchId: null,
      serverCompetitorRedName: null,
      serverCompetitorBlueName: null,
      serverMatchUpdatedAt: null
    });
    useAppStore.getState().bumpSettingsVersion();
    useAppStore.setState({ hasSession: false });
    return result;
  }

  async refreshStations() {
    return container.services.sessionService.refreshStations();
  }

  async refreshActiveMatchSnapshot() {
    return container.services.sessionService.refreshActiveMatchSnapshot();
  }

  async listStations() {
    return container.repos.connectionRepo.listActiveStations();
  }

  async connectStation(input: { stationId: string; credential: string; judgeName?: string }) {
    const session = await container.services.sessionService.connectStation(input);
    await container.repos.settingsRepo.upsertSettings({
      serverHasActiveMatch: false,
      serverActiveMatchId: null,
      serverCompetitorRedName: null,
      serverCompetitorBlueName: null,
      serverMatchUpdatedAt: null
    });
    useAppStore.getState().bumpSettingsVersion();
    useAppStore.setState({ hasSession: true });
    const [token, backend] = await Promise.all([
      container.repos.sessionRepo.getAccessToken(),
      container.repos.connectionRepo.getActiveBackend()
    ]);

    if (token && backend) {
      container.services.realtimeService.connect({
        baseUrl: backend.baseUrl,
        sessionId: session.sessionId,
        stationId: session.stationId,
        accessToken: token,
        onStatus: useAppStore.getState().setWsStatus
      });
    }

    return session;
  }

  async connectLocalMode(judgeName?: string) {
    const session = await container.services.sessionService.startLocalSession({ judgeName });
    useAppStore.setState({ hasSession: true, wsStatus: 'disconnected' });
    return session;
  }

  async disconnectServerSession() {
    const session = await container.repos.sessionRepo.getSession();
    container.services.realtimeService.disconnect();
    await container.repos.sessionRepo.clearSession();
    await container.repos.settingsRepo.upsertSettings({
      serverHasActiveMatch: false,
      serverActiveMatchId: null,
      serverCompetitorRedName: null,
      serverCompetitorBlueName: null,
      serverMatchUpdatedAt: null
    });
    useAppStore.getState().bumpSettingsVersion();
    useAppStore.setState({ hasSession: false, wsStatus: 'disconnected' });
    return Boolean(session && session.stationId !== 'local-offline');
  }

  async createMatch(input: {
    competitorLeftName: string;
    competitorRightName: string;
    leftSideColor?: AthleteSide;
    rightSideColor?: AthleteSide;
  }) {
    const [settings, session] = await Promise.all([container.repos.settingsRepo.getSettings(), container.repos.sessionRepo.getSession()]);
    const isRemoteSession = Boolean(session && session.stationId !== 'local-offline');
    const canonicalServerMatchId = (settings.serverActiveMatchId ?? '').trim();
    const wsStatus = useAppStore.getState().wsStatus;
    const isRealtimeConnected = wsStatus === 'connected';

    if (isRemoteSession && isRealtimeConnected && !canonicalServerMatchId) {
      throw new LocalizedError('errors.noServerActiveMatch');
    }

    // Matches that will never reach a server (local mode, or no WebSocket to learn the server match) get a
    // `local-` ID, so their events are never queued for sync.
    const localOnlyMatchId = `local-${createId()}`;
    const matchId = isRemoteSession && isRealtimeConnected ? canonicalServerMatchId : localOnlyMatchId;

    const match = await container.services.matchService.createMatch({
      matchId,
      competitorLeftName: input.competitorLeftName,
      competitorRightName: input.competitorRightName,
      leftSideColor: input.leftSideColor,
      rightSideColor: input.rightSideColor,
      totalRounds: settings.defaultRounds,
      startingScore: settings.defaultStartingScore,
      presentationCategoryStartScore: settings.presentationCategoryStartScore
    });
    useAppStore.getState().setActiveMatch(match);
    return match;
  }

  async getActiveScoring() {
    const projection = await container.services.matchService.getActiveMatchProjection();
    useAppStore.getState().setActiveMatch(projection?.match ?? null);
    return projection;
  }

  async applyScore(side: AthleteSide, delta: number, target: ScoreTarget = 'TECHNIQUE') {
    const event = await container.services.matchService.applyScoreDelta(side, delta, target);
    if (event) {
      container.services.syncEngine.triggerSync().catch(() => undefined);
    }
  }

  async nextRound() {
    const [match, session] = await Promise.all([
      container.repos.matchRepo.getActiveMatch(),
      container.repos.sessionRepo.getSession()
    ]);
    const next = await container.services.matchService.moveToNextRound();
    if (match && session && session.stationId !== 'local-offline') {
      try {
        container.services.realtimeService.notifyRoundCompleted({
          matchId: match.id,
          roundNumber: match.currentRound,
          sessionId: session.sessionId,
          stationId: session.stationId,
          judgeName: session.judgeName,
          deviceId: session.deviceId
        });
      } catch {
        // Non-blocking operational hint.
      }
    }
    return next;
  }

  async resetTechniqueRound() {
    const [match, session] = await Promise.all([
      container.repos.matchRepo.getActiveMatch(),
      container.repos.sessionRepo.getSession()
    ]);
    // Recorded as compensating score events (never a deletion), then synced like any other event.
    const compensations = await container.services.matchService.resetTechniqueCurrentRound();
    if (compensations.length) {
      container.services.syncEngine.triggerSync().catch(() => undefined);
    }
    if (match && session && session.stationId !== 'local-offline') {
      try {
        container.services.realtimeService.notifyResetRequested({
          matchId: match.id,
          roundNumber: match.currentRound,
          resetTarget: 'TECHNIQUE',
          sessionId: session.sessionId,
          stationId: session.stationId,
          judgeName: session.judgeName,
          deviceId: session.deviceId,
          reason: 'manual_reset_technique'
        });
      } catch {
        // Non-blocking operational hint.
      }
    }
  }

  async resetPresentationRound() {
    const [match, session] = await Promise.all([
      container.repos.matchRepo.getActiveMatch(),
      container.repos.sessionRepo.getSession()
    ]);
    const compensations = await container.services.matchService.resetPresentationCurrentRound();
    if (compensations.length) {
      container.services.syncEngine.triggerSync().catch(() => undefined);
    }
    if (match && session && session.stationId !== 'local-offline') {
      try {
        container.services.realtimeService.notifyResetRequested({
          matchId: match.id,
          roundNumber: match.currentRound,
          resetTarget: 'PRESENTATION',
          sessionId: session.sessionId,
          stationId: session.stationId,
          judgeName: session.judgeName,
          deviceId: session.deviceId,
          reason: 'manual_reset_presentation'
        });
      } catch {
        // Non-blocking operational hint.
      }
    }
  }

  async closeActiveMatch() {
    await container.services.matchService.closeActiveMatch('manual_close');
    await container.services.retentionService.enforce();
    useAppStore.getState().setActiveMatch(await container.repos.matchRepo.getActiveMatch());
  }

  async finalizeMatch() {
    const result = await container.services.finalizationService.finalizeActiveMatch();
    if (result.mode === 'pending_remote_ack') {
      const session = await container.repos.sessionRepo.getSession();
      if (session && session.stationId !== 'local-offline') {
        try {
          container.services.realtimeService.notifyMatchCompleted({
            matchId: result.payload.matchId,
            finalRound: result.payload.finalRound,
            checksum: result.payload.checksum,
            sessionId: session.sessionId,
            stationId: session.stationId,
            judgeName: session.judgeName,
            deviceId: session.deviceId
          });
        } catch {
          // Non-blocking operational hint.
        }
      }
    }
    await container.services.retentionService.enforce();
    await container.services.syncEngine.triggerSync();
    useAppStore.getState().setActiveMatch(await container.repos.matchRepo.getActiveMatch());
    return result;
  }

  async getSummary(matchId: string) {
    return container.services.matchService.getSummary(matchId);
  }

  async listHistory() {
    const settings = await container.repos.settingsRepo.getSettings();
    return container.repos.matchRepo.listRetainedMatches(settings.retainedMatchesCount);
  }

  async syncNow() {
    return container.services.syncEngine.triggerSync();
  }

  async resyncNow() {
    const syncStats = await container.services.syncEngine.triggerSync();
    const [backend, session, token] = await Promise.all([
      container.repos.connectionRepo.getActiveBackend(),
      container.repos.sessionRepo.getSession(),
      container.repos.sessionRepo.getAccessToken()
    ]);
    const wsStatus = useAppStore.getState().wsStatus;

    if (wsStatus === 'disconnected' && backend && session && token && session.stationId !== 'local-offline') {
      container.services.realtimeService.connect({
        baseUrl: backend.baseUrl,
        sessionId: session.sessionId,
        stationId: session.stationId,
        accessToken: token,
        onStatus: useAppStore.getState().setWsStatus
      });
    }

    const snapshot = await container.services.sessionService.refreshActiveMatchSnapshot().catch(() => null);
    if (snapshot) {
      useAppStore.getState().bumpSettingsVersion();
    }

    return syncStats;
  }

  async getConnectionInfo() {
    const [backend, session] = await Promise.all([
      container.repos.connectionRepo.getActiveBackend(),
      container.repos.sessionRepo.getSession()
    ]);

    return { backend, session };
  }
}

export const appFacade = new AppFacade();
