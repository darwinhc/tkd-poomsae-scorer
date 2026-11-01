import * as Crypto from 'expo-crypto';

export type CanonicalValue = string | number | boolean | null | CanonicalValue[] | { [key: string]: CanonicalValue };

export function canonicalize(value: CanonicalValue): string {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value);
  }

  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalize(item)).join(',')}]`;
  }

  const keys = Object.keys(value).sort();
  const body = keys.map((key) => `${JSON.stringify(key)}:${canonicalize(value[key] as CanonicalValue)}`).join(',');
  return `{${body}}`;
}

export async function buildSha256Checksum(value: CanonicalValue): Promise<string> {
  const canonical = canonicalize(value);
  return Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, canonical);
}

export interface FinalizeChecksumRound {
  roundNumber: number;
  techniqueRed: number;
  presentationRed: number;
  techniqueBlue: number;
  presentationBlue: number;
}

export interface FinalizeChecksumInput {
  matchId: string;
  sessionId: string;
  stationId: string;
  judgeName: string;
  totalEvents: number;
  lastSequence: number;
  finalScoreRed: number;
  finalScoreBlue: number;
  rounds: FinalizeChecksumRound[];
}

/** Scores travel in the checksum as strings with exactly 2 decimals ("8.85"), never as floats. */
export function formatScore2(value: number): string {
  return (Math.round(value * 100) / 100).toFixed(2);
}

/**
 * Canonical finalize payload of one judge, rebuilt by the backend from its own events
 * (backend/src/tkd_scorer/domain/services/finalization_checksum.py). The checksum is the SHA-256 (hex) of
 * canonicalize(payload): keys sorted, compact, scores as 2-decimal strings, rounds sorted by number.
 */
export function buildFinalizeChecksumPayload(input: FinalizeChecksumInput): { [key: string]: CanonicalValue } {
  return {
    matchId: input.matchId,
    sessionId: input.sessionId,
    stationId: input.stationId,
    judgeName: input.judgeName,
    totalEvents: input.totalEvents,
    lastSequence: input.lastSequence,
    finalScoreRed: formatScore2(input.finalScoreRed),
    finalScoreBlue: formatScore2(input.finalScoreBlue),
    rounds: [...input.rounds]
      .sort((a, b) => a.roundNumber - b.roundNumber)
      .map((round) => ({
        roundNumber: round.roundNumber,
        techniqueRed: formatScore2(round.techniqueRed),
        presentationRed: formatScore2(round.presentationRed),
        techniqueBlue: formatScore2(round.techniqueBlue),
        presentationBlue: formatScore2(round.presentationBlue)
      }))
  };
}
