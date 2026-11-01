import { describe, expect, it } from 'vitest';
import { validateQrPayload, validateStationConnection } from '@/domain/services/connectionValidation';

describe('connectionValidation', () => {
  it('validates the QR payload', () => {
    const payload = validateQrPayload(
      JSON.stringify({
        baseUrl: 'http://192.168.1.20:8080',
        stationId: 'station-01',
        bootstrapToken: 'abc123',
        protocolVersion: 'v1',
        expiresAt: '2099-01-01T00:00:00.000Z'
      })
    );

    expect(payload.baseUrl).toContain('192.168.1.20');
  });

  it('validates the station connection', () => {
    const result = validateStationConnection({
      stationId: 'station-01',
      judgeName: 'Judge 1',
      credential: '1234',
      deviceId: 'dev-1'
    });
    expect(result.stationId).toBe('station-01');
  });
});
