import { create } from 'zustand';
import type { AppSettings, BootstrapPayload, EngineEvent, MetricsSummary, ProviderDescriptor, TranscriptRecord } from './types';

interface AppStore {
  ready: boolean;
  status: EngineEvent['status'];
  waveform: number[];
  settings: AppSettings | null;
  providers: ProviderDescriptor[];
  recent: TranscriptRecord[];
  metrics: MetricsSummary | null;
  hydrate: (payload: BootstrapPayload) => void;
  setSettings: (settings: AppSettings) => void;
  setProviders: (providers: ProviderDescriptor[]) => void;
  setRecent: (items: TranscriptRecord[]) => void;
  handleEngineEvent: (event: EngineEvent) => void;
}

export const useAppStore = create<AppStore>((set) => ({
  ready: false,
  status: 'idle',
  waveform: Array.from({ length: 32 }, () => 0.05),
  settings: null,
  providers: [],
  recent: [],
  metrics: null,
  hydrate: (payload) => set({ ready: true, settings: payload.settings, providers: payload.providers, recent: payload.recent, metrics: payload.metrics }),
  setSettings: (settings) => set({ settings }),
  setProviders: (providers) => set({ providers }),
  setRecent: (recent) => set({ recent }),
  handleEngineEvent: (event) => set((state) => {
    if (event.kind === 'waveform') {
      const level = Math.max(0.02, Math.min(1, event.level ?? 0));
      return { waveform: [...state.waveform.slice(1), level] };
    }
    if (event.kind === 'status') {
      return { status: event.status ?? state.status };
    }
    if (event.kind === 'result' && event.result) {
      return { status: 'success', recent: [event.result, ...state.recent].slice(0, 100) };
    }
    if (event.kind === 'error') {
      return { status: 'error' };
    }
    if (event.kind === 'ready') {
      return { status: 'idle' };
    }
    return {};
  }),
}));
