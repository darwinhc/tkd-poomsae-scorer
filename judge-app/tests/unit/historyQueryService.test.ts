import { describe, expect, it } from 'vitest';
import { HistoryQueryService } from '@/application/services/historyQueryService';

describe('historyQueryService', () => {
  it('loads headers and lazy-loads the detail', async () => {
    const counters = { headers: 0, details: 0 };

    const service = new HistoryQueryService(
      {
        listRetainedMatches: async () => {
          counters.headers += 1;
          return [{ id: 'm1' }];
        }
      } as any,
      {
        getSummary: async () => {
          counters.details += 1;
          return { matchId: 'm1' };
        }
      } as any,
      {
        getSettings: async () => ({ retainedMatchesCount: 2 })
      } as any
    );

    await service.listHistoryHeaders();
    expect(counters.headers).toBe(1);
    expect(counters.details).toBe(0);

    await service.loadSummary('m1');
    expect(counters.details).toBe(1);
  });
});
