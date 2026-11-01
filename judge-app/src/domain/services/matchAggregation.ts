import type { ScoreTotals } from '@/domain/models/entities';

type RoundAggregateInput = {
  status?: 'pending' | 'active' | 'completed';
  technique: ScoreTotals;
  presentationTotal: ScoreTotals;
  presentationByCategory: {
    speedPower: ScoreTotals;
    rhythmTempo: ScoreTotals;
    energyExpression: ScoreTotals;
  };
};

export function aggregateMatchTotals(rounds: RoundAggregateInput[]) {
  const considered = rounds.filter((round) => round.status !== 'pending');
  if (!considered.length) {
    return {
      technique: { red: 0, blue: 0 },
      presentationTotal: { red: 0, blue: 0 },
      presentationByCategory: {
        speedPower: { red: 0, blue: 0 },
        rhythmTempo: { red: 0, blue: 0 },
        energyExpression: { red: 0, blue: 0 }
      }
    };
  }

  const sum = considered.reduce(
    (acc, round) => ({
      technique: {
        red: round1(acc.technique.red + round.technique.red),
        blue: round1(acc.technique.blue + round.technique.blue)
      },
      presentationTotal: {
        red: round1(acc.presentationTotal.red + round.presentationTotal.red),
        blue: round1(acc.presentationTotal.blue + round.presentationTotal.blue)
      },
      presentationByCategory: {
        speedPower: {
          red: round1(acc.presentationByCategory.speedPower.red + round.presentationByCategory.speedPower.red),
          blue: round1(acc.presentationByCategory.speedPower.blue + round.presentationByCategory.speedPower.blue)
        },
        rhythmTempo: {
          red: round1(acc.presentationByCategory.rhythmTempo.red + round.presentationByCategory.rhythmTempo.red),
          blue: round1(acc.presentationByCategory.rhythmTempo.blue + round.presentationByCategory.rhythmTempo.blue)
        },
        energyExpression: {
          red: round1(acc.presentationByCategory.energyExpression.red + round.presentationByCategory.energyExpression.red),
          blue: round1(acc.presentationByCategory.energyExpression.blue + round.presentationByCategory.energyExpression.blue)
        }
      }
    }),
    {
      technique: { red: 0, blue: 0 },
      presentationTotal: { red: 0, blue: 0 },
      presentationByCategory: {
        speedPower: { red: 0, blue: 0 },
        rhythmTempo: { red: 0, blue: 0 },
        energyExpression: { red: 0, blue: 0 }
      }
    }
  );

  const count = considered.length;
  return {
    technique: {
      red: divideHalfUp2(sum.technique.red, count),
      blue: divideHalfUp2(sum.technique.blue, count)
    },
    presentationTotal: {
      red: divideHalfUp2(sum.presentationTotal.red, count),
      blue: divideHalfUp2(sum.presentationTotal.blue, count)
    },
    presentationByCategory: {
      speedPower: {
        red: divideHalfUp2(sum.presentationByCategory.speedPower.red, count),
        blue: divideHalfUp2(sum.presentationByCategory.speedPower.blue, count)
      },
      rhythmTempo: {
        red: divideHalfUp2(sum.presentationByCategory.rhythmTempo.red, count),
        blue: divideHalfUp2(sum.presentationByCategory.rhythmTempo.blue, count)
      },
      energyExpression: {
        red: divideHalfUp2(sum.presentationByCategory.energyExpression.red, count),
        blue: divideHalfUp2(sum.presentationByCategory.energyExpression.blue, count)
      }
    }
  };
}

type RoundScoreInput = {
  technique: ScoreTotals;
  presentationTotal: ScoreTotals;
};

/**
 * Final score of this judge for one side: 2-decimal average of technique plus 2-decimal average of
 * presentation over the given rounds (the backend rebuilds the same value from the judge's events).
 */
export function judgeFinalScore(rounds: RoundScoreInput[], side: keyof ScoreTotals): number {
  if (!rounds.length) return 0;
  const technique = divideHalfUp2(
    rounds.reduce((acc, round) => acc + round.technique[side], 0),
    rounds.length
  );
  const presentation = divideHalfUp2(
    rounds.reduce((acc, round) => acc + round.presentationTotal[side], 0),
    rounds.length
  );
  return addScores2(technique, presentation);
}

/**
 * total / count rounded half up to 2 decimals, computed on integer hundredths so the result is exact for
 * the app's non-negative scores (like the backend's Decimal ROUND_HALF_UP): (8.2 + 9.5) / 2 = 8.85, not 8.9,
 * and 32.7 / 4 = 8.18 (plain float rounding of 8.175 gives 8.17).
 */
export function divideHalfUp2(total: number, count: number): number {
  const hundredths = Math.round(total * 100);
  return Math.floor((2 * hundredths + count) / (2 * count)) / 100;
}

export function addScores2(...values: number[]): number {
  return values.reduce((acc, value) => acc + Math.round(value * 100), 0) / 100;
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}
