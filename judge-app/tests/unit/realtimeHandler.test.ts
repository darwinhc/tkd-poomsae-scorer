import { describe, expect, it } from 'vitest';
import { mapRealtimeEvent } from '@/domain/services/realtimeHandler';

describe('realtimeHandler', () => {
  it('maps a competitors update', () => {
    const result = mapRealtimeEvent({
      type: 'new_competitors',
      payload: {
        matchId: 'm1',
        competitorRedName: 'Competitor A',
        competitorBlueName: 'Competitor B'
      }
    });

    expect(result.action.type).toBe('competitors_by_color');
    if (result.action.type === 'competitors_by_color') {
      expect(result.action.redName).toBe('Competitor A');
      expect(result.action.blueName).toBe('Competitor B');
    }
  });

  it('stays compatible with the old left/right payload', () => {
    const result = mapRealtimeEvent({
      type: 'new_competitors',
      payload: {
        matchId: 'm1',
        competitorLeftName: 'Competitor A',
        competitorRightName: 'Competitor B'
      }
    });

    expect(result.action.type).toBe('competitors_by_color');
    if (result.action.type === 'competitors_by_color') {
      expect(result.action.redName).toBe('Competitor A');
      expect(result.action.blueName).toBe('Competitor B');
    }
  });

  it('maps the active match state by color', () => {
    const result = mapRealtimeEvent({
      type: 'active_match_state',
      payload: {
        hasActiveMatch: true,
        matchId: 'match-77',
        competitorRedName: 'Competitor C',
        competitorBlueName: 'Competitor D'
      }
    });

    expect(result.action.type).toBe('active_match_state');
    if (result.action.type === 'active_match_state') {
      expect(result.action.hasActiveMatch).toBe(true);
      expect(result.action.matchId).toBe('match-77');
      expect(result.action.redName).toBe('Competitor C');
      expect(result.action.blueName).toBe('Competitor D');
    }
  });

  it('maps active_match_state with snake_case and names by color', () => {
    const result = mapRealtimeEvent({
      type: 'active_match_state',
      payload: {
        has_active_match: true,
        match_id: 'match-88',
        competitor_red_name: 'Competitor C',
        competitor_blue_name: 'Competitor D'
      }
    } as any);

    expect(result.action.type).toBe('active_match_state');
    if (result.action.type === 'active_match_state') {
      expect(result.action.hasActiveMatch).toBe(true);
      expect(result.action.matchId).toBe('match-88');
      expect(result.action.redName).toBe('Competitor C');
      expect(result.action.blueName).toBe('Competitor D');
    }
  });

  it('maps active_match_state with left/right as name fallback', () => {
    const result = mapRealtimeEvent({
      type: 'active_match_state',
      payload: {
        active: true,
        matchId: 'match-89',
        competitor_left_name: 'Competitor C',
        competitor_right_name: 'Competitor D'
      }
    } as any);

    expect(result.action.type).toBe('active_match_state');
    if (result.action.type === 'active_match_state') {
      expect(result.action.redName).toBe('Competitor C');
      expect(result.action.blueName).toBe('Competitor D');
    }
  });

  it('maps match_updated as active match state', () => {
    const result = mapRealtimeEvent({
      type: 'match_updated',
      payload: {
        match: { id: 'mx-22', status: 'active' },
        competitors: {
          red: 'Competitor C',
          blue: 'Competitor D'
        }
      }
    });

    expect(result.action.type).toBe('active_match_state');
    if (result.action.type === 'active_match_state') {
      expect(result.action.hasActiveMatch).toBe(true);
      expect(result.action.matchId).toBe('mx-22');
      expect(result.action.redName).toBe('Competitor C');
      expect(result.action.blueName).toBe('Competitor D');
    }
  });

  it('maps match_updated with snake_case and a nested match', () => {
    const result = mapRealtimeEvent({
      type: 'match_updated',
      payload: {
        match: { match_id: 'mx-23', state: 'active' },
        competitors: {
          competitor_red_name: 'Competitor E',
          competitor_blue_name: 'Competitor F'
        }
      }
    } as any);

    expect(result.action.type).toBe('active_match_state');
    if (result.action.type === 'active_match_state') {
      expect(result.action.hasActiveMatch).toBe(true);
      expect(result.action.matchId).toBe('mx-23');
      expect(result.action.redName).toBe('Competitor E');
      expect(result.action.blueName).toBe('Competitor F');
    }
  });

  it('maps a judge settings update', () => {
    const result = mapRealtimeEvent({
      type: 'judge_settings_updated',
      payload: {
        defaultRounds: 3,
        defaultStartingScore: 4,
        presentationCategoryStartScore: 2,
        actionValue1: 0.1,
        actionValue2: 0.3
      }
    });

    expect(result.action.type).toBe('judge_settings_updated');
    if (result.action.type === 'judge_settings_updated') {
      expect(result.action.defaultRounds).toBe(3);
      expect(result.action.actionValue2).toBe(0.3);
    }
  });

  it('maps judge_settings_updated with snake_case', () => {
    const result = mapRealtimeEvent({
      type: 'judge_settings_updated',
      payload: {
        default_rounds: 4,
        default_starting_score: 4,
        presentation_category_start_score: 2,
        action_value_1: 0.2,
        action_value_2: 0.4
      }
    });

    expect(result.action.type).toBe('judge_settings_updated');
    if (result.action.type === 'judge_settings_updated') {
      expect(result.action.defaultRounds).toBe(4);
      expect(result.action.actionValue1).toBe(0.2);
      expect(result.action.actionValue2).toBe(0.4);
    }
  });

  it('maps judge_settings_updated with total_rounds as a rounds alias', () => {
    const result = mapRealtimeEvent({
      type: 'judge_settings_updated',
      payload: {
        total_rounds: 5
      }
    });

    expect(result.action.type).toBe('judge_settings_updated');
    if (result.action.type === 'judge_settings_updated') {
      expect(result.action.defaultRounds).toBe(5);
    }
  });

  it('maps round_changed with round_number', () => {
    const result = mapRealtimeEvent({
      type: 'round_changed',
      payload: {
        matchId: 'mx-1',
        round_number: 2
      }
    } as any);

    expect(result.action.type).toBe('round_changed');
    if (result.action.type === 'round_changed') {
      expect(result.action.round).toBe(2);
    }
  });

  it('maps judge_kicked as a revocation action', () => {
    const result = mapRealtimeEvent({
      type: 'judge_kicked',
      payload: {
        sessionId: 'sess-1',
        stationId: 'station-01'
      }
    });

    expect(result.action.type).toBe('judge_kicked');
  });

  it('maps pong to a no-op that is never persisted nor answered', () => {
    const mapped = mapRealtimeEvent({ type: 'pong', payload: {} });
    expect(mapped.action).toEqual({ type: 'pong' });
    expect(mapped.shouldPersist).toBe(false);
  });

  it('keeps the round number of a server reset_round', () => {
    const mapped = mapRealtimeEvent({ type: 'reset_round', payload: { matchId: 'm1', round: 2 } });
    expect(mapped.action).toEqual({ type: 'reset_round', matchId: 'm1', roundNumber: 2 });
  });
});

