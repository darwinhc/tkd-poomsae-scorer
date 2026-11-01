import type { IHistoryRepository, IMatchRepository, ISettingsRepository } from '@/application/ports/repositories';

export class HistoryQueryService {
  constructor(
    private readonly matchRepo: IMatchRepository,
    private readonly historyRepo: IHistoryRepository,
    private readonly settingsRepo: ISettingsRepository
  ) {}

  async listHistoryHeaders() {
    const settings = await this.settingsRepo.getSettings();
    return this.matchRepo.listRetainedMatches(settings.retainedMatchesCount);
  }

  async loadSummary(matchId: string) {
    return this.historyRepo.getSummary(matchId);
  }
}
