import { describe, expect, it } from 'vitest';
import { validateSettings } from '@/domain/services/settingsValidation';

describe('settingsValidation', () => {
  it('accepts valid settings', () => {
    const data = validateSettings({
      judgeName: 'Judge 1',
      actionValue1: 0.1,
      actionValue2: 0.3,
      defaultStationId: 'station-01',
      remoteBaseUrl: 'http://192.168.0.1:8080',
      bootstrapToken: 'abc',
      defaultRounds: 2,
      presentationCategoryStartScore: 2,
      defaultStartingScore: 10,
      retainedMatchesCount: 2
    });

    expect(data.judgeName).toBe('Judge 1');
  });

  it('fails when retention is below the minimum', () => {
    expect(() =>
      validateSettings({
        judgeName: 'Judge 1',
        actionValue1: 0.1,
        actionValue2: 0.3,
        defaultStationId: 'station-01',
        remoteBaseUrl: '',
        bootstrapToken: '',
        defaultRounds: 2,
        presentationCategoryStartScore: 2,
        defaultStartingScore: 10,
        retainedMatchesCount: 1
      })
    ).toThrow();
  });
});
