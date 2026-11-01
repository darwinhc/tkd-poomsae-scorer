import { FinalizationService } from '@/application/services/finalizationService';
import { MatchService } from '@/application/services/matchService';
import { RealtimeService } from '@/application/services/realtimeService';
import { RecoveryService } from '@/application/services/recoveryService';
import { RetentionService } from '@/application/services/retentionService';
import { SessionService } from '@/application/services/sessionService';
import { SyncEngine } from '@/application/services/syncEngine';
import { RealtimeClient } from '@/infrastructure/network/realtimeClient';
import { createApiClient } from '@/infrastructure/network/apiClient';
import { ConnectionRepositorySqlite } from '@/infrastructure/repositories/ConnectionRepositorySqlite';
import { FinalizationRepositorySqlite } from '@/infrastructure/repositories/FinalizationRepositorySqlite';
import { HistoryRepositorySqlite } from '@/infrastructure/repositories/HistoryRepositorySqlite';
import { InboundServerEventRepositorySqlite } from '@/infrastructure/repositories/InboundServerEventRepositorySqlite';
import { MatchRepositorySqlite } from '@/infrastructure/repositories/MatchRepositorySqlite';
import { ScoreEventRepositorySqlite } from '@/infrastructure/repositories/ScoreEventRepositorySqlite';
import { SessionRepositorySqlite } from '@/infrastructure/repositories/SessionRepositorySqlite';
import { SettingsRepositorySqlite } from '@/infrastructure/repositories/SettingsRepositorySqlite';

const settingsRepo = new SettingsRepositorySqlite();
const connectionRepo = new ConnectionRepositorySqlite();
const sessionRepo = new SessionRepositorySqlite();
const matchRepo = new MatchRepositorySqlite();
const scoreRepo = new ScoreEventRepositorySqlite();
const finalizationRepo = new FinalizationRepositorySqlite();
const historyRepo = new HistoryRepositorySqlite();
const inboundRepo = new InboundServerEventRepositorySqlite();

const apiClient = createApiClient();
const realtimeClient = new RealtimeClient();

export const container = {
  repos: {
    settingsRepo,
    connectionRepo,
    sessionRepo,
    matchRepo,
    scoreRepo,
    finalizationRepo,
    historyRepo,
    inboundRepo
  },
  services: {
    sessionService: new SessionService(connectionRepo, sessionRepo, settingsRepo, apiClient),
    matchService: new MatchService(matchRepo, scoreRepo, sessionRepo, historyRepo, inboundRepo),
    finalizationService: new FinalizationService(matchRepo, historyRepo, finalizationRepo, sessionRepo, connectionRepo),
    syncEngine: new SyncEngine(scoreRepo, finalizationRepo, sessionRepo, connectionRepo, matchRepo, apiClient),
    realtimeService: new RealtimeService(realtimeClient, inboundRepo, matchRepo, scoreRepo, sessionRepo, settingsRepo),
    retentionService: new RetentionService(settingsRepo, matchRepo),
    recoveryService: new RecoveryService(settingsRepo, matchRepo)
  }
};
