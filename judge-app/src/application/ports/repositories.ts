import type {
  AthleteSide,
  AppSettings,
  BackendServer,
  FinalizationEvent,
  InboundServerEventLog,
  Match,
  MatchSummary,
  OperatorSession,
  ScoreEvent,
  Station
} from '@/domain/models/entities';
import type {
  AckResponse,
  ActiveMatchSnapshot,
  FinalizePayload,
  QrBootstrapPayload,
  ScoreEventPayload,
  StationConnectResponse
} from '@/domain/models/contracts';

export interface ISettingsRepository {
  getSettings(): Promise<AppSettings>;
  upsertSettings(input: Partial<AppSettings>): Promise<AppSettings>;
}

export interface IConnectionRepository {
  saveBackend(payload: QrBootstrapPayload): Promise<BackendServer>;
  getActiveBackend(): Promise<BackendServer | null>;
  saveStations(stations: Station[]): Promise<void>;
  listActiveStations(): Promise<Station[]>;
}

export interface ISessionRepository {
  saveSession(session: OperatorSession, accessToken?: string | null): Promise<void>;
  getSession(): Promise<OperatorSession | null>;
  getAccessToken(): Promise<string | null>;
  clearSession(): Promise<void>;
  markRevoked(): Promise<void>;
  markDisconnected(): Promise<void>;
}

export interface IMatchRepository {
  createMatch(input: {
    matchId?: string;
    competitorLeftName: string;
    competitorRightName: string;
    leftSideColor?: AthleteSide;
    rightSideColor?: AthleteSide;
    totalRounds: number;
    startingScore: number;
    presentationCategoryStartScore: number;
  }): Promise<Match>;
  getActiveMatch(): Promise<Match | null>;
  getMatchById(matchId: string): Promise<Match | null>;
  listAllMatches(): Promise<Match[]>;
  listRetainedMatches(limit: number): Promise<Match[]>;
  updateCompetitors(matchId: string, left: string, right: string): Promise<void>;
  moveToRound(matchId: string, roundNumber: number): Promise<void>;
  finishLocally(matchId: string, status: Match['status']): Promise<void>;
  markFinalizedAck(matchId: string): Promise<void>;
  resetMatch(matchId: string): Promise<void>;
  deleteMatches(matchIds: string[]): Promise<void>;
}

export interface IScoreEventRepository {
  appendScoreEvent(event: ScoreEvent): Promise<void>;
  listMatchEvents(matchId: string): Promise<ScoreEvent[]>;
  listPendingEvents(limit: number): Promise<ScoreEvent[]>;
  markEventAck(eventId: string, ackAt: string): Promise<void>;
  markEventFailed(eventId: string, error: string): Promise<void>;
  /** Definitive server refusal: the event leaves the sync queue and is not retried. */
  markEventRejected(eventId: string, error: string): Promise<void>;
  markEventSyncing(eventId: string): Promise<void>;
  getNextSequence(matchId: string): Promise<number>;
  /** Mirrors a server-side round reset (the server deleted the same events). */
  resetCurrentRound(matchId: string, roundNumber: number): Promise<void>;
}

export interface IFinalizationRepository {
  saveFinalization(event: FinalizationEvent): Promise<void>;
  listPendingFinalizations(limit: number): Promise<FinalizationEvent[]>;
  markFinalizationAck(eventId: string, ackAt: string): Promise<void>;
  markFinalizationFailed(eventId: string, error: string): Promise<void>;
  markFinalizationSyncing(eventId: string): Promise<void>;
}

export interface IHistoryRepository {
  getSummary(matchId: string): Promise<MatchSummary | null>;
}

export interface IInboundServerEventRepository {
  hasDedupeKey(dedupeKey: string): Promise<boolean>;
  appendLog(log: InboundServerEventLog): Promise<void>;
}

export interface IApiClient {
  health(baseUrl: string): Promise<boolean>;
  listActiveStations(baseUrl: string, bootstrapToken?: string): Promise<Station[]>;
  fetchActiveMatchSnapshot(baseUrl: string, stationId: string, accessToken?: string): Promise<ActiveMatchSnapshot | null>;
  connectStation(baseUrl: string, token: string | undefined, payload: {
    stationId: string;
    judgeName: string;
    credential: string;
    deviceId: string;
    replaceExistingJudgeSession?: boolean;
  }): Promise<StationConnectResponse>;
  postScoreEvent(baseUrl: string, accessToken: string, payload: ScoreEventPayload): Promise<AckResponse>;
  finalizeMatch(baseUrl: string, accessToken: string, payload: FinalizePayload): Promise<AckResponse>;
  validateSession(baseUrl: string, accessToken: string): Promise<boolean>;
}

export interface IRealtimeClient {
  connect(input: {
    baseUrl: string;
    sessionId: string;
    accessToken: string;
    stationId: string;
    onMessage: (event: unknown) => void;
    onStatus: (status: 'connecting' | 'connected' | 'disconnected') => void;
  }): void;
  disconnect(): void;
  sendEvent(type: string, payload: Record<string, unknown>): void;
  /** Keep-alive answer to a server `ping` (a `pong` is never answered). */
  sendPong(payload: Record<string, unknown>): void;
}
