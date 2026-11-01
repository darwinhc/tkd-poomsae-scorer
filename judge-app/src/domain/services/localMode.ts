/**
 * Local mode: scoring without a server. Its session (station `local-offline`, session ID `local-...`) and
 * its matches (`local-...` IDs, also used for matches started while the WebSocket was down) are never sent
 * to a backend, so their events must not wait in the sync queue nor hold server finalizations.
 */
export const LOCAL_OFFLINE_STATION_ID = 'local-offline';
const LOCAL_ID_PREFIX = 'local-';

export function isLocalOnlyMatchId(matchId: string | null | undefined): boolean {
  return (matchId ?? '').startsWith(LOCAL_ID_PREFIX);
}

export function isLocalSession(session: { stationId?: string | null; sessionId?: string | null }): boolean {
  return session.stationId === LOCAL_OFFLINE_STATION_ID || (session.sessionId ?? '').startsWith(LOCAL_ID_PREFIX);
}

/** Events recorded by a local session or for a local-only match: never sent to a server. */
export function isLocalOnlyScoreEvent(event: {
  matchId?: string | null;
  stationId?: string | null;
  sessionId?: string | null;
}): boolean {
  return isLocalOnlyMatchId(event.matchId) || isLocalSession(event);
}
