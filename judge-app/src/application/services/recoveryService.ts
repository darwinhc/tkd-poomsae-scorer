import type { IMatchRepository, ISettingsRepository } from '@/application/ports/repositories';
import { runMigrations } from '@/infrastructure/db/migrations';

export class RecoveryService {
  constructor(
    private readonly settingsRepo: ISettingsRepository,
    private readonly matchRepo: IMatchRepository
  ) {}

  async bootstrap() {
    await runMigrations();
    const [settings, activeMatch] = await Promise.all([this.settingsRepo.getSettings(), this.matchRepo.getActiveMatch()]);
    return {
      settings,
      activeMatch
    };
  }
}
