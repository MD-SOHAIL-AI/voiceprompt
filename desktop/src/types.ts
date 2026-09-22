export type NavItem = 'home' | 'history' | 'models' | 'providers' | 'performance' | 'dictionary' | 'settings';
export type EngineMode = 'local' | 'cloud' | 'auto';
export type BillingTier = 'free' | 'paid' | 'quota' | 'local' | 'unknown';

export interface ProviderDescriptor {
  id: string;
  name: string;
  description: string;
  kind: 'local' | 'cloud' | 'custom';
  connected: boolean;
  configurable: boolean;
  supportsTranscription: boolean;
  supportsCleanup: boolean;
  baseUrl?: string;
}

export interface ModelDescriptor {
  id: string;
  name: string;
  provider: string;
  capabilities: string[];
  billing: BillingTier;
  priceLabel?: string;
  contextLabel?: string;
  description?: string;
  installed?: boolean;
  recommended?: boolean;
  metadata?: Record<string, unknown>;
}

export interface TranscriptRecord {
  id: string;
  text: string;
  createdAt: string;
  audioDurationMs: number;
  transcriptionMs: number;
  cleanupMs: number;
  pasteMs: number;
  totalMs: number;
  provider: string;
  model: string;
  language: string;
  costUsd?: number | null;
  targetApp?: string | null;
  source: 'local' | 'cloud';
}

export interface MetricsSummary {
  promptsToday: number;
  audioTodayMs: number;
  avgLatencyMs: number;
  p95LatencyMs: number;
  localShare: number;
  fastestProvider?: string;
}

export interface AppSettings {
  engineMode: EngineMode;
  transcriptionProvider: string;
  transcriptionModel: string;
  cleanupEnabled: boolean;
  cleanupProvider: string;
  cleanupModel: string;
  hotkey: string;
  recordingMode: 'ptt' | 'toggle';
  language: string;
  soundFeedback: boolean;
  launchAtStartup: boolean;
  overlayEnabled: boolean;
  overlayPosition: 'bottom-center' | 'bottom-right' | 'top-center' | 'remember';
  overlayVisibility: 'always' | 'recording' | 'hidden-idle';
  overlaySize: 'compact' | 'comfortable';
  historyEnabled: boolean;
  historyRetentionDays: number;
  autoPaste: boolean;
  restoreTargetFocus: boolean;
  theme: 'dark' | 'light' | 'system';
  customReplacements: Record<string, string>;
}

export interface BootstrapPayload {
  settings: AppSettings;
  providers: ProviderDescriptor[];
  recent: TranscriptRecord[];
  metrics: MetricsSummary;
}

export interface AccuracyScore {
  recordId: string;
  referenceText: string;
  hypothesisText: string;
  wer: number;
  cer: number;
  provider: string;
  model: string;
  scoredAt: string;
}

export interface EngineEvent {
  kind: 'status' | 'waveform' | 'result' | 'error' | 'ready';
  status?: 'idle' | 'recording' | 'transcribing' | 'cleaning' | 'success' | 'error';
  level?: number;
  result?: TranscriptRecord;
  message?: string;
}

export interface EngineProfile {
  engineMode: EngineMode;
  transcriptionProvider: string;
  transcriptionModel: string;
  cleanupEnabled: boolean;
  cleanupProvider: string;
  cleanupModel: string;
  language: string;
  hotkey: string;
  recordingMode: 'ptt' | 'toggle';
  soundFeedback: boolean;
  autoPaste: boolean;
  restoreTargetFocus: boolean;
  customReplacements: Record<string, string>;
}
