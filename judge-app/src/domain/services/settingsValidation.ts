import { z } from 'zod';
import { MIN_RETAINED_MATCHES } from '@/constants/defaults';

export const settingsSchema = z.object({
  judgeName: z.string().trim().min(2).max(80),
  preferredRedSide: z.enum(['LEFT', 'RIGHT']).optional().default('LEFT'),
  actionValue1: z.number().positive().max(1),
  actionValue2: z.number().positive().max(2),
  remoteBaseUrl: z.string().url().optional().or(z.literal('')),
  bootstrapToken: z.string().max(300).optional().or(z.literal('')),
  defaultStationId: z.string().trim().min(2).max(50),
  defaultRounds: z.number().int().min(1).max(10),
  presentationCategoryStartScore: z.number().min(0).max(2),
  defaultStartingScore: z.number().min(0).max(20),
  retainedMatchesCount: z.number().int().min(MIN_RETAINED_MATCHES).max(50)
});

export type SettingsInput = z.input<typeof settingsSchema>;

export function validateSettings(input: SettingsInput) {
  return settingsSchema.parse(input);
}
