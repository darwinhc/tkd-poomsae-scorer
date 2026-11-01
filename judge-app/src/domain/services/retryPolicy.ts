export interface RetryMeta {
  retryCount: number;
  lastAttemptAt?: string | null;
}

const BASE_MS = 800;
const MAX_MS = 60_000;

export function nextRetryDelayMs(retryCount: number, jitterSeed = Math.random()): number {
  const exponential = Math.min(MAX_MS, BASE_MS * 2 ** retryCount);
  const jitter = exponential * (0.2 + jitterSeed * 0.4);
  return Math.round(exponential + jitter);
}

export function isRetryEligible(meta: RetryMeta, nowIso: string): boolean {
  if (!meta.lastAttemptAt) {
    return true;
  }

  const elapsed = Date.parse(nowIso) - Date.parse(meta.lastAttemptAt);
  return elapsed >= nextRetryDelayMs(meta.retryCount, 0.5);
}

// Answers that cannot succeed on a retry: bad request, not found, conflict (e.g. 409 `match_closed`, the
// operator closed the match), gone and validation errors. 401/403 are not here: they are fixed by
// reconnecting, and the session handling stops the sync loop meanwhile; 408/429/5xx and network errors retry.
const TERMINAL_STATUSES = new Set([400, 404, 409, 410, 422]);
const TERMINAL_CODES = new Set(['match_closed']);

/** Whether a failed sync attempt is definitive (the item is rejected instead of retried). */
export function isTerminalSyncError(error: unknown): boolean {
  if (!error || typeof error !== 'object') {
    return false;
  }
  const { status, code } = error as { status?: unknown; code?: unknown };
  if (typeof code === 'string' && TERMINAL_CODES.has(code)) {
    return true;
  }
  return typeof status === 'number' && TERMINAL_STATUSES.has(status);
}
