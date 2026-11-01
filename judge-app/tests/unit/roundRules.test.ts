import { describe, expect, it } from 'vitest';
import { canMoveToNextRound, nextRoundNumber } from '@/domain/services/roundRules';

describe('roundRules', () => {
  it('validates round transitions', () => {
    expect(canMoveToNextRound(1, 2, true)).toBe(true);
    expect(canMoveToNextRound(2, 2, true)).toBe(false);
    expect(canMoveToNextRound(1, 2, false)).toBe(false);
  });

  it('returns the next round', () => {
    expect(nextRoundNumber(1, 2)).toBe(2);
  });
});
