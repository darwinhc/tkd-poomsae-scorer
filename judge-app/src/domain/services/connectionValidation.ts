import { z } from 'zod';
import { APP_PROTOCOL_VERSION } from '@/constants/defaults';
import { LocalizedError } from '@/i18n/LocalizedError';

export const qrPayloadSchema = z.object({
  baseUrl: z.string().url(),
  stationId: z.string().min(2),
  stationName: z.string().min(2).optional(),
  bootstrapToken: z.string().min(4).optional(),
  environment: z.string().min(2).optional(),
  tournamentId: z.string().min(2).optional(),
  protocolVersion: z.string().default(APP_PROTOCOL_VERSION),
  expiresAt: z.string().datetime()
});

export function validateQrPayload(raw: string) {
  const parsed = JSON.parse(raw);
  const payload = qrPayloadSchema.parse(parsed);
  const host = new URL(payload.baseUrl).hostname.toLowerCase();
  if (host === 'localhost' || host === '127.0.0.1' || host === '::1') {
    throw new LocalizedError('errors.qrLocalhost');
  }
  if (Date.parse(payload.expiresAt) < Date.now()) {
    throw new LocalizedError('errors.qrExpired');
  }
  return payload;
}

export const stationConnectSchema = z.object({
  stationId: z.string().min(2),
  judgeName: z.string().trim().min(2),
  credential: z.string().trim().min(3),
  deviceId: z.string().min(3)
});

export function validateStationConnection(input: unknown) {
  return stationConnectSchema.parse(input);
}
