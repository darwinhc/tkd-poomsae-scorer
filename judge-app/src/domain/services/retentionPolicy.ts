import type { Match } from '@/domain/models/entities';

export function selectMatchesToDelete(matches: Match[], retainedMatchesCount: number): string[] {
  const sorted = [...matches].sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt));
  const protectedMatches = sorted.filter((m) => m.status === 'active');
  const keep = new Set<string>(protectedMatches.map((m) => m.id));

  for (const match of sorted) {
    if (keep.size >= retainedMatchesCount) {
      break;
    }
    keep.add(match.id);
  }

  return sorted.filter((m) => !keep.has(m.id)).map((m) => m.id);
}
