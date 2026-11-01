import { describe, expect, it } from 'vitest';
import { isRetryEligible, isTerminalSyncError, nextRetryDelayMs } from '@/domain/services/retryPolicy';

describe('retryPolicy', () => {
  it('computes an increasing backoff', () => {
    const d0 = nextRetryDelayMs(0, 0.5);
    const d1 = nextRetryDelayMs(1, 0.5);
    const d2 = nextRetryDelayMs(2, 0.5);

    expect(d1).toBeGreaterThan(d0);
    expect(d2).toBeGreaterThan(d1);
  });

  it('allows a retry once the window has passed', () => {
    const now = new Date('2026-03-18T10:00:00.000Z');
    const last = new Date(now.getTime() - nextRetryDelayMs(1, 0.5) - 1000).toISOString();
    expect(isRetryEligible({ retryCount: 1, lastAttemptAt: last }, now.toISOString())).toBe(true);
  });

  it('treats definitive 4xx answers as terminal and keeps retrying the others', () => {
    expect(isTerminalSyncError({ status: 409, code: 'match_closed' })).toBe(true);
    expect(isTerminalSyncError({ code: 'match_closed' })).toBe(true);
    expect(isTerminalSyncError({ status: 422 })).toBe(true);
    expect(isTerminalSyncError({ status: 400 })).toBe(true);
    expect(isTerminalSyncError({ status: 401 })).toBe(false);
    expect(isTerminalSyncError({ status: 429 })).toBe(false);
    expect(isTerminalSyncError({ status: 503 })).toBe(false);
    expect(isTerminalSyncError(new Error('network down'))).toBe(false);
    expect(isTerminalSyncError(undefined)).toBe(false);
  });
});
