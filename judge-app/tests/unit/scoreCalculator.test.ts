import { describe, expect, it } from 'vitest';
import { calculateScoreFromEvents, classifyTotals } from '@/domain/services/scoreCalculator';

describe('scoreCalculator', () => {
  it('computes the total score with positive and negative deltas', () => {
    const events = [
      { athleteSide: 'RED' as const, scoreDelta: -0.1, sequence: 2, scoreTarget: 'TECHNIQUE' as const },
      { athleteSide: 'RED' as const, scoreDelta: 0.3, sequence: 3, scoreTarget: 'TECHNIQUE' as const },
      { athleteSide: 'BLUE' as const, scoreDelta: -0.3, sequence: 1, scoreTarget: 'TECHNIQUE' as const }
    ];

    const total = calculateScoreFromEvents(10, events);
    expect(total.red).toBe(10.2);
    expect(total.blue).toBe(9.7);
  });

  it('classifies negative and positive actions per side', () => {
    const grouped = classifyTotals([
      { athleteSide: 'RED' as const, scoreDelta: -0.3, scoreTarget: 'TECHNIQUE' as const },
      { athleteSide: 'RED' as const, scoreDelta: 0.1, scoreTarget: 'TECHNIQUE' as const },
      { athleteSide: 'BLUE' as const, scoreDelta: -0.1, scoreTarget: 'TECHNIQUE' as const },
      { athleteSide: 'BLUE' as const, scoreDelta: 0.1, scoreTarget: 'PRESENTATION_SPEED_POWER' as const }
    ]);

    expect(grouped.totalNegative.red).toBe(0.3);
    expect(grouped.totalPositive.red).toBe(0.1);
    expect(grouped.totalNegative.blue).toBe(0.1);
    expect(grouped.totalPositive.blue).toBe(0);
  });
});
