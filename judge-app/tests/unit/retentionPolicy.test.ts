import { describe, expect, it } from 'vitest';
import { selectMatchesToDelete } from '@/domain/services/retentionPolicy';

const base = {
  competitorLeftName: 'A',
  competitorRightName: 'B',
  leftSideColor: 'RED' as const,
  rightSideColor: 'BLUE' as const,
  totalRounds: 2,
  currentRound: 1,
  startingScore: 10,
  startedAt: '2026-01-01T00:00:00.000Z',
  finishedAt: null,
  retentionPriority: 0
};

describe('retentionPolicy', () => {
  it('preserves the active match and the latest matches', () => {
    const matches = [
      { ...base, id: '1', status: 'active' as const, createdAt: '2026-03-18T10:00:00.000Z' },
      { ...base, id: '2', status: 'finalized_acknowledged' as const, createdAt: '2026-03-18T09:00:00.000Z' },
      { ...base, id: '3', status: 'finalized_acknowledged' as const, createdAt: '2026-03-18T08:00:00.000Z' }
    ];

    const toDelete = selectMatchesToDelete(matches as any, 2);
    expect(toDelete).toEqual(['3']);
  });
});
