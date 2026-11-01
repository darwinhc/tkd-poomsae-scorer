import type { AthleteSide, ScoreEvent, ScoreTarget, ScoreTotals } from '@/domain/models/entities';

const PRESENTATION_TARGETS: ScoreTarget[] = [
  'PRESENTATION_SPEED_POWER',
  'PRESENTATION_RHYTHM_TEMPO',
  'PRESENTATION_ENERGY_EXPRESSION'
];

export interface PresentationByCategory {
  speedPower: ScoreTotals;
  rhythmTempo: ScoreTotals;
  energyExpression: ScoreTotals;
}

export interface PresentationProjection {
  total: ScoreTotals;
  byCategory: PresentationByCategory;
}

type ScoreEventLike = Pick<ScoreEvent, 'athleteSide' | 'scoreDelta' | 'sequence'> & {
  scoreTarget?: ScoreTarget;
};

export function calculateTechniqueFromEvents(
  startingScore: number,
  events: ScoreEventLike[]
): ScoreTotals {
  const ordered = [...events].sort((a, b) => a.sequence - b.sequence);
  let red = startingScore;
  let blue = startingScore;

  for (const event of ordered) {
    if (!isTechniqueEvent(event)) continue;
    if (event.athleteSide === 'RED') {
      red += event.scoreDelta;
    } else {
      blue += event.scoreDelta;
    }
  }

  return {
    red: roundScore(red),
    blue: roundScore(blue)
  };
}

export function calculateScoreFromEvents(startingScore: number, events: ScoreEventLike[]): ScoreTotals {
  return calculateTechniqueFromEvents(startingScore, events);
}

export function calculatePresentationFromEvents(
  categoryStartScore: number,
  events: ScoreEventLike[]
): PresentationProjection {
  const ordered = [...events].sort((a, b) => a.sequence - b.sequence);
  const byCategory: PresentationByCategory = {
    speedPower: { red: categoryStartScore, blue: categoryStartScore },
    rhythmTempo: { red: categoryStartScore, blue: categoryStartScore },
    energyExpression: { red: categoryStartScore, blue: categoryStartScore }
  };

  for (const event of ordered) {
    if (!event.scoreTarget || !PRESENTATION_TARGETS.includes(event.scoreTarget)) continue;
    const key = event.athleteSide === 'RED' ? 'red' : 'blue';
    if (event.scoreTarget === 'PRESENTATION_SPEED_POWER') {
      byCategory.speedPower[key] = roundScore(byCategory.speedPower[key] + event.scoreDelta);
    } else if (event.scoreTarget === 'PRESENTATION_RHYTHM_TEMPO') {
      byCategory.rhythmTempo[key] = roundScore(byCategory.rhythmTempo[key] + event.scoreDelta);
    } else if (event.scoreTarget === 'PRESENTATION_ENERGY_EXPRESSION') {
      byCategory.energyExpression[key] = roundScore(byCategory.energyExpression[key] + event.scoreDelta);
    }
  }

  return {
    byCategory,
    total: {
      red: roundScore(byCategory.speedPower.red + byCategory.rhythmTempo.red + byCategory.energyExpression.red),
      blue: roundScore(byCategory.speedPower.blue + byCategory.rhythmTempo.blue + byCategory.energyExpression.blue)
    }
  };
}

export function buildSideScore(
  startingScore: number,
  side: AthleteSide,
  target: ScoreTarget,
  events: ScoreEventLike[]
): number {
  const ordered = [...events].sort((a, b) => a.sequence - b.sequence);
  let score = startingScore;

  for (const event of ordered) {
    if (event.athleteSide !== side || event.scoreTarget !== target) continue;
    score += event.scoreDelta;
  }

  return roundScore(score);
}

export function classifyTotals(events: Array<Pick<ScoreEvent, 'athleteSide' | 'scoreDelta'> & { scoreTarget?: ScoreTarget }>) {
  const totals = {
    totalNegative: { red: 0, blue: 0 },
    totalPositive: { red: 0, blue: 0 }
  };

  for (const event of events) {
    if (!isTechniqueEvent(event)) continue;
    const target = event.athleteSide === 'RED' ? 'red' : 'blue';
    if (event.scoreDelta < 0) {
      totals.totalNegative[target] = roundScore(totals.totalNegative[target] + Math.abs(event.scoreDelta));
    } else {
      totals.totalPositive[target] = roundScore(totals.totalPositive[target] + event.scoreDelta);
    }
  }

  return totals;
}

function roundScore(value: number): number {
  return Math.round(value * 10) / 10;
}

function isTechniqueEvent(event: { scoreTarget?: ScoreTarget }): boolean {
  return event.scoreTarget == null || event.scoreTarget === 'TECHNIQUE';
}
