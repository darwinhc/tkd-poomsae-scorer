import { create } from 'zustand';
import type { Match } from '@/domain/models/entities';

interface SyncState {
  pending: number;
  sent: number;
  failed: number;
  lastSyncAt?: string;
}

interface AppState {
  bootstrapped: boolean;
  needsJudgeSetup: boolean;
  hasSession: boolean;
  activeMatch: Match | null;
  wsStatus: 'disconnected' | 'connecting' | 'connected';
  settingsVersion: number;
  sync: SyncState;
  setBoot(data: { bootstrapped: boolean; needsJudgeSetup: boolean; hasSession: boolean; activeMatch: Match | null }): void;
  setWsStatus(status: 'disconnected' | 'connecting' | 'connected'): void;
  setActiveMatch(match: Match | null): void;
  setSync(sync: Partial<SyncState>): void;
  bumpSettingsVersion(): void;
}

export const useAppStore = create<AppState>((set) => ({
  bootstrapped: false,
  needsJudgeSetup: true,
  hasSession: false,
  activeMatch: null,
  wsStatus: 'disconnected',
  settingsVersion: 0,
  sync: {
    pending: 0,
    sent: 0,
    failed: 0,
    lastSyncAt: undefined
  },
  setBoot(data) {
    set(data);
  },
  setWsStatus(status) {
    set({ wsStatus: status });
  },
  setActiveMatch(match) {
    set({ activeMatch: match });
  },
  setSync(sync) {
    set((state) => ({
      sync: {
        ...state.sync,
        ...sync
      }
    }));
  },
  bumpSettingsVersion() {
    set((state) => ({ settingsVersion: state.settingsVersion + 1 }));
  }
}));
