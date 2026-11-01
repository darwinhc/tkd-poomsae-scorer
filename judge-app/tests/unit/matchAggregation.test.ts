import { addScores2, aggregateMatchTotals, divideHalfUp2, judgeFinalScore } from '@/domain/services/matchAggregation';

const baseCategories = {
  speedPower: { red: 2, blue: 2 },
  rhythmTempo: { red: 2, blue: 2 },
  energyExpression: { red: 2, blue: 2 }
};

describe('matchAggregation', () => {
  it('does not add up full rounds; keeps a maximum of 10 (4 technique + 6 presentation)', () => {
    const result = aggregateMatchTotals([
      {
        status: 'completed',
        technique: { red: 4, blue: 4 },
        presentationTotal: { red: 6, blue: 6 },
        presentationByCategory: baseCategories
      },
      {
        status: 'completed',
        technique: { red: 4, blue: 4 },
        presentationTotal: { red: 6, blue: 6 },
        presentationByCategory: baseCategories
      }
    ]);

    expect(result.technique.red).toBe(4);
    expect(result.technique.blue).toBe(4);
    expect(result.presentationTotal.red).toBe(6);
    expect(result.presentationTotal.blue).toBe(6);
    expect(result.technique.red + result.presentationTotal.red).toBe(10);
    expect(result.technique.blue + result.presentationTotal.blue).toBe(10);
  });

  it('ignores pending rounds in the overall aggregate', () => {
    const result = aggregateMatchTotals([
      {
        status: 'completed',
        technique: { red: 3.7, blue: 3.6 },
        presentationTotal: { red: 5.8, blue: 5.7 },
        presentationByCategory: {
          speedPower: { red: 2, blue: 1.9 },
          rhythmTempo: { red: 1.9, blue: 1.9 },
          energyExpression: { red: 1.9, blue: 1.9 }
        }
      },
      {
        status: 'pending',
        technique: { red: 4, blue: 4 },
        presentationTotal: { red: 6, blue: 6 },
        presentationByCategory: baseCategories
      }
    ]);

    expect(result.technique.red).toBe(3.7);
    expect(result.technique.blue).toBe(3.6);
    expect(result.presentationTotal.red).toBe(5.8);
    expect(result.presentationTotal.blue).toBe(5.7);
  });

  it('averages rounds with 2 decimals instead of rounding to 1 decimal', () => {
    const result = aggregateMatchTotals([
      {
        status: 'completed',
        technique: { red: 3.4, blue: 3.8 },
        presentationTotal: { red: 4.8, blue: 4.9 },
        presentationByCategory: baseCategories
      },
      {
        status: 'completed',
        technique: { red: 3.8, blue: 3.6 },
        presentationTotal: { red: 5.7, blue: 5.6 },
        presentationByCategory: baseCategories
      }
    ]);

    expect(result.presentationTotal.red).toBe(5.25);
    expect(result.technique.red + result.presentationTotal.red).toBeCloseTo(8.85, 10);
    expect(result.technique.blue + result.presentationTotal.blue).toBeCloseTo(8.95, 10);
  });

  it('rounds averages half up on exact hundredths like the backend Decimal rounding', () => {
    expect(divideHalfUp2(8.2 + 9.5, 2)).toBe(8.85);
    // 32.7 / 4 = 8.175: plain float rounding gives 8.17, the backend gives 8.18.
    expect(divideHalfUp2(32.7, 4)).toBe(8.18);
    expect(divideHalfUp2(10, 3)).toBe(3.33);
    expect(divideHalfUp2(20, 3)).toBe(6.67);
    expect(addScores2(3.6, 5.25)).toBe(8.85);
  });

  it('computes the judge final score as average technique plus average presentation', () => {
    const rounds = [
      { technique: { red: 3.4, blue: 4 }, presentationTotal: { red: 4.8, blue: 6 } },
      { technique: { red: 3.8, blue: 4 }, presentationTotal: { red: 5.7, blue: 6 } }
    ];
    expect(judgeFinalScore(rounds, 'red')).toBe(8.85);
    expect(judgeFinalScore(rounds, 'blue')).toBe(10);
    expect(judgeFinalScore([], 'red')).toBe(0);
  });
});
