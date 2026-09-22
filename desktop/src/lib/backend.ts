import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import type {
  AccuracyScore,
  AppSettings,
  BootstrapPayload,
  EngineEvent,
  EngineProfile,
  ModelDescriptor,
  ProviderDescriptor,
  TranscriptRecord,
} from '../types';
import { demoBootstrap, demoModels } from './demo';

const isTauri = () => '__TAURI_INTERNALS__' in window;

export async function bootstrap(): Promise<BootstrapPayload> {
  if (!isTauri()) return structuredClone(demoBootstrap);
  return invoke<BootstrapPayload>('bootstrap_state');
}

export async function getHistory(query = '', limit = 100): Promise<TranscriptRecord[]> {
  if (!isTauri()) {
    return demoBootstrap.recent.filter((item) => item.text.toLowerCase().includes(query.toLowerCase()));
  }
  return invoke<TranscriptRecord[]>('get_history', { query, limit });
}

export async function deleteHistory(id: string): Promise<void> {
  if (!isTauri()) return;
  await invoke('delete_history', { id });
}

export async function clearHistory(): Promise<void> {
  if (!isTauri()) return;
  await invoke('clear_history');
}

export async function saveSettings(settings: AppSettings): Promise<void> {
  if (!isTauri()) return;
  await invoke('save_app_settings', { settings });
}

export async function listProviders(): Promise<ProviderDescriptor[]> {
  if (!isTauri()) return structuredClone(demoBootstrap.providers);
  return invoke<ProviderDescriptor[]>('provider_statuses');
}

export async function saveProviderCredential(provider: string, apiKey: string, baseUrl?: string): Promise<void> {
  if (!isTauri()) return;
  await invoke('save_provider_credential', { provider, apiKey, baseUrl: baseUrl ?? null });
}

export async function removeProviderCredential(provider: string): Promise<void> {
  if (!isTauri()) return;
  await invoke('remove_provider_credential', { provider });
}

export async function testProvider(provider: string): Promise<string> {
  if (!isTauri()) return 'Browser preview: connection test skipped';
  return invoke<string>('test_provider', { provider });
}

export async function listModels(provider: string, purpose: 'transcription' | 'cleanup' | 'all' = 'transcription'): Promise<ModelDescriptor[]> {
  if (!isTauri()) return demoModels.filter((model) => model.provider === provider || provider === 'all');
  return invoke<ModelDescriptor[]>('list_provider_models', { provider, purpose });
}

export async function applyEngineProfile(profile: EngineProfile): Promise<void> {
  if (!isTauri()) return;
  await invoke('apply_engine_profile', { profile });
}

export async function setOverlayVisible(visible: boolean): Promise<void> {
  if (!isTauri()) return;
  await invoke('set_overlay_visible', { visible });
}

export async function listenEngine(handler: (event: EngineEvent) => void): Promise<UnlistenFn> {
  if (!isTauri()) return () => undefined;
  return listen<EngineEvent>('engine-event', ({ payload }) => handler(payload));
}

export async function scoreHistory(recordId: string, referenceText: string): Promise<AccuracyScore> {
  if (!isTauri()) {
    const record = demoBootstrap.recent.find((item) => item.id === recordId)!;
    return { recordId, referenceText, hypothesisText: record?.text ?? '', wer: 0, cer: 0, provider: record?.provider ?? 'Demo', model: record?.model ?? 'Demo', scoredAt: new Date().toISOString() };
  }
  return invoke<AccuracyScore>('score_history', { recordId, referenceText });
}

export async function getAccuracyScores(): Promise<AccuracyScore[]> {
  if (!isTauri()) return [];
  return invoke<AccuracyScore[]>('get_accuracy_scores');
}
