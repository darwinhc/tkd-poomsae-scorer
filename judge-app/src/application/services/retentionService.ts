import type { IMatchRepository, ISettingsRepository } from '@/application/ports/repositories';
import { selectMatchesToDelete } from '@/domain/services/retentionPolicy';

export class RetentionService {
  constructor(
    private readonly settingsRepo: ISettingsRepository,
    private readonly matchRepo: IMatchRepository
  ) {}

  async enforce() {
    const [settings, matches] = await Promise.all([this.settingsRepo.getSettings(), this.matchRepo.listAllMatches()]);
    const toDelete = selectMatchesToDelete(matches, settings.retainedMatchesCount);
    await this.matchRepo.deleteMatches(toDelete);
    return toDelete.length;
  }
}
