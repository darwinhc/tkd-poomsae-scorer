import { LocalizedError } from '@/i18n/LocalizedError';

export function canMoveToNextRound(currentRound: number, totalRounds: number, isMatchActive: boolean): boolean {
  if (!isMatchActive) {
    return false;
  }

  return currentRound < totalRounds;
}

export function nextRoundNumber(currentRound: number, totalRounds: number): number {
  if (!canMoveToNextRound(currentRound, totalRounds, true)) {
    throw new LocalizedError('errors.cannotAdvanceRound');
  }

  return currentRound + 1;
}

export function isValidRoundCount(rounds: number): boolean {
  return Number.isInteger(rounds) && rounds >= 1 && rounds <= 10;
}
