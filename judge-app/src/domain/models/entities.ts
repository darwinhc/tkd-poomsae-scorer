export type AthleteSide = 'RED' | 'BLUE';
export type ScoreTarget =
  | 'TECHNIQUE'
  | 'PRESENTATION_SPEED_POWER'
  | 'PRESENTATION_RHYTHM_TEMPO'
  | 'PRESENTATION_ENERGY_EXPRESSION';

// 'rejected': the server refused the item definitively (e.g. the match was closed); it is not retried.
export type SyncStatus = 'pending' | 'syncing' | 'acknowledged' | 'failed' | 'rejected';

export type MatchStatus =
  | 'active'
  | 'finished_locally'
  | 'finished_locally_pending_finalize_ack'
  | 'finalized_acknowledged'
  | 'finalize_failed_retrying';

export interface AppSettings {
  id: number;
  judgeName: string;
  preferredRedSide?: 'LEFT' | 'RIGHT';
  serverHasActiveMatch?: boolean;
  serverActiveMatchId?: string | null;
  serverCompetitorRedName?: string | null;
  serverCompetitorBlueName?: string | null;
  serverMatchUpdatedAt?: string | null;
  actionValue1: number;
  actionValue2: number;
  remoteBaseUrl?: string | null;
  bootstrapToken?: string | null;
  defaultStationId: string;
  defaultRounds: number;
  presentationCategoryStartScore: number;
  defaultStartingScore: number;
  retainedMatchesCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface BackendServer {
  id: string;
  baseUrl: string;
  bootstrapToken?: string | null;
  environment?: string | null;
  tournamentId?: string | null;
  protocolVersion: string;
  expiresAt?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface Station {
  id: string;
  name: string;
  status: 'active' | 'inactive';
  updatedAt: string;
}

export interface OperatorSession {
  id: string;
  backendServerId: string;
  stationId: string;
  stationName: string;
  judgeName: string;
  deviceId: string;
  sessionId: string;
  tokenExpiresAt?: string | null;
  lastValidatedAt?: string | null;
  connectionStatus: 'connected' | 'disconnected' | 'revoked';
  createdAt: string;
  updatedAt: string;
}

export interface Match {
  id: string;
  competitorLeftName: string;
  competitorRightName: string;
  leftSideColor: AthleteSide;
  rightSideColor: AthleteSide;
  totalRounds: number;
  currentRound: number;
  startingScore: number;
  presentationCategoryStartScore: number;
  status: MatchStatus;
  createdAt: string;
  startedAt: string;
  finishedAt?: string | null;
  retentionPriority: number;
}

export interface Round {
  id: string;
  matchId: string;
  roundNumber: number;
  status: 'pending' | 'active' | 'completed';
  startedAt: string;
  endedAt?: string | null;
}

export interface ScoreEvent {
  id: string;
  idempotencyKey: string;
  sessionId: string;
  stationId: string;
  deviceId: string;
  judgeName: string;
  matchId: string;
  roundNumber: number;
  athleteSide: AthleteSide;
  scoreTarget: ScoreTarget;
  scoreDelta: number;
  scoreBefore: number;
  scoreAfter: number;
  occurredAt: string;
  sequence: number;
  syncStatus: SyncStatus;
  retryCount: number;
  lastError?: string | null;
  lastAttemptAt?: string | null;
  serverAckAt?: string | null;
}

export interface FinalizationEvent {
  id: string;
  matchId: string;
  sessionId: string;
  stationId: string;
  checksum: string;
  payloadSnapshot: string;
  createdAt: string;
  syncStatus: SyncStatus;
  retryCount: number;
  lastError?: string | null;
  lastAttemptAt?: string | null;
  serverAckAt?: string | null;
}

export interface InboundServerEventLog {
  id: string;
  eventType: string;
  dedupeKey: string;
  payload: string;
  receivedAt: string;
  processedAt?: string | null;
}

export interface ScoreTotals {
  red: number;
  blue: number;
}

export interface RoundSummary {
  roundNumber: number;
  status?: 'pending' | 'active' | 'completed';
  technique: ScoreTotals;
  presentationTotal: ScoreTotals;
  presentationByCategory: {
    speedPower: ScoreTotals;
    rhythmTempo: ScoreTotals;
    energyExpression: ScoreTotals;
  };
  totalNegative: ScoreTotals;
  totalPositive: ScoreTotals;
  eventsCount: number;
}

export interface MatchSummary {
  matchId: string;
  technique: ScoreTotals;
  presentationTotal: ScoreTotals;
  presentationByCategory: {
    speedPower: ScoreTotals;
    rhythmTempo: ScoreTotals;
    energyExpression: ScoreTotals;
  };
  totalNegative: ScoreTotals;
  totalPositive: ScoreTotals;
  rounds: RoundSummary[];
  timeline: {
    eventId: string;
    sequence: number;
    athleteSide: AthleteSide;
    scoreTarget: ScoreTarget;
    scoreDelta: number;
    roundNumber: number;
    occurredAt: string;
    syncStatus: SyncStatus;
  }[];
  finalizationStatus: MatchStatus;
}
