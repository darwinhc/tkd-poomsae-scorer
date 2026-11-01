import { describe, expect, it, vi } from 'vitest';

vi.mock('@/infrastructure/db/migrations', () => ({
  runMigrations: vi.fn(async () => undefined)
}));

describe('recoveryService', () => {
  it('recovers the active match on restart', async () => {
    const { RecoveryService } = await import('@/application/services/recoveryService');
    const service = new RecoveryService(
      { getSettings: async () => ({ judgeName: 'Judge 1' }) } as any,
      { getActiveMatch: async () => ({ id: 'm1', status: 'active' }) } as any
    );

    const result = await service.bootstrap();
    expect(result.activeMatch?.id).toBe('m1');
  });
});
