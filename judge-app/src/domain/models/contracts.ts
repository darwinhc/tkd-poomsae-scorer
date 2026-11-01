import type { AthleteSide, ScoreTarget } from './entities';

export interface QrBootstrapPayload {
  baseUrl: string;
  stationId: string;
  stationName?: string;
  bootstrapToken?: string;
  environment?: string;
  tournamentId?: string;
  protocolVersion: string;
  expiresAt: string;
}

export interface StationConnectRequest {
  stationId: string;
  judgeName: string;
  credential: string;
  deviceId: string;
}

export interface StationConnectResponse {
  connected: boolean;
  sessionId: string;
  accessToken: string;
  expiresAt?: string;
  station: {
    id: string;
    name: string;
  };
}

export interface ScoreEventPayload {
  eventId: string;
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
}

/** Active match state returned by GET /stations/{station_id}/active-match-state. */
export interface ActiveMatchSnapshot {
  hasActiveMatch: boolean;
  matchId?: string;
  redName?: string;
  blueName?: string;
}

export interface AckResponse {
  acknowledged: boolean;
  eventId: string;
  serverReceivedAt: string;
}

export interface FinalizePayload {
  sessionId: string;
  stationId: string;
  matchId: string;
  judgeName: string;
  competitorLeftName: string;
  competitorRightName: string;
  totalRounds: number;
  finalRound: number;
  finalScoreRed: number;
  finalScoreBlue: number;
  totalEvents: number;
  finalSequence: number;
  startedAt: string;
  finishedAt: string;
  checksum: string;
  roundsSummary: {
    roundNumber: number;
    techniqueRed: number;
    presentationRed: number;
    techniqueBlue: number;
    presentationBlue: number;
    // Round totals (technique + presentation), kept for older backends.
    red: number;
    blue: number;
    negativeRed: number;
    negativeBlue: number;
    positiveRed: number;
    positiveBlue: number;
  }[];
}

export type RealtimeEventType =
  | 'reset_match'
  | 'reset_round'
  | 'new_competitors'
  | 'active_match_state'
  | 'judge_settings_updated'
  | 'round_changed'
  | 'match_updated'
  | 'station_disconnected'
  | 'session_revoked'
  | 'judge_kicked'
  | 'server_notice'
  | 'ping'
  | 'pong';

export interface RealtimeEvent {
  type: RealtimeEventType;
  payload: Record<string, unknown>;
}
